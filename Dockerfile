FROM python:3.12-slim

# 日本語フォントとビルド依存パッケージをインストール
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 依存パッケージをインストール（キャッシュ活用のため先にコピー）
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

# アプリケーションコードをコピー
COPY . .

# Cloud Run は PORT 環境変数を自動設定する（デフォルト: 8080）
ENV FLET_WEB=1
ENV DB_SCHEMA=calc_ecl
ENV DB_SSLMODE=require

CMD ["python", "main.py"]
