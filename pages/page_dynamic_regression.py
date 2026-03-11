"""動的回帰ページ

変数ごとの個別変換・標準化・ラグ設定による時系列回帰分析を行う。
"""
import flet as ft
import pandas as pd

from components.variable_selector import VariableSelector
from components.plot_utils import plot_residuals
from components.help_panel import build_help_panel
from components.data_source_selector import DataSourceSelector
from src.analysis.data_transform import transform_per_column
from src.analysis.regression import fit_ols
from src.data.indicator_loader import (
    merge_target_and_indicators,
)


def dynamic_regression_page(page: ft.Page) -> ft.Control:
    """動的回帰タブのUIを構築する"""
    print("DEBUG: 動的回帰ページ構築開始")

    # 変数セレクタ（後から構築）
    selector_container = ft.Column()
    selector_ref = [None]
    ind_df_ref = [None]
    tgt_df_ref = [None]
    code_to_name_ref = [{}]

    def on_data_loaded(indicator_df, target_df, code_to_name, target_c2n):
        """データソース変更時に変数セレクタを再構築する"""
        ind_df_ref[0] = indicator_df
        tgt_df_ref[0] = target_df
        all_c2n = dict(code_to_name)
        all_c2n.update(target_c2n)
        code_to_name_ref[0] = all_c2n

        columns = indicator_df.columns.tolist() if indicator_df is not None and not indicator_df.empty else []
        target_cols = target_df.columns.tolist() if target_df is not None and not target_df.empty else None

        if not columns:
            selector_container.controls = [
                ft.Text("説明変数データがありません。データソースを選択してください。", color=ft.Colors.ORANGE_700)
            ]
            selector_ref[0] = None
            page.update()
            return

        # 全値が[0,1]範囲の変数を検出（標準化不要変数）
        unit_range_cols = []
        if indicator_df is not None:
            for col in indicator_df.columns:
                valid = indicator_df[col].dropna()
                if len(valid) > 0 and (valid >= 0).all() and (valid <= 1).all():
                    unit_range_cols.append(col)

        selector_ref[0] = VariableSelector(
            page=page,
            columns=columns,
            show_target=True,
            show_transform=True,
            code_to_name=all_c2n,
            target_columns=target_cols,
            target_code_to_name=target_c2n,
            unit_range_columns=unit_range_cols,
        )
        selector_container.controls = [selector_ref[0].get_ui()]
        page.update()

    data_source = DataSourceSelector(page=page, on_data_loaded=on_data_loaded)

    # 変数ごとのラグ設定用コンテナ
    lag_settings_container = ft.Column(spacing=5)
    lag_values: dict[str, int] = {}

    def update_lag_settings():
        """選択された変数に合わせてラグスライダーを表示する"""
        lag_settings_container.controls.clear()
        selector = selector_ref[0]
        if selector is None:
            return
        features = selector.get_selected_features()
        c2n = code_to_name_ref[0]
        for col in features:
            if col not in lag_values:
                lag_values[col] = 0
            slider = ft.Slider(
                min=0, max=12, divisions=12,
                value=lag_values.get(col, 0),
                label=f"{c2n.get(col, col)}: " + "{value}",
                width=300,
                on_change=lambda e, c=col: _on_lag_change(e, c),
            )
            lag_settings_container.controls.append(
                ft.Row([ft.Text(c2n.get(col, col), width=200, size=12), slider])
            )
        page.update()

    def _on_lag_change(e, col: str):
        lag_values[col] = int(e.control.value)

    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)

    def run_analysis(e):
        """分析実行"""
        update_lag_settings()

        selector = selector_ref[0]
        if selector is None:
            result_container.controls = [ft.Text("データソースを選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        target = selector.get_target()
        features = selector.get_selected_features()
        if not target or not features:
            result_container.controls = [ft.Text("目的変数と説明変数を選択してください。", color=ft.Colors.RED_700)]
            page.update()
            return

        df = ind_df_ref[0]
        target_df = tgt_df_ref[0]
        c2n = code_to_name_ref[0]
        settings = selector.get_variable_settings()

        print(f"DEBUG: 動的回帰実行 target={target}, features={features}, settings={settings}")

        result_container.controls = [ft.ProgressRing()]
        page.update()

        try:
            # 目的変数が別ソース（target_data）の場合はマージ
            if target_df is not None and not target_df.empty and target in target_df.columns:
                base_df = merge_target_and_indicators(target_df, df[features], target)
            else:
                cols = [target] + features
                base_df = df[cols].copy()
            # 変数ごとの個別変換
            work_df = transform_per_column(base_df, settings)

            y = work_df[target]
            X = work_df[features]

            # ラグは最大値を使用（動的回帰の場合）
            max_lag = max(lag_values.get(f, 0) for f in features) if features else 0

            ols = fit_ols(y, X, lag=max_lag)

            results = []
            results.append(ft.Text("動的回帰結果", size=18, weight=ft.FontWeight.BOLD))

            # 変換設定の表示
            all_cols = [target] + features
            setting_rows = []
            for col in all_cols:
                s = settings.get(col, {})
                setting_rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(c2n.get(col, col))),
                    ft.DataCell(ft.Text(s.get("transform", "none"))),
                    ft.DataCell(ft.Text("✓" if s.get("standardize") else "")),
                    ft.DataCell(ft.Text(str(lag_values.get(col, 0)))),
                ]))
            results.append(ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("変数")),
                    ft.DataColumn(ft.Text("変換")),
                    ft.DataColumn(ft.Text("標準化")),
                    ft.DataColumn(ft.Text("ラグ")),
                ],
                rows=setting_rows,
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # モデル概要
            results.append(ft.Divider())
            summary = [
                ("R²", f"{ols['r2']:.4f}"), ("Adj. R²", f"{ols['adj_r2']:.4f}"),
                ("AIC", f"{ols['aic']:.2f}"), ("BIC", f"{ols['bic']:.2f}"),
                ("DW", f"{ols['dw']:.4f}"), ("F統計量", f"{ols['f_stat']:.4f}"),
                ("観測数", str(ols['nobs'])),
            ]
            results.append(ft.DataTable(
                columns=[ft.DataColumn(ft.Text("指標")), ft.DataColumn(ft.Text("値"))],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(k)), ft.DataCell(ft.Text(v))]) for k, v in summary],
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # 係数テーブル
            results.append(ft.Divider())
            results.append(ft.Text("係数テーブル", size=16, weight=ft.FontWeight.BOLD))
            coef_df = ols["coefficients"]
            results.append(ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("変数")), ft.DataColumn(ft.Text("係数")),
                    ft.DataColumn(ft.Text("標準誤差")), ft.DataColumn(ft.Text("t値")),
                    ft.DataColumn(ft.Text("p値")),
                ],
                rows=[ft.DataRow(cells=[
                    ft.DataCell(ft.Text(c2n.get(row["variable"], row["variable"]))),
                    ft.DataCell(ft.Text(f"{row['coef']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['std_err']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['t_stat']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['p_value']:.4f}",
                        color=ft.Colors.RED_700 if row["p_value"] > 0.05 else None)),
                ]) for _, row in coef_df.iterrows()],
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # 残差プロット
            results.append(ft.Divider())
            img = plot_residuals(ols["resid"], ols["fitted"])
            results.append(ft.Image(src="data:image/png;base64," + img, fit=ft.BoxFit.CONTAIN))

            result_container.controls = results
            print("DEBUG: 動的回帰完了")

        except Exception as ex:
            print(f"DEBUG: 動的回帰エラー: {ex}")
            result_container.controls = [ft.Text(f"分析エラー: {ex}", color=ft.Colors.RED_700)]

        page.update()

    _help = build_help_panel(
        title="⑤ 動的回帰（変数別設定）",
        purpose="変数ごとに異なるデータ変換・標準化・ラグを個別指定した回帰分析を行います。②相関分析・③回帰分析・④モデル選択が「全変数に同じ条件を適用して全体傾向を把握する」のに対し、このページは「最終モデルの細かな調整専用」として位置づけられます。④モデル選択で有望な変数の組み合わせを絞り込んだ後、このページで変数別に変換・ラグを最適化してください。",
        steps=[
            "データソース選択で説明変数・目的変数のデータセットとfrequencyを選ぶ（frequencyを揃える）",
            "変数セレクタで目的変数と説明変数を選択する（各変数に変換・標準化を個別設定）",
            "※ 目的変数（PD/LGD）は変換・標準化の対象外です（下記「設計上の注意」を参照）",
            "「ラグ設定を更新」を押して変数ごとのラグスライダーを表示する",
            "各変数のラグ期間をスライダーで調整する（例: GDP→2期、失業率→1期）",
            "「分析実行」を押す",
            "③回帰分析と同じ基準（p値・DW・Adj.R²）でモデルを評価する",
        ],
        outputs=[
            "変数設定テーブル（変数・変換方法・標準化・ラグ期間の確認）",
            "モデル概要（R²・Adj.R²・AIC・BIC・DW・F統計量）",
            "係数テーブル（係数・標準誤差・t値・p値）",
            "残差プロット",
        ],
        indicators=[
            {
                "name": "設計上の注意: 目的変数（PD/LGD）は変換・標準化しない",
                "criteria": [
                    {"level": "情報",  "range": "目的変数は変換しない",   "meaning": "PD/LGDは0〜1の比率であり、解釈可能な実測値のまま使用する"},
                    {"level": "注意",  "range": "目的変数を標準化しない", "meaning": "標準化すると係数の解釈が困難になり、ECL算出時に逆変換が必要になる"},
                    {"level": "情報",  "range": "説明変数は変換・標準化可", "meaning": "マクロ経済指標は差分・対数変換して定常化するのが一般的"},
                ],
                "note": "変数セレクタで目的変数の変換・標準化を設定しても、分析ロジック上は無視されます（目的変数はそのまま使用されます）",
            },
            {
                "name": "このページの推奨ワークフロー（他のページとの使い分け）",
                "criteria": [
                    {"level": "情報",  "range": "②相関分析",    "meaning": "変数候補の全体的な相関傾向を把握する（一括変換で均等比較）"},
                    {"level": "情報",  "range": "④モデル選択",  "meaning": "全組み合わせを網羅的に探索し、有望な変数の組み合わせを絞り込む"},
                    {"level": "良好",  "range": "⑤動的回帰（本ページ）", "meaning": "絞り込んだ変数を変数別設定で精査する（最終調整フェーズ）"},
                ],
                "note": "②〜④は全変数に同じ変換を一括適用する探索フェーズ。このページは変数別の細かな設定が可能な最終調整フェーズです",
            },
            {
                "name": "ラグ期間の設定指針",
                "criteria": [
                    {"level": "情報",  "range": "ラグ 0期",  "meaning": "同時期の値を使用（即時効果を仮定）"},
                    {"level": "情報",  "range": "ラグ 1〜2期", "meaning": "1〜2期前の値を使用（短期遅延）。月次データなら1〜2ヶ月前"},
                    {"level": "情報",  "range": "ラグ 3〜4期", "meaning": "3〜4期前（中期遅延）。経済指標がPD/LGDに波及するまでの一般的な期間"},
                    {"level": "注意",  "range": "ラグ 6期以上", "meaning": "長期遅延。サンプル数が減るため、統計的有意性が低下しやすい"},
                ],
                "note": "最適ラグは相関分析の「クロス相関」や業務知識で決める。理論的根拠のないラグ調整はデータのフィッティング（過学習）になる可能性がある",
            },
            {
                "name": "データ変換の選択指針",
                "criteria": [
                    {"level": "情報",  "range": "変換なし（levels）",    "meaning": "水準値。単位根がある場合は見かけの相関（スプリアス回帰）に注意"},
                    {"level": "良好",  "range": "対数変換（log）",        "meaning": "指数的に変化する変数（GDP・物価指数等）に有効。分散を安定させる"},
                    {"level": "良好",  "range": "差分（diff）",           "meaning": "トレンドを除去し定常化。単位根がある場合の標準的な対処"},
                    {"level": "良好",  "range": "対数差分（log diff）",   "meaning": "成長率・変化率に相当。インフレ率・GDP成長率等に適している"},
                ],
                "note": "ADF検定（ARIMA分析ページ）で単位根が確認された変数は差分変換を適用することを推奨",
            },
        ],
    )
    return ft.Column(
        controls=[
            _help,
            ft.Text("動的回帰（変数別設定）", size=24, weight=ft.FontWeight.BOLD),
            ft.Container(
                content=ft.Text(
                    "📌 このページは変数別設定の最終調整専用です。④モデル選択で有望な変数の組み合わせを絞り込んだ後にご利用ください。"
                    "　目的変数（PD/LGD）の変換・標準化は行いません。",
                    size=12, color=ft.Colors.BLUE_800,
                ),
                bgcolor=ft.Colors.BLUE_50,
                border_radius=6,
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
            ),
            data_source.get_ui(),
            selector_container,
            ft.Text("変数ごとのラグ設定:", size=14, weight=ft.FontWeight.BOLD),
            ft.ElevatedButton("ラグ設定を更新", on_click=lambda e: update_lag_settings()),
            lag_settings_container,
            ft.ElevatedButton("分析実行", on_click=run_analysis, icon=ft.Icons.ANALYTICS),
            ft.Divider(),
            result_container,
        ],
        spacing=10,
        expand=True,
    )
