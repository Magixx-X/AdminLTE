from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, Float, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def now():
    return datetime.now(timezone.utc).isoformat()


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    nickname = Column(String(80), nullable=False, default='')
    contact = Column(String(120), nullable=False, default='')
    password_hash = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    auth_epoch = Column(Integer, default=0, nullable=False)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now, onupdate=now)


class Role(Base):
    __tablename__ = 'roles'
    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    code = Column(String(80), unique=True)
    enabled = Column(Boolean, nullable=False, default=True)
    remark = Column(String(500), nullable=False, default='')
    created_at = Column(String, default=now)


class Permission(Base):
    __tablename__ = 'permissions'
    name = Column(String(80), primary_key=True)


class Menu(Base):
    __tablename__ = 'menus'
    code = Column(String(80), primary_key=True)
    title = Column(String(80), nullable=False)
    parent = Column(ForeignKey('menus.code'))
    icon = Column(String(40), nullable=False, default='circle')
    position = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    deleted = Column(Boolean, nullable=False, default=False)


class UserRole(Base):
    __tablename__ = 'user_roles'
    user_id = Column(ForeignKey('users.id'), primary_key=True)
    role_id = Column(ForeignKey('roles.id'), primary_key=True)


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    role_id = Column(ForeignKey('roles.id'), primary_key=True)
    permission = Column(ForeignKey('permissions.name'), primary_key=True)


class DataScope(Base):
    __tablename__ = 'data_scopes'
    code = Column(String(80), primary_key=True)
    name = Column(String(120), nullable=False)
    parent = Column(ForeignKey('data_scopes.code'))
    position = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    remark = Column(String(500), nullable=False, default='')
    created_at = Column(String, default=now)


class UserDataScope(Base):
    __tablename__ = 'user_data_scopes'
    user_id = Column(ForeignKey('users.id'), primary_key=True)
    scope_code = Column(ForeignKey('data_scopes.code'), primary_key=True)


class Template(Base):
    __tablename__ = 'sql_templates'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    category = Column(String(80), default='报表')
    description = Column(Text, default='')
    owner_id = Column(ForeignKey('users.id'), nullable=False)
    status = Column(String(20), default='PUBLISHED', index=True)
    latest_version = Column(Integer, default=1)
    published_version = Column(Integer)
    deleted = Column(Boolean, default=False)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now, onupdate=now)


class TemplateVersion(Base):
    __tablename__ = 'sql_template_versions'
    id = Column(Integer, primary_key=True)
    template_id = Column(ForeignKey('sql_templates.id'), nullable=False, index=True)
    number = Column(Integer, nullable=False)
    sql = Column(Text, nullable=False)
    schema = Column(JSON, nullable=False)
    sort_fields = Column(JSON, default=list)
    # Legacy columns remain readable for existing databases and immutable history.
    scope_policy = Column(JSON, nullable=False, default=dict)
    summary = Column(Text, default='')
    reviewer_id = Column(ForeignKey('users.id'))
    reviewed_at = Column(String)
    validation = Column(String, default='PENDING_HOSPITAL_VALIDATION')
    created_at = Column(String, default=now)
    __table_args__ = (UniqueConstraint('template_id', 'number'),)


class TemplatePermission(Base):
    __tablename__ = 'template_permissions'
    id = Column(Integer, primary_key=True)
    template_id = Column(ForeignKey('sql_templates.id'), nullable=False, index=True)
    user_id = Column(ForeignKey('users.id'))
    role_id = Column(ForeignKey('roles.id'))
    execute = Column(Boolean, default=False)
    view = Column(Boolean, default=False)
    export = Column(Boolean, default=False)


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(ForeignKey('users.id'), nullable=False)
    epoch = Column(Integer, nullable=False)
    expires = Column(Float, nullable=False)
    csrf = Column(String(80), nullable=False)


class LoginAttempt(Base):
    __tablename__ = 'login_attempts'
    id = Column(Integer, primary_key=True)
    key = Column(String(64), index=True)
    timestamp = Column(Float, nullable=False)


class QueryTask(Base):
    __tablename__ = 'query_tasks'
    id = Column(String(36), primary_key=True)
    group_id = Column(String(36), nullable=False, index=True)
    user_id = Column(ForeignKey('users.id'), nullable=False, index=True)
    template_id = Column(ForeignKey('sql_templates.id'), nullable=False)
    version_id = Column(ForeignKey('sql_template_versions.id'), nullable=False)
    month = Column(String(7), nullable=False)
    payload = Column(Text, nullable=False)  # authenticated encryption; never log parameter values
    params_summary = Column(JSON, default=dict)
    scopes = Column(JSON, nullable=False)
    status = Column(String(20), default='PENDING', index=True)
    cancel_requested = Column(Boolean, default=False)
    error_code = Column(String(80))
    error = Column(Text)
    row_count = Column(Integer, default=0)
    truncated = Column(Boolean, default=False)
    columns = Column(JSON, default=list)
    created_at = Column(String, default=now, index=True)
    started_at = Column(String)
    finished_at = Column(String)
    duration = Column(Float)


class ExportRecord(Base):
    __tablename__ = 'export_records'
    id = Column(String(36), primary_key=True)
    user_id = Column(ForeignKey('users.id'), nullable=False, index=True)
    group_id = Column(String(36), nullable=False)
    status = Column(String(20), default='PENDING', index=True)
    relative_path = Column(String(100))
    size = Column(Integer, default=0)
    row_count = Column(Integer, default=0)
    created_at = Column(String, default=now)
    expires = Column(Float, nullable=False)
    error = Column(Text)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, index=True)
    action = Column(String(80), nullable=False, index=True)
    timestamp = Column(String, default=now, index=True)
    template_id = Column(Integer)
    version_id = Column(Integer)
    task_id = Column(String)
    result = Column(String(30), default='OK')
    duration = Column(Float)
    row_count = Column(Integer)
    detail = Column(JSON, default=dict)


class Setting(Base):
    __tablename__ = 'system_settings'
    key = Column(String(80), primary_key=True)
    value = Column(JSON)


class DatabaseConnection(Base):
    __tablename__ = 'database_connections'
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    options = Column(JSON, nullable=False)
    password_encrypted = Column(Text, nullable=False, default='')
    enabled = Column(Boolean, nullable=False, default=True)
    revision = Column(Integer, nullable=False, default=1)
    last_test_status = Column(String(20), nullable=False, default='UNTESTED')
    last_test_at = Column(String)
    last_test_message = Column(String(300), default='')
    last_test_ms = Column(Integer)
    created_at = Column(String, default=now)
    updated_at = Column(String, default=now, onupdate=now)
