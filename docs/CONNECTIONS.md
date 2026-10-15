# 数据库连接配置

“系统管理 → 连接配置”管理 Oracle、MySQL、SQL Server 的连接参数，支持新增、编辑、删除、启用/停用、名称和类型筛选、排序及字段显示。界面沿用蓝白整页列表和弹窗样式。“权限管理 → 角色菜单授权”控制谁能访问此页面；拥有此菜单权限的管理员可以修改密码并从应用服务器发起连接测试。

## 测试与查询任务的关系

连接测试独立于当前查询数据源：系统使用 Mock 时，也能测试真实的本地或远程 Oracle、MySQL、SQL Server，无需切换模式或重启。运行状态同时显示“查询任务数据源”和“连接配置测试”统计，后者来自已保存配置的最近一次测试，不是持续心跳。

**本地测试通过不代表远程 IP 连接一定通过。** 本地成功只验证当前地址、驱动、身份验证和数据库只读探测。改用远程地址后，监听地址、端口、防火墙、账号来源限制、Windows 服务身份和 TLS 证书都可能不同，必须另存或修改为目标地址并再次测试。

本次连接配置用于连接管理与诊断，不会自动成为 SQL 查询任务的数据源。现有查询任务仍由部署配置 `DATA_SOURCE=mock/oracle` 和 Oracle 只读 SQL 审核控制；MySQL、SQL Server 的模板执行、分页、导出方言适配不在本次连接测试中。不能把“已通过”解释为业务 SQL、业务表授权或生产验收已通过。

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
3. 点击“保存”，再从列表点击“测试连接”，记录本条配置的测试状态、时间和耗时。修改配置后旧测试结果清除，显示“未测试”。弹窗草稿测试不修改已保存记录的最近测试结果。
4. 测试执行 `SELECT 1 FROM DUAL`（Oracle）或 `SELECT 1`（MySQL、SQL Server），按所填信息核对可选 Schema，然后关闭连接。没有业务查询或写入 SQL。连接失败、未安装驱动、超时均显示未通过，不生成模拟成功结果。

每个 Web 进程同时允许一项测试，驱动连接和调用设置约 3 秒上限，独立测试进程总计 10 秒上限。测试期间若配置修改或删除，旧结果不会写回新配置。Oracle Thin/Thick 在独立进程初始化，避免影响正在运行的查询服务。

## 驱动、TLS 与安装

Python 依赖已固定在 requirements.in / requirements.lock：`oracledb==3.4.2`、`PyMySQL==1.2.3`、`pyodbc==5.3.0`。安装更新：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m flask --app wsgi:application migrate
```

Oracle Thick 需要另行安装 64 位 Instant Client；使用受保护部署配置中的 `ORACLE_CLIENT_DIR`，或服务端默认 Oracle Client 查找路径。此路径不由网页任意指定。Oracle 11g 不能用 Thin 替代 Thick。

SQL Server 除 pyodbc 外，还需要由管理员在服务端安装 **Microsoft ODBC Driver 18 或 17 for SQL Server**；Windows 旧版内置“SQL Server”驱动不作为自动回退。网页会报告缺少驱动，不会自动下载安装系统组件。

MySQL 和 SQL Server 默认开启 TLS。MySQL 要求服务端支持 TLS 并验证证书、主机名；私有 CA 可用受保护配置 `MYSQL_SSL_CA` 指定 PEM 文件路径，留空使用系统默认信任。SQL Server 默认不跳过证书校验，“信任服务端证书”会跳过该校验；本地自签名环境需按实际证书设置选择。Oracle 网络加密和钱包按服务端 Oracle Client/TNS 配置管理。

## 密码与升级

密码用现有应用 `APP_SECRET` 派生的 Fernet 密钥加密存储在 SQLite；API 只返回 `has_password`，不回显明文或密文。测试凭据通过子进程标准输入传递，不放入命令行参数。审计记录连接编号、数据库类型与测试结果码，不保存密码或驱动原始异常。

备份与恢复必须同时妥善保管对应 `APP_SECRET`（开发环境为 data/development.key），否则原密码和查询任务参数无法解密。数据库连接名、主机、用户名等非密码配置仍由 SQLite 文件 ACL 保护。

0004 迁移创建 database_connections 表。首次升级给原本拥有“系统设置”权限的角色补充连接配置入口；以后重复迁移不会恢复管理员主动撤销的连接配置权限。启动脚本会自动迁移，现有账号、任务与菜单配置保留；升级前按原部署文档停服备份。

当前本机已验证 API、加密与权限边界、驱动参数契约、浏览器三类配置表单、真实驱动失败反馈及超时分支；未提供可成功登录的三类数据库，不能声称已验证真实数据库成功连接或医院业务 SQL。

参考：[python-oracledb 3.4.2 连接文档](https://python-oracledb.readthedocs.io/en/v3.4.2/user_guide/connection_handling.html)、[PyMySQL 连接参数](https://pymysql.readthedocs.io/en/latest/modules/connections.html)、[Microsoft ODBC 连接选项](https://learn.microsoft.com/en-us/sql/connect/odbc/dsn-connection-string-attribute?view=sql-server-ver17)、[pyodbc Windows 连接](https://github.com/mkleehammer/pyodbc/wiki/Connecting-to-SQL-Server-from-Windows)。
