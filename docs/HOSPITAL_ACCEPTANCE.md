# 医院环境验收单

所有项目当前状态：**PENDING_HOSPITAL_VALIDATION**。不能将 skipped 或 Mock 通过标记为医院通过。院方填写执行日期、Oracle/Client/OS/浏览器版本、DBA/业务审核人、证据路径、实际结果、问题处理。

| 项目 | 验收步骤 / 成功依据 | 当前状态 |
|---|---|---|
| Oracle 连接 | 11.2.0.4 + oracledb 3.4.2 Thick + Instant Client 19c x64，启动失败绝不回退 Mock | PENDING_HOSPITAL_VALIDATION |
| NLS / 类型 | 中文、日期/月末闰年、NUMBER 精度、CLOB/BLOB 截断提示、DBMS_LOB、ROW_NUMBER、LISTAGG、院内函数语义比对 | PENDING_HOSPITAL_VALIDATION |
| SQL 范围 | DBA 批准 SELECT 安全视图，拒绝 DML/DDL，逐模板检查科室 bind 不在注释/死分支，函数无危险副作用，跨科室汇总正确 | PENDING_HOSPITAL_VALIDATION |
| 真实结果 | 与人工业务基准逐字段、计数、日期区间比对，审核 evidence 写入发布审计 | PENDING_HOSPITAL_VALIDATION |
| 取消 / 超时 | 复杂查询 60/180 秒、排队/运行取消，观察 Oracle session/call 真正终止与连接回收 | PENDING_HOSPITAL_VALIDATION |
| 负载 | 两查询 + 一导出、十用户并发，两个进程合计连接 <=4；资源配额符合 DBA 审批 | PENDING_HOSPITAL_VALIDATION |
| 大导出 | 医院批准数据规模下流式内存/磁盘、Sheet 拆分、文件上限/到期、公式注入、下载鉴权 | PENDING_HOSPITAL_VALIDATION |
| 断连 / 重启 | DB/网络/服务异常、WinSW 自动重启、RUNNING 中断/PENDING 恢复、缓存失效提示 | PENDING_HOSPITAL_VALIDATION |
| 最低浏览器 | 院方最低 Chrome 与 Win7 客户端：登录、iframe 关闭/刷新/重复保护、DataTables 横向分页、CodeMirror、月份输入降级、XLSX 下载 | PENDING_HOSPITAL_VALIDATION |
| 安全 | 用户禁用/角色撤销/范围撤销/猜任务 ID/他人导出；管理员无隐含患者权限；HTTPS、Cookie、ACL、导出磁盘策略、脱敏 | PENDING_HOSPITAL_VALIDATION |
| 上线部署 | 支持 OS、干净 venv 离线安装、包 hash、低权限双服务、IIS TLS/防火墙、VC++ 运行库 | PENDING_HOSPITAL_VALIDATION |
| 运维恢复 | 日志滚动、空间预警、一致性备份、密钥独立备份、停服恢复/回滚、凭据轮换 | PENDING_HOSPITAL_VALIDATION |

发布真实模板前需管理员审核并在 API/UI 提供 hospital_validated=true 与 evidence；这只是院方人工验收记录，不能自动证明 Oracle SQL 安全。Mock 示例对象不是医院视图，禁止原样上线。若数据范围无法安全强制施加，拒绝该模板上线。
