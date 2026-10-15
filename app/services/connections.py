"""Validate saved profiles and run bounded, read-only driver probes."""
import ipaddress
import json
import re
import ssl
import subprocess
import sys
import threading
import time
from contextlib import closing
from app.config import ROOT
from app.security import AppError

TEST_SLOT = threading.BoundedSemaphore(1)
DEFAULT_PORTS = {'oracle': 1521, 'mysql': 3306, 'sqlserver': 1433}


def validate_profile(data):
    def text(key, default='', maximum=128):
        value = data.get(key, default)
        if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
            raise AppError('CONNECTION', '连接参数格式或长度无效')
        return value.strip()

    name = text('name', maximum=120)
    engine, mode = text('engine'), text('mode', 'tcp')
    if not name or engine not in DEFAULT_PORTS or mode not in ('tcp', 'local'):
        raise AppError('CONNECTION', '请填写连接名称并选择有效数据库类型、连接方式')
    port = data.get('port', DEFAULT_PORTS[engine])
    if type(port) is not int or not 1 <= port <= 65535:
        raise AppError('CONNECTION', '端口必须为 1–65535 的整数')
    host = text('host', '127.0.0.1', 253) if mode == 'tcp' else '127.0.0.1'
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?', host):
            raise AppError('CONNECTION', '请填写有效 IP 地址或主机名，不包含协议和端口')
    options = dict(engine=engine, mode=mode, host=host, port=port, namespace=text('namespace'),
                   username=text('username'), local_instance=text('local_instance'),
                   service_kind=text('service_kind', 'service_name'), service_value=text('service_value'),
                   oracle_driver=text('oracle_driver', 'thick'), auth_type=text('auth_type', 'password'),
                   schema=text('schema'), encrypt=data.get('encrypt', True),
                   trust_certificate=data.get('trust_certificate', False))
    enabled = data.get('enabled', True)
    if any(type(value) is not bool for value in (enabled, options['encrypt'], options['trust_certificate'])):
        raise AppError('CONNECTION', '状态和加密选项必须为布尔值')
    if options['auth_type'] not in ('password', 'windows') or options['auth_type'] == 'windows' and engine != 'sqlserver':
        raise AppError('CONNECTION', 'Windows 身份验证仅适用于 SQL Server')
    if options['auth_type'] != 'windows' and not options['username']:
        raise AppError('CONNECTION', '请填写数据库用户名')
    if engine == 'oracle':
        if options['service_kind'] not in ('service_name', 'sid') or options['oracle_driver'] not in ('thin', 'thick'):
            raise AppError('CONNECTION', 'Oracle 服务类型或驱动模式无效')
        if mode == 'local' and options['local_instance']:
            if not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', options['local_instance']):
                raise AppError('CONNECTION', '本地 Oracle 服务请填写 TNS 别名')
        elif not options['service_value']:
            raise AppError('CONNECTION', '请填写 Oracle 服务名或 SID')
    if engine in ('mysql', 'sqlserver') and not options['namespace']:
        raise AppError('CONNECTION', '请填写命名空间（数据库名称）')
    if engine == 'sqlserver' and mode == 'local' and options['local_instance']:
        if not re.fullmatch(r'(?:\.|localhost|\(local\)|\(localdb\))(?:\\[A-Za-z0-9_$-]{1,100})?', options['local_instance'], re.I):
            raise AppError('CONNECTION', r'本地实例示例：localhost\SQLEXPRESS 或 (localdb)\MSSQLLocalDB')
    if engine != 'oracle':
        options['service_value'] = ''
    if mode != 'local' or engine == 'mysql':
        options['local_instance'] = ''
    if engine != 'sqlserver':
        options['schema'], options['trust_certificate'] = '', False
    if options['auth_type'] == 'windows':
        options['username'] = ''
    return name, options, enabled


def connection_password(data, previous, config):
    from app.security import cipher
    from cryptography.fernet import InvalidToken
    value = data.get('password', '')
    if not isinstance(value, str) or len(value) > 1024 or '\0' in value:
        raise AppError('CONNECTION', '数据库密码格式无效')
    if data.get('auth_type') == 'windows':
        return ''
    if value:
        return value
    if previous and previous.options['engine'] == data.get('engine') and previous.password_encrypted:
        try:
            return cipher(config).decrypt(previous.password_encrypted.encode()).decode()
        except InvalidToken:
            raise AppError('CONNECTION_KEY', '连接密码无法解密，请检查应用密钥或重新填写密码', 409) from None
    raise AppError('CONNECTION', '请填写数据库密码；编辑时留空保留已保存密码')


def _odbc_value(value):
    # Brace every value, including passwords, so semicolons cannot inject options.
    return '{' + str(value).replace('}', '}}') + '}'


