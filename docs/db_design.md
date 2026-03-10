# ECL将来予想モデル データベース設計書

## 概要

IFRS9/予想信用損失(ECL)モデルの将来予想に使用するマクロ経済指標データと、
モデル設定・実行結果・将来シナリオを管理するためのデータベース設計。

- **DBMS**: PostgreSQL 15
- **DDLファイル**: `db/migrations/001_create_tables.sql`（説明変数・モデル）
- **DDLファイル**: `db/migrations/002_create_target_tables.sql`（目的変数）
- **DDLファイル**: `db/migrations/003_add_fiscal_year_month.sql`（決算年月カラム追加）
- **DDLファイル**: `db/migrations/004_create_ecl_tables.sql`（ARIMA予測・ECL結果）

---

## 設計方針

| 方針 | 内容 |
|------|------|
| 説明変数の可変性 | JSONB型で指標値を格納し、スキーマ変更なしで指標の追加・削除に対応 |
| 基準年改定への対応 | 指標定義マスタで基準年を管理。改定時は新しい指標コードとして登録 |
| データ取得時期の管理 | データセット単位で取得時期を管理し、モデル作成時のデータ再現性を担保 |
| IFRS9シナリオ対応 | ベース/楽観/悲観シナリオの加重平均でECLを算出する構造 |
| 説明変数と目的変数の分離 | 説明変数（indicator_*）と目的変数（target_*）は対称的だが独立したテーブル群で管理 |

---

## ER図

```
【説明変数（マクロ経済指標）】          【目的変数（PD/LGD/EAD）】

indicator_sources（データソース）
        │
        ▼                              target_definitions（目的変数定義マスタ）
indicator_definitions（指標定義マスタ）
        │                              target_datasets（目的変数データセット）
        │                                        │
indicator_datasets（データセット=取得回）         │
        │                                        ▼
        ▼                              target_data（目的変数データ本体 / JSONB）
indicator_data（指標データ本体 / JSONB）          │
        │                                        │
        │            ┌───────────────────────────┘
        ▼            ▼
       model_configs（モデル設定）← dataset_id + target_dataset_id
                     │
                     ▼
       model_results（モデル実行結果）
                     │
                     ▼
       forecast_scenarios（将来シナリオ・予測値）

【ECL算出】

indicator_datasets ──→ arima_forecasts（ARIMA予測結果）
                                │
model_configs ──────────────────┤
                                ▼
                        ecl_results（ECL計算結果）
```

---

## テーブル一覧

| # | テーブル名 | 区分 | 概要 |
|---|-----------|------|------|
| 1 | indicator_sources | マスタ | データ出典元（e-Stat等） |
| 2 | indicator_definitions | マスタ | 指標定義（指標コード・基準年・単位・粒度） |
| 3 | indicator_datasets | 管理 | データ取得回（取得日・含有指標一覧） |
| 4 | indicator_data | データ | 指標データ本体（JSONB格納） |
| 5 | model_configs | モデル | モデル設定（使用データセット・説明変数） |
| 6 | model_results | モデル | モデル学習・評価の実行結果 |
| 7 | forecast_scenarios | モデル | 将来シナリオと予測値 |
| 8 | target_definitions | マスタ | 目的変数定義（PD/LGD/EAD） |
| 9 | target_datasets | 管理 | 目的変数データ取得回 |
| 10 | target_data | データ | 目的変数データ本体（JSONB格納） |
| 11 | arima_forecasts | ECL | ARIMA予測結果（指標別・シナリオ別） |
| 12 | ecl_results | ECL | ECL計算結果（シナリオ加重平均） |

---

## テーブル詳細

### 1. indicator_sources（データソース管理）

統計ダッシュボード等、データの出典元を管理する。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| source_id | SERIAL | PK | |
| source_name | VARCHAR(100) | o | データソース名 |
| source_url | TEXT | | 取得元URL |
| description | TEXT | | 備考 |
| created_at | TIMESTAMPTZ | | 作成日時 |
| updated_at | TIMESTAMPTZ | | 更新日時 |

---

### 2. indicator_definitions（指標定義マスタ）

使用する指標を定義する。基準年改定時は新しいレコードとして登録する。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| indicator_id | SERIAL | PK | |
| indicator_code | VARCHAR(50) | o | 指標コード（ユニーク） |
| indicator_name | VARCHAR(200) | o | 指標名 |
| base_year | VARCHAR(20) | | 基準年（NULLあり） |
| unit | VARCHAR(50) | | 単位 |
| frequency | VARCHAR(20) | o | データ粒度（下記参照） |
| source_id | INTEGER | | FK → indicator_sources |
| description | TEXT | | 備考 |
| created_at | TIMESTAMPTZ | | 作成日時 |

