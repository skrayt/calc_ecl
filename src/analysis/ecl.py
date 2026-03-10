"""ECL計算コアロジック

確定済み回帰モデルとARIMA予測値を組み合わせ、PD/LGD予測値とECLを計算する。
UIに依存しない純粋な計算モジュール。
"""
import pandas as pd
import numpy as np


def apply_model_to_forecast(
    coefficients: dict,
    forecast_df: pd.DataFrame,
    feature_stats: dict | None = None,
    transform_method: str = "none",
) -> pd.Series:
    """確定済み回帰モデルにARIMA予測値を代入し、PD/LGD予測値を計算する

    モデル学習時に標準化を行った場合は feature_stats で各変数の mean/std を渡す。
    標準化なし・変換なしの場合は coefficients と forecast_df をそのまま使う。

    Parameters
    ----------
    coefficients : dict
        回帰係数の辞書。{"const": β₀, "unemployment_rate": β₁, ...}
    forecast_df : pd.DataFrame
        ARIMA予測値のDataFrame（列名=変数名、原系列スケール）
    feature_stats : dict or None
        標準化統計量 {"unemployment_rate": {"mean": 2.4, "std": 0.8}, ...}
        None の場合は標準化なしとみなす
    transform_method : str
        変換方法（'none' | 'log' | 'diff' | 'log_diff' | 'arcsinh' | 'arcsinh_diff'）
        将来値に同じ変換を適用してから係数を掛ける

    Returns
    -------
    pd.Series
        各時点のPD/LGD予測値（const を含む線形結合の結果）
    """
    work_df = forecast_df.copy()

    # データ変換を適用
    if transform_method and transform_method != "none":
        work_df = _transform_df(work_df, transform_method)

    # 標準化を適用（feature_stats が指定されている場合）
    if feature_stats:
        for col in work_df.columns:
            if col in feature_stats:
                mean = feature_stats[col]["mean"]
                std = feature_stats[col]["std"]
                if std and std != 0:
                    work_df[col] = (work_df[col] - mean) / std

    # NaN除去
    work_df = work_df.dropna()
    if work_df.empty:
        return pd.Series(dtype=float)

    # 線形結合で予測値を計算: PD = const + β₁×X₁ + β₂×X₂ + ...
    const = coefficients.get("const", 0.0)
    predicted = pd.Series(float(const), index=work_df.index, name="predicted")
    for col in work_df.columns:
        if col in coefficients:
            predicted = predicted + float(coefficients[col]) * work_df[col]

    return predicted


def calc_weighted_ecl(
    base_pd: pd.Series,
    upside_pd: pd.Series,
    downside_pd: pd.Series,
    lgd: float,
    weight_base: float,
    weight_upside: float,
    weight_downside: float,
    ead: float | None = None,
) -> dict:
    """3シナリオの加重平均でECL期待値を計算する

    Parameters
    ----------
    base_pd / upside_pd / downside_pd : pd.Series
        各シナリオのPD予測値（時点インデックス付き）
    lgd : float
        LGD固定値（例: 0.45 = 45%）
    weight_base / weight_upside / weight_downside : float
        各シナリオのウェイト（合計が1.0になること）
    ead : float or None
        デフォルト時エクスポージャー（金額）。None の場合はECL率のみ計算

    Returns
    -------
    dict
        キー:
        - pd_base: ベースシナリオPD (pd.Series)
        - pd_upside: 楽観シナリオPD (pd.Series)
        - pd_downside: 悲観シナリオPD (pd.Series)
        - pd_weighted: 加重平均PD (pd.Series)
        - lgd: LGD固定値 (float)
        - ecl_rate: ECL率 = PD_weighted × LGD (pd.Series)
        - ecl_amount: ECL金額（EAD が指定された場合のみ、pd.Series）
        - weight_base / weight_upside / weight_downside: 各ウェイト
    """
    # 共通インデックスに揃える
    common_idx = base_pd.index.intersection(upside_pd.index).intersection(downside_pd.index)
    base_pd = base_pd.reindex(common_idx)
    upside_pd = upside_pd.reindex(common_idx)
    downside_pd = downside_pd.reindex(common_idx)

    pd_weighted = (
        weight_base * base_pd
        + weight_upside * upside_pd
        + weight_downside * downside_pd
    )
    ecl_rate = pd_weighted * lgd

    result = {
        "pd_base": base_pd,
        "pd_upside": upside_pd,
        "pd_downside": downside_pd,
        "pd_weighted": pd_weighted,
        "lgd": lgd,
        "ecl_rate": ecl_rate,
        "weight_base": weight_base,
        "weight_upside": weight_upside,
        "weight_downside": weight_downside,
    }
    if ead is not None:
        result["ecl_amount"] = ecl_rate * ead

    return result


def build_scenario_forecast(
    arima_forecasts_by_var: dict[str, pd.DataFrame],
    scenario: str,
) -> pd.DataFrame:
    """説明変数ごとのARIMA予測結果から、指定シナリオの説明変数DataFrameを組み立てる

    Parameters
    ----------
    arima_forecasts_by_var : dict[str, pd.DataFrame]
        変数名 → ARIMA予測DataFrameのマッピング。
        各DataFrameのカラムは forecast / lower / upper
    scenario : str
        シナリオ名: 'base' | 'upside' | 'downside'

    Returns
    -------
    pd.DataFrame
        列名=変数名、値=指定シナリオの予測値のDataFrame

    Notes
    -----
    シナリオとARIMA列の対応（デフォルト）:
        base     → forecast 列（点予測値）
        upside   → lower 列（95%信頼区間下限）
        downside → upper 列（95%信頼区間上限）

    失業率・金利のような「高いほど悲観」の変数では上記で正しいが、
    GDP成長率のような「高いほど楽観」の変数では上限=楽観・下限=悲観となるため、
    ECL計算タブで変数ごとに対応列を選択できるようにすること。
    """
    col_map = {"base": "forecast", "upside": "lower", "downside": "upper"}
    col = col_map.get(scenario, "forecast")

    frames = {}
    for var_name, fc_df in arima_forecasts_by_var.items():
        if col in fc_df.columns:
            frames[var_name] = fc_df[col]
        elif "forecast" in fc_df.columns:
            frames[var_name] = fc_df["forecast"]

    if not frames:
        return pd.DataFrame()

    return pd.DataFrame(frames)


def _transform_df(df: pd.DataFrame, method: str) -> pd.DataFrame:
    """DataFrameに変換を適用する（src/analysis/data_transform.py の transform と同じ変換）"""
    if method == "none":
        return df
    result = df.copy()
    if method == "log":
        result = np.log1p(result)
    elif method == "diff":
        result = result.diff()
    elif method == "log_diff":
        result = np.log1p(result).diff()
    elif method == "arcsinh":
        result = np.arcsinh(result)
    elif method == "arcsinh_diff":
        result = np.arcsinh(result).diff()
    return result
