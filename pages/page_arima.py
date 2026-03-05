"""ARIMAページ

ARIMA時系列モデルの学習・次数選択・将来予測を行う。
"""
import flet as ft
import pandas as pd
import numpy as np

from components.plot_utils import plot_acf_pacf, plot_forecast
from components.help_panel import build_help_panel
from src.data.indicator_loader import get_indicator_definitions
from src.analysis.arima import (
    fit_arima,
    auto_select_order,
    forecast,
    test_stationarity,
    calc_acf_pacf,
)


def arima_page(page: ft.Page) -> ft.Control:
    """ARIMAタブのUIを構築する"""
    print("DEBUG: ARIMAページ構築開始")

    df: pd.DataFrame | None = page.session.store.get("df")
    if df is None or df.empty:
        return ft.Text("先にデータ閲覧タブでデータを読み込んでください。", color=ft.Colors.RED_700)

    columns = df.columns.tolist()

    # indicator_code → indicator_name のマッピングを取得
    defs = get_indicator_definitions(columns)
    code_to_name: dict[str, str] = dict(zip(defs["indicator_code"], defs["indicator_name"]))

    # UI部品
    target_dropdown = ft.Dropdown(
        label="対象変数",
        options=[ft.dropdown.Option(key=c, text=code_to_name.get(c, c)) for c in columns],
        value=columns[0] if columns else None,
        width=300,
    )

    # ARIMA次数設定
    p_input = ft.TextField(label="p (AR)", value="1", width=80, keyboard_type=ft.KeyboardType.NUMBER)
    d_input = ft.TextField(label="d (差分)", value="1", width=80, keyboard_type=ft.KeyboardType.NUMBER)
    q_input = ft.TextField(label="q (MA)", value="1", width=80, keyboard_type=ft.KeyboardType.NUMBER)

    # 自動選択設定
    max_p_input = ft.TextField(label="max_p", value="3", width=80, keyboard_type=ft.KeyboardType.NUMBER)
    max_d_input = ft.TextField(label="max_d", value="2", width=80, keyboard_type=ft.KeyboardType.NUMBER)
    max_q_input = ft.TextField(label="max_q", value="3", width=80, keyboard_type=ft.KeyboardType.NUMBER)

    forecast_steps = ft.TextField(label="予測期間", value="12", width=100, keyboard_type=ft.KeyboardType.NUMBER)

    progress_bar = ft.ProgressBar(visible=False)
    progress_text = ft.Text("", size=11)
    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)

    def run_adf_test(e):
        """ADF検定を実行する"""
        col = target_dropdown.value
        if not col:
            return

        print(f"DEBUG: ADF検定実行: {col}")
        try:
            y = df[col].dropna()
            adf = test_stationarity(y)

            results = [ft.Text("ADF検定（定常性検定）", size=18, weight=ft.FontWeight.BOLD)]
            adf_data = [
                ("ADF統計量", f"{adf['adf_stat']:.4f}"),
                ("p値", f"{adf['p_value']:.4f}"),
                ("使用ラグ", str(adf['used_lag'])),
                ("観測数", str(adf['n_obs'])),
                ("定常性", "あり ✓" if adf['is_stationary'] else "なし ✗"),
            ]
            for k, v in adf['critical_values'].items():
                adf_data.append((f"臨界値 ({k})", f"{v:.4f}"))

            results.append(ft.DataTable(
                columns=[ft.DataColumn(ft.Text("項目")), ft.DataColumn(ft.Text("値"))],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(k)), ft.DataCell(ft.Text(v))]) for k, v in adf_data],
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            if not adf['is_stationary']:
                results.append(ft.Text(
                    "⚠ データは非定常です。差分(d≥1)を取ることを推奨します。",
                    color=ft.Colors.ORANGE_700, size=12,
                ))

            # ACF/PACF
            acf_pacf = calc_acf_pacf(y, nlags=20)
            img = plot_acf_pacf(
                acf_pacf["acf_values"], acf_pacf["pacf_values"],
                acf_pacf["acf_confint"], acf_pacf["pacf_confint"],
            )
            results.append(ft.Divider())
            results.append(ft.Text("ACF / PACF", size=18, weight=ft.FontWeight.BOLD))
            results.append(ft.Image(src="data:image/png;base64," + img, fit=ft.BoxFit.CONTAIN))

            result_container.controls = results
            print("DEBUG: ADF検定完了")
        except Exception as ex:
            print(f"DEBUG: ADF検定エラー: {ex}")
            result_container.controls = [ft.Text(f"エラー: {ex}", color=ft.Colors.RED_700)]
        page.update()

    def run_arima_manual(e):
        """手動次数でARIMA学習"""
        col = target_dropdown.value
        if not col:
            return

        order = (int(p_input.value), int(d_input.value), int(q_input.value))
        print(f"DEBUG: ARIMA{order} 学習開始")
        result_container.controls = [ft.ProgressRing()]
        page.update()

        try:
            y = df[col].dropna()
            result = fit_arima(y, order=order)
            _show_arima_result(y, result)
        except Exception as ex:
            print(f"DEBUG: ARIMA学習エラー: {ex}")
            result_container.controls = [ft.Text(f"学習エラー: {ex}", color=ft.Colors.RED_700)]
        page.update()

    def run_auto_select(e):
        """次数自動選択"""
        col = target_dropdown.value
        if not col:
            return

        print("DEBUG: ARIMA次数自動選択開始")
        progress_bar.visible = True
        progress_bar.value = 0
        result_container.controls = [ft.Text("自動選択中...")]
        page.update()

        def progress_callback(current, total):
            progress_bar.value = current / total
            progress_text.value = f"{current}/{total}"
            page.update()

        try:
            y = df[col].dropna()
            auto = auto_select_order(
                y,
                max_p=int(max_p_input.value),
                max_d=int(max_d_input.value),
                max_q=int(max_q_input.value),
                progress_callback=progress_callback,
            )

            progress_bar.visible = False

            results = [ft.Text("次数自動選択結果", size=18, weight=ft.FontWeight.BOLD)]
            results.append(ft.Text(
                f"最良次数: ARIMA{auto['best_order']} | AIC: {auto['best_aic']:.2f} | BIC: {auto['best_bic']:.2f}",
                size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700,
            ))

            # 上位10モデル
            top10 = auto["all_results"].head(10)
            results.append(ft.Text("上位10モデル:", size=14))
            results.append(ft.DataTable(
                columns=[ft.DataColumn(ft.Text(c, size=11)) for c in ["p", "d", "q", "aic", "bic", "converged"]],
                rows=[ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(int(row["p"])))),
                    ft.DataCell(ft.Text(str(int(row["d"])))),
                    ft.DataCell(ft.Text(str(int(row["q"])))),
                    ft.DataCell(ft.Text(f"{row['aic']:.2f}" if row["aic"] != np.inf else "∞")),
                    ft.DataCell(ft.Text(f"{row['bic']:.2f}" if row["bic"] != np.inf else "∞")),
                    ft.DataCell(ft.Text("✓" if row["converged"] else "✗")),
                ]) for _, row in top10.iterrows()],
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # 最良モデルで予測
            _add_forecast(y, auto["best_model"], auto["best_order"], results)

            result_container.controls = results
            print(f"DEBUG: 自動選択完了 → ARIMA{auto['best_order']}")

        except Exception as ex:
            print(f"DEBUG: 自動選択エラー: {ex}")
            progress_bar.visible = False
            result_container.controls = [ft.Text(f"エラー: {ex}", color=ft.Colors.RED_700)]
        page.update()

    def _show_arima_result(y: pd.Series, result: dict):
        """ARIMA結果を表示する"""
        results = [ft.Text(f"ARIMA{result['order']} 学習結果", size=18, weight=ft.FontWeight.BOLD)]
        results.append(ft.Text(f"AIC: {result['aic']:.2f} | BIC: {result['bic']:.2f} | 観測数: {result['nobs']}"))

        # パラメータ
        params = result["params"]
        results.append(ft.DataTable(
            columns=[ft.DataColumn(ft.Text("パラメータ")), ft.DataColumn(ft.Text("値"))],
            rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(k)), ft.DataCell(ft.Text(f"{v:.6f}"))]) for k, v in params.items()],
            border=ft.border.all(1, ft.Colors.GREY_300),
        ))

        _add_forecast(y, result["model"], result["order"], results)
        result_container.controls = results

    def _add_forecast(y: pd.Series, model, order: tuple, results: list):
        """予測結果を追加する"""
        steps = int(forecast_steps.value)
        try:
            fc = forecast(model, steps=steps)
            img = plot_forecast(y, fc, title=f"ARIMA{order} 予測（{steps}期先）")
            results.append(ft.Divider())
            results.append(ft.Text(f"将来予測（{steps}期先）", size=16, weight=ft.FontWeight.BOLD))
            results.append(ft.Image(src="data:image/png;base64," + img, fit=ft.BoxFit.CONTAIN))
        except Exception as ex:
            results.append(ft.Text(f"予測エラー: {ex}", color=ft.Colors.ORANGE_700))

    # レイアウト
    _help = build_help_panel(
        title="⑥ ARIMA分析",
        purpose="単一の時系列変数に対してARIMA(p,d,q)モデルを学習し、将来値を予測します。",
        steps=[
            "対象変数ドロップダウンで分析したい指標を選ぶ",
            "「ADF検定 + ACF/PACF」で定常性を確認し、適切なd（差分次数）を判断する",
            "【手動】p・d・qを入力して「ARIMA学習」を押す、または",
            "【自動】max_p/max_d/max_qを指定して「自動選択実行」を押す（AIC最小モデルを選択）",
            "予測期間を入力して予測グラフを確認する",
        ],
        outputs=[
            "ADF検定結果（ADF統計量・p値・定常性判定）",
            "ACF/PACFグラフ（自己相関・偏自己相関、信頼区間付き）",
            "自動選択：上位10モデルテーブル（p・d・q・AIC・BIC・収束判定）",
            "将来予測グラフ（実績 + 予測値の時系列）",
        ],
    )
    return ft.Column(
        controls=[
            _help,
            ft.Text("ARIMA分析", size=24, weight=ft.FontWeight.BOLD),
            target_dropdown,
            ft.ElevatedButton("ADF検定 + ACF/PACF", on_click=run_adf_test, icon=ft.Icons.ASSESSMENT),
            ft.Divider(),
            ft.Text("手動次数指定", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([p_input, d_input, q_input, forecast_steps]),
            ft.ElevatedButton("ARIMA学習", on_click=run_arima_manual, icon=ft.Icons.PLAY_ARROW),
            ft.Divider(),
            ft.Text("次数自動選択", size=16, weight=ft.FontWeight.BOLD),
            ft.Row([max_p_input, max_d_input, max_q_input]),
            progress_bar,
            progress_text,
            ft.ElevatedButton("自動選択実行", on_click=run_auto_select, icon=ft.Icons.AUTO_FIX_HIGH),
            ft.Divider(),
            result_container,
        ],
        spacing=10,
        expand=True,
    )
