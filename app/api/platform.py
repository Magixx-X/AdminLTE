"""Platform administration; SQL functionality stays in its existing module."""
import platform
import sqlite3
import re
from importlib.metadata import version, PackageNotFoundError
from flask import current_app, g
from sqlalchemy import select, delete, func
from app.api import api, ok, body, repo, QUERY_SETTINGS
from app.config import ROOT
from app.models import Menu, Role, RolePermission, DataScope, UserDataScope, UserRole, User, AuthSession, Setting, DatabaseConnection
from app.navigation import PAGES, available
from app.repositories import audit, limit
from app.security import require, AppError


def menu_json(m):
    result = {k: getattr(m, k) for k in ('code', 'title', 'parent', 'icon', 'position', 'enabled')}
    result.update(kind='菜单' if m.parent else '目录', path='/pages/' + m.code if m.parent else '',
                  permission=', '.join(PAGES[m.code][2]) if m.code in PAGES else '')
    return result


@api.get('/navigation')
@require()
def navigation():
    with repo().transaction() as db:
        return ok([menu_json(m) for m in available(db, g.permissions)])


@api.get('/admin/menu-authorization')
@require('authorization:manage')
def authorization():
    with repo().transaction() as db:
        roles = []
        for role in db.scalars(select(Role).order_by(Role.id)):
            perms = set(db.scalars(select(RolePermission.permission).where(RolePermission.role_id == role.id)))
            roles.append(dict(id=role.id, name=role.name, menu_ids=[code for code, spec in PAGES.items() if set(spec[2]) <= perms]))
        return ok(dict(roles=roles, menus=[menu_json(m) for m in db.scalars(select(Menu).where(Menu.deleted == False).order_by(Menu.position))]))


@api.put('/admin/roles/<int:rid>/menus')
@require('authorization:manage')
def authorize(rid):
    values = body().get('menu_ids')
    if not isinstance(values, list) or any(not isinstance(x, str) or x not in PAGES for x in values):
        raise AppError('MENUS', '请选择有效子菜单')
    with repo().transaction() as db:
        if not db.get(Role, rid):
            raise AppError('NOT_FOUND', '角色不存在', 404)
        own_roles = set(db.scalars(select(UserRole.role_id).where(UserRole.user_id == g.user.id)))
        if rid in own_roles and 'authorization' not in values:
            raise AppError('SELF_LOCKOUT', '不能撤销当前账号所属角色的菜单授权入口，请由其他管理员操作', 409)
        db.execute(delete(RolePermission).where(RolePermission.role_id == rid))
        for perm in sorted({p for code in values for p in PAGES[code][2]}):
            db.add(RolePermission(role_id=rid, permission=perm))
        audit(db, 'role.menu_authorize', g.user.id, detail={'role_id': rid, 'menus': sorted(set(values))})
    return ok()


@api.get('/admin/menus')
@require('menu:manage')
def menus():
    with repo().transaction() as db:
        return ok([menu_json(m) for m in db.scalars(select(Menu).where(Menu.deleted == False).order_by(Menu.position, Menu.code))])


@api.get('/admin/menu-options')
@require('menu:manage')
def menu_options():
    with repo().transaction() as db:
        used = set(db.scalars(select(Menu.code).where(Menu.deleted == False)))
        return ok([dict(code=code, title=spec[1]) for code, spec in PAGES.items() if code not in used])


