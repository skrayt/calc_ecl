# ECL将来予想モデル 実装計画

## 概要

IFRS9/ECLモデルの将来予想に必要な統計分析機能をFlet GUIアプリとして実装する。
Craft_RegressionAnalysis（`../Craft_RegressionAnalysis/`）の統計分析ロジックを
UI非依存の形で抽出・再利用し、UIはFletで新規構築する。

**本番環境: WinPython64-3.12.4.1（オフライン）**
- psycopg2はwheelファイルを持ち込んでインストール
- statsmodels, scikit-learn, numpy, scipy, pandas, matplotlib, flet: WinPython同梱済み

---

## 進捗状況

| Phase | 内容 | 状態 |
|-------|------|------|
| Phase 1 | 基盤更新（requirements, CLAUDE.md） | **完了** |
| Phase 2-1 | indicator_loader（DB→DataFrame） | **完了** |
| Phase 2-2 | data_transform（データ変換） | **完了** |
| Phase 2-3 | correlation（相関分析・VIF） | **完了** |
| Phase 2-4 | regression（OLS回帰） | **完了** |
| Phase 2-5 | model_selection（組み合わせ探索） | **完了** |
| Phase 2-6 | arima（ARIMA時系列モデル） | **完了** |
| Phase 3 | Flet GUIアプリ構築（タブ①〜⑦） | **完了** |
| Phase 4 | ドキュメント更新 | **完了** |
| Phase 5-1 | DB拡張（ARIMA予測結果・モデル確定テーブル） | **未着手** |
| Phase 5-2 | src/analysis/ecl.py（ECL計算コアロジック） | **未着手** |
| Phase 5-3 | src/db_operations.py 拡張 | **未着手** |
| Phase 5-4 | ARIMAタブ拡張（予測結果の保存機能） | **未着手** |
| Phase 5-5 | page_model_confirm.py（⑦モデル確定タブ） | **未着手** |
| Phase 5-6 | page_ecl.py（⑧ECL計算タブ） | **未着手** |
| Phase 5-7 | ドキュメント更新（Phase 5完了後） | **未着手** |

---

## タブ設計の基本方針（案B: 段階的保存方式）

ECL算出に至る「分析 → 確定 → 計算」の3段階を、それぞれ独立したタブで担当する。
各段階の作業は更新頻度・担当者が異なるため、疎結合に設計する。

```
分析フェーズ（タブ①〜⑥）
  │  CSVインポート → 相関・回帰・モデル選択 → ARIMA予測
  │  ↓ 「このモデルで行く」と決定
確定フェーズ（タブ⑦）
  │  回帰モデルをDBに保存（model_configs / model_results）
  │  ARIMA予測結果をDBに保存（arima_forecasts）
  │  ↓ 保存済みデータが揃ったら
計算フェーズ（タブ⑧）
  └─ 保存済みモデル + 保存済みARIMA予測 → 3シナリオ → ECL
```

**各タブの更新頻度イメージ（年次運用）:**

| タブ | 毎年更新 | 数年に1回 |
|------|---------|---------|
| ①〜⑤ 分析系 | 探索的に使用 | — |
| ⑥ ARIMA | **毎年**: 最新データで予測し直す | — |
| ⑦ モデル確定 | 必要時のみ再登録 | モデル改定時 |
| ⑧ ECL計算 | **毎年**: ARIMA更新後に再計算 | — |

---

## 最終的なディレクトリ構成

