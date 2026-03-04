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
| 言語 | Python | 3.12 |
| DB | PostgreSQL | 15 |
| DB管理ツール | PgAdmin4 | - |
| 外部ライブラリ | psycopg2, pandas | requirements.txt参照 |

### 1.3 前提条件

- 本番環境はオフラインの可能性があるため、外部ライブラリは最小構成
- DB操作（DDL実行等）はPgAdmin4のクエリツールで手動実行
- Python標準ライブラリで代替可能なものは標準ライブラリを使用

---

## 2. ディレクトリ構成

```
calc_ecl/
├── CLAUDE.md                 ← プロジェクトルール（Claude Code用）
├── requirements.txt          ← Pythonパッケージ一覧
├── config/
│   ├── db.py                 ← DB接続モジュール
│   ├── db.ini.example        ← 接続情報テンプレート
│   └── db.ini                ← 実際の接続情報（Git管理外）
├── src/
│   └── import_indicators.py  ← CSVインポートスクリプト
├── db/
│   ├── migrations/           ← DDL（テーブル作成・変更SQL）
│   │   └── 001_create_tables.sql
│   └── seeds/                ← 初期データ・マスタデータ投入SQL
├── docs/
│   ├── system_manual.md      ← 本ファイル
│   ├── operation_manual.md   ← 運用マニュアル
│   ├── db_design.md          ← DB設計書
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
1. `indicator_sources` にデータソース登録（初回のみ）
2. `indicator_definitions` に指標定義を登録（未登録の場合）
3. `indicator_datasets` にデータセットを登録
4. CSVの各行をパースし、`indicator_data` へINSERT

**時点パースロジック**: CSVの「時点」列を正規表現で4パターンに分類。

**カラムマッピング**: スクリプト内の `COLUMN_MAPPING` 辞書でCSVカラム名と指標コードの対応を定義。CSVのカラム構成が変わった場合はここを修正する。

**重複処理**: 同一キー `(dataset_id, reference_date, frequency, region_code)` の行は `ON CONFLICT` でJSONBをマージする。

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

1. `indicator_definitions` に新しい指標コードを登録
2. `import_indicators.py` の `COLUMN_MAPPING` と `INDICATOR_FREQUENCIES` に追加
3. 新しいデータセットとしてCSVをインポート

### 6.2 基準年が改定された場合

1. 新しい指標コードで `indicator_definitions` に登録（例: `gdp_nominal_2025base`）
2. `COLUMN_MAPPING` の該当エントリを新コードに更新
3. 新しいデータセットとしてインポート（旧データセットはそのまま保持）

### 6.3 モデル系テーブルの利用（今後実装）

`model_configs` → `model_results` → `forecast_scenarios` の順で利用する。
Python側でscikit-learn等を使ったモデル学習パイプラインを構築予定。
