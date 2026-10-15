# 医院内网 SQL 查询管理系统 — Codex 完整开发交付规范

> 文件：`PROJECT_REQUIREMENTS.md`  
> 版本：1.0 | 目标：一次性完成可运行系统，不以静态 Demo 代替功能  
> 项目代号：HospitalQuerySystem | 技术路线：**AdminLTE 3.2 + Python 3.11 + Flask + SQLite + Oracle 11g**

## 0. Codex 执行指令（必须遵循）

你是本项目的全栈开发 Agent。先阅读本文件及现有项目文件，检查代码、依赖、目录和测试，然后**连续实施以下所有范围**，不要每完成一阶段就停下来等待确认。自行完成合理的安装、编码、测试、修复、打包和文档更新；尽量复用现有功能，避免不必要的重构和引入大型依赖。对不能在个人电脑验证的医院 Oracle 连接及真实业务 SQL，明确标记为 `PENDING_HOSPITAL_VALIDATION`，**不得假称已验证**。不得凭空构造真实医院凭据、IP、患者数据，也不得主动连接外部真实数据库。

完成标准：必须提供可启动的 Mock 开发模式、真实 Oracle 数据源实现、完整的后台页面及 API、安全控制、自动化测试、Windows 离线发布脚本、部署说明和 `PROJECT_STATUS.md`。在最后输出实际执行过的测试命令、结果、尚需医院环境验证的事项。

## 1. 项目目标与边界

### 1.1 场景
- 医院内网，预计 2–10 名授权用户；客户端包括 Windows 7 与旧版 Chrome，服务器优先使用仍获安全支持的 Windows Server（最终由医院提供）。
- 用户通过浏览器访问统一地址，服务器集中连接 Oracle Database 11g **11.2.0.4.0**，终端无需安装 Oracle 客户端。
- 开发电脑为 Windows 10/11，**无医院网络、无真实 Oracle 数据库**：必须支持合成数据 Mock 模式完成端到端功能开发及大多数测试。
- 业务功能：SQL 模板配置、查询条件、跨月份执行、分页结果、XLSX 导出、角色权限、查询审计、查询任务管理。

### 1.2 不做的事
- 不修改医院 Oracle 业务数据，不提供 DML/DDL 接口。
- 不在个人电脑、Git 仓库或发布包中放置真实患者信息、真实数据库密码。
- 不使用 Vue/React，不重新开发 AdminLTE 基础 UI 框架；不依赖公网 CDN。
- 首版不引入 Docker、Redis、Celery、微服务或分布式集群。
- 不支持普通用户提交任意 SQL 字符串直接执行；只允许执行经审核发布的模板。

## 2. 已确定技术栈

| 层 | 技术 | 约束 |
|---|---|---|
| 浏览器前端 | AdminLTE **3.2.0** / Bootstrap 4 / jQuery | 提供传统 iframe 多 Tab；静态资源本地化 |
| 业务页面 | HTML5/CSS3/JavaScript | 避免未经转译的现代 JS 语法；适配医院最低 Chrome 版本 |
| 表格 | AdminLTE 兼容的 DataTables | 服务器端分页优先；固定版本 |
| SQL 编辑 | CodeMirror 5 | 行号、格式高亮；编辑权限由服务端控制 |
| 后端语言 | Python **3.11 x64** | Flask 应用工厂模式 |
| HTTP API | Flask | JSON API；路由/服务/Repository 分层 |
| 正式 Web 服务 | Waitress | Windows 可运行；不要使用 Flask dev server 上线 |
| 配置持久化 | SQLite + SQLAlchemy + Alembic | WAL，busy_timeout，迁移机制 |
| 业务数据库 | Oracle 11g 11.2.0.4 | 只读账户，最小权限 |
| Oracle 驱动 | `python-oracledb==3.4.2` Thick 模式 | Oracle Instant Client **19c x64**；在医院验收版本兼容性 |
| Excel | openpyxl | write_only 流式导出，公式注入防护 |
| 登录与密码 | Flask 服务端会话 + Argon2id | CSRF、会话时效、登录失败限制 |
| 测试 | pytest + Flask test client | 单元、接口、权限、导出、Mock 集成测试 |
| Windows 服务 | Waitress + Windows 服务包装器（如 WinSW） | 使用低权限服务账户；日志滚动和自动重启 |

