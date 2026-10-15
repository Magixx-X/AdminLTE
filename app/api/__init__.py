import json
import re
import secrets
import time
import uuid
from pathlib import Path
from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy import select, func, delete
from argon2.exceptions import VerificationError
from app.models import *
from app.repositories import audit, limit
from app.security import AppError, require, password, hasher, digest, permissions, scopes, template_access, task_access, csrf_token, cipher
from app.services.parameters import parse_params, months
from app.services.templates import editable, version_for, new_version, template_json

api = Blueprint('api', __name__, url_prefix='/api')


def ok(data=None, status=200):
    return jsonify(success=True, data=data, error=None), status


def body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise AppError('JSON', '请求体必须是 JSON 对象')
    return value


def repo():
    return current_app.extensions['repo']


def template(db, tid):
    if type(tid) is not int or tid < 1:
        raise AppError('PARAMETERS', '模板 ID 必须为正整数')
    item = db.get(Template, tid)
    if not item or item.deleted:
        raise AppError('NOT_FOUND', '模板不存在', 404)
    return item


def task_json(item):
    return {k: getattr(item, k) for k in ('id', 'group_id', 'user_id', 'template_id', 'version_id', 'month', 'params_summary', 'status', 'error_code', 'error', 'row_count', 'truncated', 'columns', 'created_at', 'started_at', 'finished_at', 'duration')}


def export_json(item):
    return {k: getattr(item, k) for k in ('id', 'group_id', 'status', 'size', 'row_count', 'created_at', 'expires', 'error')}


def integer_arg(name, default, minimum=0, maximum=10000000):
    try:
        value = int(request.args.get(name, default))
        if not minimum <= value <= maximum:
            raise ValueError()
        return value
    except ValueError:
        raise AppError('PARAMETERS', name + ' 范围无效')


@api.get('/auth/csrf')
def csrf():
    return ok({'csrf_token': csrf_token()})


@api.post('/auth/login')
def login():
    data = body()
    username, supplied = data.get('username', ''), data.get('password', '')
    if not isinstance(username, str) or not isinstance(supplied, str) or len(username) > 80 or len(supplied) > 128:
        raise AppError('CREDENTIALS', '账号或密码错误', 401)
    timestamp = time.time()
    ratekey = digest(username.casefold())
    error = None
    with repo().transaction() as db:
        db.execute(delete(LoginAttempt).where(LoginAttempt.timestamp < timestamp - limit(db, current_app.config, 'LOGIN_WINDOW')))
        count = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == ratekey))
        if count >= limit(db, current_app.config, 'LOGIN_LIMIT'):
            error = AppError('LOGIN_LIMIT', '登录失败次数过多，请稍后重试', 429)
        else:
            user = db.scalar(select(User).where(User.username == username))
            valid = False
            try:
                valid = hasher.verify(user.password_hash if user else current_app.extensions['dummy_hash'], supplied)
            except VerificationError:
                pass
            if not user or not user.enabled or not valid:
                db.add(LoginAttempt(key=ratekey, timestamp=timestamp))
                audit(db, 'auth.login', user.id if user else None, result='FAILED')
                error = AppError('CREDENTIALS', '账号或密码错误', 401)
            else:
                db.execute(delete(LoginAttempt).where(LoginAttempt.key == ratekey))
                token, csrfvalue = secrets.token_hex(32), secrets.token_hex(32)
                session_seconds = limit(db, current_app.config, 'SESSION_SECONDS')
                db.add(AuthSession(token_hash=digest(token), user_id=user.id, epoch=user.auth_epoch,
                    expires=timestamp + session_seconds, csrf=csrfvalue))
                audit(db, 'auth.login', user.id)
    if error:
        raise error
    response = jsonify(success=True, data={'csrf_token': csrfvalue}, error=None)
    response.set_cookie('hqs_auth', token, httponly=True, secure=current_app.config['SESSION_COOKIE_SECURE'],
                        samesite='Lax', max_age=session_seconds)
    return response


@api.post('/auth/logout')
@require()
def logout():
    with repo().transaction() as db:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == g.auth.token_hash))
        audit(db, 'auth.logout', g.user.id)
    response = jsonify(success=True, data=None, error=None)
    response.delete_cookie('hqs_auth')
    return response


