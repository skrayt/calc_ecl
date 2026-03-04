"""
統計ダッシュボードCSVをパースしてindicator_dataへインポートするスクリプト

使い方:
    python src/import_indicators.py indicator/DataSearchResult_XXXXXX.csv

処理の流れ:
    1. indicator_sources に出典を登録（初回のみ）
    2. indicator_datasets にデータセット（取得回）を登録
    3. indicator_definitions に指標定義を登録（未登録の場合）
    4. CSVをパースして indicator_data へINSERT
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.db import get_connection


# =========================================================
# CSVカラム → 指標コードのマッピング定義
# =========================================================
COLUMN_MAPPING = {
    "総人口（総数）【人】": {
        "code": "total_population",
        "name": "総人口（総数）",
        "unit": "人",
        "base_year": None,
    },
    "完全失業率（男女計）【%】": {
        "code": "unemployment_rate",
        "name": "完全失業率（男女計）",
        "unit": "%",
        "base_year": None,
    },
    "景気動向指数（一致）2020年基準": {
        "code": "ci_index_2020base",
        "name": "景気動向指数（一致）2020年基準",
        "unit": None,
        "base_year": "2020",
    },
    "国内総生産（支出側）（名目）2020年基準【10億円】": {
        "code": "gdp_nominal_2020base",
        "name": "国内総生産（支出側）（名目）2020年基準",
        "unit": "10億円",
        "base_year": "2020",
    },
    "県内総生産（名目）2015年基準【百万円】": {
        "code": "prefectural_gdp_2015base",
        "name": "県内総生産（名目）2015年基準",
        "unit": "百万円",
        "base_year": "2015",
    },
}

# 各指標が取り得る時系列粒度
INDICATOR_FREQUENCIES = {
    "total_population": ["monthly", "calendar_year"],
    "unemployment_rate": ["monthly", "quarterly", "calendar_year", "fiscal_year"],
    "ci_index_2020base": ["monthly"],
    "gdp_nominal_2020base": ["quarterly", "calendar_year", "fiscal_year"],
    "prefectural_gdp_2015base": ["fiscal_year"],
}


# =========================================================
# 時点パーサー
# =========================================================
def parse_time_point(time_str: str) -> tuple[date, str] | None:
    """
    CSVの「時点」列をパースして (reference_date, frequency) を返す。
    パースできない場合はNoneを返す。

    例:
        '2025年1月'      → (date(2025,1,1), 'monthly')
        '2025年1-3月期'  → (date(2025,1,1), 'quarterly')
        '2025年'         → (date(2025,1,1), 'calendar_year')
        '2025年度'       → (date(2025,4,1), 'fiscal_year')
    """
    # 月次: 2025年1月
    m = re.match(r"^(\d{4})年(\d{1,2})月$", time_str)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1), "monthly"

    # 四半期: 2025年1-3月期
    m = re.match(r"^(\d{4})年(\d{1,2})-(\d{1,2})月期$", time_str)
    if m:
        return date(int(m.group(1)), int(m.group(2)), 1), "quarterly"

    # 年度: 2025年度
    m = re.match(r"^(\d{4})年度$", time_str)
    if m:
        return date(int(m.group(1)), 4, 1), "fiscal_year"

    # 暦年: 2025年
    m = re.match(r"^(\d{4})年$", time_str)
    if m:
        return date(int(m.group(1)), 1, 1), "calendar_year"

    return None


# =========================================================
# DB操作
# =========================================================
def ensure_source(cur) -> int:
    """indicator_sources に e-Stat を登録（存在すればそのIDを返す）"""
    cur.execute(
        "SELECT source_id FROM indicator_sources WHERE source_name = %s",
        ("e-Stat統計ダッシュボード",),
    )
    row = cur.fetchone()
    if row:
        return row[0]

    cur.execute(
        """INSERT INTO indicator_sources (source_name, source_url, description)
           VALUES (%s, %s, %s) RETURNING source_id""",
        (
            "e-Stat統計ダッシュボード",
            "https://dashboard.e-stat.go.jp/",
            "政府統計の総合窓口 統計ダッシュボード",
        ),
    )
    return cur.fetchone()[0]


def create_dataset(cur, source_id: int, retrieved_at: date, indicator_keys: list) -> int:
    """indicator_datasets にデータセットを登録"""
    dataset_name = f"{retrieved_at.strftime('%Y年%m月')}取得"
    cur.execute(
        """INSERT INTO indicator_datasets
           (dataset_name, retrieved_at, source_id, indicator_keys, description)
           VALUES (%s, %s, %s, %s, %s) RETURNING dataset_id""",
        (
            dataset_name,
            retrieved_at,
            source_id,
            json.dumps(indicator_keys),
            f"統計ダッシュボードから{retrieved_at}に取得",
        ),
    )
    return cur.fetchone()[0]


def ensure_indicator_definitions(cur, source_id: int):
    """indicator_definitions に未登録の指標を登録"""
    for col_name, mapping in COLUMN_MAPPING.items():
        # 指標が取り得る最も細かい粒度を代表として登録
        frequencies = INDICATOR_FREQUENCIES.get(mapping["code"], ["monthly"])
        freq = frequencies[0]

        cur.execute(
            "SELECT indicator_id FROM indicator_definitions WHERE indicator_code = %s",
            (mapping["code"],),
        )
        if cur.fetchone():
            continue

        cur.execute(
            """INSERT INTO indicator_definitions
               (indicator_code, indicator_name, base_year, unit, frequency, source_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                mapping["code"],
                mapping["name"],
                mapping["base_year"],
                mapping["unit"],
                freq,
                source_id,
            ),
        )


