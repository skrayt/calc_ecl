"""ヘルプパネルコンポーネント

各ページの上部に折りたたみ式のヘルプパネルを表示する。
"""
import flet as ft


def _badge(text: str, color: str, bg: str) -> ft.Container:
    """色付きバッジを生成する"""
    return ft.Container(
        content=ft.Text(text, size=11, color=color, weight=ft.FontWeight.BOLD),
        bgcolor=bg,
        border_radius=4,
        padding=ft.padding.symmetric(horizontal=6, vertical=2),
    )


def build_help_panel(
    title: str,
    purpose: str,
    steps: list[str],
    outputs: list[str],
    indicators: list[dict] | None = None,
) -> ft.Control:
    """折りたたみ式ヘルプパネルを構築する。

    Args:
        title: ページタイトル
        purpose: このページの目的（1〜2文）
        steps: 操作手順のリスト
        outputs: 表示される結果・出力のリスト
        indicators: 統計指標の解説リスト。各要素は以下のキーを持つ dict:
            - name (str): 指標名
            - criteria (list[dict]): 判定基準のリスト
                - level (str): "良好" / "注意" / "危険" 等
                - range (str): 数値基準（例: "p < 0.05"）
                - meaning (str): 解釈説明
            - note (str, optional): 補足説明

    Returns:
        折りたたみ可能なヘルプパネル
    """
    is_expanded = [False]

    # --- 操作手順 ---
    step_items = [
        ft.Row(
            controls=[
                ft.Text(f"  {i+1}. ", size=13, color=ft.Colors.BLUE_700, weight=ft.FontWeight.BOLD),
                ft.Text(step, size=13),
            ],
            wrap=True,
        )
        for i, step in enumerate(steps)
    ]

    # --- 表示される結果 ---
    output_items = [
        ft.Row(
            controls=[
                ft.Text("  • ", size=13, color=ft.Colors.GREEN_700, weight=ft.FontWeight.BOLD),
                ft.Text(output, size=13),
            ],
            wrap=True,
        )
        for output in outputs
    ]

    # --- 指標解説セクション ---
    LEVEL_COLORS = {
        "良好":  (ft.Colors.GREEN_800,  ft.Colors.GREEN_50),
        "注意":  (ft.Colors.ORANGE_800, ft.Colors.ORANGE_50),
        "危険":  (ft.Colors.RED_800,    ft.Colors.RED_50),
        "情報":  (ft.Colors.BLUE_800,   ft.Colors.BLUE_50),
    }

    def _make_indicator_card(ind: dict) -> ft.Container:
        rows = []
        for c in ind.get("criteria", []):
            level = c.get("level", "情報")
            color, bg = LEVEL_COLORS.get(level, (ft.Colors.GREY_800, ft.Colors.GREY_50))
            rows.append(
                ft.Row(
                    controls=[
                        _badge(level, color, bg),
                        ft.Text(c["range"], size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_900, width=140),
                        ft.Text(c["meaning"], size=12, color=ft.Colors.GREY_800, expand=True),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        note_row = []
        if ind.get("note"):
            note_row = [
                ft.Text(f"※ {ind['note']}", size=11, color=ft.Colors.GREY_600, italic=True)
            ]
        return ft.Container(
            content=ft.Column(
                controls=[
                    ft.Text(ind["name"], size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.INDIGO_700),
                    *rows,
                    *note_row,
                ],
                spacing=4,
            ),
            bgcolor=ft.Colors.WHITE,
            border=ft.border.all(1, ft.Colors.GREY_200),
            border_radius=6,
            padding=ft.padding.all(10),
        )

    indicator_section_controls = []
    if indicators:
        indicator_section_controls = [
            ft.Divider(height=1, color=ft.Colors.BLUE_100),
            ft.Text("📊 指標の見方・判定基準", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.INDIGO_700),
            ft.Column(
                controls=[_make_indicator_card(ind) for ind in indicators],
                spacing=8,
            ),
        ]

    # --- メインコンテンツ ---
    content = ft.Column(
        controls=[
            ft.Container(
                content=ft.Text(purpose, size=13, color=ft.Colors.GREY_800),
                padding=ft.padding.only(bottom=8),
            ),
            ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Text("操作手順", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                                *step_items,
                            ],
                            spacing=4,
                        ),
                        expand=True,
                    ),
                    ft.VerticalDivider(width=1, color=ft.Colors.GREY_300),
                    ft.Container(
                        content=ft.Column(
                            controls=[
                                ft.Text("表示される結果", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_700),
                                *output_items,
                            ],
                            spacing=4,
                        ),
                        expand=True,
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            *indicator_section_controls,
        ],
        spacing=8,
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