@api.get('/auth/me')
@require()
def me():
    with repo().transaction() as db:
        return ok({'id': g.user.id, 'username': g.user.username, 'nickname': g.user.nickname, 'contact': g.user.contact,
                   'permissions': sorted(g.permissions), 'scopes': scopes(db, g.user.id), 'csrf_token': g.auth.csrf, 'source': current_app.extensions['provider'].source})


@api.put('/auth/profile')
@require()
def profile_update():
    data = body()
    if set(data) - {'nickname', 'contact'}:
        raise AppError('PROFILE', '只能修改昵称和联系方式')
    with repo().transaction() as db:
        user = db.get(User, g.user.id)
        assign_profile(user, data)
        audit(db, 'auth.profile_update', user.id)
    return ok()


@api.post('/auth/password')
@require()
def change_password():
    data = body()
    old = data.get('current_password')
    if not isinstance(old, str) or not 1 <= len(old) <= 128:
        raise AppError('PASSWORD', '请输入当前密码')
    new = data.get('new_password')
    if not isinstance(new, str) or not 6 <= len(new) <= 128:
        raise AppError('PASSWORD_POLICY', '密码长度必须为 6–128 字符')
    if new != data.get('confirm_password'):
        raise AppError('PASSWORD', '两次输入的新密码不一致')
    timestamp, ratekey, error = time.time(), digest('password-change:' + str(g.user.id)), None
    with repo().transaction() as db:
        user = db.get(User, g.user.id)
        db.execute(delete(LoginAttempt).where(LoginAttempt.timestamp < timestamp - limit(db, current_app.config, 'LOGIN_WINDOW')))
        count = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key == ratekey))
        if count >= limit(db, current_app.config, 'LOGIN_LIMIT'):
            error = AppError('PASSWORD_LIMIT', '当前密码错误次数过多，请稍后重试', 429)
        else:
            valid = False
            try:
                valid = hasher.verify(user.password_hash, old)
            except VerificationError:
                pass
            if not valid:
                db.add(LoginAttempt(key=ratekey, timestamp=timestamp))
                audit(db, 'auth.password_change', user.id, result='FAILED')
                error = AppError('PASSWORD', '当前密码错误')
            elif user.auth_epoch != g.auth.epoch:
                error = AppError('UNAUTHENTICATED', '会话已过期，请重新登录', 401)
            else:
                user.password_hash, user.auth_epoch = password(new), user.auth_epoch + 1
                db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
                db.execute(delete(LoginAttempt).where(LoginAttempt.key == ratekey))
                audit(db, 'auth.password_change', user.id)
    if error:
        raise error
    response = jsonify(success=True, data=None, error=None)
    response.delete_cookie('hqs_auth')
    return response


@api.get('/dashboard')
@require()
def dashboard():
    with repo().transaction() as db:
        tasks = db.scalars(select(QueryTask).where(QueryTask.user_id == g.user.id).order_by(QueryTask.created_at.desc()).limit(10)).all()
        stats = dict(db.execute(select(QueryTask.status, func.count()).where(QueryTask.user_id == g.user.id).group_by(QueryTask.status)).all())
        heartbeat = db.get(Setting, 'worker_heartbeat')
        return ok({'recent': [task_json(t) for t in tasks], 'stats': stats,
                   'worker': heartbeat.value if heartbeat else None, 'source': current_app.extensions['provider'].source})


@api.get('/templates')
@require()
def list_templates():
    if not {'template:execute', 'template:edit', 'template:approve'} & g.permissions:
        raise AppError('FORBIDDEN', '没有查询管理权限', 403)
    with repo().transaction() as db:
        items = db.scalars(select(Template).where(Template.deleted == False).order_by(Template.id.desc())).all()
        data = []
        manage = request.args.get('manage') == '1' and ('template:edit' in g.permissions or 'template:approve' in g.permissions)
        for item in items:
            if request.args.get('q') and request.args['q'].lower() not in (item.name + item.category).lower():
                continue
            if request.args.get('category') and item.category != request.args['category']:
                continue
            if manage and (item.owner_id == g.user.id or 'template:approve' in g.permissions):
                data.append(template_json(db, item, True))
            elif item.status == 'PUBLISHED':
                try:
                    template_access(db, g.user.id, item.id, 'execute')
                    data.append(template_json(db, item))
                except AppError:
                    pass
        return ok(data)


