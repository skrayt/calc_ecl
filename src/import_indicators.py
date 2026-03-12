"""
統計ダッシュボードCSVをパースしてindicator_dataへインポートするスクリプト

使い方:
    python src/import_indicators.py indicator/DataSearchResult_XXXXXX.csv

処理の流れ:
    1. config/column_mapping.json からカラムマッピングを読み込む
    2. CSVに未知のカラムがあれば対話的にマッピングを追加（JSONに保存）
    3. indicator_sources に出典を登録（初回のみ）
    4. indicator_datasets にデータセット（決算年月単位）を登録または更新
    5. indicator_definitions に指標定義を登録（未登録の場合）
    6. CSVをパースして indicator_data へINSERT
"""
import argparse
import calendar
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


def detect_frequency_from_csv(csv_path: str = None, col_index: int = 0,
                               csv_content: str = None) -> str:
    """CSVデータをスキャンして、指定カラムに値がある行の時系列粒度を推定する。
    最も細かい粒度（月次＞四半期＞暦年＞年度）を代表粒度とする。
    csv_path または csv_content のいずれかを指定する。"""
    import csv as csv_mod
    import io
    freq_priority = {"monthly": 0, "quarterly": 1, "calendar_year": 2, "fiscal_year": 3}
    best_freq = None

    if csv_content is not None:
        f = io.StringIO(csv_content)
    else:
        f = open(csv_path, encoding="utf-8")

    try:
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
    finally:
        f.close()

    return best_freq or "monthly"


def detect_unknown_columns(csv_path: str = None, csv_columns: list[str] = None,
                            csv_content: str = None) -> list[tuple[str, int, dict]]:
    """未知のカラムを検出し、自動検出情報とともに返す。
    csv_path または csv_content のいずれかを指定する。

    Returns
    -------
    list of (col_name, col_index, auto_info)
        auto_info: {"name", "base_year", "unit", "frequency"}
    """
    mapping = load_mapping()
    known_columns = mapping["columns"]
    skip_columns = mapping.get("skip_columns", [])
    unknowns = []

    for col_index, col in enumerate(csv_columns):
        if col in known_columns or col in skip_columns:
            continue
        if col == "注記" or col.startswith("注記"):
            continue

        auto_info = {
            "name": detect_indicator_name(col),
            "base_year": detect_base_year(col),
            "unit": detect_unit(col),
            "frequency": detect_frequency_from_csv(csv_path, col_index, csv_content=csv_content),
        }
        unknowns.append((col, col_index, auto_info))

    return unknowns


def apply_mapping_results(results: list[dict]) -> dict:
    """ユーザーの入力結果をマッピングファイルに保存する。

    Parameters
    ----------
    results : list of dict
        各要素: {"col": col_name, "action": "add"|"skip"|"ignore",
                 "code": indicator_code, "auto_info": {...}}

    Returns
    -------
    dict
        更新後のマッピング設定
    """
    mapping = load_mapping()
    known_columns = mapping["columns"]
    skip_columns = mapping.get("skip_columns", [])
    updated = False

    for r in results:
        if r["action"] == "skip":
            skip_columns.append(r["col"])
            updated = True
        elif r["action"] == "add" and r.get("code"):
            ai = r["auto_info"]
            known_columns[r["col"]] = {
                "code": r["code"],
                "name": ai["name"],
                "unit": ai["unit"],
                "base_year": ai["base_year"],
                "frequency": ai["frequency"],
            }
            updated = True

    if updated:
        mapping["columns"] = known_columns
        mapping["skip_columns"] = skip_columns
        save_mapping(mapping)

    return mapping