说明：上述固定版本是开发基线，不是对所有旧 Chrome、Oracle 11g 环境的已验证承诺；必须在目标环境实测。生产第三方依赖在构建时锁定精确版本并进行安全审查。

## 3. 系统架构

```text
Win7/Win10/Win11 浏览器（AdminLTE 3.2、iframe tabs）
       │ 同源 HTTPS / JSON API
       ▼
IIS 反向代理（推荐，按医院环境可选）
       │ 127.0.0.1
       ▼
Waitress → Flask
         ├─ Auth / RBAC / 模板审核
         ├─ 参数解析与绑定 / 查询任务 / 文件下载
         ├─ 系统元数据：SQLite（用户、模板、权限、任务、审计）
         └─ 受控独立 Worker → QueryProvider 接口
                               ├─ MockProvider（个人电脑；合成数据）
                               └─ OracleProvider（医院；只读 Oracle 11g）
```

### 3.1 模式隔离
- `APP_ENV=development`、`DATA_SOURCE=mock`：本地模式，默认合成数据、可完成完整用户操作流程。
- `APP_ENV=production`、`DATA_SOURCE=oracle`：生产模式；必须要求 Oracle 连接配置完整且成功自检；**连接失败不能自动切回 Mock**。
- Flask API 的响应字段、业务状态与前端交互在两种 Provider 下必须保持一致；Mock 只模拟结果与错误，不尝试以 SQLite 运行 Oracle 专有 SQL。

### 3.2 生产安全
- 服务端保存 Oracle 账号密码；不暴露至 JS、页面或日志。
- 仅允许已发布 SQL 模板和数据库已授权对象；数据库用户仅具有必要 SELECT/安全视图权限。
- 数据范围权限（科室/角色/其他必要条件）必须由服务端强制施加，不能依赖页面传参。若无法在数据库授权视图或经过审核的查询中安全实施数据范围限制，不允许上线该模板。
- 上传文件、导出结果、日志、配置文件放在不允许 Web 静态访问的路径。

## 4. 页面及 UI 需求

### 4.1 全局布局
- 基于 AdminLTE 3.2 的左侧可折叠菜单、顶部用户菜单和 **IFrame Plugin 多标签页**；标签切换、关闭、刷新、关闭其他、关闭全部；防止重复标签；无权限菜单不显示，但权限以服务端为准。
- 中文界面，布局紧凑适合医院办公终端；兼容不同分辨率，表格横向滚动与分页可用；所有静态资源本地化，不加载外网字体、图标、脚本。
- 全局加载中、空状态、网络失败、无权限、会话过期、查询超时、取消等反馈明确。
- 个人开发机页面必须可以在 Mock 模式下完整演示。

### 4.2 模块
1. **登录/退出**：账号密码、会话过期处理、当前用户信息。
2. **首页**：常用模板、最近任务、成功/失败统计、后台服务状态。
3. **查询中心**：选择授权模板、动态参数、执行/取消/重置、查询结果表格、导出。
4. **模板管理**：创建、复制、编辑、软删除、分类、搜索、草稿/提交审核/发布/停用、历史版本；SQL 高亮；参数 schema 编辑及校验。
5. **查询历史/任务**：按用户/模板/日期筛选，查看状态、耗时、行数、错误摘要和再执行入口。
6. **导出记录**：已授权文件下载、任务状态、有效期、删除/过期提示。
7. **账号/角色/授权**：用户管理、角色、模板执行/查看/导出权限、数据范围权限。
8. **系统设置与审计**：不显示明文密码；自检、查询限制、服务状态、审计检索、配置说明。

## 5. SQL 模板与参数

