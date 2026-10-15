"""Credential/permission boundaries and driver contracts, without claiming live DB acceptance."""
import json
import secrets
import subprocess
import sys
from types import SimpleNamespace
import pytest
from sqlalchemy import select, delete
from app.models import DatabaseConnection, RolePermission, Setting
from app.security import cipher, AppError
from app.services import connections as service
from conftest import Client


def profile(**updates):
    data = dict(name='本地测试连接', engine='mysql', mode='local', port=3306, namespace='reports',
                username='reader', password=secrets.token_urlsafe(18), encrypt=True)
    return dict(data, **updates)


def test_profile_password_encryption_retention_and_invalidated_results(app, client, monkeypatch):
    data = profile()
    created = client.post('/api/admin/connections', data)
    assert created.status_code == 201, created.json
    item = created.json['data']; cid = item['id']
    assert 'password' not in item and 'password_encrypted' not in item and item['has_password']
    with app.extensions['repo'].transaction() as db:
        stored = db.get(DatabaseConnection, cid)
        assert data['password'] not in stored.password_encrypted
        assert cipher(app.config).decrypt(stored.password_encrypted.encode()).decode() == data['password']
    calls = []
    def run(options, password, config):
        calls.append((options, password))
        return dict(status='PASSED', code='OK', message='连接成功', elapsed_ms=12)
    monkeypatch.setattr('app.api.connections.test_connection', run)
    assert client.post(f'/api/admin/connections/{cid}/test').json['data']['persisted']
    assert calls[-1][1] == data['password']
    assert '通过 1 项' in client.get('/api/admin/monitor').json['data']['connection_tests']
    response = client.request('PUT', f'/api/admin/connections/{cid}', dict(data, password='', namespace='updated', revision=item['revision']))
    assert response.status_code == 200, response.json
    assert response.json['data']['last_test_status'] == 'UNTESTED'
    assert client.request('PUT', f'/api/admin/connections/{cid}', dict(data, revision=item['revision'])).status_code == 409
    assert client.post('/api/admin/connections/test', dict(data, id=cid, password='')).json['data']['status'] == 'PASSED'
    assert calls[-1][1] == data['password']
    assert data['password'] not in client.get('/api/admin/connections').get_data(as_text=True)
    assert data['password'] not in client.get('/api/admin/audits?module=connection').get_data(as_text=True)
    assert client.post('/api/admin/connections', data).status_code == 409
    assert client.request('DELETE', f'/api/admin/connections/{cid}').status_code == 200


@pytest.mark.parametrize('patch', [dict(port=True), dict(port=0), dict(port=65536), dict(engine='sqlite'),
                                  dict(host='http://127.0.0.1', mode='tcp'), dict(name=''), dict(namespace=''),
                                  dict(enabled='yes'), dict(auth_type='windows'), dict(password='')])
def test_invalid_profiles(client, patch):
    assert client.post('/api/admin/connections', profile(**patch)).status_code == 400


def test_permission_migration_and_revocation_stays_revoked(app, client):
    assert client.get('/pages/connections').status_code == 200
    rid = client.post('/api/admin/roles', dict(name='连接只读外部角色', code='CONN_DENIED')).json['data']['id']
    secret = secrets.token_urlsafe(18)
    client.post('/api/admin/users', dict(username='conn_denied', password=secret, role_ids=[rid]))
    user = Client(app, 'conn_denied', secret)
    for method, path in [('GET', '/api/admin/connections'), ('POST', '/api/admin/connections'), ('POST', '/api/admin/connections/test'), ('DELETE', '/api/admin/connections/1')]:
        assert user.request(method, path, profile()).status_code == 403
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(RolePermission).where(RolePermission.permission == 'connection:manage'))
        db.execute(delete(Setting).where(Setting.key == 'connection_menu_migration'))
    assert app.test_cli_runner().invoke(args=['migrate']).exit_code == 0
    assert client.get('/api/admin/connections').status_code == 200
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(RolePermission).where(RolePermission.permission == 'connection:manage'))
    assert app.test_cli_runner().invoke(args=['migrate']).exit_code == 0
    assert client.get('/api/admin/connections').status_code == 403


def test_changed_or_deleted_profile_does_not_inherit_old_test(app, client, monkeypatch):
    item = client.post('/api/admin/connections', profile()).json['data']
    def changed(options, password, config):
        with app.extensions['repo'].transaction() as db:
            row = db.get(DatabaseConnection, item['id'])
            row.revision += 1
        return dict(status='PASSED', code='OK', message='连接成功', elapsed_ms=10)
    monkeypatch.setattr('app.api.connections.test_connection', changed)
    result = client.post(f"/api/admin/connections/{item['id']}/test").json['data']
    assert not result['persisted']
    assert client.get('/api/admin/connections').json['data'][0]['last_test_status'] == 'UNTESTED'