def resolve_mapping(csv_path: str, csv_columns: list[str]) -> dict:
    """（既存のターミナル用）CSVカラムとマッピング設定を突合する。"""
    mapping = load_mapping()
    known_columns = mapping["columns"]
    skip_columns = mapping.get("skip_columns", [])
    updated = False

    for col_index, col in enumerate(csv_columns):
        if col in known_columns or col in skip_columns:
            continue
        if col == "注記" or col.startswith("注記"):
            continue

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
        elif action == "a":
            code = input("  指標コード (英語snake_case): ").strip()
            if not code:
                continue
            known_columns[col] = {
                "code": code,
                "name": auto_name,
                "unit": auto_unit,
                "base_year": auto_base_year,
                "frequency": auto_frequency,
            }
            updated = True
        else:
            continue

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
    reference_date は期末日（月末・四半期末・年末・年度末）で格納する。
    パースできない場合はNoneを返す。

    例:
        '2025年1月'      → (date(2025,1,31), 'monthly')      # 月末日
        '2025年1-3月期'  → (date(2025,3,31), 'quarterly')    # 四半期末
        '2025年'         → (date(2025,12,31), 'calendar_year') # 12月31日
        '2025年度'       → (date(2026,3,31), 'fiscal_year')  # 翌年3月31日
    """
    # 月次: 2025年1月 → 月末日
    m = re.match(r"^(\d{4})年(\d{1,2})月$", time_str)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, last_day), "monthly"

    # 四半期: 2025年1-3月期 → 四半期末日（終了月の末日）
    m = re.match(r"^(\d{4})年(\d{1,2})-(\d{1,2})月期$", time_str)
    if m:
        year, end_month = int(m.group(1)), int(m.group(3))
        last_day = calendar.monthrange(year, end_month)[1]
        return date(year, end_month, last_day), "quarterly"

    # 年度: 2025年度 → 翌年3月31日
    m = re.match(r"^(\d{4})年度$", time_str)
    if m:
        year = int(m.group(1))
        return date(year + 1, 3, 31), "fiscal_year"

    # 暦年: 2025年 → 12月31日
    m = re.match(r"^(\d{4})年$", time_str)
    if m:
        year = int(m.group(1))
        return date(year, 12, 31), "calendar_year"

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


def find_dataset_by_fiscal_ym(cur, fiscal_year_month: date) -> int | None:
    """指定された決算年月のデータセットIDを検索する。なければNoneを返す。"""
    cur.execute(
        "SELECT dataset_id FROM indicator_datasets WHERE fiscal_year_month = %s",
        (fiscal_year_month,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def replace_dataset_data(cur, dataset_id: int):
    """指定データセットのindicator_dataを全削除する（全置換の前処理）"""
    cur.execute(
        "DELETE FROM indicator_data WHERE dataset_id = %s",
        (dataset_id,),
    )


def update_dataset_metadata(cur, dataset_id: int, retrieved_at: date,
                            indicator_keys: list, source_id: int):
    """既存データセットのメタデータを更新する"""
    dataset_name = f"{retrieved_at.strftime('%Y年%m月')}取得"
    cur.execute(
        """UPDATE indicator_datasets
           SET dataset_name = %s, retrieved_at = %s, indicator_keys = %s,
               source_id = %s, description = %s
           WHERE dataset_id = %s""",
        (
            dataset_name,
            retrieved_at,
            json.dumps(indicator_keys),
            source_id,
            f"統計ダッシュボードから{retrieved_at}に取得",
            dataset_id,
        ),
    )


def create_dataset(cur, source_id: int, retrieved_at: date,
                    indicator_keys: list, fiscal_year_month: date) -> int:
    """indicator_datasets にデータセットを新規登録"""
    dataset_name = f"{retrieved_at.strftime('%Y年%m月')}取得"
    cur.execute(
        """INSERT INTO indicator_datasets
           (dataset_name, retrieved_at, source_id, indicator_keys, description, fiscal_year_month)
           VALUES (%s, %s, %s, %s, %s, %s) RETURNING dataset_id""",
        (
            dataset_name,
            retrieved_at,
            source_id,
            json.dumps(indicator_keys),
            f"統計ダッシュボードから{retrieved_at}に取得",
            fiscal_year_month,
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
def import_csv_gui(csv_path: str = None, retrieved_at: date = None,
                   fiscal_year_month: date = None,
                   progress_callback=None, csv_content: str = None):
    """GUI経由のインポート実行

    Parameters
    ----------
    csv_path : str, optional
        CSVファイルパス（デスクトップ時）
    retrieved_at : date
        データ取得日（通常は今日）
    fiscal_year_month : date
        決算年月（月初日で指定。例: 2026-03-01 = 2026年3月期）
    progress_callback : callable, optional
        進捗コールバック (current, total)
    csv_content : str, optional
        CSV文字列（Web時。csv_pathの代わりに使用）
    """
    import io
    if csv_content is not None:
        df = pd.read_csv(io.StringIO(csv_content), dtype=str)
    else:
        df = pd.read_csv(csv_path, encoding="utf-8", dtype=str)

    # マッピング読み込み（未知カラムの解決はUI側で事前に完了済み）
    mapping = load_mapping()

    column_mapping = mapping["columns"]
    value_columns = []
    columns = list(df.columns)
    for i, col in enumerate(columns):
        if col in column_mapping:
            value_columns.append((col, column_mapping[col]))

    if not value_columns:
        raise ValueError("マッピング済みの指標カラムがありません")

    note_col_indices = {}
    for i, col in enumerate(columns):
        if col in column_mapping:
            if i + 1 < len(columns) and (columns[i + 1] == "注記" or columns[i + 1].startswith("注記")):
                note_col_indices[col] = i + 1

    conn = get_connection()
    try:
        cur = conn.cursor()
        source_id = ensure_source(cur)
        ensure_indicator_definitions(cur, source_id, column_mapping)

        indicator_keys = [m["code"] for _, m in value_columns]

        # 決算年月で既存データセットを検索
        existing_id = find_dataset_by_fiscal_ym(cur, fiscal_year_month)
        if existing_id is not None:
            # 全置換: 既存データを削除してメタデータを更新
            replace_dataset_data(cur, existing_id)
            update_dataset_metadata(cur, existing_id, retrieved_at, indicator_keys, source_id)
            dataset_id = existing_id
        else:
            # 新規作成
            dataset_id = create_dataset(cur, source_id, retrieved_at, indicator_keys, fiscal_year_month)

        total = len(df)
        inserted = 0
        skipped = 0

        for idx, row in df.iterrows():
            if progress_callback and idx % 10 == 0:
                progress_callback(idx, total)

            time_str = row["時点"]
            parsed = parse_time_point(time_str)
            if parsed is None:
                skipped += 1
                continue

            ref_date, frequency = parsed
            region_code = row["地域コード"]
            region_name = row["地域"]

            indicators = {}
            notes = {}

            for col_name, col_def in value_columns:
                val = row[col_name]
                if pd.isna(val) or val == "":
                    continue

                try:
                    num_val = float(val.replace(",", ""))
                    indicators[col_def["code"]] = int(num_val) if num_val == int(num_val) else num_val
                except ValueError:
                    continue

                if col_name in note_col_indices:
                    note_idx = note_col_indices[col_name]
                    note_val = row.iloc[note_idx]
                    if pd.notna(note_val) and note_val != "":
                        notes[col_def["code"]] = note_val

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
                (dataset_id, ref_date, frequency, region_code, region_name,
                 json.dumps(indicators), json.dumps(notes) if notes else None),
            )
            inserted += 1

        conn.commit()
        is_replace = existing_id is not None
        return {
            "inserted": inserted,
            "skipped": skipped,
            "dataset_id": dataset_id,
            "replaced": is_replace,
        }

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def import_csv(csv_path: str, retrieved_at: date, fiscal_year_month: date):
    """メインのインポート処理（CLI用）"""
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

        # 3. データセット登録（決算年月ベース）
        indicator_keys = [m["code"] for _, m in value_columns]
        existing_id = find_dataset_by_fiscal_ym(cur, fiscal_year_month)
        if existing_id is not None:
            replace_dataset_data(cur, existing_id)
            update_dataset_metadata(cur, existing_id, retrieved_at, indicator_keys, source_id)
            dataset_id = existing_id
            print(f"既存データセットを上書き: ID={dataset_id}")
        else:
            dataset_id = create_dataset(cur, source_id, retrieved_at, indicator_keys, fiscal_year_month)
            print(f"新規データセットID: {dataset_id}")
        print(f"決算年月: {fiscal_year_month.strftime('%Y年%m月')}期")

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

            indicators = {}
            notes = {}

            for col_name, col_def in value_columns:
                val = row[col_name]
                if pd.isna(val) or val == "":
                    continue

                try:
                    num_val = float(val.replace(",", ""))
                    if num_val == int(num_val):
                        indicators[col_def["code"]] = int(num_val)
                    else:
                        indicators[col_def["code"]] = num_val
                except ValueError:
                    continue

                if col_name in note_col_indices:
                    note_idx = note_col_indices[col_name]
                    note_val = row.iloc[note_idx]
                    if pd.notna(note_val) and note_val != "":
                        notes[col_def["code"]] = note_val

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
    parser.add_argument(
        "--fiscal-ym",
        type=lambda s: date(int(s.split("-")[0]), int(s.split("-")[1]), 1),
        required=True,
        help="決算年月 (YYYY-MM形式、例: 2026-03)",
    )
    args = parser.parse_args()

    if not Path(args.csv_path).exists():
        print(f"ファイルが見つかりません: {args.csv_path}")
        sys.exit(1)

    import_csv(args.csv_path, args.retrieved_at, args.fiscal_ym)


if __name__ == "__main__":
    main()
