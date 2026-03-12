# Web公開作業記録 — Render + Supabase デプロイ

**作業日**: 2026-03-11〜12
**目的**: FletデスクトップアプリをWebアプリとしてRender上に公開する
**構成**: Flet（Python）+ Supabase（PostgreSQL）+ Render（ホスティング）

---

## アーキテクチャ概要

```
[ローカル開発]                    [Web公開]
  Fletデスクトップ                  Flet Webモード（Render）
  + config/db.ini                   + Render環境変数
  + ローカルPostgreSQL              + Supabase（PostgreSQL）
```

**設計方針**: ローカル開発フローは一切壊さない。環境変数の有無で自動切替。

---

## Phase W1: DB接続二重化（config/db.py）

### 変更内容

`config/db.py` に環境変数フォールバックを追加。接続情報の優先順位：

1. `config/db.ini` が存在する → configparser で読む（ローカル開発）
2. `DATABASE_URL` 環境変数あり → URLパースして接続（Render/Supabase）
3. `DB_HOST` 等の個別環境変数あり → dictに変換
4. どれも無し → `FileNotFoundError`

```python
def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        # ローカル: db.ini から読む
        parser = configparser.ConfigParser()
        parser.read(_CONFIG_PATH, encoding="utf-8")
        return dict(parser["postgresql"])

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return _parse_database_url(database_url)
    ...
```

- `get_connection()` のインターフェースは不変 → 呼び出し側7ファイルの変更不要
- `sslmode` パラメータ対応（Supabase接続に必要）

---

## Phase W2: main.py Web/デスクトップ切替

### 変更内容

```python
# ウィンドウサイズ設定（デスクトップ時のみ）
if not page.web:
    page.window.resizable = True
    page.window.width = 1400
    ...

# エントリポイント切替
if __name__ == "__main__":
    import os
    if os.environ.get("FLET_WEB", "").strip() == "1":
        ft.app(target=main, view=ft.AppView.WEB_BROWSER,
               port=int(os.environ.get("PORT", "8550")))
    else:
        ft.run(main)  # 従来のデスクトップモード
```

- `FLET_WEB=1` 環境変数でWebモード起動
- Renderが自動設定する `PORT` 環境変数に対応

---

## Phase W3: Supabase DBセットアップ

### 使用プロジェクト

- **プロジェクト名**: crypto-alert-hub（リネームして再利用）
- **リージョン**: Northeast Asia（Tokyo）/ ap-northeast-1
- **プラン**: FREE（Nano）

### 作業手順

#### Step 1: 既存テーブルの削除

SQL Editor で以下を実行：

```sql
DROP TABLE IF EXISTS public.alerts CASCADE;
DROP TABLE IF EXISTS public.notification_history CASCADE;
DROP TABLE IF EXISTS public.price_cache CASCADE;
DROP TABLE IF EXISTS public.subscriptions CASCADE;
DROP TABLE IF EXISTS public.profiles CASCADE;
```

#### Step 2: マイグレーション実行（001〜006）

| ファイル | 内容 |
|---------|------|
| `001_create_tables.sql` | 指標テーブル・モデルテーブル（calc_eclスキーマ作成含む） |
| `002_create_target_tables.sql` | 目的変数テーブル |
| `003_add_fiscal_year_month.sql` | 決算年月カラム追加 |
| `004_create_ecl_tables.sql` | ARIMAテーブル・ECLテーブル |
| `005_...` | スキップ（既存データなし） |
| `006_supabase_rls_setup.sql` | RLS有効化 + アクセスポリシー設定 |

#### Step 3: RLS（Row Level Security）設定

`006_supabase_rls_setup.sql` で以下を実施：
- calc_eclスキーマの全12テーブルにRLSを有効化
- `USING (true)` のポリシーで全操作を許可
- アプリはpostgresロール（superuser）で接続するためRLSをバイパス

**ハマりポイント**: 006を2回実行するとポリシー重複エラー。
→ `CREATE POLICY` の前に `DROP POLICY IF EXISTS` を追加して解決。

```sql
-- エラー: policy "allow_all_indicator_sources" already exists
DROP POLICY IF EXISTS "allow_all_indicator_sources" ON calc_ecl.indicator_sources;
CREATE POLICY "allow_all_indicator_sources"
    ON calc_ecl.indicator_sources FOR ALL
    USING (true) WITH CHECK (true);
```

### 接続文字列

**Direct connection（IPv4非対応 → 使わない）**:
```
postgresql://postgres:[PASSWORD]@db.fssxjuuhfqrvivinghnl.supabase.co:5432/postgres
```

**Session Pooler（IPv4対応 → Renderで使用）**:
```
postgresql://postgres.fssxjuuhfqrvivinghnl:[PASSWORD]@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres
```

