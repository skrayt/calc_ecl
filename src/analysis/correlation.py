"""相関分析・VIFモジュール

相関行列の計算とVIF（分散拡大係数）による多重共線性検出機能を提供する。
UIに依存しない純粋な統計処理モジュール。

移植元:
- Craft_RegressionAnalysis/pages/page_model_selection.py (calculate_vif)
- Craft_RegressionAnalysis/pages/page_analysis.py (相関分析ロジック)
"""
import pandas as pd
import numpy as np
from statsmodels.regression.linear_model import OLS
from statsmodels.tools.tools import add_constant


def calc_correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """相関行列を計算する

    Parameters
    ----------
    df : pd.DataFrame
        数値データのDataFrame

    Returns
    -------
    pd.DataFrame
        相関行列（ピアソン相関係数）
    """
    numeric_df = df.select_dtypes(include=np.number)
    return numeric_df.corr()


def calc_vif(X: pd.DataFrame) -> pd.DataFrame:
    """VIF（分散拡大係数）を計算する

    各説明変数について、他の変数で回帰したときのR²からVIFを算出する。
    VIF = 1 / (1 - R²)

    目安:
    - VIF > 10: 多重共線性あり（片方の変数を除外推奨）
    - VIF > 5: 注意が必要

    Parameters
    ----------
    X : pd.DataFrame
        説明変数のDataFrame（定数項を含まないこと）

    Returns
    -------
    pd.DataFrame
        カラム: variable（変数名）, vif（VIF値）
        VIF昇順でソート済み
    """
    if X.shape[1] < 2:
        # 説明変数が1つの場合、VIFは計算不可
        return pd.DataFrame({
            "variable": X.columns.tolist(),
            "vif": [1.0] * X.shape[1],
        })

    vif_records = []
    for col in X.columns:
        y_col = X[col]
        X_other = X.drop(columns=[col])
        X_other_const = add_constant(X_other)

        model = OLS(y_col, X_other_const).fit()
        r2 = model.rsquared

        vif = 1.0 / (1.0 - r2) if r2 < 1.0 else float("inf")
        vif_records.append({"variable": col, "vif": vif})

    result = pd.DataFrame(vif_records)
    result = result.sort_values("vif", ascending=True).reset_index(drop=True)
    return result


def calc_vif_cross_table(df: pd.DataFrame) -> pd.DataFrame:
    """VIFクロス表を計算する

    全変数ペアについて、2変数間のVIF（= 1/(1-r²)）を計算し、
    マトリクス形式で返す。変数ペアの多重共線性スクリーニングに使用。

    Parameters
    ----------
    df : pd.DataFrame
        数値データのDataFrame

    Returns
    -------
    pd.DataFrame
        VIFクロス表（対角は1.0）
    """
    corr = calc_correlation_matrix(df)
    # VIF = 1 / (1 - r²) を各セルに適用
    r2_matrix = corr ** 2
    # 対角は1.0（自己相関r²=1でVIF=inf→代わりに1.0とする）
    vif_matrix = pd.DataFrame(
        np.where(
            r2_matrix >= 1.0,
            1.0,
            1.0 / (1.0 - r2_matrix),
        ),
        index=corr.index,
        columns=corr.columns,
    )
    return vif_matrix


# ============================================================
# テスト用エントリポイント
# ============================================================
if __name__ == "__main__":
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=50, freq="MS")

    # 相関のあるデータを意図的に作成
    x1 = np.random.normal(0, 1, 50)
    x2 = x1 * 0.8 + np.random.normal(0, 0.3, 50)  # x1と高い相関
    x3 = np.random.normal(0, 1, 50)  # 独立

    test_df = pd.DataFrame(
        {"var_a": x1, "var_b": x2, "var_c": x3},
        index=dates,
    )

    print("=== 相関行列 ===")
    corr = calc_correlation_matrix(test_df)
    print(corr.to_string(float_format="%.4f"))
    print()

    print("=== VIF ===")
    vif = calc_vif(test_df)
    print(vif.to_string(float_format="%.4f"))
    print()

    print("=== VIFクロス表 ===")
    vif_cross = calc_vif_cross_table(test_df)
    print(vif_cross.to_string(float_format="%.4f"))