**指標コードの命名規則**:
- 基準年あり: `{指標名}_{基準年}base` → `gdp_nominal_2020base`
- 基準年なし: `{指標名}` → `unemployment_rate`

**基準年改定時の対応**:
```
gdp_nominal_2020base  （旧）
gdp_nominal_2025base  （新）← 別レコードとして追加
```

---

### 3. indicator_datasets（データセット管理）

「いつ取得したデータ群か」を管理する。同一データセット内で指標ごとに基準年が異なっていてもよい。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| dataset_id | SERIAL | PK | |
| dataset_name | VARCHAR(200) | o | 例: '2026年3月取得' |
| retrieved_at | DATE | o | データ取得日 |
| fiscal_year_month | DATE | | 決算年月（月初日で格納。例: 2026-03-01 = 2026年3月期） |
| source_id | INTEGER | | FK → indicator_sources |
| indicator_keys | JSONB | o | 含有指標コード配列 |
| description | TEXT | | 備考 |
| is_active | BOOLEAN | | デフォルトTRUE |
| created_at | TIMESTAMPTZ | | 作成日時 |

**部分ユニークインデックス**: `idx_indicator_datasets_fiscal_ym`
- 対象: `fiscal_year_month`（NULLは制約対象外）
- 同一決算年月のデータセットは1つだけ存在できる
- 同じ決算年月でCSVを再インポートすると、既存データセットを削除して新規作成する（DELETE + re-INSERT）

**indicator_keys の例**:
```json
[
  "total_population",
  "unemployment_rate",
  "ci_index_2020base",
  "gdp_nominal_2020base",
  "prefectural_gdp_2015base"
]
```

---

### 4. indicator_data（指標データ本体）

JSONB型で指標値を格納する。説明変数の追加・削除はJSONキーの変更で対応。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| data_id | BIGSERIAL | PK | |
| dataset_id | INTEGER | o | FK → indicator_datasets |
| reference_date | DATE | o | 基準日 |
| frequency | VARCHAR(20) | o | データ粒度 |
| region_code | VARCHAR(10) | o | 地域コード（デフォルト'00000'） |
| region_name | VARCHAR(50) | | 地域名 |
| indicators | JSONB | o | 指標値 |
| notes | JSONB | | 注記 |
| imported_at | TIMESTAMPTZ | | インポート日時 |

**ユニーク制約**: `(dataset_id, reference_date, frequency, region_code)`

#### reference_date のルール

| frequency | reference_date | CSV上の表記例 |
|-----------|----------------|---------------|
| monthly | 月初日 | `2025年1月` → `2025-01-01` |
| quarterly | 四半期初日 | `2025年1-3月期` → `2025-01-01` |
| calendar_year | 年初日 | `2025年` → `2025-01-01` |
| fiscal_year | 年度開始日(4/1) | `2025年度` → `2025-04-01` |

#### indicators カラムの格納イメージ

```json
// 月次データ（2025年12月）
{
  "total_population": 123160000,
  "unemployment_rate": 2.4,
  "ci_index_2020base": 114.3
}

// 四半期データ（2025年10-12月期）
{
  "unemployment_rate": 2.5,
  "gdp_nominal_2020base": 173798.7
}

// 年度データ（2022年度） — 基準年が混在する例
{
  "unemployment_rate": 2.6,
  "gdp_nominal_2020base": 591651.3,
  "prefectural_gdp_2015base": 595788788
}
```

#### インデックス

| インデックス名 | 対象 | 種別 |
|---------------|------|------|
| idx_indicator_data_indicators | indicators | GIN（JSONB検索用） |
| idx_indicator_data_date | reference_date | B-tree |
| idx_indicator_data_dataset | dataset_id | B-tree |
| idx_indicator_data_freq_region | (frequency, region_code) | B-tree |

---

### 5. model_configs（モデル設定）

どのデータセットのどの指標を使ってモデルを作るかを定義する。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| config_id | SERIAL | PK | |
| model_name | VARCHAR(200) | o | モデル名 |
| model_type | VARCHAR(50) | o | モデル種別（linear_regression等） |
| dataset_id | INTEGER | o | FK → indicator_datasets |
| target_variable | VARCHAR(100) | o | 目的変数 |
| feature_variables | JSONB | o | 説明変数コード配列 |
| hyperparameters | JSONB | | ハイパーパラメータ |
| frequency | VARCHAR(20) | o | 使用データ粒度 |
| region_code | VARCHAR(10) | o | 対象地域 |
| description | TEXT | | 備考 |
| is_active | BOOLEAN | | デフォルトTRUE |
| created_at | TIMESTAMPTZ | | 作成日時 |
| updated_at | TIMESTAMPTZ | | 更新日時 |