**ポイント**: RenderはIPv4ネットワークのため、Direct connectionは使えない。
Session Pooler（port 5432）を使うことで：
- IPv4対応（✅）
- `SET search_path` が維持される（✅）
- 長時間接続に対応（✅）

---

## Phase W4: Renderデプロイ設定ファイル作成

### 作成ファイル一覧

#### render.yaml

```yaml
services:
  - type: web
    name: calc-ecl
    runtime: python
    buildCommand: "apt-get install -y fonts-noto-cjk && pip install -r requirements-web.txt"
    startCommand: python main.py
    envVars:
      - key: FLET_WEB
        value: "1"
      - key: DATABASE_URL
        sync: false  # Render dashboardで手動設定
      - key: DB_SCHEMA
        value: calc_ecl
      - key: DB_SSLMODE
        value: require
```

**ポイント**:
- `apt-get install -y fonts-noto-cjk`: Render（Ubuntu）で日本語フォントを使うために必要
- `DATABASE_URL`: `sync: false` にしてダッシュボードで手動設定（秘匿情報）

#### requirements-web.txt

`requirements.txt` から以下を除外したもの：
- `flet-desktop==0.81.0` → デスクトップアプリ専用。Web版不要
- `flet-cli==0.81.0` → CLI専用。Web版不要

#### .gitignore への追加

```
.env    ← ローカルテスト用の環境変数ファイルをGitに含めない
```

---

## Renderデプロイ手順（実施中）

### GitHub連携

1. Render Dashboard → **New +** → **Web Services**
2. **GitHub** ボタンをクリック → GitHub App "Install Render" 画面
3. **Only select repositories** を選択 → `skrayt/calc_ecl` を指定
4. **Install** → GitHub認証（sudo mode）
5. `skrayt / calc_ecl` がリポジトリ一覧に表示 ✅

### 次のステップ（続き）

- リポジトリを選択 → Configure画面で設定入力
- Branch: `feature/web-deploy`
- Build/Start Commandを入力
- 環境変数（DATABASE_URLなど）を設定
- Deploy → ビルドログ確認

---

## 技術的なポイント・ハマりどころ まとめ

| ポイント | 内容 |
|---------|------|
| Supabase Direct connectionはIPv4非対応 | RenderはIPv4のためSession Pooler（port 5432）を使う |
| Session Pooler vs Transaction Pooler | port 5432（Session）なら`SET search_path`が維持される。port 6543（Transaction）はリセットされる |
| Flet WebではFilePickerの挙動が変わる | W5で対応予定。ローカルパス直読み不可 |
| 日本語フォント | Renderのビルドコマンドで`fonts-noto-cjk`をインストール |
| flet-desktopはWeb版不要 | requirements-web.txtで除外。インストールするとエラーになる可能性 |
| RLS重複エラー | `CREATE POLICY`前に`DROP POLICY IF EXISTS`を入れてべき等にする |

---

## スクリーンショット一覧

`docs/screenshots_web_deploy/` に保存済み。

| ファイル名 | 内容 |
|-----------|------|
| `01_supabase_project_dashboard.png` | Supabaseプロジェクトダッシュボード（crypto-alert-hub） |
| `02_supabase_existing_tables.png` | 削除前の既存テーブル一覧（alerts, price_cache等） |
| `03_supabase_connection_string_direct.png` | Direct connection（IPv4非対応の警告あり） |
| `04_supabase_connection_string_session_pooler.png` | Session Pooler（IPv4対応 ✅） |
| `05_render_new_service_menu.png` | Renderサービス種別選択画面 |
| `06_render_github_connect.png` | RenderとGitHub連携画面（No repositories found） |
| `07_render_github_install.png` | GitHub App "Install Render"（Only select repositoriesを選択） |
| `08_render_web_service_selected.png` | Web Services選択後 |
| `09_render_github_auth.png` | GitHub sudo mode認証 |
| `10_render_github_confirm_access.png` | Confirm access（@skraytアカウント） |
| `11_render_repo_list.png` | skrayt/calc_eclがリポジトリ一覧に表示 ✅ |
| `12_render_configure_initial.png` | Render Configure画面（初期状態）。Branch/Build Command等の変更前 |
| `13_render_configure_filled.png` | Configure画面（設定後）。Branch=feature/web-deploy, Region=Singapore, Build Command変更済み |
| `14_render_instance_type.png` | Instance Type選択。Free（$0/month, 512MB RAM, 0.1 CPU）を選択 |
| `15_render_env_vars_empty.png` | Environment Variables入力欄（入力前） |
| `16_render_env_vars_filled.png` | 環境変数4つ入力完了（FLET_WEB / DATABASE_URL / DB_SCHEMA / DB_SSLMODE） |
| `17_render_advanced_secret_files.png` | Advanced > Secret Files（今回は使わない）とHealth Check Path |
| `18_render_building.png` | デプロイ開始・ビルド中（Awaiting build logs...） |
| `19_render_build_failed_apt_permission.png` | ビルド失敗①: apt-get 権限エラー（Permission denied on dpkg lock） |
| `20_render_building_retry.png` | sudoを追加して再ビルド中 |
| `21_render_build_failed_sudo_not_found.png` | ビルド失敗②: sudo: command not found（Renderはroot環境） |
| `22_render_build_success.png` | ビルド成功 🎉 → Deploying中 |
| `23_render_live.png` | **✅ Live** / calc_ecl is live! / https://calc-ecl.onrender.com |