@api.post('/templates')
@require('template:create')
def create_template():
    data = body()
    with repo().transaction() as db:
        if not isinstance(data.get('name'), str) or not 1 <= len(data['name'].strip()) <= 120:
            raise AppError('NAME', '模板名称必须为 1–120 字符')
        if data.get('copy_from'):
            source = template(db, data['copy_from'])
            editable(source, g.user.id, g.permissions)
            old = version_for(db, source)
            data.update(sql=old.sql, schema=old.schema, sort_fields=old.sort_fields, scope_policy=old.scope_policy)
        item = Template(name=data['name'].strip(), category=str(data.get('category', '报表'))[:80], description=str(data.get('description', ''))[:2000], owner_id=g.user.id)
        db.add(item)
        db.flush()
        new_version(db, item, data, g.user.id)
        return ok(template_json(db, item, True), 201)


@api.put('/templates/<int:tid>')
@require('template:edit')
def edit_template(tid):
    data = body()
    with repo().transaction() as db:
        item = template(db, tid)
        editable(item, g.user.id, g.permissions)
        if item.status == 'REVIEW':
            raise AppError('STATE', '审核期间不能编辑', 409)
        if data.get('expected_version') != item.latest_version:
            raise AppError('VERSION_CONFLICT', '版本已更新，请重新加载', 409)
        if not isinstance(data.get('name'), str) or not 1 <= len(data['name'].strip()) <= 120:
            raise AppError('NAME', '名称无效')
        item.name = data['name'].strip()
        item.category = str(data.get('category', item.category))[:80]
        item.description = str(data.get('description', item.description))[:2000]
        item.latest_version += 1
        item.status = 'DRAFT'
        new_version(db, item, data, g.user.id)
        return ok(template_json(db, item, True))


@api.delete('/templates/<int:tid>')
@require('template:edit')
def delete_template(tid):
    with repo().transaction() as db:
        item = template(db, tid)
        editable(item, g.user.id, g.permissions)
        item.deleted, item.status = True, 'DISABLED'
        audit(db, 'template.delete', g.user.id, template_id=tid)
    return ok()


@api.post('/templates/<int:tid>/submit')
@require('template:edit')
def submit(tid):
    with repo().transaction() as db:
        item = template(db, tid)
        editable(item, g.user.id, g.permissions)
        if item.status != 'DRAFT':
            raise AppError('STATE', '只有草稿可以提交审核', 409)
        item.status = 'REVIEW'
        audit(db, 'template.submit', g.user.id, template_id=tid)
    return ok()


@api.post('/templates/<int:tid>/publish')
@require('template:approve')
def publish(tid):
    data = body()
    with repo().transaction() as db:
        item = template(db, tid)
        if item.status != 'REVIEW':
            raise AppError('STATE', '仅审核中模板可以发布', 409)
        version = version_for(db, item)
        if data.get('scope_reviewed') is not True:
            raise AppError('SCOPE_REVIEW', '审核人必须确认范围绑定及数据库授权视图安全')
        if current_app.extensions['provider'].source == 'oracle':
            if data.get('hospital_validated') is not True or not str(data.get('evidence', '')).strip():
                raise AppError('HOSPITAL_VALIDATION', '必须提交真实医院验收证据，不能用 Mock 通过代替', 409)
            version.validation = 'HOSPITAL_VALIDATED'
        version.reviewer_id, version.reviewed_at = g.user.id, now()
        item.published_version, item.status = version.number, 'PUBLISHED'
        audit(db, 'template.publish', g.user.id, template_id=tid, version_id=version.id,
              detail={'validation': version.validation, 'evidence': str(data.get('evidence', 'Mock only'))[:500]})
    return ok()


@api.post('/templates/<int:tid>/disable')
@require('template:approve')
def disable(tid):
    with repo().transaction() as db:
        item = template(db, tid)
        item.status = 'DISABLED'
        audit(db, 'template.disable', g.user.id, template_id=tid)
    return ok()


@api.get('/templates/<int:tid>/versions')
@require('template:edit')
def versions(tid):
    with repo().transaction() as db:
        editable(template(db, tid), g.user.id, g.permissions)
        items = db.scalars(select(TemplateVersion).where(TemplateVersion.template_id == tid).order_by(TemplateVersion.number.desc()))
        return ok([{k: getattr(v, k) for k in ('id', 'number', 'sql', 'schema', 'sort_fields', 'scope_policy', 'summary', 'reviewer_id', 'reviewed_at', 'validation', 'created_at')} for v in items])


