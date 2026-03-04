@echo off
echo ============================================
echo   ECL将来予想モデル 起動スクリプト
echo ============================================
echo.

REM --- パス設定（このバッチファイルの場所を基準にする） ---
set APP_DIR=%~dp0
set VENV_DIR=%APP_DIR%.venv

REM --- 仮想環境の存在チェック ---
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [エラー] 仮想環境が見つかりません: %VENV_DIR%
    echo docs\winpython_setup_guide.md を参照して環境を構築してください。
    pause
    exit /b 1
)

REM --- 仮想環境を有効化 ---
call "%VENV_DIR%\Scripts\activate.bat"

REM --- アプリ起動 ---
set PYTHONPATH=%APP_DIR%
cd /d "%APP_DIR%"
echo アプリを起動しています...
python main.py

pause
