# Windows 离线部署、升级与恢复

## 支持与前提

服务端使用仍受支持的 Windows/Windows Server x64，Python 3.11 x64；不将服务器部署在 Win7。Win7/旧 Chrome 仅客户端兼容待验收，医院决定最低支持版本及安全政策。软件包当前携带 Python 3.11.9 官方 Windows 安装程序（为本机实测版本）；医院应评估 Python 后续安全维护版本，更新运行时后完整回归重新打包。

院方提供 Oracle 11.2.0.4 只读账号、DSN、授权视图，确认无 DML/DDL/危险函数执行权限；单独按软件许可准备 Instant Client 19c x64 Basic 及对应 VC++ 运行库。离线包不包含 Oracle Client/真实配置。Oracle 数据库、DLL、NLS、取消、LOB、性能全部 PENDING_HOSPITAL_VALIDATION。

## 在联网构建机打包

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\package_offline.ps1
```

脚本只收集白名单目录，排除运行数据、`.venv`、`.runtime`、config.local.json、密钥；下载 Python 3.11 win_amd64 固定 wheel、官方 Python 安装程序、WinSW 2.12.0 x64。生成 ZIP、外部 ZIP SHA-256、包内 SHA256.json、BUILD.json。可把已下载 wheels 放 `.runtime\wheelhouse` 后 `-SkipDownloads` 打包；仍要求已有官方安装程序和 WinSW。发布前运行依赖安全审计并保存报告，核对许可。网络下载属于构建阶段；安装阶段使用 `--no-index`。

## 内网新安装

1. 使用院方批准介质传输，先与构建机保存的 ZIP SHA-256 比对，解压到例如 `C:\HospitalQuerySystem`（路径尽量无空格）。包内 `scripts\verify_package.ps1` 检查每个文件。不要带开发 data、密钥、真实结果入包。
2. 运行 `installers\python-3.11.9-amd64.exe` 安装 x64 Python（不需终端 Oracle Client），新建部署目录自己的 venv，禁止复制开发 `.venv`。

```powershell
Set-Location C:\HospitalQuerySystem
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_offline.ps1 -Python C:\Python311\python.exe
.\.venv\Scripts\python.exe -m flask --app wsgi:application init-admin --username hospital_admin
```

3. 无需预先设置 Oracle 参数或 APP_SECRET。初始化管理员后启动平台，在“系统管理 → 连接配置”填写 Oracle 并“保存并测试”，通过后供查询使用。密钥自动保存到 data/application.key，已有 development.key 或显式 APP_SECRET 优先沿用。生产 Cookie/TLS 策略通过受保护 config.local.json 或服务环境设置 APP_ENV=production；默认 DATA_SOURCE=oracle。Web/Worker 必须使用相同密钥、数据目录和 IPC_PORT，不要删除密钥文件。
4. Oracle 延迟到健康检查或查询时初始化，迁移与账号初始化不依赖业务库。未配置或测试失败时不能查询，不回退 Mock。模板保存即可查询；合成模板的示例视图需替换为实际业务表/视图并核对字段、口径。
5. Windows ACL：创建医院批准的低权限服务账号，只对应用源码/venv/Instant Client 授予读取执行，data/exports/logs/backups 授予所需修改；config.local.json/开发 key 仅服务账号与医院管理员可读。其他普通用户移除权限。可用 `icacls` 按医院账户名施加 ACL；不要将 Everyone/Users 写权限授予应用目录。exports/temp 同样敏感，建议受医院批准的磁盘加密。仅授予服务账户必要 “作为服务登录”。
6. 手动启动检查（两个 PowerShell 窗口）：

```powershell
.\scripts\start_worker.ps1
.\scripts\start_server.ps1
.\.venv\Scripts\python.exe scripts\health_check.py
```

Waitress 只监听 127.0.0.1:8080，IPC 只监听 127.0.0.1:18081。不能把 IPC 暴露到内网。生产 Secure Cookie 需要浏览器通过 HTTPS；禁止以普通 HTTP 访问生产登录。没有 IIS 时需院方提供可信 TLS 反向代理。

## Windows 服务

安装步骤需医院管理员提升权限；开发电脑不主动安装系统服务。

```powershell
.\scripts\install_services.ps1 -ServiceAccount 'DOMAIN\hospital_query_service'
```

脚本复制离线包 WinSW，注册 HospitalQueryWeb / HospitalQueryWorker 并置为 Disabled。在 services.msc 中为**两个服务**配置院方低权限账户和密码（不通过命令行暴露密码）；确认 ACL，改为 Automatic 并先启动 Worker 再 Web。默认 LocalSystem 不能用于上线。WinSW 日志按大小滚动、异常 10 秒重启；Worker 停止超时 195 秒，异常残留任务启动时中断。升级时 Stop-Service 两个服务，确认进程停止后备份；不要运行两个 Worker 或多个 Web 进程。卸载：`.\scripts\uninstall_services.ps1`，数据文件保留。

## IIS / 网络

院方安装并配置 IIS ARR + URL Rewrite，把内部 HTTPS 站点反向代理至 `http://127.0.0.1:8080`，设置可信内部证书与浏览器信任。静态请求也经 Flask（或仅映射 app/static），绝不映射项目根目录、data、exports、logs、backups。只在医院许可网段开放 HTTPS 443；8080 与 IPC 不开放。应用不信任 X-Forwarded-For/X-Forwarded-Proto，不默认安装 ProxyFix；如院方启用代理头必须严格限定一跳与代理来源。CSP 默认仅同源。导出下载授权经过 Flask。

