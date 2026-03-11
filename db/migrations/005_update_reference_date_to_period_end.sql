-- ============================================================
-- Phase 7C: reference_date を期末日に統一
-- ============================================================
-- 目的: 格納規則を「期初→期末」に変更し、frequency の包含判定を
--       月番号で一意に決定できるようにする。
--
-- 実行前に必ずバックアップを取得すること。
-- PgAdmin4 で手動実行（BEGIN/COMMIT は PgAdmin4 が自動管理）
-- ============================================================

SET search_path TO calc_ecl;

-- ---- indicator_data ----------------------------------------

-- monthly: 月末日に更新（例: 2025-01-01 → 2025-01-31）
UPDATE indicator_data
SET reference_date = (
    DATE_TRUNC('month', reference_date) + INTERVAL '1 month' - INTERVAL '1 day'
)::DATE
WHERE frequency = 'monthly';

-- quarterly: 四半期末に更新（例: 2025-01-01(Q1) → 2025-03-31）
UPDATE indicator_data
SET reference_date = (
    DATE_TRUNC('month', reference_date) + INTERVAL '3 months' - INTERVAL '1 day'
)::DATE
WHERE frequency = 'quarterly';

-- calendar_year: 12月31日に更新（例: 2025-01-01 → 2025-12-31）
UPDATE indicator_data
SET reference_date = (
    DATE_TRUNC('year', reference_date) + INTERVAL '1 year' - INTERVAL '1 day'
)::DATE
WHERE frequency = 'calendar_year';

-- fiscal_year: 翌年3月31日に更新（例: 2025-04-01 → 2026-03-31）
-- DATE_TRUNC('year', date + 9ヶ月) で対象暦年を取得し、翌年3月末を算出
UPDATE indicator_data
SET reference_date = (
    DATE_TRUNC('year', reference_date + INTERVAL '9 months')
    + INTERVAL '1 year'
    + INTERVAL '2 months'
    + INTERVAL '30 days'
)::DATE
WHERE frequency = 'fiscal_year';

-- ---- target_data -------------------------------------------

-- monthly
UPDATE target_data
SET reference_date = (
    DATE_TRUNC('month', reference_date) + INTERVAL '1 month' - INTERVAL '1 day'
)::DATE
WHERE frequency = 'monthly';

-- quarterly
UPDATE target_data
SET reference_date = (
    DATE_TRUNC('month', reference_date) + INTERVAL '3 months' - INTERVAL '1 day'
)::DATE
WHERE frequency = 'quarterly';

-- calendar_year
UPDATE target_data
SET reference_date = (
    DATE_TRUNC('year', reference_date) + INTERVAL '1 year' - INTERVAL '1 day'
)::DATE
WHERE frequency = 'calendar_year';

-- fiscal_year
UPDATE target_data
SET reference_date = (
    DATE_TRUNC('year', reference_date + INTERVAL '9 months')
    + INTERVAL '1 year'
    + INTERVAL '2 months'
    + INTERVAL '30 days'
)::DATE
WHERE frequency = 'fiscal_year';

-- ============================================================
-- 確認クエリ（実行後に結果を目視確認）
-- ============================================================
-- SELECT frequency, MIN(reference_date), MAX(reference_date), COUNT(*)
-- FROM indicator_data
-- GROUP BY frequency
-- ORDER BY frequency;
--
-- SELECT frequency, MIN(reference_date), MAX(reference_date), COUNT(*)
-- FROM target_data
-- GROUP BY frequency
-- ORDER BY frequency;
