# ECL将来予想モデル システムマニュアル

技術者・開発者向けのシステム仕様書。

---

## 1. システム概要

### 1.1 目的

IFRS9に基づく予想信用損失(ECL)の引当金計算において、将来予想モデルの構築・運用を行うシステム。
統計ダッシュボード等からマクロ経済指標を取得し、デフォルト率等の将来予測を行う。

### 1.2 技術構成

| 項目 | 技術 | バージョン |
|------|------|-----------|
| 言語 | Python | 3.12（本番: WinPython64-3.12.4.1） |
| DB | PostgreSQL（DB名: Craft, スキーマ: calc_ecl） | 15 |
| DB管理ツール | PgAdmin4 | - |
| GUI | Flet（Flutter for Python） | 0.81+ |
| 統計分析 | statsmodels, scikit-learn | requirements.txt参照 |
| 可視化 | matplotlib, seaborn | requirements.txt参照 |
| 外部ライブラリ | psycopg2, pandas 他 | requirements.txt参照 |

### 1.3 前提条件

- 本番環境はオフラインの可能性があるため、外部ライブラリは最小構成
- DB操作（DDL実行等）はPgAdmin4のクエリツールで手動実行
- Python標準ライブラリで代替可能なものは標準ライブラリを使用

---

## 2. ディレクトリ構成

```
calc_ecl/
├── CLAUDE.md                 ← プロジェクトルール
├── main.py                   ← Fletアプリ エントリポイント
├── requirements.txt          ← Pythonパッケージ一覧
├── config/
│   ├── db.py                 ← DB接続モジュール
│   ├── db.ini.example        ← 接続情報テンプレート
│   └── db.ini                ← 実際の接続情報（Git管理外）
├── src/
│   ├── import_indicators.py  ← 説明変数CSVインポートスクリプト
│   ├── import_targets.py     ← 目的変数CSVインポートスクリプト
│   ├── data/
│   │   └── indicator_loader.py ← DBからの指標・目的変数データ読み込み
│   └── analysis/             ← 統計分析コアモジュール（UI非依存）
│       ├── data_transform.py ← データ変換・標準化
│       ├── correlation.py    ← 相関行列・VIF
│       ├── regression.py     ← OLS回帰・交差検証
│       ├── model_selection.py← 説明変数の組み合わせ探索
│       └── arima.py          ← ARIMA時系列モデル
├── components/               ← 再利用可能なUIコンポーネント
│   ├── plot_utils.py         ← 描画ユーティリティ
│   └── variable_selector.py  ← 変数選択パーツ
├── pages/                    ← Fletアプリの各タブページ
│   ├── page_data_view.py     ← ① データ閲覧
│   ├── page_correlation.py   ← ② 相関分析
│   ├── page_regression.py    ← ③ 回帰分析
│   ├── page_model_selection.py ← ④ モデル選択
│   ├── page_dynamic_regression.py ← ⑤ 動的回帰
│   ├── page_arima.py         ← ⑥ ARIMA
│   └── page_forecast.py      ← ⑦ 将来シナリオ
├── db/
│   ├── migrations/           ← DDL（テーブル作成・変更SQL）
│   │   └── 001_create_tables.sql
│   └── seeds/                ← 初期データ・マスタデータ投入SQL
├── docs/
│   ├── system_manual.md      ← 本ファイル
│   ├── operation_manual.md   ← 運用マニュアル
│   ├── db_design.md          ← DB設計書
│   ├── implementation_plan.md← 実装計画
│   └── NotebookLM/           ← 参考資料
└── indicator/                ← 統計ダッシュボードからのCSV生データ
```

---

## 3. データベース設計

詳細は `docs/db_design.md` を参照。以下は概要のみ記載。

### 3.1 テーブル構成（7テーブル）

```
[マスタ系]
  indicator_sources      ← データソース（e-Stat等）
  indicator_definitions  ← 指標定義（基準年は指標単位で管理）

[データ系]
  indicator_datasets     ← データ取得回（いつ取得したか）
  indicator_data         ← 指標データ本体（JSONB格納）

[モデル系]
  model_configs          ← モデル設定（どのデータセットのどの指標を使うか）
  model_results          ← モデル学習・評価結果
  forecast_scenarios     ← 将来シナリオ・予測値（ベース/楽観/悲観）
```

### 3.2 JSONB設計の考え方

指標データは `indicator_data.indicators` カラムにJSONB型で格納する。

