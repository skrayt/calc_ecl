"""データ閲覧ページ

データセット選択・指標一覧表示・時系列グラフ表示を行う。
"""
import flet as ft
import pandas as pd

from src.data.indicator_loader import (
    list_datasets,
    list_frequencies,
    load_indicators,
    get_indicator_definitions,
)
from components.plot_utils import plot_time_series, plot_time_series_grid


def data_view_page(page: ft.Page) -> ft.Control:
    """データ閲覧タブのUIを構築する"""
    print("DEBUG: データ閲覧ページ構築開始")

    # == 状態変数 ==
    current_df: pd.DataFrame | None = None

    # == UI部品 ==
    dataset_dropdown = ft.Dropdown(
        label="データセット",
        width=400,
        on_change=lambda e: on_dataset_change(e),
    )
    freq_dropdown = ft.Dropdown(
        label="frequency",
        width=200,
        on_change=lambda e: on_freq_change(e),
    )
    status_text = ft.Text("データセットを選択してください", size=12)
    data_table_container = ft.Column(scroll=ft.ScrollMode.AUTO)
    plot_container = ft.Column()
    indicator_checkboxes = ft.Column(spacing=2)
    plot_button = ft.ElevatedButton(
        "選択した指標をプロット",
        on_click=lambda e: on_plot_click(),
        disabled=True,
    )

    def load_datasets():
        """データセット一覧を読み込む"""
        try:
            datasets = list_datasets()
            print(f"DEBUG: データセット {len(datasets)}件取得")
            dataset_dropdown.options = [
                ft.dropdown.Option(
                    key=str(row["dataset_id"]),
                    text=f"ID:{row['dataset_id']} - {row['dataset_name']} ({row['retrieved_at']})",
                )
                for _, row in datasets.iterrows()
            ]
            if not datasets.empty:
                dataset_dropdown.value = str(datasets.iloc[0]["dataset_id"])
            page.update()

            # 初期選択があれば発火
            if dataset_dropdown.value:
                _load_frequencies(int(dataset_dropdown.value))
        except Exception as ex:
            print(f"DEBUG: データセット取得エラー: {ex}")
            status_text.value = f"データセット取得エラー: {ex}"
            status_text.color = ft.Colors.RED_700
            page.update()

    def on_dataset_change(e):
        """データセット選択時"""
        ds_id = int(e.control.value)
        print(f"DEBUG: データセット変更 → ID={ds_id}")
        _load_frequencies(ds_id)

    def _load_frequencies(dataset_id: int):
        """frequency一覧を取得してドロップダウンに設定"""
        try:
            freqs = list_frequencies(dataset_id)
            print(f"DEBUG: frequency一覧: {freqs}")
            freq_dropdown.options = [
                ft.dropdown.Option(f) for f in freqs
            ]
            if freqs:
                freq_dropdown.value = freqs[0]
            page.update()

            # データ読み込み
            if freq_dropdown.value:
                _load_data(dataset_id, freq_dropdown.value)
        except Exception as ex:
            print(f"DEBUG: frequency取得エラー: {ex}")
            status_text.value = f"frequency取得エラー: {ex}"
            status_text.color = ft.Colors.RED_700
            page.update()

    def on_freq_change(e):
        """frequency変更時"""
        ds_id = int(dataset_dropdown.value)
        freq = e.control.value
        print(f"DEBUG: frequency変更 → {freq}")
        _load_data(ds_id, freq)

    def _load_data(dataset_id: int, frequency: str):
        """指標データを読み込んでテーブル・チェックボックスを更新する"""
        nonlocal current_df
        try:
            df = load_indicators(dataset_id, frequency)
            current_df = df
            print(f"DEBUG: データ読み込み完了 shape={df.shape}")

            # ページにデータを共有（他タブから参照）
            page.session.set("dataset_id", dataset_id)
            page.session.set("frequency", frequency)
            page.session.set("df", df)

            status_text.value = (
                f"データセットID: {dataset_id} | frequency: {frequency} | "
                f"期間: {df.index.min()} 〜 {df.index.max()} | "
                f"{len(df)}行 × {len(df.columns)}列"
            )
            status_text.color = ft.Colors.GREEN_700

            # テーブル表示
            _update_data_table(df)

            # チェックボックス
            _update_indicator_checkboxes(df.columns.tolist())

            plot_button.disabled = False
            plot_container.controls.clear()
            page.update()

        except Exception as ex:
            print(f"DEBUG: データ読み込みエラー: {ex}")
            status_text.value = f"データ読み込みエラー: {ex}"
            status_text.color = ft.Colors.RED_700
            current_df = None
            page.update()

    def _update_data_table(df: pd.DataFrame):
        """DataTableを更新する"""
        data_table_container.controls.clear()

        if df.empty:
            data_table_container.controls.append(ft.Text("データがありません"))
            return

        # 先頭20行を表示
        display_df = df.head(20)

        columns = [ft.DataColumn(ft.Text("日付", size=11))]
        columns += [ft.DataColumn(ft.Text(c, size=11)) for c in display_df.columns]

        rows = []
        for idx, row in display_df.iterrows():
            cells = [ft.DataCell(ft.Text(str(idx.date()), size=10))]
            for col in display_df.columns:
                val = row[col]
                text = f"{val:.4f}" if pd.notna(val) else "-"
                cells.append(ft.DataCell(ft.Text(text, size=10)))
            rows.append(ft.DataRow(cells=cells))

        table = ft.DataTable(
            columns=columns,
            rows=rows,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=5,
            column_spacing=15,
        )

        # 横スクロール対応
        data_table_container.controls.append(
            ft.Container(
                content=ft.Row([table], scroll=ft.ScrollMode.AUTO),
                height=400,
            )
        )

        if len(df) > 20:
            data_table_container.controls.append(
                ft.Text(f"※ 先頭20行を表示中（全{len(df)}行）", size=11, italic=True)
            )

    def _update_indicator_checkboxes(columns: list[str]):
        """指標チェックボックスを更新する"""
        indicator_checkboxes.controls.clear()
        for col in columns:
            indicator_checkboxes.controls.append(
                ft.Checkbox(label=col, value=True)
            )

    def on_plot_click():
        """プロットボタン押下時"""
        if current_df is None or current_df.empty:
            return

        selected_cols = [
            cb.label for cb in indicator_checkboxes.controls
            if isinstance(cb, ft.Checkbox) and cb.value
        ]
        print(f"DEBUG: プロット対象: {selected_cols}")

        if not selected_cols:
            status_text.value = "プロットする指標を選択してください"
            status_text.color = ft.Colors.ORANGE_700
            page.update()
            return

        plot_container.controls.clear()

        try:
            if len(selected_cols) <= 3:
                # 少数なら1つのグラフに重ねて表示
                img_base64 = plot_time_series(current_df, selected_cols)
            else:
                # 多数ならグリッド表示
                img_base64 = plot_time_series_grid(current_df, selected_cols)

            if img_base64:
                plot_container.controls.append(
                    ft.Image(src_base64=img_base64, fit=ft.ImageFit.CONTAIN)
                )
        except Exception as ex:
            print(f"DEBUG: プロットエラー: {ex}")
            plot_container.controls.append(
                ft.Text(f"プロットエラー: {ex}", color=ft.Colors.RED_700)
            )

        page.update()

    # == ページレイアウト ==
    layout = ft.Column(
        controls=[
            ft.Text("データ閲覧", size=24, weight=ft.FontWeight.BOLD),
            ft.Row(
                [dataset_dropdown, freq_dropdown],
                alignment=ft.MainAxisAlignment.START,
            ),
            status_text,
            ft.Divider(),
            ft.Text("指標データテーブル", size=16, weight=ft.FontWeight.BOLD),
            data_table_container,
            ft.Divider(),
            ft.Text("時系列グラフ", size=16, weight=ft.FontWeight.BOLD),
            ft.Text("プロットする指標を選択:", size=12),
            ft.Container(
                content=indicator_checkboxes,
                height=150,
                border=ft.border.all(1, ft.Colors.GREY_300),
                border_radius=5,
                padding=8,
            ),
            plot_button,
            plot_container,
        ],
        spacing=10,
        expand=True,
    )

    # 初期データ読み込み
    load_datasets()

    return layout
