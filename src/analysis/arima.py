"""ARIMA時系列モデルモジュール

statsmodelsによるARIMAモデルの学習・次数選択・将来予測機能を提供する。
UIに依存しない純粋な統計処理モジュール。

※ Craft版はダミー実装だったため、本モジュールは新規実装。
"""
import warnings

import pandas as pd
import numpy as np
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller, acf, pacf


def fit_arima(
    y: pd.Series,
    order: tuple[int, int, int] = (1, 1, 1),
) -> dict:
    """ARIMAモデルを学習する

    Parameters
    ----------
    y : pd.Series
        時系列データ（DatetimeIndex推奨）
    order : tuple[int, int, int]
        ARIMA(p, d, q) の次数

    Returns
    -------
    dict
        キー:
        - order: (p, d, q) のタプル
        - aic: AIC（赤池情報量基準）
        - bic: BIC（ベイズ情報量基準）
        - params: モデルパラメータのSeries
        - resid: 残差のSeries
        - fitted: モデルのフィットした値のSeries
        - nobs: 観測数
        - model: statsmodels ARIMAResults オブジェクト

    Raises
    ------
    ValueError
        モデルの学習に失敗した場合
    """
    try:
        model = ARIMA(y, order=order)
        result = model.fit()
    except Exception as e:
        raise ValueError(
            f"ARIMA{order} の学習に失敗しました: {e}"
        ) from e

    return {
        "order": order,
        "aic": result.aic,
        "bic": result.bic,
        "params": result.params,
        "resid": result.resid,
        "fitted": result.fittedvalues,
        "nobs": int(result.nobs),
        "model": result,
    }


def auto_select_order(
    y: pd.Series,
    max_p: int = 3,
    max_d: int = 2,
    max_q: int = 3,
    criterion: str = "aic",
    progress_callback=None,
) -> dict:
    """AIC/BICが最小になるARIMA次数を探索する

    全(p, d, q)の組み合わせを試し、指定した情報量基準が最小のモデルを返す。

    Parameters
    ----------
    y : pd.Series
        時系列データ
    max_p : int
        ARの最大次数（デフォルト: 3）
    max_d : int
        差分の最大次数（デフォルト: 2）
    max_q : int
        MAの最大次数（デフォルト: 3）
    criterion : str
        選択基準: 'aic' または 'bic'（デフォルト: 'aic'）
    progress_callback : callable or None
        進捗通知用コールバック。呼び出し形式: callback(current, total)

    Returns
    -------
    dict
        キー:
        - best_order: 最良の(p, d, q)タプル
        - best_aic: 最良モデルのAIC
        - best_bic: 最良モデルのBIC
        - best_model: 最良モデルのARIMAResults
        - all_results: 全モデルの結果DataFrame
          カラム: p, d, q, aic, bic, converged
    """
    if criterion not in ("aic", "bic"):
        raise ValueError(f"criterionは 'aic' または 'bic' を指定してください: {criterion}")

    # 全組み合わせを生成
    orders = [
        (p, d, q)
        for p in range(max_p + 1)
        for d in range(max_d + 1)
        for q in range(max_q + 1)
        if not (p == 0 and q == 0)  # ARIMA(0,d,0)は無意味なのでスキップ
    ]
    total = len(orders)
    results = []

    for i, order in enumerate(orders):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                model = ARIMA(y, order=order)
                result = model.fit()
            results.append({
                "p": order[0],
                "d": order[1],
                "q": order[2],
                "aic": result.aic,
                "bic": result.bic,
                "converged": True,
            })
        except Exception:
            results.append({
                "p": order[0],
                "d": order[1],
                "q": order[2],
                "aic": np.inf,
                "bic": np.inf,
                "converged": False,
            })

        if progress_callback is not None:
            progress_callback(i + 1, total)

    all_results = pd.DataFrame(results)

    # 収束したモデルのみで最良を選定
    converged = all_results[all_results["converged"]]
    if converged.empty:
        raise ValueError("全てのARIMAモデルの学習に失敗しました。")

    best_idx = converged[criterion].idxmin()
    best_row = converged.loc[best_idx]
    best_order = (int(best_row["p"]), int(best_row["d"]), int(best_row["q"]))

    # 最良モデルを再学習（結果オブジェクトを返すため）
    best_model = ARIMA(y, order=best_order).fit()

    return {
        "best_order": best_order,
        "best_aic": best_model.aic,
        "best_bic": best_model.bic,
        "best_model": best_model,
        "all_results": all_results.sort_values(criterion).reset_index(drop=True),
    }