**理由**: 説明変数は毎年変わる可能性があり、またモデルのフィッティングに合わせて選択する指標も可変であるため、カラム追加のスキーマ変更を避ける設計とした。

```json
{
  "unemployment_rate": 2.4,
  "gdp_nominal_2020base": 173798.7,
  "prefectural_gdp_2015base": 595788788
}
```

### 3.3 データセットによるデータ管理

同じ指標名でも基準年改定（GDP 2020年基準 → 2025年基準 等）で数値が変わる。
また基準年の改定時期は指標ごとに異なるため、データセット単位で一律に基準年を持つことはしない。

- `indicator_definitions` で**基準年を指標単位**で管理（改定=新しい指標コード）
- `indicator_datasets` は**データ取得時期のみ**を管理
- `model_configs.dataset_id` でモデルとデータセットを紐付け（再現性担保）

### 3.4 時系列粒度

| 粒度 | frequency値 | reference_dateルール | CSV上の表記 |
|------|------------|---------------------|------------|
| 月次 | `monthly` | 月初日 `2025-01-01` | `2025年1月` |
| 四半期 | `quarterly` | 四半期初日 `2025-01-01` | `2025年1-3月期` |
| 暦年 | `calendar_year` | 年初日 `2025-01-01` | `2025年` |
| 年度 | `fiscal_year` | 年度開始日 `2025-04-01` | `2025年度` |

---

## 4. モジュール仕様

### 4.1 config/db.py — DB接続

`configparser`（Python標準ライブラリ）で `config/db.ini` を読み込み、PostgreSQL接続を返す。
接続後に `SET search_path TO calc_ecl` を実行してスキーマを設定する。

```python
from config.db import get_connection

conn = get_connection()
```

設定ファイル（`config/db.ini`）が存在しない場合は `FileNotFoundError` を送出する。

### 4.2 src/import_indicators.py — CSVインポート

統計ダッシュボードからダウンロードしたCSVをパースしてDBにインポートする。

**実行方法**:
```bash
python src/import_indicators.py <CSVパス> [--retrieved-at YYYY-MM-DD]
```

**処理フロー**:
1. `config/column_mapping.json` からカラムマッピングを読み込む
2. CSVに未知のカラムがあれば対話的にマッピングを追加（JSONに自動保存）
3. `indicator_sources` にデータソース登録（初回のみ）
4. `indicator_definitions` に指標定義を登録（未登録の場合）
5. `indicator_datasets` にデータセットを登録
6. CSVの各行をパースし、`indicator_data` へINSERT

**時点パースロジック**: CSVの「時点」列を正規表現で4パターンに分類。

**カラムマッピング**: `config/column_mapping.json` で管理。CSVのカラム構成が変わった場合（基準年改定等）、インポート実行時に対話的に新しいマッピングを追加できる。コードの修正は不要。

**重複処理**: 同一キー `(dataset_id, reference_date, frequency, region_code)` の行は `ON CONFLICT` でJSONBをマージする。

### 4.2.1 src/import_targets.py — 目的変数CSVインポート

目的変数（PD/LGD/EAD）のCSVをパースしてDBにインポートする。

**実行方法**:
```bash
python src/import_targets.py <CSVパス> --target-type pd [--dataset-name "名前"] [--retrieved-at YYYY-MM-DD]
```

**CSVフォーマット**:
```csv
時点,セグメントコード,セグメント名,pd_corporate,lgd_corporate
2020年度,corporate,法人,0.0234,0.45
```
- 時点列（必須）: 説明変数CSVと同じ形式
- セグメントコード列/セグメント名列（任意）: 省略時は `all/全体`
- その他の数値列: カラム名がそのまま `target_code` になる

**処理フロー**:
1. CSV読み込み → 時点列・セグメント列・数値列を自動識別
2. `target_definitions` に目的変数定義を登録（未登録の場合）
3. `target_datasets` にデータセットを登録
4. CSVの各行をパースし、`target_data` へINSERT

**重複処理**: 同一キー `(target_dataset_id, reference_date, frequency, segment_code)` の行は `ON CONFLICT` でJSONBをマージする。

### 4.3 src/data/indicator_loader.py — 指標・目的変数データ読み込み

DBから指標データ・目的変数データをpandas DataFrameとして読み込む。

