-- =============================================================
-- Phase 5: ECL算出機能 追加テーブル
-- PostgreSQL 15
-- =============================================================

SET search_path TO calc_ecl;

-- =============================================================
-- ARIMA予測結果
-- ARIMAページで実行した予測結果をDBに保存する
-- =============================================================
CREATE TABLE arima_forecasts (
    forecast_id         SERIAL PRIMARY KEY,
    indicator_code      VARCHAR(100) NOT NULL,               -- 対象指標コード
    dataset_id          INTEGER REFERENCES indicator_datasets(dataset_id),
    frequency           VARCHAR(20) NOT NULL DEFAULT '',     -- monthly / quarterly / fiscal_year 等
    arima_order         VARCHAR(20) NOT NULL,                -- 例: '(1,1,0)'
    forecast_steps      INTEGER NOT NULL,                    -- 予測期間数
    forecast_data       JSONB NOT NULL,
    -- 例: {"index": ["2026-04-01", "2027-04-01"], "forecast": [2.5, 2.6],
    --       "lower": [2.0, 2.0], "upper": [3.0, 3.2]}
    scenario_label      VARCHAR(50) DEFAULT '',              -- 例: 'ベースシナリオ2026'
    note                TEXT DEFAULT '',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  arima_forecasts IS 'ARIMAページで実行した将来予測結果の保存先';
COMMENT ON COLUMN arima_forecasts.arima_order IS 'ARIMA次数の文字列表現（例: "(1,1,0)"）';
COMMENT ON COLUMN arima_forecasts.forecast_data IS '予測データJSON: {index, forecast, lower, upper} の各リスト';

CREATE INDEX idx_arima_forecasts_code ON arima_forecasts (indicator_code, created_at DESC);

-- =============================================================
-- ECL計算結果
-- ECL計算タブで算出した結果をDBに保存する
-- =============================================================
CREATE TABLE ecl_results (
    ecl_id              SERIAL PRIMARY KEY,
    model_config_id     INTEGER REFERENCES model_configs(config_id),
    target_dataset_id   INTEGER REFERENCES target_datasets(target_dataset_id),
    segment_code        VARCHAR(50) NOT NULL DEFAULT 'all',
    target_code         VARCHAR(100) NOT NULL,               -- 例: 'pd_corporate'
    fiscal_year_month   DATE,                                 -- 計算対象の決算年月
    weight_base         NUMERIC(5,4) NOT NULL,               -- ベースシナリオウェイト（例: 0.6）
    weight_upside       NUMERIC(5,4) NOT NULL,               -- 楽観シナリオウェイト（例: 0.2）
    weight_downside     NUMERIC(5,4) NOT NULL,               -- 悲観シナリオウェイト（例: 0.2）
    results             JSONB NOT NULL,
    -- 例: [{"period": "2026年度", "pd_base": 0.023, "pd_upside": 0.019,
    --        "pd_downside": 0.031, "pd_weighted": 0.024,
    --        "lgd": 0.45, "ecl_rate": 0.0108, "ecl_amount": null}]
    note                TEXT DEFAULT '',
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  ecl_results IS 'ECL計算タブで算出したECL計算結果の保存先';
COMMENT ON COLUMN ecl_results.results IS '計算結果JSON配列: 期間別のPD/LGD/ECL値';

CREATE INDEX idx_ecl_results_model ON ecl_results (model_config_id, created_at DESC);
