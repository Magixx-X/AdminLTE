# 信息查询管理 1.1.0

## 模板与查询流程（当前版本）

模板保存后直接可查询，已移除提交审核、发布、验收证据及数据范围策略。SQL 的每个绑定参数在参数 schema 中声明类型；不再要求 begin_time/end_time 或科室参数，也不再显示独立的开始/结束月份。模板创建者自动获得自己的模板访问权限，其他用户仍通过菜单和模板授权访问。

日期范围结束参数用 end_after 指向开始参数，开始包含、结束不含。查询页按类型生成输入框并提供本月、上月、最近3/6/12月快捷填充；跨月自动按自然月切分实际参数，结果直接显示在月份标签中，导出每个月一个工作表。无日期范围的 SQL 执行一次。多个日期范围时可在选定的结束参数设置 split_by_month=true；false 可关闭该范围拆月。

更新前停服备份 SQLite 和密钥，更新后重启 Web/Worker；双击启动入口自动执行 0005 迁移，Windows 服务部署先手动运行 migrate。迁移保留账号、历史版本和查询记录，使原草稿/审核中模板可查询；停用模板保持停用。旧版科室绑定 SQL 需编辑为普通 SQL 参数或移除对应条件后保存，历史字段仅用于数据兼容。旧 release ZIP 未重新打包。示例见 [报表 SQL 和填写规范](docs/sql/README.md)。

## 网页配置数据库（当前启动流程）

新电脑安装依赖后，双击 `01_init_admin.cmd` 初始化平台管理员，再双击 `02_start_system.cmd`。无需预先填写 Oracle 账号、DSN、客户端目录或 APP_SECRET；应用密钥自动保存到 `data/application.key`，已有 `data/development.key` 或显式 APP_SECRET 优先沿用。首次启动只连接本地 SQLite，Oracle 不可用不会阻止登录。

登录“系统管理 → 连接配置”，新增 Oracle 并填写地址、端口、服务名/SID、账号、密码和包含 oci.dll 的目录，点击“保存并测试”。通过后自动设为 SQL 查询数据源，Web 与 Worker 按需读取，无需重启；多个 Oracle 连接以最近一次保存测试通过者为准。失败或未配置时明确提示，不回退 Mock。修改/停用/删除当前连接后，需重新通过测试才能查询；旧任务不会在另一条连接上继续执行。仅当已加载的 Oracle 客户端目录或驱动模式变化时需要重启两个进程。

账号/权限/模板仍保存在 SQLite；查询使用保存后的最新版本，其他用户仍需模板授权。密钥文件必须和元数据库一起安全备份。生产模式仍需 HTTPS 与目录 ACL，两个双击入口现在兼容生产配置。旧 release ZIP 未重新打包。

## 个人资料与外观设置（2026-10-15）

用户菜单提供“个人资料”和“退出登录”。个人资料在工作区标签页打开，用户名只读，可保存昵称和联系方式；修改密码需输入当前密码并确认新密码，成功后所有原登录会话失效。初始化管理员、后台新增/重置用户及个人修改密码统一使用 6–128 字符规则。

顶栏左侧齿轮打开右侧外观设置面板，可选择预设/自定义主题颜色、12/13/15/17px 字号与系统/微软雅黑/宋体/楷体；月亮/太阳按钮切换明暗模式。设置即时同步所有工作区页面，并保存在当前浏览器，刷新和重新登录后保留；恢复默认使用原蓝色 #409eff、13px、系统字体、亮色模式。字体使用本机已有字体，无远程下载。

本次无需新增数据库迁移。关闭旧启动窗口后重新双击 `02_start_system.cmd`，浏览器按 Ctrl+F5 加载新版资源；已有账号与资料保留。release 中的旧 ZIP 未重新打包。

