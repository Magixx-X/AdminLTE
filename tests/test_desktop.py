import http.cookiejar
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import Request, build_opener, HTTPCookieProcessor

import pytest
from sqlalchemy import select
from app.config import ROOT
from app.models import User, TemplatePermission, UserDataScope
from app.security import hasher
from scripts import desktop


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def test_initialize_reuses_cli_and_preserves_existing_password(app, monkeypatch):
    secret = secrets.token_urlsafe(20)
    monkeypatch.setattr(desktop, 'local_config', lambda: app.config)
    monkeypatch.setattr(desktop, 'create_app', lambda: app)
    monkeypatch.setattr(desktop.click, 'prompt', lambda *args, **kwargs: 'launch_admin')
    monkeypatch.setattr(desktop.click, 'confirm', lambda *args, **kwargs: True)
    monkeypatch.setattr('app.cli.getpass.getpass', lambda *args: secret)
    desktop.initialize()
    with app.extensions['repo'].transaction() as db:
        user = db.scalar(select(User).where(User.username == 'launch_admin'))
        old_hash = user.password_hash
        assert hasher.verify(old_hash, secret)
        assert db.scalar(select(TemplatePermission).where(TemplatePermission.user_id == user.id)).execute
        assert len(db.scalars(select(UserDataScope).where(UserDataScope.user_id == user.id)).all()) == 2
    with pytest.raises(desktop.click.ClickException, match='已存在'):
        desktop.initialize()
    with app.extensions['repo'].transaction() as db:
        assert db.scalar(select(User).where(User.username == 'launch_admin')).password_hash == old_hash


def test_launcher_refuses_busy_port(app, monkeypatch):
    monkeypatch.setattr(desktop, 'local_config', lambda: app.config)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        with pytest.raises(RuntimeError, match='占用'):
            desktop.start(sock.getsockname()[1], False)


def test_double_click_entry_starts_both_services_and_stops_own_children(app):
    port, ipc = free_port(), free_port()
    env = dict(os.environ, APP_ENV='development', DATA_SOURCE='mock', PYTHONUTF8='1',
        APP_SECRET=app.config['SECRET_KEY'], DATA_DIR=app.config['DATA_DIR'],
        EXPORT_DIR=app.config['EXPORT_DIR'], LOG_DIR=app.config['LOG_DIR'], IPC_PORT=str(ipc))
    process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/desktop.py'), 'start', '--no-browser', '--port', str(port)],
        cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    base = f'http://127.0.0.1:{port}'
    def request(path, data=None, csrf=None):
        headers = {'Content-Type': 'application/json'}
        if csrf:
            headers['X-CSRF-Token'] = csrf
        req = Request(base + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
        with opener.open(req, timeout=2) as response:
            return json.load(response)['data']
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError(process.communicate()[0].decode('utf-8', errors='replace'))
            try:
                csrf = request('/api/auth/csrf')['csrf_token']
                break
            except OSError:
                time.sleep(.1)
        else:
            raise AssertionError('Web did not start')
        csrf = request('/api/auth/login', {'username': 'admin', 'password': app.config['TEST_PASSWORD']}, csrf)['csrf_token']
        group = request('/api/queries', {'template_id': 1, 'params': {'month_start': '2024-02', 'month_end': '2024-02', 'sample_rows': 5}}, csrf)
        for _ in range(100):
            if request('/api/queries/' + group['task_id'])['status'] == 'SUCCEEDED':
                break
            time.sleep(.1)
        else:
            raise AssertionError('Worker did not finish task')
        assert len(request('/api/queries/' + group['task_id'] + '/results')['rows']) == 5
        output, _ = process.communicate(input=b'\n', timeout=15)
        assert process.returncode == 0, output.decode('utf-8', errors='replace')
        for checked in (port, ipc):
            with socket.socket() as sock:
                assert sock.connect_ex(('127.0.0.1', checked)) != 0
    finally:
        if process.poll() is None:
            process.communicate(timeout=30)


def test_shortcuts_do_not_override_production_mode(monkeypatch):
    monkeypatch.setattr(desktop, 'configuration', lambda: {'APP_ENV': 'production', 'DATA_SOURCE': 'oracle'})
    assert desktop.local_config() == {'APP_ENV': 'production', 'DATA_SOURCE': 'oracle'}
