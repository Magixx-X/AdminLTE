from alembic import context
from sqlalchemy import create_engine, pool
from app.models import Base

config = context.config
engine = create_engine(config.get_main_option('sqlalchemy.url'), poolclass=pool.NullPool)
with engine.connect() as connection:
    connection.exec_driver_sql('PRAGMA foreign_keys=ON')
    connection.exec_driver_sql('PRAGMA journal_mode=WAL')
    connection.exec_driver_sql('PRAGMA busy_timeout=10000')
    connection.commit()
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()
