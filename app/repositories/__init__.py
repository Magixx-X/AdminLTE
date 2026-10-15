from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.models import AuditLog, Setting


class Repository:
    def __init__(self, url):
        self.engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 10})
        @event.listens_for(self.engine, 'connect')
        def pragmas(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA busy_timeout=10000')
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def transaction(self):
        with self.sessions() as session:
            with session.begin():
                yield session


def audit(db, action, user_id=None, **fields):
    db.add(AuditLog(action=action, user_id=user_id, **fields))


def limit(db, config, key):
    item = db.get(Setting, key)
    return item.value if item else config[key]
