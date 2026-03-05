"""
目的変数（PD/LGD/EAD）CSVをパースしてtarget_dataへインポートするスクリプト

使い方:
    python src/import_targets.py target_data.csv --target-type pd

CSVフォーマット:
    時点,セグメントコード,セグメント名,pd_corporate,lgd_corporate
    2020年度,corporate,法人,0.0234,0.45
    2021年度,corporate,法人,0.0198,0.42

    - 時点列（必須）: 説明変数CSVと同じ形式（2025年度, 2025年1-3月期 等）
    - セグメントコード列（任意）: なければ 'all' をデフォルト設定
    - セグメント名列（任意）: なければ '全体' をデフォルト設定
    - その他の数値列: カラム名がそのまま target_code になる

処理の流れ:
    1. CSVを読み込み、時点列・セグメント列・数値列を識別
    2. target_definitions に未登録の目的変数コードを登録
    3. target_datasets にデータセットを登録
    4. 行ごとに parse_time_point() で日付変換 → target_data へINSERT
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# プロジェクトルートをパスに追加
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from config.db import get_connection
from src.import_indicators import parse_time_point

# 固定列名（これら以外を目的変数データ列として扱う）
FIXED_COLUMNS = {"時点", "セグメントコード", "セグメント名"}

# 有効な目的変数タイプ
VALID_TARGET_TYPES = ("pd", "lgd", "ead")


# =========================================================
# CSV解析
# =========================================================
def identify_columns(df: pd.DataFrame) -> dict:
    """CSVのカラム構成を解析する。

    返り値:
        {
            "time_col": "時点",
            "segment_code_col": "セグメントコード" or None,
            "segment_name_col": "セグメント名" or None,
            "target_cols": ["pd_corporate", "lgd_corporate", ...],
        }
    """
    columns = list(df.columns)
    result = {
        "time_col": None,
        "segment_code_col": None,
        "segment_name_col": None,
        "target_cols": [],
    }

    if "時点" not in columns:
        raise ValueError("CSVに「時点」列が見つかりません")
    result["time_col"] = "時点"

    if "セグメントコード" in columns:
        result["segment_code_col"] = "セグメントコード"
    if "セグメント名" in columns:
        result["segment_name_col"] = "セグメント名"

    for col in columns:
        if col not in FIXED_COLUMNS:
            result["target_cols"].append(col)

    if not result["target_cols"]:
        raise ValueError("目的変数の数値列が見つかりません")

    return result


def detect_frequency_from_data(df: pd.DataFrame) -> str:
    """CSVの時点列から粒度を推定する。最初にパースできた行の粒度を返す。"""
    for time_str in df["時点"]:
        if pd.isna(time_str):
            continue
        parsed = parse_time_point(str(time_str).strip())
        if parsed:
            return parsed[1]
    return "fiscal_year"


# =========================================================
# DB操作
# =========================================================
def ensure_target_definitions(
    cur,
    target_codes: list[str],
    target_type: str,
    frequency: str,
    target_names: dict[str, str] | None = None,
    unit: str | None = None,
):
    """target_definitions に未登録の目的変数を登録する。

    Args:
        target_codes: 目的変数コードのリスト
        target_type: pd / lgd / ead
        frequency: monthly / quarterly / calendar_year / fiscal_year
        target_names: {target_code: 日本語名} の辞書。Noneならコードをそのまま名前に使用
        unit: 単位（例: '%'）
    """
    for code in target_codes:
        cur.execute(
            "SELECT target_id FROM target_definitions WHERE target_code = %s",
            (code,),
        )
        if cur.fetchone():
            continue

        name = (target_names or {}).get(code, code)
        cur.execute(
            """INSERT INTO target_definitions
               (target_code, target_name, target_type, unit, frequency)
               VALUES (%s, %s, %s, %s, %s)""",
            (code, name, target_type, unit, frequency),
        )


def create_target_dataset(
    cur,
    dataset_name: str,
    retrieved_at: date,
    target_keys: list[str],
    description: str | None = None,
) -> int:
    """target_datasets にデータセットを登録"""
    cur.execute(
        """INSERT INTO target_datasets
           (dataset_name, retrieved_at, target_keys, description)
           VALUES (%s, %s, %s, %s) RETURNING target_dataset_id""",
        (dataset_name, retrieved_at, json.dumps(target_keys), description),
    )
    return cur.fetchone()[0]


# =========================================================
# CSVインポート
# =========================================================
def import_target_csv_gui(
    csv_path: str,
    retrieved_at: date,
    dataset_name: str,
    target_type: str,
    target_names: dict[str, str] | None = None,
    unit: str | None = None,
    progress_callback=None,
):
    """GUI経由の目的変数CSVインポート。

    Args:
        csv_path: CSVファイルパス
        retrieved_at: データ取得日
        dataset_name: データセット名
        target_type: 目的変数タイプ (pd / lgd / ead)
        target_names: {target_code: 日本語名} の辞書
        unit: 単位
        progress_callback: (current, total) を受け取るコールバック

    Returns:
        {"inserted": int, "skipped": int, "target_dataset_id": int}
    """
    if target_type not in VALID_TARGET_TYPES:
        raise ValueError(f"無効な目的変数タイプ: {target_type}（有効値: {VALID_TARGET_TYPES}）")

    df = pd.read_csv(csv_path, encoding="utf-8", dtype=str)
    col_info = identify_columns(df)
    frequency = detect_frequency_from_data(df)

    conn = get_connection()
    try:
        cur = conn.cursor()

        # 1. 目的変数定義登録
        ensure_target_definitions(
            cur, col_info["target_cols"], target_type, frequency, target_names, unit
        )

        # 2. データセット登録
        target_dataset_id = create_target_dataset(
            cur, dataset_name, retrieved_at, col_info["target_cols"]
        )

        # 3. 行ごとにパースしてINSERT
        total = len(df)
        inserted = 0
        skipped = 0

        for idx, row in df.iterrows():
            if progress_callback and idx % 10 == 0:
                progress_callback(idx, total)

            time_str = str(row[col_info["time_col"]]).strip()
            parsed = parse_time_point(time_str)
            if parsed is None:
                skipped += 1
                continue

            ref_date, freq = parsed

            # セグメント
            segment_code = "all"
            segment_name = "全体"
            if col_info["segment_code_col"]:
                val = row[col_info["segment_code_col"]]
                if pd.notna(val) and str(val).strip():
                    segment_code = str(val).strip()
            if col_info["segment_name_col"]:
                val = row[col_info["segment_name_col"]]
                if pd.notna(val) and str(val).strip():
                    segment_name = str(val).strip()

            # 目的変数値をJSONBに組み立て
            targets = {}
            for col_name in col_info["target_cols"]:
                val = row[col_name]
                if pd.isna(val) or val == "":
                    continue
                try:
                    num_val = float(str(val).replace(",", ""))
                    if num_val == int(num_val):
                        targets[col_name] = int(num_val)
                    else:
                        targets[col_name] = num_val
                except ValueError:
                    continue

            if not targets:
                skipped += 1
                continue

            cur.execute(
                """INSERT INTO target_data
                   (target_dataset_id, reference_date, frequency,
                    segment_code, segment_name, targets)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (target_dataset_id, reference_date, frequency, segment_code)
                   DO UPDATE SET
                       targets = target_data.targets || EXCLUDED.targets,
                       imported_at = now()""",
                (target_dataset_id, ref_date, freq, segment_code, segment_name,
                 json.dumps(targets)),
            )
            inserted += 1

        conn.commit()

        if progress_callback:
            progress_callback(total, total)

        return {
            "inserted": inserted,
            "skipped": skipped,
            "target_dataset_id": target_dataset_id,
        }

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def import_target_csv(
    csv_path: str,
    retrieved_at: date,
    dataset_name: str,
    target_type: str,
):
    """CLI用の目的変数CSVインポート。"""
    if target_type not in VALID_TARGET_TYPES:
        print(f"エラー: 無効な目的変数タイプ '{target_type}'（有効値: {VALID_TARGET_TYPES}）")
        sys.exit(1)

    df = pd.read_csv(csv_path, encoding="utf-8", dtype=str)
    print(f"CSV読み込み完了: {len(df)}行")

    col_info = identify_columns(df)
    print(f"目的変数列: {col_info['target_cols']}")

    frequency = detect_frequency_from_data(df)
    print(f"検出された粒度: {frequency}")

    conn = get_connection()
    try:
        cur = conn.cursor()

        # 1. 目的変数定義登録
        ensure_target_definitions(cur, col_info["target_cols"], target_type, frequency)
        print("目的変数定義マスタ登録完了")

        # 2. データセット登録
        target_dataset_id = create_target_dataset(
            cur, dataset_name, retrieved_at, col_info["target_cols"]
        )
        print(f"データセットID: {target_dataset_id} ({dataset_name})")

        # 3. 行ごとにパースしてINSERT
        inserted = 0
        skipped = 0

        for _, row in df.iterrows():
            time_str = str(row[col_info["time_col"]]).strip()
            parsed = parse_time_point(time_str)
            if parsed is None:
                skipped += 1
                continue

            ref_date, freq = parsed

            segment_code = "all"
            segment_name = "全体"
            if col_info["segment_code_col"]:
                val = row[col_info["segment_code_col"]]
                if pd.notna(val) and str(val).strip():
                    segment_code = str(val).strip()
            if col_info["segment_name_col"]:
                val = row[col_info["segment_name_col"]]
                if pd.notna(val) and str(val).strip():
                    segment_name = str(val).strip()

            targets = {}
            for col_name in col_info["target_cols"]:
                val = row[col_name]
                if pd.isna(val) or val == "":
                    continue
                try:
                    num_val = float(str(val).replace(",", ""))
                    if num_val == int(num_val):
                        targets[col_name] = int(num_val)
                    else:
                        targets[col_name] = num_val
                except ValueError:
                    continue

            if not targets:
                skipped += 1
                continue

            cur.execute(
                """INSERT INTO target_data
                   (target_dataset_id, reference_date, frequency,
                    segment_code, segment_name, targets)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (target_dataset_id, reference_date, frequency, segment_code)
                   DO UPDATE SET
                       targets = target_data.targets || EXCLUDED.targets,
                       imported_at = now()""",
                (target_dataset_id, ref_date, freq, segment_code, segment_name,
                 json.dumps(targets)),
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
    parser = argparse.ArgumentParser(description="目的変数（PD/LGD/EAD）CSVをDBにインポート")
    parser.add_argument("csv_path", help="CSVファイルのパス")
    parser.add_argument(
        "--target-type",
        required=True,
        choices=VALID_TARGET_TYPES,
        help="目的変数の種類 (pd / lgd / ead)",
    )
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="データセット名（省略時は自動生成）",
    )
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

    dataset_name = args.dataset_name or f"{args.retrieved_at.strftime('%Y年%m月')} {args.target_type.upper()}実績"

    import_target_csv(args.csv_path, args.retrieved_at, dataset_name, args.target_type)


if __name__ == "__main__":
    main()
