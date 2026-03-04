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
| Phase 2-5 | model_selection（組み合わせ探索） | 未着手 |
| Phase 2-6 | arima（ARIMA時系列モデル） | 未着手 |
| Phase 3 | Flet GUIアプリ構築 | 未着手 |
| Phase 4 | ドキュメント更新 | 未着手 |

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
│   ├── import_indicators.py       ← CSVインポートスクリプト（既存）
│   ├── db_operations.py           ← model_configs等へのDB保存
│   ├── data/
│   │   └── indicator_loader.py    ← DB→DataFrame変換
│   └── analysis/                   ← 統計分析コアロジック（UI非依存）
│       ├── __init__.py
│       ├── data_transform.py      ← データ変換（対数・差分・標準化等）
│       ├── correlation.py         ← 相関分析・VIF
│       ├── regression.py          ← OLS回帰・評価指標
│       ├── model_selection.py     ← 説明変数の組み合わせ探索
│       └── arima.py               ← ARIMA時系列モデル
├── pages/                          ← Flet UIページ
│   ├── page_data_view.py          ← データ閲覧・確認
│   ├── page_correlation.py        ← 相関分析・VIF表示
│   ├── page_regression.py         ← 回帰分析
│   ├── page_model_selection.py    ← モデル選択
│   ├── page_arima.py              ← ARIMA分析
│   └── page_forecast.py           ← 将来シナリオ・予測
├── components/                     ← 再利用UIパーツ
│   ├── variable_selector.py       ← 変数選択チェックボックス
│   └── plot_utils.py              ← matplotlib→base64変換
├── db/
│   ├── migrations/
│   │   └── 001_create_tables.sql  ← 既存
│   └── seeds/
├── docs/
│   ├── implementation_plan.md     ← 本ファイル
│   ├── system_manual.md
│   ├── operation_manual.md
│   ├── db_design.md
│   └── NotebookLM/
└── indicator/                      ← 統計ダッシュボードCSV
```

---

## Phase 1: 基盤更新 ✅完了

- `requirements.txt` にflet, statsmodels, scikit-learn, matplotlib, seaborn, numpy追加
- `CLAUDE.md` にディレクトリ構成・設計原則（分析/UI分離、WinPython優先等）を追記

---

## Phase 2: 統計分析コアモジュール（UI非依存）

**設計原則: `src/analysis/` 以下はFletに一切依存しない純粋なPythonモジュール**

### 2-1. `src/data/indicator_loader.py` — DB→DataFrame変換

DBのindicator_dataテーブルからJSONBを展開してpandas DataFrameに変換する。

```python
# 主要な関数
def list_datasets() -> pd.DataFrame
    """indicator_datasetsの一覧を返す"""

def load_indicators(dataset_id, frequency, region_code='00000') -> pd.DataFrame
    """指定データセットの指標データをDataFrame化。
    reference_dateをインデックス、各指標コードをカラムに展開"""
```

### 2-2. `src/analysis/data_transform.py` — データ変換

**移植元:** `../Craft_RegressionAnalysis/utils/data_transformation.py`
- `get_dataframe_for_pattern(df, transformation_type, is_standardized)`

```python
# 主要な関数
def transform(df, method) -> pd.DataFrame
    """データ変換（全カラム一括）。method: none/log/diff/log_diff/arcsinh/arcsinh_diff"""

def transform_per_column(df, settings) -> pd.DataFrame
    """変数ごとに個別の変換・標準化を適用。
    settings: {col_name: {"transform": "log", "standardize": True}, ...}
    ※ Craft版のVariableSelectorの変数別設定に対応"""

def standardize(df) -> pd.DataFrame
    """Z-score標準化（sklearn StandardScaler使用）"""
```

変換の種類:
| method | 処理 | 用途 |
|--------|------|------|
| none | そのまま | 原系列 |
| log | log(1+x) | 右裾の重い分布を正規化 |
| diff | 1次差分 | トレンド除去 |
| log_diff | log→差分 | 変化率に近似 |
| arcsinh | 逆双曲線正弦 | 負値を含むデータの変換 |
| arcsinh_diff | arcsinh→差分 | 上記+トレンド除去 |

変換は「全カラム一括」と「変数ごと個別」の2モードをサポート。
相関分析・回帰分析ページでは変数ごとの個別設定を使用する。

### 2-3. `src/analysis/correlation.py` — 相関分析・VIF

**移植元:** `../Craft_RegressionAnalysis/pages/page_model_selection.py`
- `calculate_vif(X)` 関数

```python
# 主要な関数
def calc_correlation_matrix(df) -> pd.DataFrame
    """相関行列を計算"""