```python
from src.data.indicator_loader import load_indicators, load_targets, merge_target_and_indicators

# 説明変数
df = load_indicators(dataset_id=1, frequency="monthly")

# 目的変数
target_df = load_targets(target_dataset_id=1, frequency="fiscal_year")

# 結合
merged = merge_target_and_indicators(target_df, df, "pd_corporate")
```

**説明変数用関数**:

| 関数 | 説明 |
|------|------|
| `list_datasets()` | データセット一覧を取得 |
| `list_frequencies(dataset_id)` | 指定データセットのfrequency一覧 |
| `load_indicators(dataset_id, frequency)` | 指標データをDatetimeIndex付きDataFrameで返す |
| `get_indicator_definitions(codes)` | 指標定義マスタを取得 |
| `load_dataset_summary(dataset_id)` | データセットの概要情報を取得 |

**目的変数用関数**:

| 関数 | 説明 |
|------|------|
| `list_target_datasets()` | 目的変数データセット一覧を取得 |
| `list_target_frequencies(target_dataset_id)` | 目的変数データセットのfrequency一覧 |
| `list_target_segments(target_dataset_id, frequency)` | セグメント一覧を取得 |
| `load_targets(target_dataset_id, frequency, segment_code)` | 目的変数DataFrameを返す |
| `get_target_definitions(codes)` | 目的変数定義マスタを取得 |
| `merge_target_and_indicators(target_df, indicator_df, target_code)` | 目的変数と説明変数をreference_dateで内部結合 |

### 4.4 src/analysis/ — 統計分析コアモジュール

UI非依存の統計分析モジュール群。pandas DataFrame を入出力する純粋な関数群。

#### 4.4.1 data_transform.py — データ変換・標準化

| 関数 | 説明 |
|------|------|
| `transform(df, method)` | DataFrame全体に一括変換を適用 |
| `standardize(df)` | Z-score標準化 |
| `transform_per_column(df, settings)` | 変数ごとに個別の変換設定を適用 |

対応変換: `none`, `log`, `diff`, `log_diff`, `arcsinh`, `arcsinh_diff`

#### 4.4.2 correlation.py — 相関分析・VIF

| 関数 | 説明 |
|------|------|
| `calc_correlation_matrix(df)` | 相関行列を計算 |
| `calc_vif(X)` | 各変数のVIF（分散拡大係数）を計算 |
| `calc_vif_cross_table(X)` | 全変数ペア間のVIFクロス表を計算 |

#### 4.4.3 regression.py — OLS回帰分析

| 関数 | 説明 |
|------|------|
| `fit_ols(y, X, lag)` | OLS回帰。R², Adj.R², AIC, BIC, DW, 係数テーブル, 残差等を返す |
| `cross_validate(y, X, cv, lag)` | K-fold交差検証（MSE） |

#### 4.4.4 model_selection.py — モデル選択

| 関数 | 説明 |
|------|------|
| `search_best_model(df, target_col, feature_cols, n_features, ...)` | 説明変数の全組み合わせを探索しAIC/BIC/VIF等で評価 |
| `filter_models(results_df, max_vif, ...)` | 条件によるモデル候補フィルタリング |

#### 4.4.5 arima.py — ARIMA時系列モデル

| 関数 | 説明 |
|------|------|
| `fit_arima(y, order)` | ARIMAモデル学習 |
| `auto_select_order(y, max_p, max_d, max_q)` | AIC/BIC最小化による次数自動選択 |
| `forecast(model, steps, alpha)` | 将来予測（信頼区間付き） |
| `test_stationarity(y)` | ADF検定（定常性検定） |
| `calc_acf_pacf(y, nlags)` | ACF/PACF計算 |

### 4.5 GUIアプリケーション（Flet）

FletによるタブベースのGUIアプリケーション。`main.py` をエントリポイントとする。

```bash
PYTHONPATH=. python main.py
```

**タブ構成（7タブ）**:

| # | タブ | ファイル | 機能 |
|---|------|---------|------|
| 1 | データ閲覧 | `pages/page_data_view.py` | データセット選択・テーブル表示・時系列グラフ |
| 2 | 相関分析 | `pages/page_correlation.py` | データソース選択・相関行列ヒートマップ・VIF一覧・VIFクロス表 |
| 3 | 回帰分析 | `pages/page_regression.py` | データソース選択・OLS回帰・係数テーブル・残差プロット・交差検証 |
| 4 | モデル選択 | `pages/page_model_selection.py` | データソース選択・全組み合わせ探索・進捗バー・VIFフィルタ |
| 5 | 動的回帰 | `pages/page_dynamic_regression.py` | データソース選択・変数別変換・標準化・ラグ設定 |
| 6 | ARIMA | `pages/page_arima.py` | ADF検定・ACF/PACF・次数自動選択・予測 |
| 7 | 将来シナリオ | `pages/page_forecast.py` | シナリオ作成・予測結果保存（実装予定） |

