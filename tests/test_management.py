"""Management forms enforce single assignments and safe hierarchy mutations."""
import secrets
from sqlalchemy import select
from app.models import User, UserRole, UserDataScope, Role
from conftest import Client


def test_department_hierarchy_cycle_and_references(client):
    root = dict(code='HOSPITAL', name='总院', position=1, enabled=True, remark='总部')
    assert client.post('/api/admin/scopes', root).status_code == 201
    assert client.post('/api/admin/scopes', dict(code='LAB', name='检验科', parent='HOSPITAL', position=2)).status_code == 201
    assert client.request('PUT', '/api/admin/departments/HOSPITAL', {'name': '总院', 'parent': 'LAB'}).status_code == 400
    assert client.request('PUT', '/api/admin/departments/LAB', {'name': '检验科', 'parent': 'LAB'}).status_code == 400
    assert client.request('PUT', '/api/admin/departments/LAB', {'name': '检验科', 'parent': 'missing'}).status_code == 400
    assert client.request('DELETE', '/api/admin/departments/HOSPITAL').status_code == 409
    result = next(row for row in client.get('/api/admin/departments').json['data'] if row['code'] == 'HOSPITAL')
    assert result['remark'] == '总部' and result['created_at'] and result['parent'] is None
    assert client.request('DELETE', '/api/admin/departments/LAB').status_code == 200
    assert client.request('DELETE', '/api/admin/departments/HOSPITAL').status_code == 200


def test_single_role_department_profile_and_immediate_role_disable(app, client):
    rid = client.post('/api/admin/roles', dict(name='检验员', code='LAB_USER', remark='查看平台信息')).json['data']['id']
    assert client.request('PUT', f'/api/admin/roles/{rid}/menus', {'menu_ids': ['about']}).status_code == 200
    secret = secrets.token_urlsafe(18)
    data = dict(username='labuser', password=secret, nickname='小林', contact='13800138000', role_ids=[rid], scopes=['D001'])
    uid = client.post('/api/admin/users', data).json['data']['id']
    other = Client(app, 'labuser', secret)
    assert other.get('/pages/about').status_code == 200
    assert client.request('PUT', f'/api/admin/users/{uid}', {'role_ids': [rid, 1]}).status_code == 400
    assert client.request('PUT', f'/api/admin/users/{uid}', {'scopes': ['D001', 'D002']}).status_code == 400
    assert client.request('PUT', f'/api/admin/users/{uid}', {'scopes': ['D002'], 'nickname': '新昵称'}).status_code == 200
    with app.extensions['repo'].transaction() as db:
        assert list(db.scalars(select(UserDataScope.scope_code).where(UserDataScope.user_id == uid))) == ['D002']
        assert list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == uid))) == [rid]
        assert db.get(User, uid).nickname == '新昵称'
    assert client.request('PUT', f'/api/admin/roles/{rid}', dict(name='检验员', code='LAB_USER', enabled=False)).status_code == 200
    assert other.get('/pages/about').status_code == 403
    assert client.request('DELETE', f'/api/admin/roles/{rid}').status_code == 409
    assert client.request('PUT', '/api/admin/users/1', {'role_ids': [rid]}).status_code == 409
    assert client.post('/api/admin/roles', {'name': '重复标识', 'code': 'LAB_USER'}).status_code == 409


def test_menu_create_remove_restore_and_protected_entries(app, client):
    values = dict(code='custom_group', title='常用功能', position=55, enabled=True)
    assert client.post('/api/admin/menus', values).status_code == 201
    assert client.post('/api/admin/menus', dict(values, code='unknown_page', parent='custom_group')).status_code == 400
    assert client.request('DELETE', '/api/admin/menus/about').status_code == 200
    assert client.get('/pages/about').status_code == 403
    assert client.get('/api/about').status_code == 403
    assert any(row['code'] == 'about' for row in client.get('/api/admin/menu-options').json['data'])
    assert app.test_cli_runner().invoke(args=['migrate']).exit_code == 0
    assert client.get('/pages/about').status_code == 403  # migrations must not resurrect deleted menus
    assert client.post('/api/admin/menus', dict(code='about', title='平台信息', parent='custom_group', position=1, enabled=True)).status_code == 201
    assert client.get('/pages/about').status_code == 200
    assert client.request('DELETE', '/api/admin/menus/custom_group').status_code == 409
    for code in ('system', 'permissions', 'menus', 'authorization'):
        assert client.request('DELETE', '/api/admin/menus/' + code).status_code == 409
    assert client.request('DELETE', '/api/admin/menus/about').status_code == 200
    assert client.request('DELETE', '/api/admin/menus/custom_group').status_code == 200


def test_mock_notice_only_in_monitor_and_modal_forms(client):
    assert 'Mock · 合成数据' not in client.get('/').get_data(as_text=True)
    assert 'Mock 开发模式' not in client.get('/login').get_data(as_text=True)
    for page in ['users', 'roles', 'menus', 'departments']:
        html = client.get('/pages/' + page).get_data(as_text=True)
        assert 'Mock 开发模式' not in html
        assert '字段筛选' in html and 'edit-modal' in html and 'filter-name' in html
    html = client.get('/pages/users').get_data(as_text=True)
    assert 'multiple' not in html and '用户部门（科室）' in html and 'department-tree' in html
    assert client.get('/api/admin/monitor').json['data']['source'] == 'mock'


def test_upgrade_old_columns_without_changing_existing_assignments(app):
    """Exercise the actual old SQLite layout, not just a fresh metadata install."""
    from sqlalchemy import text
    with app.extensions['repo'].transaction() as db:
        previous_hash = db.get(User, 1).password_hash
        previous_roles = list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == 1)))
        previous_scopes = list(db.scalars(select(UserDataScope.scope_code).where(UserDataScope.user_id == 1)))
    # Reconstruct only this test's old schema, including its original constraints.
    with app.extensions['repo'].engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
        for table, schema, fields in [('roles', 'id INTEGER PRIMARY KEY, name VARCHAR(80) UNIQUE NOT NULL', 'id,name'),
                                      ('data_scopes', 'code VARCHAR(80) PRIMARY KEY, name VARCHAR(120) NOT NULL', 'code,name')]:
            connection.exec_driver_sql(f'CREATE TABLE legacy_{table} ({schema})')
            connection.exec_driver_sql(f'INSERT INTO legacy_{table} SELECT {fields} FROM {table}')
            connection.exec_driver_sql(f'DROP TABLE {table}')
            connection.exec_driver_sql(f'ALTER TABLE legacy_{table} RENAME TO {table}')
        for table, column in [('users', 'nickname'), ('users', 'contact'), ('menus', 'deleted')]:
            connection.exec_driver_sql(f'ALTER TABLE {table} DROP COLUMN {column}')
        connection.exec_driver_sql("UPDATE alembic_version SET version_num='0002'")
        connection.commit()
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
    result = app.test_cli_runner().invoke(args=['migrate'])
    assert result.exit_code == 0, result.output
    with app.extensions['repo'].transaction() as db:
        assert db.get(User, 1).password_hash == previous_hash
        assert list(db.scalars(select(UserRole.role_id).where(UserRole.user_id == 1))) == previous_roles
        assert list(db.scalars(select(UserDataScope.scope_code).where(UserDataScope.user_id == 1))) == previous_scopes
        assert all(role.code for role in db.scalars(select(Role)))