def calc_vif(X) -> pd.DataFrame
    """VIF（分散拡大係数）を計算。多重共線性の検出に使用。
    VIF = 1/(1-R²) で各説明変数について算出"""
```

VIFの目安: 10以上で多重共線性の疑い、5以上で注意

### 2-4. `src/analysis/regression.py` — OLS回帰・評価指標

**移植元:** `../Craft_RegressionAnalysis/pages/page_model_selection.py`
- `calculate_model_metrics(y, X, lag_order=0)` 関数
- `../Craft_RegressionAnalysis/pages/page_regression.py`
- `regression_calc(target, features, X, y)` 関数

```python
# 主要な関数
def fit_ols(y, X, lag=0) -> dict
    """OLS回帰を実行し評価指標を返す。
    戻り値: {r2, adj_r2, aic, bic, dw, f_stat, f_pvalue, coefficients}
    - statsmodels.regression.linear_model.OLS使用
    - lag>0の場合、Xをlag期ずらして回帰"""

def cross_validate(y, X, cv=5) -> float
    """k-fold交差検証スコア（MSE）を返す。
    - sklearn cross_val_score使用"""
```

### 2-5. `src/analysis/model_selection.py` — モデル選択

**移植元:** `../Craft_RegressionAnalysis/pages/page_model_selection.py`
- `run_analysis()` 内の組み合わせ探索ロジック

```python
# 主要な関数
def search_best_model(df, target_col, feature_cols, n_features,
                      transform_method='none', lag=0) -> pd.DataFrame
    """説明変数の全組み合わせを探索し、各モデルの評価指標を返す。
    処理:
      1. feature_colsからn_features個の組み合わせを全列挙
      2. 各組み合わせで fit_ols() + calc_vif()
      3. 結果をDataFrame化（AIC/BIC/R²/maxVIF等）
      4. AIC昇順でソート"""
```

### 2-6. `src/analysis/arima.py` — ARIMA時系列モデル（新規実装）

Craft版はダミーだったため、statsmodelsで新規実装する。

```python
# 主要な関数
def fit_arima(y, order=(1,1,1)) -> dict
    """ARIMAモデルを学習。
    戻り値: {aic, bic, params, resid, model_obj}
    - statsmodels.tsa.arima.model.ARIMA使用"""

def auto_select_order(y, max_p=3, max_d=2, max_q=3) -> tuple
    """AICが最小になるARIMA次数を探索"""

def forecast(model_result, steps, alpha=0.05) -> pd.DataFrame
    """将来予測。戻り値: forecast/lower/upperカラムのDataFrame"""
```

---

## Phase 3: Flet GUIアプリ構築

Craft_RegressionAnalysis（`../Craft_RegressionAnalysis/main.py`）のタブ構成を参考に再構築。
データソースがSQLite→PostgreSQLに変わる点、データセット選択が加わる点が主な違い。

### 3-1. `main.py` — エントリポイント
- `flet.app(target=main)` で起動
- タブベースのナビゲーション

### 3-2. タブ構成（7タブ）

説明変数決定プロセスの全工程をカバーする。

| タブ | ファイル | 機能 | 使用する分析モジュール |
|------|---------|------|---------------------|
| 1. データ閲覧 | `pages/page_data_view.py` | データセット選択、指標一覧、時系列グラフ | indicator_loader |
| 2. 相関分析 | `pages/page_correlation.py` | 相関行列ヒートマップ、VIFクロス表 | correlation, data_transform |
| 3. 回帰分析 | `pages/page_regression.py` | OLS実行、係数・p値、残差プロット、DW検定 | regression, data_transform |
| 4. モデル選択 | `pages/page_model_selection.py` | 全組み合わせ探索、AIC/BIC/R²比較、CSV出力 | model_selection |
| 5. 動的回帰 | `pages/page_dynamic_regression.py` | 変数ごとの個別ラグ設定、時系列回帰 | regression, data_transform |
| 6. ARIMA | `pages/page_arima.py` | ARIMA学習、ACF/PACFプロット、次数自動選択 | arima |
| 7. 将来シナリオ | `pages/page_forecast.py` | ベース/楽観/悲観作成、加重平均、DB保存 | db_operations |

### 3-2a. 説明変数決定ワークフロー（タブ1〜5の推奨利用順序）

```
タブ1: データ閲覧
  └─ データセット選択、時系列グラフで傾向確認
      ↓