@api.post('/admin/menus')
@api.put('/admin/menus/<code>')
@require('menu:manage')
def menu_save(code=None):
    data = body()
    if (not isinstance(data.get('title'), str) or not 1 <= len(data['title'].strip()) <= 80
            or any(c in data['title'] for c in '<>&\"\'')
            or type(data.get('position')) is not int or not 0 <= data['position'] <= 9999
            or type(data.get('enabled')) is not bool):
        raise AppError('MENU', '菜单名称、排序或启用状态无效')
    with repo().transaction() as db:
        creating = code is None
        code = data.get('code') if creating else code
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', code):
            raise AppError('MENU', '菜单标识无效')
        m = db.get(Menu, code)
        if creating:
            if m and not m.deleted:
                raise AppError('CONFLICT', '菜单标识已存在', 409)
            if data.get('parent') and code not in PAGES:
                raise AppError('MENU', '请选择已实现的工作页面')
            if not data.get('parent') and code in PAGES:
                raise AppError('MENU', '工作页面必须归入目录')
            m = m or Menu(code=code)
            m.parent = data.get('parent') or None
            m.deleted = False
        elif not m or m.deleted:
            raise AppError('NOT_FOUND', '菜单不存在', 404)
        if code in ('menus', 'authorization', 'system', 'permissions') and not data['enabled']:
            raise AppError('MENU', '管理与授权入口必须保留')
        if m.parent:
            with db.no_autoflush:
                parent = db.get(Menu, data.get('parent')) if isinstance(data.get('parent'), str) else None
            if not parent or parent.parent or parent.deleted:
                raise AppError('MENU', '子菜单只能归入一级菜单')
            if code in ('menus', 'authorization') and parent.code not in ('system', 'permissions'):
                raise AppError('MENU', '管理入口必须位于受保护管理目录')
            m.parent = parent.code
        m.title, m.position, m.enabled = data['title'].strip(), data['position'], data['enabled']
        db.add(m)
        audit(db, 'menu.create' if creating else 'menu.update', g.user.id, detail={'code': code})
    return ok(status=201 if creating else 200)


@api.delete('/admin/menus/<code>')
@require('menu:manage')
def menu_delete(code):
    with repo().transaction() as db:
        item = db.get(Menu, code)
        if not item or item.deleted:
            raise AppError('NOT_FOUND', '菜单不存在', 404)
        if code in ('menus', 'authorization', 'system', 'permissions'):
            raise AppError('MENU', '管理与授权入口必须保留', 409)
        if db.scalar(select(Menu).where(Menu.parent == code, Menu.deleted == False).limit(1)):
            raise AppError('IN_USE', '请先删除目录下的子菜单', 409)
        item.deleted = True
        audit(db, 'menu.delete', g.user.id, detail={'code': code})
    return ok()


@api.get('/admin/user-options')
@require('user:manage')
def user_options():
    with repo().transaction() as db:
        return ok(dict(roles=[dict(id=r.id, name=r.name, enabled=r.enabled) for r in db.scalars(select(Role))],
                       scopes=[department_json(d) for d in db.scalars(select(DataScope).order_by(DataScope.position, DataScope.code))]))


@api.get('/admin/grant-options')
@require('template:grant')
def grant_options():
    from app.models import Template
    with repo().transaction() as db:
        return ok(dict(templates=[dict(id=t.id, name=t.name) for t in db.scalars(select(Template).where(Template.deleted == False))],
                       roles=[dict(id=r.id, name=r.name) for r in db.scalars(select(Role))],
                       users=[dict(id=u.id, name=u.username) for u in db.scalars(select(User))]))


@api.get('/admin/departments')
@require('department:manage')
def departments():
    with repo().transaction() as db:
        return ok([department_json(d) for d in db.scalars(select(DataScope).order_by(DataScope.position, DataScope.code))])


def department_json(item):
    return {k: getattr(item, k) for k in ('code', 'name', 'parent', 'position', 'enabled', 'remark', 'created_at')}


def department_fields(db, item, data):
    name = data.get('name', item.name)
    parent = data.get('parent', item.parent) or None
    position = data.get('position', item.position or 0)
    enabled = data.get('enabled', item.enabled if item.enabled is not None else True)
    remark = data.get('remark', item.remark or '')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or type(position) is not int or not 0 <= position <= 9999:
        raise AppError('DEPARTMENT', '部门名称或排序无效')
    if type(enabled) is not bool or not isinstance(remark, str) or len(remark) > 500:
        raise AppError('DEPARTMENT', '部门状态或备注无效')
    if parent is not None and (not isinstance(parent, str) or not db.get(DataScope, parent)):
        raise AppError('DEPARTMENT', '上级部门不存在')
    ancestor, visited = parent, {item.code}
    while ancestor:
        if ancestor in visited:
            raise AppError('DEPARTMENT', '上级部门不能是自身或下级部门')
        visited.add(ancestor)
        ancestor = db.get(DataScope, ancestor).parent
    item.name, item.parent, item.position, item.enabled, item.remark = name.strip(), parent, position, enabled, remark.strip()


@api.put('/admin/departments/<code>')
@require('department:manage')
def department_update(code):
    data = body()
    with repo().transaction() as db:
        item = db.get(DataScope, code)
        if not item:
            raise AppError('NOT_FOUND', '部门不存在', 404)
        department_fields(db, item, data)
        audit(db, 'department.update', g.user.id, detail={'code': code})
    return ok()