### 5.1 模板生命周期
- 模板字段：ID、名称、分类、描述、所有者、状态（DRAFT / REVIEW / PUBLISHED / DISABLED）、创建/更新时间、最新版本号。
- 模板版本独立保存 SQL 原文、参数 schema、可用排序字段、权限范围、版本摘要、审核人/时间；已发布版本不可被静默覆盖。
- 只有有权限的管理员可批准发布；普通用户只能执行获授权的 `PUBLISHED` 版本。
- SQL 允许 Oracle 11g 合法 CTE、分析函数、`LISTAGG`、批准的院内业务函数等，但发布前需要管理员审核和正式环境验证。

### 5.2 动态参数要求
- 支持 `string`、`integer`、`decimal`、`date`、`datetime`、`month`、单选、多选、布尔及可选参数。
- 起始月份和结束月份自动生成所有自然月份；快捷最近 3/6/12 月、本月、上月；允许超过 12 月，**但设置可配置的最大月份/耗时/导出配额**。
- 日期范围采用开始时间包含、结束边界排他（`>= :begin_time AND < :end_time`），月末准确，处理闰年。
- 含两个或更多可选参数时允许只选其中任一项、全部或全不选（若业务 schema 允许）；不可错误要求全部填写。
- 提供 3 种清除：清除模板、重置查询参数、重置全部。
- 后端校验参数类型、枚举值、长度、日期逻辑及可访问数据范围；执行 SQL 时使用绑定变量。
- 无法通过绑定变量传入的 SQL 标识符、排序字段等采用服务器端固定白名单，禁止用户自由拼接。

### 5.3 SQL 执行安全
- 不允许仅用字符串 `startswith('SELECT')`、正则或禁止关键词列表当作 SQL 沙箱；只读 Oracle 授权 + 已审核模板 + 参数绑定 + 执行资源约束作为核心防线。
- 可选在模板发布时借助 Oracle Parser/DBA 审核 SQL 依赖对象；复杂函数可能有副作用，需评估授权。
- 查询、导出、任务历史 API 全部检查用户、模板、数据范围、结果归属及授权。

## 6. 结果展示与 Excel

- 查询结果在 DataTables 分页展示；普通预览默认每页 100 行，上限由服务端设置，禁止把任意大的完整结果一次性传到浏览器。
- 数据可按允许字段排序；若查询本身不具备稳定排序，提醒分页结果可能不稳定，正式模板应明确排序规则。
- 每个查询月份可独立执行，但同一批次统一记录 `group_id`。
- 导出同一 XLSX：每月独立 Sheet（`YYYY-MM`），同月超行数拆为 `YYYY-MM_2` 等；控制 Excel Sheet 31 字符长度和名称非法字符。
- 使用 openpyxl `write_only` 流式写入；记录格式、日期、空值及中文；对不可信单元格文本的 `=`, `+`, `-`, `@` 等潜在公式注入前缀作安全处理。
- 导出时重新鉴权；文件名安全、文件只在受保护目录保存、可配置过期删除、下载受控；不允许以用户提供的任意路径下载文件。
- 文件大小/行数/并发上限可配置；超过限制返回可理解的提示并记录日志。

## 7. 用户权限和审计

### 7.1 RBAC
角色：`SYSTEM_ADMIN`（系统配置、用户及审核）、`SQL_EDITOR`（创建/编辑草稿）、`QUERY_USER`（执行已授权模板）。系统管理员**不自动拥有所有患者数据权限**。

权限标识：
- `user:manage`, `role:manage`, `system:configure`, `audit:view`
- `template:create`, `template:edit`, `template:approve`, `template:execute`
- `result:view`, `result:export`, `task:cancel`

模板级授权与用户/角色关联；所有后端资源操作检查对象所有权、模板许可、科室数据范围。未经授权的数据不可被导出、通过任务 ID 猜测获取或跨用户查看。

### 7.2 认证
- Argon2id 密码哈希；默认首次管理员账号通过安全初始化命令创建，**不在源码里写默认固定密码**。
- 安全会话、HttpOnly / SameSite Cookie、HTTPS 下 Secure Cookie、CSRF 校验；会话超时；登录失败限制；注销失效。
- 权限变化应使后续请求及时生效；管理员禁用账号后应阻止继续操作。

