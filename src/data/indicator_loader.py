"""DB→DataFrame変換モジュール

indicator_datasetsおよびindicator_dataテーブルから
pandas DataFrameに変換するユーティリティ。
UIに依存しない純粋なデータ取得モジュール。
"""
import json

import pandas as pd

from config.db import get_connection


def list_datasets(active_only: bool = True) -> pd.DataFrame:
    """indicator_datasetsの一覧を返す

    Parameters
    ----------
    active_only : bool
        Trueの場合、is_active=TRUEのデータセットのみ返す

    Returns
    -------
    pd.DataFrame
        カラム: dataset_id, dataset_name, retrieved_at, indicator_keys,
                description, is_active, created_at
    """
    query = """
        SELECT dataset_id, dataset_name, retrieved_at,
               indicator_keys, description, is_active, created_at
        FROM indicator_datasets
    """
    if active_only:
        query += " WHERE is_active = TRUE"
    query += " ORDER BY retrieved_at DESC, dataset_id DESC"

    conn = get_connection()
    try:
        df = pd.read_sql(query, conn)
        # JSONB列をPythonリストに変換
        if not df.empty:
            df["indicator_keys"] = df["indicator_keys"].apply(
                lambda v: json.loads(v) if isinstance(v, str) else v
            )
        return df
    finally:
        conn.close()


def list_frequencies(dataset_id: int) -> list[str]:
    """指定データセットに含まれるfrequencyの一覧を返す

    Parameters
    ----------
    dataset_id : int
        データセットID

    Returns
    -------
    list[str]
        frequency値のリスト（例: ['monthly', 'quarterly']）
    """
    query = """
        SELECT DISTINCT frequency
        FROM indicator_data
        WHERE dataset_id = %s
        ORDER BY frequency
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (dataset_id,))
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def load_indicators(
    dataset_id: int,
    frequency: str,
    region_code: str = "00000",
    indicator_codes: list[str] | None = None,
) -> pd.DataFrame:
    """指定データセットの指標データをDataFrame化する

    indicator_dataテーブルのJSONB列（indicators）を展開し、
    reference_dateをインデックス、各指標コードをカラムとするDataFrameを返す。

    Parameters
    ----------
    dataset_id : int
        データセットID
    frequency : str
        時系列粒度（monthly / quarterly / calendar_year / fiscal_year）
    region_code : str
        地域コード（デフォルト: '00000' = 全国）
    indicator_codes : list[str] | None
        取得する指標コードのリスト。Noneの場合は全指標を取得

    Returns
    -------
    pd.DataFrame
        インデックス: reference_date（DatetimeIndex）
        カラム: 各指標コード（例: unemployment_rate, gdp_nominal_2020base）
        値: 数値（NaN含む）
    """
    query = """
        SELECT reference_date, indicators
        FROM indicator_data
        WHERE dataset_id = %s
          AND frequency = %s
          AND region_code = %s
        ORDER BY reference_date
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (dataset_id, frequency, region_code))
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame()

    # JSONB展開: 各行の indicators辞書を展開してDataFrame化
    records = []
    for ref_date, indicators_raw in rows:
        # psycopg2はJSONBをdictで返すが、念のためstr対応
        if isinstance(indicators_raw, str):
            indicators_raw = json.loads(indicators_raw)

        record = {"reference_date": ref_date}
        record.update(indicators_raw)
        records.append(record)

    df = pd.DataFrame(records)
    df["reference_date"] = pd.to_datetime(df["reference_date"])
    df = df.set_index("reference_date").sort_index()

    # 数値変換（JSONB内の値が文字列の場合への対応）
    df = df.apply(pd.to_numeric, errors="coerce")

    # 指標コードのフィルタリング
    if indicator_codes is not None:
        existing = [c for c in indicator_codes if c in df.columns]
        df = df[existing]

    return df


def get_indicator_definitions(
    indicator_codes: list[str] | None = None,
) -> pd.DataFrame:
    """指標定義マスタを取得する

    Parameters
    ----------
    indicator_codes : list[str] | None
        取得する指標コードのリスト。Noneの場合は全件取得

    Returns
    -------
    pd.DataFrame
        カラム: indicator_id, indicator_code, indicator_name,
                base_year, unit, frequency
    """
    query = """
        SELECT indicator_id, indicator_code, indicator_name,
               base_year, unit, frequency
        FROM indicator_definitions
    """
    params = None
    if indicator_codes is not None:
        placeholders = ", ".join(["%s"] * len(indicator_codes))
        query += f" WHERE indicator_code IN ({placeholders})"
        params = tuple(indicator_codes)

    query += " ORDER BY indicator_code"

    conn = get_connection()
    try:
        df = pd.read_sql(query, conn, params=params)
        return df
    finally:
        conn.close()


