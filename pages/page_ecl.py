"""ECL計算ページ

確定済み回帰モデル + ARIMA予測を組み合わせ、3シナリオでECLを算出する。
"""
import csv
import io
import json

import flet as ft
import pandas as pd

from components.help_panel import build_help_panel
from components.plot_utils import fig_to_base64
from src.analysis.ecl import apply_model_to_forecast, calc_weighted_ecl
from src.db_operations import (
    load_model_configs,
    load_model_result,
    load_arima_forecasts,
    load_arima_forecast_data,
    save_ecl_result,
)

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use("Agg")
    _MPL_OK = True
except ImportError:
    _MPL_OK = False


def ecl_page(page: ft.Page) -> ft.Control:
    """ECL計算タブのUIを構築する"""
    print("DEBUG: ECL計算ページ構築開始")

    # ── Step1: モデル選択 ──────────────────────────────
    model_dd = ft.Dropdown(label="保存済みモデル（config_id）", width=500)
    model_info_text = ft.Text("", size=11, color=ft.Colors.GREY_700)
    feature_assign_container = ft.Column()  # 変数ごとのARIMA予測割り当て

    current_model_ref = [None]   # load_model_result() の結果を保持
    arima_dd_refs = {}           # {feature_code: Dropdown} の辞書

    # ── Step2: シナリオウェイト ────────────────────────
    w_base_input = ft.TextField(label="ベース ウェイト", value="0.6", width=120,
                                 keyboard_type=ft.KeyboardType.NUMBER)
    w_up_input = ft.TextField(label="楽観 ウェイト", value="0.2", width=120,
                               keyboard_type=ft.KeyboardType.NUMBER)
    w_down_input = ft.TextField(label="悲観 ウェイト", value="0.2", width=120,
                                 keyboard_type=ft.KeyboardType.NUMBER)
    weight_status = ft.Text("", size=11)

    def check_weights(e=None):
        try:
            total = float(w_base_input.value) + float(w_up_input.value) + float(w_down_input.value)
            if abs(total - 1.0) < 0.001:
                weight_status.value = "✓ ウェイト合計 = 1.0"
                weight_status.color = ft.Colors.GREEN_700
            else:
                weight_status.value = f"⚠ ウェイト合計 = {total:.3f}（1.0 になるよう調整してください）"
                weight_status.color = ft.Colors.ORANGE_700
        except ValueError:
            weight_status.value = "数値を入力してください"
            weight_status.color = ft.Colors.RED_700
        page.update()

    w_base_input.on_change = check_weights
    w_up_input.on_change = check_weights
    w_down_input.on_change = check_weights

    # ── Step3: LGD・EAD ───────────────────────────────
    lgd_input = ft.TextField(label="LGD（固定値）", value="0.45", width=150,
                              hint_text="例: 0.45 = 45%",
                              keyboard_type=ft.KeyboardType.NUMBER)
    ead_input = ft.TextField(label="EAD（億円、空欄=ECL率のみ）", width=200,
                              hint_text="例: 1000",
                              keyboard_type=ft.KeyboardType.NUMBER)

    # ── 結果表示 ──────────────────────────────────────
    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)
    save_status_text = ft.Text("", size=12)
    last_ecl_ref = [None]   # 計算結果を保持

    def _load_models(e=None):
        """保存済みモデルをDBから読み込んでドロップダウンに設定する"""
        try:
            configs = load_model_configs()
            if configs.empty:
                model_dd.options = []
                model_info_text.value = "保存済みモデルがありません。⑦モデル確定タブで保存してください。"
            else:
                model_dd.options = [
                    ft.dropdown.Option(
                        key=str(row["config_id"]),
                        text=f"ID:{row['config_id']} - {row['model_name']} ({row['target_variable']})",
                    )
                    for _, row in configs.iterrows()
                ]
                if not model_dd.value and model_dd.options:
                    model_dd.value = model_dd.options[0].key
                    _on_model_select(None)
        except Exception as ex:
            model_info_text.value = f"モデル取得エラー: {ex}"
        page.update()

    def _on_model_select(e):
        """モデル選択時に変数情報を表示し、ARIMA予測割り当てUIを構築する"""
        if not model_dd.value:
            return
        try:
            config_id = int(model_dd.value)
            result = load_model_result(config_id)
            if result is None:
                model_info_text.value = f"config_id={config_id} の結果が見つかりません"
                page.update()
                return

            current_model_ref[0] = result

            features = result.get("feature_variables") or []
            if isinstance(features, str):
                try:
                    features = json.loads(features)
                except Exception:
                    features = []

            metrics = result.get("metrics") or {}
            freq = result.get("frequency", "")
            model_info_text.value = (
                f"目的変数: {result['target_variable']}  |  "
                f"frequency: {freq}  |  "
                f"説明変数: {', '.join(features)}  |  "
                f"Adj.R²: {metrics.get('adj_r2', 'N/A')}"
            )

            # ARIMA予測割り当てUIを構築
            arima_dd_refs.clear()
            controls = [ft.Text("説明変数ごとのARIMA予測を選択", size=14, weight=ft.FontWeight.BOLD)]
            for feat in features:
                try:
                    fc_list = load_arima_forecasts(indicator_code=feat)
                except Exception:
                    fc_list = pd.DataFrame()

                if fc_list.empty:
                    dd_options = [ft.dropdown.Option(key="none", text="保存済み予測なし")]
                    dd_value = "none"
                else:
                    dd_options = [
                        ft.dropdown.Option(
                            key=str(r["forecast_id"]),
                            text=f"ID:{r['forecast_id']} ARIMA{r['arima_order']} {r['forecast_steps']}期 {str(r['created_at'])[:10]}",
                        )
                        for _, r in fc_list.iterrows()
                    ]
                    dd_value = str(fc_list.iloc[0]["forecast_id"])

                dd = ft.Dropdown(
                    label=feat,
                    options=dd_options,
                    value=dd_value,
                    width=480,
                )
                arima_dd_refs[feat] = dd
                controls.append(dd)

            feature_assign_container.controls = controls
            page.update()

        except Exception as ex:
            print(f"DEBUG: モデル選択エラー: {ex}")
            model_info_text.value = f"エラー: {ex}"
            page.update()

    model_dd.on_change = _on_model_select

    def run_ecl(e):
        """ECLを計算して結果を表示する"""
        model_data = current_model_ref[0]
        if model_data is None:
            result_container.controls = [ft.Text("モデルを選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        result_container.controls = [ft.ProgressRing()]
        page.update()

        try:
            features = model_data.get("feature_variables") or []
            if isinstance(features, str):
                try:
                    features = json.loads(features)
                except Exception:
                    features = []

            hyperparams = model_data.get("hyperparameters") or {}
            if isinstance(hyperparams, str):
                try:
                    hyperparams = json.loads(hyperparams)
                except Exception:
                    hyperparams = {}

            coefficients = model_data.get("coefficients") or {}
            if isinstance(coefficients, str):
                try:
                    coefficients = json.loads(coefficients)
                except Exception:
                    coefficients = {}

            # ARIMA予測を読み込む
            fc_by_var = {}
            for feat in features:
                dd = arima_dd_refs.get(feat)
                if dd is None or dd.value == "none":
                    result_container.controls = [
                        ft.Text(f"変数「{feat}」のARIMA予測が選択されていません。", color=ft.Colors.RED_700)
                    ]
                    page.update()
                    return
                fc_df = load_arima_forecast_data(int(dd.value))
                if fc_df.empty:
                    result_container.controls = [
                        ft.Text(f"変数「{feat}」の予測データが空です。", color=ft.Colors.RED_700)
                    ]
                    page.update()
                    return
                fc_by_var[feat] = fc_df

            # 各シナリオのDataFrameを組み立てる
            # base: forecast列 / upside: lower列 / downside: upper列
            def _build_scenario_df(col: str) -> pd.DataFrame:
                frames = {}
                for var, fc_df in fc_by_var.items():
                    frames[var] = fc_df[col] if col in fc_df.columns else fc_df["forecast"]
                return pd.DataFrame(frames)

            base_df = _build_scenario_df("forecast")
            upside_df = _build_scenario_df("lower")
            downside_df = _build_scenario_df("upper")

            # 変換・標準化設定
            transform_method = hyperparams.get("transform", "none")
            feature_stats = hyperparams.get("feature_stats") or {}

            # 各シナリオのPD予測値を計算
            base_pd = apply_model_to_forecast(
                coefficients, base_df, feature_stats, transform_method
            )
            upside_pd = apply_model_to_forecast(
                coefficients, upside_df, feature_stats, transform_method
            )
            downside_pd = apply_model_to_forecast(
                coefficients, downside_df, feature_stats, transform_method
            )

            if base_pd.empty:
                result_container.controls = [ft.Text("予測値の計算結果が空です。係数と予測データを確認してください。", color=ft.Colors.RED_700)]
                page.update()
                return

            # ウェイトとLGD
            w_base = float(w_base_input.value)
            w_up = float(w_up_input.value)
            w_down = float(w_down_input.value)
            lgd = float(lgd_input.value)
            ead = float(ead_input.value) if ead_input.value.strip() else None

            ecl = calc_weighted_ecl(
                base_pd=base_pd,
                upside_pd=upside_pd,
                downside_pd=downside_pd,
                lgd=lgd,
                weight_base=w_base,
                weight_upside=w_up,
                weight_downside=w_down,
                ead=ead,
            )

            # 結果テーブルを作成
            result_rows = []
            for idx in ecl["pd_weighted"].index:
                row_data = {
                    "period": str(idx)[:10],
                    "pd_base": float(ecl["pd_base"].get(idx, float("nan"))),
                    "pd_upside": float(ecl["pd_upside"].get(idx, float("nan"))),
                    "pd_downside": float(ecl["pd_downside"].get(idx, float("nan"))),
                    "pd_weighted": float(ecl["pd_weighted"].get(idx, float("nan"))),
                    "lgd": lgd,
                    "ecl_rate": float(ecl["ecl_rate"].get(idx, float("nan"))),
                }
                if ead is not None:
                    row_data["ecl_amount"] = float(ecl["ecl_amount"].get(idx, float("nan")))
                result_rows.append(row_data)

            last_ecl_ref[0] = {
                "model_config_id": int(model_dd.value),
                "target_code": model_data["target_variable"],
                "weight_base": w_base,
                "weight_upside": w_up,
                "weight_downside": w_down,
                "lgd": lgd,
                "ead": ead,
                "results": result_rows,
            }

            # 表示用コントロール
            controls = [ft.Text("ECL計算結果", size=18, weight=ft.FontWeight.BOLD)]

            # グラフ
            if _MPL_OK:
                img = _plot_ecl(ecl, model_data["target_variable"])
                if img:
                    controls.append(ft.Image(src="data:image/png;base64," + img, fit=ft.BoxFit.CONTAIN))

            # 結果テーブル
            has_amount = ead is not None
            col_headers = ["時点", "PD(ベース)", "PD(楽観)", "PD(悲観)", "PD加重", "LGD", "ECL率"]
            if has_amount:
                col_headers.append("ECL金額(億円)")

            data_rows = []
            for r in result_rows:
                cells = [
                    ft.DataCell(ft.Text(r["period"])),
                    ft.DataCell(ft.Text(f"{r['pd_base']:.4f}")),
                    ft.DataCell(ft.Text(f"{r['pd_upside']:.4f}")),
                    ft.DataCell(ft.Text(f"{r['pd_downside']:.4f}")),
                    ft.DataCell(ft.Text(f"{r['pd_weighted']:.4f}", weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(f"{r['lgd']:.2%}")),
                    ft.DataCell(ft.Text(f"{r['ecl_rate']:.4%}", weight=ft.FontWeight.BOLD,
                                        color=ft.Colors.BLUE_700)),
                ]
                if has_amount:
                    cells.append(ft.DataCell(ft.Text(f"{r['ecl_amount']:.2f}")))
                data_rows.append(ft.DataRow(cells=cells))

            controls.append(ft.DataTable(
                columns=[ft.DataColumn(ft.Text(h, size=11)) for h in col_headers],
                rows=data_rows,
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # シナリオ設定の要約
            controls.append(ft.Text(
                f"ウェイト: ベース {w_base:.0%} / 楽観 {w_up:.0%} / 悲観 {w_down:.0%}  |  "
                f"LGD: {lgd:.2%}  |  EAD: {'なし（ECL率のみ）' if ead is None else f'{ead:.0f}億円'}",
                size=11, color=ft.Colors.GREY_700,
            ))

            result_container.controls = controls
            save_status_text.value = "計算完了。「DBに保存」または「CSVエクスポート」を押してください。"
            save_status_text.color = ft.Colors.BLUE_700

        except Exception as ex:
            print(f"DEBUG: ECL計算エラー: {ex}")
            import traceback
            traceback.print_exc()
            result_container.controls = [ft.Text(f"計算エラー: {ex}", color=ft.Colors.RED_700)]

        page.update()

    def _plot_ecl(ecl: dict, target_label: str) -> str | None:
        """ECLシナリオ別グラフを作成してbase64文字列を返す"""
        try:
            fig, ax = plt.subplots(figsize=(10, 4))
            idx = ecl["pd_weighted"].index
            ax.plot(idx, ecl["pd_base"], label="ベース", color="steelblue", linewidth=1.5)
            ax.plot(idx, ecl["pd_upside"], label="楽観", color="green", linewidth=1.2, linestyle="--")
            ax.plot(idx, ecl["pd_downside"], label="悲観", color="red", linewidth=1.2, linestyle="--")
            ax.plot(idx, ecl["pd_weighted"], label="加重平均", color="black", linewidth=2.0)
            ax.set_title(f"{target_label} シナリオ別PD予測")
            ax.set_ylabel("PD")
            ax.legend(fontsize=9)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            img = fig_to_base64(fig)
            plt.close(fig)
            return img
        except Exception as ex:
            print(f"DEBUG: ECLグラフ作成エラー: {ex}")
            return None

    def save_to_db(e):
        """ECL計算結果をDBに保存する"""
        ecl_state = last_ecl_ref[0]
        if ecl_state is None:
            save_status_text.value = "先にECLを計算してください。"
            save_status_text.color = ft.Colors.RED_700
            page.update()
            return
        try:
            ecl_id = save_ecl_result(ecl_state)
            save_status_text.value = f"✓ DBに保存しました（ecl_id: {ecl_id}）"
            save_status_text.color = ft.Colors.GREEN_700
        except Exception as ex:
            save_status_text.value = f"保存エラー: {ex}"
            save_status_text.color = ft.Colors.RED_700
        page.update()

    def export_csv(e):
        """ECL計算結果をCSVエクスポートする（クリップボードに出力）"""
        ecl_state = last_ecl_ref[0]
        if ecl_state is None:
            save_status_text.value = "先にECLを計算してください。"
            save_status_text.color = ft.Colors.RED_700
            page.update()
            return
        try:
            rows = ecl_state["results"]
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
            csv_str = buf.getvalue()
            page.set_clipboard(csv_str)
            save_status_text.value = "✓ CSVをクリップボードにコピーしました。テキストエディタ・Excelに貼り付けてください。"
            save_status_text.color = ft.Colors.GREEN_700
        except Exception as ex:
            save_status_text.value = f"CSVエクスポートエラー: {ex}"
            save_status_text.color = ft.Colors.RED_700
        page.update()

    # 初期ロード
    _load_models()

    _help = build_help_panel(
        title="⑧ ECL計算",
        purpose="確定済み回帰モデル（⑦で保存）と ARIMA予測（⑥で保存）を組み合わせ、3シナリオ加重平均でECL（予想信用損失）率・金額を算出します。",
        steps=[
            "「モデル一覧をロード」を押して保存済みモデルを読み込む",
            "ドロップダウンから使用する回帰モデルを選択する",
            "各説明変数に対応するARIMA予測をドロップダウンで選択する",
            "シナリオウェイト（ベース/楽観/悲観）を設定する（合計=1.0）",
            "LGD固定値を入力する（例: 0.45 = 45%）",
            "EAD（残高）を入力する（任意。空欄=ECL率のみ計算）",
            "「ECLを計算する」を押す",
            "結果を確認し「DBに保存」または「CSVエクスポート」する",
        ],
        outputs=[
            "シナリオ別PD推移グラフ（ベース/楽観/悲観/加重平均）",
            "ECL結果テーブル（期間別 PD・LGD・ECL率・ECL金額）",
        ],
        indicators=[
            {
                "name": "シナリオとARIMA出力の対応（デフォルト）",
                "criteria": [
                    {"level": "情報",  "range": "ベースシナリオ → forecast（点予測）",  "meaning": "最も可能性が高い予測値をベースに使用"},
                    {"level": "情報",  "range": "楽観シナリオ → lower（95%信頼区間下限）", "meaning": "失業率など「低いほど楽観」の変数に適切"},
                    {"level": "注意",  "range": "悲観シナリオ → upper（95%信頼区間上限）", "meaning": "GDP成長率など「高いほど楽観」の変数は対応が逆になることに注意"},
                ],
                "note": "変数によってlower/upperのシナリオ対応方向が異なる場合は、手動でARIMA予測を調整してください",
            },
            {
                "name": "シナリオウェイトの設定指針",
                "criteria": [
                    {"level": "情報",  "range": "ベース: 50〜70%",  "meaning": "市場コンセンサス・日銀展望レポート等のベースラインに準拠"},
                    {"level": "情報",  "range": "楽観: 10〜25%",    "meaning": "設備投資増・輸出回復等、景気回復が早まる場合"},
                    {"level": "情報",  "range": "悲観: 15〜30%",    "meaning": "海外景気後退・金融市場混乱・自然災害等のテールリスク"},
                ],
                "note": "IFRS9の要求: ウェイトの設定根拠を文書化し、毎期末に見直すことが求められる",
            },
        ],
    )

    return ft.Column(
        controls=[
            _help,
            ft.Text("ECL計算", size=24, weight=ft.FontWeight.BOLD),

            # Step 1: モデル選択
            ft.Container(
                content=ft.Column([
                    ft.Text("Step 1: 回帰モデルの選択", size=16, weight=ft.FontWeight.BOLD),
                    ft.Row([
                        model_dd,
                        ft.ElevatedButton("モデル一覧をロード", icon=ft.Icons.REFRESH,
                                          on_click=_load_models),
                    ]),
                    model_info_text,
                ]),
                padding=10, border=ft.border.all(1, ft.Colors.BLUE_100),
                border_radius=8, bgcolor=ft.Colors.BLUE_50,
            ),

            # Step 2: ARIMA予測割り当て
            ft.Container(
                content=ft.Column([
                    ft.Text("Step 2: 説明変数ごとのARIMA予測割り当て", size=16, weight=ft.FontWeight.BOLD),
                    feature_assign_container,
                ]),
                padding=10, border=ft.border.all(1, ft.Colors.PURPLE_100),
                border_radius=8, bgcolor=ft.Colors.PURPLE_50,
            ),

            # Step 3: シナリオウェイト・LGD・EAD
            ft.Container(
                content=ft.Column([
                    ft.Text("Step 3: シナリオウェイト・LGD・EAD", size=16, weight=ft.FontWeight.BOLD),
                    ft.Row([w_base_input, w_up_input, w_down_input, weight_status]),
                    ft.Row([lgd_input, ead_input]),
                    ft.Text("LGD: モデルがない場合は固定値を使用。EAD は任意（空欄=ECL率のみ）",
                            size=11, color=ft.Colors.GREY_600),
                ]),
                padding=10, border=ft.border.all(1, ft.Colors.GREEN_100),
                border_radius=8, bgcolor=ft.Colors.GREEN_50,
            ),

            ft.ElevatedButton("ECLを計算する", on_click=run_ecl, icon=ft.Icons.CALCULATE),
            ft.Divider(),
            result_container,
            ft.Row([
                ft.ElevatedButton("DBに保存", icon=ft.Icons.SAVE, on_click=save_to_db),
                ft.ElevatedButton("CSVエクスポート（クリップボード）",
                                   icon=ft.Icons.COPY, on_click=export_csv),
                save_status_text,
            ]),
        ],
        spacing=10,
        expand=True,
    )
