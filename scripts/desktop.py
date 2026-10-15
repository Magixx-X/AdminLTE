"""Double-click initialization/startup; database connections are configured on the web."""
import argparse
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import click
from sqlalchemy import select
from app import create_app
from app.config import configuration
from app.models import User, Setting
from app.repositories import Repository
from app.security import AppError


def local_config():
    return configuration()


def initialize():
    local_config()
    app = create_app()
    with app.app_context():
        app.cli.main(args=['migrate'], standalone_mode=False)
        username = click.prompt('请输入首次管理员账号', default='admin')
        with app.extensions['repo'].transaction() as db:
            if db.scalar(select(User).where(User.username == username)):
                raise click.ClickException('该账号已存在，未修改密码。可以直接登录；重置密码请参考 README。')
        app.cli.main(args=['init-admin', '--username', username], standalone_mode=False)
        if app.config['DATA_SOURCE'] == 'mock' and app.config['APP_ENV'] == 'development' and click.confirm('是否为此账号准备 Mock 合成月报、查询权限与合成科室范围？', default=True):
            app.cli.main(args=['seed-mock', username], standalone_mode=False)
    click.echo('初始化完成。双击 02_start_system.cmd 启动系统；密码输入时不显示字符。')


def start(port=8080, open_browser=True):
    config = local_config()
    for checked_port in (port, config['IPC_PORT']):
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1', checked_port))
            except OSError:
                raise RuntimeError(f'端口 {checked_port} 已被占用，请检查是否已经启动系统；本次不会重复启动。') from None
    subprocess.run([sys.executable, '-m', 'flask', '--app', 'wsgi:application', 'migrate'], cwd=ROOT, check=True)
    repo = Repository(config['DATABASE_URL'])
    try:
        with repo.transaction() as db:
            if not db.scalar(select(User.id).where(User.enabled == True).limit(1)):
                raise RuntimeError('还没有可登录账号，请先双击 01_init_admin.cmd 创建管理员。')
        processes, logs = [], []
        started_at = time.time()
        try:
            for name, args in (
                ('worker', [sys.executable, 'worker.py']),
                ('web', [sys.executable, '-m', 'waitress', f'--listen=127.0.0.1:{port}', '--threads=8', 'wsgi:application']),
            ):
                log = open(Path(config['LOG_DIR']) / f'launcher-{name}.log', 'a', encoding='utf-8')
                logs.append(log)
                # Share the launcher console: no extra windows; closing it also signals the children.
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' and not sys.stdin.isatty() else 0
                processes.append(subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, creationflags=flags))
            url = f'http://127.0.0.1:{port}'
            for _ in range(100):
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError(f'服务启动失败，请查看 {config["LOG_DIR"]} 下 launcher-web.log / launcher-worker.log。')
                try:
                    with urlopen(url + '/login', timeout=.5) as response:
                        ready = response.status == 200
                    with repo.transaction() as db:
                        heartbeat = db.get(Setting, 'worker_heartbeat')
                        # Windows venv python.exe can be a redirector with a different child PID.
                        ready = ready and heartbeat is not None and heartbeat.value.get('timestamp', 0) >= started_at
                    if ready:
                        break
                except OSError:
                    pass
                time.sleep(.2)
            else:
                raise RuntimeError('启动超时，请检查 logs 下的启动日志。')
            click.echo(f'系统已启动：{url}')
            click.echo('首次使用请在系统管理 → 连接配置中新增 Oracle 连接，保存并测试。')
            if config['APP_ENV'] == 'production':
                click.echo('生产登录请通过已配置的 HTTPS 反向代理地址访问。')
            click.echo('请保持本窗口打开。回车或 Ctrl+C 停止本次启动的 Web 和 Worker；运行中的任务会中断。')
            if open_browser and config['APP_ENV'] != 'production':
                webbrowser.open(url)
            input()
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for log in logs:
                log.close()
    finally:
        repo.engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['init', 'start'])
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    try:
        if args.action == 'init':
            initialize()
        elif not 1 <= args.port <= 65535:
            raise RuntimeError('端口必须为 1–65535')
        else:
            start(args.port, not args.no_browser)
    except (KeyboardInterrupt, EOFError):
        click.echo('\n已退出。')
    except (AppError, click.ClickException, RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        click.echo('操作失败：' + (exc.message if isinstance(exc, AppError) else str(exc)), err=True)
        sys.exit(1)
