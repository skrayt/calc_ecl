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

    page.scroll = ft.ScrollMode.AUTO

    # タブの本体表示領域
    body = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)

    def on_tab_change(e):
        """タブ切替時にページを動的ロードする"""
        selected = e.control.selected_index
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

    # タブメニュー
    tabs = ft.Tabs(
        selected_index=0,
        on_change=on_tab_change,
        tabs=[
            ft.Tab(text="① データ閲覧"),
            ft.Tab(text="② 相関分析"),
            ft.Tab(text="③ 回帰分析"),
            ft.Tab(text="④ モデル選択"),
            ft.Tab(text="⑤ 動的回帰"),
            ft.Tab(text="⑥ ARIMA"),
            ft.Tab(text="⑦ 将来シナリオ"),
        ],
    )

    # 初期ページ
    body.controls.append(data_view_page(page))

    page.add(tabs, body)
    print("DEBUG: 初期ページ表示完了")


if __name__ == "__main__":
    ft.app(target=main)
