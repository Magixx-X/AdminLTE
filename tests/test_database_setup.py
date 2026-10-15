"""Web-first database setup, shared activation, and source isolation."""
from types import SimpleNamespace
import pytest
from app.config import configuration
from app.models import DatabaseConnection, QueryTask, Template, TemplateVersion, now
from app.providers.configured import ConfiguredProvider
from app.security import AppError
from conftest import submit
from test_connections import profile


def _activate_oracle(client, monkeypatch, **updates):
    monkeypatch.setattr('app.api.connections.test_connection', lambda *args:
                        dict(status='PASSED', code='OK', message='连接成功', elapsed_ms=1))
    data = profile(engine='oracle', port=1521, service_value='ORCL', oracle_driver='thick', **updates)
    item = client.post('/api/admin/connections', data).json['data']
    result = client.post(f"/api/admin/connections/{item['id']}/test").json['data']
    assert result['query_source']
    return item, data


def test_automatic_secret_persists_and_preserves_legacy_key(monkeypatch, tmp_path):
    monkeypatch.setenv('APP_CONFIG', str(tmp_path / 'absent.json'))
    monkeypatch.delenv('APP_SECRET', raising=False)
    config = dict(APP_ENV='production', DATA_SOURCE='oracle', SECRET_KEY=None,
                  DATA_DIR=str(tmp_path / 'data'), EXPORT_DIR=str(tmp_path / 'exports'), LOG_DIR=str(tmp_path / 'logs'))
    first = configuration(config)
    assert len(first['SECRET_KEY']) == 64
    assert configuration(config)['SECRET_KEY'] == first['SECRET_KEY']
    (tmp_path / 'data' / 'development.key').write_text('legacy-' * 10, encoding='ascii')
    assert configuration(config)['SECRET_KEY'] == 'legacy-' * 10


def test_startup_without_credentials_and_web_connection_activation(app, client, monkeypatch):
    app.config.update(DATA_SOURCE='oracle', ORACLE_USER=None, ORACLE_PASSWORD=None, ORACLE_DSN=None)
    assert client.get('/pages/connections').status_code == 200
    assert client.get('/api/admin/health').json['error']['code'] == 'DATABASE_NOT_CONFIGURED'
    item, data = _activate_oracle(client, monkeypatch)
    assert client.get('/api/admin/connections').json['data'][0]['is_query_source']
    # A separate Worker provider discovers the persisted selection without restarting.
    worker_provider = ConfiguredProvider(app.config, app.extensions['repo'])
    configs = []
    class FakeOracle:
        def __init__(self, config):
            configs.append(config)
            self.pool = SimpleNamespace(close=lambda: None)
        def health(self): return {'source': 'oracle', 'status': 'OK'}
        def rows(self, *args): yield ['VALUE'], (1,)
    monkeypatch.setattr('app.providers.configured.OracleProvider', FakeOracle)
    assert worker_provider.health()['status'] == 'OK'
    assert configs[0]['ORACLE_USER'] == data['username']
    assert configs[0]['ORACLE_PASSWORD'] == data['password']
    assert 'ORCL' in configs[0]['ORACLE_DSN']
    identity = worker_provider.identity()
    assert list(worker_provider.rows(None, {}, '2024-02', ['D001'], lambda: False, 1, source=identity)) == [(['VALUE'], (1,))]
    assert client.get('/api/admin/monitor').json['data']['source'] == 'oracle'
    # The already-created Worker executes using the web profile, with no restart or env credentials.
    with app.extensions['repo'].transaction() as db:
        template = db.get(Template, 1)
        old = db.get(TemplateVersion, 1)
        db.add(TemplateVersion(template_id=template.id, number=2, sql=old.sql, schema=old.schema,
                               scope_policy=old.scope_policy, sort_fields=old.sort_fields,
                               validation='HOSPITAL_VALIDATED', reviewer_id=1, reviewed_at=now()))
        template.latest_version = template.published_version = 2
    group = submit(client)
    worker = app.extensions['test_worker']
    for task_id in group['task_ids']:
        assert worker.claim(QueryTask) == task_id
        worker.execute_query(task_id)
        with app.extensions['repo'].transaction() as db:
            assert db.get(QueryTask, task_id).status == 'SUCCEEDED'
    # Editing invalidates the passed test; there is no fallback to stale credentials.
    updated = client.request('PUT', f"/api/admin/connections/{item['id']}",
                             dict(data, password='', revision=item['revision'], username='updated_reader'))
    assert updated.status_code == 200
    with pytest.raises(AppError) as exc:
        worker_provider.health()
    assert exc.value.code == 'DATABASE_NOT_READY'
    client.post(f"/api/admin/connections/{item['id']}/test")
    assert worker_provider.health()['status'] == 'OK'
    assert configs[-1]['ORACLE_USER'] == 'updated_reader'


def test_failed_or_changed_test_never_activates(app, client, monkeypatch):
    app.config.update(DATA_SOURCE='oracle', ORACLE_USER=None)
    monkeypatch.setattr('app.api.connections.test_connection', lambda *args:
                        dict(status='FAILED', code='ORACLE_CLIENT', message='客户端不可用', elapsed_ms=1))
    item = client.post('/api/admin/connections', profile(engine='oracle', service_value='ORCL')).json['data']
    assert not client.post(f"/api/admin/connections/{item['id']}/test").json['data'].get('query_source')
    assert not client.get('/api/admin/connections').json['data'][0]['is_query_source']


def test_source_change_blocks_pending_tasks_and_disabled_connection(app, client, monkeypatch):
    group = submit(client)
    _activate_oracle(client, monkeypatch)
    task_id = group['task_ids'][0]
    worker = app.extensions['test_worker']
    assert worker.claim(QueryTask) == task_id
    worker.execute_query(task_id)
    with app.extensions['repo'].transaction() as db:
        assert db.get(QueryTask, task_id).error_code == 'DATABASE_CHANGED'
        item = db.get(DatabaseConnection, 1)
        item.enabled = False
    with pytest.raises(AppError) as exc:
        app.extensions['provider'].health()
    assert exc.value.code == 'DATABASE_NOT_READY'


def test_provider_never_uses_changed_source_snapshot(app, client, monkeypatch):
    original = app.extensions['provider'].identity()
    _activate_oracle(client, monkeypatch)
    with pytest.raises(AppError) as exc:
        list(app.extensions['provider'].rows(None, {}, '2024-02', ['D001'], lambda: False, 1, source=original))
    assert exc.value.code == 'DATABASE_CHANGED'
