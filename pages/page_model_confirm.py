"""モデル確定ページ

回帰モデルを実行して確認し、DBに保存する。
保存済みモデルの一覧・削除も行う。
"""
import json

import flet as ft
import pandas as pd

from components.variable_selector import VariableSelector
from components.plot_utils import plot_residuals
from components.help_panel import build_help_panel
from components.data_source_selector import DataSourceSelector
from src.analysis.data_transform import transform, standardize, TRANSFORM_METHODS
from src.analysis.regression import fit_ols
from src.data.indicator_loader import merge_target_and_indicators
from src.db_operations import (
    save_model_config,
    save_model_result,
    load_model_configs,
    delete_model_config,
)


def model_confirm_page(page: ft.Page) -> ft.Control:
    """モデル確定タブのUIを構築する"""
    print("DEBUG: モデル確定ページ構築開始")

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

        selector_ref[0] = VariableSelector(
            page=page,
            columns=columns,
            show_target=True,
            show_transform=False,
            code_to_name=all_c2n,
            target_columns=target_cols,
            target_code_to_name=target_c2n,
        )
        selector_container.controls = [selector_ref[0].get_ui()]
        page.update()

    data_source = DataSourceSelector(page=page, on_data_loaded=on_data_loaded)

    transform_dropdown = ft.Dropdown(
        label="データ変換",
        options=[ft.dropdown.Option(key=k, text=v) for k, v in TRANSFORM_METHODS.items()],
        value="none",
        width=300,
    )
    standardize_switch = ft.Switch(label="標準化", value=False)
    lag_slider = ft.Slider(
        min=0, max=12, divisions=12, label="ラグ: {value}",
        value=0, width=300,
    )
    lag_label = ft.Text("ラグ: 0", size=12)

    result_container = ft.Column(scroll=ft.ScrollMode.AUTO)

    # モデル保存UI
    model_name_input = ft.TextField(
        label="モデル名",
        hint_text="例: ECL予測モデル v1.0（法人PD）",
        width=400,
    )
    model_note_input = ft.TextField(
        label="メモ（任意）",
        hint_text="例: 2026年3月期用。失業率・GDP成長率を使用",
        width=400,
    )
    save_status_text = ft.Text("", size=12)
    save_btn = ft.ElevatedButton(
        "このモデルをDBに保存",
        icon=ft.Icons.SAVE,
        disabled=True,
        on_click=lambda e: _save_model(e),
    )

    # 保存済みモデル一覧
    saved_models_container = ft.Column()

    # 最後に実行した回帰結果を保持
    last_result_ref = [None]
    # {"ols_result": dict, "target": str, "features": list, "lag": int,
    #  "transform": str, "standardize": bool, "feature_stats": dict,
    #  "training_start": date, "training_end": date}

    def on_lag_change(e):
        lag_label.value = f"ラグ: {int(lag_slider.value)}"
        page.update()

    lag_slider.on_change = on_lag_change

    def run_analysis(e):
        """回帰分析を実行してプレビュー表示する"""
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

        result_container.controls = [ft.ProgressRing()]
        page.update()

        try:
            # 目的変数が target_data の場合はマージ
            if target_df is not None and not target_df.empty and target in target_df.columns:
                work_df = merge_target_and_indicators(target_df, df[features], target)
            else:
                work_df = df[[target] + features].copy()

            work_df = transform(work_df, transform_dropdown.value)

            # 標準化の場合は各特徴量の mean/std を保存する（ECL計算時の逆変換に必要）
            feature_stats = {}
            if standardize_switch.value:
                for col in features:
                    if col in work_df.columns:
                        feature_stats[col] = {
                            "mean": float(work_df[col].mean()),
                            "std": float(work_df[col].std()),
                        }
                work_df = standardize(work_df)

            lag = int(lag_slider.value)
            ols = fit_ols(work_df[target], work_df[features], lag=lag)

            # 訓練期間
            y_aligned = work_df[target]
            if lag > 0:
                y_aligned = y_aligned.iloc[lag:]
            training_start = str(y_aligned.index[0])[:10] if not y_aligned.empty else None
            training_end = str(y_aligned.index[-1])[:10] if not y_aligned.empty else None

            # 最後の結果を保存
            last_result_ref[0] = {
                "ols_result": ols,
                "target": target,
                "features": features,
                "lag": lag,
                "transform": transform_dropdown.value,
                "standardize": standardize_switch.value,
                "feature_stats": feature_stats,
                "training_start": training_start,
                "training_end": training_end,
            }
            save_btn.disabled = False

            # 結果表示
            controls = []
            controls.append(ft.Text(
                f"Adj.R²: {ols['adj_r2']:.4f}  |  AIC: {ols['aic']:.2f}  |  DW: {ols['dw']:.3f}  |  F p値: {ols['f_pvalue']:.4f}  |  N: {ols['nobs']}",
                size=13, weight=ft.FontWeight.BOLD,
            ))

            # 係数テーブル
            coef_df = ols["coefficients"]
            coef_rows = []
            for _, row in coef_df.iterrows():
                p_color = ft.Colors.RED_700 if row["p_value"] > 0.05 else ft.Colors.BLACK
                vname = c2n.get(row["variable"], row["variable"])
                coef_rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(vname, size=11)),
                    ft.DataCell(ft.Text(f"{row['coef']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['std_err']:.4f}")),
                    ft.DataCell(ft.Text(f"{row['t_stat']:.3f}")),
                    ft.DataCell(ft.Text(f"{row['p_value']:.4f}", color=p_color)),
                ]))
            controls.append(ft.DataTable(
                columns=[ft.DataColumn(ft.Text(c, size=11)) for c in ["変数", "係数", "標準誤差", "t値", "p値"]],
                rows=coef_rows,
                border=ft.border.all(1, ft.Colors.GREY_300),
            ))

            # 残差プロット
            img = plot_residuals(ols["resid"], ols["fitted"])
            controls.append(ft.Image(src="data:image/png;base64," + img, fit=ft.BoxFit.CONTAIN))

            result_container.controls = controls
            save_status_text.value = "分析完了。モデル名を入力して「DBに保存」を押してください。"
            save_status_text.color = ft.Colors.BLUE_700

        except Exception as ex:
            print(f"DEBUG: モデル確定 回帰エラー: {ex}")
            result_container.controls = [ft.Text(f"分析エラー: {ex}", color=ft.Colors.RED_700)]
            save_btn.disabled = True

        page.update()

    def _save_model(e):
        """現在の回帰結果をDBに保存する"""
        state = last_result_ref[0]
        if state is None:
            save_status_text.value = "先に「回帰を実行して確認」を押してください。"
            save_status_text.color = ft.Colors.RED_700
            page.update()
            return

        model_name = model_name_input.value.strip()
        if not model_name:
            save_status_text.value = "モデル名を入力してください。"
            save_status_text.color = ft.Colors.RED_700
            page.update()
            return

        try:
            ols = state["ols_result"]

            # hyperparameters に変換設定と feature_stats を保存
            hyperparams = {
                "transform": state["transform"],
                "standardize": state["standardize"],
                "lag": state["lag"],
                "feature_stats": state["feature_stats"],
            }

            # coefficients: {変数名: 係数値} の形に変換
            coef_dict = dict(zip(
                ols["coefficients"]["variable"],
                ols["coefficients"]["coef"].astype(float),
            ))

            # 評価指標
            metrics = {
                "r2": float(ols["r2"]),
                "adj_r2": float(ols["adj_r2"]),
                "aic": float(ols["aic"]),
                "bic": float(ols["bic"]),
                "dw": float(ols["dw"]),
                "f_stat": float(ols["f_stat"]),
                "f_pvalue": float(ols["f_pvalue"]),
                "nobs": int(ols["nobs"]),
            }

            # データセットID・frequencyをDataSourceSelectorから取得
            dataset_id_val = data_source._ind_dataset_dd.value
            frequency_val = data_source._ind_freq_dd.value

            config_dict = {
                "model_name": model_name,
                "model_type": "ols",
                "dataset_id": int(dataset_id_val) if dataset_id_val else None,
                "target_variable": state["target"],
                "feature_variables": state["features"],
                "hyperparameters": hyperparams,
                "frequency": frequency_val or "",
                "description": model_note_input.value or "",
            }

            config_id = save_model_config(config_dict)
            save_model_result(config_id, {
                "training_period_start": state["training_start"],
                "training_period_end": state["training_end"],
                "metrics": metrics,
                "coefficients": coef_dict,
            })

            save_status_text.value = f"✓ モデルをDBに保存しました（config_id: {config_id}）"
            save_status_text.color = ft.Colors.GREEN_700
            _refresh_saved_models()

        except Exception as ex:
            print(f"DEBUG: モデル保存エラー: {ex}")
            save_status_text.value = f"保存エラー: {ex}"
            save_status_text.color = ft.Colors.RED_700

        page.update()

    def _refresh_saved_models():
        """保存済みモデル一覧を更新する"""
        try:
            configs = load_model_configs()
            if configs.empty:
                saved_models_container.controls = [ft.Text("保存済みモデルはありません。", color=ft.Colors.GREY_600)]
                return

            rows = []
            for _, row in configs.iterrows():
                metrics = row.get("metrics") or {}
                adj_r2 = metrics.get("adj_r2", "-")
                adj_r2_str = f"{adj_r2:.4f}" if isinstance(adj_r2, float) else str(adj_r2)
                features = row.get("feature_variables") or []
                if isinstance(features, str):
                    try:
                        features = json.loads(features)
                    except Exception:
                        pass

                cid = row["config_id"]

                def make_delete(config_id):
                    def on_delete(e):
                        try:
                            delete_model_config(config_id)
                            _refresh_saved_models()
                            page.update()
                        except Exception as ex:
                            print(f"DEBUG: モデル削除エラー: {ex}")
                    return on_delete

                rows.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(str(cid))),
                    ft.DataCell(ft.Text(row.get("model_name", ""), size=11)),
                    ft.DataCell(ft.Text(row.get("target_variable", ""), size=11)),
                    ft.DataCell(ft.Text(", ".join(features) if isinstance(features, list) else str(features), size=10)),
                    ft.DataCell(ft.Text(adj_r2_str)),
                    ft.DataCell(ft.Text(str(row.get("frequency", "")))),
                    ft.DataCell(ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_color=ft.Colors.RED_400,
                        tooltip="削除",
                        on_click=make_delete(cid),
                    )),
                ]))

            saved_models_container.controls = [
                ft.Text("保存済みモデル一覧", size=16, weight=ft.FontWeight.BOLD),
                ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("ID")),
                        ft.DataColumn(ft.Text("モデル名")),
                        ft.DataColumn(ft.Text("目的変数")),
                        ft.DataColumn(ft.Text("説明変数")),
                        ft.DataColumn(ft.Text("Adj.R²")),
                        ft.DataColumn(ft.Text("frequency")),
                        ft.DataColumn(ft.Text("操作")),
                    ],
                    rows=rows,
                    border=ft.border.all(1, ft.Colors.GREY_300),
                ),
            ]
        except Exception as ex:
            saved_models_container.controls = [ft.Text(f"一覧取得エラー: {ex}", color=ft.Colors.RED_700)]

    # 初期ロード
    _refresh_saved_models()

    _help = build_help_panel(
        title="⑦ モデル確定",
        purpose="回帰モデルを実行して確認し、ECL計算で使うモデルとしてDBに登録します。③回帰分析・⑤動的回帰で精査したモデルの設定（変数・変換・ラグ）をここで正式登録してください。",
        steps=[
            "データソース選択で説明変数・目的変数を選ぶ",
            "③回帰分析で確認した変数・変換・ラグを同じように設定する",
            "「回帰を実行して確認」を押して結果を確認する",
            "モデル名を入力する（例: 法人PD予測モデル v1.0）",
            "「このモデルをDBに保存」を押す",
            "⑧ECL計算タブで保存したモデル（config_id）を使ってECLを計算する",
        ],
        outputs=[
            "回帰結果プレビュー（Adj.R² / AIC / DW / 係数テーブル）",
            "残差プロット",
            "保存済みモデル一覧（config_id・モデル名・目的変数・Adj.R²）",
        ],
        indicators=[
            {
                "name": "このページで何をするか",
                "criteria": [
                    {"level": "情報",  "range": "モデルの再現性を担保する",   "meaning": "変数・変換・ラグ・係数をDBに記録することで、翌年以降も同じモデルを再現できる"},
                    {"level": "情報",  "range": "毎年の通常更新",              "meaning": "変数を変えない年は再登録不要。ECL計算タブで前年のconfig_idを流用する"},
                    {"level": "注意",  "range": "モデルを変更した年",          "meaning": "新しい変数を採用した場合は新規登録する（旧モデルは削除しない）"},
                ],
                "note": "③回帰分析と同じ計算をする。③で良い結果が出た設定をそのままここで再実行して保存してください",
            },
        ],
    )

    return ft.Column(
        controls=[
            _help,
            ft.Text("モデル確定", size=24, weight=ft.FontWeight.BOLD),
            data_source.get_ui(),
            selector_container,
            ft.Row([transform_dropdown, standardize_switch]),
            ft.Row([lag_slider, lag_label]),
            ft.ElevatedButton("回帰を実行して確認", on_click=run_analysis, icon=ft.Icons.ANALYTICS),
            ft.Divider(),
            result_container,
            ft.Container(
                visible=True,
                content=ft.Column([
                    ft.Text("モデルをDBに保存", size=16, weight=ft.FontWeight.BOLD),
                    model_name_input,
                    model_note_input,
                    ft.Row([save_btn, save_status_text]),
                ]),
                padding=12,
                border=ft.border.all(1, ft.Colors.BLUE_200),
                border_radius=8,
                bgcolor=ft.Colors.BLUE_50,
                margin=ft.margin.only(top=12),
            ),
            ft.Divider(),
            saved_models_container,
            ft.ElevatedButton(
                "一覧を更新",
                icon=ft.Icons.REFRESH,
                on_click=lambda e: [_refresh_saved_models(), page.update()],
            ),
        ],
        spacing=10,
        expand=True,
    )
