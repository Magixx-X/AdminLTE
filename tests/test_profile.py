"""Self-service profile, password boundaries, and session revocation."""
import pytest
from sqlalchemy import select
from app.models import AuditLog, User
from app.security import AppError, password, hasher
from conftest import Client


def test_profile_is_available_without_management_permissions(app, client):
    uid = client.post('/api/admin/users', dict(username='ordinary', password='123456')).json['data']['id']
    other = Client(app, 'ordinary', '123456')
    assert other.get('/pages/profile').status_code == 200
    assert other.get('/api/admin/users').status_code == 403
    assert other.request('PUT', '/api/auth/profile', dict(nickname=' 小林 ', contact=' person@example.com ')).status_code == 200
    me = other.get('/api/auth/me').json['data']
    assert (me['username'], me['nickname'], me['contact']) == ('ordinary', '小林', 'person@example.com')
    for data in ({'username': 'changed'}, {'role_ids': [1]}, {'id': 1}, {'password': '123456'}, {'nickname': 'x' * 81}, {'contact': None}):
        assert other.request('PUT', '/api/auth/profile', data).status_code == 400
    assert other.raw.put('/api/auth/profile', json={'nickname': 'csrf bypass'}).status_code == 403
    with app.extensions['repo'].transaction() as db:
        assert db.get(User, 1).nickname == ''
        assert db.get(User, uid).nickname == '小林'
    assert app.test_client().get('/pages/profile').status_code == 302


def test_password_change_rejects_invalid_input_and_revokes_all_sessions(app, client):
    second = Client(app)
    url = '/api/auth/password'
    payload = dict(current_password=app.config['TEST_PASSWORD'], new_password='123456', confirm_password='123456')
    for data in (dict(payload, new_password='12345', confirm_password='12345'), dict(payload, new_password='x'*129),
                 dict(payload, confirm_password='mismatch'), dict(payload, current_password='wrong')):
        assert client.post(url, data).status_code == 400
    assert client.raw.post(url, json=payload).status_code == 403
    assert client.post(url, payload).status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    assert second.get('/api/auth/me').status_code == 401
    new_client = Client(app, secret='123456')
    assert new_client.get('/api/auth/me').status_code == 200
    assert new_client.get('/api/auth/me').json['data']['username'] == 'admin'
    with app.extensions['repo'].transaction() as db:
        assert hasher.verify(db.get(User, 1).password_hash, '123456')
        logs = db.scalars(select(AuditLog).where(AuditLog.action == 'auth.password_change')).all()
        assert len(logs) == 2
        assert all(log.detail == {} for log in logs)


def test_current_password_guessing_is_limited(app, client):
    for _ in range(app.config['LOGIN_LIMIT']):
        assert client.post('/api/auth/password', dict(current_password='wrong', new_password='123456', confirm_password='123456')).status_code == 400
    assert client.post('/api/auth/password', dict(current_password=app.config['TEST_PASSWORD'], new_password='123456', confirm_password='123456')).status_code == 429
    assert client.get('/api/auth/me').status_code == 200


def test_shared_password_boundaries_and_admin_reset(app, client, monkeypatch):
    for value in ('12345', 'x'*129, None):
        with pytest.raises(AppError):
            password(value)
    assert hasher.verify(password('x'*128), 'x'*128)
    created = client.post('/api/admin/users', dict(username='sixchar', password='123456'))
    assert created.status_code == 201
    uid = created.json['data']['id']
    assert client.request('PUT', f'/api/admin/users/{uid}', {'password': '12345'}).status_code == 400
    assert client.request('PUT', f'/api/admin/users/{uid}', {'password': 'abcdef'}).status_code == 200
    monkeypatch.setattr('getpass.getpass', lambda _: '654321')
    assert app.test_cli_runner().invoke(args=['reset-password', 'sixchar']).exit_code == 0
    assert Client(app, 'sixchar', '654321').get('/api/auth/me').status_code == 200
    assert app.test_cli_runner().invoke(args=['init-admin', '--username', 'newadmin']).exit_code == 0
    assert Client(app, 'newadmin', '654321').get('/api/auth/me').status_code == 200


def test_shell_profile_and_appearance_entries(client):
    html = client.get('/').get_data(as_text=True)
    assert '会话有效期' not in html
    for text in ('个人资料', '退出登录', 'appearance-toggle', 'mode-toggle', 'appearance-panel'):
        assert text in html