@api.post('/queries')
@require('template:execute')
def query(data=None):
    data = body() if data is None else data
    if type(data.get('template_id')) is not int or data['template_id'] < 1:
        raise AppError('PARAMETERS', 'template_id 必须为正整数')
    with repo().transaction() as db:
        # SQLite serializes this short write transaction: capacity checks and inserts are atomic.
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        item = template_access(db, g.user.id, data.get('template_id'), 'execute')
        if item.status != 'PUBLISHED':
            raise AppError('STATE', '只能执行已发布模板', 409)
        version = version_for(db, item, True)
        source = current_app.extensions['provider'].identity(db, required=True)
        if source[0] == 'oracle' and version.validation != 'HOSPITAL_VALIDATED':
            raise AppError('HOSPITAL_VALIDATION', '模板尚未经真实医院验收', 409)
        supplied = data.get('params', {})
        parsed = parse_params(version.schema, supplied)
        periods = months(supplied.get('month_start'), supplied.get('month_end'), limit(db, current_app.config, 'MAX_MONTHS'))
        ranges = scopes(db, g.user.id)
        if not ranges:
            raise AppError('SCOPE', '账号未获数据范围授权（管理员也必须单独授权）', 403)
        pending = db.scalar(select(func.count()).select_from(QueryTask).where(QueryTask.status == 'PENDING'))
        if pending + len(periods) > limit(db, current_app.config, 'QUEUE_LIMIT'):
            raise AppError('QUEUE_FULL', '查询队列已满，请稍后重试', 409)
        group = str(uuid.uuid4())
        result = []
        for period in periods:
            tid = str(uuid.uuid4())
            payload = cipher(current_app.config).encrypt(json.dumps(parsed, ensure_ascii=False).encode()).decode()
            task = QueryTask(id=tid, group_id=group, user_id=g.user.id, template_id=item.id, version_id=version.id, month=period,
                payload=payload, params_summary={'names': sorted(k for k, v in parsed.items() if v is not None), 'month': period, 'source': source}, scopes=ranges)
            db.add(task)
            audit(db, 'query.submit', g.user.id, template_id=item.id, version_id=version.id, task_id=tid)
            result.append(tid)
        return ok({'group_id': group, 'task_id': result[0], 'task_ids': result}, 202)


@api.post('/queries/<tid>/retry')
@require('template:execute')
def retry_query(tid):
    with repo().transaction() as db:
        item = db.get(QueryTask, tid)
        task_access(db, item, g.user.id, 'execute')
        values = json.loads(cipher(current_app.config).decrypt(item.payload.encode()))
        values.update(month_start=item.month, month_end=item.month)
        data = {'template_id': item.template_id, 'params': values}
    return query(data)


@api.get('/queries/history')
@require('history:view')
def history():
    with repo().transaction() as db:
        stmt = select(QueryTask).where(QueryTask.user_id == g.user.id)
        if request.args.get('user_id') and integer_arg('user_id', g.user.id, 1) != g.user.id:
            raise AppError('OWNER_FORBIDDEN', '任务历史仅允许查看本人', 403)
        for field in ('template_id', 'status', 'group_id'):
            if request.args.get(field):
                stmt = stmt.where(getattr(QueryTask, field) == request.args[field])
        for field, op in (('date_from', 'ge'), ('date_to', 'lt')):
            if request.args.get(field):
                value = request.args[field]
                stmt = stmt.where(QueryTask.created_at >= value) if op == 'ge' else stmt.where(QueryTask.created_at < value)
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        items = db.scalars(stmt.order_by(QueryTask.created_at.desc()).offset(integer_arg('start', 0)).limit(integer_arg('length', 100, 1, 200)))
        return ok({'items': [task_json(t) for t in items], 'total': total})


@api.get('/queries/<tid>')
@require('result:view')
def query_status(tid):
    with repo().transaction() as db:
        item = db.get(QueryTask, tid)
        task_access(db, item, g.user.id)
        return ok(task_json(item))


