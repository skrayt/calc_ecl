# WinPython 本番環境構築マニュアル

本マニュアルでは、**オンライン環境**で WinPython + 仮想環境を準備し、**オフラインの本番環境**に持ち込む手順を説明します。

---

## 前提条件

- 本番環境: Windows（インターネット接続なし）
- 準備環境: Windows（インターネット接続あり）
- 必要ディスク容量: 約 3GB（WinPython + 仮想環境 + パッケージ）

---

## 手順概要

```
[オンライン環境]                      [オフライン本番環境]
 ① WinPython ダウンロード
 ② 展開・仮想環境作成
 ③ pip install -r requirements.txt     
 ④ フォルダごとUSB等にコピー ------→ ⑤ USB から配置
                                      ⑥ アプリ起動
```

---

## ① WinPython のダウンロード（オンライン環境）

1. 以下のいずれかから WinPython をダウンロードします：
   - **GitHub**: https://github.com/winpython/winpython/releases
   - **SourceForge**: https://sourceforge.net/projects/winpython/

2. 推奨バージョン: **WinPython 2025-05 post1** 以降（Python 3.13 同梱版）
   - ファイル名例: `Winpython64-3.13.11.0.exe`
   - **dot 版**（軽量版）でも OK: `Winpython64-3.13.11.0dot.exe`

> **注意**: 本プロジェクトは Python 3.13 + Flet 0.81.0 で開発されています。  
> Python 3.12 系の WinPython を使う場合、一部パッケージのバージョンが異なる可能性があります。

---

## ② WinPython の展開（オンライン環境）

1. ダウンロードした `.exe` を実行し、任意のフォルダに展開します：
   ```
   例: D:\WinPython\
   ```

2. 展開後のフォルダ構成：
   ```
   D:\WinPython\
   ├── python-3.13.x.amd64\    ← Python 本体
   ├── scripts\                 ← 管理スクリプト
   ├── WinPython Powershell Prompt.exe
   ├── WinPython Command Prompt.exe
   └── ...
   ```

---

## ③ 仮想環境の作成とパッケージインストール（オンライン環境）

### 3-1. WinPython コマンドプロンプトを開く

`WinPython Command Prompt.exe` をダブルクリックします。  
これにより、WinPython 同梱の Python にパスが通った状態のコマンドプロンプトが起動します。

### 3-2. プロジェクトフォルダに移動

```cmd
cd /d D:\work
git clone https://github.com/skrayt/calc_ecl.git
cd calc_ecl
```

> Git が使えない場合は、GitHub から ZIP でダウンロードして展開してください。

### 3-3. 仮想環境を作成

```cmd
python -m venv .venv
```

### 3-4. 仮想環境を有効化

```cmd
.venv\Scripts\activate
```

プロンプトの先頭に `(.venv)` と表示されれば成功です。

### 3-5. パッケージをインストール

```cmd
pip install -r requirements.txt
```

全パッケージのダウンロード＆インストールが完了するまで待ちます（数分かかります）。

### 3-6. インストール確認

```cmd
python -c "import flet; print(flet.version)"
python -c "import pandas; print(pandas.__version__)"
python -c "import statsmodels; print(statsmodels.__version__)"
```

それぞれバージョンが表示されれば OK です。

---

## ④ オフライン環境への持ち込み準備

### 持ち込むフォルダ

以下の **2つのフォルダ** を USB メモリ等にコピーします：

| コピー元 | 内容 |
|---|---|
| `D:\WinPython\` フォルダ全体 | Python 本体 + 管理ツール |
| `D:\work\calc_ecl\` フォルダ全体 | アプリ + `.venv`（仮想環境） |

> `.venv` フォルダには全パッケージが含まれているため、  
> オフライン環境で再度 `pip install` する必要はありません。

### フォルダサイズの目安

| フォルダ | サイズ目安 |
|---|---|
| WinPython 本体 | 約 800MB〜1.5GB |
| calc_ecl + .venv | 約 500MB〜1GB |

---

## ⑤ オフライン本番環境への配置

1. USB メモリから本番環境の PC にフォルダをコピーします：
   ```
   C:\Apps\WinPython\          ← WinPython 本体
   C:\Apps\calc_ecl\           ← アプリ + 仮想環境
   ```

2. コピー先のパスは自由ですが、**日本語や空白を含まないパス**を推奨します。

---

## ⑥ 本番環境でのアプリ起動

### 方法 A: コマンドプロンプトから起動

1. `WinPython Command Prompt.exe` を起動
2. 以下のコマンドを実行：

```cmd
cd /d C:\Apps\calc_ecl
.venv\Scripts\activate
set PYTHONPATH=.
python main.py
```

### 方法 B: バッチファイルで起動（推奨）

`calc_ecl` フォルダ内に `start_app.bat` を作成しておくと便利です：

```bat
@echo off
echo ECL将来予想モデルを起動します...

REM --- パス設定（環境に合わせて変更） ---
set APP_DIR=%~dp0
set VENV_DIR=%APP_DIR%.venv

REM --- 仮想環境を有効化 ---
call "%VENV_DIR%\Scripts\activate.bat"

REM --- アプリ起動 ---
set PYTHONPATH=%APP_DIR%
cd /d "%APP_DIR%"
python main.py

pause
```

このバッチファイルをダブルクリックするだけでアプリが起動します。

---

## トラブルシューティング

### 「python が見つかりません」エラー  
→ `WinPython Command Prompt.exe` から起動しているか確認してください。通常のコマンドプロンプトでは WinPython の Python にパスが通っていません。

### 仮想環境の activate でエラー
→ PowerShell の場合、実行ポリシーの変更が必要なことがあります：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### パッケージの import エラー
→ 仮想環境が有効化されているか確認してください（プロンプト先頭に `(.venv)` が表示されているか）。

### Docker（PostgreSQL）への接続エラー
→ 本番環境でも Docker Desktop が起動しており、`docker-compose up -d` でコンテナが稼働していることを確認してください。  
→ `config/db.ini` の接続先設定が正しいか確認してください。

---

## 仮想環境のパス修正（必要な場合）

`.venv` を別のマシンにコピーした場合、内部のパスが元のマシンを参照していることがあります。通常は問題なく動作しますが、もしエラーが出る場合は仮想環境を再作成してください：

```cmd
REM 古い仮想環境を削除
rmdir /s /q .venv

REM WinPython Command Prompt から再作成
python -m venv .venv
.venv\Scripts\activate

REM オフラインでのインストール（事前にwheelを用意する場合）
pip install --no-index --find-links=wheels/ -r requirements.txt
```

> オフラインで pip install する場合は、オンライン環境で事前にパッケージをダウンロードしておく必要があります：
> ```cmd
> pip download -r requirements.txt -d wheels/
> ```
