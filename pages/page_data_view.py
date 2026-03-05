"""データ閲覧ページ

データセット選択・指標一覧表示・時系列グラフ表示、および新規データインポートを行う。
"""
import flet as ft
import pandas as pd
from datetime import date
import threading
import time

from src.data.indicator_loader import (
    list_datasets,
    list_frequencies,
    load_indicators,
    get_indicator_definitions,
)
from components.plot_utils import plot_single_series
from src.import_indicators import import_csv_gui
from components.help_panel import build_help_panel


def data_view_page(page: ft.Page) -> ft.Control:
    """データ閲覧タブのUIを構築する"""
    print("DEBUG: データ閲覧ページ構築開始")

    # == 状態変数 ==
    current_df: pd.DataFrame | None = None
    code_to_name: dict[str, str] = {}  # indicator_code → indicator_name（日本語表示用）
    import_result_data = None
    prompt_result = None
    prompt_event = threading.Event()

    # == UI部品 ==
    dataset_dropdown = ft.Dropdown(
        label="データセット",
        width=400,
        on_select=lambda e: on_dataset_change(e),
    )
    freq_dropdown = ft.Dropdown(
        label="frequency",
        width=200,
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

    # -- インポート関連 UI --
    progress_bar = ft.ProgressBar(width=400, color="blue", visible=False)
    import_status = ft.Text("", size=12)
    
    # 指標コード入力ダイアログ
    new_code_input = ft.TextField(label="指標コード (snake_case)")
    col_name_text = ft.Text("", weight="bold")
    auto_info_text = ft.Text("", size=11)
    
    def close_dlg(e):
        nonlocal prompt_result
        prompt_result = e.control.data # "skip" or "add" or "ignore"
        prompt_event.set()
        mapping_dialog.open = False
        page.update()

    mapping_dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text("未知のカラムが見つかりました"),
        content=ft.Column([
            col_name_text,
            auto_info_text,
            new_code_input,
        ], tight=True, spacing=10),
        actions=[
            ft.TextButton("追加", on_click=close_dlg, data="add"),
            ft.TextButton("スキップ登録", on_click=close_dlg, data="skip"),
            ft.TextButton("今回は無視", on_click=close_dlg, data="ignore"),
        ],
    )

    def prompt_callback_gui(col_name, auto_info):
        """未知カラムが見つかったときにGUIダイアログを表示する"""
        nonlocal prompt_result
        col_name_text.value = f"カラム名: {col_name}"
        auto_info_text.value = (
            f"自動検出結果:\n"
            f"  名前: {auto_info['name']}\n"
            f"  基準年: {auto_info['base_year'] or 'なし'}\n"
            f"  単位: {auto_info['unit'] or 'なし'}\n"
            f"  粒度: {auto_info['frequency']}"
        )
        new_code_input.value = "" # クリア
        
        prompt_event.clear()
        mapping_dialog.open = True
        page.update()
        
        # ユーザーの入力を待機
        prompt_event.wait()
        
        if prompt_result == "add":
            return {"action": "add", "code": new_code_input.value}
        elif prompt_result == "skip":
            return {"action": "skip"}
        else:
            return None

    def on_import_result(res):
        """インポート完了時の処理"""
        progress_bar.visible = False
        if "error" in res:
            import_status.value = f"エラー: {res['error']}"
            import_status.color = ft.Colors.RED_700
        else:
            import_status.value = f"インポート完了: {res['inserted']}件登録 (ID: {res['dataset_id']})"
            import_status.color = ft.Colors.GREEN_700
            load_datasets() # リスト更新
        page.update()

    def start_import_thread(file_path):
        """インポートを別スレッドで実行"""
        def run():
            try:
                def prog(curr, total):
                    progress_bar.value = curr / total
                    import_status.value = f"インポート中... {curr}/{total}"
                    page.update()

                res = import_csv_gui(
                    file_path, 
                    date.today(), 
                    progress_callback=prog,
                    prompt_callback=prompt_callback_gui
                )
                on_import_result(res)
            except Exception as ex:
                on_import_result({"error": str(ex)})

        threading.Thread(target=run, daemon=True).start()

    async def pick_csv(e):
        files = await file_picker.pick_files(allow_multiple=False, allowed_extensions=["csv"])
        if files:
            file_path = files[0].path
            print(f"DEBUG: ファイル選択: {file_path}")
            progress_bar.visible = True
            progress_bar.value = 0
            import_status.value = "準備中..."
            page.update()
            start_import_thread(file_path)

    file_picker = ft.FilePicker()
    page.overlay.append(mapping_dialog)

    # -- データ読み込み・表示ロジック --
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
                _load_frequencies(int(dataset_dropdown.value))
            page.update()
        except Exception as ex:
            print(f"DEBUG: データセット取得エラー: {ex}")
            status_text.value = f"データセット取得エラー: {ex}"
            status_text.color = ft.Colors.RED_700
            page.update()

    def on_dataset_change(e):
        ds_id = int(e.control.value)
        _load_frequencies(ds_id)

    def _load_frequencies(dataset_id: int):
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

    def _load_data(dataset_id: int, frequency: str):
        nonlocal current_df, code_to_name
        try:
            from src.data.indicator_loader import load_indicators
            df = load_indicators(dataset_id, frequency)
            current_df = df
            # indicator_code → indicator_name のマッピングを取得
            if not df.empty:
                defs = get_indicator_definitions(df.columns.tolist())
                code_to_name = dict(zip(defs["indicator_code"], defs["indicator_name"]))
            page.session.store.set("df", df)

            status_text.value = (
                f"ID: {dataset_id} | {frequency} | "
                f"{df.index.min().date()}〜{df.index.max().date()} | {len(df)}行"
            )
            status_text.color = ft.Colors.GREEN_700
            
            _update_data_table(df)
            _update_indicator_checkboxes(df.columns.tolist())
            plot_button.disabled = False
            plot_container.controls.clear()
            page.update()
        except Exception as ex:
            status_text.value = f"ロードエラー: {ex}"
            status_text.color = ft.Colors.RED_700
            page.update()

    def _update_data_table(df: pd.DataFrame):
        data_table_container.controls.clear()
        display_df = df.head(20)

        COL_DATE_W = 90
        COL_W = 130  # 各指標列の固定幅

        HEADER_H = 50  # ヘッダー固定高さ（2行分を想定）
        DATA_H = 28    # データ行固定高さ

        def _header_cell(text, width):
            return ft.Container(
                content=ft.Text(text, size=10, weight=ft.FontWeight.BOLD),
                width=width,
                height=HEADER_H,
                padding=ft.padding.symmetric(horizontal=6, vertical=4),
                border=ft.border.all(1, ft.Colors.GREY_300),
                alignment=ft.alignment.Alignment(-1, 0),
            )

        def _cell(text, width):
            return ft.Container(
                content=ft.Text(text, size=10),
                width=width,
                height=DATA_H,
                padding=ft.padding.symmetric(horizontal=6, vertical=4),
                border=ft.border.all(1, ft.Colors.GREY_300),
                alignment=ft.alignment.Alignment(-1, 0),
            )

        # ヘッダー行
        header = ft.Row(
            controls=(
                [_header_cell("日付", COL_DATE_W)]
                + [_header_cell(code_to_name.get(c, c), COL_W) for c in display_df.columns]
            ),
            spacing=0,
        )

        # 列ごとに整数列かどうかを判定（全非NaN値が整数なら整数列）
        def _is_int_col(series):
            valid = series.dropna()
            return len(valid) > 0 and (valid == valid.round()).all()

        is_int = {c: _is_int_col(display_df[c]) for c in display_df.columns}

        def _fmt(val, col):
            if pd.isna(val):
                return "-"
            return f"{int(val):,}" if is_int[col] else f"{val:,.2f}"

        # データ行
        data_rows = []
        for idx, row in display_df.iterrows():
            data_rows.append(ft.Row(
                controls=(
                    [_cell(str(idx.date()), COL_DATE_W)]
                    + [_cell(_fmt(row[c], c), COL_W) for c in display_df.columns]
                ),
                spacing=0,
            ))

        table_col = ft.Column(controls=[header] + data_rows, spacing=0)
        data_table_container.controls.append(
            ft.Row(controls=[table_col], scroll=ft.ScrollMode.AUTO)
        )

    def _update_indicator_checkboxes(columns: list[str]):
        indicator_checkboxes.controls = [
            ft.Checkbox(label=code_to_name.get(col, col), data=col, value=True)
            for col in columns
        ]

    def on_plot_click():
        selected_cols = [cb.data for cb in indicator_checkboxes.controls if cb.value]
        if not selected_cols:
            return
        plot_container.controls.clear()

        N_COLS = 3
        row_controls = []
        for i, col in enumerate(selected_cols):
            label = code_to_name.get(col, col)
            try:
                img = plot_single_series(current_df, col, label=label, figsize=(5, 3))
                cell = ft.Image(src="data:image/png;base64," + img, fit=ft.BoxFit.CONTAIN, expand=True)
            except Exception as ex:
                cell = ft.Text(f"{label}: エラー: {ex}", color=ft.Colors.RED_700, expand=True)
            row_controls.append(cell)

            if len(row_controls) == N_COLS:
                plot_container.controls.append(ft.Row(controls=row_controls, spacing=4))
                row_controls = []

        # 端数（列が埋まらない行）
        if row_controls:
            # 空セルで埋めてレイアウトを揃える
            while len(row_controls) < N_COLS:
                row_controls.append(ft.Container(expand=True))
            plot_container.controls.append(ft.Row(controls=row_controls, spacing=4))

        page.update()

    # == レイアウト ==
    _help = build_help_panel(
        title="① データ閲覧・管理",
        purpose="DBに格納されたマクロ経済指標データを閲覧・グラフ表示し、新しいCSVファイルをインポートします。まず最初にこのページでデータを確認し、分析対象のデータセットを把握してください。",
        steps=[
            "データセットドロップダウンで対象データセットを選択する",
            "frequencyドロップダウンで粒度（月次・四半期・年度等）を選択する",
            "チェックボックスで表示したい指標を選び、「選択した指標をプロット」を押す",
            "グラフで欠損・外れ値・トレンドの有無を目視確認する（分析前の必須ステップ）",
            "新しいデータを取り込む場合は「新規CSVインポート」でCSVファイルを選択する",
        ],
        outputs=[
            "データセットの期間・行数・ID（ステータス表示）",
            "最新データの先頭20行（日付 + 指標値のテーブル）",
            "選択した指標の時系列グラフ（指標ごとに個別の図を表示）",
            "インポート進捗バーと完了メッセージ",
        ],
        indicators=[
            {
                "name": "分析前のデータ確認チェックリスト",
                "criteria": [
                    {"level": "良好",  "range": "欠損値なし",       "meaning": "テーブルに空白・NaNがないことを確認。欠損があると分析でエラーになる場合がある"},
                    {"level": "注意",  "range": "外れ値を目視確認", "meaning": "グラフで突出した値があれば、統計的ミス入力か実際の異常値かを業務的に判断する"},
                    {"level": "情報",  "range": "トレンドの確認",   "meaning": "右上がり/右下がりのトレンドがある変数は非定常の可能性。ARIMA分析で確認推奨"},
                    {"level": "情報",  "range": "frequency（粒度）の統一", "meaning": "月次・四半期・年度で粒度が混在していると相関分析で誤差が生じる。同一粒度で揃えること"},
                ],
                "note": "CSVインポート後はデータセットIDが新たに発行される。同じ指標でも複数バージョンが存在する場合は最新のものを使用すること",
            },
        ],
    )
    layout = ft.Column(
        controls=[
            _help,
            ft.Row([
                ft.Text("データ閲覧・管理", size=24, weight=ft.FontWeight.BOLD),
                ft.ElevatedButton(
                    "新規CSVインポート",
                    icon=ft.Icons.UPLOAD_FILE,
                    on_click=pick_csv
                ),
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

    load_datasets()
    return layout
