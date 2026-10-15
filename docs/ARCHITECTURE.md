# 架构与安全边界

传统 Jinja 页面 + ES5 风格 jQuery，复用原版 AdminLTE 3.2 iframe 插件、DataTables 和 CodeMirror 5。Web 使用应用工厂；`api` 处理契约，`services` 校验参数/版本/导出，`repositories` 管理短事务，`models` 保存元数据，`providers` 隔离合成与 Oracle，`tasks` 管理独立 Worker。

SQLite WAL、foreign_keys、busy_timeout=10000；任务和导出先原子入队，`BEGIN IMMEDIATE` 序列化容量检查与 claim。一个 Worker supervisor 通过 OS 文件锁防止重复启动，最多两个查询线程与一个导出线程；线程只负责独立 Worker 中已持久化的任务，Web 不执行长查询。异常退出后 RUNNING 标记 INTERRUPTED，PENDING 保持可恢复。手动再执行创建新任务、保留历史与审计。Worker 每五秒维护心跳/导出清理，每天用 SQLite Backup API 一致性备份。

查询结果默认不落盘：独立 Worker 有界内存缓存（总 64 MiB，每任务最大 32 MiB，预览 10000 行，30 分钟）。Web 完成权限检查后，通过 127.0.0.1 IPC 请求分页，HMAC 校验与 10 秒时效，接口不允许提交 SQL，只能读缓存。Worker 重启/TTL/容量淘汰后返回 RESULT_EXPIRED。结果计数为实际预览行数；truncated 表示不能视为全量计数。排序仅对有界预览操作；正式 SQL 应有稳定 ORDER BY。空集没有列元信息时前端显示空状态。

Oracle Web 自检池最大 1，Worker 查询/导出池最大 3，两个进程合计最多 4；仅支持一个 Web 进程 + 一个 Worker，不要多进程水平扩展。服务启动只初始化本地平台；网页保存测试通过的 Oracle ID 存于 system_settings.query_connection_id，查询/健康检查时延迟初始化客户端与连接池。连接修改使测试失效，任务记录来源 ID/版本，防止切换后跨库执行；连接池更新等待旧请求释放，客户端模式/目录改变需重启。每次执行 SET TRANSACTION READ ONLY，参数强类型绑定，科室从服务器授权表读取，每个科室单独绑定执行。多选扩展为服务器生成的具名占位符，用户值始终是 bind。跨科室去重/汇总语义必须由 DBA 审核专门视图。Oracle watchdog 调用 connection.cancel()；call_timeout 设置网络调用上限；取消/超时效果必须医院实测。

SQL 不是通过正则实现的沙箱。只读账号、DBA 最小授权安全视图、模板发布审核、绑定、配额构成边界。任何可能有副作用的院内函数、包或授权对象都必须 DBA 审核。不能安全实施范围的模板不能发布；生产需医院验收证据。Mock 发布保留 PENDING_HOSPITAL_VALIDATION，迁入生产后不能直接执行，必须复制为新版本重新审核。

登录使用 Argon2id。浏览器保存随机认证 token，数据库只保存其 SHA-256；权限每请求从数据库读取，禁用立即生效，重置密码 auth_epoch 使旧会话失效。会话绝对有效期 30 分钟，注销删除服务端记录。所有修改 API 包括登录要求 CSRF（登录前 /api/auth/csrf 或页面 meta）；HttpOnly/SameSite、生产 Secure、CSP/SAMEORIGIN/no-store。登录失败计数持久化。模板 SQL、会话 token、数据库密码不会写入审计；任务参数值使用由 APP_SECRET 派生的 Fernet 加密，公开摘要只包含参数名与月份。

全局角色权限 + 模板对象授权 + 任务归属 + 科室授权同时校验。SYSTEM_ADMIN 没有隐含数据查询权限。范围缩减后旧任务拒绝读取/导出；账号禁用/权限撤销在 Worker 执行、完成和下载时重新检查。API 不提供跨用户结果。SQLite trigger 保证版本内容不可 UPDATE/DELETE、审核记录只能首次设置、审计仅追加；操作系统管理员仍能修改数据库文件，需院方 ACL 与备份保管。

