-- 003: indicator_datasets に決算年月カラムを追加
-- ECLモデルの対象決算期でデータセットを一意に管理するため
--
-- 実行方法: PgAdmin4で本ファイルの内容を実行する

SET search_path TO calc_ecl;

-- 決算年月カラムを追加（既存行はNULL許容）
ALTER TABLE indicator_datasets
    ADD COLUMN fiscal_year_month DATE;

-- 同一決算年月のデータセットは1つだけ（NULLは制約対象外）
CREATE UNIQUE INDEX idx_indicator_datasets_fiscal_ym
    ON indicator_datasets (fiscal_year_month)
    WHERE fiscal_year_month IS NOT NULL;

COMMENT ON COLUMN indicator_datasets.fiscal_year_month
    IS '決算年月。ECLモデルの対象決算期を示す（例: 2026-03-01 = 2026年3月期）。月初日で格納';