```
calc_ecl/
├── main.py                        ← Fletアプリ エントリポイント
├── requirements.txt
├── CLAUDE.md
├── config/
│   ├── db.py                      ← DB接続（psycopg2 + configparser）
│   ├── db.ini.example
│   └── db.ini                     ← .gitignore対象
├── src/
│   ├── import_indicators.py       ← 説明変数CSVインポートスクリプト
│   ├── import_targets.py          ← 目的変数CSVインポートスクリプト
│   ├── db_operations.py           ← model_configs等へのDB保存（Phase 5-3で拡張）
│   ├── data/
│   │   └── indicator_loader.py    ← DB→DataFrame変換
│   └── analysis/                   ← 統計分析コアロジック（UI非依存）
│       ├── __init__.py
│       ├── data_transform.py      ← データ変換（対数・差分・標準化等）
│       ├── correlation.py         ← 相関分析・VIF
│       ├── regression.py          ← OLS回帰・評価指標
│       ├── model_selection.py     ← 説明変数の組み合わせ探索
│       ├── arima.py               ← ARIMA時系列モデル
│       └── ecl.py                 ← ECL計算コアロジック（Phase 5-2で新規追加）
├── pages/                          ← Flet UIページ
│   ├── page_data_view.py          ← ① データ閲覧・確認
│   ├── page_correlation.py        ← ② 相関分析・VIF表示
│   ├── page_regression.py         ← ③ 回帰分析
│   ├── page_model_selection.py    ← ④ モデル選択
│   ├── page_dynamic_regression.py ← ⑤ 動的回帰
│   ├── page_arima.py              ← ⑥ ARIMA分析（Phase 5-4で予測保存機能を追加）
│   ├── page_model_confirm.py      ← ⑦ モデル確定（Phase 5-5で新規追加）
│   └── page_ecl.py                ← ⑧ ECL計算（Phase 5-6で新規追加、page_forecast.pyを置換）
├── components/                     ← 再利用UIパーツ
│   ├── variable_selector.py       ← 変数選択チェックボックス
│   ├── plot_utils.py              ← matplotlib→base64変換
│   ├── data_source_selector.py    ← データソース選択UI
│   └── help_panel.py              ← 折りたたみ式ヘルプパネル
├── db/
│   ├── migrations/
│   │   ├── 001_create_tables.sql              ← 説明変数・モデル系テーブル
│   │   ├── 002_create_target_tables.sql       ← 目的変数テーブル
│   │   ├── 003_add_fiscal_year_month.sql      ← 決算年月カラム追加
│   │   └── 004_create_ecl_tables.sql          ← ECL計算用テーブル（Phase 5-1で追加）
│   └── seeds/
├── docs/
│   ├── implementation_plan.md     ← 本ファイル
│   ├── system_manual.md
│   ├── operation_manual.md
│   ├── interpretation_manual.md   ← 統計結果解釈ガイド
│   ├── db_design.md
│   └── NotebookLM/
└── indicator/                      ← 統計ダッシュボードCSV
```

---

## Phase 1〜4: 完了済み（詳細省略）

Phase 1〜4はすべて完了。以下の成果物が存在する。

- `src/analysis/` 以下: data_transform, correlation, regression, model_selection, arima
- `pages/` 以下: page_data_view, page_correlation, page_regression, page_model_selection,
  page_dynamic_regression, page_arima, page_forecast（プレースホルダ）
- `docs/`: system_manual, operation_manual, interpretation_manual, db_design

---

## Phase 5: ECL算出機能の実装

### 全体構成

```
Phase 5-1: DB拡張
  └─ 004_create_ecl_tables.sql
       ├─ arima_forecasts          ← ARIMA予測結果の保存先
       └─ ecl_results              ← ECL計算結果の保存先
       ※ model_configs / model_results は既存テーブルをそのまま利用

Phase 5-2: src/analysis/ecl.py（新規）
  └─ ECL計算の純粋な数値ロジック（UI非依存）

Phase 5-3: src/db_operations.py 拡張
  └─ モデル・ARIMA予測・ECL結果のDB保存/読込関数を追加

Phase 5-4: page_arima.py 拡張
  └─ 「ARIMA予測結果を保存」ボタンを追加

Phase 5-5: page_model_confirm.py（新規）
  └─ ⑦ モデル確定タブ

Phase 5-6: page_ecl.py（新規）
  └─ ⑧ ECL計算タブ（page_forecast.py を置換）

Phase 5-7: ドキュメント更新
```

---

### 5-1. DB拡張 — `db/migrations/004_create_ecl_tables.sql`

