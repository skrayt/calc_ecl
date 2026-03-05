-- =============================================================
-- ECL将来予想モデル データベーススキーマ
-- PostgreSQL 15
-- DB名: craft  スキーマ: calc_ecl
-- 作成日: 2026-03-04
-- =============================================================

-- スキーマ作成
CREATE SCHEMA IF NOT EXISTS calc_ecl;
SET search_path TO calc_ecl;

-- =============================================================
-- 1. データソース管理
--    統計ダッシュボード等、データの出典元を管理
-- =============================================================
CREATE TABLE indicator_sources (
    source_id       SERIAL PRIMARY KEY,
    source_name     VARCHAR(100) NOT NULL,               -- 例: 'e-Stat統計ダッシュボード'
    source_url      TEXT,                                 -- 取得元URL
    description     TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  indicator_sources IS 'マクロ経済指標のデータ出典元を管理';
COMMENT ON COLUMN indicator_sources.source_name IS 'データソース名（例: e-Stat統計ダッシュボード）';

-- =============================================================
-- 2. 指標定義マスタ
--    使用する指標を定義。基準年改定時は新しいレコードとして登録。
--    例: GDP2020年基準 と GDP2025年基準 は別レコード
-- =============================================================
CREATE TABLE indicator_definitions (
    indicator_id    SERIAL PRIMARY KEY,
    indicator_code  VARCHAR(50)  NOT NULL UNIQUE,         -- 例: 'gdp_nominal_2020base'
    indicator_name  VARCHAR(200) NOT NULL,                 -- 例: '国内総生産（名目）2020年基準'
    base_year       VARCHAR(20),                           -- 基準年（例: '2020'）。基準年がない指標はNULL
    unit            VARCHAR(50),                           -- 単位（例: '%', '人', '10億円'）
    frequency       VARCHAR(20) NOT NULL                   -- データの時系列粒度
                    CHECK (frequency IN ('monthly', 'quarterly', 'calendar_year', 'fiscal_year')),
    source_id       INTEGER REFERENCES indicator_sources(source_id),
    description     TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  indicator_definitions IS '説明変数として使用するマクロ経済指標の定義マスタ';
COMMENT ON COLUMN indicator_definitions.indicator_code IS '指標コード。基準年改定時は別コードで登録（例: gdp_nominal_2020base → gdp_nominal_2025base）';
COMMENT ON COLUMN indicator_definitions.base_year IS '指標の基準年。失業率など基準年のない指標はNULL';
COMMENT ON COLUMN indicator_definitions.frequency IS 'データ粒度: monthly=月次, quarterly=四半期, calendar_year=暦年(12月締), fiscal_year=年度(3月締)';

-- =============================================================
-- 3. データセット管理
--    「いつ取得したデータ群か」を管理する単位。
--    同一データセット内で指標ごとに基準年が異なっていてもよい。
-- =============================================================
CREATE TABLE indicator_datasets (
    dataset_id      SERIAL PRIMARY KEY,
    dataset_name    VARCHAR(200) NOT NULL,                 -- 例: '2026年3月取得'
    retrieved_at    DATE NOT NULL,                          -- データ取得日
    source_id       INTEGER REFERENCES indicator_sources(source_id),
    indicator_keys  JSONB NOT NULL,                         -- 含まれる指標コード一覧
                                                            -- 例: ["unemployment_rate", "gdp_nominal_2020base"]
    description     TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  indicator_datasets IS 'データ取得回（取得時期）を管理。モデル作成時のデータ再現性を担保する';
COMMENT ON COLUMN indicator_datasets.retrieved_at IS 'データ取得日。同じ指標でも取得時期が異なれば別データセット';
COMMENT ON COLUMN indicator_datasets.indicator_keys IS 'このデータセットに含まれる指標コードのJSON配列';

-- =============================================================
-- 4. 指標データ本体
--    JSONB型で指標値を格納。説明変数の可変に対応。
-- =============================================================
CREATE TABLE indicator_data (
    data_id         BIGSERIAL PRIMARY KEY,
    dataset_id      INTEGER NOT NULL REFERENCES indicator_datasets(dataset_id),
    reference_date  DATE NOT NULL,                         -- 基準日（下記ルール参照）
    frequency       VARCHAR(20) NOT NULL
                    CHECK (frequency IN ('monthly', 'quarterly', 'calendar_year', 'fiscal_year')),
    region_code     VARCHAR(10) NOT NULL DEFAULT '00000',  -- 地域コード（全国='00000'）
    region_name     VARCHAR(50),                           -- 地域名
    indicators      JSONB NOT NULL,                        -- 指標値 例: {"unemployment_rate": 2.4, "ci_index_2020base": 114.3}
    notes           JSONB,                                 -- 注記 例: {"unemployment_rate": "速報"}
    imported_at     TIMESTAMP WITH TIME ZONE DEFAULT now(),

    UNIQUE (dataset_id, reference_date, frequency, region_code)
);

-- reference_date のルール:
--   monthly       : 月初日      (例: 2025-01-01 = 2025年1月)
--   quarterly     : 四半期初日  (例: 2025-01-01 = 2025年1-3月期)
--   calendar_year : 年初日      (例: 2025-01-01 = 2025年)
--   fiscal_year   : 年度開始日  (例: 2025-04-01 = 2025年度)

COMMENT ON TABLE  indicator_data IS 'マクロ経済指標の時系列データ本体。JSONB型で指標値を格納';
COMMENT ON COLUMN indicator_data.reference_date IS '基準日。monthly=月初, quarterly=期初, calendar_year=年初, fiscal_year=4/1';
COMMENT ON COLUMN indicator_data.indicators IS '指標値のJSONオブジェクト。キーはindicator_definitionsのindicator_codeに対応';

CREATE INDEX idx_indicator_data_indicators  ON indicator_data USING GIN (indicators);
CREATE INDEX idx_indicator_data_date        ON indicator_data (reference_date);
CREATE INDEX idx_indicator_data_dataset     ON indicator_data (dataset_id);
CREATE INDEX idx_indicator_data_freq_region ON indicator_data (frequency, region_code);

-- =============================================================
-- 5. モデル設定
--    どのデータセットのどの指標を使ってモデルを作るか管理
-- =============================================================
CREATE TABLE model_configs (
    config_id         SERIAL PRIMARY KEY,
    model_name        VARCHAR(200) NOT NULL,               -- 例: 'ECL予測モデル v1.0'
    model_type        VARCHAR(50) NOT NULL,                 -- 例: 'linear_regression', 'logistic', 'xgboost'
    dataset_id        INTEGER NOT NULL REFERENCES indicator_datasets(dataset_id),
    target_variable   VARCHAR(100) NOT NULL,                -- 目的変数（例: 'default_rate'）
    feature_variables JSONB NOT NULL,                       -- 説明変数リスト ["unemployment_rate", "gdp_nominal_2020base"]
    hyperparameters   JSONB,                                -- ハイパーパラメータ
    frequency         VARCHAR(20) NOT NULL
                      CHECK (frequency IN ('monthly', 'quarterly', 'calendar_year', 'fiscal_year')),
    region_code       VARCHAR(10) NOT NULL DEFAULT '00000',
    description       TEXT,
    is_active         BOOLEAN DEFAULT TRUE,
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at        TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  model_configs IS '将来予想モデルの設定。使用データセットと説明変数の組み合わせを定義';
COMMENT ON COLUMN model_configs.dataset_id IS '参照するデータセット。モデル作成時のデータ再現性を担保';
COMMENT ON COLUMN model_configs.feature_variables IS '説明変数の指標コード配列。indicator_datasets.indicator_keysのサブセット';

-- =============================================================
-- 6. モデル実行結果
--    学習・評価の履歴を保持
-- =============================================================
CREATE TABLE model_results (
    result_id               BIGSERIAL PRIMARY KEY,
    config_id               INTEGER NOT NULL REFERENCES model_configs(config_id),
    run_date                TIMESTAMP WITH TIME ZONE DEFAULT now(),
    training_period_start   DATE NOT NULL,                 -- 学習期間の開始
    training_period_end     DATE NOT NULL,                 -- 学習期間の終了
    metrics                 JSONB NOT NULL,                -- 評価指標 {"r2": 0.85, "rmse": 0.012, "aic": -320.5}
    coefficients            JSONB,                         -- 回帰係数 {"intercept": 0.02, "unemployment_rate": 0.15}
    model_binary            BYTEA,                         -- pickleしたモデルオブジェクト（任意）
    status                  VARCHAR(20) DEFAULT 'completed'
                            CHECK (status IN ('running', 'completed', 'failed')),
    error_message           TEXT,
    created_at              TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  model_results IS 'モデル学習・評価の実行結果履歴';
COMMENT ON COLUMN model_results.metrics IS '評価指標（R², RMSE, AIC等）のJSONオブジェクト';
COMMENT ON COLUMN model_results.coefficients IS '回帰係数等のJSONオブジェクト';
COMMENT ON COLUMN model_results.model_binary IS 'Python pickleでシリアライズしたモデルオブジェクト（任意）';

CREATE INDEX idx_model_results_config ON model_results (config_id, run_date DESC);

-- =============================================================
-- 7. 将来シナリオ・予測値
--    ベース/楽観/悲観シナリオ × 予測期間
-- =============================================================
CREATE TABLE forecast_scenarios (
    scenario_id      BIGSERIAL PRIMARY KEY,
    result_id        BIGINT NOT NULL REFERENCES model_results(result_id),
    scenario_name    VARCHAR(50) NOT NULL,                 -- 'base', 'optimistic', 'pessimistic'
    forecast_date    DATE NOT NULL,                        -- 予測対象日
    input_values     JSONB NOT NULL,                       -- シナリオごとの説明変数想定値
    predicted_value  NUMERIC(18, 8),                       -- 予測値（例: デフォルト率）
    confidence_lower NUMERIC(18, 8),                       -- 信頼区間下限
    confidence_upper NUMERIC(18, 8),                       -- 信頼区間上限
    weight           NUMERIC(5, 4) DEFAULT 1.0,            -- シナリオ加重（IFRS9用）
    created_at       TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  forecast_scenarios IS 'IFRS9準拠の将来シナリオ（ベース/楽観/悲観）と予測値';
COMMENT ON COLUMN forecast_scenarios.weight IS 'シナリオ加重。IFRS9ではベース/楽観/悲観の加重平均でECLを算出';
COMMENT ON COLUMN forecast_scenarios.input_values IS 'シナリオごとの説明変数想定値（将来のマクロ指標予測値）';

CREATE INDEX idx_forecast_scenario ON forecast_scenarios (result_id, scenario_name, forecast_date);

