import hashlib
import hmac
import secrets
import time
from functools import wraps
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from cryptography.fernet import Fernet
import base64
from flask import current_app, g, request, session
from sqlalchemy import select
from app.models import AuthSession, User, UserRole, Role, RolePermission, UserDataScope, DataScope, TemplatePermission, Template

hasher = PasswordHasher()


class AppError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def cipher(config):
    key = hashlib.sha256(('task-payload:' + config['SECRET_KEY']).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def password(value):
    if not isinstance(value, str) or not 6 <= len(value) <= 128:
        raise AppError('PASSWORD_POLICY', '密码长度必须为 6–128 字符')
    return hasher.hash(value)


def permissions(db, uid):
    roles = select(UserRole.role_id).join(Role).where(UserRole.user_id == uid, Role.enabled == True)
    result = set(db.scalars(select(RolePermission.permission).where(RolePermission.role_id.in_(roles))))
    from app.models import Menu
    from app.navigation import PAGES
    menus = {m.code: m for m in db.scalars(select(Menu))}
    for code, spec in PAGES.items():
        m = menus.get(code)
        parent = menus.get(m.parent) if m else None
        if not m or m.deleted or not m.enabled or not parent or parent.deleted or not parent.enabled:
            result.difference_update(spec[2])
    return result


def scopes(db, uid):
    return sorted(db.scalars(select(UserDataScope.scope_code).join(DataScope).where(UserDataScope.user_id == uid, DataScope.enabled == True)))


def require(permission=None):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not g.user:
                raise AppError('UNAUTHENTICATED', '会话已过期，请重新登录', 401)
            if permission and permission not in g.permissions:
                raise AppError('FORBIDDEN', '没有此操作权限', 403)
            return fn(*args, **kwargs)
        return wrapped
    return decorator


def template_access(db, uid, tid, action):
    if type(tid) is not int or tid < 1:
        raise AppError('PARAMETERS', '模板 ID 必须为正整数')
    template = db.get(Template, tid)
    if not template or template.deleted:
        raise AppError('NOT_FOUND', '模板不存在', 404)
    roles = select(UserRole.role_id).join(Role).where(UserRole.user_id == uid, Role.enabled == True)
    grants = db.scalars(select(TemplatePermission).where(TemplatePermission.template_id == tid))
    roleids = set(db.scalars(roles))
    if not any((p.user_id == uid or p.role_id in roleids) and getattr(p, action) for p in grants):
        raise AppError('TEMPLATE_FORBIDDEN', '未获此模板授权', 403)
    return template


def task_access(db, task, uid, action='view'):
    if not task:
        raise AppError('NOT_FOUND', '任务不存在', 404)
    if task.user_id != uid:
        raise AppError('OWNER_FORBIDDEN', '不能访问其他用户任务', 403)
    template = template_access(db, uid, task.template_id, action)
    if template.status != 'PUBLISHED':
        raise AppError('TEMPLATE_UNAVAILABLE', '模板已停用或未发布', 409)
    if not set(task.scopes).issubset(scopes(db, uid)):
        raise AppError('SCOPE_REVOKED', '任务数据范围已被撤销，请重新查询', 403)


def setup_security(app):
    @app.before_request
    def authenticate():
        g.user, g.permissions, g.auth = None, set(), None
        token = request.cookies.get('hqs_auth', '')
        if token:
            with app.extensions['repo'].transaction() as db:
                auth = db.get(AuthSession, digest(token))
                if auth and auth.expires > time.time():
                    user = db.get(User, auth.user_id)
                    if user and user.enabled and auth.epoch == user.auth_epoch:
                        g.user, g.auth = user, auth
                        g.permissions = permissions(db, user.id)
        if request.path.startswith('/api/') and request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            expected = g.auth.csrf if g.auth else session.get('csrf')
            if not expected or not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), expected):
                raise AppError('CSRF', 'CSRF 校验失败，请刷新页面', 403)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'"
        if not request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'no-store'
        if app.config['APP_ENV'] == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response


def csrf_token():
    if g.get('auth'):
        return g.auth.csrf
    if 'csrf' not in session:
        session['csrf'] = secrets.token_hex(32)
    return session['csrf']