def load_dataset_summary(dataset_id: int) -> dict:
    """データセットのサマリ情報を返す

    Parameters
    ----------
    dataset_id : int
        データセットID

    Returns
    -------
    dict
        キー: dataset_info（基本情報dict）, frequencies（frequency別レコード数）,
              date_range（frequency別の日付範囲）
    """
    conn = get_connection()
    try:
        # データセット基本情報
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT dataset_id, dataset_name, retrieved_at,
                       indicator_keys, description, is_active
                FROM indicator_datasets
                WHERE dataset_id = %s
                """,
                (dataset_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError(f"データセットが見つかりません: dataset_id={dataset_id}")

            indicator_keys = row[3]
            if isinstance(indicator_keys, str):
                indicator_keys = json.loads(indicator_keys)

            dataset_info = {
                "dataset_id": row[0],
                "dataset_name": row[1],
                "retrieved_at": row[2],
                "indicator_keys": indicator_keys,
                "description": row[4],
                "is_active": row[5],
            }

        # frequency別のレコード数と日付範囲
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT frequency,
                       COUNT(*) as record_count,
                       MIN(reference_date) as date_from,
                       MAX(reference_date) as date_to
                FROM indicator_data
                WHERE dataset_id = %s
                GROUP BY frequency
                ORDER BY frequency
                """,
                (dataset_id,),
            )
            freq_rows = cur.fetchall()

        frequencies = {}
        for freq, count, date_from, date_to in freq_rows:
            frequencies[freq] = {
                "record_count": count,
                "date_from": date_from,
                "date_to": date_to,
            }

        return {
            "dataset_info": dataset_info,
            "frequencies": frequencies,
        }
    finally:
        conn.close()


# ============================================================
# 目的変数（PD/LGD/EAD）データ取得
# ============================================================
def list_target_datasets(active_only: bool = True) -> pd.DataFrame:
    """target_datasetsの一覧を返す

    Parameters
    ----------
    active_only : bool
        Trueの場合、is_active=TRUEのデータセットのみ返す

    Returns
    -------
    pd.DataFrame
        カラム: target_dataset_id, dataset_name, retrieved_at,
                target_keys, description, is_active, created_at
    """
    query = """
        SELECT target_dataset_id, dataset_name, retrieved_at,
               target_keys, description, is_active, created_at
        FROM target_datasets
    """
    if active_only:
        query += " WHERE is_active = TRUE"
    query += " ORDER BY retrieved_at DESC, target_dataset_id DESC"

    conn = get_connection()
    try:
        df = pd.read_sql(query, conn)
        if not df.empty:
            df["target_keys"] = df["target_keys"].apply(
                lambda v: json.loads(v) if isinstance(v, str) else v
            )
        return df
    finally:
        conn.close()


def list_target_frequencies(target_dataset_id: int) -> list[str]:
    """指定目的変数データセットに含まれるfrequencyの一覧を返す

    Parameters
    ----------
    target_dataset_id : int
        目的変数データセットID

    Returns
    -------
    list[str]
        frequency値のリスト
    """
    query = """
        SELECT DISTINCT frequency
        FROM target_data
        WHERE target_dataset_id = %s
        ORDER BY frequency
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (target_dataset_id,))
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def list_target_segments(target_dataset_id: int, frequency: str) -> list[dict]:
    """指定データセット・粒度のセグメント一覧を返す

    Returns
    -------
    list[dict]
        [{"segment_code": "all", "segment_name": "全体"}, ...]
    """
    query = """
        SELECT DISTINCT segment_code, segment_name
        FROM target_data
        WHERE target_dataset_id = %s AND frequency = %s
        ORDER BY segment_code
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (target_dataset_id, frequency))
            return [
                {"segment_code": row[0], "segment_name": row[1] or row[0]}
                for row in cur.fetchall()
            ]
    finally:
        conn.close()


