# calc_ecl — ECL将来予想モデル システム

IFRS9/予想信用損失(ECL)モデルの将来予想に使用するマクロ経済指標の管理・モデル構築・シナリオ予測システム。

---

## 技術スタック

| 項目 | 技術 |
|------|------|
| 言語 | Python 3.12（本番: WinPython64-3.12.4.1） |
| DB | PostgreSQL 15（DB名: Craft, スキーマ: calc_ecl） |
| DB管理ツール | PgAdmin4（SQLは手動実行） |
| GUI | Flet（Flutter for Python） |
| 統計分析 | statsmodels, scikit-learn |
| 可視化 | matplotlib, seaborn |
| データ処理 | pandas, numpy |
| DB接続 | psycopg2 |

---

## ディレクトリ構成

```
calc_ecl/
├── CLAUDE.md                 ← 本ファイル（プロジェクトルール）
├── main.py                   ← Fletアプリ エントリポイント
├── requirements.txt
├── config/
│   ├── db.py                 ← DB接続設定
│   ├── db.ini.example        ← 接続情報テンプレート
│   └── db.ini                ← 実際の接続情報（.gitignore対象）
├── src/
│   ├── import_indicators.py  ← CSVインポートスクリプト
│   ├── db_operations.py      ← モデル結果等のDB保存
│   ├── data/
│   │   └── indicator_loader.py  ← DB→DataFrame変換
│   └── analysis/              ← 統計分析コアロジック（UI非依存）
│       ├── data_transform.py  ← データ変換（対数・差分・標準化等）
│       ├── correlation.py     ← 相関分析・VIF
│       ├── regression.py      ← OLS回帰・評価指標
│       ├── model_selection.py ← 説明変数の組み合わせ探索
│       └── arima.py           ← ARIMA時系列モデル
├── pages/                     ← Flet UIページ
│   ├── page_data_view.py     ← データ閲覧・確認
│   ├── page_correlation.py   ← 相関分析・VIF表示
│   ├── page_regression.py    ← 回帰分析
│   ├── page_model_selection.py ← モデル選択
│   ├── page_dynamic_regression.py ← 動的回帰（変数別ラグ）
│   ├── page_arima.py         ← ARIMA分析
│   └── page_forecast.py      ← 将来シナリオ・予測
├── components/                ← 再利用UIパーツ
│   ├── variable_selector.py  ← 変数選択チェックボックス
│   └── plot_utils.py         ← matplotlib→base64変換
├── db/
│   ├── migrations/           ← DDL（テーブル作成SQL）
│   └── seeds/                ← 初期データ投入SQL
├── docs/
│   ├── system_manual.md      ← システムマニュアル（技術者向け）
│   ├── operation_manual.md   ← 運用マニュアル（実務担当者向け）
│   ├── db_design.md          ← DB設計書
│   └── NotebookLM/           ← 参考資料
└── indicator/                ← 統計ダッシュボードから取得したCSV
```

---

## ドキュメントルール（最重要）

### マニュアルは必ず2種類をセットで管理する

| ドキュメント | パス | 対象読者 | 内容 |
|-------------|------|---------|------|
| システムマニュアル | `docs/system_manual.md` | 技術者・開発者 | 設計思想、DB構造、コード構成、拡張方法 |
| 運用マニュアル | `docs/operation_manual.md` | 実務担当者 | 手順書、操作方法、年次作業フロー |

**コードや設計を変更した場合、必ず両方のマニュアルへの反映が必要かを確認し、該当箇所を更新すること。**

- 機能追加 → システムマニュアルに技術仕様を追記 ＋ 運用マニュアルに操作手順を追記
- バグ修正 → 運用マニュアルに影響があれば注意事項を追記
- DB変更 → `docs/db_design.md` + システムマニュアル + 運用マニュアル の3点を更新

---

## 設計原則

### 1. 本番環境はオフラインを前提とする

- 外部ライブラリは最小限に抑える（pip installできない可能性がある）
- Python標準ライブラリで代替できるものは標準ライブラリを使う
- 設定ファイルは `configparser`（標準ライブラリ）で読む（dotenv等は使わない）

### 2. 説明変数（マクロ経済指標）は常に変動する前提で設計する

- 毎年、取得する指標が変わる可能性がある
- 同じ指標名でも基準年改定（例: GDP 2020年基準 → 2025年基準）で数値が変わる
- 基準年の改定時期は指標ごとに異なる（同一データセット内で基準年が混在する）
- 指標データはJSONB型で格納し、スキーマ変更なしで対応する
- 重要なのは「いつ取得したデータか」（データセット単位の管理）

### 3. 時系列の粒度は4種類

| 粒度 | frequency値 | 期間 | reference_dateルール |
|------|------------|------|---------------------|
| 月次 | monthly | 毎月 | 月初日（1日） |
| 四半期 | quarterly | 3ヶ月 | 四半期初日 |
| 暦年 | calendar_year | 1-12月 | 年初日（1/1） |
| 年度 | fiscal_year | 4月-翌3月 | 年度開始日（4/1） |

暦年（12月締め）と年度（3月締め）は明確に区別する。

### 4. 分析ロジックとUIは分離する

- `src/analysis/` 以下はFlet（UI）に一切依存しない純粋なPythonモジュールとする
- UIからは `src/analysis/` の関数を呼び出すだけの構造にする
- これにより、CLI・Jupyter・Flet等どのインターフェースからも同じ分析が実行可能

### 5. WinPython同梱ライブラリを優先する

- 本番環境は WinPython64-3.12.4.1
- WinPythonに同梱されているライブラリ（statsmodels, scikit-learn, flet, matplotlib等）は利用可能
- 同梱されていないライブラリを使う場合は、wheelファイルの持ち込みで対応する

### 6. SQLはPgAdmin4で手動実行する

- DDLファイルは `db/migrations/` に連番で配置する
- `BEGIN` / `COMMIT` は記述しない（PgAdmin4が自動管理する）
- マイグレーションツール（Alembic等）は使わない

---

## コーディング規約

- Python標準のスタイル（PEP 8）に従う
- ドキュメントストリングは日本語で書く
- コメントは日本語で書く
- 変数名・関数名は英語（snake_case）

---

## 指摘のフィードバックルール

ユーザーからの指摘・修正依頼を受けた場合：

1. **まず指摘を反映する**（コード修正、設計変更等）
2. **指摘内容を抽象化・一般化して分析する**
   - 「この指摘は今回だけの話か、今後も繰り返し発生しうるパターンか？」
   - 繰り返しうるパターンであれば、このCLAUDE.mdの設計原則やルールとして追記する
3. **マニュアルへの反映が必要かを確認する**
   - システムマニュアル・運用マニュアルの両方について更新要否を判断する

例: 「dotenvはオフライン環境で使えない」→ 設計原則「本番環境はオフライン前提」として一般化

---

## 実装計画

統計分析機能の実装計画は `docs/implementation_plan.md` に記載。
Phase/進捗状況・移植元の対応表・ディレクトリ構成を含む。
新セッション開始時はこのファイルを最初に参照すること。

---

## Git運用

- コミットメッセージは日本語で書く
- 詳細ルールは親ディレクトリの `/git-operations` スキルを参照
