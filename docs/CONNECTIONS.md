# 数据库连接配置

“系统管理 → 连接配置”管理 Oracle、MySQL、SQL Server 的连接参数，支持新增、编辑、删除、启用/停用、名称和类型筛选、排序及字段显示。界面沿用蓝白整页列表和弹窗样式。“权限管理 → 角色菜单授权”控制谁能访问此页面；拥有此菜单权限的管理员可以修改密码并从应用服务器发起连接测试。

## 测试与查询任务的关系

平台启动不要求预先填写 Oracle 参数，也不在启动阶段连接 Oracle。初始化平台账号并登录后，在网页新增 Oracle，点击“保存并测试”，通过后自动设为查询数据源。多个 Oracle 连接以最近一次对已保存配置测试通过者为准，列表显示“查询数据源”标记。Web/Worker 从 SQLite 按需读取相同配置，普通连接信息变更无需重启。

**本地测试通过不代表远程 IP 连接一定通过。** 本地成功只验证当前地址、驱动、身份验证和数据库只读探测。改用远程地址后，监听地址、端口、防火墙、账号来源限制、Windows 服务身份和 TLS 证书都可能不同，必须另存或修改为目标地址并再次测试。

未配置/未通过测试时允许登录和管理，但查询会提示需要配置，不自动回退 Mock。修改、停用或删除当前连接后不会使用旧凭据，必须重新测试；旧任务绑定当时的连接 ID/版本，切换后拒绝跨连接执行或重新导出。MySQL、SQL Server 仍只提供连接诊断。查询模板保存即启用，菜单及模板访问授权继续有效；真实业务 SQL 结果需在目标数据库核对。

## 参数填写

| 字段 | Oracle | MySQL | SQL Server |
|---|---|---|---|
| 连接名称 | 唯一、易识别的名称 | 同左 | 同左 |
| 命名空间 | Schema，可选；填入时核对 ALL_USERS 可见性，按常规大写名称匹配 | 数据库名称，必填 | 数据库名称，必填；另有可选 Schema |
| IP / 主机名、端口 | 默认 1521 | 默认 3306 | 默认 1433 |
| 服务类型 | 选择 Service Name 或 SID，填写对应值 | 不适用 | 不适用 |
| 身份验证 | 用户名和密码 | 用户名和密码 | 用户名和密码，或 Windows 身份验证 |
| 驱动 | Thick：Oracle 11g；Thin：Oracle 12.1 及以上 | PyMySQL | pyodbc + Microsoft ODBC Driver 18/17 |
| 本地方式 | 本机端口 + 服务名/SID，或本地 TNS 服务别名 | 127.0.0.1 + 端口 | 本机端口，或本地命名实例/LocalDB |

“本地”指安装在**运行 Web 服务的服务器**上的数据库，不是浏览器所在电脑，也不是 SQLite、Excel 或任意数据库文件。

- Oracle 本地 TNS 别名例如 `ORCL`：需在服务端 Oracle Client/TNS_ADMIN 配置对应的 tnsnames.ora；别名实际指向的地址以服务端 TNS 配置为准。留空别名时使用 `127.0.0.1`、端口与服务名/SID。
- MySQL 本地方式要求实例监听本机 TCP 端口；不使用 Windows 命名管道。
- SQL Server 实例示例：`localhost\SQLEXPRESS`、`(localdb)\MSSQLLocalDB`。指定命名实例时使用实例解析，表单端口不参与该路径。LocalDB 隶属于 Windows 用户，Windows 服务账号未必能访问桌面用户创建的实例。Windows 身份验证使用运行 Web 服务的账号，不使用浏览器登录账号。

## 使用步骤

1. 点击“新增连接”，选择数据库和连接方式，填写相应参数。数据库密码不要求与平台登录密码相同。
2. 弹窗“测试连接”验证当前填写参数；编辑已有配置时密码留空保留，首次创建或切换数据库类型时须重新填写密码。Windows 身份验证不需要填写密码。
3. Oracle 点击“保存并测试”，服务器保存后测试同一版本，通过后设为 SQL 查询数据源。列表“测试连接”通过也会启用该 Oracle 配置。MySQL/SQL Server 仍先保存再独立测试。修改配置后旧测试结果清除；弹窗草稿测试不保存或启用连接。
4. 测试执行 `SELECT 1 FROM DUAL`（Oracle）或 `SELECT 1`（MySQL、SQL Server），按所填信息核对可选 Schema，然后关闭连接。没有业务查询或写入 SQL。连接失败、未安装驱动、超时均显示未通过，不生成模拟成功结果。

每个 Web 进程同时允许一项测试，驱动连接和调用设置约 3 秒上限，独立测试进程总计 10 秒上限。测试期间若配置修改或删除，旧结果不会写回新配置。Oracle Thin/Thick 在独立进程初始化，避免影响正在运行的查询服务。

