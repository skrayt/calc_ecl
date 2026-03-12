"""DB接続設定

接続情報の優先順位:
1. config/db.ini が存在する → configparser で読む（ローカル開発用）
2. db.ini が存在しない → 環境変数から読む（Web/Render本番用）
   - DATABASE_URL があれば → URLをパースして接続パラメータに変換
   - DB_HOST 等の個別環境変数があれば → dictに変換
3. どちらも無い → FileNotFoundError（従来と同じ）
"""
import configparser
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

# config/db.ini を読み込む
_CONFIG_PATH = Path(__file__).parent / "db.ini"


def _load_config() -> dict:
    """接続情報を読み込む（db.ini → 環境変数の順で試行）"""
    # 1. db.ini が存在する場合（ローカル開発）
    if _CONFIG_PATH.exists():
        parser = configparser.ConfigParser()
        parser.read(_CONFIG_PATH, encoding="utf-8")
        return dict(parser["postgresql"])

    # 2. 環境変数から読む（Web/Render本番）
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return _parse_database_url(database_url)

    # 個別環境変数
    db_host = os.environ.get("DB_HOST", "").strip()
    if db_host:
        return {
            "host": db_host,
            "port": os.environ.get("DB_PORT", "5432"),
            "dbname": os.environ.get("DB_NAME", "postgres"),
            "user": os.environ.get("DB_USER", "postgres"),
            "password": os.environ.get("DB_PASSWORD", ""),
            "schema": os.environ.get("DB_SCHEMA", "calc_ecl"),
            "sslmode": os.environ.get("DB_SSLMODE", "require"),
        }

    # 3. どちらも無い
    raise FileNotFoundError(
        f"DB接続情報が見つかりません。\n"
        f"ローカル開発: {_CONFIG_PATH} を作成してください（db.ini.example を参照）。\n"
        f"Web/本番: DATABASE_URL または DB_HOST 等の環境変数を設定してください。"
    )


def _parse_database_url(url: str) -> dict:
    """DATABASE_URL（postgres://user:pass@host:port/dbname）を接続パラメータに変換する"""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "dbname": (parsed.path or "/postgres").lstrip("/"),
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "schema": os.environ.get("DB_SCHEMA", "calc_ecl"),
        "sslmode": os.environ.get("DB_SSLMODE", "require"),
    }


def get_connection():
    """PostgreSQL接続を返す

    DB名: craft（ローカル）/ postgres（Supabase）、スキーマ: calc_ecl
    接続後に search_path を calc_ecl に設定する。
    Supabase接続時は sslmode=require が自動設定される。
    """
    cfg = _load_config()

    # 接続パラメータ構築
    connect_params = {
        "host": cfg.get("host", "localhost"),
        "port": cfg.get("port", "5432"),
        "dbname": cfg.get("dbname", "craft"),
        "user": cfg.get("user", "postgres"),
        "password": cfg.get("password", ""),
    }
    # sslmode が設定されている場合のみ追加（ローカルでは不要なため）
    sslmode = cfg.get("sslmode", "").strip()
    if sslmode:
        connect_params["sslmode"] = sslmode

    conn = psycopg2.connect(**connect_params)

    # スキーマを calc_ecl に設定
    schema = cfg.get("schema", "calc_ecl")
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}")
    conn.commit()
    return conn
