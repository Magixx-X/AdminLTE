import logging
import secrets
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, jsonify, g, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError
from app.config import configuration
from app.repositories import Repository
from app.security import setup_security, AppError, csrf_token, hasher


def create_app(overrides=None):
    import sys
    import struct
    if sys.version_info[:2] != (3, 11) or struct.calcsize('P') != 8:
        raise RuntimeError('本应用仅支持 Python 3.11 x64')
    app = Flask(__name__)
    app.config.update(configuration(overrides))
    app.extensions['repo'] = Repository(app.config['DATABASE_URL'])
    app.extensions['dummy_hash'] = hasher.hash(secrets.token_hex(16))
    tempdir = Path(app.config['EXPORT_DIR']) / 'temp'
    tempdir.mkdir(exist_ok=True)
    tempfile.tempdir = str(tempdir)
    handler = RotatingFileHandler(Path(app.config['LOG_DIR']) / 'application.log', maxBytes=2 * 1024 * 1024, backupCount=5, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    if app.config['DATA_SOURCE'] == 'oracle':
        from app.providers.oracle import OracleProvider
        app.extensions['provider'] = OracleProvider(app.config)
    else:
        from app.providers.mock import MockProvider
        app.extensions['provider'] = MockProvider()
    setup_security(app)
    from app.api import api
    app.register_blueprint(api)
    app.jinja_env.globals['csrf_token'] = csrf_token

    @app.errorhandler(AppError)
    def expected(exc):
        return jsonify(success=False, data=None, error={'code': exc.code, 'message': exc.message}), exc.status

    @app.errorhandler(HTTPException)
    def http_error(exc):
        if request.path.startswith('/api/'):
            return jsonify(success=False, data=None, error={'code': exc.name.upper().replace(' ', '_'), 'message': '请求无法处理'}), exc.code
        return render_template('error.html', message=exc.description), exc.code

    @app.errorhandler(IntegrityError)
    def conflict(_):
        return expected(AppError('CONFLICT', '数据冲突，请刷新后重试', 409))

    @app.errorhandler(Exception)
    def unexpected(exc):
        app.logger.error('Request failed: %s', type(exc).__name__)
        return expected(AppError('INTERNAL_ERROR', '服务错误，请联系管理员', 500))

    @app.get('/login')
    def login_page():
        return render_template('login.html')

    @app.get('/')
    def index():
        if not g.user:
            return redirect(url_for('login_page'))
        from app.navigation import tree
        with app.extensions['repo'].transaction() as db:
            menus = tree(db, g.permissions)
        return render_template('index.html', menus=menus)

    from app.navigation import PAGES, available
    @app.get('/pages/<name>')
    def page(name):
        if not g.user:
            return redirect(url_for('login_page'))
        if name == 'profile':
            return render_template('profile.html', page_title='个人资料')
        if name not in PAGES and name != 'dashboard':
            return render_template('error.html', message='页面不存在'), 404
        with app.extensions['repo'].transaction() as db:
            allowed = {m.code: m.title for m in available(db, g.permissions)}
        if name != 'dashboard' and name not in allowed:
            return render_template('error.html', message='无权访问此页面'), 403
        return render_template('page.html', page=name, page_title=allowed.get(name, '工作概览'))

    from app.cli import register_cli
    register_cli(app)
    return app