@api.get('/queries/<tid>/results')
@require('result:view')
def results(tid):
    with repo().transaction() as db:
        item = db.get(QueryTask, tid)
        task_access(db, item, g.user.id)
        if item.status != 'SUCCEEDED':
            raise AppError('STATE', '查询尚未成功完成', 409)
        version = db.get(TemplateVersion, item.version_id)
        sort = request.args.get('sort', '')
        if sort and sort not in version.sort_fields:
            raise AppError('SORT', '排序字段未获批准')
        direction = request.args.get('direction', 'asc')
        if direction not in ('asc', 'desc'):
            raise AppError('SORT', '排序方向无效')
        start = integer_arg('start', 0)
        length = integer_arg('length', 100, 1, limit(db, current_app.config, 'MAX_PAGE_SIZE'))
        from app.tasks.cache import get_page
        page = get_page(current_app, tid, start, length, sort, direction)
        page.update(draw=integer_arg('draw', 0), recordsTotal=item.row_count, recordsFiltered=item.row_count, truncated=item.truncated,
                    warning='仅在配额内的预览排序；正式 SQL 必须具备稳定 ORDER BY')
        return ok(page)


@api.post('/queries/<tid>/cancel')
@require('task:cancel')
def cancel(tid):
    with repo().transaction() as db:
        item = db.get(QueryTask, tid)
        task_access(db, item, g.user.id, 'execute')
        if item.status not in ('PENDING', 'RUNNING'):
            raise AppError('STATE', '任务已经结束', 409)
        item.cancel_requested = True
        if item.status == 'PENDING':
            item.status, item.finished_at = 'CANCELLED', now()
        audit(db, 'query.cancel', g.user.id, task_id=tid)
    return ok()


def group_access(db, group, action='export'):
    items = db.scalars(select(QueryTask).where(QueryTask.group_id == group).order_by(QueryTask.month)).all()
    if not items:
        raise AppError('NOT_FOUND', '查询批次不存在', 404)
    for task in items:
        task_access(db, task, g.user.id, action)
    return items


@api.post('/exports')
@require('result:export')
def export_create():
    data = body()
    with repo().transaction() as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        tasks = group_access(db, data.get('group_id'))
        if any(t.status != 'SUCCEEDED' for t in tasks):
            raise AppError('STATE', '请等待同批次所有月份查询成功', 409)
        active = db.scalar(select(func.count()).select_from(ExportRecord).where(ExportRecord.status.in_(['PENDING', 'RUNNING'])))
        if active >= limit(db, current_app.config, 'QUEUE_LIMIT'):
            raise AppError('QUEUE_FULL', '导出队列已满', 409)
        item = ExportRecord(id=str(uuid.uuid4()), user_id=g.user.id, group_id=data['group_id'], expires=time.time() + limit(db, current_app.config, 'EXPORT_TTL'))
        db.add(item)
        audit(db, 'export.submit', g.user.id, task_id=item.id)
        return ok(export_json(item), 202)


@api.get('/exports')
@require('result:export')
def export_list():
    with repo().transaction() as db:
        items = db.scalars(select(ExportRecord).where(ExportRecord.user_id == g.user.id).order_by(ExportRecord.created_at.desc()).limit(200))
        return ok([export_json(e) for e in items])


def accessible_export(db, eid):
    item = db.get(ExportRecord, eid)
    if not item:
        raise AppError('NOT_FOUND', '导出记录不存在', 404)
    if item.user_id != g.user.id:
        raise AppError('OWNER_FORBIDDEN', '不能访问他人文件', 403)
    group_access(db, item.group_id)
    return item


@api.get('/exports/<eid>')
@require('result:export')
def export_status(eid):
    with repo().transaction() as db:
        return ok(export_json(accessible_export(db, eid)))


@api.get('/exports/<eid>/download')
@require('result:export')
def download(eid):
    with repo().transaction() as db:
        item = accessible_export(db, eid)
        if item.expires < time.time():
            raise AppError('EXPIRED', '文件已经过期', 410)
        if item.status != 'SUCCEEDED' or not item.relative_path:
            raise AppError('STATE', '文件尚未生成或已删除', 409)
        root = Path(current_app.config['EXPORT_DIR']).resolve()
        path = (root / item.relative_path).resolve()
        if path.parent != root or not path.is_file():
            raise AppError('NOT_FOUND', '文件不存在', 404)
        audit(db, 'export.download', g.user.id, task_id=eid)
    return send_file(path, as_attachment=True, download_name='查询报表-' + eid + '.xlsx')