## 备份与恢复

Worker 每天一致性备份到 data/backups；院方也可用任务计划程序每日执行：

```powershell
.\.venv\Scripts\python.exe scripts\backup_sqlite.py --destination C:\HospitalQueryBackup
```

SQLite Backup API 保证正在写入时一致，不直接复制 metadata.db。监控管理员自检 free_disk_bytes 与心跳，Windows 服务日志和 application.log；磁盘阈值由院方监控系统配置。院方制定备份保留/加密/转移策略；备份包含账号与权限/加密任务参数，必须限制访问。APP_SECRET 另行安全备份，不能只备份 DB。导出文件不自动纳入 DB 备份，恢复后的旧下载可能不存在；重新导出即可。

恢复必须先停服（Web 和 Worker）：

```powershell
Stop-Service HospitalQueryWeb,HospitalQueryWorker
.\.venv\Scripts\python.exe scripts\restore_sqlite.py C:\HospitalQueryBackup\metadata-YYYYMMDD-HHMMSS.db --services-stopped
# 恢复原 APP_SECRET 和受保护配置，再启动 Worker / Web
Start-Service HospitalQueryWorker,HospitalQueryWeb
```

脚本验证备份 integrity_check，恢复前保存现状，再用 Backup API 写入。`--services-stopped` 是操作员确认，脚本不会擅自停服务；确认无运行进程才能执行。Worker 自动标记 RUNNING 中断，PENDING 重新鉴权再执行，内存预览需重查。回滚使用原版本应用与对应备份，不自动 downgrade 销毁审计。

管理员忘记密码：在维护期停止两服务，运行 `.\.venv\Scripts\python.exe -m flask --app wsgi:application reset-password hospital_admin`，旧会话失效并记录审计，然后重启。迁移与密码管理不初始化 Oracle 池；health_check.py 只检查本地元数据库和 Worker 心跳。实时 Oracle 自检通过管理员 /api/admin/health 按需使用 Web 池。数据库密码轮换在网页编辑并保存测试，无需重启；APP_SECRET 或自动密钥文件不能直接更换，否则已有连接密码和任务参数不可读。

磁盘空间预警默认 1 GiB，Worker 每小时最多记录一次 DISK_SPACE_LOW，管理员健康检查显示 warnings；可通过环境 DISK_WARNING_BYTES 设置院方批准阈值。

本机离线安装/脚本语法验证与医院服务注册/IIS/TLS/ACL 验收分开记录，不能以开发电脑 Mock 成功替代真实上线验收。

## 连接配置补充（2026-10-15）

更新 requirements.lock 增加 PyMySQL 与 pyodbc，升级时安装新增 Python 驱动后迁移 0004。离线构建仍由 package_offline.ps1 下载固定 wheels；SkipDownloads 前须把新增的两项 wheels 放入 .runtime/wheelhouse。旧 ZIP 不包含本次源码变化，不可当作已更新发布包。

连接配置的三类测试独立于 DATA_SOURCE，不要求在运行状态切换 Mock。SQL Server 在服务端另行安装 ODBC Driver 18/17；Oracle Thick 准备 Instant Client 与 ORACLE_CLIENT_DIR/TNS_ADMIN；MySQL 私有 CA 可设置 MYSQL_SSL_CA。系统服务的本地实例和 Windows 身份验证使用服务身份，LocalDB 的用户归属与桌面登录可能不同。诊断额外最多占用一个连接。详见 [连接配置](CONNECTIONS.md)；真实数据库成功与院内 SQL 验收需独立记录。

## 保存即查询与日期参数升级（0005）

停止 Web/Worker，备份元数据库及原密钥，更新源码后运行：

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi:application migrate
```

双击启动入口也会执行迁移；Windows 服务需先手动迁移再启动。0005 保留账号、历史版本和任务，使原草稿/审核中模板启用；停用模板保持停用。模板创建者获得缺失的对象授权，模板编辑角色获得查询菜单所需权限，删除审核权限。旧版 scope_policy 不再生效；旧 SQL 的 scope_department 等隐式变量需移除或在 schema 声明为普通参数。begin_time/end_time 若仍用于新查询，也需声明类型及 end_after 日期配对。刷新网页后使用按类型生成的参数表单。更新已有离线包需重新构建，旧 ZIP 不含这些变化。
