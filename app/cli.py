import getpass
import click
from sqlalchemy import select
from app.models import User, Role, Permission, UserRole, RolePermission, DataScope, Template, TemplateVersion, TemplatePermission, UserDataScope
from app.security import password
from app.repositories import audit
from app.navigation import PAGES, seed_menus
from app.models import Setting

ROLE_DEFAULTS = {
    'SYSTEM_ADMIN': ['user:manage', 'role:manage', 'system:configure', 'audit:view', 'template:create', 'template:edit', 'template:approve'],
    'SQL_EDITOR': ['template:create', 'template:edit', 'template:approve', 'about:view'],
    'QUERY_USER': ['template:execute', 'result:view', 'result:export', 'task:cancel', 'history:view', 'about:view'],
}

ROLE_DEFAULTS['SYSTEM_ADMIN'] += ['authorization:manage', 'menu:manage', 'department:manage', 'monitor:view', 'about:view', 'history:view', 'template:grant', 'query:configure']
ROLE_DEFAULTS['SYSTEM_ADMIN'] += ['connection:manage']

def seed_roles(db):
    seed_menus(db)
    for name in sorted(set(sum(ROLE_DEFAULTS.values(), []) + sum([v[2] for v in PAGES.values()], []))):
        if not db.get(Permission, name):
            db.add(Permission(name=name))
    db.flush()
    for name, perms in ROLE_DEFAULTS.items():
        role = db.scalar(select(Role).where(Role.name == name))
        if not role:
            role = Role(name=name, code=name)
            db.add(role)
            db.flush()
            for perm in perms:
                db.add(RolePermission(role_id=role.id, permission=perm))

    if not db.get(Setting, 'platform_menu_migration'):
        db.flush()
        for role in db.scalars(select(Role)):
            old = set(db.scalars(select(RolePermission.permission).where(RolePermission.role_id == role.id)))
            additions = {'about:view', 'history:view'}
            for source, targets in {'role:manage': ['authorization:manage', 'template:grant'],
                                    'user:manage': ['department:manage'],
                                    'system:configure': ['menu:manage', 'monitor:view', 'query:configure']}.items():
                if source in old:
                    additions.update(targets)
            for perm in additions - old:
                db.add(RolePermission(role_id=role.id, permission=perm))
        db.add(Setting(key='platform_menu_migration', value=1))

    if not db.get(Setting, 'connection_menu_migration'):
        db.flush()
        for rid in db.scalars(select(RolePermission.role_id).where(RolePermission.permission == 'system:configure')):
            if not db.get(RolePermission, (rid, 'connection:manage')):
                db.add(RolePermission(role_id=rid, permission='connection:manage'))
        db.add(Setting(key='connection_menu_migration', value=1))


