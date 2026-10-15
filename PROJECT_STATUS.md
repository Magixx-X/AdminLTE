# HospitalQuerySystem 开发状态

## 模板与查询简化（2026-10-15，当前版本）

- 取消提交审核、发布和验收证据门槛；保存即启用最新版本，创建者自动获得模板访问权。历史版本、停用、复制、软删除与其他用户模板授权保留。
- 移除数据范围策略及按科室重复执行/过滤，用户部门仅作组织信息；历史数据库列保留兼容，不参与查询或超时设置。
- 查询表单按 SQL 参数 schema 类型生成，移除独立开始/结束月份。支持本月、上月、最近3/6/12月快捷填充；日期开始包含、结束不含，跨月按自然月拆分实际参数。
- 执行完成自动显示月份标签及结果，导出各月独立工作表；已打开的查询页在模板保存后自动更新可选模板。
- 新增迁移 0005，保留账号、版本及任务记录，启用原草稿/审核中模板，停用模板保持停用。旧科室绑定 SQL 及未声明类型的日期绑定需编辑后保存；使用现有部署升级前停服备份，再 migrate 并重启 Web/Worker。
- 完整 pytest 118 passed、6 skipped（24.73s）；JS 语法、Python 编译及差异检查通过。Edge 全流程通过，0 pageerror / 0 外网请求，证据 `.runtime/browser-smoke/20261015-193357`，包含五种快捷日期、保存即查询、结果月份切换和480行两工作表导出。
- 测试使用隔离合成数据和 Oracle 驱动替身，真实医院验收项仍待目标环境验证。源码已更新，既有 release ZIP 未重新打包。

以下为历史实现及测试记录，功能现状以本节为准。

## 个人资料、外观与明暗模式（2026-10-15）

- 用户下拉仅保留个人资料、退出登录；资料为可恢复且不重复的 iframe 标签，复用既有昵称/联系方式字段，用户名只读。自助接口只修改本人资料，权限字段拒绝。
- 所有系统密码入口统一 6–128 字符。自助改密校验当前密码与确认值、限流、审计、撤销全部旧会话；保留 Argon2id 和 CSRF。
- 左侧顶栏新增同系列齿轮和月亮/太阳图标；右侧外观抽屉，预设/自定义主题色、字号、字体、恢复默认。当前浏览器 localStorage 持久化，所有 iframe 即时同步并在首屏应用；默认原蓝色/13px/系统字体/亮色。
- 共享 CSS 变量覆盖亮暗背景、导航、标签、树、表格、表单、下拉、分页、提示、状态、弹窗与 CodeMirror。未添加依赖或数据库迁移。修复 Bootstrap iframe 标签 fade 回调在快速切换时重新激活旧页的问题。
- pytest 完整回归 94 passed, 6 skipped（19.38s）；补充 CLI 六位密码初始化断言后专项 5 passed。JS 语法与 Python 编译通过。Edge 全流程通过，0 pageerror / 0 外网请求，证据 .runtime/browser-smoke/20261015-141952；最终大字体暗色布局与抽屉另以隔离测试库检查，截图已存 docs。
- 使用源码启动入口重启后 Ctrl+F5 生效。release ZIP 未重新打包；真实医院环境验收范围保持原状态。

更新时间：2026-10-14（Asia/Shanghai）；交付版本：1.0.0

## 初始检查
- 已完整阅读 PROJECT_REQUIREMENTS.md（0–15 节），项目目录只有该需求文件，无现有代码或 Git 仓库。
- 已阅读指定 ponytail、前端开发、后端架构技能。采用 Flask 单体、SQLite 持久任务与独立 Worker，传统 AdminLTE 页面；不引入 React/Vue。
- 当前主机仅发现 Python 3.12，将在项目私有运行目录准备 Python 3.11 x64，严格用其安装、运行和测试。
- Oracle 网络、数据库、客户端均不可用；全部医院测试保持 PENDING_HOSPITAL_VALIDATION。

