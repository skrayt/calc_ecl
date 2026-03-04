"""OLS回帰・評価指標モジュール

statsmodelsによるOLS回帰分析とscikit-learnによる交差検証機能を提供する。
UIに依存しない純粋な統計処理モジュール。

移植元:
- Craft_RegressionAnalysis/pages/page_model_selection.py (calculate_model_metrics)
- Craft_RegressionAnalysis/pages/page_regression.py (regression_calc)
"""
import pandas as pd
import numpy as np
from statsmodels.regression.linear_model import OLS
from statsmodels.tools.tools import add_constant
from statsmodels.stats.stattools import durbin_watson
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import cross_val_score


def fit_ols(y: pd.Series, X: pd.DataFrame, lag: int = 0) -> dict:
    """OLS回帰を実行し評価指標を返す

    Parameters
    ----------
    y : pd.Series
        目的変数
    X : pd.DataFrame
        説明変数（定数項を含まないこと）
    lag : int
        ラグ次数。lag>0の場合、Xをlag期ずらして回帰する。
        yの先頭lag行とXの末尾lag行が削除される

    Returns
    -------
    dict
        キー:
        - r2: 決定係数
        - adj_r2: 調整済み決定係数
        - aic: AIC（赤池情報量基準）
        - bic: BIC（ベイズ情報量基準）
        - dw: Durbin-Watson統計量
        - f_stat: F統計量
        - f_pvalue: F検定のp値
        - coefficients: 係数のDataFrame（variable, coef, std_err, t_stat, p_value）
        - resid: 残差のSeries
        - fitted: 予測値のSeries
        - nobs: 観測数
        - model: statsmodels OLS結果オブジェクト
    """
    y_aligned, X_aligned = _apply_lag(y, X, lag)

    # 定数項を追加
    X_const = add_constant(X_aligned)

    # OLS推定
    model = OLS(y_aligned, X_const).fit()

    # 係数テーブル
    coef_records = []
    for name, coef, se, t, p in zip(
        model.params.index,
        model.params.values,
        model.bse.values,
        model.tvalues.values,
        model.pvalues.values,
    ):
        coef_records.append({
            "variable": name,
            "coef": coef,
            "std_err": se,
            "t_stat": t,
            "p_value": p,
        })

    return {
        "r2": model.rsquared,
        "adj_r2": model.rsquared_adj,
        "aic": model.aic,
        "bic": model.bic,
        "dw": float(durbin_watson(model.resid)),
        "f_stat": model.fvalue,
        "f_pvalue": model.f_pvalue,
        "coefficients": pd.DataFrame(coef_records),
        "resid": model.resid,
        "fitted": model.fittedvalues,
        "nobs": int(model.nobs),
        "model": model,
    }


def cross_validate(
    y: pd.Series,
    X: pd.DataFrame,
    cv: int = 5,
    lag: int = 0,
) -> dict:
    """k-fold交差検証を実行する

    Parameters
    ----------
    y : pd.Series
        目的変数
    X : pd.DataFrame
        説明変数
    cv : int
        分割数（デフォルト: 5）
    lag : int
        ラグ次数

    Returns
    -------
    dict
        キー:
        - mean_mse: 交差検証MSEの平均
        - std_mse: 交差検証MSEの標準偏差
        - scores: 各foldのMSE（負のMSEを反転済み）
    """
    y_aligned, X_aligned = _apply_lag(y, X, lag)

    lr = LinearRegression()
    scores = cross_val_score(
        lr, X_aligned, y_aligned, cv=cv, scoring="neg_mean_squared_error"
    )
    mse_scores = -scores  # 負のMSEを正に反転

    return {
        "mean_mse": float(mse_scores.mean()),
        "std_mse": float(mse_scores.std()),
        "scores": mse_scores.tolist(),
    }


def _apply_lag(
    y: pd.Series, X: pd.DataFrame, lag: int
) -> tuple[pd.Series, pd.DataFrame]:
    """ラグを適用してyとXのアライメントを行う

    lag>0の場合、「過去のXで現在のyを予測する」形にデータをずらす。
    具体的にはXをlag期分シフトし、NaN行を削除する。

    Parameters
    ----------
    y : pd.Series
        目的変数
    X : pd.DataFrame
        説明変数
    lag : int
        ラグ次数

    Returns
    -------
    tuple[pd.Series, pd.DataFrame]
        アライメント後の (y, X)
    """
    if lag <= 0:
        return y, X

    # Xをlag期前にずらす（shift(lag)で過去のデータを現在の行に持ってくる）
    X_lagged = X.shift(lag)

    # NaN行を削除（先頭lag行）
    valid_idx = X_lagged.dropna().index
    common_idx = valid_idx.intersection(y.index)

    return y.loc[common_idx], X_lagged.loc[common_idx]


# ============================================================
# テスト用エントリポイント
# ============================================================
if __name__ == "__main__":
    np.random.seed(42)
    n = 100
    dates = pd.date_range("2015-01-01", periods=n, freq="MS")

    # テスト用データ: y = 2*x1 - 0.5*x2 + noise
    x1 = np.random.normal(0, 1, n)
    x2 = np.random.normal(0, 1, n)
    noise = np.random.normal(0, 0.3, n)
    y_values = 2.0 * x1 - 0.5 * x2 + noise

    X = pd.DataFrame({"x1": x1, "x2": x2}, index=dates)
    y = pd.Series(y_values, index=dates, name="y")

    print("=== OLS回帰（ラグなし） ===")
    result = fit_ols(y, X)
    print(f"R²: {result['r2']:.4f}")
    print(f"Adj R²: {result['adj_r2']:.4f}")
    print(f"AIC: {result['aic']:.2f}")
    print(f"BIC: {result['bic']:.2f}")
    print(f"DW: {result['dw']:.4f}")
    print(f"F統計量: {result['f_stat']:.2f} (p={result['f_pvalue']:.4e})")
    print(f"観測数: {result['nobs']}")
    print()
    print("係数:")
    print(result["coefficients"].to_string(index=False, float_format="%.4f"))
    print()

    print("=== OLS回帰（ラグ=3） ===")
    result_lag = fit_ols(y, X, lag=3)
    print(f"R²: {result_lag['r2']:.4f}")
    print(f"観測数: {result_lag['nobs']}")
    print()

    print("=== 交差検証 ===")
    cv_result = cross_validate(y, X)
    print(f"平均MSE: {cv_result['mean_mse']:.4f}")
    print(f"MSE標準偏差: {cv_result['std_mse']:.4f}")
    print(f"各foldのMSE: {[f'{s:.4f}' for s in cv_result['scores']]}")
