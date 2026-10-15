import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def configuration(overrides=None):
    import json
    local = Path(os.environ.get('APP_CONFIG', ROOT / 'config.local.json'))
    if local.exists():
        values = json.loads(local.read_text(encoding='utf-8-sig'))
        if not isinstance(values, dict) or any(not isinstance(v, (str, int)) for v in values.values()):
            raise RuntimeError('配置必须是字符串或整数值的 JSON 对象')
        for key, value in values.items():
            os.environ.setdefault(key, str(value))
    env = os.environ
    result = dict(
        APP_ENV=env.get('APP_ENV', 'development'), DATA_SOURCE=env.get('DATA_SOURCE', 'oracle'),
        SECRET_KEY=env.get('APP_SECRET'), DATA_DIR=env.get('DATA_DIR', str(ROOT / 'data')),
        EXPORT_DIR=env.get('EXPORT_DIR', str(ROOT / 'exports')), LOG_DIR=env.get('LOG_DIR', str(ROOT / 'logs')),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=env.get('APP_ENV') == 'production',
        MAX_CONTENT_LENGTH=256 * 1024, SESSION_SECONDS=1800,
        LOGIN_LIMIT=5, LOGIN_WINDOW=900, MAX_MONTHS=36, QUERY_TIMEOUT=60,
        MAX_QUERY_TIMEOUT=180, QUERY_CONCURRENCY=2, EXPORT_CONCURRENCY=1,
        QUEUE_LIMIT=40, MAX_PAGE_SIZE=200, MAX_PREVIEW_ROWS=10000,
        MAX_EXPORT_ROWS=500000, MAX_EXPORT_BYTES=100 * 1024 * 1024,
        EXPORT_TTL=86400, RESULT_TTL=1800, CACHE_BYTES=64 * 1024 * 1024,
        MAX_CELL_CHARS=4000, IPC_PORT=int(env.get('IPC_PORT', '18081')),
        ORACLE_USER=env.get('ORACLE_USER'), ORACLE_PASSWORD=env.get('ORACLE_PASSWORD'),
        ORACLE_DSN=env.get('ORACLE_DSN'), ORACLE_CLIENT_DIR=env.get('ORACLE_CLIENT_DIR'),
        MYSQL_SSL_CA=env.get('MYSQL_SSL_CA'),
        ORACLE_POOL_MAX=4, TESTING=False, EXCEL_SHEET_ROWS=1048575,
        PROCESS_ROLE=env.get('PROCESS_ROLE', 'web'),
        DISK_WARNING_BYTES=int(env.get('DISK_WARNING_BYTES', str(1024 * 1024 * 1024))),
    )
    result.update(overrides or {})
    if result['APP_ENV'] == 'production':
        result['SESSION_COOKIE_SECURE'] = True
    if result['DATA_SOURCE'] not in ('mock', 'oracle'):
        raise RuntimeError('DATA_SOURCE 必须为 mock 或 oracle')
    if result['APP_ENV'] == 'production' and result['DATA_SOURCE'] != 'oracle':
        raise RuntimeError('生产模式必须显式配置 Oracle，禁止回退 Mock')
    for key in ('DATA_DIR', 'EXPORT_DIR', 'LOG_DIR'):
        Path(result[key]).mkdir(parents=True, exist_ok=True)
    if not result['SECRET_KEY']:
        keyfile = Path(result['DATA_DIR']) / 'development.key'
        if not keyfile.exists():
            keyfile = Path(result['DATA_DIR']) / 'application.key'
        if not keyfile.exists():
            import secrets
            try:
                with keyfile.open('x', encoding='ascii') as stream:
                    stream.write(secrets.token_hex(32))
            except FileExistsError:
                pass
        result['SECRET_KEY'] = keyfile.read_text(encoding='ascii').strip()
    if len(result['SECRET_KEY']) < 32:
        raise RuntimeError('APP_SECRET 至少 32 字符')
    result['DATABASE_URL'] = result.get('DATABASE_URL', 'sqlite:///' + str(Path(result['DATA_DIR']) / 'metadata.db'))
    return result
