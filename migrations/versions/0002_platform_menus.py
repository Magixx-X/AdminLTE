"""Add configurable platform navigation without changing historical grants."""
from alembic import op
from app.models import Menu

revision = '0002'
down_revision = '0001'


def upgrade():
    Menu.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('使用停服备份回滚，保留授权和审计历史')