class Cursor:
    def __init__(self, trace): self.trace = trace
    def execute(self, sql, *params): self.trace.append((sql, params))
    def fetchone(self): return (1,)
    def close(self): self.trace.append('cursor_closed')


class Connection:
    def __init__(self, trace): self.trace = trace
    def cursor(self): return Cursor(self.trace)
    def close(self): self.trace.append('connection_closed')


@pytest.mark.parametrize('engine', ['oracle', 'mysql', 'sqlserver'])
def test_driver_contract_only_reads_and_closes(monkeypatch, engine, tmp_path):
    trace, kwargs = [], {}
    def connect(*args, **values):
        kwargs.update(values)
        if args: kwargs['odbc'] = args[0]
        return Connection(trace)
    fake = SimpleNamespace(connect=connect, init_oracle_client=lambda **values: trace.append(values),
                           drivers=lambda: ['ODBC Driver 18 for SQL Server'], constants=SimpleNamespace(CLIENT=SimpleNamespace(SSL=2048)))
    monkeypatch.setitem(sys.modules, {'oracle':'oracledb', 'mysql':'pymysql', 'sqlserver':'pyodbc'}[engine], fake)
    data = profile(engine=engine, mode='tcp', host='127.0.0.1', port=service.DEFAULT_PORTS[engine],
                   service_kind='sid', service_value='ORCL', schema='dbo', oracle_driver='thick')
    _, options, _ = service.validate_profile(data)
    (tmp_path / 'oci.dll').touch()
    result = service.probe(options, 'secret};Encrypt=no;PWD=injected', str(tmp_path))
    assert result['status'] == 'PASSED'
    assert trace[-2:] == ['cursor_closed', 'connection_closed']
    assert all(not entry[0].startswith(('UPDATE', 'INSERT', 'DELETE', 'ALTER')) for entry in trace if isinstance(entry, tuple))
    if engine == 'oracle':
        assert trace[0] == {'lib_dir': str(tmp_path)}
        assert kwargs['sid'] == 'ORCL' and 'service_name' not in kwargs
        assert kwargs['tcp_connect_timeout'] == 3 and kwargs['retry_count'] == 0
    elif engine == 'mysql':
        assert kwargs['database'] == 'reports' and kwargs['client_flag'] == 2048
        assert kwargs['ssl'].check_hostname and kwargs['local_infile'] is False
    else:
        assert 'PWD={secret}};Encrypt=no;PWD=injected}' in kwargs['odbc']
        assert 'TrustServerCertificate={no}' in kwargs['odbc'] and kwargs['timeout'] == 3


def test_local_instance_windows_auth_and_raw_errors_hidden(monkeypatch):
    data = profile(engine='sqlserver', mode='local', auth_type='windows', local_instance=r'(localdb)\MSSQLLocalDB')
    _, options, _ = service.validate_profile(data)
    assert service.connection_password(data, None, {}) == ''
    seen = []
    def connect(value, **kwargs):
        seen.append(value)
        raise RuntimeError('28000 user=reader password=secret-do-not-leak')
    monkeypatch.setitem(sys.modules, 'pyodbc', SimpleNamespace(drivers=lambda: ['ODBC Driver 18 for SQL Server'], connect=connect))
    result = service.probe(options, '')
    assert result['code'] == 'AUTH_FAILED' and 'secret-do-not-leak' not in json.dumps(result)
    assert r'Server={(localdb)\MSSQLLocalDB}' in seen[0] and 'Trusted_Connection={yes}' in seen[0] and 'PWD=' not in seen[0]
    with pytest.raises(AppError): service.validate_profile(dict(data, local_instance=r'remote\SQLEXPRESS'))


def test_probe_process_timeout_uses_stdin_and_releases_slot(monkeypatch):
    def timeout(command, **kwargs):
        assert 'hidden-secret' not in str(command) and json.loads(kwargs['input'])['password'] == 'hidden-secret'
        assert kwargs['timeout'] == 10
        raise subprocess.TimeoutExpired(command, 10)
    monkeypatch.setattr(service.subprocess, 'run', timeout)
    _, options, _ = service.validate_profile(profile())
    assert service.test_connection(options, 'hidden-secret', {})['code'] == 'TIMEOUT'
    assert service.TEST_SLOT.acquire(blocking=False)
    service.TEST_SLOT.release()


def test_different_driver_requires_new_password_and_disabling_blocks_saved_test(client):
    data = profile()
    item = client.post('/api/admin/connections', data).json['data']
    cid = item['id']
    assert client.request('PUT', f'/api/admin/connections/{cid}', dict(data, engine='oracle', service_value='ORCL', password='', revision=item['revision'])).status_code == 400
    assert client.request('PUT', f'/api/admin/connections/{cid}', dict(data, enabled=False, revision=item['revision'])).status_code == 200
    assert client.post(f'/api/admin/connections/{cid}/test').status_code == 409


