import secrets
import pytest
from pathlib import Path
from app.config import ROOT
from sqlalchemy import select
from app import create_app
from app.models import User, Role, UserRole
from app.security import password
from app.tasks.worker import Worker

# Fresh offline archives do not contain any runtime directory.
(ROOT / '.runtime').mkdir(parents=True, exist_ok=True)


@pytest.fixture
def app(tmp_path):
    import tempfile
    previous_tempdir = tempfile.tempdir
    config = dict(TESTING=True, DATA_SOURCE='mock', APP_ENV='development', SECRET_KEY=secrets.token_hex(32),
                  DATA_DIR=str(tmp_path / 'data'), EXPORT_DIR=str(tmp_path / 'exports'), LOG_DIR=str(tmp_path / 'logs'),
                  QUERY_TIMEOUT=1, RESULT_TTL=30, EXCEL_SHEET_ROWS=10)
    app = create_app(config)
    runner = app.test_cli_runner()
    result = runner.invoke(args=['migrate'])
    assert result.exit_code == 0, result.output
    secret = secrets.token_urlsafe(18)
    with app.extensions['repo'].transaction() as db:
        user = User(username='admin', password_hash=password(secret))
        db.add(user)
        db.flush()
        role = db.scalar(select(Role).where(Role.name == 'SYSTEM_ADMIN'))
        db.add(UserRole(user_id=user.id, role_id=role.id))
    result = runner.invoke(args=['seed-mock', 'admin'])
    assert result.exit_code == 0, result.output
    worker = Worker(app)
    app.extensions['result_cache'] = worker.cache
    app.extensions['test_worker'] = worker
    app.config['TEST_PASSWORD'] = secret
    yield app
    worker.shutdown.set()
    for _, thread in worker.active.values():
        thread.join(5)
    app.extensions['repo'].engine.dispose()
    tempfile.tempdir = previous_tempdir
    for handler in list(app.logger.handlers):
        if hasattr(handler, 'baseFilename'):
            handler.close()
            app.logger.removeHandler(handler)


class Client:
    def __init__(self, app, username='admin', secret=None):
        self.raw = app.test_client()
        self.csrf = self.raw.get('/api/auth/csrf').json['data']['csrf_token']
        result = self.request('POST', '/api/auth/login', {'username': username, 'password': secret or app.config['TEST_PASSWORD']})
        assert result.status_code == 200, result.json
        self.csrf = result.json['data']['csrf_token']

    def request(self, method, path, data=None):
        return self.raw.open(path, method=method, json=data, headers={'X-CSRF-Token': self.csrf})

    def get(self, path):
        return self.request('GET', path)

    def post(self, path, data=None):
        return self.request('POST', path, data or {})


@pytest.fixture
def client(app):
    return Client(app)


def submit(client, params=None):
    values = {'month_start': '2024-02', 'month_end': '2024-03', 'sample_rows': 25}
    values.update(params or {})
    result = client.post('/api/queries', {'template_id': 1, 'params': values})
    assert result.status_code == 202, result.json
    return result.json['data']


def complete(app, group):
    worker = app.extensions['test_worker']
    from app.models import QueryTask
    for tid in group['task_ids']:
        assert worker.claim(QueryTask) == tid
        worker.execute_query(tid)