@api.delete('/exports/<eid>')
@require('result:export')
def export_delete(eid):
    with repo().transaction() as db:
        item = accessible_export(db, eid)
        if item.status in ('PENDING', 'RUNNING'):
            raise AppError('STATE', '正在生成，不能删除', 409)
        if item.relative_path:
            root = Path(current_app.config['EXPORT_DIR']).resolve()
            path = (root / item.relative_path).resolve()
            if path.parent == root:
                path.unlink(missing_ok=True)
        item.status, item.relative_path = 'DELETED', None
        audit(db, 'export.delete', g.user.id, task_id=eid)
    return ok()


@api.get('/admin/users')
@require('user:manage')
def users():
    with repo().transaction() as db:
        return ok([{'id': u.id, 'username': u.username, 'nickname': u.nickname, 'contact': u.contact,
                    'created_at': u.created_at, 'enabled': u.enabled,
                    'role_ids': list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == u.id))),
                    'scopes': list(db.scalars(select(UserDataScope.scope_code).where(UserDataScope.user_id == u.id)))}
                   for u in db.scalars(select(User).order_by(User.id))])


def assign_profile(user, data):
    for key, maximum in [('nickname', 80), ('contact', 120)]:
        if key in data:
            if not isinstance(data[key], str) or len(data[key]) > maximum:
                raise AppError('USER', '昵称或联系方式无效')
            setattr(user, key, data[key].strip())


def assign_user(db, user, data):
    assign_profile(user, data)
    if 'role_ids' in data:
        roleids = data['role_ids']
        if not isinstance(roleids, list) or len(roleids) > 1 or any(type(x) is not int or not db.get(Role, x) for x in roleids):
            raise AppError('ROLE', '请选择一个有效角色')
        if user.id == g.user.id and not any('user:manage' in set(db.scalars(select(RolePermission.permission).where(RolePermission.role_id == rid)))
                                          and db.get(Role, rid).enabled for rid in roleids):
            raise AppError('SELF_LOCKOUT', '不能撤销当前账号的用户管理权限', 409)
        db.execute(delete(UserRole).where(UserRole.user_id == user.id))
        for rid in set(roleids):
            db.add(UserRole(user_id=user.id, role_id=rid))
    if 'scopes' in data:
        if not isinstance(data['scopes'], list) or len(data['scopes']) > 1 or any(not isinstance(x, str) or not db.get(DataScope, x) for x in data['scopes']):
            raise AppError('SCOPE', '请选择一个有效用户部门（科室）')
        db.execute(delete(UserDataScope).where(UserDataScope.user_id == user.id))
        for code in set(data['scopes']):
            db.add(UserDataScope(user_id=user.id, scope_code=code))
    if 'enabled' in data:
        if not isinstance(data['enabled'], bool):
            raise AppError('PARAMETERS', 'enabled 必须为布尔值')
        if user.id == g.user.id and not data['enabled']:
            raise AppError('SELF_DISABLE', '不能禁用当前管理账号')
        user.enabled = data['enabled']
    if data.get('password'):
        user.password_hash = password(data['password'])
        user.auth_epoch += 1
    audit(db, 'user.update', g.user.id, detail={'target_user_id': user.id})


@api.post('/admin/users')
@require('user:manage')
def user_create():
    data = body()
    name = data.get('username', '')
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{3,80}', name):
        raise AppError('USERNAME', '账号须为 3–80 位英文、数字或 ._-')
    with repo().transaction() as db:
        if db.scalar(select(User).where(User.username == name)):
            raise AppError('CONFLICT', '账号已存在', 409)
        user = User(username=name, password_hash=password(data.get('password')))
        db.add(user)
        db.flush()
        assign_user(db, user, data)
        return ok({'id': user.id}, 201)


@api.put('/admin/users/<int:uid>')
@require('user:manage')
def user_update(uid):
    data = body()
    with repo().transaction() as db:
        user = db.get(User, uid)
        if not user:
            raise AppError('NOT_FOUND', '账号不存在', 404)
        assign_user(db, user, data)
    return ok()


@api.get('/admin/roles')
@require('role:manage')
def roles():
    with repo().transaction() as db:
        return ok({'roles': [{k: getattr(r, k) for k in ('id', 'name', 'code', 'enabled', 'created_at', 'remark')}
                             for r in db.scalars(select(Role).order_by(Role.id))]})


