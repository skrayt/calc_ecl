"""DB接続設定"""
import configparser
from pathlib import Path

import psycopg2

# config/db.ini を読み込む
_CONFIG_PATH = Path(__file__).parent / "db.ini"


def _load_config() -> dict:
    """db.ini から接続情報を読み込む"""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"設定ファイルが見つかりません: {_CONFIG_PATH}\n"
            f"db.ini.example をコピーして db.ini を作成してください。"
        )
    parser = configparser.ConfigParser()
    parser.read(_CONFIG_PATH, encoding="utf-8")
    return dict(parser["postgresql"])


def get_connection():
    """PostgreSQL接続を返す

    DB名: craft、スキーマ: calc_ecl
    接続後に search_path を calc_ecl に設定する。
    """
    cfg = _load_config()
    conn = psycopg2.connect(
        host=cfg.get("host", "localhost"),
        port=cfg.get("port", "5432"),
        dbname=cfg.get("dbname", "craft"),
        user=cfg.get("user", "postgres"),
        password=cfg.get("password", ""),
    )
    # スキーマを calc_ecl に設定
    schema = cfg.get("schema", "calc_ecl")
    with conn.cursor() as cur:
        cur.execute(f"SET search_path TO {schema}")
    conn.commit()
    return conn
