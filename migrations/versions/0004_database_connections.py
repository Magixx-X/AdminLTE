"""Saved, encrypted database connection profiles."""
from alembic import op
from app.models import DatabaseConnection

revision = '0004'
down_revision = '0003'


def upgrade():
    DatabaseConnection.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('请使用停服备份回滚，保留连接与审计历史')
