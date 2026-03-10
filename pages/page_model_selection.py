"""モデル選択ページ

説明変数の全組み合わせ探索によるモデル候補の評価・比較を行う。
"""
import flet as ft
import pandas as pd

from src.analysis.data_transform import TRANSFORM_METHODS
from src.analysis.model_selection import search_best_model, filter_models
from components.help_panel import build_help_panel
from components.data_source_selector import DataSourceSelector
from components.variable_selector import VariableSelector
from src.data.indicator_loader import (
    merge_target_and_indicators,
)


def model_selection_page(page: ft.Page) -> ft.Control:
    """モデル選択タブのUIを構築する"""
    print("DEBUG: モデル選択ページ構築開始")

    # データ参照用
    ind_df_ref = [None]
    tgt_df_ref = [None]
    code_to_name_ref = [{}]

    # 変数セレクタ（DataSourceSelector変更時に再構築）
    selector_container = ft.Column()
    selector_ref = [None]

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
        selector_container.controls = [selector_ref[0].get_ui(height=180)]
        page.update()

    data_source = DataSourceSelector(page=page, on_data_loaded=on_data_loaded)

    n_features_input = ft.TextField(
        label="組み合わせ変数数",
        hint_text="例: 2",
        value="2",
        width=140,
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    transform_dropdown_ui = ft.Dropdown(
        label="データ変換",
        options=[ft.dropdown.Option(key=k, text=v) for k, v in TRANSFORM_METHODS.items()],
        value="none", width=250,
    )
    standardize_switch = ft.Switch(label="標準化", value=True)
    lag_slider = ft.Slider(min=0, max=12, divisions=12, label="ラグ: {value}", value=0, width=250)
    sort_dropdown = ft.Dropdown(
        label="ソート基準",
        options=[
            ft.dropdown.Option(key="aic", text="AIC昇順"),
            ft.dropdown.Option(key="bic", text="BIC昇順"),
            ft.dropdown.Option(key="adj_r2", text="Adj.R²降順"),
        ],
        value="aic", width=200,
    )

    # 全結果を保持（VIFフィルタのトグル切り替え時に再フィルタリングするため）
    all_results_ref = [None]
    last_target_ref = [""]

    vif_filter_switch = ft.Switch(label="VIF≤10のみ表示", value=False)
    progress_bar = ft.ProgressBar(visible=False)
    progress_text = ft.Text("", size=11)
    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)

    def on_vif_toggle(e):
        """VIFフィルタのトグル切り替え時に即時再表示する"""
        if all_results_ref[0] is None:
            return
        results_df = all_results_ref[0]
        target = last_target_ref[0]
        if vif_filter_switch.value:
            display_df = filter_models(results_df, max_vif=10.0, min_dw=None, max_dw=None)
        else:
            display_df = results_df
        _show_results(target, display_df, len(results_df))
        page.update()

    vif_filter_switch.on_change = on_vif_toggle

    def run_analysis(e):
        """分析実行"""
        selector = selector_ref[0]
        if selector is None:
            result_container.controls = [ft.Text("データソースを選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        target = selector.get_target()
        if not target:
            result_container.controls = [ft.Text("目的変数を選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        df = ind_df_ref[0]
        target_df = tgt_df_ref[0]

        if df is None or df.empty:
            result_container.controls = [ft.Text("説明変数データがありません。", color=ft.Colors.RED_700)]
            page.update()
            return

        feature_cols = selector.get_selected_features()
        if not feature_cols:
            result_container.controls = [ft.Text("説明変数候補を1つ以上チェックしてください。", color=ft.Colors.RED_700)]
            page.update()
            return

        n_feat = int(n_features_input.value)
        if n_feat > len(feature_cols):
            result_container.controls = [ft.Text(f"組み合わせ変数数({n_feat})が候補数({len(feature_cols)})を超えています。", color=ft.Colors.RED_700)]
            page.update()
            return

        print(f"DEBUG: モデル選択実行 target={target}, features={len(feature_cols)}候補, n={n_feat}")
        progress_bar.visible = True
        progress_bar.value = 0
        result_container.controls = [ft.Text("分析中...")]
        page.update()

        def progress_callback(current, total):
            progress_bar.value = current / total
            progress_text.value = f"探索中: {current}/{total}"
            page.update()

        try:
            # 目的変数が別ソース（target_data）の場合はマージ
            if target_df is not None and not target_df.empty and target in target_df.columns:
                analysis_df = merge_target_and_indicators(target_df, df[feature_cols], target)
            else:
                analysis_df = df

            results_df = search_best_model(
                df=analysis_df,
                target_col=target,
                feature_cols=feature_cols,
                n_features=n_feat,
                transform_method=transform_dropdown_ui.value,
                do_standardize=standardize_switch.value,
                lag=int(lag_slider.value),
                sort_by=sort_dropdown.value,
                progress_callback=progress_callback,
            )

            # 全結果を保持（トグル切り替え時の再フィルタリング用）
            all_results_ref[0] = results_df
            last_target_ref[0] = target

            # VIFフィルタ（min_dw/max_dwはNoneにしてVIFのみで絞り込む）
            display_df = results_df
            if vif_filter_switch.value:
                display_df = filter_models(results_df, max_vif=10.0, min_dw=None, max_dw=None)

            progress_bar.visible = False
            progress_text.value = ""
            _show_results(target, display_df, len(results_df))
            print(f"DEBUG: モデル選択完了 {len(results_df)}モデル")

        except Exception as ex:
            print(f"DEBUG: モデル選択エラー: {ex}")
            progress_bar.visible = False
            progress_text.value = ""
            result_container.controls = [ft.Text(f"分析エラー: {ex}", color=ft.Colors.RED_700)]

        page.update()

    def _show_results(target: str, results_df: pd.DataFrame, total_count: int):
        """結果テーブルを表示する"""
        result_container.controls.clear()

        c2n = code_to_name_ref[0]
        target_name = c2n.get(target, target)
        result_container.controls.append(ft.Text("モデル候補の評価結果", size=18, weight=ft.FontWeight.BOLD))
        result_container.controls.append(ft.Text(f"目的変数: {target_name} | 表示: {len(results_df)}/{total_count}件"))

        if results_df.empty:
            result_container.controls.append(ft.Text("条件に合うモデルがありません。", italic=True))
            return

        col_labels = {
            "features": "説明変数",
            "r2": "R²",
            "adj_r2": "Adj.R²",
            "aic": "AIC",
            "bic": "BIC",
            "dw": "DW",
            "f_stat": "F統計量",
            "f_pvalue": "F p値",
            "max_vif": "最大VIF",
            "nobs": "観測数",
        }
        display_cols = list(col_labels.keys())

        def _make_cell(row, c):
            """セルの内容と色を決定する"""
            val = row[c]
            if c == "features":
                # 変数名を日本語＋改行表示
                if isinstance(val, list):
                    text = "\n".join(c2n.get(v, v) for v in val)
                else:
                    text = "\n".join(c2n.get(v.strip(), v.strip()) for v in str(val).strip("[]").split(","))
                return ft.DataCell(ft.Text(text, size=10))
            if c == "max_vif" and isinstance(val, float):
                color = ft.Colors.RED_700 if val > 10 else ft.Colors.GREEN_700
                return ft.DataCell(ft.Text(f"{val:.2f}", size=10, color=color))
            if c == "adj_r2" and isinstance(val, float):
                color = ft.Colors.GREEN_700 if val >= 0.7 else (ft.Colors.ORANGE_700 if val >= 0.4 else ft.Colors.RED_700)
                return ft.DataCell(ft.Text(f"{val:.4f}", size=10, color=color))
            if c == "f_pvalue" and isinstance(val, float):
                color = ft.Colors.GREEN_700 if val < 0.05 else ft.Colors.RED_700
                return ft.DataCell(ft.Text(f"{val:.4e}", size=10, color=color))
            if isinstance(val, float):
                return ft.DataCell(ft.Text(f"{val:.4f}", size=10))
            return ft.DataCell(ft.Text(str(val), size=10))

        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(col_labels[c], size=11)) for c in display_cols],
            rows=[
                ft.DataRow(cells=[_make_cell(row, c) for c in display_cols])
                for _, row in results_df.head(50).iterrows()
            ],
            border=ft.border.all(1, ft.Colors.GREY_300),
            column_spacing=10,
        )

        result_container.controls.append(
            ft.Container(
                content=ft.Row([table], scroll=ft.ScrollMode.AUTO),
            )
        )

    # レイアウト
    _help = build_help_panel(
        title="④ モデル選択（組み合わせ探索）",
        purpose="説明変数の全組み合わせを自動探索し、AIC・BIC・Adj.R²で最適なモデルを比較します。「VIF < 10 かつ Adj.R² 最大」のモデルが最良候補です。",
        steps=[
            "データソース選択で説明変数・目的変数のデータセットとfrequencyを選ぶ（frequencyを揃える）",
            "変数セレクタで目的変数を選択し、探索候補にしたい説明変数をチェックする（5〜10個程度推奨）",
            "「組み合わせ変数数」で1モデルに含める変数の数を指定する（例：2〜3）",
            "データ変換・標準化・ラグ・ソート基準・VIFフィルタを設定する",
            "「組み合わせ探索実行」を押す",
            "結果テーブルでAIC/BICが最小かつVIF < 10のモデルを選択し、③回帰分析で詳細確認する",
        ],
        outputs=[
            "モデル候補テーブル（説明変数・R²・Adj.R²・AIC・BIC・DW・最大VIF、最大50件）",
            "Adj.R²: 緑≥0.7 / 橙≥0.4 / 赤<0.4、最大VIF: 緑≤10 / 赤>10、F p値: 緑<0.05 / 赤≥0.05",
            "表示件数（X/Y件）。VIFトグルで即時フィルタリング可能",
        ],
        indicators=[
            {
                "name": "モデル選択の総合判断フロー",
                "criteria": [
                    {"level": "良好",  "range": "Step 1: max_VIF < 10",       "meaning": "多重共線性がないモデルのみを候補とする（赤色行を除外）"},
                    {"level": "良好",  "range": "Step 2: Adj.R² が高い順",     "meaning": "VIFフィルタ後の候補からAdj.R²が最大のものを選ぶ"},
                    {"level": "良好",  "range": "Step 3: AIC/BICで最終選択",   "meaning": "Adj.R²が近い複数モデルはAIC/BICが小さい方を選ぶ"},
                    {"level": "注意",  "range": "DW を確認",                   "meaning": "DWが1.5〜2.5の範囲外のモデルは残差に問題がある可能性"},
                ],
                "note": "変数が多すぎると組み合わせ数が爆発的に増加（8変数の3択＝56通り）。候補変数は相関分析で絞り込んでから探索することを推奨",
            },
            {
                "name": "AIC / BIC（情報量基準）",
                "criteria": [
                    {"level": "情報",  "range": "値が小さいほど良い",           "meaning": "同一データ内での相対比較用。絶対値に意味はない"},
                    {"level": "注意",  "range": "ΔAIC > 2（上位モデルとの差）", "meaning": "2以上差があるモデルは明確に劣る。10以上は論外"},
                    {"level": "情報",  "range": "BICはAICより厳しい",           "meaning": "BICはサンプル数が多いほど変数へのペナルティが大きい"},
                ],
                "note": "AICとBICの選択が割れた場合は、ECLモデルの予測安定性を重視してBICが小さい（よりシンプルな）モデルを選ぶことを推奨",
            },
        ],
    )
    return ft.Column(
        controls=[
            _help,
            ft.Text("モデル選択（組み合わせ探索）", size=24, weight=ft.FontWeight.BOLD),
            data_source.get_ui(),
            selector_container,
            ft.Row([n_features_input, transform_dropdown_ui, standardize_switch]),
            ft.Row([lag_slider, sort_dropdown, vif_filter_switch]),
            progress_bar,
            progress_text,
            ft.ElevatedButton("組み合わせ探索実行", on_click=run_analysis, icon=ft.Icons.SEARCH),
            ft.Divider(),
            result_container,
        ],
        spacing=10,
        expand=True,
    )