def probe(options, password, client_dir=None, mysql_ca=None):
    engine = options['engine']
    connection = None
    try:
        if engine == 'oracle':
            import oracledb
            if options['oracle_driver'] == 'thick':
                oracledb.init_oracle_client(lib_dir=client_dir or None)
            params = dict(user=options['username'], password=password, tcp_connect_timeout=3, retry_count=0)
            if options['mode'] == 'local' and options['local_instance']:
                params['dsn'] = options['local_instance']
            else:
                params.update(host=options['host'], port=options['port'])
                params[options['service_kind']] = options['service_value']
            connection = oracledb.connect(**params)
            connection.call_timeout = 3000
        elif engine == 'mysql':
            import pymysql
            params = dict(host=options['host'], port=options['port'], user=options['username'], password=password,
                          database=options['namespace'], charset='utf8mb4', connect_timeout=3,
                          read_timeout=3, write_timeout=3, local_infile=False, autocommit=False)
            if options['encrypt']:
                params.update(ssl=ssl.create_default_context(cafile=mysql_ca or None), client_flag=pymysql.constants.CLIENT.SSL)
            else:
                params['ssl_disabled'] = True
            connection = pymysql.connect(**params)
        else:
            import pyodbc
            driver = next((name for name in ('ODBC Driver 18 for SQL Server', 'ODBC Driver 17 for SQL Server') if name in pyodbc.drivers()), None)
            if not driver:
                raise AppError('DRIVER_MISSING', '请在服务端安装 Microsoft ODBC Driver 18 或 17 for SQL Server')
            host = '[' + options['host'] + ']' if ':' in options['host'] else options['host']
            address = options['local_instance'] if options['mode'] == 'local' and options['local_instance'] else 'tcp:' + host + ',' + str(options['port'])
            values = dict(Driver=driver, Server=address, Database=options['namespace'],
                          Encrypt='yes' if options['encrypt'] else 'no',
                          TrustServerCertificate='yes' if options['trust_certificate'] else 'no')
            if options['auth_type'] == 'windows':
                values['Trusted_Connection'] = 'yes'
            else:
                values.update(UID=options['username'], PWD=password)
            connection = pyodbc.connect(';'.join(key + '=' + _odbc_value(value) for key, value in values.items()), timeout=3, autocommit=False)
            connection.timeout = 3
        with closing(connection.cursor()) as cursor:
            cursor.execute('SELECT 1 FROM DUAL' if engine == 'oracle' else 'SELECT 1')
            row = cursor.fetchone()
            if not row or row[0] != 1:
                raise AppError('PROBE_RESULT', '数据库探测语句未返回预期结果')
            if engine == 'oracle' and options['namespace']:
                cursor.execute('SELECT COUNT(*) FROM ALL_USERS WHERE USERNAME=:schema_name', {'schema_name': options['namespace'].upper()})
                if not cursor.fetchone()[0]:
                    raise AppError('NAMESPACE', '连接成功，但所填 Oracle 命名空间不存在或不可见')
            if engine == 'sqlserver' and options['schema']:
                cursor.execute('SELECT COUNT(*) FROM sys.schemas WHERE name=?', options['schema'])
                if not cursor.fetchone()[0]:
                    raise AppError('NAMESPACE', '连接成功，但所填 SQL Server Schema 不存在或不可见')
        return dict(status='PASSED', code='OK', message='连接成功，登录与只读探测已通过')
    except AppError as exc:
        return dict(status='FAILED', code=exc.code, message=exc.message)
    except ImportError:
        return dict(status='FAILED', code='DRIVER_MISSING', message='数据库 Python 驱动未安装，请按连接配置文档安装依赖')
    except Exception as exc:
        # Never return raw driver text: it can contain usernames, DSNs or passwords.
        description = str(exc)
        if 'DPI-1047' in description:
            code, message = 'ORACLE_CLIENT', '未找到可用 Oracle Client；Oracle 11g 请选择 Thick 并配置 64 位 Instant Client'
        elif any(token in description for token in ('ORA-01017', '1045', '28000', '18456')):
            code, message = 'AUTH_FAILED', '数据库身份验证失败，请检查用户名、密码及登录权限'
        elif any(token in description for token in ('ORA-12514', 'ORA-12505', 'DPY-6001')):
            code, message = 'SERVICE', 'Oracle 服务名或 SID 未注册，请核对监听配置'
        else:
            code, message = 'CONNECT_FAILED', '连接未通过，请检查实例、网络、端口、数据库权限、TLS 证书与驱动配置'
        return dict(status='FAILED', code=code, message=message)
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def test_connection(options, password, config):
    if not TEST_SLOT.acquire(blocking=False):
        raise AppError('CONNECTION_BUSY', '已有连接测试正在进行，请稍后重试', 409)
    started = time.monotonic()
    try:
        # Separate process bounds native-driver hangs and isolates Oracle Thin/Thick mode.
        payload = dict(options=options, password=password, client_dir=config.get('ORACLE_CLIENT_DIR'), mysql_ca=config.get('MYSQL_SSL_CA'))
        result = subprocess.run([sys.executable, '-m', 'app.services.connections'], input=json.dumps(payload),
                                capture_output=True, text=True, encoding='utf-8', timeout=10,
                                cwd=str(ROOT),
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0:
            return dict(status='FAILED', code='PROBE_FAILED', message='连接测试进程未完成，请检查服务端驱动安装', elapsed_ms=round((time.monotonic() - started) * 1000))
        response = json.loads(result.stdout)
        response['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        return response
    except subprocess.TimeoutExpired:
        return dict(status='FAILED', code='TIMEOUT', message='连接测试超过 10 秒，请检查地址、端口、监听及网络', elapsed_ms=10000)
    except (OSError, ValueError):
        return dict(status='FAILED', code='PROBE_FAILED', message='连接测试无法完成，请检查服务端驱动与运行环境', elapsed_ms=round((time.monotonic() - started) * 1000))
    finally:
        TEST_SLOT.release()


if __name__ == '__main__':
    request = json.loads(sys.stdin.read(65536))
    response = probe(request['options'], request['password'], request.get('client_dir'), request.get('mysql_ca'))
    print(json.dumps(response, ensure_ascii=True))