タブ2: 相関分析
  └─ 相関行列で変数間の関係を把握
  └─ VIFクロス表で多重共線性を初期スクリーニング
  └─ 判断: VIF>10の変数ペアを特定→除外候補
      ↓
タブ4: モデル選択（中心的ツール）
  └─ N個の説明変数の全組み合わせを網羅的に探索
  └─ AIC/BIC/Adj.R²/maxVIF/DWで各モデルを評価
  └─ 判断: AIC最小かつVIF<10のモデルを3〜5件選出
      ↓
タブ3: 回帰分析（選出モデルの精査）
  └─ 最良候補でOLS回帰を実行
  └─ 各変数のp値・t値・係数を確認
  └─ 残差プロット・DW検定で残差の性質を確認
  └─ 判断: p>0.05の変数があれば除外を検討
      ↓
タブ5: 動的回帰（必要に応じて）
  └─ 変数ごとに個別のラグを設定して時系列回帰
  └─ 判断: ラグ追加でAdj.R²が改善するか確認
      ↓
タブ6〜7: ARIMA・将来シナリオ
  └─ 確定した説明変数でモデル構築→予測→ECL算出
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

### 3-3. 共通コンポーネント

- `components/variable_selector.py`
  - **移植元:** `../Craft_RegressionAnalysis/components/variable_selector.py` のVariableSelectorクラス
  - チェックボックスで説明変数を選択するUIパーツ
  - **変数ごとに個別の変換方法・標準化ON/OFFを設定可能**
  - calc_eclではJSONBの指標キーを動的に表示
  - UIレイアウト: 各変数行 = [チェックボックス] [標準化トグル] [変換ドロップダウン] [変数名]

- `components/plot_utils.py`
  - **移植元:** `../Craft_RegressionAnalysis/` のmatplotlib描画ロジック
  - matplotlib Figure → base64 PNG文字列 → Flet ft.Image に変換
  - 時系列プロット、相関ヒートマップ、残差プロット等の共通描画

### 3-4. `src/db_operations.py` — モデル結果のDB保存

```python
# 主要な関数
def save_model_config(config_dict) -> int
    """model_configsにINSERTし、config_idを返す"""

def save_model_result(result_dict) -> int
    """model_resultsにINSERT"""

def save_forecast_scenario(scenario_dict) -> None
    """forecast_scenariosにINSERT"""

def load_model_configs() -> pd.DataFrame
    """保存済みモデル設定の一覧"""
```

---

## Phase 4: ドキュメント更新

全Phaseの実装完了後に一括更新する。

| ドキュメント | 追記内容 |
|-------------|---------|
| `docs/system_manual.md` | 分析モジュール仕様、Fletアプリ構成、拡張ガイド |
| `docs/operation_manual.md` | アプリ起動方法、各タブ操作手順、年次運用フロー更新 |
| `docs/db_design.md` | 変更があれば更新 |

---

## 実装順序

| 順番 | 内容 | 依存 |
|------|------|------|
| 1 | Phase 1: requirements + CLAUDE.md更新 | なし | ✅完了 |
| 2 | Phase 2-1: indicator_loader | Phase 1 |
| 3 | Phase 2-2〜2-4: data_transform, correlation, regression | なし（並行可） |
| 4 | Phase 2-5: model_selection | 2-2, 2-3, 2-4 |
| 5 | Phase 2-6: arima | なし |
| 6 | Phase 3-1〜3-3: Fletアプリ（main.py + pages + components） | Phase 2全体 |
| 7 | Phase 3-4: db_operations | Phase 1 |
| 8 | Phase 4: ドキュメント更新 | 全Phase |

---

## Craft_RegressionAnalysis 移植対象まとめ

新セッション時に移植元コードを参照するための一覧。

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

---

## 検証方法

1. **Phase 2**: 各分析モジュールの `if __name__ == "__main__"` テストで動作確認
2. **Phase 3**: `python main.py` でFletアプリ起動、全6タブの操作を確認
3. **E2E**: CSVインポート→データ閲覧→相関分析→モデル選択→予測→シナリオDB保存