## 实现进度
- Python 3.11.9 x64 已安装到 .runtime/python311，.venv 为实际 3.11 环境；生产依赖 requirements.lock 已锁定。
- AdminLTE v3.2.0 原版本地资源、Bootstrap 4/jQuery、DataTables、CodeMirror 5；全部页面通过 Flask 权限校验。
- 完成 app 工厂、API / services / repositories / models / providers / tasks 分层；SQLite WAL/busy_timeout/Alembic；不可变模板版本与只追加审计触发器。
- 完成服务端会话、Argon2id、CSRF、登录限流、用户/角色/模板对象授权/科室范围；管理员没有隐含患者权限。
- 完成草稿/审核/发布/停用/软删除/复制/版本记录、动态参数、跨月查询、持久队列、独立 Worker、内存预览 IPC、分页排序、取消/中断恢复与再执行。
- 完成多月流式 XLSX、Sheet 拆分、公式防护、日期/中文、配额/有效期/受控下载/清理。
- OracleProvider 生产代码已实现 Thick、只读事务、服务器绑定、合计最多 4 连接（Web 1 + Worker 3）、watchdog 取消与超时；真实 Oracle 全部待医院验收。
- 完成 scripts 的安装/启动/打包/校验/备份/恢复/双服务注册卸载，以及 README、架构/API/部署/测试/验收文档。
- 已完成真实 Edge 浏览器端到端及独立 Worker kill/restart 持久任务恢复验证。
- Python 依赖漏洞审查首轮发现 3 个包共 9 个记录，已将 Flask 升级 3.1.3、cryptography 升级 50.0.0、pytest 升级 9.0.3；重新锁定后 pip-audit 报告 No known vulnerabilities found，pip check 通过。
- AdminLTE 仍固定 3.2.0；其使用的 jQuery 更新 3.7.1、Bootstrap 4 更新 4.6.2、DataTables 更新 1.13.11、CodeMirror 5 更新 5.65.20，资源来源/哈希/许可证已记录在 docs/frontend-assets.json、docs/licenses。更新后真实浏览器复测通过。
- 离线首包构建、484 文件 SHA 校验、全新 Python 3.11 venv 的 27 wheels --no-index 安装与 SQLite 迁移已通过；发布目录 pytest 53 项通过。发现新安装缺少 .runtime 测试目录的问题后已修复 conftest 并复测通过。
- 前端完整上游 npm 依赖树审查发现 5 moderate（Summernote/Moment/Tempusdominus 等传递依赖）；这些未使用插件不部署。实际部署资源已精简到约 5.2 MB，报告与边界见 docs/FRONTEND_SECURITY.md。旧栈不宣称绝对安全。
- 全新离线环境最终回归：**54 passed, 6 skipped**（7.32 秒）；`pip check` 通过，SHA-256 校验与主动篡改检测通过。安装只使用包内 wheels、没有网络安装请求。
- 完成 Mock 开发交付、Oracle 生产实现与离线部署方案；医院环境范围维持待验收。正式发布位置见下方。

## 测试
- 最新执行 `.venv\\Scripts\\python.exe -m pytest -q --tb=short --junitxml=docs/local-tests.xml`：**58 passed, 6 skipped**，6 个 skip 均明确 PENDING_HOSPITAL_VALIDATION，耗时 14.19 秒（含快捷入口补充测试）。
- Oracle driver-double 合约测试检查 Thick 初始化、只读事务、绑定与 Web 1 / Worker 3 连接预算；该测试不是 Oracle 集成验收。
- 实际 Edge 浏览器 + 独立 Waitress/Worker 流程通过；480 行、两月份 Sheet 导出验证通过，0 外网资源请求、0 pageerror。真实 Worker 被终止重启后：2 个 RUNNING -> INTERRUPTED，1 个 PENDING -> SUCCEEDED。
- 最终浏览器报告：.runtime/browser-smoke/20261014-175053/result.json（使用随机测试账号，不包含真实数据）。iframe 重复防护、刷新、关闭其他、关闭全部均通过。
- 首轮默认 pytest temp 目录因沙箱访问受限，已改为项目 .runtime/pytest；两处失败（缺少模板 ID 返回码、Windows 测试下载句柄未关闭）已修复并复测。
- `node --check app/static/app.js` 通过；Python compileall 通过；全部 PowerShell 脚本 Parser.ParseFile 语法检查通过。
- WinSW 服务 XML 语法解析通过；未在开发电脑注册系统服务。
- 机器可读结果：docs/TEST_RESULTS.json、docs/local-tests.xml、docs/offline-tests.xml、docs/browser-tests.json、docs/dependency-audit.json、docs/frontend-audit.json。

