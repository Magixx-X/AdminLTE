from sqlalchemy import select
from app.models import Template, TemplateVersion
from app.repositories import audit
from app.security import AppError
from app.services.parameters import validate_schema


def version_for(db, template, published=False):
    number = template.published_version if published else template.latest_version
    return db.scalar(select(TemplateVersion).where(TemplateVersion.template_id == template.id, TemplateVersion.number == number))


def editable(template, uid, permissions):
    if 'template:edit' not in permissions or (template.owner_id != uid and 'template:approve' not in permissions):
        raise AppError('FORBIDDEN', '仅所有者或审核管理员可以编辑', 403)


def new_version(db, template, body, uid):
    sql, schema = body.get('sql', ''), body.get('schema', [])
    fields, policy = body.get('sort_fields', []), body.get('scope_policy', {})
    validate_schema(schema, fields, policy, sql)
    item = TemplateVersion(template_id=template.id, number=template.latest_version, sql=sql,
        schema=schema, sort_fields=fields, scope_policy=policy, summary=str(body.get('summary', ''))[:1000])
    db.add(item)
    db.flush()
    audit(db, 'template.version.create', uid, template_id=template.id, version_id=item.id)
    return item


def template_json(db, template, include_sql=False):
    item = version_for(db, template, published=not include_sql)
    data = {k: getattr(template, k) for k in ('id', 'name', 'category', 'description', 'owner_id', 'status', 'latest_version', 'published_version', 'updated_at')}
    if item:
        data.update(schema=item.schema, sort_fields=item.sort_fields, scope_policy=item.scope_policy, validation=item.validation, version_id=item.id)
        if include_sql:
            data.update(sql=item.sql, summary=item.summary)
    return data
