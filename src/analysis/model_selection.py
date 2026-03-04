"""モデル選択モジュール

説明変数の全組み合わせ探索によるモデル選択機能を提供する。
UIに依存しない純粋な統計処理モジュール。

移植元: Craft_RegressionAnalysis/pages/page_model_selection.py (run_analysis)
"""
from itertools import combinations

import pandas as pd
import numpy as np

from src.analysis.data_transform import transform, standardize
from src.analysis.correlation import calc_vif
from src.analysis.regression import fit_ols


def search_best_model(
    df: pd.DataFrame,
    target_col: str,
    feature_cols: list[str],
    n_features: int,
    transform_method: str = "none",
    do_standardize: bool = True,
    lag: int = 0,
    sort_by: str = "aic",
    progress_callback=None,
) -> pd.DataFrame:
    """説明変数の全組み合わせを探索し、各モデルの評価指標を返す。

    Parameters
    ----------
    df : pd.DataFrame
        元データのDataFrame（インデックスはDatetimeIndex推奨）
    target_col : str
        目的変数のカラム名
    feature_cols : list[str]
        説明変数候補のカラム名リスト
    n_features : int
        組み合わせる説明変数の数
    transform_method : str
        変換メソッド: none / log / diff / log_diff / arcsinh / arcsinh_diff
    do_standardize : bool
        標準化するかどうか（デフォルト: True）
    lag : int
        ラグ次数（デフォルト: 0）
    sort_by : str
        ソート基準: aic / bic / adj_r2 / r2（デフォルト: aic）
    progress_callback : callable or None
        進捗通知用コールバック。呼び出し形式: callback(current, total)
        GUIから進捗バーを更新するために使用

    Returns
    -------
    pd.DataFrame
        各モデルの評価指標。カラム:
        - features: 説明変数名のリスト（カンマ区切り文字列）
        - n_features: 説明変数の数
        - r2: 決定係数
        - adj_r2: 調整済み決定係数
        - aic: AIC
        - bic: BIC
        - dw: Durbin-Watson統計量
        - f_stat: F統計量
        - f_pvalue: F検定のp値
        - max_vif: 最大VIF値
        - nobs: 観測数
        sort_by基準でソート済み

    Raises
    ------
    ValueError
        n_featuresがfeature_colsの数を超える場合
        target_colがdfに存在しない場合
    """
    # バリデーション
    if target_col not in df.columns:
        raise ValueError(f"目的変数 '{target_col}' がDataFrameに存在しません。")

    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise ValueError(f"説明変数がDataFrameに存在しません: {missing}")

    if n_features < 1:
        raise ValueError("説明変数の数は1以上を指定してください。")

    if n_features > len(feature_cols):
        raise ValueError(
            f"説明変数の数({n_features})が候補数({len(feature_cols)})を超えています。"
        )

    # データ変換
    cols_needed = [target_col] + list(feature_cols)
    work_df = df[cols_needed].copy()
    work_df = transform(work_df, transform_method)

    if do_standardize:
        work_df = standardize(work_df)

    y = work_df[target_col]

    # 全組み合わせを生成
    combos = list(combinations(feature_cols, n_features))
    total = len(combos)
    results = []

    for i, combo in enumerate(combos):
        combo_list = list(combo)
        X = work_df[combo_list]

        try:
            # OLS回帰
            ols_result = fit_ols(y, X, lag=lag)

            # VIF計算（説明変数が2つ以上の場合のみ意味がある）
            if len(combo_list) >= 2:
                vif_df = calc_vif(X)
                max_vif = vif_df["vif"].max()
            else:
                max_vif = 1.0

            results.append({
                "features": ", ".join(combo_list),
                "n_features": len(combo_list),
                "r2": ols_result["r2"],
                "adj_r2": ols_result["adj_r2"],
                "aic": ols_result["aic"],
                "bic": ols_result["bic"],
                "dw": ols_result["dw"],
                "f_stat": ols_result["f_stat"],
                "f_pvalue": ols_result["f_pvalue"],
                "max_vif": max_vif,
                "nobs": ols_result["nobs"],
            })
        except Exception as e:
            # 特異行列等で回帰が失敗した場合はスキップ
            results.append({
                "features": ", ".join(combo_list),
                "n_features": len(combo_list),
                "r2": np.nan,
                "adj_r2": np.nan,
                "aic": np.nan,
                "bic": np.nan,
                "dw": np.nan,
                "f_stat": np.nan,
                "f_pvalue": np.nan,
                "max_vif": np.nan,
                "nobs": 0,
            })

        # 進捗通知
        if progress_callback is not None:
            progress_callback(i + 1, total)

    results_df = pd.DataFrame(results)

    # ソート
    sort_ascending = _get_sort_ascending(sort_by)
    if sort_by in results_df.columns:
        results_df = results_df.sort_values(
            sort_by, ascending=sort_ascending
        ).reset_index(drop=True)

    return results_df