## 启动
```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:application migrate
.\.venv\Scripts\python.exe -m flask --app wsgi:application init-admin --username admin
.\.venv\Scripts\python.exe -m flask --app wsgi:application seed-mock admin
# 终端 A
.\.venv\Scripts\python.exe -m flask --app wsgi:application run --host 127.0.0.1 --port 8080
# 终端 B
.\.venv\Scripts\python.exe worker.py
```
浏览器访问 http://127.0.0.1:8080；安全初始化时自行设置密码，无固定默认密码。

## 文件变更
- 根目录：README.md、requirements.in / requirements.lock / requirements.dev.in、config.example.json、.env.example、.gitignore、wsgi.py、worker.py、alembic.ini、pytest.ini、VERSION、PROJECT_STATUS.md。
- app：应用工厂、配置与 CLI；api、services（参数/模板/Excel/备份）、repositories、models、security、providers（base/mock/oracle）、tasks（Worker/IPC 缓存），全部从零新增。
- app/templates：登录、iframe 主框架、通用业务页、错误页；app/static：业务 CSS/ES5 风格 JS 与精选固定版本本地 vendor 资源。
- migrations：初始迁移、SQLite 审计只追加与版本不可变触发器。
- tests：认证/权限/API/生命周期、参数边界、Mock Worker/Excel、附加安全边界/恢复、Oracle driver-double、医院待验收占位。
- scripts：离线打包/校验/安装、Web/Worker 启动、管理员初始化、健康检查、Backup API 备份/恢复、WinSW 双服务配置/注册/卸载、浏览器端到端、vendor 版本下载记录。
- docs：架构、API、Windows 部署、测试、医院验收、前端安全、组件哈希/许可证、依赖初始/最终审计。
- 原始 PROJECT_REQUIREMENTS.md 保留，无现有代码被替换，未创建/提交 Git 记录。

## 已知限制与医院待验收
- **PENDING_HOSPITAL_VALIDATION**：真实 Oracle 11.2.0.4 + Instant Client 19c + oracledb 3.4.2 Thick；NLS/中文/NUMBER/LOB、业务 SQL、LISTAGG/DBMS_LOB/分析函数/院内函数；真正超时取消与连接恢复；2 查询 + 10 用户 + 大导出负载。
- **PENDING_HOSPITAL_VALIDATION**：最低 Win7/Chrome 的 iframe、DataTables、CodeMirror、月份输入和下载；低权限 Windows 双服务、IIS/TLS、ACL、院内防火墙、备份恢复和数据脱敏审批。没有在开发机注册系统服务或假称医院验证通过。
- 数据隔离策略为审核 SQL 中的科室绑定 + DBA 只读授权视图，跨科室汇总/去重语义需要单独审核；审核接口的人工确认不是自动 SQL 沙箱。
- 预览为有界短期内存，行数是预览计数（达到上限显示 truncated）；TTL/Worker 重启/容量淘汰后需要重新执行。导出重新查询，可能与旧预览时间点不同。
- 一台部署仅运行一个 Web 进程和一个 Worker，避免超过总 4 Oracle 连接预算。文本/LOB 超配额拒绝任务，禁止静默截断。
- 生产不得回退 Mock；Mock 模板仍标记 PENDING_HOSPITAL_VALIDATION，生产需要创建新版本并经医院证据审核发布。
- Python 3.11.9 是本机已验证 Windows 安装版本；医院需审查运行时安全维护策略并验证升级。Oracle Client/VC++ 运行库由医院按许可另行提供。
- Bootstrap 4 / AdminLTE 3.2 为固定旧栈，已保存依赖审查，未做医院渗透测试或声称满足全部 WCAG/Lighthouse 指标。

