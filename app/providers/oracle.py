import threading
import time
from datetime import date, datetime
from decimal import Decimal
import oracledb
from app.providers.base import QueryProvider, QueryCancelled, QueryTimeout
from app.services.parameters import oracle_binds
from app.security import AppError


class OracleProvider(QueryProvider):
    def __init__(self, config):
        self.config = config
        if any(not config.get(k) for k in ('ORACLE_USER', 'ORACLE_PASSWORD', 'ORACLE_DSN')):
            raise RuntimeError('Oracle 配置不完整，禁止回退 Mock')
        thick = config.get('ORACLE_DRIVER', 'thick') == 'thick'
        if thick:
            oracledb.init_oracle_client(lib_dir=config.get('ORACLE_CLIENT_DIR') or None)
        if thick and oracledb.is_thin_mode():
            raise RuntimeError('Oracle 11g 必须使用 Thick 模式')
        self.pool = oracledb.create_pool(user=config['ORACLE_USER'], password=config['ORACLE_PASSWORD'],
            dsn=config['ORACLE_DSN'], min=1, max=3 if config['PROCESS_ROLE'] == 'worker' else 1, increment=1,
            getmode=oracledb.POOL_GETMODE_TIMEDWAIT, wait_timeout=5000, tcp_connect_timeout=5)
        try:
            self.health()
        except Exception:
            self.pool.close(force=True)
            raise

    def health(self):
        with self.pool.acquire() as connection:
            connection.call_timeout = 5000
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1 FROM DUAL')
                cursor.fetchone()
            return {'source': 'oracle', 'status': 'OK', 'mode': 'Thin' if oracledb.is_thin_mode() else 'Thick',
                    'version': connection.version, 'validation': 'PENDING_HOSPITAL_VALIDATION'}

    def rows(self, version, params, month, scopes, stop, timeout):
        if version.validation != 'HOSPITAL_VALIDATED' or not version.reviewed_at:
            raise RuntimeError('PENDING_HOSPITAL_VALIDATION')
        deadline = time.monotonic() + timeout
        for department in scopes:
            if stop():
                raise QueryCancelled()
            if time.monotonic() >= deadline:
                raise QueryTimeout()
            with self.pool.acquire() as connection:
                done = threading.Event()
                reason = []
                def watchdog():
                    while not done.wait(.1):
                        try:
                            cancelled = stop()
                        except AppError as exc:
                            cancelled = True
                            reason.append(exc)
                        if cancelled or time.monotonic() >= deadline:
                            if not reason:
                                reason.append('cancel' if cancelled else 'timeout')
                            try:
                                connection.cancel()
                            except oracledb.Error:
                                pass
                            return
                watcher = threading.Thread(target=watchdog, daemon=True)
                watcher.start()
                try:
                    connection.call_timeout = max(1, int((deadline - time.monotonic()) * 1000))
                    with connection.cursor() as cursor:
                        cursor.execute('SET TRANSACTION READ ONLY')
                        sql, binds = oracle_binds(version, params, month, department)
                        cursor.arraysize = 100
                        cursor.execute(sql, binds)
                        if not cursor.description:
                            raise RuntimeError('SQL 必须返回查询结果')
                        columns = [d[0] for d in cursor.description]
                        while True:
                            batch = cursor.fetchmany(100)
                            if not batch:
                                break
                            for row in batch:
                                if stop():
                                    raise QueryCancelled()
                                if time.monotonic() >= deadline:
                                    raise QueryTimeout()
                                values = []
                                for value in row:
                                    if isinstance(value, oracledb.LOB):
                                        if value.size() > self.config['MAX_CELL_CHARS']:
                                            raise AppError('CELL_QUOTA', 'LOB 超过单元格配额，请由管理员收窄模板或批准提高限制')
                                        value = value.read(1, self.config['MAX_CELL_CHARS'])
                                    if isinstance(value, bytes):
                                        if len(value) > self.config['MAX_CELL_CHARS']:
                                            raise AppError('CELL_QUOTA', '二进制单元格超过配额')
                                        value = value.hex()
                                    if isinstance(value, Decimal):
                                        value = str(value)
                                    if isinstance(value, str):
                                        if len(value) > self.config['MAX_CELL_CHARS']:
                                            raise AppError('CELL_QUOTA', '文本单元格超过配额，请收窄模板')
                                    values.append(value)
                                yield columns, tuple(values)
                except oracledb.Error:
                    if reason:
                        if isinstance(reason[0], AppError):
                            raise reason[0]
                        if reason[0] == 'cancel':
                            raise QueryCancelled()
                        raise QueryTimeout()
                    raise RuntimeError('ORACLE_QUERY_ERROR：请由 DBA 检查服务器日志与审核 SQL') from None
                finally:
                    done.set()
                    watcher.join(1)
                    connection.rollback()
