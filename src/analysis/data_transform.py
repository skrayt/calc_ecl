"""データ変換モジュール

対数変換・差分・標準化等のデータ変換機能を提供する。
UIに依存しない純粋な統計処理モジュール。

移植元: Craft_RegressionAnalysis/utils/data_transformation.py
"""
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler


# サポートする変換メソッド一覧
TRANSFORM_METHODS = {
    "none": "原系列（変換なし）",
    "log": "対数変換 log(1+x)",
    "diff": "1次差分",
    "log_diff": "対数変換→差分",
    "arcsinh": "逆双曲線正弦変換",
    "arcsinh_diff": "逆双曲線正弦→差分",
}


def transform(df: pd.DataFrame, method: str = "none") -> pd.DataFrame:
    """データ変換（全カラム一括）

    Parameters
    ----------
    df : pd.DataFrame
        数値データのDataFrame（インデックスはDatetimeIndex推奨）
    method : str
        変換メソッド: none / log / diff / log_diff / arcsinh / arcsinh_diff

    Returns
    -------
    pd.DataFrame
        変換後のDataFrame。差分系の変換では先頭行がNaNで削除される
    """
    if method not in TRANSFORM_METHODS:
        raise ValueError(
            f"不明な変換メソッド: {method}。"
            f"利用可能: {list(TRANSFORM_METHODS.keys())}"
        )

    if method == "none":
        return df.copy()

    result = df.copy()

    # 数値カラムのみ処理
    numeric_cols = result.select_dtypes(include=np.number).columns

    if method == "log":
        result[numeric_cols] = np.log1p(result[numeric_cols])

    elif method == "diff":
        result[numeric_cols] = result[numeric_cols].diff()
        result = result.dropna()

    elif method == "log_diff":
        result[numeric_cols] = np.log1p(result[numeric_cols]).diff()
        result = result.dropna()

    elif method == "arcsinh":
        result[numeric_cols] = np.arcsinh(result[numeric_cols])

    elif method == "arcsinh_diff":
        result[numeric_cols] = np.arcsinh(result[numeric_cols]).diff()
        result = result.dropna()

    return result


def standardize(df: pd.DataFrame) -> pd.DataFrame:
    """Z-score標準化

    各カラムを平均0・標準偏差1に変換する。
    標準偏差が0のカラムは0のまま返す。

    Parameters
    ----------
    df : pd.DataFrame
        数値データのDataFrame

    Returns
    -------
    pd.DataFrame
        標準化後のDataFrame（インデックスは維持）
    """
    numeric_cols = df.select_dtypes(include=np.number).columns
    result = df.copy()

    if len(numeric_cols) == 0:
        return result

    scaler = StandardScaler()
    result[numeric_cols] = scaler.fit_transform(result[numeric_cols])

    return result


def transform_per_column(
    df: pd.DataFrame,
    settings: dict[str, dict],
) -> pd.DataFrame:
    """変数ごとに個別の変換・標準化を適用する

    Parameters
    ----------
    df : pd.DataFrame
        元データのDataFrame
    settings : dict
        変数ごとの設定。形式:
        {
            "col_name": {
                "transform": "log",      # 変換メソッド（TRANSFORM_METHODSのキー）
                "standardize": True       # 標準化するかどうか
            },
            ...
        }
        settingsに含まれないカラムはそのまま保持される

    Returns
    -------
    pd.DataFrame
        変数ごとに変換・標準化を適用したDataFrame。
        差分系の変換を含む場合、行数が減少する（最も行数が少ない変換に合わせる）
    """
    result = pd.DataFrame(index=df.index)

    for col in df.columns:
        if col not in settings:
            # 設定がないカラムはそのまま
            result[col] = df[col]
            continue

        col_settings = settings[col]
        method = col_settings.get("transform", "none")
        do_standardize = col_settings.get("standardize", False)

        # 単一カラムをDataFrameとして変換
        col_df = df[[col]].copy()
        col_df = transform(col_df, method)

        if do_standardize and not col_df.empty:
            col_df = standardize(col_df)

        result[col] = col_df[col]

    # 全カラムのNaNが出た行を削除（差分系変換の行数ずれ対応）
    result = result.dropna()

    return result


# ============================================================
# テスト用エントリポイント
# ============================================================
if __name__ == "__main__":
    # テスト用のサンプルデータ
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=24, freq="MS")
    test_df = pd.DataFrame(
        {
            "gdp": np.random.uniform(500, 600, 24),
            "unemployment": np.random.uniform(2.0, 4.0, 24),
            "cpi": np.random.uniform(100, 110, 24),
        },
        index=dates,
    )

    print("=== 元データ ===")
    print(test_df.head())
    print()

    for method in TRANSFORM_METHODS:
        print(f"=== 変換: {method} ({TRANSFORM_METHODS[method]}) ===")
        result = transform(test_df, method)
        print(f"shape: {result.shape}")
        print(result.head())
        print()

    print("=== 標準化 ===")
    std_df = standardize(test_df)
    print(std_df.head())
    print(f"平均: {std_df.mean().to_dict()}")
    print(f"標準偏差: {std_df.std().to_dict()}")
    print()

    print("=== 変数ごと個別変換 ===")
    per_col_settings = {
        "gdp": {"transform": "log", "standardize": True},
        "unemployment": {"transform": "diff", "standardize": False},
        "cpi": {"transform": "none", "standardize": True},
    }
    result = transform_per_column(test_df, per_col_settings)
    print(f"shape: {result.shape}")
    print(result.head())
