# ECL将来予想モデル 運用マニュアル

実務担当者向けの操作手順書。

---

## 1. 初期セットアップ

### 1.1 環境準備

以下がインストールされていることを確認する。

- Python 3.12
- PostgreSQL 15
- PgAdmin4

### 1.2 Pythonパッケージのインストール

```bash
cd calc_ecl
pip install -r requirements.txt
```

必要なパッケージ: `psycopg2-binary`, `pandas`

### 1.3 DB接続設定

1. テンプレートをコピーする
   ```bash
   cp config/db.ini.example config/db.ini
   ```
2. `config/db.ini` を開き、接続情報を環境に合わせて編集する
   ```ini
   [postgresql]
   host = localhost
   port = 5432
   dbname = calc_ecl
   user = postgres
   password = （実際のパスワード）
   ```

### 1.4 データベース作成

1. PgAdmin4を開く
2. データベース `calc_ecl` を新規作成する
3. `db/migrations/001_create_tables.sql` の内容をクエリツールにコピー＆ペーストして実行する
4. 7テーブルが作成されたことを確認する

作成されるテーブル一覧:

| # | テーブル名 | 概要 |
|---|-----------|------|
| 1 | indicator_sources | データソース |
| 2 | indicator_definitions | 指標定義マスタ |
| 3 | indicator_datasets | データセット（取得回） |
| 4 | indicator_data | 指標データ本体 |
| 5 | model_configs | モデル設定 |
| 6 | model_results | モデル実行結果 |
| 7 | forecast_scenarios | 将来シナリオ・予測値 |

---

## 2. 指標データのインポート

### 2.1 CSVの取得

1. [統計ダッシュボード](https://dashboard.e-stat.go.jp/) にアクセスする
2. 必要な指標を選択してCSVをダウンロードする
3. ダウンロードしたCSVを `indicator/` フォルダに配置する

### 2.2 インポート実行

```bash
python src/import_indicators.py indicator/DataSearchResult_XXXXXX.csv --retrieved-at 2026-03-04
```

| 引数 | 説明 | 必須 |
|------|------|------|
| CSVパス | CSVファイルのパス | o |
| `--retrieved-at` | データ取得日（YYYY-MM-DD） | 省略時は当日 |

### 2.3 実行結果の確認

正常に完了すると以下のように表示される:

```
CSV読み込み完了: 555行
データソースID: 1
指標定義マスタ登録完了
データセットID: 1 (2026-03-04取得)

完了: 520件INSERT, 35件スキップ
```

スキップされる行は、時点が解析できない行や指標値が空の行。

### 2.4 PgAdmin4での確認

インポート後、以下のSQLで内容を確認できる。

```sql
-- データセット一覧
SELECT * FROM indicator_datasets ORDER BY dataset_id DESC;

-- 月次データの確認（直近12ヶ月）
SELECT reference_date, indicators
FROM indicator_data
WHERE frequency = 'monthly' AND region_code = '00000'
ORDER BY reference_date DESC
LIMIT 12;

-- 特定の指標値を取り出す（例: 失業率）
SELECT reference_date,
       indicators->>'unemployment_rate' AS 失業率
FROM indicator_data
WHERE frequency = 'monthly' AND region_code = '00000'
ORDER BY reference_date DESC
LIMIT 12;
```

---

## 3. 年次運用フロー

毎年度の引当金計算に向けた作業フロー。

### 3.1 年次作業スケジュール

```
1. 統計ダッシュボードから最新データを取得（CSV）
       ↓
2. CSVをインポート（新しいデータセットとして登録）
       ↓
3. モデル設定を作成（使用するデータセット・説明変数を指定）
       ↓
4. モデル学習を実行
       ↓
5. 将来シナリオ（ベース/楽観/悲観）を作成
       ↓
6. 加重平均でECL算出
```

### 3.2 基準年が改定された場合

基準年の改定（例: GDP 2020年基準 → 2025年基準）が行われた場合:

1. CSVのカラム名が変わるため、`src/import_indicators.py` の `COLUMN_MAPPING` を確認・修正する
2. 新しいデータセットとしてインポートする
3. **旧データセットは削除しない**（過去モデルの再現に必要）

### 3.3 指標を追加・変更する場合

モデルのフィッティングに合わせて説明変数を変更する場合:

1. 統計ダッシュボードから新しい指標を含むCSVを取得する
2. `src/import_indicators.py` の `COLUMN_MAPPING` に新指標のマッピングを追加する
3. 新しいデータセットとしてインポートする

---

## 4. トラブルシューティング

### 4.1 インポート時のエラー

| エラーメッセージ | 原因 | 対処 |
|----------------|------|------|
| `設定ファイルが見つかりません` | `config/db.ini` が未作成 | `db.ini.example` をコピーして作成 |
| `connection refused` | PostgreSQLが起動していない | PostgreSQLサービスを起動 |
| `UNIQUE constraint` | 同じデータセット・日付・地域の重複 | 既にインポート済み。新規データセットとしてインポートする |
| `UnicodeDecodeError` | CSVの文字コード | UTF-8で保存し直す |

### 4.2 PgAdmin4でのSQL実行エラー

- DDL実行時にエラーが出た場合、エラーが出た文だけが失敗し、それ以前のテーブルは作成される
- 既にテーブルが存在する場合は `relation "xxx" already exists` エラーになる。問題がなければ無視してよい