openpyxl write_only 流式导出，每月分 Sheet，默认 Excel 最大数据行数 1048575（另留表头），超行拆分。文本前缀公式防护，非法字符清除，日期格式保留。protected exports/temp 保存短期 XML，finally 清理；失败/中断清理 partial 文件。医院需批准导出患者数据落盘策略与磁盘加密，低权限服务账户与 Windows ACL 限制读写，IIS 只代理 Flask 端口不映射 exports/data/logs。导出重新查询，因此无法承诺与此前预览同一 Oracle snapshot。

Oracle 文本/LOB 超过单元格配额时拒绝该任务，避免无提示截断业务内容。模板可在 scope_policy 配置 query_timeout=1–180 秒，经版本审核后生效。Worker 重启还会清除残留 openpyxl 临时 XML。前端实际部署组件与上游完整依赖树审查差异见 FRONTEND_SECURITY.md。

依赖与上游参考：[AdminLTE v3.2.0](https://github.com/ColorlibHQ/AdminLTE/tree/v3.2.0)、[iframe 官方说明](https://adminlte.io/docs/3.2/javascript/iframe.html)、[Oracle Thick 初始化](https://python-oracledb.readthedocs.io/en/v3.4.2/user_guide/initialization.html)、[Connection API](https://python-oracledb.readthedocs.io/en/v3.4.2/api_manual/connection.html)。


## 1.1.0 平台菜单架构
菜单定义及功能映射集中在 app/navigation.py，显示名称、目录、排序、启用状态存储 menus 表。角色菜单授权展开为既有 RolePermission，接口与 Worker 共用 permissions()，禁用目录同时收回其功能代码。没有新增权限服务、缓存层或前端框架。
角色管理仅维护角色；角色菜单授权决定功能入口。查询模板对象授权和用户部门数据范围属于数据边界，独立于菜单。旧内部权限写入 API 已移除，角色名维护与菜单授权接口分离；新界面不显示操作代码。历史部分授权不会自动增加审核能力，菜单只在其完整功能权限满足时显示；管理员可在新授权页面确认并重设角色菜单。
部门复用 DataScope（部门代码/名称）和 UserDataScope（可访问的部门），不等同用户唯一组织归属。当前需求不引入独立人事组织树。
平台配置和 SQL 查询配置分别展示；SESSION_SECONDS 对后续登录生效，LOGIN_LIMIT/WINDOW 即时读取，磁盘预警由 Web/Worker 动态读取。审计为全平台共用。
iframe 使用 AdminLTE 原插件，禁用重复打开时刷新；sessionStorage 只存本账号的菜单 URL 和当前标签，不存表单参数或查询数据。刷新仅恢复授权菜单，登录退出清除当前账号的工作区记录。
参考 pure-admin 的目录导航、角色菜单勾选和标签工作区交互；未引入其 Vue/构建依赖。参考仓库：https://github.com/pure-admin/vue-pure-admin 。在线演示在本次环境加载超时，未声称逐屏复刻。

## 连接配置与诊断（2026-10-15）

DatabaseConnection 保存非密码 options JSON、加密密码、版本与最近测试结果；connection:manage 独立授权，新增/修改/删除/测试进入既有审计。探测只执行固定只读 SQL，不接收自定义查询；每 Web 进程只允许一个探测，通过独立进程隔离 Oracle Thin/Thick 和原生驱动超时，总时限 10 秒。凭据通过标准输入，不放命令行，不回显驱动原始异常。

探测最多临时增加一个连接；原查询池 Web 1 + Worker 3 的预算不包含诊断连接，DBA 需额外预留 1 个。Oracle 已保存配置测试通过后成为查询数据源；MySQL/SQL Server 仍仅用于诊断。密码加密复用 APP_SECRET，未显式设置则沿用 development.key 或生成持久化 application.key，备份恢复须同时保管元数据库和密钥。
