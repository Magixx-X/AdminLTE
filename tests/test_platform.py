import secrets
from sqlalchemy import select, delete
from app.models import RolePermission, Menu, UserDataScope
from conftest import Client, submit


def test_menu_authorization_is_immediate_and_data_is_separate(app, client):
    rid = client.post('/api/admin/roles', {'name': '菜单授权测试'}).json['data']['id']
    url = f'/api/admin/roles/{rid}/menus'
    assert client.request('PUT', url, {'menu_ids': ['query', 'history', 'about']}).status_code == 200
    secret = secrets.token_urlsafe(18)
    uid = client.post('/api/admin/users', {'username': 'menuuser', 'password': secret, 'role_ids': [rid], 'scopes': ['D001']}).json['data']['id']
    user = Client(app, 'menuuser', secret)
    assert {m['code'] for m in user.get('/api/navigation').json['data']} == {'query', 'history', 'about'}
    assert user.get('/pages/query').status_code == 200
    assert user.get('/pages/users').status_code == 403
    assert user.get('/api/admin/users').status_code == 403
    payload = {'template_id': 1, 'params': {'month_start': '2024-01', 'month_end': '2024-01'}}
    assert user.post('/api/queries', payload).status_code == 403
    assert client.post('/api/admin/grants', {'template_id': 1, 'user_id': uid, 'execute': True, 'view': True, 'export': True}).status_code == 200
    assert user.post('/api/queries', payload).status_code == 202
    assert client.request('PUT', url, {'menu_ids': ['about']}).status_code == 200
    assert user.get('/pages/query').status_code == 403
    assert user.post('/api/queries', payload).status_code == 403
    assert user.get('/api/queries/history').status_code == 403
    assert user.request('PUT', url, {'menu_ids': ['users']}).status_code == 403
    assert client.request('PUT', url, {'menu_ids': ['not-a-menu']}).status_code == 400


def test_menu_disable_parent_and_safe_labels(app, client):
    values = dict(title='查询管理', position=0, enabled=False)
    assert client.request('PUT', '/api/admin/menus/query_management', values).status_code == 200
    assert client.get('/pages/query').status_code == 403
    assert client.post('/api/queries', {}).status_code == 403
    assert client.get('/api/admin/query-settings').status_code == 403
    values['enabled'] = True
    assert client.request('PUT', '/api/admin/menus/query_management', values).status_code == 200
    assert client.get('/pages/query').status_code == 200
    values.update(title='<img src=x onerror=alert(1)>')
    assert client.request('PUT', '/api/admin/menus/query_management', values).status_code == 400
    values.update(title='系统管理', enabled=False)
    assert client.request('PUT', '/api/admin/menus/system', values).status_code == 400
    values.update(title='查询入口', enabled=True, parent='about')
    assert client.request('PUT', '/api/admin/menus/query', values).status_code == 400
    values['parent'] = 'query_management'
    assert client.request('PUT', '/api/admin/menus/query', values).status_code == 200
    assert '查询入口' in client.get('/').get_data(as_text=True)


def test_platform_settings_monitor_about_and_departments(app, client):
    assert client.request('PUT', '/api/admin/settings', {'SESSION_SECONDS': 600, 'LOGIN_LIMIT': 4}).status_code == 200
    raw = app.test_client()
    csrf = raw.get('/api/auth/csrf').json['data']['csrf_token']
    result = raw.post('/api/auth/login', json={'username': 'admin', 'password': app.config['TEST_PASSWORD']}, headers={'X-CSRF-Token': csrf})
    assert 'Max-Age=600' in result.headers['Set-Cookie']
    assert client.get('/api/admin/monitor').json['data']['users'] == 1
    about = client.get('/api/about').json['data']
    assert about['platform'][0]['name'] == '信息查询管理'
    assert any(d['name'] == 'Flask' for d in about['production'])
    assert any(d['name'] == 'playwright' for d in about['development'])
    assert client.post('/api/admin/scopes', {'code': 'TEST', 'name': '测试部门'}).status_code == 201
    assert client.request('PUT', '/api/admin/departments/TEST', {'name': '更名部门'}).status_code == 200
    assert client.request('DELETE', '/api/admin/departments/D001').status_code == 409
    assert client.request('DELETE', '/api/admin/departments/TEST').status_code == 200
    assert client.request('PUT', '/api/admin/query-settings', {'MAX_MONTHS': 24}).status_code == 200
    assert client.get('/api/admin/query-settings').json['data']['MAX_MONTHS'] == 24
    assert client.get('/api/admin/audits?action=department.update').json['data']['total'] == 1


def test_migrate_idempotent_keeps_revocations_and_menu_configuration(app, client):
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(RolePermission).where(RolePermission.permission == 'menu:manage'))
        db.get(Menu, 'about').title = '版本与依赖'
    result = app.test_cli_runner().invoke(args=['migrate'])
    assert result.exit_code == 0, result.output
    assert client.get('/api/admin/menus').status_code == 403
    assert '版本与依赖' in client.get('/').get_data(as_text=True)


def test_platform_pages_and_no_default_workspace_tab(app, client):
    for name in ['authorization', 'menus', 'departments', 'grants', 'query_settings', 'monitor', 'about']:
        assert client.get('/pages/' + name).status_code == 200
    html = client.get('/').get_data(as_text=True)
    assert '信息查询管理' in html and '医院查询管理' not in html
    assert '/pages/dashboard' not in html
    assert '<iframe ' not in html
    assert html.count('has-treeview') == 5


def test_upgrade_from_existing_schema_preserves_accounts_and_history(app, client):
    from sqlalchemy import text
    from app.models import User, Setting, QueryTask
    group = submit(client)
    with app.extensions['repo'].transaction() as db:
        original_hash = db.get(User, 1).password_hash
        db.execute(delete(Setting).where(Setting.key == 'platform_menu_migration'))
        db.execute(text('DROP TABLE menus'))
        db.execute(text("UPDATE alembic_version SET version_num='0001'"))
        db.execute(delete(RolePermission).where(RolePermission.permission.in_(['menu:manage', 'authorization:manage'])))
    result = app.test_cli_runner().invoke(args=['migrate'])
    assert result.exit_code == 0, result.output
    with app.extensions['repo'].transaction() as db:
        assert db.get(User, 1).password_hash == original_hash
        assert db.get(QueryTask, group['task_id']).status == 'PENDING'
        assert db.get(Menu, 'authorization') is not None
    assert client.get('/api/admin/menus').status_code == 200
    assert client.get('/api/admin/menu-authorization').status_code == 200


def test_disabled_query_menu_stops_worker_and_no_legacy_permission_writes(app, client):
    from app.models import QueryTask
    group = submit(client, {'month_end': '2024-02'})
    assert client.request('PUT', '/api/admin/menus/query', dict(title='SQL 查询', parent='query_management', position=0, enabled=False)).status_code == 200
    worker = app.extensions['test_worker']
    tid = worker.claim(QueryTask)
    worker.execute_query(tid)
    with app.extensions['repo'].transaction() as db:
        assert db.get(QueryTask, tid).status == 'FAILED'
    assert client.get('/api/templates').status_code == 200  # template administrators retain management capability
    assert client.post('/api/admin/roles', {'name': 'invalid', 'permissions': ['user:manage']}).status_code == 400
    assert client.request('PUT', '/api/admin/settings', {'MAX_MONTHS': 48}).status_code == 400
    assert 'MAX_MONTHS' not in client.get('/api/admin/settings').json['data']
