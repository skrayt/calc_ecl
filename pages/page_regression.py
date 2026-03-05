"""回帰分析ページ

OLS回帰分析・係数テーブル・残差プロット・交差検証の表示を行う。
"""
import flet as ft
import pandas as pd

from components.variable_selector import VariableSelector
from components.plot_utils import plot_residuals
from components.help_panel import build_help_panel
from components.data_source_selector import DataSourceSelector
from src.analysis.data_transform import transform, standardize, TRANSFORM_METHODS
from src.analysis.regression import fit_ols, cross_validate
from src.data.indicator_loader import (
    merge_target_and_indicators,
)


def regression_page(page: ft.Page) -> ft.Control:
    """回帰分析タブのUIを構築する"""
    print("DEBUG: 回帰分析ページ構築開始")

    # 変数セレクタ（後から構築）
    selector_container = ft.Column()
    selector_ref = [None]
    ind_df_ref = [None]
    tgt_df_ref = [None]
    code_to_name_ref = [{}]

    def on_data_loaded(indicator_df, target_df, code_to_name, target_c2n):
        """データソース変更時に変数セレクタを再構築する"""
        ind_df_ref[0] = indicator_df
        tgt_df_ref[0] = target_df
        all_c2n = dict(code_to_name)
        all_c2n.update(target_c2n)
        code_to_name_ref[0] = all_c2n

        columns = indicator_df.columns.tolist() if indicator_df is not None and not indicator_df.empty else []
        target_cols = target_df.columns.tolist() if target_df is not None and not target_df.empty else None

        if not columns:
            selector_container.controls = [
                ft.Text("説明変数データがありません。データソースを選択してください。", color=ft.Colors.ORANGE_700)
            ]
            selector_ref[0] = None
            page.update()
            return

        selector_ref[0] = VariableSelector(
            page=page,
            columns=columns,
            show_target=True,
            show_transform=False,
            code_to_name=all_c2n,
            target_columns=target_cols,
            target_code_to_name=target_c2n,
        )
        selector_container.controls = [selector_ref[0].get_ui()]
        page.update()

    data_source = DataSourceSelector(page=page, on_data_loaded=on_data_loaded)

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
        selector = selector_ref[0]
        if selector is None:
            result_container.controls = [ft.Text("データソースを選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        target = selector.get_target()
        features = selector.get_selected_features()
        if not target or not features:
            result_container.controls = [ft.Text("目的変数と説明変数を選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        df = ind_df_ref[0]
        target_df = tgt_df_ref[0]
        c2n = code_to_name_ref[0]

        print(f"DEBUG: 回帰分析実行 target={target}, features={features}, lag={int(lag_slider.value)}")
        result_container.controls = [ft.ProgressRing()]
        page.update()

        try:
            # 目的変数が別ソース（target_data）の場合はマージ
            if target_df is not None and not target_df.empty and target in target_df.columns:
                work_df = merge_target_and_indicators(target_df, df[features], target)
            else:
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
                        ft.DataCell(ft.Text(c2n.get(row["variable"], row["variable"]))),
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
        purpose="OLS（最小二乗法）で回帰モデルを構築し、係数・適合度・残差を評価します。良いモデルの目安: Adj.R² > 0.7、p値 < 0.05（全係数）、Durbin-Watson 1.5〜2.5。",
        steps=[
            "データソース選択で説明変数・目的変数のデータセットとfrequencyを選ぶ（frequencyを揃える）",
            "変数セレクタで目的変数と説明変数を選択する",
            "データ変換・標準化・ラグ期間（0〜12）を設定する",
            "交差検証の分割数を指定する（デフォルト5）",
            "「分析実行」を押す",
            "係数テーブルで赤色のp値（> 0.05）の変数は有意でないため除外を検討する",
            "残差プロットでパターンがあれば変換や変数追加を検討する",
        ],
        outputs=[
            "モデル概要（R²・Adj.R²・AIC・BIC・Durbin-Watson・F統計量）",
            "係数テーブル（係数・標準誤差・t値・p値、p > 0.05 は赤色）",
            "残差プロット（正規性・等分散性の診断）",
            "交差検証結果（平均MSE ± 標準偏差）",
        ],
        indicators=[
            {
                "name": "R²（決定係数）・Adj.R²（自由度調整済み）",
                "criteria": [
                    {"level": "良好",  "range": "Adj.R² ≥ 0.7",          "meaning": "モデルが目的変数の変動の70%以上を説明できている"},
                    {"level": "注意",  "range": "0.4 ≤ Adj.R² < 0.7",    "meaning": "説明力は中程度。変数の追加・変換を検討"},
                    {"level": "危険",  "range": "Adj.R² < 0.4",           "meaning": "説明力が低い。変数選択・データ変換を見直す"},
                ],
                "note": "変数を増やすとR²は常に上がるが、Adj.R²は不要な変数を増やすと下がる。Adj.R²を重視すること",
            },
            {
                "name": "p値（各係数の有意性検定）",
                "criteria": [
                    {"level": "良好",  "range": "p < 0.05",  "meaning": "統計的に有意。その変数はモデルに貢献している"},
                    {"level": "注意",  "range": "0.05 ≤ p < 0.1", "meaning": "10%水準で有意。業務的重要性があれば残すことも可"},
                    {"level": "危険",  "range": "p ≥ 0.1",   "meaning": "有意でない。モデルから除外することを検討する"},
                ],
                "note": "係数テーブルで赤色表示される行がp ≥ 0.05の変数。Intercept（定数項）のp値は参考程度でよい",
            },
            {
                "name": "Durbin-Watson統計量（残差の自己相関検定）",
                "criteria": [
                    {"level": "良好",  "range": "1.5 ≤ DW ≤ 2.5", "meaning": "残差に自己相関なし。モデルの仮定を満たしている"},
                    {"level": "注意",  "range": "1.0 ≤ DW < 1.5 または 2.5 < DW ≤ 3.0", "meaning": "軽度の自己相関の可能性。ラグ変数の追加を検討"},
                    {"level": "危険",  "range": "DW < 1.0 または DW > 3.0", "meaning": "強い自己相関あり。時系列モデル（ARIMA等）への切り替えを検討"},
                ],
                "note": "DW ≈ 2 が理想。DW < 2 は正の自己相関、DW > 2 は負の自己相関を示す",
            },
            {
                "name": "F統計量・F検定のp値（モデル全体の有意性）",
                "criteria": [
                    {"level": "良好",  "range": "F検定 p < 0.05", "meaning": "モデル全体として統計的に有意。少なくとも1つの変数が有効"},
                    {"level": "危険",  "range": "F検定 p ≥ 0.05", "meaning": "モデル全体が有意でない。変数選択を根本から見直す"},
                ],
                "note": "F統計量の数値が大きいほどモデルの説明力が高い傾向にある",
            },
            {
                "name": "AIC / BIC（情報量基準、モデル比較用）",
                "criteria": [
                    {"level": "情報",  "range": "AIC・BICが小さい方が良い", "meaning": "複数モデルを比較する際に使用。絶対値自体には意味がない"},
                    {"level": "注意",  "range": "ΔAIC > 2",               "meaning": "AICが2以上大きいモデルは明確に劣る"},
                    {"level": "情報",  "range": "BICはAICより変数に厳しい",  "meaning": "BICは変数が多いほど強くペナルティを課すため、簡潔なモデルを選ぶ傾向"},
                ],
                "note": "同一データセット内での相対比較にのみ使用。異なるデータセット間での比較には使用しない",
            },
        ],
    )
    return ft.Column(
        controls=[
            _help,
            ft.Text("回帰分析", size=24, weight=ft.FontWeight.BOLD),
            data_source.get_ui(),
            selector_container,
            ft.Row([transform_dropdown, standardize_switch]),
            ft.Row([lag_slider, lag_label, cv_folds_input]),
            ft.ElevatedButton("分析実行", on_click=run_analysis, icon=ft.Icons.ANALYTICS),
            ft.Divider(),
            result_container,
        ],
        spacing=10,
        expand=True,
    )