### 7.3 审计事件
登录成功/失败、退出、角色授权变更、模板版本创建/审核/发布、查询任务提交/状态/取消、导出生成和下载；包含用户 ID、时间、模板 ID/版本、任务 ID、操作结果、持续时间、行数和必要的非敏感参数摘要。日志不记录完整患者结果、数据库密码、会话密钥。

## 8. 任务调度及资源控制

- 初始受控限制：最多 **2** 个 Oracle 查询同时执行、**1** 个导出任务同时运行、Oracle 连接池最大 **4**；有界等待队列；实际值在医院按 DBA 建议调整。
- 查询超时初始建议 60 秒，复杂报表可单独配置至 180 秒或院内批准值；对 Oracle 查询取消/超时的真实效果必须集成测试。
- 不让长时间查询阻塞 Web 请求线程：API 提交任务后立即返回 `task_id`；前端轮询任务状态。
- 任务状态：`PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `INTERRUPTED`。
- **生产必须持久化任务记录**，由独立受控 Worker 执行；重启后清理/标记遗留运行态任务，允许安全地人工或自动重试。不能依靠单个进程内 `ThreadPoolExecutor` 保证任务持久可靠。
- 大结果集不全量缓存内存；预览结果与导出结果均按明确配额管理。对结果缓存不持久化患者敏感数据为默认策略，需要时通过安全、短期、授权的缓存方案实现。

## 9. SQLite 数据模型（最小集合）

- `users`：账号、哈希、启用状态、创建/更新时间。
- `roles`、`permissions`、`user_roles`、`role_permissions`：RBAC。
- `sql_templates`：模板基础信息及当前发布状态。
- `sql_template_versions`：不可变 SQL 版本、参数 schema、审核记录。
- `template_permissions`：角色/用户可执行、查看、导出授权。
- `data_scopes` / `user_data_scopes`：数据范围授权，不允许仅凭前端过滤。
- `query_tasks`：任务归属、模板版本、参数安全摘要、状态、时间、耗时、行数、错误摘要、group_id。
- `export_records`：任务归属、文件受控相对路径、状态、大小、到期时间。
- `audit_logs`：不可随意修改的操作记录。
- `system_settings`：不含明文密钥的应用设置。

提供 Alembic 迁移、SQLite WAL、busy_timeout、事务/索引策略；每天使用 SQLite Backup API 做一致性备份（不能简单复制正在写入的主 DB 文件）。

## 10. API 契约

统一返回：`{ "success": true|false, "data": ..., "error": { "code": "...", "message": "..." } }`；登录未授权 HTTP 401、权限不足 403、非法参数 400/422、资源不存在 404、冲突 409、服务错误 500。

| 方法 | 路径 | 权限/行为 |
|---|---|---|
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 注销 |
| GET | `/api/auth/me` | 当前账号/权限摘要 |
| GET | `/api/templates` | 已授权模板列表/筛选 |
| POST | `/api/templates` | 草稿创建 |
| PUT | `/api/templates/{id}` | 更新草稿、新增版本 |
| POST | `/api/templates/{id}/submit` | 提交审核 |
| POST | `/api/templates/{id}/publish` | 审核发布 |
| POST | `/api/templates/{id}/disable` | 停用 |
| GET | `/api/templates/{id}/versions` | 版本列表 |
| POST | `/api/queries` | 根据模板 ID/参数提交异步任务 |
| GET | `/api/queries/{id}` | 任务状态与摘要 |
| GET | `/api/queries/{id}/results` | 服务端分页/授权结果 |
| POST | `/api/queries/{id}/cancel` | 取消任务 |
| GET | `/api/queries/history` | 查询历史 |
| POST | `/api/exports` | 提交导出任务 |
| GET | `/api/exports/{id}` | 导出状态 |
| GET | `/api/exports/{id}/download` | 权限校验 + 下载 |
| GET/POST/PUT | `/api/admin/users` | 用户管理，实际按 REST 划分 |
| GET/POST/PUT | `/api/admin/roles` | 角色与授权 |
| GET | `/api/admin/audits` | 审计检索 |
| GET | `/api/admin/health` | 管理员健康检查（不得泄漏凭据） |

提交任务请求示意：`{"template_id": 7, "params": {"month_start": "2026-08", "month_end": "2026-09"}}`。**前端不发送可执行 SQL 原文**。

## 11. 推荐工程结构

```text
hospital-query-system/
├── PROJECT_REQUIREMENTS.md
├── PROJECT_STATUS.md
├── README.md
├── requirements.in
├── requirements.lock
├── .gitignore
├── .env.example
├── app/
│   ├── __init__.py             # Flask app factory
│   ├── config.py
│   ├── api/                    # auth/templates/queries/exports/admin
│   ├── services/               # auth/template/query/export/permission
│   ├── providers/              # base/mock/oracle
│   ├── repositories/           # SQLite CRUD
│   ├── models/                 # SQLAlchemy models
│   ├── security/               # CSRF/RBAC/SQL binding checks
│   ├── tasks/                  # durable queue/worker
│   ├── templates/              # 如果需要 HTML 模板渲染
│   └── static/                 # AdminLTE 3.2 与本地资源
├── migrations/
├── tests/
│   ├── unit/
│   ├── api/
│   ├── integration_mock/
│   └── hospital_pending/
├── scripts/
│   ├── init_admin.py
│   ├── package_offline.ps1
│   ├── install_offline.ps1
│   ├── start_server.ps1
│   ├── start_worker.ps1
│   ├── health_check.py
│   └── backup_sqlite.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── DEPLOY_WINDOWS.md
│   ├── TESTING.md
│   └── HOSPITAL_ACCEPTANCE.md
├── wsgi.py
└── worker.py
```

`data/`、`logs/`、`exports/`、`backups/`、`.venv/` 不提交 Git，也不能作为 Web 静态目录。保留部署目录权限边界。

## 12. 本地开发要求

- Python 3.11 x64、VS Code/Codex，纯本地 Mock 数据，不需要安装医院 Oracle 数据库。
- 开发服务启动：使用 Flask 开发服务；生产服务用 Waitress。提供 `README.md` 中可复制的准确启动命令（包含 Web 和 Worker）。
- 测试数据为**合成**科室、手术、设备/患者示例，不复制患者真实数据，也不把 Mock 数据伪装为生产查询结果。
- 先验证 UI 和 API（含未授权操作、超时/失败模拟），再构建离线发布包。
- 对 Oracle 专用 `LISTAGG`、`DBMS_LOB`、`ROW_NUMBER` 和自定义函数的实际语义，只能在 Oracle 11g 集成环境认证，不得通过 SQLite 假设兼容。

## 13. Windows 离线部署

### 13.1 发布包
- 应用源/运行文件与 AdminLTE 本地化静态资源。
- 固定 Python 依赖及 wheelhouse（确保适配部署 OS、架构与 Python 版本）。
- 数据库迁移和初始化脚本；默认配置示例（**无真实密码**）。
- Web 服务与 Worker 的 Windows 服务包装器配置及安装/卸载脚本。
- `DEPLOY_WINDOWS.md`、`HOSPITAL_ACCEPTANCE.md`、版本号及 SHA-256 校验清单。
- Oracle Instant Client 19c x64 依据医院软件采购/许可管理另行取得部署，不把未授权软件随意打入包内。

### 13.2 安装步骤
1. 医院确认部署机器系统是受支持的 Windows/Windows Server，具备已授权网络与只读数据库账户。
2. 将发布文件通过院方批准的方式传入内网，并校验 SHA-256。
3. 安装 Python 3.11 x64；在目标主机创建全新虚拟环境（**不直接复制开发机 `.venv`**）。
4. 从本地 wheelhouse 离线安装已锁定依赖。
5. 配置 Instant Client 19c x64 的实际 DLL 路径和所需运行库。
6. 通过环境变量或受保护配置设置 Oracle DSN、只读账号密码、会话密钥等；限制 Windows ACL。
7. 运行 SQLite 迁移及管理员安全初始化；设置定时一致性备份。
8. 使用 Waitress 监听 `127.0.0.1:8080`，后台 Worker 独立运行；都使用非管理员低权限服务账号。
9. 如具备条件，配置 IIS 反向代理与内网受信任 HTTPS 证书；受信任代理头需严格配置。
10. 仅开放必要端口、限定访问源网段；检查防火墙、数据库连接和日志；完成验收才启用生产。

### 13.3 运行维护
- 自动重启、日志滚动、磁盘空间预警、导出文件超期清理；更新前备份与回滚。
- 记录安装、升级、恢复、管理员重置、数据库凭据轮换操作。
- 旧版 Win7/Chrome 终端存在已知安全风险，必须符合院方安全政策并推进升级；后端服务不得因此安装到不再受支持的 Win7 系统。

## 14. 自动化测试与医院验收

### 14.1 个人电脑必须自动通过
1. 无 Oracle 网络/客户端仍可启动 Mock 模式，所有页面和主要 API 可用。
2. 用户登录、退出、禁用、会话失效、CSRF、角色及模板越权测试。
3. SQL 模板草稿→审核→发布→停用、版本不可变与历史可追溯。
4. 月份边界、跨年、闰年；最近 3/6/12 月、本月/上月；多选与可选参数组合。
5. 查询任务正常、排队、失败、超时、取消、中断、恢复状态。
6. 结果分页、排序白名单、下载授权及横向权限隔离。
7. 多月份 XLSX Sheet、中文和日期、超 Sheet 行数、公式注入测试。
8. 10 用户登录模拟、2 并发执行限制、导出上限测试。
9. 全静态资源本地加载、无公网依赖；基础页面自动化/UI 冒烟验证。
10. 打包脚本可生成 ZIP、离线依赖与 hash 文件；文档命令在目标兼容环境实测。

### 14.2 医院环境待验收（必须逐项留待医院执行）
- 真实 Oracle 11.2.0.4 与 python-oracledb Thick + Instant Client 19c 连接、NLS/编码、日期、LOB、自定义函数测试。
- 真实业务 SQL 结果与人工基准比对；查询资源配额及超时、取消行为。
- 2 个复杂查询并发、10 用户在线、大数据量导出、服务/数据库断连恢复。
- 院内最低版本 Chrome/Win7 客户端的登录、iframe Tab、DataTables、CodeMirror、月份控件和 XLSX 下载。
- 数据范围、脱敏、未授权任务访问、审计记录和正式部署安全检查。

## 15. Codex 工作流程与交付判定

1. 阅读仓库，列出已实现/未实现范围，保留既有有效代码；如果是空仓库，从零创建。
2. 建立清晰的项目模块、SQLite 迁移、MockProvider、OracleProvider 接口和测试基础。
3. 继续开发全部页面、登录 RBAC、SQL 模板生命周期、参数生成、任务、结果分页及 XLSX；不暂停征求逐项许可。
4. 补齐负面/权限/边界测试，运行所有可运行测试；自动修复失败直到通过或明确记录真实阻碍。
5. 完成 Windows 离线部署脚本、服务启动、备份/恢复脚本及部署说明。
6. 写 `PROJECT_STATUS.md`：版本、已完成功能、修改文件、执行命令、测试结果、已知问题、医院待验收清单和准确启动方式。
7. 最终说明**已执行**和**未能执行**的验证，禁止声称已完成医院 Oracle 真实环境测试。

### 完成条件

- [ ] Mock 模式可完整运行；不存在仅展示而不能操作的主要页面。
- [ ] Flask API / SQLite / RBAC / 审核版 SQL 模板 / 参数 / 任务 / Excel 流程打通。
- [ ] OracleProvider 生产实现可配置、代码完整，医院环境测试项清晰。
- [ ] 旧版浏览器兼容约束、离线静态资源及 Windows 发布流程落实。
- [ ] 测试记录、SQL 安全机制、审计、部署与恢复文档交付。
- [ ] `PROJECT_STATUS.md` 同步最新真实状态。

**重要：** 不得用“代码已写完”替代自动化测试与交付验证；未在医院网络中完成的兼容性、性能和真实 SQL 验收，一律标记待验证。
