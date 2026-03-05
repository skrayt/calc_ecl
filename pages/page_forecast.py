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
        purpose="回帰・ARIMAモデルの予測結果をもとに、ベース/楽観/悲観シナリオを作成してECLを算出します。IFRS9では複数シナリオの加重平均でECLを算出することが求められています。",
        steps=[
            "事前準備: ⑥ARIMAで各説明変数の将来予測値を生成しておく",
            "事前準備: ③または⑤でPD/LGD予測の回帰モデルを確定しておく",
            "（実装後）シナリオ（ベース/楽観/悲観）を選択する",
            "（実装後）各シナリオの重み（合計100%）を設定する（例: ベース60%・楽観20%・悲観20%）",
            "（実装後）加重平均によるECL算出を実行し、結果をDBに保存する",
        ],
        outputs=[
            "（実装後）シナリオ別の予測値グラフ（マクロ指標 + PD/LGD予測）",
            "（実装後）加重平均ECL算出結果（期間別・シナリオ別）",
        ],
        indicators=[
            {
                "name": "IFRS9 ECLシナリオ設計の考え方",
                "criteria": [
                    {"level": "情報",  "range": "ベースシナリオ",  "meaning": "現状維持・中央予測。最も可能性が高いシナリオ。重みは通常50〜70%"},
                    {"level": "良好",  "range": "楽観シナリオ",   "meaning": "経済改善を仮定。GDP高め・失業率低めの前提。重みは通常10〜25%"},
                    {"level": "危険",  "range": "悲観シナリオ",   "meaning": "経済悪化を仮定。景気後退・信用コスト上昇を想定。重みは通常15〜30%"},
                ],
                "note": "各シナリオの重みの合計は必ず100%になるようにする。重みは経営判断・監査法人との合意に基づき設定する",
            },
            {
                "name": "ECL（予想信用損失）の構成要素",
                "criteria": [
                    {"level": "情報",  "range": "PD（デフォルト確率）",  "meaning": "借り手がデフォルトする確率。マクロ経済変数で将来予測する主対象"},
                    {"level": "情報",  "range": "LGD（デフォルト時損失率）", "meaning": "デフォルト発生時に回収できない割合。担保・保証で変動する"},
                    {"level": "情報",  "range": "EAD（デフォルト時エクスポージャー）", "meaning": "デフォルト時点の残高予測。ローン残高・コミットメント等"},
                    {"level": "情報",  "range": "ECL = PD × LGD × EAD",  "meaning": "予想信用損失の基本算式。これをシナリオ別に算出し加重平均する"},
                ],
                "note": "本システムではPDおよびLGDのマクロ連動モデル構築が主目的。EADは別途残高データから取得する",
            },
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
