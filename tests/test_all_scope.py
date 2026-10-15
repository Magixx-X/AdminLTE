import json
from types import SimpleNamespace
import pytest
from sqlalchemy import delete
from app.config import ROOT
from app.models import UserDataScope, TemplatePermission, QueryTask
from app.security import AppError
from app.services.parameters import validate_schema, parse_params, oracle_binds
from conftest import complete


def test_rounds_template_contract_and_typed_dates():
    sql = (ROOT / 'docs/sql/rounds_record.sql').read_text(encoding='utf-8')
    spec = json.loads((ROOT / 'docs/sql/rounds_record.json').read_text(encoding='utf-8'))
    validate_schema(spec['schema'], spec['sort_fields'], spec['scope_policy'], sql)
    params = parse_params(spec['schema'], {'start_date': '2026-10-01', 'end_date': '2026-11-01'})
    version = SimpleNamespace(sql=sql, schema=spec['schema'], scope_policy=spec['scope_policy'])
    _, binds = oracle_binds(version, params, '2026-10', None)
    assert set(binds) == {'begin_time', 'end_time', 'start_date', 'end_date'}
    assert binds['start_date'].year == 2026 and binds['end_date'].month == 11
    with pytest.raises(AppError):
        validate_schema([], [], {'kind': 'all'}, sql + ' :scope_department')


def test_all_scope_requires_explicit_publish_review_and_template_grant(app, client):
    sql = 'SELECT :begin_time AS begin_time, :end_time AS end_time FROM dual'
    template = client.post('/api/templates', dict(name='全院测试', sql=sql, schema=[], sort_fields=[],
                           scope_policy={'kind': 'all'}, summary='全院测试')).json['data']
    tid = template['id']
    client.post(f'/api/templates/{tid}/submit')
    assert client.post(f'/api/templates/{tid}/publish', {'scope_reviewed': True}).status_code == 400
    assert client.post(f'/api/templates/{tid}/publish', {'scope_reviewed': True, 'all_scope_reviewed': True}).status_code == 200
    with app.extensions['repo'].transaction() as db:
        db.execute(delete(UserDataScope).where(UserDataScope.user_id == 1))
    request = {'template_id': tid, 'params': {'month_start': '2026-10', 'month_end': '2026-10'}}
    assert client.post('/api/queries', request).status_code == 403
    with app.extensions['repo'].transaction() as db:
        db.add(TemplatePermission(template_id=tid, user_id=1, execute=True, view=True, export=True))
    response = client.post('/api/queries', request)
    assert response.status_code == 202, response.json
    group = response.json['data']
    complete(app, group)
    with app.extensions['repo'].transaction() as db:
        task = db.get(QueryTask, group['task_ids'][0])
        assert task.scopes == [] and task.status == 'SUCCEEDED'


def test_oracle_all_scope_runs_once_even_with_multiple_departments(monkeypatch):
    import oracledb
    from app.providers.oracle import OracleProvider
    from test_oracle_contract import Connection
    trace = []
    monkeypatch.setattr(oracledb, 'init_oracle_client', lambda **kwargs: None)
    monkeypatch.setattr(oracledb, 'is_thin_mode', lambda: False)
    monkeypatch.setattr(oracledb, 'create_pool', lambda **kwargs: SimpleNamespace(acquire=lambda: Connection(trace)))
    provider = OracleProvider(dict(ORACLE_USER='fake', ORACLE_PASSWORD='fake', ORACLE_DSN='fake',
                                   PROCESS_ROLE='worker', MAX_CELL_CHARS=4000))
    version = SimpleNamespace(validation='HOSPITAL_VALIDATED', reviewed_at='test', schema=[],
                              scope_policy={'kind': 'all'}, sql='SELECT :begin_time, :end_time FROM dual')
    rows = list(provider.rows(version, {}, '2026-10', ['D001', 'D002'], lambda: False, 1))
    assert len(rows) == 1
    queries = [binds for sql, binds in trace if sql == version.sql]
    assert len(queries) == 1 and 'scope_department' not in queries[0]