@pytest.mark.parametrize('directory', [123, 'relative/client', r'\\server\client', 'x' * 1025, 'C:\\bad\npath'])
def test_invalid_oracle_client_directory(client, directory):
    data = profile(engine='oracle', service_value='ORCL', oracle_client_dir=directory)
    assert client.post('/api/admin/connections', data).status_code == 400


def test_oracle_client_directory_roundtrip_and_clear(client, monkeypatch, tmp_path):
    data = profile(engine='oracle', service_value='ORCL', oracle_client_dir=str(tmp_path))
    item = client.post('/api/admin/connections', data).json['data']
    assert item['oracle_client_dir'] == str(tmp_path)
    assert client.get('/api/admin/connections').json['data'][0]['oracle_client_dir'] == str(tmp_path)
    seen = []
    def run(options, password, config):
        seen.append(options['oracle_client_dir'])
        return dict(status='FAILED', code='ORACLE_CLIENT', message='客户端不可用', elapsed_ms=1)
    monkeypatch.setattr('app.api.connections.test_connection', run)
    assert client.post('/api/admin/connections/test', dict(data, id=item['id'], password='')).status_code == 200
    assert client.post(f"/api/admin/connections/{item['id']}/test").status_code == 200
    assert seen == [str(tmp_path), str(tmp_path)]
    updated = client.request('PUT', f"/api/admin/connections/{item['id']}",
                             dict(data, password='', oracle_client_dir='', revision=item['revision'])).json['data']
    assert updated['oracle_client_dir'] == '' and updated['has_password']
    assert updated['last_test_status'] == 'UNTESTED'


@pytest.mark.parametrize('source', ['profile', 'deployment', 'system', 'thin'])
def test_oracle_client_directory_resolution(monkeypatch, tmp_path, source):
    (tmp_path / 'oci.dll').touch()
    trace = []
    fake = SimpleNamespace(init_oracle_client=lambda **values: trace.append(values),
                           connect=lambda **values: Connection(trace))
    monkeypatch.setitem(sys.modules, 'oracledb', fake)
    data = profile(engine='oracle', service_value='ORCL',
                   oracle_driver='thin' if source == 'thin' else 'thick',
                   oracle_client_dir=str(tmp_path) if source in ('profile', 'thin') else '')
    _, options, _ = service.validate_profile(data)
    fallback = str(tmp_path / 'wrong-default') if source == 'profile' else str(tmp_path) if source == 'deployment' else None
    result = service.probe(options, 'secret', fallback)
    assert result['status'] == 'PASSED'
    if source == 'thin':
        assert options['oracle_client_dir'] == ''
        assert not any(isinstance(entry, dict) for entry in trace)
    else:
        assert trace[0] == {'lib_dir': None if source == 'system' else str(tmp_path)}


def test_oracle_client_directory_missing_dll_and_invalid_library(monkeypatch, tmp_path):
    def fail(**kwargs):
        raise RuntimeError('DPI-1047 private driver details')
    monkeypatch.setitem(sys.modules, 'oracledb', SimpleNamespace(init_oracle_client=fail))
    _, options, _ = service.validate_profile(profile(engine='oracle', service_value='ORCL', oracle_client_dir=str(tmp_path)))
    result = service.probe(options, 'secret')
    assert result['code'] == 'ORACLE_CLIENT' and '缺少 oci.dll' in result['message']
    (tmp_path / 'oci.dll').touch()
    result = service.probe(options, 'secret')
    assert result['code'] == 'ORACLE_CLIENT' and 'VC++' in result['message']
    assert 'private driver details' not in result['message']
    with pytest.raises(AppError):
        service.validate_profile(profile(engine='oracle', service_value='ORCL', oracle_client_dir=str(tmp_path / 'oci.dll')))


def test_oracle_client_directory_environment_overrides_local_config(monkeypatch, tmp_path):
    from app.config import configuration
    local = tmp_path / 'config.json'
    local.write_text(json.dumps({'ORACLE_CLIENT_DIR': 'local-default'}), encoding='utf-8')
    monkeypatch.setenv('APP_CONFIG', str(local))
    monkeypatch.setenv('ORACLE_CLIENT_DIR', str(tmp_path))
    config = configuration(dict(DATA_DIR=str(tmp_path / 'data'), EXPORT_DIR=str(tmp_path / 'exports'),
                                LOG_DIR=str(tmp_path / 'logs'), SECRET_KEY='x' * 64,
                                APP_ENV='development', DATA_SOURCE='mock'))
    assert config['ORACLE_CLIENT_DIR'] == str(tmp_path)
