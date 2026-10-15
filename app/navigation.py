"""One menu catalog shared by navigation, role grants and page access.

Internal operation codes remain an implementation detail; data scopes and
reviewed SQL grants remain independent security boundaries.
"""
from sqlalchemy import select
from app.models import Menu

GROUPS = [('query_management', '查询管理', 'search'), ('permissions', '权限管理', 'key'),
          ('system', '系统管理', 'cogs'), ('monitoring', '系统监控', 'heartbeat'), ('information', '关于', 'info-circle')]
PAGES = {
    'query': ('query_management', 'SQL 查询', ['template:execute', 'result:view', 'task:cancel']),
    'templates': ('query_management', '查询模板', ['template:create', 'template:edit', 'template:approve']),
    'history': ('query_management', '查询任务', ['history:view']),
    'exports': ('query_management', '导出记录', ['result:export']),
    'grants': ('query_management', '模板数据授权', ['template:grant']),
    'query_settings': ('query_management', '查询配置', ['query:configure']),
    'authorization': ('permissions', '角色菜单授权', ['authorization:manage']),
    'users': ('system', '用户管理', ['user:manage']),
    'roles': ('system', '角色管理', ['role:manage']),
    'menus': ('system', '菜单管理', ['menu:manage']),
    'departments': ('system', '部门管理', ['department:manage']),
    'connections': ('system', '连接配置', ['connection:manage']),
    'settings': ('system', '系统设置', ['system:configure']),
    'monitor': ('monitoring', '运行状态', ['monitor:view']),
    'audits': ('monitoring', '审计日志', ['audit:view']),
    'about': ('information', '平台信息', ['about:view']),
}


def seed_menus(db):
    for order, (code, title, icon) in enumerate(GROUPS):
        if not db.get(Menu, code):
            db.add(Menu(code=code, title=title, icon=icon, position=order * 10))
    db.flush()
    for order, (code, (parent, title, _)) in enumerate(PAGES.items()):
        if not db.get(Menu, code):
            db.add(Menu(code=code, title=title, parent=parent, icon='circle', position=order * 10))


def available(db, perms):
    items = db.scalars(select(Menu).order_by(Menu.position, Menu.code)).all()
    enabled_groups = {m.code for m in items if m.enabled and not m.deleted and not m.parent}
    return [m for m in items if m.enabled and not m.deleted and m.parent in enabled_groups and m.code in PAGES
            and set(PAGES[m.code][2]).issubset(perms)]


def tree(db, perms):
    leaves = available(db, perms)
    groups = db.scalars(select(Menu).where(Menu.parent == None).order_by(Menu.position, Menu.code))
    return [dict(code=g.code, title=g.title, icon=g.icon, children=[m for m in leaves if m.parent == g.code])
            for g in groups if any(m.parent == g.code for m in leaves)]