@api.post('/admin/roles')
@api.put('/admin/roles/<int:rid>')
@require('role:manage')
def role_save(rid=None):
    data = body()
    with repo().transaction() as db:
        name = data.get('name')
        if 'permissions' in data:
            raise AppError('ROLE', '请使用角色菜单授权接口')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise AppError('ROLE', '角色名或权限数组无效')
        name = name.strip()
        if db.scalar(select(Role).where(Role.name == name, Role.id != (rid or 0))):
            raise AppError('CONFLICT', '角色名已存在', 409)
        role = db.get(Role, rid) if rid else Role(name=name)
        if not role:
            raise AppError('NOT_FOUND', '角色不存在', 404)
        code = data.get('code', role.code or 'ROLE_' + secrets.token_hex(4))
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', code):
            raise AppError('ROLE', '角色标识须为英文、数字、下划线或短横线')
        if db.scalar(select(Role).where(Role.code == code, Role.id != (rid or 0))):
            raise AppError('CONFLICT', '角色标识已存在', 409)
        enabled = data.get('enabled', role.enabled if rid else True)
        remark = data.get('remark', role.remark or '')
        if type(enabled) is not bool or not isinstance(remark, str) or len(remark) > 500:
            raise AppError('ROLE', '角色状态或备注无效')
        if not enabled and rid and db.get(UserRole, (g.user.id, rid)):
            raise AppError('SELF_LOCKOUT', '不能停用当前账号所属角色', 409)
        role.name, role.code, role.enabled, role.remark = name.strip(), code, enabled, remark.strip()
        db.add(role)
        db.flush()
        audit(db, 'role.update', g.user.id, detail={'role_id': role.id})
        return ok({'id': role.id})


@api.delete('/admin/roles/<int:rid>')
@require('role:manage')
def role_delete(rid):
    with repo().transaction() as db:
        role = db.get(Role, rid)
        if not role:
            raise AppError('NOT_FOUND', '角色不存在', 404)
        if db.scalar(select(UserRole).where(UserRole.role_id == rid).limit(1)) or db.scalar(select(TemplatePermission).where(TemplatePermission.role_id == rid).limit(1)):
            raise AppError('IN_USE', '角色已被用户或模板授权引用，不能删除', 409)
        db.execute(delete(RolePermission).where(RolePermission.role_id == rid))
        db.delete(role)
        audit(db, 'role.delete', g.user.id, detail={'role_id': rid})
    return ok()


@api.get('/admin/grants')
@require('template:grant')
def grants():
    with repo().transaction() as db:
        return ok([{k: getattr(p, k) for k in ('id', 'template_id', 'user_id', 'role_id', 'execute', 'view', 'export')} for p in db.scalars(select(TemplatePermission))])


@api.post('/admin/grants')
@require('template:grant')
def grant_save():
    data = body()
    with repo().transaction() as db:
        template(db, data.get('template_id'))
        uid, rid = data.get('user_id'), data.get('role_id')
        if uid is not None and (type(uid) is not int or uid < 1) or rid is not None and (type(rid) is not int or rid < 1):
            raise AppError('GRANT', '授权 ID 必须为正整数')
        if bool(uid) == bool(rid) or uid and not db.get(User, uid) or rid and not db.get(Role, rid):
            raise AppError('GRANT', '必须选择一个有效用户或角色')
        if any(not isinstance(data.get(k, False), bool) for k in ('execute', 'view', 'export')):
            raise AppError('GRANT', '授权字段必须为布尔值')
        stmt = select(TemplatePermission).where(TemplatePermission.template_id == data['template_id'], TemplatePermission.user_id == uid, TemplatePermission.role_id == rid)
        item = db.scalar(stmt) or TemplatePermission(template_id=data['template_id'], user_id=uid, role_id=rid)
        for key in ('execute', 'view', 'export'):
            setattr(item, key, data.get(key, False))
        db.add(item)
        audit(db, 'template.grant', g.user.id, template_id=data['template_id'], detail={'user_id': uid, 'role_id': rid})
    return ok()