def load_targets(
    target_dataset_id: int,
    frequency: str,
    segment_code: str = "all",
    target_codes: list[str] | None = None,
) -> pd.DataFrame:
    """目的変数データをDataFrame化する

    Parameters
    ----------
    target_dataset_id : int
        目的変数データセットID
    frequency : str
        時系列粒度
    segment_code : str
        セグメントコード（デフォルト: 'all'）
    target_codes : list[str] | None
        取得する目的変数コードのリスト。Noneの場合は全目的変数を取得

    Returns
    -------
    pd.DataFrame
        インデックス: reference_date（DatetimeIndex）
        カラム: 各目的変数コード（例: pd_corporate, lgd_corporate）
    """
    query = """
        SELECT reference_date, targets
        FROM target_data
        WHERE target_dataset_id = %s
          AND frequency = %s
          AND segment_code = %s
        ORDER BY reference_date
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (target_dataset_id, frequency, segment_code))
            rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame()

    records = []
    for ref_date, targets_raw in rows:
        if isinstance(targets_raw, str):
            targets_raw = json.loads(targets_raw)
        record = {"reference_date": ref_date}
        record.update(targets_raw)
        records.append(record)

    df = pd.DataFrame(records)
    df["reference_date"] = pd.to_datetime(df["reference_date"])
    df = df.set_index("reference_date").sort_index()
    df = df.apply(pd.to_numeric, errors="coerce")

    if target_codes is not None:
        existing = [c for c in target_codes if c in df.columns]
        df = df[existing]

    return df


def get_target_definitions(
    target_codes: list[str] | None = None,
) -> pd.DataFrame:
    """目的変数定義マスタを取得する

    Returns
    -------
    pd.DataFrame
        カラム: target_id, target_code, target_name, target_type, unit, frequency
    """
    query = """
        SELECT target_id, target_code, target_name,
               target_type, unit, frequency
        FROM target_definitions
    """
    params = None
    if target_codes is not None:
        placeholders = ", ".join(["%s"] * len(target_codes))
        query += f" WHERE target_code IN ({placeholders})"
        params = tuple(target_codes)

    query += " ORDER BY target_code"

    conn = get_connection()
    try:
        df = pd.read_sql(query, conn, params=params)
        return df
    finally:
        conn.close()


def merge_target_and_indicators(
    target_df: pd.DataFrame,
    indicator_df: pd.DataFrame,
    target_code: str,
) -> pd.DataFrame:
    """目的変数と説明変数をreference_dateで内部結合する

    Parameters
    ----------
    target_df : pd.DataFrame
        目的変数DataFrame（index=reference_date）
    indicator_df : pd.DataFrame
        説明変数DataFrame（index=reference_date）
    target_code : str
        使用する目的変数コード（target_dfのカラム名）

    Returns
    -------
    pd.DataFrame
        インデックス: reference_date
        カラム: [target_code] + [説明変数コード群]
    """
    if target_code not in target_df.columns:
        raise ValueError(f"目的変数 '{target_code}' がデータに存在しません")

    # 目的変数の1列だけを取り出して結合
    target_series = target_df[[target_code]]
    merged = target_series.join(indicator_df, how="inner")

    if merged.empty:
        raise ValueError(
            "目的変数と説明変数の期間が重なりません。"
            "同じfrequencyのデータを選択してください。"
        )

    return merged


# ============================================================
# テスト用エントリポイント
# ============================================================
if __name__ == "__main__":
    print("=== データセット一覧 ===")
    datasets = list_datasets()
    print(datasets.to_string())
    print()

    if not datasets.empty:
        ds_id = datasets.iloc[0]["dataset_id"]
        print(f"=== データセットサマリ (ID={ds_id}) ===")
        summary = load_dataset_summary(ds_id)
        print(f"名称: {summary['dataset_info']['dataset_name']}")
        print(f"取得日: {summary['dataset_info']['retrieved_at']}")
        print(f"指標: {summary['dataset_info']['indicator_keys']}")
        print(f"frequency別:")
        for freq, info in summary["frequencies"].items():
            print(f"  {freq}: {info['record_count']}件 "
                  f"({info['date_from']} 〜 {info['date_to']})")
        print()

        freqs = list_frequencies(ds_id)
        print(f"=== frequency一覧: {freqs} ===")
        print()

        for freq in freqs:
            print(f"=== 指標データ (dataset={ds_id}, freq={freq}) ===")
            df = load_indicators(ds_id, freq)
            print(f"shape: {df.shape}")
            print(df.head(10).to_string())
            print()

    print("=== 指標定義マスタ ===")
    defs = get_indicator_definitions()
    print(defs.to_string())
