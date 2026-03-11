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
    find_dataset_by_fiscal_ym,
    list_target_datasets,
    list_target_frequencies,
    list_target_segments,
    load_targets,
    get_target_definitions,
)
from components.plot_utils import plot_single_series, plot_compare_series
from src.analysis.data_transform import transform, standardize, TRANSFORM_METHODS
from src.import_indicators import (
    import_csv_gui,
    detect_unknown_columns,
    apply_mapping_results,
)
from src.import_targets import import_target_csv_gui
from components.help_panel import build_help_panel


def data_view_page(page: ft.Page) -> ft.Control:
    """データ閲覧タブのUIを構築する"""
    print("DEBUG: データ閲覧ページ構築開始")

    # =========================================================
    # 比較プロット用の共有データ参照（両タブを横断）
    # =========================================================
    shared = {
        "ind_df": None,
        "ind_c2n": {},
        "tgt_df": None,
        "tgt_c2n": {},
    }

    # =========================================================
    # 説明変数タブ
    # =========================================================
    def _build_indicator_tab():
        """説明変数タブのUIを構築する"""
        current_df_ref = [None]
        code_to_name_ref = [{}]

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
        transform_dropdown = ft.Dropdown(
            label="変換方法",
            options=[ft.dropdown.Option(key=k, text=v) for k, v in TRANSFORM_METHODS.items()],
            value="none", width=200,
        )
        standardize_switch = ft.Switch(label="標準化（z-score）", value=False)
        transform_plot_button = ft.ElevatedButton(
            "変換してプロット",
            on_click=lambda e: on_transform_plot_click(),
            disabled=True,
            icon=ft.Icons.TRANSFORM,
        )

        # インポート関連UI
        progress_bar = ft.ProgressBar(width=400, color="blue", visible=False)
        import_status = ft.Text("", size=12)

        # 決算年月入力
        current_year = date.today().year
        fiscal_year_dd = ft.Dropdown(
            label="決算年", width=120,
            options=[ft.dropdown.Option(str(y), f"{y}年") for y in range(current_year - 2, current_year + 5)],
            value=str(current_year),
        )
        fiscal_month_dd = ft.Dropdown(
            label="決算月", width=100,
            options=[ft.dropdown.Option(str(m), f"{m}月") for m in range(1, 13)],
            value="3",
        )

        # --- 一括マッピングダイアログ ---
        batch_dialog_content = ft.Column([], spacing=12, scroll=ft.ScrollMode.AUTO)
        batch_dialog_result = [None]
        batch_dialog_event = threading.Event()
        batch_col_widgets = []  # [(col_name, auto_info, action_dd, code_tf), ...]

        def close_batch_dialog(e):
            batch_dialog_result[0] = e.control.data
            page.pop_dialog()
            page.update()
            batch_dialog_event.set()

        batch_mapping_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("未知のカラムが見つかりました"),
            content=ft.Container(
                content=batch_dialog_content,
                height=400, width=550,
            ),
            actions=[
                ft.TextButton("確定", on_click=close_batch_dialog, data="ok"),
                ft.TextButton("キャンセル", on_click=close_batch_dialog, data="cancel"),
            ],
        )

        # --- 上書き確認ダイアログ ---
        confirm_dialog_result = [None]
        confirm_dialog_event = threading.Event()
        confirm_text = ft.Text("")

        def close_confirm_dialog(e):
            confirm_dialog_result[0] = e.control.data
            page.pop_dialog()
            page.update()
            confirm_dialog_event.set()

        confirm_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("データセットの上書き確認"),
            content=confirm_text,
            actions=[
                ft.TextButton("上書き", on_click=close_confirm_dialog, data="yes"),
                ft.TextButton("キャンセル", on_click=close_confirm_dialog, data="no"),
            ],
        )

        def _get_fiscal_year_month() -> date:
            """UIから決算年月を取得する"""
            y = int(fiscal_year_dd.value or current_year)
            m = int(fiscal_month_dd.value or 3)
            return date(y, m, 1)

        def on_import_result(res):
            progress_bar.visible = False
            if "error" in res:
                import_status.value = f"エラー: {res['error']}"
                import_status.color = ft.Colors.RED_700
            else:
                action = "上書き" if res.get("replaced") else "新規登録"
                import_status.value = (
                    f"インポート完了({action}): {res['inserted']}件登録 "
                    f"(ID: {res['dataset_id']})"
                )
                import_status.color = ft.Colors.GREEN_700
                load_datasets_list()
            page.update()

        def start_import_thread(file_path, fiscal_year_month):
            """インポートをバックグラウンドスレッドで実行する"""
            def run():
                try:
                    import pandas as _pd
                    # 1. CSV読み込みとヘッダー取得
                    csv_df = _pd.read_csv(file_path, encoding="utf-8", dtype=str, nrows=0)
                    csv_columns = list(csv_df.columns)

                    # 2. 未知カラム検出
                    unknowns = detect_unknown_columns(file_path, csv_columns)

                    # 3. 未知カラムがあれば一括ダイアログ表示
                    if unknowns:
                        batch_col_widgets.clear()
                        batch_dialog_content.controls.clear()

                        for col_name, _, auto_info in unknowns:
                            action_dd = ft.Dropdown(
                                label="アクション", width=140,
                                options=[
                                    ft.dropdown.Option("add", "追加"),
                                    ft.dropdown.Option("skip", "スキップ登録"),
                                    ft.dropdown.Option("ignore", "今回は無視"),
                                ],
                                value="add",
                            )
                            code_tf = ft.TextField(
                                label="指標コード (snake_case)", width=250,
                            )
                            batch_col_widgets.append(
                                (col_name, auto_info, action_dd, code_tf)
                            )

                            info_text = (
                                f"名前: {auto_info['name']}"
                                + (f" | 基準年: {auto_info['base_year']}" if auto_info['base_year'] else "")
                                + (f" | 単位: {auto_info['unit']}" if auto_info['unit'] else "")
                                + f" | 粒度: {auto_info['frequency']}"
                            )
                            batch_dialog_content.controls.append(
                                ft.Container(
                                    content=ft.Column([
                                        ft.Text(f"カラム: {col_name}", weight=ft.FontWeight.BOLD, size=13),
                                        ft.Text(info_text, size=11),
                                        ft.Row([action_dd, code_tf], spacing=8),
                                    ], spacing=4),
                                    padding=8,
                                    border=ft.border.all(1, ft.Colors.GREY_300),
                                    border_radius=4,
                                )
                            )

                        batch_dialog_event.clear()
                        batch_dialog_result[0] = None
                        page.show_dialog(batch_mapping_dialog)
                        page.update()
                        batch_dialog_event.wait()

                        if batch_dialog_result[0] == "cancel":
                            on_import_result({"error": "キャンセルされました"})
                            return

                        # ユーザー入力結果を保存
                        results = []
                        for col_name, auto_info, action_dd, code_tf in batch_col_widgets:
                            results.append({
                                "col": col_name,
                                "action": action_dd.value or "ignore",
                                "code": code_tf.value or "",
                                "auto_info": auto_info,
                            })
                        apply_mapping_results(results)

                    # 4. 既存データセットの確認（上書き確認）
                    existing = find_dataset_by_fiscal_ym(fiscal_year_month)
                    if existing:
                        confirm_text.value = (
                            f"決算年月 {fiscal_year_month.strftime('%Y年%m月')}期 のデータセットが\n"
                            f"既に存在します（ID: {existing['dataset_id']}, "
                            f"{existing['dataset_name']}）。\n\n"
                            f"既存データを全て削除して上書きしますか？"
                        )
                        confirm_dialog_event.clear()
                        confirm_dialog_result[0] = None
                        page.show_dialog(confirm_dialog)
                        page.update()
                        confirm_dialog_event.wait()

                        if confirm_dialog_result[0] != "yes":
                            on_import_result({"error": "キャンセルされました"})
                            return

                    # 5. インポート実行
                    def prog(curr, total):
                        progress_bar.value = curr / total
                        import_status.value = f"インポート中... {curr}/{total}"
                        page.update()

                    res = import_csv_gui(
                        file_path, date.today(), fiscal_year_month,
                        progress_callback=prog,
                    )
                    on_import_result(res)
                except Exception as ex:
                    on_import_result({"error": str(ex)})
            threading.Thread(target=run, daemon=True).start()

        async def pick_csv(e):
            files = await file_picker.pick_files(allow_multiple=False, allowed_extensions=["csv"])
            if files and files[0].path:
                fiscal_ym = _get_fiscal_year_month()
                progress_bar.visible = True
                progress_bar.value = 0
                import_status.value = "準備中..."
                page.update()
                start_import_thread(files[0].path, fiscal_ym)

        file_picker = ft.FilePicker()

        def load_datasets_list():
            try:
                datasets = list_datasets()
                dataset_dropdown.options = [
                    ft.dropdown.Option(
                        key=str(row["dataset_id"]),
                        text=(
                            f"ID:{row['dataset_id']} - {row['dataset_name']}"
                            + (f" [{row['fiscal_year_month'].strftime('%Y年%m月')}期]"
                               if pd.notna(row.get('fiscal_year_month')) else "")
                            + f" ({row['retrieved_at']})"
                        ),
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
                    status_text.value = (
                        f"ID: {dataset_id} | {frequency} | "
                        f"{df.index.min().date()}〜{df.index.max().date()} | {len(df)}行"
                    )
                    status_text.color = ft.Colors.GREEN_700
                else:
                    status_text.value = f"ID: {dataset_id} | {frequency} | データなし（0行）"
                    status_text.color = ft.Colors.ORANGE_700
                # 比較プロット用に共有参照を更新
                shared["ind_df"] = df
                shared["ind_c2n"] = code_to_name_ref[0]
                page.session.store.set("df", df)
                page.session.store.set("dataset_id", dataset_id)
                page.session.store.set("frequency", frequency)
                _update_data_table(df)
                _update_checkboxes(df.columns.tolist())
                plot_button.disabled = df.empty
                transform_plot_button.disabled = df.empty
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
            checkboxes = [
                ft.Checkbox(label=c2n.get(col, col), data=col, value=True, expand=True)
                for col in columns
            ]
            rows = []
            for i in range(0, len(checkboxes), 3):
                row_items = checkboxes[i:i + 3]
                while len(row_items) < 3:
                    row_items.append(ft.Container(expand=True))
                rows.append(ft.Row(controls=row_items, spacing=4))
            indicator_checkboxes.controls = rows

        def on_plot_click():
            selected = [
                cb.data for row in indicator_checkboxes.controls
                for cb in row.controls if isinstance(cb, ft.Checkbox) and cb.value
            ]
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

        def _is_unit_range(series: pd.Series) -> bool:
            """系列の全値が[0, 1]範囲に収まるか判定する"""
            valid = series.dropna()
            return len(valid) > 0 and (valid >= 0).all() and (valid <= 1).all()

        def on_transform_plot_click():
            """変換後の時系列グラフをプロットする"""
            df = current_df_ref[0]
            if df is None or df.empty:
                return
            selected = [
                cb.data for row in indicator_checkboxes.controls
                for cb in row.controls if isinstance(cb, ft.Checkbox) and cb.value
            ]
            if not selected:
                return
            method = transform_dropdown.value or "none"
            do_std = standardize_switch.value
            plot_container.controls.clear()
            c2n = code_to_name_ref[0]
            N_COLS = 3
            row_controls = []
            for col in selected:
                label = c2n.get(col, col)
                try:
                    transformed = transform(df[[col]].copy(), method=method)
                    if do_std and not _is_unit_range(df[col]):
                        transformed = standardize(transformed)
                    suffix = TRANSFORM_METHODS.get(method, method)
                    if do_std and not _is_unit_range(df[col]):
                        suffix += "＋標準化"
                    img = plot_single_series(
                        transformed, col,
                        label=f"{label}（{suffix}）",
                        figsize=(5, 3),
                    )
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
                    ft.Row([
                        fiscal_year_dd, fiscal_month_dd,
                        ft.ElevatedButton("CSVインポート", icon=ft.Icons.UPLOAD_FILE, on_click=pick_csv),
                    ], spacing=8),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([progress_bar, import_status]),
                ft.Row([dataset_dropdown, freq_dropdown]),
                status_text,
                ft.Divider(),
                ft.Text("最新データのプレビュー (先頭20行)", size=14, weight=ft.FontWeight.BOLD),
                data_table_container,
                ft.Divider(),
                ft.Text("時系列グラフ表示", size=16, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Column(controls=[indicator_checkboxes], scroll=ft.ScrollMode.AUTO),
                    height=200, border=ft.border.all(1, ft.Colors.GREY_300), padding=8,
                ),
                plot_button,
                ft.Row([transform_dropdown, standardize_switch, transform_plot_button], spacing=8),
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
        t_transform_dropdown = ft.Dropdown(
            label="変換方法",
            options=[ft.dropdown.Option(key=k, text=v) for k, v in TRANSFORM_METHODS.items()],
            value="none", width=200,
        )
        t_standardize_switch = ft.Switch(label="標準化（z-score）", value=False)
        t_transform_plot_button = ft.ElevatedButton(
            "変換してプロット",
            on_click=lambda e: on_t_transform_plot_click(),
            disabled=True,
            icon=ft.Icons.TRANSFORM,
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
            page.pop_dialog()
            page.update()
            t_name_dialog_event.set()

        t_name_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("目的変数の日本語名を入力"),
            content=t_name_dialog_content,
            actions=[
                ft.TextButton("OK", on_click=on_t_name_dialog_close, data="ok"),
                ft.TextButton("キャンセル", on_click=on_t_name_dialog_close, data="cancel"),
            ],
        )
        # t_name_dialogはpage.show_dialog()で表示、page.pop_dialog()で閉じる（Flet V1 API）

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
                        page.show_dialog(t_name_dialog)
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
            if files and files[0].path:
                ds_name = t_dataset_name_input.value or f"{date.today().strftime('%Y年%m月')} {t_type_dropdown.value.upper()}実績"
                t_progress_bar.visible = True
                t_progress_bar.value = 0
                t_import_status.value = "準備中..."
                page.update()
                start_target_import_thread(
                    files[0].path, ds_name, t_type_dropdown.value, t_unit_input.value
                )

        t_file_picker = ft.FilePicker()

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
                # 比較プロット用に共有参照を更新
                shared["tgt_df"] = df
                shared["tgt_c2n"] = target_code_to_name_ref[0]
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
                t_transform_plot_button.disabled = False
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
            checkboxes = [
                ft.Checkbox(label=c2n.get(col, col), data=col, value=True, expand=True)
                for col in columns
            ]
            rows = []
            for i in range(0, len(checkboxes), 3):
                row_items = checkboxes[i:i + 3]
                while len(row_items) < 3:
                    row_items.append(ft.Container(expand=True))
                rows.append(ft.Row(controls=row_items, spacing=4))
            t_checkboxes.controls = rows

        def on_t_plot_click():
            selected = [
                cb.data for row in t_checkboxes.controls
                for cb in row.controls if isinstance(cb, ft.Checkbox) and cb.value
            ]
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

        def _is_t_unit_range(series: pd.Series) -> bool:
            """系列の全値が[0, 1]範囲に収まるか判定する"""
            valid = series.dropna()
            return len(valid) > 0 and (valid >= 0).all() and (valid <= 1).all()

        def on_t_transform_plot_click():
            """変換後の目的変数グラフをプロットする"""
            df = current_target_df_ref[0]
            if df is None or df.empty:
                return
            selected = [
                cb.data for row in t_checkboxes.controls
                for cb in row.controls if isinstance(cb, ft.Checkbox) and cb.value
            ]
            if not selected:
                return
            method = t_transform_dropdown.value or "none"
            do_std = t_standardize_switch.value
            t_plot_container.controls.clear()
            c2n = target_code_to_name_ref[0]
            N_COLS = 3
            row_controls = []
            for col in selected:
                label = c2n.get(col, col)
                try:
                    transformed = transform(df[[col]].copy(), method=method)
                    if do_std and not _is_t_unit_range(df[col]):
                        transformed = standardize(transformed)
                    suffix = TRANSFORM_METHODS.get(method, method)
                    if do_std and not _is_t_unit_range(df[col]):
                        suffix += "＋標準化"
                    img = plot_single_series(
                        transformed, col,
                        label=f"{label}（{suffix}）",
                        figsize=(5, 3),
                    )
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
                ft.Container(
                    content=ft.Column(controls=[t_checkboxes], scroll=ft.ScrollMode.AUTO),
                    height=200, border=ft.border.all(1, ft.Colors.GREY_300), padding=8,
                ),
                t_plot_button,
                ft.Row([t_transform_dropdown, t_standardize_switch, t_transform_plot_button], spacing=8),
                t_plot_container,
            ],
            spacing=10,
        )

        load_target_datasets_list()
        return layout

    # =========================================================
    # 比較プロットタブ
    # =========================================================
    def _build_compare_tab():
        """説明変数と目的変数を重ねてプロットする比較タブ"""
        compare_plot_container = ft.Column()
        compare_status = ft.Text("説明変数・目的変数の両タブでデータを読み込んでから使用してください", size=12, color=ft.Colors.GREY_600)

        # 説明変数側チェックボックス
        ind_checkboxes_col = ft.Column(spacing=2)
        # 目的変数側チェックボックス
        tgt_checkboxes_col = ft.Column(spacing=2)

        normalize_switch = ft.Switch(label="0-1正規化（スケール統一）", value=True)
        # 右軸選択チェックボックス（変数リスト更新時に構築される）
        right_axis_checkboxes_col = ft.Column(spacing=2)

        refresh_button = ft.ElevatedButton(
            "変数リストを更新",
            icon=ft.Icons.REFRESH,
            on_click=lambda e: _refresh_compare_lists(),
        )
        plot_compare_button = ft.ElevatedButton(
            "比較プロット実行",
            icon=ft.Icons.SHOW_CHART,
            on_click=lambda e: _run_compare_plot(),
        )

        def _refresh_compare_lists():
            """共有データから変数チェックボックスを再構築する"""
            ind_df = shared["ind_df"]
            ind_c2n = shared["ind_c2n"]
            tgt_df = shared["tgt_df"]
            tgt_c2n = shared["tgt_c2n"]

            if ind_df is None or ind_df.empty:
                compare_status.value = "説明変数データが読み込まれていません。①説明変数データタブでデータを選択してください。"
                compare_status.color = ft.Colors.ORANGE_700
                page.update()
                return

            # 説明変数チェックボックス
            ind_cbs = [
                ft.Checkbox(label=ind_c2n.get(col, col), data=col, value=False, expand=True)
                for col in ind_df.columns
            ]
            rows = []
            for i in range(0, len(ind_cbs), 3):
                row_items = ind_cbs[i:i + 3]
                while len(row_items) < 3:
                    row_items.append(ft.Container(expand=True))
                rows.append(ft.Row(controls=row_items, spacing=4))
            ind_checkboxes_col.controls = rows

            # 目的変数チェックボックス
            if tgt_df is not None and not tgt_df.empty:
                tgt_cbs = [
                    ft.Checkbox(label=tgt_c2n.get(col, col), data=col, value=True, expand=True)
                    for col in tgt_df.columns
                ]
                tgt_rows = []
                for i in range(0, len(tgt_cbs), 3):
                    row_items = tgt_cbs[i:i + 3]
                    while len(row_items) < 3:
                        row_items.append(ft.Container(expand=True))
                    tgt_rows.append(ft.Row(controls=row_items, spacing=4))
                tgt_checkboxes_col.controls = tgt_rows
            else:
                tgt_checkboxes_col.controls = [
                    ft.Text("目的変数データが読み込まれていません。②目的変数データタブでデータを選択してください。", size=11, color=ft.Colors.ORANGE_600)
                ]

            # 右軸チェックボックス（全変数、デフォルト未選択）
            all_vars = [
                (ind_c2n.get(col, col), col) for col in ind_df.columns
            ]
            if tgt_df is not None and not tgt_df.empty:
                all_vars += [(tgt_c2n.get(col, col), col) for col in tgt_df.columns]
            right_cbs = [
                ft.Checkbox(label=name, data=col, value=False, expand=True)
                for name, col in all_vars
            ]
            ra_rows = []
            for i in range(0, len(right_cbs), 3):
                row_items = right_cbs[i:i + 3]
                while len(row_items) < 3:
                    row_items.append(ft.Container(expand=True))
                ra_rows.append(ft.Row(controls=row_items, spacing=4))
            right_axis_checkboxes_col.controls = ra_rows

            compare_status.value = "変数を選択して「比較プロット実行」を押してください"
            compare_status.color = ft.Colors.GREEN_700
            page.update()

        def _run_compare_plot():
            """選択した説明変数・目的変数を重ねてプロットする"""
            ind_df = shared["ind_df"]
            ind_c2n = shared["ind_c2n"]
            tgt_df = shared["tgt_df"]
            tgt_c2n = shared["tgt_c2n"]

            # 説明変数の選択
            ind_selected = [
                cb.data for row in ind_checkboxes_col.controls
                for cb in row.controls if isinstance(cb, ft.Checkbox) and cb.value
            ]
            # 目的変数の選択
            tgt_selected = [
                cb.data for row in tgt_checkboxes_col.controls
                for cb in row.controls if isinstance(cb, ft.Checkbox) and cb.value
            ]

            all_selected = ind_selected + tgt_selected
            if not all_selected:
                compare_status.value = "比較する変数を選択してください"
                compare_status.color = ft.Colors.ORANGE_700
                page.update()
                return

            compare_plot_container.controls.clear()
            compare_status.value = "プロット生成中..."
            compare_status.color = ft.Colors.GREY_600
            page.update()

            try:
                # 系列データと名前を組み立てる
                series_list = []
                labels = []
                combined_c2n = {**ind_c2n, **tgt_c2n}

                for col in ind_selected:
                    if ind_df is not None and col in ind_df.columns:
                        series_list.append(ind_df[col].dropna())
                        labels.append(combined_c2n.get(col, col))

                for col in tgt_selected:
                    if tgt_df is not None and col in tgt_df.columns:
                        series_list.append(tgt_df[col].dropna())
                        labels.append(combined_c2n.get(col, col))

                if not series_list:
                    compare_status.value = "有効なデータがありません"
                    compare_status.color = ft.Colors.ORANGE_700
                    page.update()
                    return

                right_axis_selected = [
                    combined_c2n.get(cb.data, cb.data)
                    for row in right_axis_checkboxes_col.controls
                    for cb in row.controls if isinstance(cb, ft.Checkbox) and cb.value
                ]
                img = plot_compare_series(
                    series_list=series_list,
                    labels=labels,
                    normalize=normalize_switch.value,
                    right_axis_labels=right_axis_selected if right_axis_selected else None,
                    figsize=(12, 6),
                )
                compare_plot_container.controls.append(
                    ft.Image(src="data:image/png;base64," + img, fit=ft.BoxFit.CONTAIN)
                )
                compare_status.value = f"{len(series_list)}系列をプロットしました"
                compare_status.color = ft.Colors.GREEN_700
            except Exception as ex:
                compare_status.value = f"プロットエラー: {ex}"
                compare_status.color = ft.Colors.RED_700

            page.update()

        return ft.Column(
            controls=[
                ft.Text("比較プロット（説明変数 × 目的変数）", size=20, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Text(
                        "①・②タブでデータを読み込んだ後、「変数リストを更新」を押してください。"
                        "説明変数と目的変数を選択して重ね合わせプロットができます。",
                        size=12, color=ft.Colors.BLUE_800,
                    ),
                    bgcolor=ft.Colors.BLUE_50, border_radius=6,
                    padding=ft.padding.symmetric(horizontal=12, vertical=8),
                ),
                ft.Row([refresh_button, normalize_switch], spacing=16),
                compare_status,
                ft.Divider(),
                ft.Text("説明変数（チェックして選択）", size=14, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Column(controls=[ind_checkboxes_col], scroll=ft.ScrollMode.AUTO),
                    height=150, border=ft.border.all(1, ft.Colors.GREY_300), padding=8,
                ),
                ft.Text("目的変数（チェックして選択）", size=14, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Column(controls=[tgt_checkboxes_col], scroll=ft.ScrollMode.AUTO),
                    height=100, border=ft.border.all(1, ft.Colors.GREY_300), padding=8,
                ),
                ft.Text("右軸に割り当てる変数（未選択なら1軸表示）", size=14, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=ft.Column(controls=[right_axis_checkboxes_col], scroll=ft.ScrollMode.AUTO),
                    height=100, border=ft.border.all(1, ft.Colors.GREY_300), padding=8,
                ),
                plot_compare_button,
                compare_plot_container,
            ],
            spacing=10,
        )

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
    # サブタブ: ボタン切替（TabBarは親Tabsにイベントがバブルするため不使用）
    indicator_tab_content = _build_indicator_tab()
    target_tab_content = _build_target_tab()
    compare_tab_content = _build_compare_tab()

    sub_tab_body = ft.Container(content=indicator_tab_content, padding=10)

    btn_indicator = ft.ElevatedButton("① 説明変数データ", disabled=True)
    btn_target = ft.OutlinedButton("② 目的変数データ")
    btn_compare = ft.OutlinedButton("③ 比較プロット")

    def switch_to_indicator(e):
        sub_tab_body.content = indicator_tab_content
        btn_indicator.disabled = True
        btn_target.disabled = False
        btn_compare.disabled = False
        page.update()

    def switch_to_target(e):
        sub_tab_body.content = target_tab_content
        btn_indicator.disabled = False
        btn_target.disabled = True
        btn_compare.disabled = False
        page.update()

    def switch_to_compare(e):
        sub_tab_body.content = compare_tab_content
        btn_indicator.disabled = False
        btn_target.disabled = False
        btn_compare.disabled = True
        page.update()

    btn_indicator.on_click = switch_to_indicator
    btn_target.on_click = switch_to_target
    btn_compare.on_click = switch_to_compare

    layout = ft.Column(
        controls=[
            _help,
            ft.Text("データ閲覧・管理", size=24, weight=ft.FontWeight.BOLD),
            ft.Row([btn_indicator, btn_target, btn_compare], spacing=8),
            sub_tab_body,
        ],
        spacing=10,
    )

    return layout
