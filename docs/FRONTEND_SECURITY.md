# 前端组件审查与部署范围

AdminLTE 固定 3.2.0；实际加载资源 jQuery 3.7.1、Bootstrap 4.6.2、DataTables 1.13.11、CodeMirror 5.65.20、FontAwesome Free 5.15.4。`frontend-assets.json` 记录下载来源和 SHA-256，许可证存 docs/licenses。没有 CDN，也不采用整个 npm 依赖树部署。

实际执行了临时 npm package-lock-only 与 npm audit（公开 registry.npmjs.org），结果保存在 frontend-audit.json。上游 AdminLTE 完整 npm 依赖树报告 **5 个 moderate**，涉及 summernote、moment、tempusdominus 及其传递依赖标记；本应用不部署或加载这些插件。它们不是本应用实际加载组件的已知漏洞通过证明，也不能把上游完整审查说成零漏洞。部署目录只收集明确使用的资源，避免附带这些插件。

固定 Bootstrap 4 / AdminLTE 3.2 属于旧技术栈。审查数据库覆盖有限，旧栈、最低 Chrome 与 Windows 客户端的安全和兼容性需要医院批准；不能声称已经完成全面渗透测试。应用将所有表格和通知中的不可信文本转义，不将用户输入赋给 Bootstrap HTML 组件属性，不开放任意 HTML 内容编辑，使用 CSP 同源与 CSRF/RBAC。

Python 依赖独立 pip-audit：首轮 9 个记录/3 包，修复后报告 No known vulnerabilities found（审查时点的公开数据库，非绝对安全保证）。Oracle、IIS、ACL、WinSW 服务账户、医院内网最低浏览器见 HOSPITAL_ACCEPTANCE.md，当前均待院方验收。
