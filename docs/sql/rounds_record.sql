WITH base_visit AS (
    SELECT
        pv.patient_id,
        pv.visit_id,
        pv.inp_no,
        pv.admission_date_time,
        pm.name AS patient_name,
        CASE WHEN EXISTS (
            SELECT 1
            FROM jhmr_file_index jfi
            WHERE jfi.patient_id = pv.patient_id
              AND jfi.visit_id = pv.visit_id
              AND jfi.topic LIKE '%查房%'
              AND jfi.caption_date_time BETWEEN pv.admission_date_time
                                            AND pv.admission_date_time + 2
        ) THEN 1 ELSE 0 END AS is_qualified
    FROM pat_visit pv
    LEFT JOIN pat_master_index pm ON pm.patient_id = pv.patient_id
    WHERE pv.discharge_date_time >= :start_date
      AND pv.discharge_date_time < :end_date
),
stat AS (
    SELECT
        COUNT(DISTINCT CASE WHEN is_qualified = 1 THEN patient_id END) AS cnt_numerator,
        COUNT(DISTINCT patient_id) AS cnt_denominator
    FROM base_visit
),
detail_data AS (
    SELECT
        patient_name AS 患者姓名,
        inp_no AS ID号,
        TO_CHAR(admission_date_time, 'YYYY-MM-DD') AS 入院日期,
        CASE is_qualified WHEN 1 THEN '是' ELSE '否' END AS 是否规范完整,
        ROW_NUMBER() OVER (
            ORDER BY admission_date_time, inp_no, patient_id, visit_id
        ) AS rn
    FROM base_visit
)
SELECT
    '汇总统计' AS 序号,
    '分子:' || s.cnt_numerator || ' 分母:' || s.cnt_denominator ||
    ' 规范率:' || CASE WHEN s.cnt_denominator = 0 THEN '无样本'
        ELSE TO_CHAR(ROUND(s.cnt_numerator * 100 / s.cnt_denominator, 2), 'FM990.00') || '%'
    END AS 患者姓名,
    '' AS ID号,
    '' AS 入院日期,
    '' AS 是否规范完整,
    0 AS sort_flag
FROM stat s
UNION ALL
SELECT
    TO_CHAR(rn) AS 序号,
    患者姓名,
    ID号,
    入院日期,
    是否规范完整,
    rn AS sort_flag
FROM detail_data
ORDER BY sort_flag