# =========================================================
# CSVパース & インポート
# =========================================================
def import_csv(csv_path: str, retrieved_at: date):
    """メインのインポート処理"""
    # CSV読み込み
    df = pd.read_csv(csv_path, encoding="utf-8", dtype=str)
    print(f"CSV読み込み完了: {len(df)}行")

    # 注記カラムの位置を特定
    # CSVは [指標値, 注記, 指標値, 注記, ...] の構造
    value_columns = []
    note_columns = []
    columns = list(df.columns)
    for i, col in enumerate(columns):
        if col in COLUMN_MAPPING:
            value_columns.append((col, COLUMN_MAPPING[col]))
            # 直後の「注記」カラムを対応する注記列とする
            if i + 1 < len(columns) and columns[i + 1] == "注記":
                note_columns.append((col, columns[i + 1]))
            elif i + 1 < len(columns) and columns[i + 1].startswith("注記"):
                note_columns.append((col, columns[i + 1]))

    # 注記カラム名の重複を解消するためインデックスベースで管理
    note_col_indices = {}
    for i, col in enumerate(columns):
        if col in COLUMN_MAPPING:
            # 直後が「注記」系なら記録
            if i + 1 < len(columns):
                note_col_indices[col] = i + 1

    conn = get_connection()
    try:
        cur = conn.cursor()

        # 1. データソース登録
        source_id = ensure_source(cur)
        print(f"データソースID: {source_id}")

        # 2. 指標定義登録
        ensure_indicator_definitions(cur, source_id)
        print("指標定義マスタ登録完了")

        # 3. データセット登録
        indicator_keys = [m["code"] for _, m in value_columns]
        dataset_id = create_dataset(cur, source_id, retrieved_at, indicator_keys)
        print(f"データセットID: {dataset_id} ({retrieved_at}取得)")

        # 4. 行ごとにパースしてINSERT
        inserted = 0
        skipped = 0

        for row_idx, row in df.iterrows():
            time_str = row["時点"]
            parsed = parse_time_point(time_str)
            if parsed is None:
                skipped += 1
                continue

            ref_date, frequency = parsed
            region_code = row["地域コード"]
            region_name = row["地域"]

            # 指標値をJSONBに組み立て
            indicators = {}
            notes = {}

            for col_name, mapping in value_columns:
                val = row[col_name]
                if pd.isna(val) or val == "":
                    continue

                # 数値変換
                try:
                    num_val = float(val.replace(",", ""))
                    # 整数として扱える場合はintに
                    if num_val == int(num_val):
                        indicators[mapping["code"]] = int(num_val)
                    else:
                        indicators[mapping["code"]] = num_val
                except ValueError:
                    continue

                # 注記
                if col_name in note_col_indices:
                    note_idx = note_col_indices[col_name]
                    note_val = row.iloc[note_idx]
                    if pd.notna(note_val) and note_val != "":
                        notes[mapping["code"]] = note_val

            # 指標が1つもなければスキップ
            if not indicators:
                skipped += 1
                continue

            cur.execute(
                """INSERT INTO indicator_data
                   (dataset_id, reference_date, frequency, region_code, region_name, indicators, notes)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (dataset_id, reference_date, frequency, region_code)
                   DO UPDATE SET
                       indicators = indicator_data.indicators || EXCLUDED.indicators,
                       notes = COALESCE(indicator_data.notes, '{}'::jsonb) || COALESCE(EXCLUDED.notes, '{}'::jsonb),
                       imported_at = now()""",
                (
                    dataset_id,
                    ref_date,
                    frequency,
                    region_code,
                    region_name,
                    json.dumps(indicators),
                    json.dumps(notes) if notes else None,
                ),
            )
            inserted += 1

        conn.commit()
        print(f"\n完了: {inserted}件INSERT, {skipped}件スキップ")

    except Exception as e:
        conn.rollback()
        print(f"エラー: {e}")
        raise
    finally:
        conn.close()


# =========================================================
# エントリポイント
# =========================================================
def main():
    parser = argparse.ArgumentParser(description="統計ダッシュボードCSVをDBにインポート")
    parser.add_argument("csv_path", help="CSVファイルのパス")
    parser.add_argument(
        "--retrieved-at",
        type=lambda s: date.fromisoformat(s),
        default=date.today(),
        help="データ取得日 (YYYY-MM-DD形式、デフォルト: 今日)",
    )
    args = parser.parse_args()

    if not Path(args.csv_path).exists():
        print(f"ファイルが見つかりません: {args.csv_path}")
        sys.exit(1)

    import_csv(args.csv_path, args.retrieved_at)


if __name__ == "__main__":
    main()
