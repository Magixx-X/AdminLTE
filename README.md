# 信息查询管理 1.1.0

## 个人资料与外观设置（2026-10-15）

用户菜单提供“个人资料”和“退出登录”。个人资料在工作区标签页打开，用户名只读，可保存昵称和联系方式；修改密码需输入当前密码并确认新密码，成功后所有原登录会话失效。初始化管理员、后台新增/重置用户及个人修改密码统一使用 6–128 字符规则。

顶栏左侧齿轮打开右侧外观设置面板，可选择预设/自定义主题颜色、12/13/15/17px 字号与系统/微软雅黑/宋体/楷体；月亮/太阳按钮切换明暗模式。设置即时同步所有工作区页面，并保存在当前浏览器，刷新和重新登录后保留；恢复默认使用原蓝色 #409eff、13px、系统字体、亮色模式。字体使用本机已有字体，无远程下载。

本次无需新增数据库迁移。关闭旧启动窗口后重新双击 `02_start_system.cmd`，浏览器按 Ctrl+F5 加载新版资源；已有账号与资料保留。release 中的旧 ZIP 未重新打包。

信息查询管理平台（SQL 查询为独立业务模块）。Python **3.11 x64**、Flask、AdminLTE **3.2.0**（Bootstrap 4 / jQuery / iframe）、SQLite / SQLAlchemy / Alembic，独立持久任务 Worker。全部资源本地提供，无 React、Vue、CDN。Oracle 11g 11.2.0.4 生产代码使用 `oracledb==3.4.2` Thick 与 Instant Client 19c。

## 本机启动（PowerShell，项目根目录）

### 双击快捷启动（推荐）

1. 首次使用，双击项目根目录 **01_init_admin.cmd**。自动迁移数据库，输入管理员账号、密码并确认；密码输入时不显示字符。可以选择准备 Mock 合成月报与查询权限。已有账号不会被覆盖。
2. 双击 **02_start_system.cmd**。自动启动 Waitress Web 与独立 Worker，服务就绪后打开 `http://127.0.0.1:8080`。请保持启动窗口打开，按回车或 Ctrl+C 停止；运行中的任务会中断，重启时保留中断记录。

快捷脚本使用项目 `.venv`，路径包含空格也可运行；未安装依赖时提示先安装。重复启动会提示端口占用。启动日志在 `logs/launcher-web.log` 和 `logs/launcher-worker.log`。这两个入口用于本机 Mock 开发，医院生产使用 Windows 服务部署方案。

需要更换本机端口或不自动打开浏览器：`.\.venv\Scripts\python.exe scripts\desktop.py start --port 8082 --no-browser`。

### 手动启动

项目已在 `.venv` 安装 Python 3.11 依赖。首次管理员需要自己设置密码，不存在内置默认密码。

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:application migrate
.\.venv\Scripts\python.exe -m flask --app wsgi:application init-admin --username admin
.\.venv\Scripts\python.exe -m flask --app wsgi:application seed-mock admin
```

终端 A 启动 Web（Mock 开发）：

```powershell
$env:APP_ENV = 'development'
$env:DATA_SOURCE = 'mock'
.\.venv\Scripts\python.exe -m flask --app wsgi:application run --host 127.0.0.1 --port 8080
```

终端 B 启动 Worker：

```powershell
$env:APP_ENV = 'development'
$env:DATA_SOURCE = 'mock'
.\.venv\Scripts\python.exe worker.py
```

访问 `http://127.0.0.1:8080`。可以查询合成月报、筛选设备/关键词、模拟失败/慢查询/超时、取消、分页排序、按月导出。所有数据标明合成。管理员首次没有患者数据权限；`seed-mock` 仅在开发模式显式为该账号授予合成科室和模板权限。

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

1. 编辑员创建草稿，配置 SQL、参数 schema、排序白名单、范围策略，提交审核。
2. 管理员审核绑定、只读视图/数据库对象/函数，并发布。Mock 发布不会变为真实医院验证通过。
3. 管理员配置角色的全局权限，再配置模板对象的执行/查看/导出授权和用户科室范围。
4. 查询用户选择模板、起止月份和参数，按批次异步执行；每个月份有自己的任务。
5. 预览结果是配额内的 Worker 内存数据，默认 30 分钟到期。Worker 重启后预览需再执行。导出重新读取业务数据库，按月分 Sheet、重新鉴权，有效期默认一天。

代码不会尝试把 Oracle SQL 在 SQLite 中执行。SQL 文本只对有编辑权限的所有者/审核管理员开放。生产不能回退 Mock。没有真实医院环境，本交付不声称 Oracle 连接、业务结果、取消性能或旧 Chrome 兼容已经通过。


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

连接测试无需切换 Mock，运行状态同时显示当前查询任务数据源与已保存连接的最近测试统计。本地成功不代表目标 IP 一定可连，远程监听、网络、账号和证书需对目标地址再测。连接配置不会自动切换 SQL 查询任务的数据源；现有查询仍使用部署配置的 Mock 或 Oracle。填写说明、驱动安装、TLS、密码备份及测试边界见 [连接配置文档](docs/CONNECTIONS.md)。