@api.delete('/admin/departments/<code>')
@require('department:manage')
def department_delete(code):
    from app.models import QueryTask
    with repo().transaction() as db:
        item = db.get(DataScope, code)
        if not item:
            raise AppError('NOT_FOUND', '部门不存在', 404)
        if (db.scalar(select(DataScope).where(DataScope.parent == code).limit(1))
                or db.scalar(select(UserDataScope).where(UserDataScope.scope_code == code).limit(1))
                or any(code in row for row in db.scalars(select(QueryTask.scopes)))):
            raise AppError('IN_USE', '部门包含下级部门或已被用户、历史任务引用，不能删除', 409)
        db.delete(item)
        audit(db, 'department.delete', g.user.id, detail={'code': code})
    return ok()


@api.get('/admin/query-settings')
@require('query:configure')
def query_settings():
    with repo().transaction() as db:
        return ok({key: limit(db, current_app.config, key) for key in QUERY_SETTINGS})


@api.put('/admin/query-settings')
@require('query:configure')
def query_settings_save():
    data = body()
    if set(data) - QUERY_SETTINGS.keys():
        raise AppError('SETTINGS', '未知查询配置')
    with repo().transaction() as db:
        for key, value in data.items():
            low, high = QUERY_SETTINGS[key]
            if type(value) is not int or not low <= value <= high:
                raise AppError('SETTINGS', f'{key} 必须为 {low}–{high} 的整数')
            item = db.get(Setting, key) or Setting(key=key)
            item.value = value
            db.add(item)
        audit(db, 'query.settings', g.user.id, detail={'keys': sorted(data)})
    return ok()


@api.get('/admin/monitor')
@require('monitor:view')
def monitor():
    import time
    import shutil
    with repo().transaction() as db:
        heartbeat = db.get(Setting, 'worker_heartbeat')
        free = shutil.disk_usage(current_app.config['DATA_DIR']).free
        connection_counts = dict(db.execute(select(DatabaseConnection.last_test_status, func.count()).where(
            DatabaseConnection.enabled == True).group_by(DatabaseConnection.last_test_status)).all())
        connection_summary = '启用 {} 项，通过 {} 项，未通过 {} 项，未测试 {} 项（已保存配置的最近测试）'.format(
            sum(connection_counts.values()), connection_counts.get('PASSED', 0), connection_counts.get('FAILED', 0), connection_counts.get('UNTESTED', 0))
        return ok(dict(database='SQLite · 正常', users=db.scalar(select(func.count()).select_from(User)),
                       active_sessions=db.scalar(select(func.count()).select_from(AuthSession).join(User).where(
                           AuthSession.expires > time.time(), User.enabled == True, AuthSession.epoch == User.auth_epoch)),
                       worker='在线' if heartbeat and time.time() - heartbeat.value['timestamp'] < 20 else '未启动 / 心跳过期',
                       free_disk_bytes=free, disk_warning=free < limit(db, current_app.config, 'DISK_WARNING_BYTES'),
                       environment=current_app.config['APP_ENV'], source=current_app.config['DATA_SOURCE'], connection_tests=connection_summary))


@api.get('/about')
@require('about:view')
def about():
    def dependencies(filename):
        result = []
        for line in (ROOT / filename).read_text(encoding='utf-8-sig').splitlines():
            if '==' not in line or line.startswith('#'):
                continue
            name, pinned = line.split('==', 1)
            try:
                installed = version(name)
            except PackageNotFoundError:
                installed = '未安装（当前环境）'
            result.append(dict(name=name, version=pinned, installed=installed))
        return result
    return ok(dict(platform=[dict(name='信息查询管理', version=(ROOT / 'VERSION').read_text().strip()),
                             dict(name='Python', version=platform.python_version()), dict(name='操作系统', version=platform.platform()),
                             dict(name='SQLite', version=sqlite3.sqlite_version), dict(name='AdminLTE', version='3.2.0'),
                             dict(name='jQuery', version='3.7.1'), dict(name='Bootstrap', version='4.6.2'),
                             dict(name='DataTables', version='1.13.11'), dict(name='CodeMirror', version='5.65.20'),
                             dict(name='Oracle 11g / Instant Client', version='医院部署与兼容性待验收')],
                   production=dependencies('requirements.lock'), development=dependencies('requirements.dev.in')))
