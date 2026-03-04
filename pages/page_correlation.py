"""相関分析ページ

相関行列ヒートマップ・VIF一覧テーブル・VIFクロス表の表示を行う。
"""
import flet as ft
import pandas as pd

from components.variable_selector import VariableSelector
from components.plot_utils import plot_correlation_heatmap, plot_vif_heatmap
from src.analysis.data_transform import transform, standardize
from src.analysis.correlation import (
    calc_correlation_matrix,
    calc_vif,
    calc_vif_cross_table,
)


def correlation_page(page: ft.Page) -> ft.Control:
    """相関分析タブのUIを構築する"""
    print("DEBUG: 相関分析ページ構築開始")

    # 共有データを取得
    df: pd.DataFrame | None = page.session.store.get("df")
    if df is None or df.empty:
        return ft.Text("先にデータ閲覧タブでデータを読み込んでください。", color=ft.Colors.RED_700)

    # 変数セレクタ
    selector = VariableSelector(
        page=page,
        columns=df.columns.tolist(),
        show_target=True,
        show_transform=False,
    )

    # 変換ドロップダウン（全カラム一括）
    from src.analysis.data_transform import TRANSFORM_METHODS
    transform_dropdown = ft.Dropdown(
        label="データ変換",
        options=[ft.dropdown.Option(key=k, text=v) for k, v in TRANSFORM_METHODS.items()],
        value="none",
        width=300,
    )
    standardize_switch = ft.Switch(label="標準化", value=False)

    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)

    def run_analysis(e):
        """分析実行"""
        target = selector.get_target()
        features = selector.get_selected_features()

        if not target:
            result_container.controls = [ft.Text("目的変数を選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return
        if not features:
            result_container.controls = [ft.Text("説明変数を1つ以上選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        print(f"DEBUG: 相関分析実行 target={target}, features={features}")
        result_container.controls = [ft.ProgressRing()]
        page.update()

        try:
            cols = [target] + features
            work_df = df[cols].copy()

            # データ変換
            method = transform_dropdown.value
            work_df = transform(work_df, method)
            if standardize_switch.value:
                work_df = standardize(work_df)

            results = []

            # 相関行列
            corr = calc_correlation_matrix(work_df)
            img_corr = plot_correlation_heatmap(corr)
            results.append(ft.Text("相関行列", size=18, weight=ft.FontWeight.BOLD))
            results.append(ft.Image(src_base64=img_corr, fit=ft.ImageFit.CONTAIN))

            # VIF一覧
            if len(features) >= 2:
                X = work_df[features]
                vif_df = calc_vif(X)
                results.append(ft.Divider())
                results.append(ft.Text("VIF（分散拡大係数）", size=18, weight=ft.FontWeight.BOLD))
                results.append(ft.Text("VIF > 10: 多重共線性あり, VIF > 5: 注意", size=11, color=ft.Colors.GREY_600))

                vif_table = ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("変数")),
                        ft.DataColumn(ft.Text("VIF"), numeric=True),
                    ],
                    rows=[
                        ft.DataRow(cells=[
                            ft.DataCell(ft.Text(row["variable"])),
                            ft.DataCell(ft.Text(
                                f"{row['vif']:.4f}",
                                color=ft.Colors.RED_700 if row["vif"] > 10 else None,
                            )),
                        ])
                        for _, row in vif_df.iterrows()
                    ],
                    border=ft.border.all(1, ft.Colors.GREY_300),
                )
                results.append(vif_table)

                # VIFクロス表ヒートマップ
                vif_cross = calc_vif_cross_table(work_df[features])
                img_vif = plot_vif_heatmap(vif_cross)
                results.append(ft.Divider())
                results.append(ft.Text("VIFクロス表", size=18, weight=ft.FontWeight.BOLD))
                results.append(ft.Image(src_base64=img_vif, fit=ft.ImageFit.CONTAIN))
            else:
                results.append(ft.Text("VIF算出には説明変数を2つ以上選択してください。", size=12, italic=True))

            result_container.controls = results
            print("DEBUG: 相関分析完了")

        except Exception as ex:
            print(f"DEBUG: 相関分析エラー: {ex}")
            result_container.controls = [ft.Text(f"分析エラー: {ex}", color=ft.Colors.RED_700)]

        page.update()

    # レイアウト
    return ft.Column(
        controls=[
            ft.Text("相関分析", size=24, weight=ft.FontWeight.BOLD),
            selector.get_ui(),
            ft.Row([transform_dropdown, standardize_switch]),
            ft.ElevatedButton("分析実行", on_click=run_analysis, icon=ft.Icons.ANALYTICS),
            ft.Divider(),
            result_container,
        ],
        spacing=10,
        expand=True,
    )
