"""将来シナリオページ

将来シナリオ（ベース/楽観/悲観）の作成と予測値のDB保存を行う。

※ Phase 3-8で本格実装予定。現時点ではプレースホルダ。
"""
import flet as ft
from components.help_panel import build_help_panel


def forecast_page(page: ft.Page) -> ft.Control:
    """将来シナリオタブのUIを構築する"""
    print("DEBUG: 将来シナリオページ構築開始")

    _help = build_help_panel(
        title="⑦ 将来シナリオ（実装予定）",
        purpose="回帰・ARIMAモデルの予測結果をもとに、ベース/楽観/悲観シナリオを作成してECLを算出します。",
        steps=[
            "（実装後）シナリオを選択し、各シナリオの重みを設定する",
            "（実装後）加重平均によるECL算出を実行する",
            "（実装後）結果をDBに保存する",
        ],
        outputs=[
            "（実装後）シナリオ別の予測値グラフ",
            "（実装後）加重平均ECL算出結果",
        ],
    )
    return ft.Column(
        controls=[
            _help,
            ft.Text("将来シナリオ", size=24, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.CONSTRUCTION, size=64, color=ft.Colors.GREY_400),
                    ft.Text(
                        "このページは今後実装予定です。",
                        size=16, color=ft.Colors.GREY_600,
                    ),
                    ft.Text(
                        "ベース/楽観/悲観シナリオの作成、加重平均によるECL算出、DB保存機能を提供します。",
                        size=13, color=ft.Colors.GREY_500,
                    ),
                    ft.Text(
                        "実装には src/db_operations.py（モデル結果のDB保存）が前提となります。",
                        size=13, color=ft.Colors.GREY_500,
                    ),
                ],
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
                padding=40,
                alignment=ft.Alignment(0, 0),
            ),
        ],
        spacing=10,
        expand=True,
    )
