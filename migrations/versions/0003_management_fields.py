"""Department hierarchy and management fields, preserving historical grants."""
from datetime import datetime, timezone
import sqlalchemy as sa
from alembic import op

revision = '0003'
down_revision = '0002'


def upgrade():
    connection = op.get_bind()
    # 0001 uses current metadata on fresh installs; existing installs need additions.
    additions = {
        'users': [sa.Column('nickname', sa.String(80), nullable=False, server_default=''),
                  sa.Column('contact', sa.String(120), nullable=False, server_default='')],
        'roles': [sa.Column('code', sa.String(80)),
                  sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
                  sa.Column('remark', sa.String(500), nullable=False, server_default=''),
                  sa.Column('created_at', sa.String())],
        'menus': [sa.Column('deleted', sa.Boolean(), nullable=False, server_default=sa.false())],
        'data_scopes': [sa.Column('parent', sa.String(80)),
                        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
                        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
                        sa.Column('remark', sa.String(500), nullable=False, server_default=''),
                        sa.Column('created_at', sa.String())],
    }
    for table, columns in additions.items():
        existing = {column['name'] for column in sa.inspect(connection).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)
    connection.execute(sa.text("UPDATE roles SET code = 'ROLE_' || id WHERE code IS NULL"))
    timestamp = datetime.now(timezone.utc).isoformat()
    for table in ('roles', 'data_scopes'):
        connection.execute(sa.text(f'UPDATE {table} SET created_at=:timestamp WHERE created_at IS NULL'), {'timestamp': timestamp})
    if not any(index['name'] == 'uq_roles_code' for index in sa.inspect(connection).get_indexes('roles')):
        op.create_index('uq_roles_code', 'roles', ['code'], unique=True)


def downgrade():
    raise RuntimeError('使用停服备份回滚，保留用户、授权与审计历史')
