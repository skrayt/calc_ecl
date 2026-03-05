# 作業ログ: 目的変数（被説明変数）データ管理機能の追加

**作業日**: 2026-03-05
**作業者**: Claude Code

---

## 背景

calc_eclシステムは説明変数（マクロ経済指標）のCSVインポート・DB管理・分析機能が完成していたが、
目的変数（PD/LGD）を取り込む機能がなかった。回帰分析で目的変数を選ぶ際も説明変数リストから
選ぶ形になっていた。目的変数専用のDBテーブル・インポート機能・UIを追加し、説明変数とは独立して
管理できるようにした。

## 要件

- 対象: PD（デフォルト率）、LGD（損失率）がモデル構築対象。EADは将来対応
- 1モデル1目的変数の前提
- 粒度（frequency）が一致するデータ同士でマッチ
- データ形式: CSV
- 目的変数未読込時は従来動作にフォールバック

---

## 実施内容

### Step 1: DDL作成

**ファイル**: `db/migrations/002_create_target_tables.sql`

新規3テーブル + 既存テーブル拡張:

| テーブル | 概要 |
|---------|------|
| target_definitions | 目的変数定義マスタ（target_code, target_name, target_type, frequency） |
| target_datasets | データセット管理（dataset_name, retrieved_at, target_keys JSONB） |
| target_data | データ本体（reference_date, frequency, segment_code, targets JSONB） |
| model_configs (ALTER) | target_dataset_id カラム追加（FK → target_datasets） |

- CHECK制約: target_type IN ('pd', 'lgd', 'ead'), frequency 4種類
- UNIQUE制約: (target_dataset_id, reference_date, frequency, segment_code)
- インデックス: GIN(targets), B-tree(reference_date, target_dataset_id, frequency+segment_code)

### Step 2: CSVインポートスクリプト

**ファイル**: `src/import_targets.py`（新規作成）

- CLI + GUI両対応のインポート関数
- `parse_time_point()` を `import_indicators.py` から再利用
- 固定列（時点, セグメントコード, セグメント名）以外を目的変数データ列として自動認識
- ON CONFLICT時はJSONBマージ
- 主要関数:
  - `identify_columns()`: CSVカラム構成解析
  - `detect_frequency_from_data()`: 粒度自動検出
  - `ensure_target_definitions()`: 目的変数定義の自動登録
  - `create_target_dataset()`: データセット登録
  - `import_target_csv()`: CLI用インポート
  - `import_target_csv_gui()`: GUI用インポート（プログレスコールバック対応）

### Step 3: データロード関数

**ファイル**: `src/data/indicator_loader.py`（追加）

6関数を追加:

| 関数 | 概要 |
|------|------|
| `list_target_datasets()` | アクティブなデータセット一覧 |
| `list_target_frequencies()` | データセット内の粒度一覧 |
| `list_target_segments()` | データセット内のセグメント一覧 |
| `load_targets()` | 目的変数データをDataFrameで取得 |
| `get_target_definitions()` | 目的変数定義マスタ取得 |
| `merge_target_and_indicators()` | 目的変数と説明変数をreference_dateで内部結合 |

### Step 4: GUI（データ閲覧ページ）

**ファイル**: `pages/page_data_view.py`（大幅改修）

- タブ構造に変更: [説明変数データ] [目的変数データ]
- 目的変数タブの機能:
  - データセット/frequency/セグメント選択ドロップダウン
  - データテーブル表示 + 時系列グラフ
  - CSVインポートダイアログ（ファイル選択、データセット名、target_type、日本語名入力）
- セッションストアに `target_df`, `target_dataset_id`, `target_frequency` を追加

### Step 5: VariableSelector改修

**ファイル**: `components/variable_selector.py`（改修）

- `target_columns` パラメータ追加（後方互換: None時は従来動作）
- `target_code_to_name` パラメータ追加
- 目的変数ドロップダウンと説明変数チェックボックスの分離

### Step 6: 各分析ページの改修

**対象**: 4ファイル

| ファイル | 改修内容 |
|---------|---------|
| `page_correlation.py` | target_df取得、VariableSelectorにtarget_columns渡し、merge処理 |
| `page_regression.py` | 同上 |
| `page_dynamic_regression.py` | 同上 |
| `page_model_selection.py` | 独自ドロップダウンでtarget選択、feature_checkboxesは説明変数のみ |

### Step 7: ドキュメント更新

3ファイルを更新:

| ファイル | 更新内容 |
|---------|---------|
| `docs/db_design.md` | target_*テーブル3つの設計、ER図、データフロー |
| `docs/system_manual.md` | ディレクトリ構成、import_targets.pyセクション、ロード関数 |
| `docs/operation_manual.md` | CSVフォーマット、インポート手順、トラブルシューティング |

---

## テスト結果

### DDL実行

- psycopg2経由でDDL実行 → 10テーブル確認OK

### CSVインポートテスト

- サンプルCSV: `target_data/sample_pd_lgd.csv`（法人PD/LGD 2015〜2024年度 10行）
- インポート結果: 10件INSERT, 0件スキップ
- DB確認:
  - target_definitions: 2件（pd_corporate, lgd_corporate）
  - target_datasets: 1件（データセットID=1）
  - target_data: 10件（reference_date = 年度開始日 4/1）

### 既知の制限事項

1. CLIの `--target-type` は全列に適用される。PD/LGD混在CSVの場合、lgd列もtarget_type='pd'で登録される
   → 運用回避策: PD/LGDを別CSVに分けるか、GUI側で個別指定する

---

## 変更ファイル一覧

### 新規作成
- `db/migrations/002_create_target_tables.sql`
- `src/import_targets.py`
- `target_data/sample_pd_lgd.csv`

### 改修
- `src/data/indicator_loader.py` (+225行)
- `pages/page_data_view.py` (大幅改修)
- `components/variable_selector.py`
- `pages/page_correlation.py`
- `pages/page_regression.py`
- `pages/page_dynamic_regression.py`
- `pages/page_model_selection.py`
- `docs/db_design.md`
- `docs/system_manual.md`
- `docs/operation_manual.md`
