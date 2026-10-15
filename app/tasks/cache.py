import hashlib
import hmac
import json
import socket
import socketserver
import threading
import time
from datetime import date, datetime
from decimal import Decimal
from app.security import AppError


def scalar(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


class ResultCache:
    """Worker-owned, bounded, short-lived memory; no patient preview rows on disk."""
    def __init__(self, config):
        self.config, self.items, self.lock = config, {}, threading.Lock()

    def put(self, tid, columns, rows):
        rows = [[scalar(v) for v in row] for row in rows]
        size = len(json.dumps(rows, ensure_ascii=False).encode())
        if size > self.config['CACHE_BYTES']:
            raise AppError('CACHE_QUOTA', '结果内存配额不足，请缩小查询范围', 409)
        with self.lock:
            self.purge()
            while sum(v[3] for v in self.items.values()) + size > self.config['CACHE_BYTES'] and self.items:
                del self.items[min(self.items, key=lambda k: self.items[k][0])]
            self.items[tid] = (time.time() + self.config['RESULT_TTL'], columns, rows, size)

    def purge(self):
        for key in list(self.items):
            if self.items[key][0] < time.time():
                del self.items[key]

    def page(self, tid, start, length, sort='', direction='asc'):
        with self.lock:
            self.purge()
            item = self.items.get(tid)
            if not item:
                raise AppError('RESULT_EXPIRED', '预览已过期或 Worker 已重启，请重新执行', 410)
            columns, rows = item[1], item[2]
            if sort:
                names = [c.lower() for c in columns]
                if sort.lower() not in names:
                    raise AppError('SORT', '此结果不存在指定排序字段')
                index = names.index(sort.lower())
                rows = sorted(rows, key=lambda r: (r[index] is None, r[index]), reverse=direction == 'desc')
            return {'columns': columns, 'rows': rows[start:start + length], 'data': rows[start:start + length]}


def mac(secret, payload):
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def cache_server(config, cache):
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.connection.settimeout(3)
            try:
                message = json.loads(self.rfile.readline(8192))
                payload = message['payload']
                if not hmac.compare_digest(message['signature'], mac(config['SECRET_KEY'], payload)):
                    return
                args = json.loads(payload)
                if abs(time.time() - args.pop('timestamp')) > 10:
                    return
                if not 1 <= args.get('length', 0) <= 500:
                    return
                data = {'data': cache.page(**args)}
            except AppError as exc:
                data = {'error': {'code': exc.code, 'message': exc.message, 'status': exc.status}}
            except (ValueError, KeyError, TypeError):
                return
            self.wfile.write((json.dumps(data, ensure_ascii=False) + '\n').encode())
    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
    server = Server(('127.0.0.1', config['IPC_PORT']), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def get_page(app, tid, start, length, sort, direction):
    if app.extensions.get('result_cache'):
        return app.extensions['result_cache'].page(tid, start, length, sort, direction)
    payload = json.dumps(dict(tid=tid, start=start, length=length, sort=sort, direction=direction, timestamp=time.time()))
    try:
        with socket.create_connection(('127.0.0.1', app.config['IPC_PORT']), timeout=3) as sock:
            sock.sendall((json.dumps({'payload': payload, 'signature': mac(app.config['SECRET_KEY'], payload)}) + '\n').encode())
            raw = sock.makefile('rb').readline(app.config['CACHE_BYTES'] * 2)
            result = json.loads(raw)
        if 'error' in result:
            err = result['error']
            raise AppError(err['code'], err['message'], err['status'])
        return result['data']
    except (OSError, ValueError):
        raise AppError('WORKER_UNAVAILABLE', 'Worker 未启动或预览服务不可用', 503)
