"""動的回帰ページ

変数ごとの個別変換・標準化・ラグ設定による時系列回帰分析を行う。
"""
import flet as ft
import pandas as pd

from components.variable_selector import VariableSelector
from components.plot_utils import plot_residuals
from src.analysis.data_transform import transform_per_column
from src.analysis.regression import fit_ols


def dynamic_regression_page(page: ft.Page) -> ft.Control:
    """動的回帰タブのUIを構築する"""
    print("DEBUG: 動的回帰ページ構築開始")

    df: pd.DataFrame | None = page.session.get("df")
    if df is None or df.empty:
        return ft.Text("先にデータ閲覧タブでデータを読み込んでください。", color=ft.Colors.RED_700)

    # 変数セレクタ（変数ごとの変換・標準化設定あり）
    selector = VariableSelector(
        page=page,
        columns=df.columns.tolist(),
        show_target=True,
        show_transform=True,
    )

    # 変数ごとのラグ設定用コンテナ
    lag_settings_container = ft.Column(spacing=5)
    lag_values: dict[str, int] = {}

    def update_lag_settings():
        """選択された変数に合わせてラグスライダーを表示する"""
        lag_settings_container.controls.clear()
        features = selector.get_selected_features()
        for col in features:
            if col not in lag_values:
                lag_values[col] = 0
            slider = ft.Slider(
                min=0, max=12, divisions=12,
                value=lag_values.get(col, 0),
                label=f"{col}: " + "{value}",
                width=300,
                on_change=lambda e, c=col: _on_lag_change(e, c),
            )
            lag_settings_container.controls.append(
                ft.Row([ft.Text(col, width=200, size=12), slider])
            )
        page.update()

    def _on_lag_change(e, col: str):
        lag_values[col] = int(e.control.value)

    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)

    def run_analysis(e):
        """分析実行"""
        update_lag_settings()

        target = selector.get_target()
        features = selector.get_selected_features()
        if not target or not features:
            result_container.controls = [ft.Text("目的変数と説明変数を選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        settings = selector.get_variable_settings()
        print(f"DEBUG: 動的回帰実行 target={target}, features={features}, settings={settings}")

        result_container.controls = [ft.ProgressRing()]
        page.update()

        try:
            # 変数ごとの個別変換
            cols = [target] + features
            work_df = transform_per_column(df[cols], settings)

            y = work_df[target]
            X = work_df[features]

            # ラグは最大値を使用（動的回帰の場合）
            max_lag = max(lag_values.get(f, 0) for f in features) if features else 0

            ols = fit_ols(y, X, lag=max_lag)

            results = []
            results.append(ft.Text("動的回帰結果", size=18, weight=ft.FontWeight.BOLD))

            # 変換設定の表示
            setting_rows = []
            for col in cols:
                s = settings.get(col, {})
                setting_rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(col)),
                    ft.DataCell(ft.Text(s.get("transform", "none"))),
                    ft.DataCell(ft.Text("✓" if s.get("standardize") else "")),
                    ft.DataCell(ft.Text(str(lag_values.get(col, 0)))),
                ]))
            results.append(ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("変数")),
                    ft.DataColumn(ft.Text("変換")),
                    ft.DataColumn(ft.Text("標準化")),
                    ft.DataColumn(ft.Text("ラグ")),
                ],
                rows=setting_rows,
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # モデル概要
            results.append(ft.Divider())
            summary = [
                ("R²", f"{ols['r2']:.4f}"), ("Adj. R²", f"{ols['adj_r2']:.4f}"),
                ("AIC", f"{ols['aic']:.2f}"), ("BIC", f"{ols['bic']:.2f}"),
                ("DW", f"{ols['dw']:.4f}"), ("F統計量", f"{ols['f_stat']:.4f}"),
                ("観測数", str(ols['nobs'])),
            ]
            results.append(ft.DataTable(
                columns=[ft.DataColumn(ft.Text("指標")), ft.DataColumn(ft.Text("値"))],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(k)), ft.DataCell(ft.Text(v))]) for k, v in summary],
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # 係数テーブル
            results.append(ft.Divider())
            results.append(ft.Text("係数テーブル", size=16, weight=ft.FontWeight.BOLD))
            coef_df = ols["coefficients"]
            results.append(ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("変数")), ft.DataColumn(ft.Text("係数")),
                    ft.DataColumn(ft.Text("標準誤差")), ft.DataColumn(ft.Text("t値")),
                    ft.DataColumn(ft.Text("p値")),
                ],
                rows=[ft.DataRow(cells=[
                    ft.DataCell(ft.Text(row["variable"])),
                    ft.DataCell(ft.Text(f"{row['coef']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['std_err']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['t_stat']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['p_value']:.4f}",
                        color=ft.Colors.RED_700 if row["p_value"] > 0.05 else None)),
                ]) for _, row in coef_df.iterrows()],
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # 残差プロット
            results.append(ft.Divider())
            img = plot_residuals(ols["resid"], ols["fitted"])
            results.append(ft.Image(src_base64=img, fit=ft.ImageFit.CONTAIN))

            result_container.controls = results
            print("DEBUG: 動的回帰完了")

        except Exception as ex:
            print(f"DEBUG: 動的回帰エラー: {ex}")
            result_container.controls = [ft.Text(f"分析エラー: {ex}", color=ft.Colors.RED_700)]

        page.update()

    return ft.Column(
        controls=[
            ft.Text("動的回帰（変数別設定）", size=24, weight=ft.FontWeight.BOLD),
            selector.get_ui(),
            ft.Text("変数ごとのラグ設定:", size=14, weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("ラグ設定を更新", on_click=lambda e: update_lag_settings()),
            lag_settings_container,
            ft.ElevatedButton("分析実行", on_click=run_analysis, icon=ft.Icons.ANALYTICS),
            ft.Divider(),
            result_container,
        ],
        spacing=10,
        expand=True,
    )
