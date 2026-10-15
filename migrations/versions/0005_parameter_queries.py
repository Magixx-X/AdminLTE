"""Save-to-query templates and parameter-driven execution; preserve historical versions."""
from alembic import op

revision = '0005'
down_revision = '0004'


def upgrade():
    db = op.get_bind()
    db.exec_driver_sql("UPDATE sql_templates SET status='PUBLISHED', published_version=latest_version WHERE deleted=0 AND status IN ('DRAFT','REVIEW')")
    db.exec_driver_sql("""INSERT INTO template_permissions (template_id,user_id,execute,view,export)
        SELECT t.id,t.owner_id,1,1,1 FROM sql_templates t WHERE t.deleted=0
        AND NOT EXISTS (SELECT 1 FROM template_permissions p WHERE p.template_id=t.id AND p.user_id=t.owner_id)""")
    for permission in ('template:execute', 'result:view', 'result:export', 'task:cancel', 'history:view'):
        db.exec_driver_sql("""INSERT INTO role_permissions (role_id,permission)
            SELECT DISTINCT p.role_id,? FROM role_permissions p
            WHERE p.permission IN ('template:create','template:edit')
            AND NOT EXISTS (SELECT 1 FROM role_permissions q WHERE q.role_id=p.role_id AND q.permission=?)""", (permission, permission))
    db.exec_driver_sql("DELETE FROM role_permissions WHERE permission='template:approve'")
    db.exec_driver_sql("DELETE FROM permissions WHERE name='template:approve'")


def downgrade():
    raise RuntimeError('请使用停服备份回滚，保留模板版本及查询历史')