def filter_models(
    results_df: pd.DataFrame,
    max_vif: float | None = 10.0,
    max_aic: float | None = None,
    min_adj_r2: float | None = None,
    min_dw: float | None = 1.5,
    max_dw: float | None = 2.5,
) -> pd.DataFrame:
    """評価指標に基づいてモデル候補をフィルタリングする

    Parameters
    ----------
    results_df : pd.DataFrame
        search_best_model() の戻り値
    max_vif : float or None
        VIFの上限。Noneの場合はフィルタリングしない
    max_aic : float or None
        AICの上限。Noneの場合はフィルタリングしない
    min_adj_r2 : float or None
        Adj.R²の下限。Noneの場合はフィルタリングしない
    min_dw : float or None
        DWの下限。Noneの場合はフィルタリングしない
    max_dw : float or None
        DWの上限。Noneの場合はフィルタリングしない

    Returns
    -------
    pd.DataFrame
        フィルタリング後のDataFrame
    """
    filtered = results_df.copy()

    if max_vif is not None:
        filtered = filtered[filtered["max_vif"] <= max_vif]

    if max_aic is not None:
        filtered = filtered[filtered["aic"] <= max_aic]

    if min_adj_r2 is not None:
        filtered = filtered[filtered["adj_r2"] >= min_adj_r2]

    if min_dw is not None:
        filtered = filtered[filtered["dw"] >= min_dw]

    if max_dw is not None:
        filtered = filtered[filtered["dw"] <= max_dw]

    return filtered.reset_index(drop=True)


def _get_sort_ascending(sort_by: str) -> bool:
    """ソート基準に応じた昇順/降順を返す"""
    descending_metrics = {"r2", "adj_r2"}
    return sort_by not in descending_metrics


# ============================================================
# テスト用エントリポイント
# ============================================================
if __name__ == "__main__":
    np.random.seed(42)
    n = 60
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")

    # テスト用データ: y = 2*x1 - 0.5*x2 + noise
    x1 = np.random.normal(0, 1, n)
    x2 = np.random.normal(0, 1, n)
    x3 = x1 * 0.8 + np.random.normal(0, 0.3, n)  # x1と高い相関
    x4 = np.random.normal(0, 1, n)  # 独立
    noise = np.random.normal(0, 0.3, n)
    y = 2.0 * x1 - 0.5 * x2 + noise

    test_df = pd.DataFrame(
        {"y": y, "x1": x1, "x2": x2, "x3": x3, "x4": x4},
        index=dates,
    )

    feature_cols = ["x1", "x2", "x3", "x4"]

    # 進捗表示コールバック
    def show_progress(current, total):
        if current % 2 == 0 or current == total:
            print(f"  進捗: {current}/{total}")

    print("=== 2変数の全組み合わせ探索 ===")
    results = search_best_model(
        test_df,
        target_col="y",
        feature_cols=feature_cols,
        n_features=2,
        transform_method="none",
        do_standardize=True,
        lag=0,
        sort_by="aic",
        progress_callback=show_progress,
    )
    print(results.to_string(index=False, float_format="%.4f"))
    print()

    print("=== VIF≤10でフィルタリング ===")
    filtered = filter_models(results, max_vif=10.0)
    print(filtered.to_string(index=False, float_format="%.4f"))
    print()

    print("=== 3変数の全組み合わせ探索（ラグ=1） ===")
    results3 = search_best_model(
        test_df,
        target_col="y",
        feature_cols=feature_cols,
        n_features=3,
        transform_method="none",
        do_standardize=True,
        lag=1,
        sort_by="adj_r2",
        progress_callback=show_progress,
    )
    print(results3.to_string(index=False, float_format="%.4f"))
