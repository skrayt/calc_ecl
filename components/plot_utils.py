"""描画ユーティリティモジュール

matplotlib Figure → base64 PNG文字列 → Flet ft.Image への変換と、
各種統計プロットの描画関数を提供する。

移植元: Craft_RegressionAnalysis/components/plot_utils.py
"""
import base64
from io import BytesIO
from math import ceil

import matplotlib
matplotlib.use("Agg")  # GUIバックエンドを使わない
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# フォントの設定（WinPython/macOS両対応）
# matplotlibキャッシュに存在するフォントのみ有効になるため、両環境分を列挙する
# Windows: "Yu Gothic", "Meiryo", "MS Gothic"
# macOS:   "YuGothic"（スペースなし）, "Hiragino Sans", "Hiragino Maru Gothic Pro"
import sys as _sys
import matplotlib.font_manager as _fm

def _get_available_fonts(candidates: list[str]) -> list[str]:
    """候補フォントのうちmatplotlibキャッシュに存在するものだけ返す"""
    registered = {f.name for f in _fm.fontManager.ttflist}
    return [f for f in candidates if f in registered]

_jp_font_candidates = [
    "Yu Gothic",                 # Windows（WinPython標準）
    "Meiryo",                    # Windows
    "MS Gothic",                 # Windows（フォールバック）
    "YuGothic",                  # macOS（スペースなし）
    "Hiragino Sans",             # macOS新
    "Hiragino Maru Gothic Pro",  # macOS旧
]
_available_fonts = _get_available_fonts(_jp_font_candidates) + ["Arial"]

# seabornの設定（先に行う。set_styleはrcParamsを上書きするためフォント設定より前に実行する）
sns.set_style("whitegrid")

# フォント設定はset_styleの後に行う（set_styleによる上書きを防ぐため）
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = _available_fonts
plt.rcParams["axes.unicode_minus"] = False

# デフォルトのfigsize
DEFAULT_FIGSIZE = (12, 6)


def fig_to_base64(fig: plt.Figure, dpi: int = 100) -> str:
    """matplotlib Figure → base64文字列に変換する

    Parameters
    ----------
    fig : plt.Figure
        matplotlib Figure オブジェクト
    dpi : int
        解像度（デフォルト: 100）

    Returns
    -------
    str
        base64エンコードされたPNG画像文字列
    """
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=dpi)
    buf.seek(0)
    img_base64 = base64.b64encode(buf.getvalue()).decode()
    plt.close(fig)
    return img_base64


def plot_single_series(
    df: pd.DataFrame,
    col: str,
    label: str | None = None,
    figsize: tuple = DEFAULT_FIGSIZE,
) -> str:
    """単一カラムの時系列プロット

    Parameters
    ----------
    df : pd.DataFrame
        DatetimeIndexのDataFrame
    col : str
        プロットするカラム名
    label : str | None
        凡例・タイトルに使う表示名。None のときは col をそのまま使う
    figsize : tuple
        グラフサイズ

    Returns
    -------
    str
        base64エンコードされたPNG画像
    """
    display = label or col
    fig, ax = plt.subplots(figsize=figsize)
    if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
        ax.plot(df.index, df[col], color="steelblue")
    ax.set_title(display, fontsize=13)
    ax.set_xlabel("日付", fontsize=10)
    ax.set_ylabel("値", fontsize=10)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.2f}".rstrip("0").rstrip(".")))
    ax.grid(True, linestyle="--", alpha=0.7)
    fig.tight_layout()
    return fig_to_base64(fig)


def plot_time_series(
    df: pd.DataFrame,
    columns: list[str],
    title: str = "時系列プロット",
    figsize: tuple = DEFAULT_FIGSIZE,
) -> str:
    """時系列プロット（複数カラム対応）

    Parameters
    ----------
    df : pd.DataFrame
        DatetimeIndexのDataFrame
    columns : list[str]
        プロットするカラム名リスト
    title : str
        グラフタイトル
    figsize : tuple
        グラフサイズ

    Returns
    -------
    str
        base64エンコードされたPNG画像
    """
    if not columns:
        return ""

    fig, ax = plt.subplots(figsize=figsize)
    for col in columns:
        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            ax.plot(df.index, df[col], label=col)

    ax.set_title(title, fontsize=14)
    ax.set_xlabel("日付", fontsize=10)
    ax.set_ylabel("値", fontsize=10)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.7)
    fig.tight_layout()

    return fig_to_base64(fig)