def register_cli(app):
    @app.cli.command('migrate')
    def migrate():
        from alembic.config import Config
        from alembic import command
        cfg = Config(str(__import__('app.config', fromlist=['ROOT']).ROOT / 'alembic.ini'))
        cfg.set_main_option('sqlalchemy.url', app.config['DATABASE_URL'].replace('%', '%%'))
        command.upgrade(cfg, 'head')
        with app.extensions['repo'].transaction() as db:
            seed_roles(db)
        click.echo('SQLite 迁移完成')

    @app.cli.command('init-admin')
    @click.option('--username', prompt='管理员账号')
    def init_admin(username):
        if not __import__('re').fullmatch(r'[A-Za-z0-9_.-]{3,80}', username):
            raise click.ClickException('账号格式无效')
        secret = getpass.getpass('管理员密码（6–128 字符）：')
        if secret != getpass.getpass('确认密码：'):
            raise click.ClickException('密码不一致')
        with app.extensions['repo'].transaction() as db:
            seed_roles(db)
            if db.scalar(select(User).where(User.username == username)):
                raise click.ClickException('账号已存在，请使用 reset-password')
            user = User(username=username, password_hash=password(secret))
            db.add(user)
            db.flush()
            role = db.scalar(select(Role).where(Role.name == 'SYSTEM_ADMIN'))
            db.add(UserRole(user_id=user.id, role_id=role.id))
            audit(db, 'admin.initialize', user.id)
        click.echo('管理员已创建；没有自动授予任何数据范围或模板权限')

    @app.cli.command('reset-password')
    @click.argument('username')
    def reset(username):
        secret = getpass.getpass('新密码：')
        if secret != getpass.getpass('确认新密码：'):
            raise click.ClickException('密码不一致')
        with app.extensions['repo'].transaction() as db:
            user = db.scalar(select(User).where(User.username == username))
            if not user:
                raise click.ClickException('账号不存在')
            user.password_hash, user.auth_epoch = password(secret), user.auth_epoch + 1
            audit(db, 'admin.password_reset', detail={'target_user_id': user.id})
        click.echo('密码已重置，原会话失效')

    @app.cli.command('seed-mock')
    @click.argument('username')
    def seed_mock(username):
        if app.extensions['provider'].source != 'mock' or app.config['APP_ENV'] == 'production':
            raise click.ClickException('仅开发 Mock 模式允许此命令')
        with app.extensions['repo'].transaction() as db:
            user = db.scalar(select(User).where(User.username == username))
            if not user:
                raise click.ClickException('先安全初始化账号')
            role = db.scalar(select(Role).where(Role.name == 'QUERY_USER'))
            if not db.get(UserRole, (user.id, role.id)):
                db.add(UserRole(user_id=user.id, role_id=role.id))
            for code, label in [('D001', '合成外科'), ('D002', '合成影像科')]:
                if not db.get(DataScope, code):
                    db.add(DataScope(code=code, name=label))
                    db.flush()
                if not db.get(UserDataScope, (user.id, code)):
                    db.add(UserDataScope(user_id=user.id, scope_code=code))
            item = db.scalar(select(Template).where(Template.name == '合成就诊月报', Template.deleted == False))
            if not item:
                item = Template(name='合成就诊月报', category='Mock 合成示例', owner_id=user.id, status='PUBLISHED', published_version=1)
                db.add(item)
                db.flush()
                db.add(TemplateVersion(template_id=item.id, number=1,
                    sql='SELECT record_id, department, patient_label, equipment, amount, visit_time\nFROM hospital_approved_view\nWHERE department = :scope_department\nAND visit_time >= :begin_time AND visit_time < :end_time\nAND (:keyword IS NULL OR patient_label LIKE :keyword)\nORDER BY record_id',
                    schema=[{'name': 'keyword', 'type': 'string', 'label': '样例关键词', 'required': False},
                            {'name': 'equipment', 'type': 'multiselect', 'label': '设备', 'choices': ['CT', 'MRI', '超声']},
                            {'name': 'sample_rows', 'type': 'integer', 'label': '合成行数', 'default': 240, 'min': 1, 'max': 500000},
                            {'name': 'scenario', 'type': 'select', 'label': 'Mock 场景', 'choices': ['normal', 'slow', 'failure', 'timeout'], 'default': 'normal'}],
                    sort_fields=['record_id', 'department', 'amount', 'visit_time'], scope_policy={'kind': 'department_bind'},
                    summary='仅合成数据。示例 SQL 不用于生产；医院必须改为真实批准视图并验收。', reviewer_id=user.id, reviewed_at=__import__('app.models', fromlist=['now']).now()))
            grant = db.scalar(select(TemplatePermission).where(TemplatePermission.template_id == item.id, TemplatePermission.user_id == user.id))
            if not grant:
                grant = TemplatePermission(template_id=item.id, user_id=user.id)
                db.add(grant)
            grant.execute, grant.view, grant.export = True, True, True
            audit(db, 'mock.seed', user.id, template_id=item.id)
        click.echo('合成模板、数据范围和查询权限已准备；Oracle 验收仍待执行')
