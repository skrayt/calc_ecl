"""ECL将来予想モデル — Fletアプリ エントリポイント

タブベースのUIで各分析機能を切り替える。
"""
import flet as ft

from pages.page_data_view import data_view_page
from pages.page_correlation import correlation_page
from pages.page_regression import regression_page
from pages.page_model_selection import model_selection_page
from pages.page_dynamic_regression import dynamic_regression_page
from pages.page_arima import arima_page
from pages.page_forecast import forecast_page


def main(page: ft.Page):
    """Fletアプリを初期化し、各タブ画面を切り替えるUIを構築する"""
    print("DEBUG: アプリ起動")

    page.title = "ECL将来予想モデル"
    page.theme_mode = ft.ThemeMode.LIGHT

    # ウィンドウサイズ可変対応
    page.window.resizable = True
    page.window.width = 1400
    page.window.height = 900
    page.window.min_width = 800
    page.window.min_height = 600

    # タブの本体表示領域
    body = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True)

    def on_tab_change(e):
        """タブ切替時にページを動的ロードする"""
        # TabBar.on_click: e.data にクリック位置(int文字列)が入る
        try:
            selected = int(e.data) if e.data else 0
        except (ValueError, TypeError):
            selected = 0
        print(f"DEBUG: タブ切替 → index={selected}")
        body.controls.clear()

        try:
            if selected == 0:
                body.controls.append(data_view_page(page))
            elif selected == 1:
                body.controls.append(correlation_page(page))
            elif selected == 2:
                body.controls.append(regression_page(page))
            elif selected == 3:
                body.controls.append(model_selection_page(page))
            elif selected == 4:
                body.controls.append(dynamic_regression_page(page))
            elif selected == 5:
                body.controls.append(arima_page(page))
            elif selected == 6:
                body.controls.append(forecast_page(page))
        except Exception as ex:
            print(f"DEBUG: タブ{selected}のロードエラー: {ex}")
            body.controls.append(
                ft.Text(f"ページのロードに失敗しました: {ex}", color=ft.Colors.RED_700)
            )

        page.update()

    # TabBar (Tabsの中に配置する必要がある)
    tab_bar = ft.TabBar(
        tabs=[
            ft.Tab(label="① データ閲覧"),
            ft.Tab(label="② 相関分析"),
            ft.Tab(label="③ 回帰分析"),
            ft.Tab(label="④ モデル選択"),
            ft.Tab(label="⑤ 動的回帰"),
            ft.Tab(label="⑥ ARIMA"),
            ft.Tab(label="⑦ 将来シナリオ"),
        ],
        # on_click は設定しない（Tabs.on_change と二重発火するため）
    )

    # 初期ページをロード
    body.controls.append(data_view_page(page))

    # Tabs コントローラー（TabBarを内包する必要がある）
    # expand=True で画面高さいっぱいに広げることで、body の scroll が機能する
    tabs_ctrl = ft.Tabs(
        length=7,
        selected_index=0,
        on_change=on_tab_change,
        expand=True,
        content=ft.Column(
            controls=[tab_bar, body],
            expand=True,
        ),
    )

    page.add(tabs_ctrl)
    print("DEBUG: 初期ページ表示完了")


if __name__ == "__main__":
    ft.run(main)