def plot_time_series_grid(
    df: pd.DataFrame,
    columns: list[str],
    n_cols: int = 2,
    figsize_per_plot: tuple = (6, 3),
) -> str:
    """複数の時系列データをグリッド形式でプロットする

    Parameters
    ----------
    df : pd.DataFrame
        DatetimeIndexのDataFrame
    columns : list[str]
        プロットするカラム名リスト
    n_cols : int
        グリッドの列数
    figsize_per_plot : tuple
        1つのグラフのサイズ

    Returns
    -------
    str
        base64エンコードされたPNG画像
    """
    if not columns:
        return ""

    n_rows = ceil(len(columns) / n_cols)
    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(figsize_per_plot[0] * n_cols, figsize_per_plot[1] * n_rows),
    )

    # 1行1列の場合の処理
    if n_rows == 1 and n_cols == 1:
        axes = np.array([[axes]])
    elif n_rows == 1:
        axes = axes.reshape(1, -1)
    elif n_cols == 1:
        axes = axes.reshape(-1, 1)

    colors = sns.color_palette("deep", len(columns))

    for idx, col in enumerate(columns):
        row = idx // n_cols
        col_idx = idx % n_cols
        ax = axes[row, col_idx]

        if col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            ax.plot(df.index, df[col], color=colors[idx], label=col)

        ax.set_title(col, fontsize=10)
        ax.tick_params(axis="x", rotation=45, labelsize=7)
        ax.tick_params(axis="y", labelsize=7)
        ax.grid(True, linestyle="--", alpha=0.7)
        ax.legend(fontsize=7)

    # 未使用のサブプロットを非表示
    for idx in range(len(columns), n_rows * n_cols):
        row = idx // n_cols
        col_idx = idx % n_cols
        axes[row, col_idx].set_visible(False)

    fig.tight_layout()
    return fig_to_base64(fig)


def plot_compare_series(
    series_list: list[pd.Series],
    labels: list[str],
    normalize: bool = False,
    dual_axis: bool = False,
    figsize: tuple = DEFAULT_FIGSIZE,
) -> str:
    """複数の時系列を1グラフに重ねて比較プロットする

    Parameters
    ----------
    series_list : list[pd.Series]
        プロットするSeries（DatetimeIndex）のリスト
    labels : list[str]
        各Seriesの表示名
    normalize : bool
        True のとき各系列を0-1に正規化して比較する
    dual_axis : bool
        True のとき先頭系列を左軸、残りを右軸に表示する（正規化と排他）
    figsize : tuple
        グラフサイズ

    Returns
    -------
    str
        base64エンコードされたPNG画像
    """
    if not series_list:
        return ""

    colors = sns.color_palette("tab10", len(series_list))
    fig, ax1 = plt.subplots(figsize=figsize)

    if normalize:
        # 各系列を0-1スケールに正規化
        for series, label, color in zip(series_list, labels, colors):
            s = series.dropna()
            if s.empty:
                continue
            mn, mx = s.min(), s.max()
            norm = (s - mn) / (mx - mn) if mx != mn else s * 0
            ax1.plot(norm.index, norm.values, label=f"{label} (正規化)", color=color)
        ax1.set_ylabel("正規化値 (0-1)", fontsize=10)

    elif dual_axis and len(series_list) >= 2:
        # 左軸: 1本目, 右軸: 2本目以降
        s0 = series_list[0].dropna()
        ax1.plot(s0.index, s0.values, label=labels[0], color=colors[0])
        ax1.set_ylabel(labels[0], fontsize=10, color=colors[0])
        ax1.tick_params(axis="y", labelcolor=colors[0])

        ax2 = ax1.twinx()
        for series, label, color in zip(series_list[1:], labels[1:], colors[1:]):
            s = series.dropna()
            ax2.plot(s.index, s.values, label=label, color=color, linestyle="--")
        ax2.set_ylabel(" / ".join(labels[1:]), fontsize=10)

        # 両軸の凡例を統合
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8)

    else:
        # 通常: 全系列を同一軸に重ねて表示
        for series, label, color in zip(series_list, labels, colors):
            s = series.dropna()
            ax1.plot(s.index, s.values, label=label, color=color)
        ax1.set_ylabel("値", fontsize=10)

    ax1.set_xlabel("日付", fontsize=10)
    ax1.tick_params(axis="x", rotation=45, labelsize=8)
    ax1.grid(True, linestyle="--", alpha=0.5)

    if not dual_axis or len(series_list) < 2:
        ax1.legend(loc="upper left", fontsize=8)

    title = "比較プロット"
    if normalize:
        title += "（正規化）"
    elif dual_axis:
        title += "（2軸表示）"
    ax1.set_title(title, fontsize=13)
    fig.tight_layout()
    return fig_to_base64(fig)


