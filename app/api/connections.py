"""Connection profile administration; never changes the running query provider."""
from flask import current_app, g
from sqlalchemy import select
from app.api import api, body, ok, repo
from app.models import DatabaseConnection, now
from app.repositories import audit
from app.security import AppError, cipher, require
from app.services.connections import validate_profile, connection_password, test_connection


def public_connection(item):
    result = {key: getattr(item, key) for key in ('id', 'name', 'enabled', 'revision', 'last_test_status', 'last_test_at',
                                                'last_test_message', 'last_test_ms', 'created_at', 'updated_at')}
    result.update(item.options)
    result['has_password'] = bool(item.password_encrypted)
    result['address'] = item.options['local_instance'] or item.options['host'] + ':' + str(item.options['port'])
    return result


def get_connection(db, cid):
    item = db.get(DatabaseConnection, cid)
    if not item:
        raise AppError('NOT_FOUND', '连接配置不存在', 404)
    return item


@api.get('/admin/connections')
@require('connection:manage')
def connections():
    with repo().transaction() as db:
        return ok([public_connection(item) for item in db.scalars(select(DatabaseConnection).order_by(DatabaseConnection.id))])


@api.post('/admin/connections')
@api.put('/admin/connections/<int:cid>')
@require('connection:manage')
def connection_save(cid=None):
    data = body()
    name, options, enabled = validate_profile(data)
    with repo().transaction() as db:
        previous = get_connection(db, cid) if cid else None
        if previous and (type(data.get('revision')) is not int or data['revision'] != previous.revision):
            raise AppError('CONFLICT', '连接配置已变更，请刷新后重新编辑', 409)
        if db.scalar(select(DatabaseConnection.id).where(DatabaseConnection.name == name, DatabaseConnection.id != (cid or 0))):
            raise AppError('CONFLICT', '连接名称已存在', 409)
        secret = connection_password(data, previous, current_app.config)
        item = previous or DatabaseConnection()
        item.name, item.options, item.enabled = name, options, enabled
        item.password_encrypted = cipher(current_app.config).encrypt(secret.encode()).decode() if secret else ''
        item.revision = previous.revision + 1 if previous else 1
        item.last_test_status, item.last_test_at, item.last_test_message, item.last_test_ms = 'UNTESTED', None, '', None
        db.add(item)
        db.flush()
        audit(db, 'connection.update' if cid else 'connection.create', g.user.id, detail={'connection_id': item.id, 'engine': options['engine']})
        return ok(public_connection(item), 200 if cid else 201)


@api.delete('/admin/connections/<int:cid>')
@require('connection:manage')
def connection_delete(cid):
    with repo().transaction() as db:
        db.delete(get_connection(db, cid))
        audit(db, 'connection.delete', g.user.id, detail={'connection_id': cid})
    return ok()


@api.post('/admin/connections/test')
@require('connection:manage')
def connection_test_draft():
    data = body()
    _, options, _ = validate_profile(data)
    cid = data.get('id')
    if cid is not None and (type(cid) is not int or cid < 1):
        raise AppError('CONNECTION', '连接编号无效')
    with repo().transaction() as db:
        previous = get_connection(db, cid) if cid else None
        secret = connection_password(data, previous, current_app.config)
    result = test_connection(options, secret, current_app.config)
    with repo().transaction() as db:
        audit(db, 'connection.test_draft', g.user.id, result=result['status'], detail={'connection_id': cid, 'engine': options['engine'], 'code': result['code']})
    return ok(result)


@api.post('/admin/connections/<int:cid>/test')
@require('connection:manage')
def connection_test_saved(cid):
    with repo().transaction() as db:
        item = get_connection(db, cid)
        if not item.enabled:
            raise AppError('CONNECTION_DISABLED', '连接已停用，请启用后测试', 409)
        options, revision = item.options, item.revision
        secret = connection_password(options, item, current_app.config)
    result = test_connection(options, secret, current_app.config)
    with repo().transaction() as db:
        current = db.get(DatabaseConnection, cid)
        result['persisted'] = bool(current and current.revision == revision)
        if result['persisted']:
            current.last_test_status, current.last_test_at = result['status'], now()
            current.last_test_message, current.last_test_ms = result['message'], result['elapsed_ms']
        audit(db, 'connection.test', g.user.id, result=result['status'], detail={'connection_id': cid, 'engine': options['engine'], 'code': result['code'], 'revision': revision})
    return ok(result)
