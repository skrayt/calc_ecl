"""相関分析ページ

相関行列ヒートマップ・VIF一覧テーブル・VIFクロス表の表示を行う。
"""
import flet as ft
import pandas as pd

from components.variable_selector import VariableSelector
from components.plot_utils import plot_correlation_heatmap, plot_vif_heatmap
from components.help_panel import build_help_panel
from src.analysis.data_transform import transform, standardize
from src.data.indicator_loader import (
    get_indicator_definitions,
    get_target_definitions,
    merge_target_and_indicators,
)
from src.analysis.correlation import (
    calc_correlation_matrix,
    calc_vif,
    calc_vif_cross_table,
)


def correlation_page(page: ft.Page) -> ft.Control:
    """相関分析タブのUIを構築する"""
    print("DEBUG: 相関分析ページ構築開始")

    # 共有データを取得
    df: pd.DataFrame | None = page.session.store.get("df")
    if df is None or df.empty:
        return ft.Text("先にデータ閲覧タブでデータを読み込んでください。", color=ft.Colors.RED_700)

    # indicator_code → indicator_name のマッピングを取得
    defs = get_indicator_definitions(df.columns.tolist())
    code_to_name: dict[str, str] = dict(zip(defs["indicator_code"], defs["indicator_name"]))

    # 目的変数データの取得（セッションストアから）
    target_df: pd.DataFrame | None = page.session.store.get("target_df")
    target_cols = None
    target_c2n: dict[str, str] = {}
    if target_df is not None and not target_df.empty:
        target_cols = target_df.columns.tolist()
        t_defs = get_target_definitions(target_cols)
        target_c2n = dict(zip(t_defs["target_code"], t_defs["target_name"]))
        code_to_name.update(target_c2n)

    # 変数セレクタ
    selector = VariableSelector(
        page=page,
        columns=df.columns.tolist(),
        show_target=True,
        show_transform=False,
        code_to_name=code_to_name,
        target_columns=target_cols,
        target_code_to_name=target_c2n,
    )

    # 変換ドロップダウン（全カラム一括）
    from src.analysis.data_transform import TRANSFORM_METHODS
    transform_dropdown = ft.Dropdown(
        label="データ変換",
        options=[ft.dropdown.Option(key=k, text=v) for k, v in TRANSFORM_METHODS.items()],
        value="none",
        width=300,
    )
    standardize_switch = ft.Switch(label="標準化", value=False)

    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)

    def run_analysis(e):
        """分析実行"""
        target = selector.get_target()
        features = selector.get_selected_features()

        if not target:
            result_container.controls = [ft.Text("目的変数を選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return
        if not features:
            result_container.controls = [ft.Text("説明変数を1つ以上選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        print(f"DEBUG: 相関分析実行 target={target}, features={features}")
        result_container.controls = [ft.ProgressRing()]
        page.update()

        try:
            # 目的変数が別ソース（target_data）の場合はマージ
            if target_df is not None and not target_df.empty and target in target_df.columns:
                work_df = merge_target_and_indicators(target_df, df[features], target)
            else:
                cols = [target] + features
                work_df = df[cols].copy()

            # データ変換
            method = transform_dropdown.value
            work_df = transform(work_df, method)
            if standardize_switch.value:
                work_df = standardize(work_df)

            results = []

            # 相関行列
            corr = calc_correlation_matrix(work_df)
            img_corr = plot_correlation_heatmap(corr)
            results.append(ft.Text("相関行列", size=18, weight=ft.FontWeight.BOLD))
            results.append(ft.Image(src="data:image/png;base64," + img_corr, fit=ft.BoxFit.CONTAIN))

            # VIF一覧
            if len(features) >= 2:
                X = work_df[features]
                vif_df = calc_vif(X)
                results.append(ft.Divider())
                results.append(ft.Text("VIF（分散拡大係数）", size=18, weight=ft.FontWeight.BOLD))
                results.append(ft.Text("VIF > 10: 多重共線性あり, VIF > 5: 注意", size=11, color=ft.Colors.GREY_600))

                vif_table = ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("変数")),
                        ft.DataColumn(ft.Text("VIF"), numeric=True),
                    ],
                    rows=[
                        ft.DataRow(cells=[
                            ft.DataCell(ft.Text(code_to_name.get(row["variable"], row["variable"]))),
                            ft.DataCell(ft.Text(
                                f"{row['vif']:.4f}",
                                color=ft.Colors.RED_700 if row["vif"] > 10 else None,
                            )),
                        ])
                        for _, row in vif_df.iterrows()
                    ],
                    border=ft.border.all(1, ft.Colors.GREY_300),
                )
                results.append(vif_table)

                # VIFクロス表ヒートマップ
                vif_cross = calc_vif_cross_table(work_df[features])
                img_vif = plot_vif_heatmap(vif_cross)
                results.append(ft.Divider())
                results.append(ft.Text("VIFクロス表", size=18, weight=ft.FontWeight.BOLD))
                results.append(ft.Image(src="data:image/png;base64," + img_vif, fit=ft.BoxFit.CONTAIN))
            else:
                results.append(ft.Text("VIF算出には説明変数を2つ以上選択してください。", size=12, italic=True))

            result_container.controls = results
            print("DEBUG: 相関分析完了")

        except Exception as ex:
            print(f"DEBUG: 相関分析エラー: {ex}")
            result_container.controls = [ft.Text(f"分析エラー: {ex}", color=ft.Colors.RED_700)]

        page.update()

    # レイアウト
    _help = build_help_panel(
        title="② 相関分析",
        purpose="目的変数と説明変数の相関係数を可視化し、多重共線性（VIF）を診断します。強い相関（|r| > 0.6）の変数を選び、VIF < 10 の組み合わせで回帰分析に進みましょう。",
        steps=[
            "変数セレクタで目的変数（1つ）と説明変数（複数）を選択する",
            "必要に応じてデータ変換（log・差分等）と標準化を設定する",
            "「分析実行」を押す",
            "相関ヒートマップで目的変数との相関が強い変数（赤・青の濃い色）を確認する",
            "VIF一覧で赤色（VIF > 10）の変数は説明変数から除外することを検討する",
        ],
        outputs=[
            "相関行列ヒートマップ（色分けで相関の強さを可視化）",
            "VIF一覧テーブル（VIF > 10 は赤色警告）",
            "VIFクロス表ヒートマップ（変数間の多重共線性の関係）",
        ],
        indicators=[
            {
                "name": "相関係数（Pearson r）",
                "criteria": [
                    {"level": "良好",  "range": "|r| ≥ 0.7",        "meaning": "強い相関。目的変数の説明変数として有力な候補"},
                    {"level": "注意",  "range": "0.3 ≤ |r| < 0.7",  "meaning": "中程度の相関。他の変数と組み合わせて検討"},
                    {"level": "危険",  "range": "|r| < 0.3",         "meaning": "弱い相関。説明変数としての有効性が低い可能性がある"},
                ],
                "note": "ヒートマップの色が濃いほど相関が強い。赤＝正の相関、青＝負の相関",
            },
            {
                "name": "VIF（分散拡大係数）— 多重共線性の診断",
                "criteria": [
                    {"level": "良好",  "range": "VIF < 5",   "meaning": "多重共線性なし。安心して使用できる"},
                    {"level": "注意",  "range": "5 ≤ VIF < 10", "meaning": "軽度の多重共線性。係数の解釈に注意が必要"},
                    {"level": "危険",  "range": "VIF ≥ 10",  "meaning": "深刻な多重共線性。相関の高い変数を一方除外することを推奨"},
                ],
                "note": "VIFが高い変数が複数ある場合、それらは互いに高い相関を持つ（例: 名目GDP と 実質GDP を同時投入するケース）",
            },
        ],
    )
    return ft.Column(
        controls=[
            _help,
            ft.Text("相関分析", size=24, weight=ft.FontWeight.BOLD),
            selector.get_ui(),
            ft.Row([transform_dropdown, standardize_switch]),
            ft.ElevatedButton("分析実行", on_click=run_analysis, icon=ft.Icons.ANALYTICS),
            ft.Divider(),
            result_container,
        ],
        spacing=10,
        expand=True,
    )
