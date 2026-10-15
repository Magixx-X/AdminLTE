# JSON API

成功 `{success:true,data:...,error:null}`；失败 `{success:false,data:null,error:{code,message}}`。401 会话失效、403 越权/CSRF、400 参数错误、404 不存在、409 状态冲突/队列满、410 结果/文件过期、429 登录限制、500 内部错误、503 Worker 不可用。二进制下载成功直接返回 XLSX。

登录前 GET `/api/auth/csrf` 取得 token，用 X-CSRF-Token 请求头和同源 Cookie 提交 POST `/api/auth/login`（username/password）。成功返回新 csrf_token；GET `/api/auth/me` 返回用户权限/科室范围/模式；POST logout 注销。

个人资料对所有已登录用户开放，不依赖管理菜单授权。GET `/api/auth/me` 另返回 `username/nickname/contact`；PUT `/api/auth/profile` 仅接受本人 `nickname`（最多 80 字符）与 `contact`（最多 120 字符），拒绝用户名、角色等其他字段。POST `/api/auth/password` 接受 `current_password/new_password/confirm_password`，新密码 6–128 字符；验证当前密码、确认值并限制密码猜测，成功后撤销本人全部会话、清除认证 Cookie，需重新登录。写操作沿用 CSRF，审计不包含资料或密码值。管理员创建、重置及命令行密码规则同为 6–128 字符。

| 路径 | 方法 / 请求 |
|---|---|
| /api/templates | GET（q/category，编辑页 manage=1）、POST name/category/description/sql/schema/sort_fields/scope_policy/summary，可 copy_from |
| /api/templates/{id} | PUT 全部草稿字段 + expected_version（乐观并发），DELETE 软删除 |
| /api/templates/{id}/submit | POST 草稿进入 REVIEW |
| /api/templates/{id}/publish | POST scope_reviewed:true；Oracle 另要求 hospital_validated:true、evidence |
| /api/templates/{id}/disable | POST 停用 |
| /api/templates/{id}/versions | GET 所有历史 SQL 版本（编辑授权） |
| /api/queries | POST template_id、params，返回 202 group_id/task_id/task_ids |
| /api/queries/{id} | GET 状态、版本、月份、预览行数、truncated、非敏感摘要 |
| /api/queries/{id}/results | GET start/length/draw/sort/direction；返回 DataTables data/recordsTotal/recordsFiltered、columns/rows |
| /api/queries/{id}/cancel | POST 请求取消，PENDING 立即取消 |
| /api/queries/{id}/retry | POST 从加密参数再执行该月份，按最新发布版重新校验 |
| /api/queries/history | GET 本人 history；template_id/status/group_id/date_from/date_to（排他）/start/length，返回 items/total |
| /api/exports | POST group_id；GET 本人记录 |
| /api/exports/{id} | GET 状态，DELETE 已结束文件 |
| /api/exports/{id}/download | GET 重新鉴权与有效期检查 |
| /api/admin/users | GET、POST username/password/nickname/contact/role_ids/scopes/enabled |
| /api/admin/users/{id} | PUT password（可选）/nickname/contact/role_ids/scopes/enabled |
| /api/admin/roles | GET 角色 id/name/code/enabled/created_at/remark；POST name/code/enabled/remark |
| /api/admin/roles/{id} | PUT name/code/enabled/remark；DELETE 未引用角色（授权使用 /menus 子资源） |
| /api/admin/grants | GET；POST template_id、user_id 或 role_id、execute/view/export（全部 false 即撤销） |
| /api/admin/scopes | POST code/name/parent/position/enabled/remark，创建部门（科室） |
| /api/admin/settings | GET/PUT 平台登录与磁盘设置（不接受凭据） |
| /api/admin/audits | GET module/action/user_id/template_id/task_id/result/date_from/date_to/start/length |
| /api/admin/health | GET 管理员服务自检，脱敏配置摘要 |
| /api/dashboard | GET 本人统计、近期任务和 Worker 心跳 |

提交示例：

```json
{"template_id":1,"params":{"month_start":"2024-02","month_end":"2024-03","sample_rows":240,"scenario":"normal","equipment":["CT"]}}
```

参数 schema 支持 string/integer/decimal/date/datetime/month/select/multiselect/boolean、required、default、choices、max_length、min/max、end_after（结束参数引用开始参数名）。可选参数可独立为空；额外字段一律拒绝。内置 month_start/month_end 不在 schema 中重复定义。SQL 使用 :begin_time（包含）、:end_time（排他）、:scope_department（服务端范围）。JSON 参数值不直接拼到 SQL。动态筛选需要审核 SQL 实际使用相应 binds；Mock 示例 SQL 的业务对象并不存在，不能原样生产发布。

