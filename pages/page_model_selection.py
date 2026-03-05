"""モデル選択ページ

説明変数の全組み合わせ探索によるモデル候補の評価・比較を行う。
"""
import flet as ft
import pandas as pd

from src.analysis.data_transform import TRANSFORM_METHODS
from src.analysis.model_selection import search_best_model, filter_models
from components.help_panel import build_help_panel


def model_selection_page(page: ft.Page) -> ft.Control:
    """モデル選択タブのUIを構築する"""
    print("DEBUG: モデル選択ページ構築開始")

    df: pd.DataFrame | None = page.session.store.get("df")
    if df is None or df.empty:
        return ft.Text("先にデータ閲覧タブでデータを読み込んでください。", color=ft.Colors.RED_700)

    columns = df.columns.tolist()

    # UI部品
    target_dropdown = ft.Dropdown(
        label="目的変数",
        options=[ft.dropdown.Option(c) for c in columns],
        value=columns[0] if columns else None,
        width=300,
    )

    feature_checkboxes = ft.Column(spacing=2)
    for col in columns:
        feature_checkboxes.controls.append(ft.Checkbox(label=col, value=True))

    n_features_input = ft.TextField(
        label="説明変数の数", value="2", width=120,
        keyboard_type=ft.KeyboardType.NUMBER,
    )
    transform_dropdown = ft.Dropdown(
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
    vif_filter_switch = ft.Switch(label="VIF≤10のみ表示", value=False)
    progress_bar = ft.ProgressBar(visible=False)
    progress_text = ft.Text("", size=11)
    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)

    def run_analysis(e):
        """分析実行"""
        target = target_dropdown.value
        if not target:
            result_container.controls = [ft.Text("目的変数を選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        # 選択された説明変数候補
        feature_cols = [
            cb.label for cb in feature_checkboxes.controls
            if isinstance(cb, ft.Checkbox) and cb.value and cb.label != target
        ]
        n_feat = int(n_features_input.value)

        if n_feat > len(feature_cols):
            result_container.controls = [ft.Text(f"説明変数の数({n_feat})が候補数({len(feature_cols)})を超えています。", color=ft.Colors.RED_700)]
            page.update()
            return

        print(f"DEBUG: モデル選択実行 target={target}, features={len(feature_cols)}候補, n={n_feat}")
        progress_bar.visible = True
        progress_bar.value = 0
        result_container.controls = [ft.Text("分析中...")]
        page.update()

        def progress_callback(current, total):
            progress_bar.value = current / total
            progress_text.value = f"{current}/{total}"
            page.update()

        try:
            results_df = search_best_model(
                df=df,
                target_col=target,
                feature_cols=feature_cols,
                n_features=n_feat,
                transform_method=transform_dropdown.value,
                do_standardize=standardize_switch.value,
                lag=int(lag_slider.value),
                sort_by=sort_dropdown.value,
                progress_callback=progress_callback,
            )

            # VIFフィルタ
            display_df = results_df
            if vif_filter_switch.value:
                display_df = filter_models(results_df, max_vif=10.0)

            progress_bar.visible = False
            _show_results(target, display_df, len(results_df))
            print(f"DEBUG: モデル選択完了 {len(results_df)}モデル")

        except Exception as ex:
            print(f"DEBUG: モデル選択エラー: {ex}")
            progress_bar.visible = False
            result_container.controls = [ft.Text(f"分析エラー: {ex}", color=ft.Colors.RED_700)]

        page.update()

    def _show_results(target: str, results_df: pd.DataFrame, total_count: int):
        """結果テーブルを表示する"""
        result_container.controls.clear()

        result_container.controls.append(ft.Text("モデル候補の評価結果", size=18, weight=ft.FontWeight.BOLD))
        result_container.controls.append(ft.Text(f"目的変数: {target} | 表示: {len(results_df)}/{total_count}件"))

        if results_df.empty:
            result_container.controls.append(ft.Text("条件に合うモデルがありません。", italic=True))
            return

        # DataTable
        display_cols = ["features", "r2", "adj_r2", "aic", "bic", "dw", "f_stat", "f_pvalue", "max_vif", "nobs"]
        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(c, size=11)) for c in display_cols],
            rows=[
                ft.DataRow(cells=[
                    ft.DataCell(ft.Text(
                        f"{row[c]:.4f}" if isinstance(row[c], float) else str(row[c]),
                        size=10,
                        color=ft.Colors.RED_700 if c == "max_vif" and isinstance(row[c], float) and row[c] > 10 else None,
                    ))
                    for c in display_cols
                ])
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
        purpose="説明変数の全組み合わせを自動探索し、AIC・BIC・Adj.R²で最適なモデルを比較します。",
        steps=[
            "目的変数ドロップダウンで目的変数を選択する",
            "「説明変数候補」チェックボックスで探索対象の変数を選ぶ",
            "「説明変数の個数」で最終モデルに含める変数数を指定する（例：2）",
            "データ変換・標準化・ラグ・ソート基準・VIFフィルタを設定する",
            "「組み合わせ探索実行」を押す",
        ],
        outputs=[
            "モデル候補テーブル（features・R²・Adj.R²・AIC・BIC・DW・max_VIF、最大50件）",
            "max_VIF > 10 のモデルは赤色でハイライト",
            "表示件数（X/Y件）",
        ],
    )
    return ft.Column(
        controls=[
            _help,
            ft.Text("モデル選択（組み合わせ探索）", size=24, weight=ft.FontWeight.BOLD),
            target_dropdown,
            ft.Text("説明変数候補:", size=14, weight=ft.FontWeight.BOLD),
            ft.Container(content=feature_checkboxes, height=150, border=ft.border.all(1, ft.Colors.GREY_300), border_radius=5, padding=8),
            ft.Row([n_features_input, transform_dropdown, standardize_switch]),
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