def forecast(
    model_result,
    steps: int,
    alpha: float = 0.05,
) -> pd.DataFrame:
    """将来予測を実行する

    Parameters
    ----------
    model_result : ARIMAResults
        fit_arima() の戻り値の 'model' キー、
        または auto_select_order() の 'best_model' キー
    steps : int
        予測期間数
    alpha : float
        信頼区間の有意水準（デフォルト: 0.05 → 95%信頼区間）

    Returns
    -------
    pd.DataFrame
        カラム:
        - forecast: 予測値
        - lower: 信頼区間下限
        - upper: 信頼区間上限
        インデックスは元データの続きの日付
    """
    pred = model_result.get_forecast(steps=steps, alpha=alpha)
    forecast_mean = pred.predicted_mean
    conf_int = pred.conf_int(alpha=alpha)

    result_df = pd.DataFrame({
        "forecast": forecast_mean,
        "lower": conf_int.iloc[:, 0],
        "upper": conf_int.iloc[:, 1],
    })

    return result_df


def test_stationarity(y: pd.Series) -> dict:
    """ADF検定（拡張ディッキー・フラー検定）で定常性を検定する

    Parameters
    ----------
    y : pd.Series
        時系列データ

    Returns
    -------
    dict
        キー:
        - adf_stat: ADF統計量
        - p_value: p値
        - used_lag: 使用したラグ次数
        - n_obs: 観測数
        - critical_values: 臨界値（1%, 5%, 10%）
        - is_stationary: 5%水準で定常性があるかどうか
    """
    result = adfuller(y, autolag="AIC")

    return {
        "adf_stat": result[0],
        "p_value": result[1],
        "used_lag": result[2],
        "n_obs": result[3],
        "critical_values": result[4],
        "is_stationary": result[1] < 0.05,
    }


def calc_acf_pacf(
    y: pd.Series,
    nlags: int = 20,
    alpha: float = 0.05,
) -> dict:
    """ACF（自己相関関数）とPACF（偏自己相関関数）を計算する

    Parameters
    ----------
    y : pd.Series
        時系列データ
    nlags : int
        計算するラグの最大数（デフォルト: 20）
    alpha : float
        信頼区間の有意水準（デフォルト: 0.05）

    Returns
    -------
    dict
        キー:
        - acf_values: ACF値の配列
        - acf_confint: ACFの信頼区間（(nlags+1, 2) の配列）
        - pacf_values: PACF値の配列
        - pacf_confint: PACFの信頼区間（(nlags+1, 2) の配列）
        - nlags: 使用したラグ数
    """
    # ACF
    acf_result = acf(y, nlags=nlags, alpha=alpha)
    acf_values = acf_result[0]
    acf_confint = acf_result[1]

    # PACF
    pacf_result = pacf(y, nlags=nlags, alpha=alpha)
    pacf_values = pacf_result[0]
    pacf_confint = pacf_result[1]

    return {
        "acf_values": acf_values,
        "acf_confint": acf_confint,
        "pacf_values": pacf_values,
        "pacf_confint": pacf_confint,
        "nlags": nlags,
    }


# ============================================================
# テスト用エントリポイント
# ============================================================
if __name__ == "__main__":
    np.random.seed(42)
    n = 120
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")

    # テスト用: トレンド + 季節性 + ノイズ
    trend = np.linspace(100, 150, n)
    noise = np.random.normal(0, 2, n)
    y = pd.Series(trend + noise, index=dates, name="test_series")

    print("=== ADF検定（定常性検定） ===")
    adf = test_stationarity(y)
    print(f"ADF統計量: {adf['adf_stat']:.4f}")
    print(f"p値: {adf['p_value']:.4f}")
    print(f"定常性: {'あり' if adf['is_stationary'] else 'なし'}")
    print(f"臨界値: {adf['critical_values']}")
    print()

    print("=== ACF/PACF ===")
    acf_pacf = calc_acf_pacf(y, nlags=10)
    print(f"ACF (lag 0-5): {acf_pacf['acf_values'][:6]}")
    print(f"PACF (lag 0-5): {acf_pacf['pacf_values'][:6]}")
    print()

    print("=== ARIMA(1,1,1) ===")
    result = fit_arima(y, order=(1, 1, 1))
    print(f"AIC: {result['aic']:.2f}")
    print(f"BIC: {result['bic']:.2f}")
    print(f"パラメータ: {result['params'].to_dict()}")
    print(f"観測数: {result['nobs']}")
    print()

    print("=== 次数自動選択 ===")
    def show_progress(current, total):
        if current % 10 == 0 or current == total:
            print(f"  進捗: {current}/{total}")

    auto = auto_select_order(y, max_p=2, max_d=1, max_q=2,
                             progress_callback=show_progress)
    print(f"最良次数: ARIMA{auto['best_order']}")
    print(f"AIC: {auto['best_aic']:.2f}")
    print(f"BIC: {auto['best_bic']:.2f}")
    print()
    print("上位5モデル:")
    print(auto["all_results"].head().to_string(index=False, float_format="%.2f"))
    print()

    print("=== 将来予測（12期先） ===")
    fc = forecast(auto["best_model"], steps=12)
    print(fc.to_string(float_format="%.2f"))
