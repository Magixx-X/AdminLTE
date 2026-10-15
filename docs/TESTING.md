# 测试方法与实际边界

网页优先配置数据库（2026-10-15）：完整 pytest 111 passed、6 skipped；追加查询链路断言后，数据库启动/激活专项 5 passed。覆盖无 Oracle 参数启动、自动密钥持久化/旧密钥沿用、网页测试激活、已有 Worker 无重启读取加密配置并执行查询、连接修改使测试失效、来源变更阻止旧任务跨库执行。Oracle 成功执行使用驱动替身，不代表目标 Oracle 已验收。

Edge 首次启动专项通过，`.runtime/oracle-client-ui/20261015-174809/` 验证 Web/Worker 在无 Oracle 参数、无 APP_SECRET 时启动，以及目录输入/保存/回显/清空。完整浏览器回归报告 `.runtime/browser-smoke/20261015-175611/result.json` 通过，外部请求和 pageerror 为零。回归脚本已等待模板初始列表加载，并移除“保存并测试”后重复发起的 Oracle 探测，避免占用下一项连接测试的并发槽。管理 JS 语法检查通过。

Oracle Client 网页目录配置专项（2026-10-15）：连接测试 31 passed；完整 pytest 106 passed、6 skipped（医院环境验收项），management.js 语法检查及 git diff --check 通过。新增覆盖目录保存/回显/清空、当前连接优先于部署配置、空值回退与系统查找、环境变量优先级、Thin 忽略路径、非法路径拒绝、缺少 oci.dll 与加载失败的脱敏提示。驱动成功路径仍使用替身，不代表真实 Oracle 成功验收。

Edge 专项浏览器验证通过，截图在 `.runtime/oracle-client-ui/20261015-170220/`，覆盖 Thick 输入、Thin/MySQL/SQL Server 显隐、缺少 DLL 提示、保存/编辑/清空和移动端布局。完整浏览器脚本首次在 SQL 模板保存提示断言处停止，重跑通过，报告 `.runtime/browser-smoke/20261015-170310/result.json`；包含新增 Oracle 目录流程及原查询/导出/管理/Worker 恢复检查，外部请求和 pageerror 均为零。

个人资料与外观专项（2026-10-15）：完整 pytest **94 passed, 6 skipped**；新增 tests/test_profile.py 覆盖普通账号资料访问、越权字段拒绝、CSRF、当前密码校验与限流、6/128 字符边界、所有原会话撤销，以及管理端/CLI 统一规则。更新后专项 5 passed。医院环境跳过项维持原状态。

Edge 完整回归通过，报告 `.runtime/browser-smoke/20261015-141952/result.json`：资料保存/只读用户名/重复标签/刷新恢复、6 位密码修改后重新登录、右侧面板不新增标签、颜色/字号/字体同步、设置持久化与恢复默认、移动端与 Esc 焦点恢复，以及所有工作页和用户弹窗的暗色底色。原查询/480 行导出/管理/真实 Worker 中断恢复回归通过，外网资源请求与 pageerror 均为零。截图等待加载完成并禁用捕获时过渡，避免浏览器全页截图临时改变视口产生布局动画。最终大字体暗色截图见 docs/workspace-appearance-dark.png、docs/appearance-settings-dark.png。

主测试：`.\.venv\Scripts\python.exe -m pytest -q --tb=short`（Python 3.11）。覆盖 API 与 RBAC、CSRF、会话、模板生命周期/不可变 DB trigger、参数、月份、持久队列、取消/失败/超时/恢复、两查询/一导出并发限制、内存 IPC、预览配额/TTL、Excel 拆分/日期/中文/注入、Backup API。

真实浏览器脚本：`.\.venv\Scripts\python.exe scripts\browser_smoke.py`。使用 Playwright 与主机 Edge/Chrome，在私有测试目录创建合成账号，启动独立 Waitress 与 Worker，通过浏览器登录、iframe tab、查询分页与导出下载，并检查资源请求只来自 localhost。随机测试密码不输出、不进入发布包。截图与日志放 .runtime/browser-smoke。额外工具安装 `requirements.dev.in`；离线生产运行不需要浏览器自动化依赖。

编译/JS：`node --check app\static\app.js`；`python -m compileall -q app migrations scripts worker.py wsgi.py`。PowerShell 使用 Parser.ParseFile 解析全部 scripts/*.ps1，发布后运行 verify_package.ps1，再在发布目录新建 venv 并 --no-index 安装、迁移、测试。

依赖审查：`python -m pip_audit -r requirements.lock --no-deps --disable-pip -f json -o docs/dependency-audit.json`（需联网查询漏洞库）。必须按报告实际记录，不把不可用的漏洞数据库或未扫描的 JS 资源说成通过。

医院 tests/hospital_pending 只给待验收项占位，故意 pytest.skip 并标记 PENDING_HOSPITAL_VALIDATION。实际统计以 PROJECT_STATUS.md 最新运行记录为准。目标 Win7/旧 Chrome、真实 Oracle SQL、服务/IIS/ACL 和医院负载只能在院方环境验收。

## 连接配置专项（2026-10-15）

新增 tests/test_connections.py：加密密码/留空保留/不回显、重复名称、配置版本冲突、修改后清除测试结果、测试中修改不写回、独立菜单权限及幂等升级、参数边界、驱动只读语句和参数传递、ODBC 密码转义、Windows 本地身份验证、异常脱敏和子进程总超时。驱动成功路径使用替身验证调用契约，不当作真实数据库验收。

完整回归 89 passed, 6 skipped（18.28s）；JS 检查、Python 编译与 pip check 通过。Edge 实测三种表单保存、密码留空保留、类型筛选、真实驱动失败反馈（关闭的本机端口/缺少 ODBC 17/18）、监控统计和 Mock 查询源保持不变；没有已知可登录数据库，三类成功连接仍需部署环境验收。
