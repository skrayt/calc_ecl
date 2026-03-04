"""変数選択UIコンポーネント

目的変数・説明変数の選択、変換方法・標準化設定を行う
共通UIパーツ。

移植元: Craft_RegressionAnalysis/components/variable_selector.py
"""
import flet as ft

from src.analysis.data_transform import TRANSFORM_METHODS


class VariableSelector:
    """変数選択UIコンポーネント

    各変数行のレイアウト:
    [チェックボックス] [変換ドロップダウン] [標準化トグル] [変数名ラベル]

    Parameters
    ----------
    page : ft.Page
        Fletページ
    columns : list[str]
        選択可能なカラム名リスト
    on_change : callable or None
        変数選択が変更された時のコールバック
    show_target : bool
        目的変数ドロップダウンを表示するかどうか（デフォルト: True）
    show_transform : bool
        変換設定を表示するかどうか（デフォルト: True）
    initial_target : str or None
        初期選択する目的変数
    """

    def __init__(
        self,
        page: ft.Page,
        columns: list[str],
        on_change=None,
        show_target: bool = True,
        show_transform: bool = True,
        initial_target: str | None = None,
    ):
        self.page = page
        self.columns = list(columns)
        self.on_change = on_change
        self.show_target = show_target
        self.show_transform = show_transform

        # 状態管理
        self._selected: dict[str, bool] = {c: False for c in self.columns}
        self._transforms: dict[str, str] = {c: "none" for c in self.columns}
        self._standardize: dict[str, bool] = {c: False for c in self.columns}

        # UIコンポーネント初期化
        self._target_dropdown = ft.Dropdown(
            label="目的変数",
            options=[ft.dropdown.Option(c) for c in self.columns],
            value=initial_target or (self.columns[0] if self.columns else None),
            on_change=self._on_target_change,
            width=300,
        )

        self._feature_column = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=2)
        self._build_feature_controls()

    def _build_feature_controls(self):
        """説明変数のUIコントロールを構築する"""
        self._feature_column.controls.clear()

        target = self._target_dropdown.value

        for col in self.columns:
            if col == target:
                continue

            row_controls = []

            # チェックボックス
            cb = ft.Checkbox(
                value=self._selected.get(col, False),
                on_change=lambda e, c=col: self._on_checkbox_change(e, c),
            )
            row_controls.append(cb)

            # 変数名ラベル
            label = ft.Text(col, size=13, width=200)
            row_controls.append(label)

            if self.show_transform:
                # 変換ドロップダウン
                transform_dd = ft.Dropdown(
                    options=[
                        ft.dropdown.Option(key=k, text=v)
                        for k, v in TRANSFORM_METHODS.items()
                    ],
                    value=self._transforms.get(col, "none"),
                    on_change=lambda e, c=col: self._on_transform_change(e, c),
                    width=200,
                    dense=True,
                    text_size=12,
                )
                row_controls.append(transform_dd)

                # 標準化トグル
                std_switch = ft.Switch(
                    label="標準化",
                    value=self._standardize.get(col, False),
                    on_change=lambda e, c=col: self._on_standardize_change(e, c),
                    label_style=ft.TextStyle(size=11),
                )
                row_controls.append(std_switch)

            self._feature_column.controls.append(
                ft.Row(controls=row_controls, spacing=10, alignment=ft.MainAxisAlignment.START)
            )

    def _on_target_change(self, e):
        """目的変数の変更ハンドラ"""
        print(f"DEBUG: 目的変数変更: {e.control.value}")
        self._build_feature_controls()
        if self.on_change:
            self.on_change()
        self.page.update()

    def _on_checkbox_change(self, e, col: str):
        """チェックボックスの変更ハンドラ"""
        self._selected[col] = e.control.value
        if self.on_change:
            self.on_change()

    def _on_transform_change(self, e, col: str):
        """変換タイプの変更ハンドラ"""
        self._transforms[col] = e.control.value

    def _on_standardize_change(self, e, col: str):
        """標準化スイッチの変更ハンドラ"""
        self._standardize[col] = e.control.value

    def get_target(self) -> str | None:
        """選択された目的変数を返す"""
        if not self.show_target:
            return None
        return self._target_dropdown.value

    def get_selected_features(self) -> list[str]:
        """選択された説明変数のリストを返す"""
        target = self.get_target()
        return [
            c for c in self.columns
            if self._selected.get(c, False) and c != target
        ]

    def get_variable_settings(self) -> dict[str, dict]:
        """各変数の設定を返す

        Returns
        -------
        dict
            {col_name: {"transform": "log", "standardize": True}, ...}
        """
        settings = {}
        for col in self.get_selected_features():
            settings[col] = {
                "transform": self._transforms.get(col, "none"),
                "standardize": self._standardize.get(col, False),
            }
        # 目的変数の設定も含める
        target = self.get_target()
        if target:
            settings[target] = {
                "transform": self._transforms.get(target, "none"),
                "standardize": self._standardize.get(target, False),
            }
        return settings

    def get_ui(self) -> ft.Control:
        """UIコンポーネントを返す

        Returns
        -------
        ft.Control
            変数選択UI全体のコントロール
        """
        controls = []

        if self.show_target:
            controls.append(self._target_dropdown)
            controls.append(ft.Divider(height=1))

        controls.append(
            ft.Text("説明変数の選択", size=14, weight=ft.FontWeight.BOLD)
        )

        if self.show_transform:
            controls.append(
                ft.Text(
                    "各変数のチェック・変換方法・標準化を設定してください",
                    size=11, color=ft.Colors.GREY_600,
                )
            )

        controls.append(self._feature_column)

        return ft.Container(
            content=ft.Column(controls=controls, spacing=8),
            padding=10,
            border=ft.border.all(1, ft.Colors.GREY_300),
            border_radius=8,
        )