信息查询管理平台（SQL 查询为独立业务模块）。Python **3.11 x64**、Flask、AdminLTE **3.2.0**（Bootstrap 4 / jQuery / iframe）、SQLite / SQLAlchemy / Alembic，独立持久任务 Worker。全部资源本地提供，无 React、Vue、CDN。Oracle 11g 11.2.0.4 生产代码使用 `oracledb==3.4.2` Thick 与 Instant Client 19c。

## 本机启动（PowerShell，项目根目录）

### 双击快捷启动（推荐）

1. 首次使用，双击项目根目录 **01_init_admin.cmd**。自动迁移数据库，输入管理员账号、密码并确认；密码输入时不显示字符。只有显式选择 development/mock 时才询问是否准备合成数据。已有账号不会被覆盖。
2. 双击 **02_start_system.cmd**。自动启动 Waitress Web 与独立 Worker，服务就绪后打开 `http://127.0.0.1:8080`。请保持启动窗口打开，按回车或 Ctrl+C 停止；运行中的任务会中断，重启时保留中断记录。

快捷脚本使用项目 `.venv`，路径包含空格也可运行；未安装依赖时提示先安装。重复启动会提示端口占用。启动日志在 `logs/launcher-web.log` 和 `logs/launcher-worker.log`。默认从网页配置 Oracle；医院长期运行可使用 Windows 服务部署方案。production 模式不会自动打开 HTTP 登录页面，应访问已配置的 HTTPS 入口。

需要更换本机端口或不自动打开浏览器：`.\.venv\Scripts\python.exe scripts\desktop.py start --port 8082 --no-browser`。

### 手动启动

项目已在 `.venv` 安装 Python 3.11 依赖。首次管理员需要自己设置密码，不存在内置默认密码。

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:application migrate
.\.venv\Scripts\python.exe -m flask --app wsgi:application init-admin --username admin
```

终端 A 启动 Web（默认使用网页配置的 Oracle）：

```powershell
.\.venv\Scripts\python.exe -m waitress --listen=127.0.0.1:8080 --threads=8 wsgi:application
```

终端 B 启动 Worker：

```powershell
.\.venv\Scripts\python.exe worker.py
```

默认 development 模式访问 `http://127.0.0.1:8080`，在网页配置真实 Oracle；production 模式访问 HTTPS 代理入口。需要 Mock 开发时，在初始化与两个启动窗口显式设置 APP_ENV=development、DATA_SOURCE=mock，再运行 `seed-mock admin`；管理员首次没有业务数据权限，需单独授权。

新机器开发安装：`py -3.11 -m venv .venv`，然后 `.\.venv\Scripts\python.exe -m pip install -r requirements.lock`。无可用 3.11 时可用发布包官方 3.11.9 安装程序；生产升级到院方审查的安全维护版本后重新测试并打包。

