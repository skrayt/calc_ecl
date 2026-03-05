"""回帰分析ページ

OLS回帰分析・係数テーブル・残差プロット・交差検証の表示を行う。
"""
import flet as ft
import pandas as pd

from components.variable_selector import VariableSelector
from components.plot_utils import plot_residuals
from components.help_panel import build_help_panel
from src.analysis.data_transform import transform, standardize, TRANSFORM_METHODS
from src.analysis.regression import fit_ols, cross_validate
from src.data.indicator_loader import get_indicator_definitions


def regression_page(page: ft.Page) -> ft.Control:
    """回帰分析タブのUIを構築する"""
    print("DEBUG: 回帰分析ページ構築開始")

    df: pd.DataFrame | None = page.session.store.get("df")
    if df is None or df.empty:
        return ft.Text("先にデータ閲覧タブでデータを読み込んでください。", color=ft.Colors.RED_700)

    # indicator_code → indicator_name のマッピングを取得
    defs = get_indicator_definitions(df.columns.tolist())
    code_to_name: dict[str, str] = dict(zip(defs["indicator_code"], defs["indicator_name"]))

    selector = VariableSelector(
        page=page,
        columns=df.columns.tolist(),
        show_target=True,
        show_transform=False,
        code_to_name=code_to_name,
    )

    transform_dropdown = ft.Dropdown(
        label="データ変換",
        options=[ft.dropdown.Option(key=k, text=v) for k, v in TRANSFORM_METHODS.items()],
        value="none",
        width=300,
    )
    standardize_switch = ft.Switch(label="標準化", value=True)
    lag_slider = ft.Slider(
        min=0, max=12, divisions=12, label="ラグ: {value}",
        value=0, width=300,
    )
    lag_label = ft.Text("ラグ: 0", size=12)
    cv_folds_input = ft.TextField(
        label="交差検証 分割数", value="5", width=100,
        keyboard_type=ft.KeyboardType.NUMBER,
    )

    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)

    def on_lag_change(e):
        lag_label.value = f"ラグ: {int(lag_slider.value)}"
        page.update()

    lag_slider.on_change = on_lag_change

    def run_analysis(e):
        """分析実行"""
        target = selector.get_target()
        features = selector.get_selected_features()
        if not target or not features:
            result_container.controls = [ft.Text("目的変数と説明変数を選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        print(f"DEBUG: 回帰分析実行 target={target}, features={features}, lag={int(lag_slider.value)}")
        result_container.controls = [ft.ProgressRing()]
        page.update()

        try:
            cols = [target] + features
            work_df = df[cols].copy()
            work_df = transform(work_df, transform_dropdown.value)
            if standardize_switch.value:
                work_df = standardize(work_df)

            y = work_df[target]
            X = work_df[features]
            lag = int(lag_slider.value)

            # OLS回帰
            ols = fit_ols(y, X, lag=lag)

            results = []
            results.append(ft.Text("モデル概要", size=18, weight=ft.FontWeight.BOLD))

            # 概要テーブル
            summary_data = [
                ("R²", f"{ols['r2']:.4f}"),
                ("Adj. R²", f"{ols['adj_r2']:.4f}"),
                ("AIC", f"{ols['aic']:.2f}"),
                ("BIC", f"{ols['bic']:.2f}"),
                ("Durbin-Watson", f"{ols['dw']:.4f}"),
                ("F統計量", f"{ols['f_stat']:.4f}"),
                ("F検定 p値", f"{ols['f_pvalue']:.4e}"),
                ("観測数", str(ols['nobs'])),
            ]
            summary_table = ft.DataTable(
                columns=[ft.DataColumn(ft.Text("指標")), ft.DataColumn(ft.Text("値"))],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(k)), ft.DataCell(ft.Text(v))]) for k, v in summary_data],
                border=ft.border.all(1, ft.Colors.GREY_300),
            )
            results.append(summary_table)

            # 係数テーブル
            results.append(ft.Divider())
            results.append(ft.Text("係数テーブル", size=18, weight=ft.FontWeight.BOLD))
            coef_df = ols["coefficients"]
            coef_table = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("変数")),
                    ft.DataColumn(ft.Text("係数"), numeric=True),
                    ft.DataColumn(ft.Text("標準誤差"), numeric=True),
                    ft.DataColumn(ft.Text("t値"), numeric=True),
                    ft.DataColumn(ft.Text("p値"), numeric=True),
                ],
                rows=[
                    ft.DataRow(cells=[
                        ft.DataCell(ft.Text(code_to_name.get(row["variable"], row["variable"]))),
                        ft.DataCell(ft.Text(f"{row['coef']:.4f}")),
                        ft.DataCell(ft.Text(f"{row['std_err']:.4f}")),
                        ft.DataCell(ft.Text(f"{row['t_stat']:.4f}")),
                        ft.DataCell(ft.Text(
                            f"{row['p_value']:.4f}",
                            color=ft.Colors.RED_700 if row["p_value"] > 0.05 else None,
                        )),
                    ])
                    for _, row in coef_df.iterrows()
                ],
                border=ft.border.all(1, ft.Colors.GREY_300),
            )
            results.append(coef_table)

            # 残差プロット
            results.append(ft.Divider())
            results.append(ft.Text("残差プロット", size=18, weight=ft.FontWeight.BOLD))
            img_resid = plot_residuals(ols["resid"], ols["fitted"])
            results.append(ft.Image(src="data:image/png;base64," + img_resid, fit=ft.BoxFit.CONTAIN))

            # 交差検証
            try:
                cv_k = int(cv_folds_input.value)
                cv_result = cross_validate(y, X, cv=cv_k, lag=lag)
                results.append(ft.Divider())
                results.append(ft.Text("交差検証", size=18, weight=ft.FontWeight.BOLD))
                results.append(ft.Text(f"平均MSE: {cv_result['mean_mse']:.4f} (±{cv_result['std_mse']:.4f})"))
            except Exception as cv_ex:
                results.append(ft.Text(f"交差検証エラー: {cv_ex}", color=ft.Colors.ORANGE_700))

            result_container.controls = results
            print("DEBUG: 回帰分析完了")

        except Exception as ex:
            print(f"DEBUG: 回帰分析エラー: {ex}")
            result_container.controls = [ft.Text(f"分析エラー: {ex}", color=ft.Colors.RED_700)]

        page.update()

    _help = build_help_panel(
        title="③ 回帰分析",
        purpose="OLS（最小二乗法）で回帰モデルを構築し、係数・適合度・残差を評価します。",
        steps=[
            "変数セレクタで目的変数と説明変数を選択する",
            "データ変換・標準化・ラグ期間（0〜12）を設定する",
            "交差検証の分割数を指定する（デフォルト5）",
            "「分析実行」を押す",
        ],
        outputs=[
            "モデル概要（R²・Adj.R²・AIC・BIC・Durbin-Watson・F統計量）",
            "係数テーブル（係数・標準誤差・t値・p値、p > 0.05 は赤色）",
            "残差プロット（正規性・等分散性の診断）",
            "交差検証結果（平均MSE ± 標準偏差）",
        ],
    )
    return ft.Column(
        controls=[
            _help,
            ft.Text("回帰分析", size=24, weight=ft.FontWeight.BOLD),
            selector.get_ui(),
            ft.Row([transform_dropdown, standardize_switch]),
            ft.Row([lag_slider, lag_label, cv_folds_input]),
            ft.ElevatedButton("分析実行", on_click=run_analysis, icon=ft.Icons.ANALYTICS),
            ft.Divider(),
            result_container,
        ],
        spacing=10,
        expand=True,
    )