## 驱动、TLS 与安装

Python 依赖已固定在 requirements.in / requirements.lock：`oracledb==3.4.2`、`PyMySQL==1.2.3`、`pyodbc==5.3.0`。安装更新：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m flask --app wsgi:application migrate
```

Oracle Thick 需要另行安装 64 位 Instant Client。新增/编辑连接时，可在“Oracle Client 目录（可选）”填写运行本系统的服务器上包含 `oci.dll` 的本地绝对目录，例如 `C:\oracle\instantclient_19_25`，不要填写 DLL 文件本身、相对路径或网络共享路径。此字段仅在 Oracle Thick 下显示；Thin、MySQL 和 SQL Server 不使用此字段。路径随每条连接保存在 SQLite 的 options JSON，编辑时回显，清空并保存即可恢复默认，无需数据库迁移。

客户端目录按以下优先级使用：当前连接的网页设置 → 部署配置 `ORACLE_CLIENT_DIR`（进程环境变量优先于 config.local.json）→ Oracle 驱动的系统默认查找方式（含 Windows PATH）。例如可在启动 Web 的 PowerShell 中设置 `$env:ORACLE_CLIENT_DIR = 'C:\oracle\instantclient_19_25'`；Windows 服务需在服务运行环境配置并重启。`.env` 不会自动加载。网页路径保存后下次连接测试立即使用，环境变量或部署配置变更则需要重启相关进程。

测试时会检查所指定目录是否包含 `oci.dll`；存在 DLL 但仍无法加载时，检查客户端位数、完整文件集、服务账号读取权限和所需 VC++ 运行库。保存路径不会安装、上传或复制客户端。只有既有 `connection:manage` 权限用户可设置并测试路径，应由部署管理员维护可信的客户端目录。Oracle 11g 不能用 Thin 替代 Thick。

网页设置同时用于连接测试与后续查询。已加载 Oracle 客户端后，变更目录或 Thin/Thick 模式需重启 Web/Worker；仅改地址、账号或密码无需重启。全局 ORACLE_USER/PASSWORD/DSN 作为尚未选中网页连接时的兼容方案保留，不再必填。默认 DATA_SOURCE=oracle，Mock 仅由开发者显式启用。

SQL Server 除 pyodbc 外，还需要由管理员在服务端安装 **Microsoft ODBC Driver 18 或 17 for SQL Server**；Windows 旧版内置“SQL Server”驱动不作为自动回退。网页会报告缺少驱动，不会自动下载安装系统组件。

MySQL 和 SQL Server 默认开启 TLS。MySQL 要求服务端支持 TLS 并验证证书、主机名；私有 CA 可用受保护配置 `MYSQL_SSL_CA` 指定 PEM 文件路径，留空使用系统默认信任。SQL Server 默认不跳过证书校验，“信任服务端证书”会跳过该校验；本地自签名环境需按实际证书设置选择。Oracle 网络加密和钱包按服务端 Oracle Client/TNS 配置管理。

## 密码与升级

密码用现有应用 `APP_SECRET` 派生的 Fernet 密钥加密存储在 SQLite；API 只返回 `has_password`，不回显明文或密文。测试凭据通过子进程标准输入传递，不放入命令行参数。审计记录连接编号、数据库类型与测试结果码，不保存密码或驱动原始异常。

未显式设置 APP_SECRET 时，自动生成并保存到 data/application.key；已有 data/development.key 优先沿用，不覆盖已有密钥。恢复必须同时保管实际使用的 APP_SECRET 或密钥文件，否则原密码和任务参数无法解密。数据库文件和密钥需目录 ACL 保护；生产仍需 HTTPS。

0004 迁移创建 database_connections 表。首次升级给原本拥有“系统设置”权限的角色补充连接配置入口；以后重复迁移不会恢复管理员主动撤销的连接配置权限。启动脚本会自动迁移，现有账号、任务与菜单配置保留；升级前按原部署文档停服备份。

当前本机已验证 API、加密与权限边界、驱动参数契约、浏览器三类配置表单、真实驱动失败反馈及超时分支；未提供可成功登录的三类数据库，不能声称已验证真实数据库成功连接或医院业务 SQL。

参考：[python-oracledb 3.4.2 连接文档](https://python-oracledb.readthedocs.io/en/v3.4.2/user_guide/connection_handling.html)、[PyMySQL 连接参数](https://pymysql.readthedocs.io/en/latest/modules/connections.html)、[Microsoft ODBC 连接选项](https://learn.microsoft.com/en-us/sql/connect/odbc/dsn-connection-string-attribute?view=sql-server-ver17)、[pyodbc Windows 连接](https://github.com/mkleehammer/pyodbc/wiki/Connecting-to-SQL-Server-from-Windows)。