## 测试与发布

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
node --check app\static\app.js
.\.venv\Scripts\python.exe -m compileall -q app migrations scripts worker.py wsgi.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\package_offline.ps1
```

pytest 将医院验收项明确跳过为 `PENDING_HOSPITAL_VALIDATION`。真实浏览器端到端脚本（额外测试工具，不属于生产依赖）：安装 `requirements.dev.in` 后运行 `.\.venv\Scripts\python.exe scripts\browser_smoke.py`。

离线包不包含运行数据、开发密钥、患者数据或 Oracle Client。包含 WinSW 包装器、Python 安装程序、wheelhouse 和 SHA-256 清单。以完整包哈希和院方批准渠道保障传输，包内哈希用于完整性校验。详见 [部署文档](docs/DEPLOY_WINDOWS.md)、[医院验收表](docs/HOSPITAL_ACCEPTANCE.md)、[测试文档](docs/TESTING.md)、[状态记录](PROJECT_STATUS.md)。

## 使用流程

1. 在“查询模板”填写 SQL、参数 schema、排序白名单及摘要，保存即启用。
2. 创建者可直接查询自己的模板；管理员为其他角色或用户分配菜单和模板执行/查看/导出权限。
3. 查询页只显示模板声明的参数。日期范围可快捷填充并自动拆月，执行后直接显示月份结果标签。
4. 切换月份标签查看结果，导出按月分工作表。预览默认30分钟过期，导出重新查询并校验权限。


## 1.1.0 菜单与升级
- 查询管理：SQL 查询、查询模板、查询任务、导出记录、模板数据授权、查询配置。
- 权限管理：角色菜单授权（选择角色、勾选子菜单、保存）。
- 系统管理：用户、角色、菜单、部门、系统设置。
- 系统监控：运行状态、审计日志。
- 关于：平台信息、生产环境依赖、开发环境依赖。

关闭旧启动窗口后重新双击 `02_start_system.cmd`，会自动执行 0002 菜单迁移，再启动 Web/Worker。已有账号无需重复初始化。生产升级先停服务并用 SQLite Backup API 备份，再执行 `python -m flask --app wsgi:application migrate`，最后启动服务。历史部分权限保留；如某角色未显示完整功能菜单，管理员进入“角色菜单授权”明确重新勾选即可。
工作区首次登录为空；点击子菜单生成标签，重复点击保留当前表单。支持刷新当前、关闭当前/其他/全部；刷新浏览器恢复同一账号本次会话已打开且仍授权的标签。
菜单管理维护已实现页面的名称、目录、排序和启用状态；新增业务功能需先实现并注册页面，不能把任意地址配置为系统内部 iframe。已有引用的部门不能删除。

## 管理界面更新（2026-10-15）

用户、角色、部门、菜单采用整页列表与弹窗编辑，工具栏提供新增、刷新、排序和字段显示筛选。部门支持上级部门、排序、状态和备注；用户左侧部门树可筛选本部门与下级部门，编辑用户单选角色和用户部门（科室）。角色增加标识、状态和备注。菜单每行支持编辑、新增、删除，新增目录或重新添加已注册的工作页面。菜单授权为左侧紧凑树，支持目录勾选、全选、半选和展开收起。

页面统一蓝白配色、13px 正文字体与紧凑行距；Mock 提示仅在系统监控的运行状态显示。0003 迁移补充字段，不改动已有密码、查询历史与历史授权。历史多角色、多部门账号编辑时会提示，保存后采用表单中的单选配置；部门层级不自动授予下级科室查询权限。

重新双击 `02_start_system.cmd` 启动新版；启动入口自动执行迁移。如旧启动窗口仍在运行，先按回车停止，再启动并在浏览器按 Ctrl+F5 刷新。原 release 中的 ZIP 是此前版本，本次源代码更新未重新打包。

## 连接配置（2026-10-15）

新增“系统管理 → 连接配置”，支持 Oracle、MySQL、SQL Server 的 IP/端口与本地实例配置、命名空间、服务名/SID、用户名/加密密码及真实只读连接测试，沿用蓝白列表和弹窗。安装新增依赖后重启，启动脚本自动执行 0004 迁移；原有系统设置管理员首次升级获得入口。

运行状态同时显示当前查询任务数据源与已保存连接的最近测试统计。本地成功不代表目标 IP 一定可连，远程监听、网络、账号和证书需对目标地址再测。Oracle 保存测试通过后成为查询数据源；MySQL、SQL Server 仍仅用于连接诊断。填写说明、驱动安装、TLS、密码备份及测试边界见 [连接配置文档](docs/CONNECTIONS.md)。

Oracle Thick 连接可在新增/编辑弹窗填写“Oracle Client 目录”，指向服务器上包含 `oci.dll` 的本地绝对目录；留空使用 `ORACLE_CLIENT_DIR` 环境变量/部署配置，再由驱动按系统默认方式查找。网页目录随连接保存、编辑回显，清空恢复默认，同时供连接测试和查询服务使用，无需数据库迁移。更新代码后重启 Web/Worker 并按 Ctrl+F5 刷新页面；旧 release ZIP 未重新打包。