---

### 6. model_results（モデル実行結果）

学習・評価の履歴を保持する。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| result_id | BIGSERIAL | PK | |
| config_id | INTEGER | o | FK → model_configs |
| run_date | TIMESTAMPTZ | | 実行日時 |
| training_period_start | DATE | o | 学習期間開始 |
| training_period_end | DATE | o | 学習期間終了 |
| metrics | JSONB | o | 評価指標（R², RMSE, AIC等） |
| coefficients | JSONB | | 回帰係数等 |
| model_binary | BYTEA | | pickleしたモデルオブジェクト |
| status | VARCHAR(20) | | running / completed / failed |
| error_message | TEXT | | エラー時のメッセージ |
| created_at | TIMESTAMPTZ | | 作成日時 |

---

### 7. forecast_scenarios（将来シナリオ・予測値）

IFRS9準拠のベース/楽観/悲観シナリオと予測値を管理する。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| scenario_id | BIGSERIAL | PK | |
| result_id | BIGINT | o | FK → model_results |
| scenario_name | VARCHAR(50) | o | base / optimistic / pessimistic |
| forecast_date | DATE | o | 予測対象日 |
| input_values | JSONB | o | シナリオごとの説明変数想定値 |
| predicted_value | NUMERIC(18,8) | | 予測値 |
| confidence_lower | NUMERIC(18,8) | | 信頼区間下限 |
| confidence_upper | NUMERIC(18,8) | | 信頼区間上限 |
| weight | NUMERIC(5,4) | | シナリオ加重（デフォルト1.0） |
| created_at | TIMESTAMPTZ | | 作成日時 |

---

### 8. target_definitions（目的変数定義マスタ）

PD（デフォルト率）・LGD（損失率）・EAD（エクスポージャー）等の目的変数を定義する。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| target_id | SERIAL | PK | |
| target_code | VARCHAR(50) | o | 目的変数コード（ユニーク） |
| target_name | VARCHAR(200) | o | 日本語名（例: 法人PD） |
| target_type | VARCHAR(20) | o | pd / lgd / ead（CHECK制約） |
| unit | VARCHAR(50) | | 単位（例: %） |
| frequency | VARCHAR(20) | o | データ粒度 |
| description | TEXT | | 備考 |
| created_at | TIMESTAMPTZ | | 作成日時 |

---

### 9. target_datasets（目的変数データセット管理）

目的変数のデータ取得回を管理する。indicator_datasetsと対称的な構造。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| target_dataset_id | SERIAL | PK | |
| dataset_name | VARCHAR(200) | o | 例: '2026年3月 法人PD実績' |
| retrieved_at | DATE | o | データ取得日 |
| target_keys | JSONB | o | 含有目的変数コード配列 |
| description | TEXT | | 備考 |
| is_active | BOOLEAN | | デフォルトTRUE |
| created_at | TIMESTAMPTZ | | 作成日時 |

---

### 10. target_data（目的変数データ本体）

JSONB型で目的変数値を格納する。indicator_dataのregion_codeに対応するsegment_codeでセグメント（法人/個人等）を区分する。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| data_id | BIGSERIAL | PK | |
| target_dataset_id | INTEGER | o | FK → target_datasets |
| reference_date | DATE | o | 基準日（indicator_dataと同じルール） |
| frequency | VARCHAR(20) | o | データ粒度 |
| segment_code | VARCHAR(50) | o | セグメントコード（デフォルト'all'） |
| segment_name | VARCHAR(100) | | セグメント名 |
| targets | JSONB | o | 目的変数値 |
| notes | JSONB | | 注記 |
| imported_at | TIMESTAMPTZ | | インポート日時 |

**ユニーク制約**: `(target_dataset_id, reference_date, frequency, segment_code)`

#### targets カラムの格納イメージ

```json
// 年度データ（2022年度・法人セグメント）
{
  "pd_corporate": 0.0234,
  "lgd_corporate": 0.45
}
```

#### インデックス

| インデックス名 | 対象 | 種別 |
|---------------|------|------|
| idx_target_data_targets | targets | GIN（JSONB検索用） |
| idx_target_data_date | reference_date | B-tree |
| idx_target_data_dataset | target_dataset_id | B-tree |
| idx_target_data_freq_seg | (frequency, segment_code) | B-tree |