所有 UTC 时间使用 ISO 格式，月份按自然月份，不使用终端时区转换 Oracle 业务时间；医院需确认 Oracle 业务时区/NLS。前端不提交可执行 SQL 给 queries API。


## 1.1.0 平台接口
| 路径 | 方法 / 内容 |
|---|---|
| /api/navigation | GET 当前账号可用子菜单 |
| /api/admin/menu-authorization | GET 角色及勾选菜单，用于授权页面 |
| /api/admin/roles/{id}/menus | PUT {"menu_ids":["query","history","about"]}；立即生效 |
| /api/admin/menus | GET 菜单目录；POST code/title/parent/position/enabled 新建目录或恢复已注册页面 |
| /api/admin/menu-options | GET 可添加的已注册工作页面 |
| /api/admin/menus/{code} | PUT title/parent/position/enabled；DELETE 软删除，管理入口与有子菜单的目录不能删除；拒绝任意 URL、环和 HTML 标签 |
| /api/admin/user-options | GET 用户管理可选角色与部门 |
| /api/admin/grant-options | GET 模板授权可选模板/用户/角色名称（无 SQL） |
| /api/admin/departments | GET 部门目录；新增沿用 POST /admin/scopes |
| /api/admin/departments/{code} | PUT name/parent/position/enabled/remark；DELETE 没有子部门且未被引用的部门 |
| /api/admin/query-settings | GET/PUT SQL 查询模块配额 |
| /api/admin/monitor | GET 平台会话/用户/Worker/磁盘状态 |
| /api/about | GET 平台信息与生产/开发依赖版本 |

系统设置仅接受 SESSION_SECONDS/LOGIN_LIMIT/LOGIN_WINDOW/DISK_WARNING_BYTES。旧 /admin/settings 的查询配额输入已移至 /admin/query-settings；旧角色 permissions 写入返回 400，请改用 menu_ids。菜单只决定功能，模板对象授权/部门范围/任务归属继续校验。

用户角色与用户部门使用单选：role_ids、scopes 为兼容既有接口仍用数组，每次提交最多一项，空数组表示清除。编辑会替换原有关联；升级保留历史多项配置，在编辑表单中提示保存后的变化。部门层级仅用于组织和列表筛选，不自动扩大查询范围。停用角色立即撤销其功能与模板权限，停用科室立即撤销该科室查询范围。

## 数据库连接配置

均要求 connection:manage 与现有会话/CSRF；未授权用户不返回配置和密码状态。

| 路径 | 方法 / 内容 |
|---|---|
| /api/admin/connections | GET 配置列表（无密码，仅 has_password）；POST 新增 |
| /api/admin/connections/{id} | PUT 全部表单参数 + revision（乐观版本检查）；DELETE 删除 |
| /api/admin/connections/test | POST 测试当前表单；可带 id 使用旧密码，不写回保存记录 |
| /api/admin/connections/{id}/test | POST 测试已保存启用配置并记录结果；参数变更或删除时 persisted=false |

表单字段：name、engine（oracle/mysql/sqlserver）、mode（tcp/local）、host、port（整数 1–65535）、namespace、username、password、local_instance、service_kind（service_name/sid）、service_value、oracle_driver（thin/thick）、oracle_client_dir（可选，最多 1024 字符，包含 oci.dll 的服务器本地绝对目录）、auth_type（password/windows）、schema、encrypt、trust_certificate、enabled。Windows 验证仅用于 SQL Server；其余新建配置必须给密码。密码编辑留空保留，改数据库类型必须重新提供。

oracle_client_dir 保存在 options JSON 并回显，无需数据库迁移。Oracle Thick 优先使用该字段，空值使用部署配置 ORACLE_CLIENT_DIR，再由驱动按系统默认方式查找。Thin 与其他类型清空此项；非法路径返回 400，缺少 DLL 或加载失败返回 data.code=ORACLE_CLIENT，不回显原始驱动异常。网页设置同时供查询服务使用。

测试 API 的 success=true 表示请求已处理；是否连通看 data.status、code、message、elapsed_ms。已保存启用的 Oracle 在当前版本测试通过后，将 system_settings.query_connection_id 设为该 ID，并返回 query_source=true。变更或删除则 persisted=false，不切换；草稿测试不启用连接。GET 列表增加 is_query_source。网页“保存并测试”依次调用保存和已保存测试 API。任务 params_summary.source 保存来源身份，Worker 拒绝跨来源执行；审计增加 connection.query_source。