@api.post('/admin/scopes')
@require('department:manage')
def scope_create():
    data = body()
    if not isinstance(data.get('code'), str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', data['code']) or not isinstance(data.get('name'), str) or not 1 <= len(data['name']) <= 120:
        raise AppError('SCOPE', '范围代码或名称无效')
    with repo().transaction() as db:
        if db.get(DataScope, data['code']):
            raise AppError('CONFLICT', '范围已存在', 409)
        from app.api.platform import department_fields
        item = DataScope(code=data['code'], name=data['name'])
        department_fields(db, item, data)
        db.add(item)
        audit(db, 'scope.create', g.user.id, detail={'code': data['code']})
    return ok(status=201)


@api.get('/admin/audits')
@require('audit:view')
def audits():
    with repo().transaction() as db:
        stmt = select(AuditLog)
        module = request.args.get('module')
        if module:
            if module not in ('auth', 'user', 'role', 'menu', 'department', 'scope', 'connection', 'system', 'query', 'template', 'export', 'admin', 'mock'):
                raise AppError('PARAMETERS', '未知审计模块')
            stmt = stmt.where(AuditLog.action.like(module + '.%'))
        for name in ('action', 'user_id', 'template_id', 'task_id', 'result'):
            if request.args.get(name):
                stmt = stmt.where(getattr(AuditLog, name) == request.args[name])
        if request.args.get('date_from'):
            stmt = stmt.where(AuditLog.timestamp >= request.args['date_from'])
        if request.args.get('date_to'):
            stmt = stmt.where(AuditLog.timestamp < request.args['date_to'])
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        items = db.scalars(stmt.order_by(AuditLog.id.desc()).offset(integer_arg('start', 0)).limit(integer_arg('length', 100, 1, 200)))
        return ok({'total': total, 'items': [{k: getattr(a, k) for k in ('id', 'user_id', 'action', 'timestamp', 'template_id', 'version_id', 'task_id', 'result', 'duration', 'row_count', 'detail')} for a in items]})


QUERY_SETTINGS = {'MAX_MONTHS': (1, 120), 'QUERY_TIMEOUT': (1, 180), 'QUEUE_LIMIT': (1, 200), 'MAX_PAGE_SIZE': (1, 500),
            'MAX_PREVIEW_ROWS': (100, 50000), 'MAX_EXPORT_ROWS': (1, 2000000), 'MAX_EXPORT_BYTES': (1024, 500 * 1024 * 1024), 'EXPORT_TTL': (60, 604800)}


SETTINGS = {'SESSION_SECONDS': (300, 28800), 'LOGIN_LIMIT': (3, 20), 'LOGIN_WINDOW': (60, 3600), 'DISK_WARNING_BYTES': (104857600, 107374182400)}

@api.get('/admin/settings')
@require('system:configure')
def settings():
    with repo().transaction() as db:
        return ok({key: limit(db, current_app.config, key) for key in SETTINGS})


@api.put('/admin/settings')
@require('system:configure')
def settings_save():
    data = body()
    if set(data) - SETTINGS.keys():
        raise AppError('SETTINGS', '设置包含未知字段')
    with repo().transaction() as db:
        for key, value in data.items():
            low, high = SETTINGS[key]
            if type(value) is not int or not low <= value <= high:
                raise AppError('SETTINGS', f'{key} 必须为 {low}–{high} 的整数')
            item = db.get(Setting, key) or Setting(key=key)
            item.value = value
            db.add(item)
        audit(db, 'system.settings', g.user.id, detail={'keys': sorted(data)})
    return ok()


@api.get('/admin/health')
@require('monitor:view')
def health():
    import shutil
    with repo().transaction() as db:
        db.execute(select(1))
        heartbeat = db.get(Setting, 'worker_heartbeat')
        free_bytes = shutil.disk_usage(current_app.config['EXPORT_DIR']).free
        return ok({'database': 'OK', 'provider': current_app.extensions['provider'].health(),
                   'worker': heartbeat.value if heartbeat else None, 'free_disk_bytes': free_bytes,
                   'warnings': ['磁盘剩余空间低于预警阈值'] if free_bytes < limit(db, current_app.config, 'DISK_WARNING_BYTES') else [],
                   'query_concurrency': current_app.config['QUERY_CONCURRENCY'], 'export_concurrency': 1,
                   'oracle_pool_max': current_app.config['ORACLE_POOL_MAX'], 'hospital_validation': 'PENDING_HOSPITAL_VALIDATION'})


from app.api import platform  # register platform routes on the existing blueprint
from app.api import connections
