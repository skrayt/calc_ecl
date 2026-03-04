"""
統計ダッシュボードCSVをパースしてindicator_dataへインポートするスクリプト

使い方:
    python src/import_indicators.py indicator/DataSearchResult_XXXXXX.csv

処理の流れ:
    1. config/column_mapping.json からカラムマッピングを読み込む
    2. CSVに未知のカラムがあれば対話的にマッピングを追加（JSONに保存）
    3. indicator_sources に出典を登録（初回のみ）
    4. indicator_datasets にデータセット（取得回）を登録
    5. indicator_definitions に指標定義を登録（未登録の場合）
    6. CSVをパースして indicator_data へINSERT
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from config.db import get_connection

# マッピング設定ファイルのパス
MAPPING_FILE = PROJECT_ROOT / "config" / "column_mapping.json"


# =========================================================
# カラムマッピング管理
# =========================================================
def load_mapping() -> dict:
    """column_mapping.json を読み込む"""
    if not MAPPING_FILE.exists():
        return {"columns": {}, "skip_columns": ["時点", "地域コード", "地域", "注記"]}
    with open(MAPPING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_mapping(mapping: dict):
    """column_mapping.json に保存"""
    with open(MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"マッピング設定を保存: {MAPPING_FILE}")


def detect_base_year(col_name: str) -> str | None:
    """カラム名から基準年を自動検出する（例: '2020年基準' → '2020'）"""
    m = re.search(r"(\d{4})年基準", col_name)
    return m.group(1) if m else None


def detect_unit(col_name: str) -> str | None:
    """カラム名から単位を自動検出する（例: '【10億円】' → '10億円'）"""
    m = re.search(r"【(.+?)】", col_name)
    return m.group(1) if m else None


def detect_indicator_name(col_name: str) -> str:
    """カラム名から指標名を自動抽出する（単位部分を除去）"""
    return re.sub(r"【.+?】", "", col_name).strip()


def detect_frequency_from_csv(csv_path: str, col_index: int) -> str:
    """CSVデータをスキャンして、指定カラムに値がある行の時系列粒度を推定する。
    最も細かい粒度（月次＞四半期＞暦年＞年度）を代表粒度とする。"""
    import csv as csv_mod
    freq_priority = {"monthly": 0, "quarterly": 1, "calendar_year": 2, "fiscal_year": 3}
    best_freq = None

    with open(csv_path, encoding="utf-8") as f:
        reader = csv_mod.reader(f)
        next(reader)  # ヘッダースキップ
        for row in reader:
            if col_index >= len(row) or not row[col_index].strip():
                continue
            time_str = row[0].strip().strip('"')
            parsed = parse_time_point(time_str)
            if parsed is None:
                continue
            _, freq = parsed
            if best_freq is None or freq_priority.get(freq, 99) < freq_priority.get(best_freq, 99):
                best_freq = freq

    return best_freq or "monthly"


def resolve_mapping(csv_path: str, csv_columns: list[str]) -> dict:
    """CSVカラムとマッピング設定を突合する。

    ルールベースで自動検出できるもの:
        - 指標名: カラム名から単位【】を除去
        - 基準年: カラム名から「YYYY年基準」を抽出
        - 単位: カラム名から「【単位】」を抽出
        - 粒度: CSVデータをスキャンして値がある行の時点パターンから推定

    対話入力が必要なもの:
        - 指標コード（英語snake_case）: 日本語→英語は自動変換できない
    """
    mapping = load_mapping()
    known_columns = mapping["columns"]
    skip_columns = mapping.get("skip_columns", [])
    updated = False

    for col_index, col in enumerate(csv_columns):
        # 既知のカラム or スキップ対象
        if col in known_columns or col in skip_columns:
            continue

        # 「注記」カラムはスキップ（統計ダッシュボードCSVの構造上の列）
        if col == "注記" or col.startswith("注記"):
            continue

        # ルールベースで自動検出
        auto_name = detect_indicator_name(col)
        auto_base_year = detect_base_year(col)
        auto_unit = detect_unit(col)
        auto_frequency = detect_frequency_from_csv(csv_path, col_index)

        print(f"\n{'='*60}")
        print(f"未登録のカラム: 「{col}」")
        print(f"{'='*60}")
        print(f"  自動検出 - 指標名: {auto_name}")
        print(f"  自動検出 - 基準年: {auto_base_year or '(なし)'}")
        print(f"  自動検出 - 単位:   {auto_unit or '(なし)'}")
        print(f"  自動検出 - 粒度:   {auto_frequency}")
        print()

        action = input("  (a)追加 / (s)スキップ登録 / (i)今回だけ無視 ? [a/s/i]: ").strip().lower()

        if action == "s":
            skip_columns.append(col)
            updated = True
            print(f"  → スキップ対象に追加")
        elif action == "a":
            # 指標コードのみ対話入力（自動変換不可能なため）
            code = input("  指標コード (英語snake_case, 例: gdp_nominal_2025base): ").strip()
            if not code:
                print("  → コードが空のためスキップします")
                continue

            known_columns[col] = {
                "code": code,
                "name": auto_name,
                "unit": auto_unit,
                "base_year": auto_base_year,
                "frequency": auto_frequency,
            }
            updated = True
            print(f"  → 自動登録: {code} (名前={auto_name}, 単位={auto_unit}, "
                  f"基準年={auto_base_year}, 粒度={auto_frequency})")
        else:
            print("  → 今回は無視します")

    if updated:
        mapping["columns"] = known_columns
        mapping["skip_columns"] = skip_columns
        save_mapping(mapping)

    return mapping


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


def ensure_indicator_definitions(cur, source_id: int, column_mapping: dict):
    """indicator_definitions に未登録の指標を登録"""
    for _, col_def in column_mapping.items():
        cur.execute(
            "SELECT indicator_id FROM indicator_definitions WHERE indicator_code = %s",
            (col_def["code"],),
        )
        if cur.fetchone():
            continue

        cur.execute(
            """INSERT INTO indicator_definitions
               (indicator_code, indicator_name, base_year, unit, frequency, source_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                col_def["code"],
                col_def["name"],
                col_def["base_year"],
                col_def["unit"],
                col_def.get("frequency", "monthly"),
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

    # カラムマッピングの解決（未知カラムがあれば自動検出＋指標コードのみ対話入力）
    mapping = resolve_mapping(csv_path, list(df.columns))
    column_mapping = mapping["columns"]

    # マッピング済みカラムの特定
    value_columns = []
    columns = list(df.columns)
    for i, col in enumerate(columns):
        if col in column_mapping:
            value_columns.append((col, column_mapping[col]))

    if not value_columns:
        print("エラー: マッピング済みの指標カラムがありません")
        sys.exit(1)

    print(f"マッピング済み指標: {[m['code'] for _, m in value_columns]}")

    # 注記カラム名の重複を解消するためインデックスベースで管理
    note_col_indices = {}
    for i, col in enumerate(columns):
        if col in column_mapping:
            # 直後が「注記」系なら記録
            if i + 1 < len(columns) and (columns[i + 1] == "注記" or columns[i + 1].startswith("注記")):
                note_col_indices[col] = i + 1

    conn = get_connection()
    try:
        cur = conn.cursor()

        # 1. データソース登録
        source_id = ensure_source(cur)
        print(f"データソースID: {source_id}")

        # 2. 指標定義登録
        ensure_indicator_definitions(cur, source_id, column_mapping)
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

            for col_name, col_def in value_columns:
                val = row[col_name]
                if pd.isna(val) or val == "":
                    continue

                # 数値変換
                try:
                    num_val = float(val.replace(",", ""))
                    # 整数として扱える場合はintに
                    if num_val == int(num_val):
                        indicators[col_def["code"]] = int(num_val)
                    else:
                        indicators[col_def["code"]] = num_val
                except ValueError:
                    continue

                # 注記
                if col_name in note_col_indices:
                    note_idx = note_col_indices[col_name]
                    note_val = row.iloc[note_idx]
                    if pd.notna(note_val) and note_val != "":
                        notes[col_def["code"]] = note_val

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
