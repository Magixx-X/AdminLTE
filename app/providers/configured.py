"""Load the tested query connection on demand, shared through SQLite across processes."""
import threading
from contextlib import contextmanager
from cryptography.fernet import InvalidToken
from app.models import DatabaseConnection, Setting
from app.security import AppError, cipher
from app.providers.mock import MockProvider
from app.providers.oracle import OracleProvider


class ConfiguredProvider:
    def __init__(self, config, repo):
        self.config, self.repo = config, repo
        self.lock = threading.Lock()
        self.provider, self.loaded, self.client_signature = None, None, None
        self.active = 0

    def identity(self, db=None, required=False):
        if db is None:
            with self.repo.transaction() as session:
                return self.identity(session, required)
        selected = db.get(Setting, 'query_connection_id')
        if selected:
            item = db.get(DatabaseConnection, selected.value)
            if required and (not item or not item.enabled or item.last_test_status != 'PASSED'):
                raise AppError('DATABASE_NOT_READY', '查询连接已变更、停用或测试未通过，请在连接配置中保存并测试', 409)
            return ['oracle', selected.value, item.revision if item else None]
        source = self.config['DATA_SOURCE']
        if source == 'mock':
            return ['mock']
        if required and any(not self.config.get(k) for k in ('ORACLE_USER', 'ORACLE_PASSWORD', 'ORACLE_DSN')):
            raise AppError('DATABASE_NOT_CONFIGURED', '请先在系统管理 → 连接配置中新增 Oracle 连接，保存并测试通过后再查询', 409)
        return ['oracle', 'deployment']

    @property
    def source(self):
        return self.identity()[0]

    @contextmanager
    def acquire(self, expected=None):
        with self.lock:
            with self.repo.transaction() as db:
                identity = self.identity(db, required=True)
                if expected is not None and identity != expected:
                    raise AppError('DATABASE_CHANGED', '查询连接已变更，请重新执行查询', 409)
                config = dict(self.config)
                if len(identity) == 3:
                    item = db.get(DatabaseConnection, identity[1])
                    options = item.options
                    if options['engine'] != 'oracle':
                        raise AppError('DATABASE_TYPE', '当前查询任务仅支持 Oracle', 409)
                    try:
                        secret = cipher(config).decrypt(item.password_encrypted.encode()).decode()
                    except InvalidToken:
                        raise AppError('CONNECTION_KEY', '连接密码无法解密，请恢复原应用密钥或重新填写密码', 409) from None
                    import oracledb
                    dsn = options['local_instance'] if options['mode'] == 'local' and options['local_instance'] else oracledb.makedsn(
                        options['host'], options['port'], **{options['service_kind']: options['service_value']})
                    config.update(ORACLE_USER=options['username'], ORACLE_PASSWORD=secret, ORACLE_DSN=dsn,
                                  ORACLE_DRIVER=options['oracle_driver'],
                                  ORACLE_CLIENT_DIR=options.get('oracle_client_dir') or config.get('ORACLE_CLIENT_DIR'))
            if self.loaded != identity:
                if self.active:
                    raise AppError('DATABASE_BUSY', '查询连接已更新，等待当前任务结束后重试', 409)
                signature = (config.get('ORACLE_DRIVER', 'thick'), config.get('ORACLE_CLIENT_DIR'))
                if identity[0] == 'oracle' and self.client_signature is not None and self.client_signature != signature:
                    raise AppError('ORACLE_CLIENT_RESTART', 'Oracle 驱动模式或客户端目录已变更，请重启 Web 和 Worker 后重试', 409)
                if self.provider and hasattr(self.provider, 'pool'):
                    self.provider.pool.close()
                self.provider, self.loaded = None, None
                try:
                    provider = MockProvider() if identity[0] == 'mock' else OracleProvider(config)
                except Exception:
                    raise AppError('DATABASE_UNAVAILABLE', '查询数据库连接失败，请在连接配置中重新测试，并检查运行服务的客户端与网络', 503) from None
                self.provider, self.loaded = provider, identity
                if identity[0] == 'oracle':
                    self.client_signature = signature
            self.active += 1
            provider = self.provider
        try:
            yield provider
        finally:
            with self.lock:
                self.active -= 1

    def health(self):
        with self.acquire() as provider:
            return provider.health()

    def rows(self, version, params, month, scopes, stop, timeout, source=None):
        with self.acquire(source) as provider:
            yield from provider.rows(version, params, month, scopes, stop, timeout)