def plot_correlation_heatmap(
    corr_matrix: pd.DataFrame,
    title: str = "相関行列ヒートマップ",
    figsize: tuple = DEFAULT_FIGSIZE,
) -> str:
    """相関行列ヒートマップを描画する

    Parameters
    ----------
    corr_matrix : pd.DataFrame
        相関行列（correlation.calc_correlation_matrix() の戻り値）
    title : str
        グラフタイトル
    figsize : tuple
        グラフサイズ

    Returns
    -------
    str
        base64エンコードされたPNG画像
    """
    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(
        corr_matrix, annot=True, cmap="coolwarm",
        cbar=True, fmt=".2f", ax=ax, square=True,
    )
    ax.set_title(title, fontsize=14)
    plt.xticks(rotation=60, fontsize=8)
    plt.yticks(fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def plot_vif_heatmap(
    vif_matrix: pd.DataFrame,
    title: str = "VIFクロス表",
    figsize: tuple = DEFAULT_FIGSIZE,
) -> str:
    """VIFクロス表ヒートマップを描画する

    Parameters
    ----------
    vif_matrix : pd.DataFrame
        VIFクロス表（correlation.calc_vif_cross_table() の戻り値）
    title : str
        グラフタイトル
    figsize : tuple
        グラフサイズ

    Returns
    -------
    str
        base64エンコードされたPNG画像
    """
    fig, ax = plt.subplots(figsize=figsize)

    # VIF > 10 を赤くするカラーマップ
    sns.heatmap(
        vif_matrix.astype(float), annot=True, cmap="YlOrRd",
        cbar=True, fmt=".2f", ax=ax, square=True,
        vmin=1, vmax=20,
    )
    ax.set_title(title, fontsize=14)
    plt.xticks(rotation=60, fontsize=8)
    plt.yticks(fontsize=8)
    fig.tight_layout()
    return fig_to_base64(fig)


def plot_residuals(
    resid: pd.Series,
    fitted: pd.Series,
    figsize: tuple = (16, 4),
) -> str:
    """残差プロット（残差vs予測値、時系列残差プロット、残差ヒストグラム）

    Parameters
    ----------
    resid : pd.Series
        残差（DatetimeIndexであれば時系列プロットに日付を使用）
    fitted : pd.Series
        予測値
    figsize : tuple
        グラフサイズ（全体）

    Returns
    -------
    str
        base64エンコードされたPNG画像
    """
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=figsize)

    # 残差 vs 予測値
    ax1.scatter(fitted, resid, alpha=0.5, s=20)
    ax1.axhline(y=0, color="red", linestyle="--", alpha=0.7)
    ax1.set_title("残差 vs 予測値", fontsize=12)
    ax1.set_xlabel("予測値", fontsize=10)
    ax1.set_ylabel("残差", fontsize=10)
    ax1.grid(True, linestyle="--", alpha=0.5)

    # 時系列残差プロット
    ax2.plot(resid.index, resid.values, color="steelblue", linewidth=1.0)
    ax2.axhline(y=0, color="red", linestyle="--", alpha=0.7)
    ax2.set_title("時系列残差プロット", fontsize=12)
    ax2.set_xlabel("日付", fontsize=10)
    ax2.set_ylabel("残差", fontsize=10)
    ax2.tick_params(axis="x", rotation=45, labelsize=7)
    ax2.grid(True, linestyle="--", alpha=0.5)

    # 残差ヒストグラム
    ax3.hist(resid, bins=20, edgecolor="white", alpha=0.7)
    ax3.set_title("残差ヒストグラム", fontsize=12)
    ax3.set_xlabel("残差", fontsize=10)
    ax3.set_ylabel("頻度", fontsize=10)
    ax3.grid(True, linestyle="--", alpha=0.5)

    fig.tight_layout()
    return fig_to_base64(fig)