---

### 11. arima_forecasts（ARIMA予測結果）

ARIMAモデルで生成した指標別・シナリオ別の将来予測値を保存する。ECL計算タブで参照する。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| forecast_id | SERIAL | PK | |
| indicator_code | VARCHAR(100) | o | 指標コード（indicator_definitions.indicator_code と対応） |
| dataset_id | INTEGER | | FK → indicator_datasets（NULLは未紐付け） |
| frequency | VARCHAR(20) | o | データ粒度 |
| arima_order | VARCHAR(20) | o | 次数文字列（例: `(1,1,0)`） |
| forecast_steps | INTEGER | o | 予測ステップ数 |
| forecast_data | JSONB | o | 予測結果（下記参照） |
| scenario_label | VARCHAR(50) | | シナリオラベル（base / upside / downside 等） |
| note | TEXT | | メモ |
| created_at | TIMESTAMPTZ | | 作成日時 |

**forecast_data の格納イメージ**:
```json
{
  "index":    ["2026-04-01", "2027-04-01", "2028-04-01"],
  "forecast": [2.4, 2.5, 2.6],
  "lower":    [1.8, 1.7, 1.6],
  "upper":    [3.0, 3.3, 3.6]
}
```
- `forecast`: モデル中心予測値（ベースシナリオ）
- `lower`: 95%信頼区間下限（楽観シナリオの参考値）
- `upper`: 95%信頼区間上限（悲観シナリオの参考値）

---

### 12. ecl_results（ECL計算結果）

シナリオ加重平均によるECL計算結果を保存する。

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| ecl_id | SERIAL | PK | |
| model_config_id | INTEGER | | FK → model_configs |
| target_dataset_id | INTEGER | | FK → target_datasets |
| segment_code | VARCHAR(50) | o | セグメントコード（デフォルト'all'） |
| target_code | VARCHAR(100) | o | 目的変数コード（例: pd_corporate） |
| fiscal_year_month | DATE | | 決算年月 |
| weight_base | NUMERIC(5,4) | o | ベースシナリオウェイト（合計が1.0になること） |
| weight_upside | NUMERIC(5,4) | o | 楽観シナリオウェイト |
| weight_downside | NUMERIC(5,4) | o | 悲観シナリオウェイト |
| results | JSONB | o | 計算結果（下記参照） |
| note | TEXT | | メモ |
| created_at | TIMESTAMPTZ | | 作成日時 |

**results の格納イメージ**:
```json
{
  "2026-04-01": {
    "pd_base": 0.023,
    "pd_upside": 0.018,
    "pd_downside": 0.031,
    "pd_weighted": 0.024,
    "lgd": 0.45,
    "ecl_rate": 0.0108,
    "ecl_amount": 1080000
  }
}
```

---

### model_configs への追加カラム

| カラム | 型 | 必須 | 説明 |
|--------|-----|------|------|
| target_dataset_id | INTEGER | | FK → target_datasets。目的変数データとの紐付け |

---

## データの流れ

```
【説明変数】                              【目的変数】
1. 統計ダッシュボードからCSVダウンロード   1. PD/LGD実績データをCSV準備
        ↓                                        ↓
2. indicator_datasets に取得回を登録       2. target_datasets に取得回を登録
        ↓                                        ↓
3. CSVパース→indicator_dataへINSERT        3. CSVパース→target_dataへINSERT
        ↓                                        ↓
        └────────────┬───────────────────────────┘
                     ↓
4. model_configs でモデル設定を定義
   （dataset_id + target_dataset_id で紐付け）
                     ↓
5. Python でモデル学習 → model_results に結果保存
                     ↓
6. シナリオ別に将来予測 → forecast_scenarios に保存
                     ↓
7. 加重平均でECL算出
```

---

## 運用例

### 年次でのデータ更新・モデル再作成

```
■ 2026年3月 初回モデル作成
  dataset: "2026年3月取得"
    indicator_keys: ["unemployment_rate", "gdp_nominal_2020base",
                     "ci_index_2020base", "prefectural_gdp_2015base"]
  model_config → dataset_id = 1

■ 2027年3月 データ更新＋モデル再作成
  dataset: "2027年3月取得"
    indicator_keys: ["unemployment_rate", "gdp_nominal_2025base",  ← 基準年改定
                     "ci_index_2020base", "consumer_price_index"]  ← 指標入替
  model_config → dataset_id = 2
  ※ 旧データセット(id=1)は残るため、過去モデルの再現が可能
```