## Windows 离线交付
- 正式 ZIP：`release/HospitalQuerySystem-1.0.0-windows-x64.zip`。
- ZIP 校验：同目录 `HospitalQuerySystem-1.0.0-windows-x64.zip.sha256`；包内 SHA256.json 与 BUILD.json。以院方批准渠道获取可信外部哈希，包内清单检测损坏/篡改。
- 包含：全量应用、精选本地前端资源、迁移与测试、部署文档、27 个固定 Python 3.11 win_amd64 wheels、官方 Python 3.11.9 安装程序、WinSW 2.12.0 x64 及许可证、双服务配置。
- 不包含：.venv、.runtime、运行数据库、认证密钥、真实/合成导出文件、config.local.json、医院凭据、Oracle Client。
- 已实际执行：package_offline.ps1；verify_package.ps1；install_offline.ps1（全新 venv / --no-index）；SQLite 迁移；离线 pytest；文件篡改检测并恢复后 hash 复验。Windows 服务注册/IIS/真实 Oracle 在医院验收。
- 准确部署步骤见 docs/DEPLOY_WINDOWS.md；安全初始化管理员无固定默认密码。完整文件清单见 docs/FILE_MANIFEST.json。

### 最终 ZIP 独立验证（构建后记录）
- 从正式 ZIP 解压到全新 .runtime/offline-final，运行其 install_offline.ps1：全新 Python 3.11 venv、27 wheels 离线安装、迁移均通过。
- 在解压后的环境执行 `python -m pytest -q --tb=short`：**54 passed, 6 skipped in 7.43s**；pip check 通过；139 个包文件 hash 复验通过。
- ZIP testzip 完整性检查与运行目录/凭据排除检查通过。
- ZIP 字节数：47,195,156（约 45 MiB）。
- SHA-256：`438927b0ceeb2aaa547c8f61ea36e0b73a26413aab2d86c6585b3257d124d10c`。
- ZIP 内状态是构建前测试记录；本根目录状态补充构建后的最终 ZIP 验证与外部哈希，避免把 ZIP 的自身哈希写入 ZIP 造成循环。
- 本机开发与发布交付完成；正式医院上线仍须 HOSPITAL_ACCEPTANCE.md 全部院方验收。无未解决的本地自动化测试失败。

## 快捷入口补充（2026-10-14）
- 新增根目录 `01_init_admin.cmd`：可双击，自动迁移，交互输入管理员账号/密码，可选择准备 Mock 合成查询；不会覆盖已有账号密码，无固定默认密码。
- 新增根目录 `02_start_system.cmd`：可双击，检查端口/账号，启动独立 Worker 与 Waitress，等待两者就绪后自动打开浏览器；启动窗口回车/Ctrl+C 停止本次启动的进程，查询中任务会中断。
- 新增 scripts/desktop.py：复用已有应用 CLI，日志写入 logs/launcher-web.log / launcher-worker.log；支持 --port / --no-browser；不覆盖生产模式，只服务本机 Mock 开发。
- 修复 app/cli.py 的 seed-mock：模板已存在时也向指定账号授予合成模板权限，保持重复初始化幂等。没有授予任何真实患者范围。
- 更新 README.md、离线打包脚本（包含两个 .cmd）、新增 tests/test_desktop.py。
- 实测覆盖：管理员创建与合成授权、重复创建不覆盖、端口冲突、真实 Web + Worker 启动/查询/内存分页/停止与释放端口、生产模式拒绝快捷入口。Windows venv 重定向进程 PID 与实际 Worker PID 不同的问题已改为校验新的 Worker 心跳时间并复测。
- 完整回归：58 passed, 6 skipped in 14.19s；Python 编译与打包 PowerShell 语法通过。医院验收状态保持 PENDING_HOSPITAL_VALIDATION。
- 补充离线包：release/HospitalQuerySystem-1.0.0-windows-x64-with-launchers.zip（原包保留历史；新增两个入口的包以此为准）。
- 补充包构建成功，143 个文件 SHA-256 校验通过，ZIP 完整性及两个 .cmd 入口检查通过；该补充包未另建全新 venv 重跑离线安装，固定依赖与安装机制沿用前次已验证版本。