def plot_acf_pacf(
    acf_values: np.ndarray,
    pacf_values: np.ndarray,
    acf_confint: np.ndarray,
    pacf_confint: np.ndarray,
    figsize: tuple = (12, 4),
) -> str:
    """ACF/PACFプロットを描画する

    Parameters
    ----------
    acf_values : np.ndarray
        ACF値
    pacf_values : np.ndarray
        PACF値
    acf_confint : np.ndarray
        ACFの信頼区間
    pacf_confint : np.ndarray
        PACFの信頼区間
    figsize : tuple
        グラフサイズ

    Returns
    -------
    str
        base64エンコードされたPNG画像
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize)
    nlags = len(acf_values) - 1

    # ACF
    ax1.bar(range(nlags + 1), acf_values, width=0.3, color="steelblue", alpha=0.7)
    # 信頼区間
    ax1.fill_between(
        range(nlags + 1),
        acf_confint[:, 0] - acf_values,
        acf_confint[:, 1] - acf_values,
        alpha=0.2, color="blue",
    )
    ax1.axhline(y=0, color="black", linewidth=0.5)
    ax1.set_title("ACF（自己相関関数）", fontsize=12)
    ax1.set_xlabel("ラグ", fontsize=10)

    # PACF
    ax2.bar(range(nlags + 1), pacf_values, width=0.3, color="darkorange", alpha=0.7)
    ax2.fill_between(
        range(nlags + 1),
        pacf_confint[:, 0] - pacf_values,
        pacf_confint[:, 1] - pacf_values,
        alpha=0.2, color="orange",
    )
    ax2.axhline(y=0, color="black", linewidth=0.5)
    ax2.set_title("PACF（偏自己相関関数）", fontsize=12)
    ax2.set_xlabel("ラグ", fontsize=10)

    fig.tight_layout()
    return fig_to_base64(fig)


def plot_forecast(
    y_history: pd.Series,
    forecast_df: pd.DataFrame,
    title: str = "将来予測",
    figsize: tuple = DEFAULT_FIGSIZE,
) -> str:
    """予測結果プロット（実績+予測+信頼区間）

    Parameters
    ----------
    y_history : pd.Series
        実績データ（DatetimeIndex）
    forecast_df : pd.DataFrame
        forecast() 関数の戻り値。カラム: forecast, lower, upper
    title : str
        グラフタイトル
    figsize : tuple
        グラフサイズ

    Returns
    -------
    str
        base64エンコードされたPNG画像
    """
    fig, ax = plt.subplots(figsize=figsize)

    # 実績
    ax.plot(y_history.index, y_history.values, label="実績", color="steelblue")

    # 予測
    ax.plot(forecast_df.index, forecast_df["forecast"],
            label="予測", color="darkorange", linestyle="--")

    # 信頼区間
    ax.fill_between(
        forecast_df.index,
        forecast_df["lower"],
        forecast_df["upper"],
        alpha=0.2, color="orange", label="95%信頼区間",
    )

    ax.set_title(title, fontsize=14)
    ax.set_xlabel("日付", fontsize=10)
    ax.set_ylabel("値", fontsize=10)
    ax.tick_params(axis="x", rotation=45, labelsize=8)
    ax.legend(fontsize=9)
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()

    return fig_to_base64(fig)
