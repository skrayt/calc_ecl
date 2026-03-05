"""データソース選択UIコンポーネント

分析ページ共通で使用する、データセット・frequency選択UI。
説明変数と目的変数のfrequencyを合わせてデータを取得する。
"""
import flet as ft
import pandas as pd

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


class DataSourceSelector:
    """データソース選択UIコンポーネント

    説明変数データセット・frequency、目的変数データセット・frequency・セグメントを
    選択し、両者のDataFrameを取得する。

    Parameters
    ----------
    page : ft.Page
        Fletページ
    on_data_loaded : callable or None
        データ読み込み完了時のコールバック。
        引数: (indicator_df, target_df, code_to_name, target_code_to_name)
    """

    def __init__(self, page: ft.Page, on_data_loaded=None):
        self.page = page
        self.on_data_loaded = on_data_loaded

        # 現在のデータ
        self.indicator_df: pd.DataFrame | None = None
        self.target_df: pd.DataFrame | None = None
        self.code_to_name: dict[str, str] = {}
        self.target_code_to_name: dict[str, str] = {}

        # 説明変数UI
        self._ind_dataset_dd = ft.Dropdown(
            label="説明変数データセット", width=350,
            on_select=lambda e: self._on_ind_dataset_change(e),
        )
        self._ind_freq_dd = ft.Dropdown(
            label="frequency", width=180,
            on_select=lambda e: self._on_ind_freq_change(e),
        )

        # 目的変数UI
        self._tgt_dataset_dd = ft.Dropdown(
            label="目的変数データセット", width=350,
            on_select=lambda e: self._on_tgt_dataset_change(e),
        )
        self._tgt_freq_dd = ft.Dropdown(
            label="frequency", width=180,
            on_select=lambda e: self._on_tgt_freq_change(e),
        )
        self._tgt_segment_dd = ft.Dropdown(
            label="セグメント", width=180,
            on_select=lambda e: self._on_tgt_segment_change(e),
        )

        self._status_text = ft.Text("", size=11)

        # 初期化
        self._load_initial_data()

    def _load_initial_data(self):
        """初期データの読み込み"""
        try:
            # 説明変数データセット一覧
            ind_datasets = list_datasets()
            self._ind_dataset_dd.options = [
                ft.dropdown.Option(
                    key=str(row["dataset_id"]),
                    text=f"ID:{row['dataset_id']} - {row['dataset_name']}",
                )
                for _, row in ind_datasets.iterrows()
            ]

            # 目的変数データセット一覧
            tgt_datasets = list_target_datasets()
            self._tgt_dataset_dd.options = [
                ft.dropdown.Option(
                    key=str(row["target_dataset_id"]),
                    text=f"ID:{row['target_dataset_id']} - {row['dataset_name']}",
                )
                for _, row in tgt_datasets.iterrows()
            ]

            # セッションストアから初期値を復元
            stored_ds_id = self.page.session.store.get("dataset_id")
            stored_tgt_ds_id = self.page.session.store.get("target_dataset_id")

            # 説明変数の初期選択
            if not ind_datasets.empty:
                if stored_ds_id and str(stored_ds_id) in [o.key for o in self._ind_dataset_dd.options]:
                    self._ind_dataset_dd.value = str(stored_ds_id)
                else:
                    self._ind_dataset_dd.value = str(ind_datasets.iloc[0]["dataset_id"])
                self._load_ind_frequencies(int(self._ind_dataset_dd.value))

            # 目的変数の初期選択
            if not tgt_datasets.empty:
                if stored_tgt_ds_id and str(stored_tgt_ds_id) in [o.key for o in self._tgt_dataset_dd.options]:
                    self._tgt_dataset_dd.value = str(stored_tgt_ds_id)
                else:
                    self._tgt_dataset_dd.value = str(tgt_datasets.iloc[0]["target_dataset_id"])
                self._load_tgt_frequencies(int(self._tgt_dataset_dd.value))
            else:
                self._status_text.value = "目的変数データセットがありません。データ閲覧ページでインポートしてください。"
                self._status_text.color = ft.Colors.ORANGE_700

        except Exception as ex:
            self._status_text.value = f"データ取得エラー: {ex}"
            self._status_text.color = ft.Colors.RED_700

    # =========================================================
    # 説明変数のイベントハンドラ
    # =========================================================
    def _on_ind_dataset_change(self, e):
        self._load_ind_frequencies(int(e.control.value))

    def _load_ind_frequencies(self, dataset_id):
        try:
            freqs = list_frequencies(dataset_id)
            self._ind_freq_dd.options = [ft.dropdown.Option(f) for f in freqs]

            # 目的変数のfrequencyと合わせる
            tgt_freq = self._tgt_freq_dd.value
            if tgt_freq and tgt_freq in freqs:
                self._ind_freq_dd.value = tgt_freq
            elif freqs:
                self._ind_freq_dd.value = freqs[0]

            self._load_data()
            self.page.update()
        except Exception as ex:
            self._status_text.value = f"frequency取得エラー: {ex}"
            self.page.update()

    def _on_ind_freq_change(self, e):
        self._load_data()
        self.page.update()

    # =========================================================
    # 目的変数のイベントハンドラ
    # =========================================================
    def _on_tgt_dataset_change(self, e):
        self._load_tgt_frequencies(int(e.control.value))

    def _load_tgt_frequencies(self, target_dataset_id):
        try:
            freqs = list_target_frequencies(target_dataset_id)
            self._tgt_freq_dd.options = [ft.dropdown.Option(f) for f in freqs]
            if freqs:
                self._tgt_freq_dd.value = freqs[0]
                self._load_tgt_segments(target_dataset_id, freqs[0])

                # 説明変数のfrequencyも自動で合わせる
                ind_freqs = [o.key for o in self._ind_freq_dd.options]
                if freqs[0] in ind_freqs:
                    self._ind_freq_dd.value = freqs[0]

            self._load_data()
            self.page.update()
        except Exception as ex:
            self._status_text.value = f"frequency取得エラー: {ex}"
            self.page.update()

    def _on_tgt_freq_change(self, e):
        tgt_ds_id = int(self._tgt_dataset_dd.value)
        self._load_tgt_segments(tgt_ds_id, e.control.value)

        # 説明変数のfrequencyも自動で合わせる
        ind_freqs = [o.key for o in self._ind_freq_dd.options]
        if e.control.value in ind_freqs:
            self._ind_freq_dd.value = e.control.value

        self._load_data()
        self.page.update()

    def _load_tgt_segments(self, target_dataset_id, frequency):
        try:
            segments = list_target_segments(target_dataset_id, frequency)
            self._tgt_segment_dd.options = [
                ft.dropdown.Option(
                    key=s["segment_code"],
                    text=f"{s['segment_name']} ({s['segment_code']})",
                )
                for s in segments
            ]
            if segments:
                self._tgt_segment_dd.value = segments[0]["segment_code"]
        except Exception as ex:
            self._status_text.value = f"セグメント取得エラー: {ex}"

    def _on_tgt_segment_change(self, e):
        self._load_data()
        self.page.update()

    # =========================================================
    # データ読み込み
    # =========================================================
    def _load_data(self):
        """説明変数・目的変数データを読み込み、コールバックを呼ぶ"""
        try:
            # 説明変数
            ind_ds_id = self._ind_dataset_dd.value
            ind_freq = self._ind_freq_dd.value
            if ind_ds_id and ind_freq:
                self.indicator_df = load_indicators(int(ind_ds_id), ind_freq)
                if not self.indicator_df.empty:
                    defs = get_indicator_definitions(self.indicator_df.columns.tolist())
                    self.code_to_name = dict(zip(defs["indicator_code"], defs["indicator_name"]))
            else:
                self.indicator_df = pd.DataFrame()

            # 目的変数
            tgt_ds_id = self._tgt_dataset_dd.value
            tgt_freq = self._tgt_freq_dd.value
            tgt_seg = self._tgt_segment_dd.value
            if tgt_ds_id and tgt_freq and tgt_seg:
                self.target_df = load_targets(int(tgt_ds_id), tgt_freq, tgt_seg)
                if not self.target_df.empty:
                    t_defs = get_target_definitions(self.target_df.columns.tolist())
                    self.target_code_to_name = dict(zip(t_defs["target_code"], t_defs["target_name"]))
            else:
                self.target_df = pd.DataFrame()

            # ステータス表示
            ind_info = ""
            tgt_info = ""
            if self.indicator_df is not None and not self.indicator_df.empty:
                ind_info = f"説明変数: {ind_freq} {len(self.indicator_df)}行"
            if self.target_df is not None and not self.target_df.empty:
                tgt_info = f"目的変数: {tgt_freq} {len(self.target_df)}行"

            # frequency不一致チェック
            if ind_freq and tgt_freq and ind_freq != tgt_freq:
                self._status_text.value = f"{ind_info} | {tgt_info} | ⚠ frequencyが異なります！マージ時にエラーになります"
                self._status_text.color = ft.Colors.ORANGE_700
            else:
                self._status_text.value = f"{ind_info} | {tgt_info}"
                self._status_text.color = ft.Colors.GREEN_700

            # コールバック
            if self.on_data_loaded:
                self.on_data_loaded(
                    self.indicator_df,
                    self.target_df,
                    self.code_to_name,
                    self.target_code_to_name,
                )

        except Exception as ex:
            self._status_text.value = f"データ読み込みエラー: {ex}"
            self._status_text.color = ft.Colors.RED_700

    def get_ui(self) -> ft.Control:
        """UIコンポーネントを返す"""
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text("データソース選択", size=14, weight=ft.FontWeight.BOLD),
                    ft.Row([self._ind_dataset_dd, self._ind_freq_dd]),
                    ft.Row([self._tgt_dataset_dd, self._tgt_freq_dd, self._tgt_segment_dd]),
                    self._status_text,
                ],
                spacing=6,
            ),
            padding=10,
            border=ft.border.all(1, ft.Colors.BLUE_100),
            border_radius=8,
            bgcolor=ft.Colors.BLUE_50,
        )
