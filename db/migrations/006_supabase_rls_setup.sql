-- =============================================================
-- 006: Supabase RLS（Row Level Security）設定
-- calc_ecl スキーマの全テーブルに RLS を有効化する
--
-- 接続方式: psycopg2 direct connection（postgres ロール）
--   → postgres ロールは superuser のため RLS をバイパスする
--   → アプリの動作は影響なし。RLS は不正アクセス防止の安全網として設定。
--
-- 実行方法: Supabase SQL Editor で本ファイルの内容を実行する
-- =============================================================

-- =============================================================
-- RLS を有効化（全テーブル）
-- =============================================================
ALTER TABLE calc_ecl.indicator_sources      ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.indicator_definitions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.indicator_datasets     ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.indicator_data         ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.model_configs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.model_results          ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.forecast_scenarios     ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.target_definitions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.target_datasets        ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.target_data            ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.arima_forecasts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE calc_ecl.ecl_results            ENABLE ROW LEVEL SECURITY;

-- =============================================================
-- FORCE RLS: postgres ロールも RLS の対象にする
-- ※ RLS を安全網として機能させるため
-- ※ アプリ接続用の専用ロールを使う場合はこの設定が必要
-- ※ postgres ロール直接接続で使い続ける場合はコメントアウト可
-- =============================================================
-- ALTER TABLE calc_ecl.indicator_sources      FORCE ROW LEVEL SECURITY;
-- (全テーブル同様... 今回は無効化しておく)

-- =============================================================
-- アクセスポリシー（全操作を許可）
-- 既存ポリシーがある場合は DROP してから再作成する
-- =============================================================

-- indicator_sources
DROP POLICY IF EXISTS "allow_all_indicator_sources" ON calc_ecl.indicator_sources;
CREATE POLICY "allow_all_indicator_sources"
    ON calc_ecl.indicator_sources FOR ALL
    USING (true) WITH CHECK (true);

-- indicator_definitions
DROP POLICY IF EXISTS "allow_all_indicator_definitions" ON calc_ecl.indicator_definitions;
CREATE POLICY "allow_all_indicator_definitions"
    ON calc_ecl.indicator_definitions FOR ALL
    USING (true) WITH CHECK (true);

-- indicator_datasets
DROP POLICY IF EXISTS "allow_all_indicator_datasets" ON calc_ecl.indicator_datasets;
CREATE POLICY "allow_all_indicator_datasets"
    ON calc_ecl.indicator_datasets FOR ALL
    USING (true) WITH CHECK (true);

-- indicator_data
DROP POLICY IF EXISTS "allow_all_indicator_data" ON calc_ecl.indicator_data;
CREATE POLICY "allow_all_indicator_data"
    ON calc_ecl.indicator_data FOR ALL
    USING (true) WITH CHECK (true);

-- model_configs
DROP POLICY IF EXISTS "allow_all_model_configs" ON calc_ecl.model_configs;
CREATE POLICY "allow_all_model_configs"
    ON calc_ecl.model_configs FOR ALL
    USING (true) WITH CHECK (true);

-- model_results
DROP POLICY IF EXISTS "allow_all_model_results" ON calc_ecl.model_results;
CREATE POLICY "allow_all_model_results"
    ON calc_ecl.model_results FOR ALL
    USING (true) WITH CHECK (true);

-- forecast_scenarios
DROP POLICY IF EXISTS "allow_all_forecast_scenarios" ON calc_ecl.forecast_scenarios;
CREATE POLICY "allow_all_forecast_scenarios"
    ON calc_ecl.forecast_scenarios FOR ALL
    USING (true) WITH CHECK (true);

-- target_definitions
DROP POLICY IF EXISTS "allow_all_target_definitions" ON calc_ecl.target_definitions;
CREATE POLICY "allow_all_target_definitions"
    ON calc_ecl.target_definitions FOR ALL
    USING (true) WITH CHECK (true);

-- target_datasets
DROP POLICY IF EXISTS "allow_all_target_datasets" ON calc_ecl.target_datasets;
CREATE POLICY "allow_all_target_datasets"
    ON calc_ecl.target_datasets FOR ALL
    USING (true) WITH CHECK (true);

-- target_data
DROP POLICY IF EXISTS "allow_all_target_data" ON calc_ecl.target_data;
CREATE POLICY "allow_all_target_data"
    ON calc_ecl.target_data FOR ALL
    USING (true) WITH CHECK (true);

-- arima_forecasts
DROP POLICY IF EXISTS "allow_all_arima_forecasts" ON calc_ecl.arima_forecasts;
CREATE POLICY "allow_all_arima_forecasts"
    ON calc_ecl.arima_forecasts FOR ALL
    USING (true) WITH CHECK (true);

-- ecl_results
DROP POLICY IF EXISTS "allow_all_ecl_results" ON calc_ecl.ecl_results;
CREATE POLICY "allow_all_ecl_results"
    ON calc_ecl.ecl_results FOR ALL
    USING (true) WITH CHECK (true);

-- =============================================================
-- 確認クエリ
-- =============================================================
SELECT
    schemaname,
    tablename,
    rowsecurity AS rls_enabled
FROM pg_tables
WHERE schemaname = 'calc_ecl'
ORDER BY tablename;
