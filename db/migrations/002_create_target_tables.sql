-- =============================================================
-- 目的変数（PD/LGD/EAD）データ管理テーブル
-- PostgreSQL 15
-- DB名: craft  スキーマ: calc_ecl
-- 作成日: 2026-03-05
--
-- 説明変数（indicator_*）と対称的だが独立した構造。
-- モデル構築対象: PD（デフォルト率）、LGD（損失率）
-- 将来対応: EAD（エクスポージャー）
-- =============================================================

SET search_path TO calc_ecl;

-- =============================================================
-- 1. 目的変数定義マスタ
--    PD/LGD/EAD等の目的変数を定義。
--    セグメント×指標タイプの組み合わせで管理。
-- =============================================================
CREATE TABLE target_definitions (
    target_id       SERIAL PRIMARY KEY,
    target_code     VARCHAR(50)  NOT NULL UNIQUE,          -- 例: 'pd_corporate', 'lgd_mortgage'
    target_name     VARCHAR(200) NOT NULL,                  -- 例: '法人PD', '住宅ローンLGD'
    target_type     VARCHAR(20)  NOT NULL                   -- 目的変数の種類
                    CHECK (target_type IN ('pd', 'lgd', 'ead')),
    unit            VARCHAR(50),                            -- 単位（例: '%', '率'）
    frequency       VARCHAR(20)  NOT NULL                   -- データの時系列粒度
                    CHECK (frequency IN ('monthly', 'quarterly', 'calendar_year', 'fiscal_year')),
    description     TEXT,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  target_definitions IS '目的変数（PD/LGD/EAD）の定義マスタ';
COMMENT ON COLUMN target_definitions.target_code IS '目的変数コード（例: pd_corporate, lgd_mortgage）';
COMMENT ON COLUMN target_definitions.target_type IS '目的変数の種類: pd=デフォルト率, lgd=損失率, ead=エクスポージャー';
COMMENT ON COLUMN target_definitions.frequency IS 'データ粒度: monthly=月次, quarterly=四半期, calendar_year=暦年(12月締), fiscal_year=年度(3月締)';

-- =============================================================
-- 2. 目的変数データセット管理
--    「いつ取得したデータ群か」を管理する単位。
--    indicator_datasetsと対称的な構造。
-- =============================================================
CREATE TABLE target_datasets (
    target_dataset_id SERIAL PRIMARY KEY,
    dataset_name      VARCHAR(200) NOT NULL,                -- 例: '2026年3月 法人PD実績'
    retrieved_at      DATE NOT NULL,                         -- データ取得日
    target_keys       JSONB NOT NULL,                        -- 含まれる目的変数コード一覧
                                                             -- 例: ["pd_corporate", "lgd_corporate"]
    description       TEXT,
    is_active         BOOLEAN DEFAULT TRUE,
    created_at        TIMESTAMP WITH TIME ZONE DEFAULT now()
);

COMMENT ON TABLE  target_datasets IS '目的変数のデータ取得回を管理。モデル作成時のデータ再現性を担保';
COMMENT ON COLUMN target_datasets.retrieved_at IS 'データ取得日';
COMMENT ON COLUMN target_datasets.target_keys IS 'このデータセットに含まれる目的変数コードのJSON配列';

-- =============================================================
-- 3. 目的変数データ本体
--    JSONB型で目的変数値を格納。
--    indicator_dataのregion_codeに対応するsegment_codeで
--    セグメント（法人/個人/住宅ローン等）を区分。
-- =============================================================
CREATE TABLE target_data (
    data_id            BIGSERIAL PRIMARY KEY,
    target_dataset_id  INTEGER NOT NULL REFERENCES target_datasets(target_dataset_id),
    reference_date     DATE NOT NULL,                        -- 基準日（indicator_dataと同じルール）
    frequency          VARCHAR(20) NOT NULL
                       CHECK (frequency IN ('monthly', 'quarterly', 'calendar_year', 'fiscal_year')),
    segment_code       VARCHAR(50) NOT NULL DEFAULT 'all',   -- セグメントコード（例: corporate, retail_mortgage）
    segment_name       VARCHAR(100),                          -- セグメント名（例: 法人, 住宅ローン）
    targets            JSONB NOT NULL,                        -- 目的変数値 例: {"pd_corporate": 0.0234, "lgd_corporate": 0.45}
    notes              JSONB,                                 -- 注記
    imported_at        TIMESTAMP WITH TIME ZONE DEFAULT now(),

    UNIQUE (target_dataset_id, reference_date, frequency, segment_code)
);

-- reference_date のルール（indicator_dataと同一）:
--   monthly       : 月初日      (例: 2025-01-01 = 2025年1月)
--   quarterly     : 四半期初日  (例: 2025-01-01 = 2025年1-3月期)
--   calendar_year : 年初日      (例: 2025-01-01 = 2025年)
--   fiscal_year   : 年度開始日  (例: 2025-04-01 = 2025年度)

COMMENT ON TABLE  target_data IS '目的変数（PD/LGD/EAD）の時系列データ本体。JSONB型で格納';
COMMENT ON COLUMN target_data.reference_date IS '基準日。monthly=月初, quarterly=期初, calendar_year=年初, fiscal_year=4/1';
COMMENT ON COLUMN target_data.segment_code IS 'セグメントコード。全体の場合はall。例: corporate, retail_mortgage';
COMMENT ON COLUMN target_data.targets IS '目的変数値のJSONオブジェクト。キーはtarget_definitionsのtarget_codeに対応';

CREATE INDEX idx_target_data_targets   ON target_data USING GIN (targets);
CREATE INDEX idx_target_data_date      ON target_data (reference_date);
CREATE INDEX idx_target_data_dataset   ON target_data (target_dataset_id);
CREATE INDEX idx_target_data_freq_seg  ON target_data (frequency, segment_code);

-- =============================================================
-- 4. model_configsに目的変数データセット参照を追加
--    既存のtarget_variable（文字列）に加え、
--    実データへの紐付けを可能にする。
-- =============================================================
ALTER TABLE model_configs
    ADD COLUMN target_dataset_id INTEGER REFERENCES target_datasets(target_dataset_id);

COMMENT ON COLUMN model_configs.target_dataset_id IS '目的変数のデータセットID。target_datasetsへの外部キー';