## 信息查询管理 1.1.0 架构调整（2026-10-14）
- 按本次需求覆盖旧文档中的扁平菜单和细粒度角色界面；保持 Python 3.11 / Flask / AdminLTE 3.2 / SQLite / 独立 Worker / Oracle Thick。
- 新增 app/navigation.py 统一菜单目录、app/api/platform.py 平台管理接口、menus 元数据表和 0002 增量迁移。已有账号、SQL 版本、查询历史和数据范围保留。
- 主菜单：查询管理、权限管理、系统管理、系统监控、关于；子菜单分别承载已有查询功能和平台管理功能。不生成没有实际页面的任意 URL 菜单。
- 角色界面只管理名称，角色菜单授权用中文复选框；内部操作权限用于兼容历史授权和 Worker 鉴权。模板数据授权简化为访问开关，保留独立数据范围及只读 SQL 审核边界。
- 平台设置新增登录有效期、失败次数、限制窗口及磁盘预警；查询配额移到查询配置。平台监控展示元数据库、用户数、有效会话、Worker、环境、磁盘。审计沿用全平台追加日志并记录菜单/角色/部门操作。
- 工作区不自动打开首页；点击子菜单生成 iframe 标签，同一子菜单复用标签并保留表单；按账号在浏览器会话中保存打开标签，刷新时仅恢复仍获授权的菜单。
- 部门管理复用现有数据范围表（避免维护两份部门），支持新增、改名和删除未引用部门。关于页列出平台版本、生产与开发依赖的锁定/实际版本。
- 已修改 app 模型、安全、API、CLI、Jinja/JS/CSS、Worker；启动入口继续可用，启动时自动迁移。发布脚本版本改从 VERSION 读取。
- 第一轮旧回归：58 passed, 6 skipped。新增平台专项测试：5 passed。浏览器回归进行中；真实 Oracle/医院 SQL/Windows 服务验收仍待院方执行。

- 最终本地回归：**65 passed, 6 skipped in 16.86s**；包含旧数据库 0001 → 0002 迁移保留密码/任务、重复迁移不恢复已撤销授权、菜单停用后 Worker 拒绝执行、平台设置实际作用于登录。
- Edge 实际浏览器：通过。验证全部平台子页面、角色创建与菜单勾选、部门新增、首次空工作区、重复点击保留表单、全部已打开标签恢复/当前选中恢复、刷新/关闭其他/全部、查询分页、480 行两 Sheet 导出、模板审核生命周期、真实 Worker 中断与恢复。无脚本错误、无外网请求。
- 标签恢复曾出现 Bootstrap 并发过渡导致多个活动页，已改为监听 shown.bs.tab 逐个恢复并加入全部标签数量与最终选中页断言，回归通过。
- 浏览器证据：.runtime/browser-smoke/20261014-203401；workspace.png 已人工查看，完整工作区与子菜单正常。
- 移除旧 permissions 写入接口和系统设置中的 SQL 配额分支；旧调用方须按 docs/API.md 使用角色 /menus 与 /query-settings。Windows 服务显示名改为 Information Query，保留既有服务 ID 以便升级，不在本机注册服务。
- 新包已完成：release/InformationQuerySystem-1.1.0-windows-x64.zip；旧 1.0.0 包保留为历史。

- 1.1.0 全新解压目录 .runtime/offline-1.1.0 实际 --no-index 安装 27 个 wheels 成功，迁移完成；离线环境完整回归 **65 passed, 6 skipped in 16.06s**；pip check 通过。Python 编译、PowerShell 语法解析、ZIP 完整性与排除运行数据检查通过。
- 发布目录同步最终测试文档后重新生成包内 SHA-256 和 ZIP，业务代码/依赖与实测解压版本一致；截图为 docs/workspace-1.1.0.png。
- 使用方法：关闭旧启动窗口后双击 02_start_system.cmd 自动执行增量迁移并启动；既有管理员账号保留。真实 Oracle/医院 SQL、Win7/旧浏览器、院内服务/IIS/权限/负载测试未执行，仍为待验收。
- 最终包：149 个文件校验；47,033,861 字节；SHA-256 `0818dcc21cd2c84e8f20ea1d93e7bdf6c5de4e5081b9cabf26efacf99e4836a9`。此哈希为包外构建后记录。