**共通コンポーネント**:

| ファイル | 説明 |
|---------|------|
| `components/plot_utils.py` | matplotlib→base64変換、各種プロット関数 |
| `components/variable_selector.py` | 目的変数・説明変数の選択UIパーツ |
| `components/data_source_selector.py` | データソース選択UI（データセット・frequency・セグメント） |
| `components/help_panel.py` | 折りたたみ式ヘルプパネル |

**データソース選択コンポーネント（DataSourceSelector）**:

分析ページ（②相関〜⑤動的回帰）の上部に配置され、説明変数と目的変数のデータソースを統一的に選択する。

- 説明変数: データセット + frequency を選択
- 目的変数: データセット + frequency + セグメント を選択
- 目的変数のfrequency変更時、説明変数のfrequencyも自動的に合わせる
- frequency不一致時は警告メッセージを表示
- データ変更時にコールバックで変数セレクタ等を再構築する

### 4.6 config/column_mapping.json — カラムマッピング設定

CSVカラム名と指標コードの対応を管理する外部設定ファイル。

```json
{
  "columns": {
    "国内総生産（支出側）（名目）2020年基準【10億円】": {
      "code": "gdp_nominal_2020base",
      "name": "国内総生産（支出側）（名目）2020年基準",
      "unit": "10億円",
      "base_year": "2020",
      "frequency": "quarterly"
    }
  },
  "skip_columns": ["時点", "地域コード", "地域", "注記"]
}
```

- `columns`: CSVカラム名 → 指標定義のマッピング
- `skip_columns`: インポート対象外のカラム名リスト
- 未知のカラム検出時、以下をルールベースで自動検出:
  - **指標名**: `re.sub(r"【.+?】", "", col_name)` で単位を除去
  - **基準年**: `re.search(r"(\d{4})年基準", col_name)` で抽出
  - **単位**: `re.search(r"【(.+?)】", col_name)` で抽出
  - **粒度**: CSVデータをスキャンし、値がある行の時点パターンから最も細かい粒度を推定
- **対話入力は指標コード（英語snake_case）のみ**

---

## 5. DDL管理

### 5.1 ファイル命名規則

`db/migrations/` に連番で配置する。

```
001_create_tables.sql       ← 初期テーブル作成
002_add_xxx_column.sql      ← 将来のスキーマ変更
```

### 5.2 実行方法

PgAdmin4のクエリツールで手動実行する。`BEGIN` / `COMMIT` は記述しない。

---

## 6. 拡張ガイド

### 6.1 新しい指標を追加する場合

1. 統計ダッシュボードから新しい指標を含むCSVをダウンロード
2. `python src/import_indicators.py` を実行
3. 未知のカラムが検出され、対話プロンプトが表示される
4. 指標コード・名前・単位・基準年・粒度を入力
5. `config/column_mapping.json` に自動保存される
6. 以降のインポートでは自動的に認識される

### 6.2 基準年が改定された場合

1. 統計ダッシュボードから新基準年のCSVをダウンロード
2. `python src/import_indicators.py` を実行
3. CSVカラム名が変わっていれば（例: `2025年基準`）未知カラムとして検出される
4. 新しい指標コード（例: `gdp_nominal_2025base`）を入力
5. 新しいデータセットとしてインポート（旧データセットはそのまま保持）

### 6.3 モデル系テーブルの利用

`model_configs` → `model_results` → `forecast_scenarios` の順で利用する。
GUIアプリの回帰分析・モデル選択・ARIMAタブで分析し、将来シナリオタブで結果をDB保存する。

### 6.4 新しいタブページを追加する場合

1. `pages/page_xxx.py` に `xxx_page(page: ft.Page) -> ft.Control` 関数を作成
2. `main.py` の `tabs` リストとタブ切替ロジック（`on_tab_change`）に追加
3. 分析ロジックは `src/analysis/` に独立モジュールとして配置
4. 描画は `components/plot_utils.py` の共通関数を使用
