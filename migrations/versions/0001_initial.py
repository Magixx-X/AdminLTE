"""Initial metadata schema, immutable versions and append-only audit."""
from alembic import op
from app.models import Base

revision = '0001'
down_revision = None


def upgrade():
    Base.metadata.create_all(op.get_bind())
    op.execute("CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_logs BEGIN SELECT RAISE(ABORT, 'audit append only'); END")
    op.execute("CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_logs BEGIN SELECT RAISE(ABORT, 'audit append only'); END")
    op.execute("CREATE TRIGGER version_immutable BEFORE UPDATE OF sql, schema, sort_fields, scope_policy, summary, number, template_id ON sql_template_versions BEGIN SELECT RAISE(ABORT, 'version immutable'); END")
    op.execute("CREATE TRIGGER version_no_delete BEFORE DELETE ON sql_template_versions BEGIN SELECT RAISE(ABORT, 'version immutable'); END")
    op.execute("CREATE TRIGGER review_once BEFORE UPDATE OF reviewer_id, reviewed_at, validation ON sql_template_versions WHEN OLD.reviewed_at IS NOT NULL BEGIN SELECT RAISE(ABORT, 'review immutable'); END")


def downgrade():
    raise RuntimeError('禁止自动销毁审计和模板历史；回滚使用停服后的验收备份')
