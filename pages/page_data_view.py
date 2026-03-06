"""データ閲覧ページ

データセット選択・指標一覧表示・時系列グラフ表示、および新規データインポートを行う。
説明変数（マクロ経済指標）と目的変数（PD/LGD/EAD）の2タブ構成。
"""
import flet as ft
import pandas as pd
from datetime import date
import threading

from src.data.indicator_loader import (
    list_datasets,
    list_frequencies,
    load_indicators,
    get_indicator_definitions,
    list_target_datasets,
    list_target_frequencies,
    list_target_segments,
    load_targets,
    get_target_definitions,
)
from components.plot_utils import plot_single_series
from src.import_indicators import import_csv_gui
from src.import_targets import import_target_csv_gui
from components.help_panel import build_help_panel


def data_view_page(page: ft.Page) -> ft.Control:
    """データ閲覧タブのUIを構築する"""
    print("DEBUG: データ閲覧ページ構築開始")

    # =========================================================
    # 説明変数タブ
    # =========================================================
    def _build_indicator_tab():
        """説明変数タブのUIを構築する"""
        current_df_ref = [None]
        code_to_name_ref = [{}]
        prompt_result = None
        prompt_event = threading.Event()

        # UI部品
        dataset_dropdown = ft.Dropdown(
            label="データセット", width=400,
            on_select=lambda e: on_dataset_change(e),
        )
        freq_dropdown = ft.Dropdown(
            label="frequency", width=200,
            on_select=lambda e: on_freq_change(e),
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

        # インポート関連UI
        progress_bar = ft.ProgressBar(width=400, color="blue", visible=False)
        import_status = ft.Text("", size=12)

        # 指標コード入力ダイアログ
        new_code_input = ft.TextField(label="指標コード (snake_case)")
        col_name_text = ft.Text("", weight="bold")
        auto_info_text = ft.Text("", size=11)

        def close_dlg(e):
            nonlocal prompt_result
            prompt_result = e.control.data
            prompt_event.set()
            mapping_dialog.open = False
            page.update()

        mapping_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("未知のカラムが見つかりました"),
            content=ft.Column([col_name_text, auto_info_text, new_code_input], tight=True, spacing=10),
            actions=[
                ft.TextButton("追加", on_click=close_dlg, data="add"),
                ft.TextButton("スキップ登録", on_click=close_dlg, data="skip"),
                ft.TextButton("今回は無視", on_click=close_dlg, data="ignore"),
            ],
        )

        def prompt_callback_gui(col_name, auto_info):
            nonlocal prompt_result
            col_name_text.value = f"カラム名: {col_name}"
            auto_info_text.value = (
                f"自動検出結果:\n"
                f"  名前: {auto_info['name']}\n"
                f"  基準年: {auto_info['base_year'] or 'なし'}\n"
                f"  単位: {auto_info['unit'] or 'なし'}\n"
                f"  粒度: {auto_info['frequency']}"
            )
            new_code_input.value = ""
            prompt_event.clear()
            page.dialog = mapping_dialog
            mapping_dialog.open = True
            page.update()
            prompt_event.wait()
            if prompt_result == "add":
                return {"action": "add", "code": new_code_input.value}
            elif prompt_result == "skip":
                return {"action": "skip"}
            return None

        def on_import_result(res):
            progress_bar.visible = False
            if "error" in res:
                import_status.value = f"エラー: {res['error']}"
                import_status.color = ft.Colors.RED_700
            else:
                import_status.value = f"インポート完了: {res['inserted']}件登録 (ID: {res['dataset_id']})"
                import_status.color = ft.Colors.GREEN_700
                load_datasets_list()
            page.update()

        def start_import_thread(file_path):
            def run():
                try:
                    def prog(curr, total):
                        progress_bar.value = curr / total
                        import_status.value = f"インポート中... {curr}/{total}"
                        page.update()
                    res = import_csv_gui(file_path, date.today(), progress_callback=prog, prompt_callback=prompt_callback_gui)
                    on_import_result(res)
                except Exception as ex:
                    on_import_result({"error": str(ex)})
            threading.Thread(target=run, daemon=True).start()

        async def pick_csv(e):
            files = await file_picker.pick_files(allow_multiple=False, allowed_extensions=["csv"])
            if files:
                progress_bar.visible = True
                progress_bar.value = 0
                import_status.value = "準備中..."
                page.update()
                start_import_thread(files[0].path)

        file_picker = ft.FilePicker()
        page.overlay.append(file_picker)
        page.update()

        def load_datasets_list():
            try:
                datasets = list_datasets()
                dataset_dropdown.options = [
                    ft.dropdown.Option(
                        key=str(row["dataset_id"]),
                        text=f"ID:{row['dataset_id']} - {row['dataset_name']} ({row['retrieved_at']})",
                    )
                    for _, row in datasets.iterrows()
                ]
                if not datasets.empty:
                    dataset_dropdown.value = str(datasets.iloc[0]["dataset_id"])
                    _load_frequencies(int(dataset_dropdown.value))
                page.update()
            except Exception as ex:
                status_text.value = f"データセット取得エラー: {ex}"
                status_text.color = ft.Colors.RED_700
                page.update()

        def on_dataset_change(e):
            _load_frequencies(int(e.control.value))

        def _load_frequencies(dataset_id):
            try:
                freqs = list_frequencies(dataset_id)
                freq_dropdown.options = [ft.dropdown.Option(f) for f in freqs]
                if freqs:
                    freq_dropdown.value = freqs[0]
                    _load_data(dataset_id, freq_dropdown.value)
                page.update()
            except Exception as ex:
                status_text.value = f"frequency取得エラー: {ex}"
                page.update()

        def on_freq_change(e):
            _load_data(int(dataset_dropdown.value), e.control.value)

        def _load_data(dataset_id, frequency):
            try:
                df = load_indicators(dataset_id, frequency)
                current_df_ref[0] = df
                if not df.empty:
                    defs = get_indicator_definitions(df.columns.tolist())
                    code_to_name_ref[0] = dict(zip(defs["indicator_code"], defs["indicator_name"]))
                page.session.store.set("df", df)
                status_text.value = (
                    f"ID: {dataset_id} | {frequency} | "
                    f"{df.index.min().date()}〜{df.index.max().date()} | {len(df)}行"
                )
                status_text.color = ft.Colors.GREEN_700
                _update_data_table(df)
                _update_checkboxes(df.columns.tolist())
                plot_button.disabled = False
                plot_container.controls.clear()
                page.update()
            except Exception as ex:
                status_text.value = f"ロードエラー: {ex}"
                status_text.color = ft.Colors.RED_700
                page.update()

        def _update_data_table(df):
            data_table_container.controls.clear()
            display_df = df.head(20)
            COL_DATE_W, COL_W = 90, 130
            HEADER_H, DATA_H = 50, 28
            c2n = code_to_name_ref[0]

            def _header_cell(text, width):
                return ft.Container(
                    content=ft.Text(text, size=10, weight=ft.FontWeight.BOLD),
                    width=width, height=HEADER_H,
                    padding=ft.padding.symmetric(horizontal=6, vertical=4),
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    alignment=ft.alignment.Alignment(-1, 0),
                )

            def _cell(text, width):
                return ft.Container(
                    content=ft.Text(text, size=10),
                    width=width, height=DATA_H,
                    padding=ft.padding.symmetric(horizontal=6, vertical=4),
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    alignment=ft.alignment.Alignment(-1, 0),
                )

            header = ft.Row(
                controls=[_header_cell("日付", COL_DATE_W)]
                + [_header_cell(c2n.get(c, c), COL_W) for c in display_df.columns],
                spacing=0,
            )

            def _is_int_col(series):
                valid = series.dropna()
                return len(valid) > 0 and (valid == valid.round()).all()
            is_int = {c: _is_int_col(display_df[c]) for c in display_df.columns}

            def _fmt(val, col):
                if pd.isna(val):
                    return "-"
                return f"{int(val):,}" if is_int[col] else f"{val:,.2f}"

            data_rows = []
            for idx, row in display_df.iterrows():
                data_rows.append(ft.Row(
                    controls=[_cell(str(idx.date()), COL_DATE_W)]
                    + [_cell(_fmt(row[c], c), COL_W) for c in display_df.columns],
                    spacing=0,
                ))

            table_col = ft.Column(controls=[header] + data_rows, spacing=0)
            data_table_container.controls.append(
                ft.Row(controls=[table_col], scroll=ft.ScrollMode.AUTO)
            )

        def _update_checkboxes(columns):
            c2n = code_to_name_ref[0]
            indicator_checkboxes.controls = [
                ft.Checkbox(label=c2n.get(col, col), data=col, value=True)
                for col in columns
            ]

        def on_plot_click():
            selected = [cb.data for cb in indicator_checkboxes.controls if cb.value]
            if not selected:
                return
            plot_container.controls.clear()
            c2n = code_to_name_ref[0]
            N_COLS = 3
            row_controls = []
            for col in selected:
                label = c2n.get(col, col)
                try:
                    img = plot_single_series(current_df_ref[0], col, label=label, figsize=(5, 3))
                    cell = ft.Image(src="data:image/png;base64," + img, fit=ft.BoxFit.CONTAIN, expand=True)
                except Exception as ex:
                    cell = ft.Text(f"{label}: エラー: {ex}", color=ft.Colors.RED_700, expand=True)
                row_controls.append(cell)
                if len(row_controls) == N_COLS:
                    plot_container.controls.append(ft.Row(controls=row_controls, spacing=4))
                    row_controls = []
            if row_controls:
                while len(row_controls) < N_COLS:
                    row_controls.append(ft.Container(expand=True))
                plot_container.controls.append(ft.Row(controls=row_controls, spacing=4))
            page.update()

        layout = ft.Column(
            controls=[
                ft.Row([
                    ft.Text("説明変数（マクロ経済指標）", size=20, weight=ft.FontWeight.BOLD),
                    ft.ElevatedButton("新規CSVインポート", icon=ft.Icons.UPLOAD_FILE, on_click=pick_csv),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([progress_bar, import_status]),
                ft.Row([dataset_dropdown, freq_dropdown]),
                status_text,
                ft.Divider(),
                ft.Text("最新データのプレビュー (先頭20行)", size=14, weight=ft.FontWeight.BOLD),
                data_table_container,
                ft.Divider(),
                ft.Text("時系列グラフ表示", size=16, weight=ft.FontWeight.BOLD),
                ft.Container(content=indicator_checkboxes, height=150, border=ft.border.all(1, ft.Colors.GREY_300), padding=8),
                plot_button,
                plot_container,
            ],
            spacing=10,
        )

        load_datasets_list()
        return layout

    # =========================================================
    # 目的変数タブ
    # =========================================================
    def _build_target_tab():
        """目的変数（PD/LGD/EAD）タブのUIを構築する"""
        current_target_df_ref = [None]
        target_code_to_name_ref = [{}]

        # UI部品
        t_dataset_dropdown = ft.Dropdown(
            label="目的変数データセット", width=400,
            on_select=lambda e: on_t_dataset_change(e),
        )
        t_freq_dropdown = ft.Dropdown(
            label="frequency", width=200,
            on_select=lambda e: on_t_freq_change(e),
        )
        t_segment_dropdown = ft.Dropdown(
            label="セグメント", width=200,
            on_select=lambda e: on_t_segment_change(e),
        )
        t_status_text = ft.Text("目的変数データセットを選択してください", size=12)
        t_data_table_container = ft.Column(scroll=ft.ScrollMode.AUTO)
        t_plot_container = ft.Column()
        t_checkboxes = ft.Column(spacing=2)
        t_plot_button = ft.ElevatedButton(
            "選択した目的変数をプロット",
            on_click=lambda e: on_t_plot_click(),
            disabled=True,
        )

        # インポート関連UI
        t_progress_bar = ft.ProgressBar(width=400, color="blue", visible=False)
        t_import_status = ft.Text("", size=12)
        t_dataset_name_input = ft.TextField(label="データセット名", width=300)
        t_type_dropdown = ft.Dropdown(
            label="目的変数タイプ", width=150,
            options=[
                ft.dropdown.Option("pd", "PD（デフォルト率）"),
                ft.dropdown.Option("lgd", "LGD（損失率）"),
                ft.dropdown.Option("ead", "EAD（エクスポージャー）"),
            ],
            value="pd",
        )
        t_unit_input = ft.TextField(label="単位 (例: %)", width=100, value="%")

        # 目的変数名入力ダイアログ
        t_name_inputs = {}
        t_name_dialog_content = ft.Column([], tight=True, spacing=8)
        t_name_dialog_result = [None]
        t_name_dialog_event = threading.Event()

        def on_t_name_dialog_close(e):
            t_name_dialog_result[0] = e.control.data
            t_name_dialog_event.set()
            t_name_dialog.open = False
            page.update()

        t_name_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("目的変数の日本語名を入力"),
            content=t_name_dialog_content,
            actions=[
                ft.TextButton("OK", on_click=on_t_name_dialog_close, data="ok"),
                ft.TextButton("キャンセル", on_click=on_t_name_dialog_close, data="cancel"),
            ],
        )
        # t_name_dialogはpage.dialogに設定して表示する

        def on_t_import_result(res):
            t_progress_bar.visible = False
            if "error" in res:
                t_import_status.value = f"エラー: {res['error']}"
                t_import_status.color = ft.Colors.RED_700
            else:
                t_import_status.value = (
                    f"インポート完了: {res['inserted']}件登録 "
                    f"(ID: {res['target_dataset_id']})"
                )
                t_import_status.color = ft.Colors.GREEN_700
                load_target_datasets_list()
            page.update()

        def start_target_import_thread(file_path, dataset_name, target_type, unit):
            def run():
                try:
                    # CSVを読み込んで目的変数列を確認
                    import csv
                    with open(file_path, encoding="utf-8") as f:
                        reader = csv.reader(f)
                        headers = next(reader)
                    fixed = {"時点", "セグメントコード", "セグメント名"}
                    target_cols = [h for h in headers if h not in fixed]

                    # 未登録の目的変数名をダイアログで入力
                    from config.db import get_connection
                    conn = get_connection()
                    try:
                        cur = conn.cursor()
                        new_cols = []
                        for tc in target_cols:
                            cur.execute(
                                "SELECT target_name FROM target_definitions WHERE target_code = %s",
                                (tc,),
                            )
                            if not cur.fetchone():
                                new_cols.append(tc)
                    finally:
                        conn.close()

                    target_names = {}
                    if new_cols:
                        # GUIスレッドで名前入力ダイアログを表示
                        t_name_inputs.clear()
                        t_name_dialog_content.controls.clear()
                        for nc in new_cols:
                            tf = ft.TextField(label=f"{nc} の日本語名", value=nc)
                            t_name_inputs[nc] = tf
                            t_name_dialog_content.controls.append(tf)

                        t_name_dialog_event.clear()
                        page.dialog = t_name_dialog
                        t_name_dialog.open = True
                        page.update()
                        t_name_dialog_event.wait()

                        if t_name_dialog_result[0] == "cancel":
                            on_t_import_result({"error": "キャンセルされました"})
                            return

                        for nc, tf in t_name_inputs.items():
                            target_names[nc] = tf.value or nc

                    def prog(curr, total):
                        t_progress_bar.value = curr / total
                        t_import_status.value = f"インポート中... {curr}/{total}"
                        page.update()

                    res = import_target_csv_gui(
                        file_path,
                        date.today(),
                        dataset_name,
                        target_type,
                        target_names=target_names if target_names else None,
                        unit=unit,
                        progress_callback=prog,
                    )
                    on_t_import_result(res)
                except Exception as ex:
                    on_t_import_result({"error": str(ex)})

            threading.Thread(target=run, daemon=True).start()

        async def pick_target_csv(e):
            files = await t_file_picker.pick_files(allow_multiple=False, allowed_extensions=["csv"])
            if files:
                ds_name = t_dataset_name_input.value or f"{date.today().strftime('%Y年%m月')} {t_type_dropdown.value.upper()}実績"
                t_progress_bar.visible = True
                t_progress_bar.value = 0
                t_import_status.value = "準備中..."
                page.update()
                start_target_import_thread(
                    files[0].path, ds_name, t_type_dropdown.value, t_unit_input.value
                )

        t_file_picker = ft.FilePicker()
        page.overlay.append(t_file_picker)
        page.update()

        # データ読み込み・表示ロジック
        def load_target_datasets_list():
            try:
                datasets = list_target_datasets()
                t_dataset_dropdown.options = [
                    ft.dropdown.Option(
                        key=str(row["target_dataset_id"]),
                        text=f"ID:{row['target_dataset_id']} - {row['dataset_name']} ({row['retrieved_at']})",
                    )
                    for _, row in datasets.iterrows()
                ]
                if not datasets.empty:
                    t_dataset_dropdown.value = str(datasets.iloc[0]["target_dataset_id"])
                    _load_t_frequencies(int(t_dataset_dropdown.value))
                else:
                    t_status_text.value = "目的変数データセットがありません。CSVをインポートしてください。"
                page.update()
            except Exception as ex:
                t_status_text.value = f"データセット取得エラー: {ex}"
                t_status_text.color = ft.Colors.RED_700
                page.update()

        def on_t_dataset_change(e):
            _load_t_frequencies(int(e.control.value))

        def _load_t_frequencies(target_dataset_id):
            try:
                freqs = list_target_frequencies(target_dataset_id)
                t_freq_dropdown.options = [ft.dropdown.Option(f) for f in freqs]
                if freqs:
                    t_freq_dropdown.value = freqs[0]
                    _load_t_segments(target_dataset_id, freqs[0])
                page.update()
            except Exception as ex:
                t_status_text.value = f"frequency取得エラー: {ex}"
                page.update()

        def on_t_freq_change(e):
            _load_t_segments(int(t_dataset_dropdown.value), e.control.value)

        def _load_t_segments(target_dataset_id, frequency):
            try:
                segments = list_target_segments(target_dataset_id, frequency)
                t_segment_dropdown.options = [
                    ft.dropdown.Option(
                        key=s["segment_code"],
                        text=f"{s['segment_name']} ({s['segment_code']})",
                    )
                    for s in segments
                ]
                if segments:
                    t_segment_dropdown.value = segments[0]["segment_code"]
                    _load_target_data(target_dataset_id, frequency, segments[0]["segment_code"])
                page.update()
            except Exception as ex:
                t_status_text.value = f"セグメント取得エラー: {ex}"
                page.update()

        def on_t_segment_change(e):
            _load_target_data(
                int(t_dataset_dropdown.value),
                t_freq_dropdown.value,
                e.control.value,
            )

        def _load_target_data(target_dataset_id, frequency, segment_code):
            try:
                df = load_targets(target_dataset_id, frequency, segment_code)
                current_target_df_ref[0] = df
                if not df.empty:
                    defs = get_target_definitions(df.columns.tolist())
                    target_code_to_name_ref[0] = dict(zip(defs["target_code"], defs["target_name"]))
                # セッションストアに保存（分析ページで使用）
                page.session.store.set("target_df", df)
                page.session.store.set("target_dataset_id", target_dataset_id)
                page.session.store.set("target_frequency", frequency)

                t_status_text.value = (
                    f"ID: {target_dataset_id} | {frequency} | セグメント: {segment_code} | "
                    f"{df.index.min().date()}〜{df.index.max().date()} | {len(df)}行"
                )
                t_status_text.color = ft.Colors.GREEN_700
                _update_t_data_table(df)
                _update_t_checkboxes(df.columns.tolist())
                t_plot_button.disabled = False
                t_plot_container.controls.clear()
                page.update()
            except Exception as ex:
                t_status_text.value = f"ロードエラー: {ex}"
                t_status_text.color = ft.Colors.RED_700
                page.update()

        def _update_t_data_table(df):
            t_data_table_container.controls.clear()
            display_df = df.head(20)
            COL_DATE_W, COL_W = 90, 150
            HEADER_H, DATA_H = 50, 28
            c2n = target_code_to_name_ref[0]

            def _header_cell(text, width):
                return ft.Container(
                    content=ft.Text(text, size=10, weight=ft.FontWeight.BOLD),
                    width=width, height=HEADER_H,
                    padding=ft.padding.symmetric(horizontal=6, vertical=4),
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    alignment=ft.alignment.Alignment(-1, 0),
                )

            def _cell(text, width):
                return ft.Container(
                    content=ft.Text(text, size=10),
                    width=width, height=DATA_H,
                    padding=ft.padding.symmetric(horizontal=6, vertical=4),
                    border=ft.border.all(1, ft.Colors.GREY_300),
                    alignment=ft.alignment.Alignment(-1, 0),
                )

            header = ft.Row(
                controls=[_header_cell("日付", COL_DATE_W)]
                + [_header_cell(c2n.get(c, c), COL_W) for c in display_df.columns],
                spacing=0,
            )

            def _fmt(val):
                if pd.isna(val):
                    return "-"
                return f"{val:,.6f}" if abs(val) < 1 else f"{val:,.4f}"

            data_rows = []
            for idx, row in display_df.iterrows():
                data_rows.append(ft.Row(
                    controls=[_cell(str(idx.date()), COL_DATE_W)]
                    + [_cell(_fmt(row[c]), COL_W) for c in display_df.columns],
                    spacing=0,
                ))

            table_col = ft.Column(controls=[header] + data_rows, spacing=0)
            t_data_table_container.controls.append(
                ft.Row(controls=[table_col], scroll=ft.ScrollMode.AUTO)
            )

        def _update_t_checkboxes(columns):
            c2n = target_code_to_name_ref[0]
            t_checkboxes.controls = [
                ft.Checkbox(label=c2n.get(col, col), data=col, value=True)
                for col in columns
            ]

        def on_t_plot_click():
            selected = [cb.data for cb in t_checkboxes.controls if cb.value]
            if not selected:
                return
            t_plot_container.controls.clear()
            c2n = target_code_to_name_ref[0]
            N_COLS = 3
            row_controls = []
            for col in selected:
                label = c2n.get(col, col)
                try:
                    img = plot_single_series(current_target_df_ref[0], col, label=label, figsize=(5, 3))
                    cell = ft.Image(src="data:image/png;base64," + img, fit=ft.BoxFit.CONTAIN, expand=True)
                except Exception as ex:
                    cell = ft.Text(f"{label}: エラー: {ex}", color=ft.Colors.RED_700, expand=True)
                row_controls.append(cell)
                if len(row_controls) == N_COLS:
                    t_plot_container.controls.append(ft.Row(controls=row_controls, spacing=4))
                    row_controls = []
            if row_controls:
                while len(row_controls) < N_COLS:
                    row_controls.append(ft.Container(expand=True))
                t_plot_container.controls.append(ft.Row(controls=row_controls, spacing=4))
            page.update()

        layout = ft.Column(
            controls=[
                ft.Row([
                    ft.Text("目的変数（PD/LGD/EAD）", size=20, weight=ft.FontWeight.BOLD),
                    ft.ElevatedButton("目的変数CSVインポート", icon=ft.Icons.UPLOAD_FILE, on_click=pick_target_csv),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([t_dataset_name_input, t_type_dropdown, t_unit_input]),
                ft.Row([t_progress_bar, t_import_status]),
                ft.Row([t_dataset_dropdown, t_freq_dropdown, t_segment_dropdown]),
                t_status_text,
                ft.Divider(),
                ft.Text("最新データのプレビュー (先頭20行)", size=14, weight=ft.FontWeight.BOLD),
                t_data_table_container,
                ft.Divider(),
                ft.Text("時系列グラフ表示", size=16, weight=ft.FontWeight.BOLD),
                ft.Container(content=t_checkboxes, height=150, border=ft.border.all(1, ft.Colors.GREY_300), padding=8),
                t_plot_button,
                t_plot_container,
            ],
            spacing=10,
        )

        load_target_datasets_list()
        return layout

    # =========================================================
    # ヘルプパネル
    # =========================================================
    _help = build_help_panel(
        title="① データ閲覧・管理",
        purpose="DBに格納されたマクロ経済指標（説明変数）と目的変数（PD/LGD/EAD）を閲覧・グラフ表示し、新しいCSVファイルをインポートします。",
        steps=[
            "「説明変数データ」タブ: マクロ経済指標のデータセットを選択・表示・インポートする",
            "「目的変数データ」タブ: PD/LGD/EADのデータセットを選択・表示・インポートする",
            "frequencyドロップダウンで粒度（月次・四半期・年度等）を選択する",
            "チェックボックスで表示したい指標を選び、プロットボタンを押す",
            "グラフで欠損・外れ値・トレンドの有無を目視確認する（分析前の必須ステップ）",
        ],
        outputs=[
            "データセットの期間・行数・ID（ステータス表示）",
            "最新データの先頭20行（日付 + 指標値のテーブル）",
            "選択した指標の時系列グラフ",
            "インポート進捗バーと完了メッセージ",
        ],
        indicators=[
            {
                "name": "目的変数CSVフォーマット",
                "criteria": [
                    {"level": "必須", "range": "時点列", "meaning": "「2025年度」「2025年1-3月期」等の形式。説明変数CSVと同じ"},
                    {"level": "任意", "range": "セグメントコード列", "meaning": "法人=corporate 等。省略時は「all（全体）」"},
                    {"level": "任意", "range": "セグメント名列", "meaning": "セグメントの日本語名。省略時は「全体」"},
                    {"level": "必須", "range": "数値列（目的変数）", "meaning": "カラム名がそのまま目的変数コードになる（例: pd_corporate）"},
                ],
                "note": "目的変数と説明変数のfrequencyを揃えることで、分析時に自動結合される",
            },
        ],
    )

    # =========================================================
    # タブ構成
    # =========================================================
    indicator_tab_content = _build_indicator_tab()
    target_tab_content = _build_target_tab()

    # サブタブ: ボタン切替（TabBarは親Tabsにイベントがバブルするため不使用）
    sub_tab_body = ft.Container(content=indicator_tab_content, padding=10)

    btn_indicator = ft.ElevatedButton("説明変数データ", disabled=True)
    btn_target = ft.OutlinedButton("目的変数データ")

    def switch_to_indicator(e):
        sub_tab_body.content = indicator_tab_content
        btn_indicator.disabled = True
        btn_target.disabled = False
        page.update()

    def switch_to_target(e):
        sub_tab_body.content = target_tab_content
        btn_indicator.disabled = False
        btn_target.disabled = True
        page.update()

    btn_indicator.on_click = switch_to_indicator
    btn_target.on_click = switch_to_target

    layout = ft.Column(
        controls=[
            _help,
            ft.Text("データ閲覧・管理", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([btn_indicator, btn_target], spacing=8),
            sub_tab_body,
        ],
        spacing=10,
    )

    return layout