## 管理页面与蓝白主题更新（2026-10-15）
- 新增管理页共用模板与本地 management.js，复用 Bootstrap 弹窗和 jQuery；未添加生产依赖。用户、角色、部门、菜单完整列表与搜索/重置/排序/列筛选/刷新；用户部门树；部门层级；菜单目录新增、页面删除与恢复；角色字段和引用删除校验。
- 新增 0003 字段迁移，使用 ALTER ADD COLUMN 避免重建角色表导致既有外键引用失败。本地 metadata.db 已用 SQLite Backup API 备份并迁移；历史密码、角色/部门关联与任务不裁剪。
- 角色、部门提交最多一项；停用角色与科室立即影响查询鉴权；防止自停用和部门循环；删除菜单不在下次迁移时复活。Mock 顶栏、页面黄色提示和登录页模式提示移除，仅在运行状态显示。
- pytest：70 passed, 6 skipped（18.70s）；新测覆盖层级循环/引用、单选更新、角色停用、菜单恢复、防误删、真正旧字段布局升级保留关联。医院验收项未执行。
- Edge 浏览器最终回归通过，无页面脚本错误、无外网请求；覆盖部门新增子节点/折叠、用户创建编辑/单选/部门树筛选/搜索/排序/列筛选、角色增改删、菜单删除恢复与编辑，以及原查询、导出、iframe 状态和 Worker 中断恢复。
- 最终截图人工检查：.runtime/browser-smoke/20261015-002824（users/departments/roles/menus/authorization.png）；发布 ZIP 沿用旧版本，未重新打包。

## 连接配置子菜单（2026-10-15）
- 系统管理新增连接配置，沿用管理列表/弹窗/搜索/类型筛选/排序/字段显示。Oracle 服务名/SID、Thin/Thick；MySQL 数据库/TLS；SQL Server 数据库/Schema、IP端口、本地命名实例/LocalDB、Windows 身份验证。
- 0004 新增 DatabaseConnection 表；密码 Fernet 加密，不回显、不放命令行或审计；编辑留空保留。独立 connection:manage 授权，首次给已有系统设置角色增加入口，以后不恢复主动撤销。
- 固定只读 SELECT 1 实际探测，独立子进程隔离 Oracle 模式和驱动卡死；10 秒上限，每 Web 进程同时一项；测试中配置修改不覆盖新版本状态。运行状态增加连接测试汇总，无需为连接测试切换 Mock；未将连接配置接入查询任务 provider。
- 依赖新增 PyMySQL 1.2.3、pyodbc 5.3.0，已装入项目 venv，固定 wheels 已加入 .runtime/wheelhouse。当前机器没有可验收数据库实例；系统仅有旧 SQL Server ODBC 驱动，没有 ODBC Driver 17/18。原生驱动和真实数据库成功仍需部署时验证。
- 本地 metadata.db 已先以 SQLite Backup API 备份后迁移，原有数据保留；未重新构建 release ZIP。已更新 README、API、架构、部署、测试及 docs/CONNECTIONS.md。
- pytest 89 passed, 6 skipped（18.28s）；连接专项最终复测 19 passed；JS 检查、Python 编译、pip check 通过。Edge 首轮通过，三类实际失败反馈、凭据保留、无切换 Mock 与原查询/导出/Worker 回归均通过，无脚本错误/外网请求。

- 最终 Edge 复测通过，证据 .runtime/browser-smoke/20261015-110218；connections.png 与 connection-form.png 已人工检查，列表、按钮与两列表单正常；结果报告 page_errors/external_requests 均为空。
