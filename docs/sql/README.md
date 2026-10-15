# 上级医师查房记录规范率模板

SQL 使用 rounds_record.sql，配置参照 rounds_record.json。保存后即可在查询页选择执行，不再填写数据范围策略、不提交审核或验收证据。创建者自动获得自己的模板访问权限，其他用户仍由管理员授予菜单与模板权限。

参数 schema 仅定义 start_date/end_date，均为必填 date；end_date 使用 end_after=start_date，表示结束严格晚于开始且不包含结束当天。查询一整月：2026-10-01 至2026-11-01；查询一天：2026-10-15 至2026-10-16。SQL 直接比较日期绑定对象，不再 TO_DATE，也不需要 begin_time/end_time 或 scope_department。

查询页只有这两个出院日期输入框，提供本月、上月、最近3/6/12月。跨月按自然月切分参数，例如2026-09-15至2026-11-05分别查询9月15日至10月1日、10月1日至11月1日、11月1日至11月5日。结果完成后直接显示月份标签，导出按月分工作表。最近N月包含本月，结束为下月1日；日期范围均左闭右开。多个月份的患者去重率不能直接相加得到全期间总率。

排序白名单推荐 []，保留 SQL 的 sort_flag 顺序，使汇总在前；["sort_flag"]允许预览排序，但降序会把汇总移到最后。白名单仅接受英文字段名，不填中文别名、ASC/DESC或表达式；它不改写导出 SQL 顺序。

当前SQL保留原 COUNT(DISTINCT patient_id) 口径，明细按住院记录展示；同一患者多次住院可能只计一个患者。规则只判断入院48小时内是否存在标题含“查房”的记录，未验证医师级别、签名、正文完整性或作废状态。零分母显示“无样本”。这些SQL是配置示例，需核对实际业务表与字段。

schema字段：name与SQL的:参数名对应；label为界面名称；type支持string/integer/decimal/date/datetime/month/select/multiselect/boolean；required表示必填。结束日期使用end_after引用同类型的开始日期，单一日期范围默认拆月；多个范围时用split_by_month=true选择一个，false关闭该范围拆月。无日期范围时只执行一次。

平台SQL填写SELECT/WITH查询，不包含CREATE VIEW、SQL*Plus的/结束符。保留只读数据库账号和既有登录、模板访问、配额及导出授权控制。
