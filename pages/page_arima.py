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
from src.db_operations import save_arima_forecast


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

    # ACF/PACF nlags設定（空欄で自動選択）
    nlags_input = ft.TextField(
        label="ACF/PACF nlagsオプション",
        hint_text="空欄で自動",
        width=180,
        keyboard_type=ft.KeyboardType.NUMBER,
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

    # 最後に実行したARIMA予測の状態を保持する
    last_forecast_ref = [None]
    # {"indicator_code": str, "order": tuple, "steps": int, "fc_df": pd.DataFrame}

    # 予測結果保存UI
    save_note_input = ft.TextField(
        label="メモ（任意）",
        hint_text="例: 2026年度 ベースシナリオ用",
        width=300,
    )
    save_status_text = ft.Text("", size=12)
    save_section = ft.Container(
        visible=False,
        content=ft.Column([
            ft.Text("予測結果をDBに保存", size=14, weight=ft.FontWeight.BOLD),
            save_note_input,
            ft.Row([
                ft.ElevatedButton(
                    "DBに保存",
                    icon=ft.Icons.SAVE,
                    on_click=lambda e: _save_forecast(e),
                ),
                save_status_text,
            ]),
        ]),
        padding=10,
        border=ft.border.all(1, ft.Colors.GREEN_200),
        border_radius=8,
        bgcolor=ft.Colors.GREEN_50,
        margin=ft.margin.only(top=8),
    )

    def _save_forecast(e):
        """ARIMA予測結果をDBに保存する"""
        state = last_forecast_ref[0]
        if state is None:
            save_status_text.value = "保存するARIMA予測結果がありません。先に予測を実行してください。"
            save_status_text.color = ft.Colors.RED_700
            page.update()
            return

        fc_df = state["fc_df"]
        try:
            forecast_data = {
                "index": [str(i) for i in fc_df.index],
                "forecast": [float(v) for v in fc_df["forecast"]],
                "lower": [float(v) for v in fc_df["lower"]],
                "upper": [float(v) for v in fc_df["upper"]],
            }
            dataset_id = page.session.store.get("dataset_id")

            forecast_dict = {
                "indicator_code": state["indicator_code"],
                "dataset_id": int(dataset_id) if dataset_id else None,
                "frequency": page.session.store.get("frequency") or "",
                "arima_order": str(state["order"]),
                "forecast_steps": state["steps"],
                "forecast_data": forecast_data,
                "note": save_note_input.value or "",
            }
            fid = save_arima_forecast(forecast_dict)
            save_status_text.value = f"✓ 保存しました（forecast_id: {fid}）"
            save_status_text.color = ft.Colors.GREEN_700
        except Exception as ex:
            save_status_text.value = f"保存エラー: {ex}"
            save_status_text.color = ft.Colors.RED_700
        page.update()

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

            # ACF/PACF（nlags: 入力フィールドの値 or データ数の1/3を上限とした自動値）
            if nlags_input.value and nlags_input.value.strip().isdigit():
                nlags = min(int(nlags_input.value), len(y) - 1)
            else:
                nlags = min(20, max(5, len(y) // 3))
            acf_pacf = calc_acf_pacf(y, nlags=nlags)
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

            # 予測値テーブルを表示
            fc_rows = []
            for idx, row in fc.iterrows():
                fc_rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(idx)[:10])),
                    ft.DataCell(ft.Text(f"{row['forecast']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['lower']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['upper']:.4f}")),
                ]))
            results.append(ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("時点")),
                    ft.DataColumn(ft.Text("予測値")),
                    ft.DataColumn(ft.Text("下限（楽観参考）")),
                    ft.DataColumn(ft.Text("上限（悲観参考）")),
                ],
                rows=fc_rows,
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # 最後の予測状態を保存し、保存ボタンセクションを表示
            last_forecast_ref[0] = {
                "indicator_code": target_dropdown.value,
                "order": order,
                "steps": steps,
                "fc_df": fc,
            }
            save_status_text.value = ""
            save_section.visible = True

        except Exception as ex:
            results.append(ft.Text(f"予測エラー: {ex}", color=ft.Colors.ORANGE_700))

    # レイアウト
    _help = build_help_panel(
        title="⑥ ARIMA分析",
        purpose="単一の時系列変数に対してARIMA(p,d,q)モデルを学習し、将来値を予測します。ECLモデルで使う説明変数（GDP・失業率等）の将来シナリオ値をここで生成します。",
        steps=[
            "対象変数ドロップダウンで分析したい指標を選ぶ",
            "「ADF検定 + ACF/PACF」を押してADF検定結果とグラフを確認する",
            "ADF検定のp値 ≥ 0.05（単位根あり）なら d=1 を選択。p < 0.05 なら d=0",
            "ACFグラフの有意ラグ数 → q の候補、PACFグラフの有意ラグ数 → p の候補として設定",
            "【自動】max_p/max_d/max_qを指定して「自動選択実行」を押す（AIC最小モデルを選択）",
            "予測期間を入力して予測グラフを確認する（予測値が将来シナリオのベース値になる）",
        ],
        outputs=[
            "ADF検定結果（ADF統計量・p値・定常性判定）",
            "ACF/PACFグラフ（自己相関・偏自己相関、信頼区間付き）",
            "自動選択：上位10モデルテーブル（p・d・q・AIC・BIC・収束判定）",
            "将来予測グラフ（実績 + 予測値の時系列）",
        ],
        indicators=[
            {
                "name": "ADF検定（Augmented Dickey-Fuller）— 定常性の確認",
                "criteria": [
                    {"level": "良好",  "range": "p < 0.05",  "meaning": "定常（単位根なし）。d=0 で ARIMA を学習できる"},
                    {"level": "注意",  "range": "0.05 ≤ p < 0.1", "meaning": "境界領域。1回差分して再検定することを推奨"},
                    {"level": "危険",  "range": "p ≥ 0.1",   "meaning": "非定常（単位根あり）。d=1（1回差分）で再度 ADF 検定を実施する"},
                ],
                "note": "ほとんどのマクロ経済指標（GDP・物価指数・住宅価格等）は非定常（p ≥ 0.05）。1回差分後に定常になることが多い",
            },
            {
                "name": "ARIMA(p, d, q) — 各パラメータの意味",
                "criteria": [
                    {"level": "情報",  "range": "p（AR次数）",  "meaning": "自己回帰の次数。PACFグラフで有意なラグの数を目安にする"},
                    {"level": "情報",  "range": "d（差分次数）", "meaning": "定常化に必要な差分回数。ADF検定のp値 ≥ 0.05 なら d=1"},
                    {"level": "情報",  "range": "q（MA次数）",  "meaning": "移動平均の次数。ACFグラフで有意なラグの数を目安にする"},
                ],
                "note": "典型的なマクロ指標は ARIMA(1,1,0) や ARIMA(0,1,1) になることが多い。自動選択（AIC最小）を活用することを推奨",
            },
            {
                "name": "ACF / PACF グラフの読み方",
                "criteria": [
                    {"level": "情報",  "range": "青い点線（信頼区間）の外に出るラグ", "meaning": "統計的に有意な自己相関が存在するラグ"},
                    {"level": "情報",  "range": "ACFが徐々に減衰",  "meaning": "ARプロセスの特徴。p次数の候補はPACFのカットオフ点"},
                    {"level": "情報",  "range": "PACFが急にカットオフ", "meaning": "MA混じりの可能性。q次数の候補はACFのカットオフ点"},
                    {"level": "注意",  "range": "ACF・PACFともにゆっくり減衰", "meaning": "非定常の可能性。差分（d を増やす）を試す"},
                ],
                "note": "グラフ解釈が難しい場合は「自動選択実行」を使用し、AICが最小のモデルを採用することを推奨",
            },
        ],
    )
    return ft.Column(
        controls=[
            _help,
            ft.Text("ARIMA分析", size=24, weight=ft.FontWeight.BOLD),
            target_dropdown,
            ft.Row([
                nlags_input,
                ft.Text("空欄でデータ数に応じた自動設定（目安: データ数の1/3以下）", size=11, color=ft.Colors.GREY_600),
            ]),
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
            save_section,
        ],
        spacing=10,
        expand=True,
    )