#### 新規テーブル: `arima_forecasts`

ARIMAで予測した説明変数・目的変数の将来値を保存する。
1回の「予測セッション」が1レコードに対応する。

```sql
CREATE TABLE arima_forecasts (
    forecast_id         SERIAL PRIMARY KEY,
    indicator_code      VARCHAR(100) NOT NULL,   -- 予測対象の指標コード（例: unemployment_rate）
    dataset_id          INTEGER REFERENCES indicator_datasets(dataset_id),
    frequency           VARCHAR(20) NOT NULL,    -- monthly / quarterly / fiscal_year 等
    arima_order         VARCHAR(20) NOT NULL,    -- "(p,d,q)" 形式の文字列
    forecast_steps      INTEGER NOT NULL,        -- 予測期間数
    forecast_data       JSONB NOT NULL,          -- {日付: {forecast, lower, upper}, ...}
    scenario_label      VARCHAR(50),             -- "base" / "upside" / "downside"（任意）
    note                TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**forecast_dataのJSONB構造:**

```json
{
  "2026-04-01": {"forecast": 3.1, "lower": 2.5, "upper": 3.7},
  "2027-04-01": {"forecast": 3.3, "lower": 2.4, "upper": 4.2},
  "2028-04-01": {"forecast": 3.5, "lower": 2.2, "upper": 4.8}
}
```

#### 新規テーブル: `ecl_results`

ECL計算の最終結果を保存する。

```sql
CREATE TABLE ecl_results (
    ecl_id              SERIAL PRIMARY KEY,
    model_config_id     INTEGER REFERENCES model_configs(config_id),
    target_dataset_id   INTEGER REFERENCES target_datasets(target_dataset_id),
    segment_code        VARCHAR(50) NOT NULL DEFAULT 'all',
    target_code         VARCHAR(100) NOT NULL,   -- pd_corporate 等
    fiscal_year_month   DATE,                    -- 対象決算期
    weight_base         NUMERIC(5,4) NOT NULL,   -- ベースシナリオウェイト（例: 0.60）
    weight_upside       NUMERIC(5,4) NOT NULL,   -- 楽観シナリオウェイト
    weight_downside     NUMERIC(5,4) NOT NULL,   -- 悲観シナリオウェイト
    results             JSONB NOT NULL,           -- シナリオ別・期間別の計算結果
    note                TEXT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**resultsのJSONB構造:**

```json
{
  "periods": ["2026-04-01", "2027-04-01", "2028-04-01"],
  "base":     {"pd": [0.023, 0.025, 0.026], "lgd": [0.45, 0.46, 0.46]},
  "upside":   {"pd": [0.019, 0.020, 0.021], "lgd": [0.43, 0.43, 0.44]},
  "downside": {"pd": [0.031, 0.035, 0.038], "lgd": [0.48, 0.50, 0.51]},
  "weighted_pd":  [0.024, 0.026, 0.027],
  "weighted_lgd": [0.45, 0.46, 0.46]
}
```

#### 既存テーブルの利用

| テーブル | Phase 5での利用方法 |
|---------|-----------------|
| `model_configs` | ⑦モデル確定タブからINSERT。使用変数・変換設定を記録 |
| `model_results` | モデル評価指標（R²・AIC等）を保存 |
| `forecast_scenarios` | （利用しない。ecl_resultsで代替） |

---

### 5-2. `src/analysis/ecl.py` — ECL計算コアロジック（新規）

UIに依存しない純粋なECL計算関数群。

```python
def apply_model_to_forecast(
    model_result: dict,
    forecast_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    確定済み回帰モデルにARIMA予測値を代入し、PD/LGD予測値を計算する。

    Parameters
    ----------
    model_result : dict
        fit_ols() / fit_arima() の戻り値。
        model_result["model"] = statsmodels OLS結果オブジェクト
    forecast_df : pd.DataFrame
        説明変数の予測値DataFrame。カラム = 説明変数名、インデックス = 将来日付
        ※ 各シナリオ（base/lower/upper）ごとに呼び出す

    Returns
    -------
    pd.DataFrame
        カラム: predicted（予測値）
        インデックス: 将来日付
    """

def calc_weighted_ecl(
    base_pd: pd.Series,
    upside_pd: pd.Series,
    downside_pd: pd.Series,
    base_lgd: pd.Series,
    upside_lgd: pd.Series,
    downside_lgd: pd.Series,
    weight_base: float,
    weight_upside: float,
    weight_downside: float,
) -> dict:
    """
    3シナリオの加重平均でECL期待値を計算する。

    Returns
    -------
    dict
        キー:
        - weighted_pd: 加重平均PD（Series）
        - weighted_lgd: 加重平均LGD（Series）
        - weighted_ecl_rate: 加重平均ECL率 = weighted_pd × weighted_lgd（Series）
          ※ EADは外部から受け取り、最終的な金額換算は呼び出し元で行う
    """

def build_scenario_forecast(
    arima_forecasts: dict[str, pd.DataFrame],
    scenario: str,
) -> pd.DataFrame:
    """
    説明変数ごとのARIMA予測結果から、指定シナリオの説明変数DataFrameを組み立てる。

    Parameters
    ----------
    arima_forecasts : dict
        {指標コード: forecast()の戻り値DataFrame(forecast/lower/upper列)}
    scenario : str
        "base" → forecast列, "upside" → lower列, "downside" → upper列

    Returns
    -------
    pd.DataFrame
        カラム = 指標コード、インデックス = 将来日付
    """
```

---

### 5-3. `src/db_operations.py` 拡張

既存ファイルに以下の関数を追加する。

```python
# --- モデル確定 ---

def save_model_config(config_dict: dict) -> int:
    """
    model_configsにモデル設定を保存し、config_idを返す。

    config_dict のキー:
      dataset_id, target_dataset_id, target_code, segment_code,
      frequency, feature_cols (list), transform_settings (dict),
      lag_settings (dict), note
    """

def save_model_result(config_id: int, result_dict: dict) -> int:
    """
    model_resultsにOLS評価指標を保存する。

    result_dict のキー:
      r2, adj_r2, aic, bic, dw, f_stat, f_pvalue,
      coefficients (dict: {variable: {coef, std_err, t_stat, p_value}}),
      nobs
    """

def load_model_configs() -> pd.DataFrame:
    """保存済みモデル設定の一覧をDataFrameで返す"""

def load_model_result(config_id: int) -> dict:
    """指定config_idのモデル結果を返す"""

# --- ARIMA予測結果 ---

def save_arima_forecast(forecast_dict: dict) -> int:
    """
    arima_forecastsにARIMA予測結果を保存し、forecast_idを返す。

    forecast_dict のキー:
      indicator_code, dataset_id, frequency, arima_order,
      forecast_steps, forecast_data (dict), scenario_label, note
    """

def load_arima_forecasts(indicator_code: str = None) -> pd.DataFrame:
    """保存済みARIMA予測一覧を返す。indicator_codeで絞り込み可"""

def load_arima_forecast_data(forecast_id: int) -> pd.DataFrame:
    """指定forecast_idの予測値をDataFrame（forecast/lower/upper列）で返す"""

# --- ECL計算結果 ---

def save_ecl_result(ecl_dict: dict) -> int:
    """ecl_resultsにECL計算結果を保存し、ecl_idを返す"""

def load_ecl_results() -> pd.DataFrame:
    """保存済みECL計算結果の一覧を返す"""
```

---

### 5-4. `pages/page_arima.py` 拡張

既存のARIMAタブに「予測結果を保存」セクションを追加する。

**追加するUI要素:**

```
────────────────────────────────────────
 予測結果の保存
────────────────────────────────────────
 指標コード    : [unemployment_rate    ]  ← 自動入力（選択中の変数から）
 シナリオラベル: [base / 任意入力      ]  ← オプション
 メモ          : [                     ]
 [予測結果をDBに保存]
────────────────────────────────────────
```

**保存の流れ:**
1. ARIMA予測（`forecast()`）を実行済みであることを確認
2. `save_arima_forecast()` を呼び出し、`arima_forecasts` テーブルに保存
3. 保存完了メッセージを表示し、`forecast_id` を表示する

**設計上の注意:**
- 1回の予測実行 = 1レコード（forecast/lower/upperをまとめて1件として保存）
- シナリオラベルは任意。付けない場合は後でECL計算タブで振り分ける

---

### 5-5. `pages/page_model_confirm.py` — ⑦ モデル確定タブ（新規）

確定した回帰モデル（③回帰分析または⑤動的回帰で精査したもの）をDBに登録する専用タブ。

**UI構成:**

```
────────────────────────────────────────
 データソース選択（DataSourceSelectorを再利用）
────────────────────────────────────────
 目的変数・説明変数の選択（VariableSelectorを再利用）
────────────────────────────────────────
 モデル設定
  ラグ設定    : [変数ごとに入力]
  変換設定    : [変数ごとに選択]
  メモ        : [               ]
────────────────────────────────────────
 [回帰を実行して確認]
────────────────────────────────────────
 回帰結果プレビュー（fit_ols()の結果を表示）
  Adj.R²: 0.73 | AIC: -45.3 | DW: 1.87
  係数テーブル（variable / coef / p_value）
────────────────────────────────────────
 [このモデルをDBに保存]
────────────────────────────────────────
 保存済みモデル一覧
  config_id | 目的変数 | 説明変数 | Adj.R² | 保存日 | [削除]
────────────────────────────────────────
```

**保存の流れ:**
1. DataSourceSelector・VariableSelectorで変数・設定を選択
2. 「回帰を実行して確認」→ `fit_ols()` でプレビュー表示
3. 「このモデルをDBに保存」→ `save_model_config()` + `save_model_result()` を実行
4. 保存済みモデル一覧を更新表示

---

### 5-6. `pages/page_ecl.py` — ⑧ ECL計算タブ（新規）

保存済みの回帰モデルとARIMA予測を組み合わせ、3シナリオでECLを計算する。
現在の `page_forecast.py` を置換する（ファイル名を変更して内容を全面書き直す）。

**UI構成:**

```
────────────────────────────────────────
 Step 1: 回帰モデルの選択
  [保存済みモデル一覧ドロップダウン]
  → 選択すると: 目的変数・説明変数・Adj.R²・AIC等を表示
────────────────────────────────────────
 Step 2: 説明変数ごとのARIMA予測の割り当て
  変数名        | ARIMA予測（保存済み）    | シナリオ対応
  unemployment  | [予測ID=3を選択▼]        | forecast=base, lower=楽観, upper=悲観
  gdp_growth    | [予測ID=7を選択▼]        | forecast=base, lower=楽観, upper=悲観
────────────────────────────────────────
 Step 3: シナリオウェイトの設定
  ベース   : [60]%
  楽観     : [20]%
  悲観     : [20]%  ← 合計100%でない場合は警告
────────────────────────────────────────
 Step 4: 予測期間の設定
  決算年月 : [2026年3月期]
  EAD（残高）: [任意入力。空欄の場合はECL率のみ計算]
────────────────────────────────────────
 [ECLを計算する]
────────────────────────────────────────
 計算結果
  ┌ グラフ: シナリオ別PD予測の時系列
  │  ベース(青)・楽観(緑)・悲観(赤)・加重平均(黒破線)
  ├ グラフ: シナリオ別LGD予測の時系列（LGDモデルが保存済みの場合）
  └ 結果テーブル:
      期間    | PD_base | PD_up | PD_down | PD_weighted | LGD_weighted | ECL率
      2026FY  | 2.3%    | 1.9%  | 3.1%   | 2.4%        | 45.0%        | 1.08%

 [結果をDBに保存]  [CSVエクスポート]
────────────────────────────────────────
```

**計算の流れ:**

```
1. 選択されたモデル（config_id）から fit_ols() のパラメータを復元
2. 各説明変数のARIMA予測データ（forecast_id）を読み込む
3. build_scenario_forecast() で3シナリオの説明変数DataFrameを作成
4. apply_model_to_forecast() でシナリオ別のPD/LGD予測値を計算
5. calc_weighted_ecl() で加重平均を計算
6. グラフ・テーブルに結果を表示
7. 「保存」ボタンで save_ecl_result() を呼び出す
```

---

## タブ構成（Phase 5完了後: 8タブ）

| # | タブ名 | ファイル | 主な機能 | 状態 |
|---|--------|---------|---------|------|
| ① | データ閲覧 | `page_data_view.py` | データセット確認・CSVインポート | 完了 |
| ② | 相関分析 | `page_correlation.py` | 相関行列・VIF | 完了 |
| ③ | 回帰分析 | `page_regression.py` | OLS回帰・残差プロット・交差検証 | 完了 |
| ④ | モデル選択 | `page_model_selection.py` | 全組み合わせ探索 | 完了 |
| ⑤ | 動的回帰 | `page_dynamic_regression.py` | 変数別ラグ・変換設定 | 完了 |
| ⑥ | ARIMA | `page_arima.py` | ADF検定・ACF/PACF・次数選択・**予測保存** | 拡張予定 |
| ⑦ | モデル確定 | `page_model_confirm.py` | 回帰モデルのDB登録・一覧管理 | 未着手 |
| ⑧ | ECL計算 | `page_ecl.py` | シナリオ設定・ECL計算・結果保存 | 未着手 |

※ `page_forecast.py`（旧⑦プレースホルダ）は `page_ecl.py` に置換する。

---

## 年次運用ワークフロー（Phase 5完了後）

```
毎年度の引当金計算フロー:

【データ更新】
  ① データ閲覧タブ
      - 最新の説明変数CSVをインポート（決算年月を指定して上書き）
      - PD/LGD実績値のCSVをインポート

【モデル探索（必要な年のみ）】
  ② 相関分析 → ④ モデル選択 → ③ 回帰分析 → ⑤ 動的回帰
      - 変数の入替・改善が必要な場合に実施
      - 毎年やる必要はない（モデルが安定している場合は⑦の保存済みを流用）

【ARIMA予測（毎年実施）】
  ⑥ ARIMAタブ
      - 各説明変数について最新データでARIMAを再推定
      - 予測結果（n年分）をDBに保存（「予測結果をDBに保存」ボタン）

【モデル確定（必要な年のみ）】
  ⑦ モデル確定タブ
      - 変数・設定を選択して回帰を実行し確認
      - 「このモデルをDBに保存」でconfig_idを取得
      - モデルが変わらない年はスキップし、前年のconfig_idを流用

【ECL計算（毎年実施）】
  ⑧ ECL計算タブ
      - config_id（確定済み回帰モデル）を選択
      - 各変数にforecast_id（ARIMA予測結果）を割り当て
      - シナリオウェイト・EADを設定
      - 「ECLを計算する」→「結果をDBに保存」
```

---

## Phase 5 実装順序

| 順番 | Phase | 内容 | 依存 |
|------|-------|------|------|
| 1 | 5-1 | DB拡張（004_create_ecl_tables.sql） | なし |
| 2 | 5-2 | src/analysis/ecl.py | なし（並行可） |
| 3 | 5-3 | src/db_operations.py 拡張 | 5-1 |
| 4 | 5-4 | page_arima.py 拡張（予測保存） | 5-3 |
| 5 | 5-5 | page_model_confirm.py 新規 | 5-3 |
| 6 | 5-6 | page_ecl.py 新規 | 5-2, 5-3, 5-4, 5-5 |
| 7 | 5-7 | ドキュメント更新 | 5-1〜5-6 |

---

## Phase 2〜4: 詳細仕様（参考）

### 2-2. `src/analysis/data_transform.py` — データ変換

| method | 処理 | 用途 |
|--------|------|------|
| none | そのまま | 原系列 |
| log | log(1+x) | 右裾の重い分布を正規化 |
| diff | 1次差分 | トレンド除去 |
| log_diff | log→差分 | 変化率に近似 |
| arcsinh | 逆双曲線正弦 | 負値を含むデータの変換 |
| arcsinh_diff | arcsinh→差分 | 上記+トレンド除去 |

### 3-2a. 説明変数決定ワークフロー（タブ①〜⑤の推奨利用順序）

```
タブ①: データ閲覧
  └─ データセット選択、時系列グラフで傾向確認
      ↓
タブ②: 相関分析
  └─ 相関行列で変数間の関係を把握
  └─ VIFクロス表で多重共線性を初期スクリーニング
      ↓
タブ④: モデル選択（中心的ツール）
  └─ N個の説明変数の全組み合わせを網羅的に探索
  └─ AIC/BIC/Adj.R²/maxVIF/DWで各モデルを評価
      ↓
タブ③: 回帰分析（選出モデルの精査）
  └─ 最良候補でOLS回帰を実行
  └─ 各変数のp値・t値・係数を確認
  └─ 残差プロット・DW検定で残差の性質を確認
      ↓
タブ⑤: 動的回帰（必要に応じて）
  └─ 変数ごとに個別のラグを設定して時系列回帰
      ↓
タブ⑦: モデル確定
  └─ 確定したモデルをDBに保存
```

**変数選定の判断基準まとめ:**

| 基準 | 閾値 | アクション |
|------|------|-----------|
| VIF | > 10 | 多重共線性あり。片方を除外 |
| 相関係数 | > 0.9 | 強い相関。片方を除外 |
| p値 | > 0.05 | 統計的に有意でない。除外を検討 |
| AIC/BIC | 小さいほど良い | モデル比較の主要指標 |
| Adj. R² | < 0.5 | 説明力不足。変数追加を検討 |
| DW | < 1.5 or > 2.5 | 残差に自己相関。ラグ変数を検討 |

---

## Craft_RegressionAnalysis 移植対象まとめ

| 移植先（calc_ecl） | 移植元（Craft_RegressionAnalysis） | 抽出対象 |
|--------------------|------------------------------------|---------|
| `src/analysis/data_transform.py` | `utils/data_transformation.py` | `get_dataframe_for_pattern()`, 変換ロジック全体 |
| `src/analysis/correlation.py` | `pages/page_model_selection.py` | `calculate_vif()` 関数 |
| `src/analysis/correlation.py` | `pages/page_analysis.py` | 相関ヒートマップ・VIFクロス表ロジック |
| `src/analysis/regression.py` | `pages/page_model_selection.py` | `calculate_model_metrics()` 関数 |
| `src/analysis/regression.py` | `pages/page_regression.py` | `regression_calc()` 関数（交差検証、残差プロット） |
| `src/analysis/regression.py` | `pages/page_dynamic_regression.py` | 変数別ラグ設定ロジック |
| `src/analysis/model_selection.py` | `pages/page_model_selection.py` | `run_analysis()` 内の組み合わせ探索ロジック |
| `components/variable_selector.py` | `components/variable_selector.py` | VariableSelectorクラス（変数別変換・標準化設定） |
| `components/plot_utils.py` | 各pageのmatplotlib描画コード | base64変換パターン |
| `pages/page_dynamic_regression.py` | `pages/page_dynamic_regression.py` | 変数ごと個別ラグの動的回帰UIロジック |
| `src/analysis/arima.py` | ※Craft版はダミーのため新規実装 | — |
| `src/analysis/ecl.py` | ※新規実装（ECL算出ロジック） | — |

---

## 検証方法

1. **Phase 2**: 各分析モジュールの `if __name__ == "__main__"` テストで動作確認 ✅
2. **Phase 3**: `python main.py` でFletアプリ起動、全タブの操作を確認 ✅
3. **Phase 5**: E2Eフロー検証
   - CSVインポート → 分析 → ⑦モデル確定（DB保存）→ ⑥ARIMA予測（DB保存）→ ⑧ECL計算 → 結果CSV出力
