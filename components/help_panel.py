"""ヘルプパネルコンポーネント

各ページの上部に折りたたみ式のヘルプパネルを表示する。
"""
import flet as ft


def build_help_panel(
    title: str,
    purpose: str,
    steps: list[str],
    outputs: list[str],
) -> ft.Control:
    """折りたたみ式ヘルプパネルを構築する。

    Args:
        title: ページタイトル
        purpose: このページの目的（1〜2文）
        steps: 操作手順のリスト
        outputs: 表示される結果・出力のリスト

    Returns:
        折りたたみ可能なヘルプパネル
    """
    is_expanded = [False]

    step_items = [
        ft.Row(
            controls=[
                ft.Text(f"  {i+1}. ", size=13, color=ft.Colors.BLUE_700, weight=ft.FontWeight.BOLD),
                ft.Text(step, size=13, expand=True),
            ],
            wrap=True,
        )
        for i, step in enumerate(steps)
    ]

    output_items = [
        ft.Row(
            controls=[
                ft.Text("  • ", size=13, color=ft.Colors.GREEN_700, weight=ft.FontWeight.BOLD),
                ft.Text(output, size=13, expand=True),
            ],
            wrap=True,
        )
        for output in outputs
    ]

    content = ft.Column(
        controls=[
            ft.Container(
                content=ft.Text(purpose, size=13, color=ft.Colors.GREY_800),
                padding=ft.padding.only(bottom=8),
            ),
            ft.Row(
                controls=[
                    ft.Column(
                        controls=[
                            ft.Text("操作手順", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                            *step_items,
                        ],
                        expand=True,
                        spacing=4,
                    ),
                    ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                    ft.Column(
                        controls=[
                            ft.Text("表示される結果", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                            *output_items,
                        ],
                        expand=True,
                        spacing=4,
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ],
        spacing=4,
        visible=False,
    )

    toggle_icon = ft.Icon(ft.Icons.EXPAND_MORE, size=18, color=ft.Colors.BLUE_700)
    toggle_text = ft.Text("使い方を見る", size=13, color=ft.Colors.BLUE_700)

    def on_toggle(e):
        is_expanded[0] = not is_expanded[0]
        content.visible = is_expanded[0]
        toggle_icon.name = ft.Icons.EXPAND_LESS if is_expanded[0] else ft.Icons.EXPAND_MORE
        toggle_text.value = "閉じる" if is_expanded[0] else "使い方を見る"
        e.page.update()

    toggle_button = ft.TextButton(
        content=ft.Row(
            controls=[toggle_icon, toggle_text],
            spacing=2,
        ),
        on_click=on_toggle,
        style=ft.ButtonStyle(padding=ft.padding.all(4)),
    )

    return ft.Container(
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=ft.Colors.BLUE_700),
                        ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900),
                        ft.Container(expand=True),
                        toggle_button,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                content,
            ],
            spacing=4,
        ),
        bgcolor=ft.Colors.BLUE_50,
        border=ft.border.all(1, ft.Colors.BLUE_200),
        border_radius=8,
        padding=ft.padding.symmetric(horizontal=16, vertical=10),
        margin=ft.margin.only(bottom=12),
    )