---

## デプロイ成功

**公開URL**: https://calc-ecl.onrender.com
**ステータス**: Live 🟢
**達成日**: 2026-03-12

### ビルド失敗の履歴（ブログネタ）

| 試行 | Build Command | エラー | 原因 |
|-----|--------------|--------|------|
| 1回目 | `apt-get install -y fonts-noto-cjk && pip install -r requirements-web.txt` | Permission denied on dpkg lock | Renderビルド環境でapt-getが別プロセスにロックされている |
| 2回目 | `sudo apt-get install -y ...` | sudo: command not found | Renderはroot実行のためsudoが存在しない |
| 3回目 | `pip install -r requirements-web.txt`（apt.txtで分離） | なし ✅ | **apt.txt** に `fonts-noto-cjk` を記述するのがRender推奨方式 |

### 追加の修正点

- **Python 3.14.3 → 3.12.4固定**: `.python-version` ファイルで指定（3.14はパッケージ互換性問題）
- **apt.txt**: システムパッケージのインストールはこのファイルで管理するのがRenderの正式方式

---

## Phase W5: FilePickerのWeb対応

### 問題

FletデスクトップではFilePickerで `files[0].path` からローカルパスを取得できるが、Webでは `files[0].path` が `None` になるためCSVが読み込めない。

### 解決策: CSVペースト方式

`page.web` フラグで分岐し、Web時はCSV内容をテキストエリアに貼り付けるダイアログを表示する。

```python
def pick_csv(e):
    if page.web:
        # Web: テキストエリアにCSVを貼り付けるダイアログを表示
        page.show_dialog(web_csv_dialog)
        page.update()
    else:
        # デスクトップ: 従来のFilePickerを使用
        fp.pick_files(allowed_extensions=["csv"])
```

### 変更ファイル

| ファイル | 変更内容 |
|---------|---------|
| `pages/page_data_view.py` | pick_csv / pick_target_csv にpage.web分岐を追加、ペーストダイアログ実装 |
| `src/import_indicators.py` | `import_csv_gui()` に `csv_content` 引数追加（io.StringIO対応） |
| `src/import_targets.py` | `import_target_csv_gui()` に `csv_content` 引数追加（io.StringIO対応） |

**ポイント**: CSVペーストは手順が増えるが、Webではファイルパスが取得できないため必須の対応。

---

## Phase W6: 日本語フォント文字化け修正

### 問題

グラフのタイトル・軸ラベル・凡例の日本語が □□□ に文字化けする。

**原因**: `components/plot_utils.py` の `_jp_font_candidates` に Noto CJK フォント名が含まれていなかった。apt.txtで `fonts-noto-cjk` をインストールしているが、matplotlib がフォントキャッシュを再構築しないと認識されない場合がある。

### 解決策

`_jp_font_candidates` に Linux（Render/Ubuntu）用のフォント名を追加し、フォントが見つからない場合はキャッシュを自動再構築するフォールバックを実装。

```python
_jp_font_candidates = [
    "Noto Sans CJK JP",   # Linux（apt.txtでインストール）
    "Noto Sans CJK SC",   # Linux（代替名）
    "Noto Sans JP",       # Linux
    "NotoSansCJK-Regular",
    "Yu Gothic",          # Windows
    ...
]

# フォントが見つからない場合はキャッシュを再構築
if not _available_fonts:
    _fm.fontManager.rebuild()
    _available_fonts = _get_available_fonts(_jp_font_candidates)
```

**変更ファイル**: `components/plot_utils.py`

---

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `config/db.py` | DB接続（ローカル/Web切替） |
| `main.py` | Fletエントリポイント（デスクトップ/Web切替） |
| `render.yaml` | Renderデプロイ定義 |
| `requirements-web.txt` | Web版依存パッケージ |
| `apt.txt` | システムパッケージ（fonts-noto-cjk） |
| `.python-version` | Pythonバージョン固定（3.12.4） |
| `db/migrations/006_supabase_rls_setup.sql` | Supabase RLS設定 |
| `pages/page_data_view.py` | CSVペーストダイアログ（Web対応） |
| `src/import_indicators.py` | csv_content引数追加 |
| `src/import_targets.py` | csv_content引数追加 |
| `components/plot_utils.py` | Noto CJKフォント対応 |
