"""DBへのモデル・ARIMA予測・ECL結果の保存・読込モジュール

model_configs / model_results / arima_forecasts / ecl_results テーブルを操作する。
"""
import json

import pandas as pd

from config.db import get_connection


# ============================================================
# モデル設定（model_configs / model_results）
# ============================================================

def save_model_config(config_dict: dict) -> int:
    """モデル設定をDBに保存し、config_id を返す

    Parameters
    ----------
    config_dict : dict
        必須キー: model_name, target_variable, feature_variables, frequency
        任意キー: dataset_id, hyperparameters, region_code, description
          hyperparameters は以下の構造を推奨:
          {
            "transform": "none",
            "standardize": true,
            "lag": 2,
            "feature_stats": {"var1": {"mean": 2.4, "std": 0.8}, ...}
          }

    Returns
    -------
    int
        登録されたconfig_id
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO model_configs
                    (model_name, model_type, dataset_id, target_variable,
                     feature_variables, hyperparameters, frequency, region_code, description)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s)
                RETURNING config_id
            """, (
                config_dict["model_name"],
                config_dict.get("model_type", "ols"),
                config_dict.get("dataset_id"),
                config_dict["target_variable"],
                json.dumps(config_dict["feature_variables"]),
                json.dumps(config_dict.get("hyperparameters", {})),
                config_dict["frequency"],
                config_dict.get("region_code", "00000"),
                config_dict.get("description", ""),
            ))
            config_id = cur.fetchone()[0]
        conn.commit()
        return config_id
    finally:
        conn.close()


def save_model_result(config_id: int, result_dict: dict) -> int:
    """モデル実行結果をDBに保存し、result_id を返す

    Parameters
    ----------
    config_id : int
        関連するmodel_configs.config_id
    result_dict : dict
        必須キー: metrics, coefficients, training_period_start, training_period_end
          metrics: {"r2": 0.8, "adj_r2": 0.75, "aic": -32.0, "bic": -28.0,
                    "dw": 1.9, "f_stat": 15.0, "f_pvalue": 0.001, "nobs": 30}
          coefficients: {"const": 0.02, "unemployment_rate": 0.0015, ...}
          training_period_start/end: date 文字列または None

    Returns
    -------
    int
        登録されたresult_id
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO model_results
                    (config_id, training_period_start, training_period_end,
                     metrics, coefficients, status)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, 'completed')
                RETURNING result_id
            """, (
                config_id,
                result_dict.get("training_period_start"),
                result_dict.get("training_period_end"),
                json.dumps(result_dict["metrics"]),
                json.dumps(result_dict["coefficients"]),
            ))
            result_id = cur.fetchone()[0]
        conn.commit()
        return result_id
    finally:
        conn.close()


def load_model_configs() -> pd.DataFrame:
    """保存済みモデル設定一覧を返す（最新の実行結果指標も含む）

    Returns
    -------
    pd.DataFrame
        カラム: config_id, model_name, target_variable, feature_variables,
                hyperparameters, frequency, created_at, metrics, result_id
    """
    conn = get_connection()
    try:
        df = pd.read_sql("""
            SELECT
                mc.config_id,
                mc.model_name,
                mc.target_variable,
                mc.feature_variables,
                mc.hyperparameters,
                mc.frequency,
                mc.created_at,
                mr.metrics,
                mr.result_id
            FROM model_configs mc
            LEFT JOIN LATERAL (
                SELECT result_id, metrics
                FROM model_results
                WHERE config_id = mc.config_id
                ORDER BY run_date DESC
                LIMIT 1
            ) mr ON true
            ORDER BY mc.created_at DESC
        """, conn)
        return df
    finally:
        conn.close()


def load_model_result(config_id: int) -> dict | None:
    """指定 config_id の最新モデル設定と結果を返す

    Returns
    -------
    dict or None
        キー: config_id, model_name, target_variable, feature_variables,
              hyperparameters, frequency,
              metrics, coefficients, result_id
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    mc.config_id, mc.dataset_id, mc.model_name, mc.target_variable,
                    mc.feature_variables, mc.hyperparameters, mc.frequency,
                    mr.metrics, mr.coefficients, mr.result_id
                FROM model_configs mc
                LEFT JOIN LATERAL (
                    SELECT result_id, metrics, coefficients
                    FROM model_results
                    WHERE config_id = mc.config_id
                    ORDER BY run_date DESC
                    LIMIT 1
                ) mr ON true
                WHERE mc.config_id = %s
            """, (config_id,))
            row = cur.fetchone()
            if row is None:
                return None
            col_names = [desc[0] for desc in cur.description]
            return dict(zip(col_names, row))
    finally:
        conn.close()


def delete_model_config(config_id: int) -> None:
    """モデル設定と関連する実行結果を削除する"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM model_results WHERE config_id = %s", (config_id,))
            cur.execute("DELETE FROM model_configs WHERE config_id = %s", (config_id,))
        conn.commit()
    finally:
        conn.close()


# ============================================================
# ARIMA予測（arima_forecasts）
# ============================================================

def save_arima_forecast(forecast_dict: dict) -> int:
    """ARIMA予測結果をDBに保存し、forecast_id を返す

    Parameters
    ----------
    forecast_dict : dict
        必須キー: indicator_code, arima_order, forecast_steps, forecast_data
          forecast_data: {"index": [...], "forecast": [...], "lower": [...], "upper": [...]}
        任意キー: dataset_id, frequency, scenario_label, note

    Returns
    -------
    int
        登録されたforecast_id
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO arima_forecasts
                    (indicator_code, dataset_id, frequency, arima_order,
                     forecast_steps, forecast_data, scenario_label, note)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                RETURNING forecast_id
            """, (
                forecast_dict["indicator_code"],
                forecast_dict.get("dataset_id"),
                forecast_dict.get("frequency", ""),
                forecast_dict["arima_order"],
                forecast_dict["forecast_steps"],
                json.dumps(forecast_dict["forecast_data"]),
                forecast_dict.get("scenario_label", ""),
                forecast_dict.get("note", ""),
            ))
            forecast_id = cur.fetchone()[0]
        conn.commit()
        return forecast_id
    finally:
        conn.close()


def load_arima_forecasts(
    indicator_code: str | None = None,
    dataset_id: int | None = None,
) -> pd.DataFrame:
    """保存済みARIMA予測一覧を返す

    Parameters
    ----------
    indicator_code : str or None
        指定した場合はその指標コードのみ返す
    dataset_id : int or None
        指定した場合はそのデータセットIDのみ返す

    Returns
    -------
    pd.DataFrame
        カラム: forecast_id, indicator_code, dataset_id, frequency, arima_order,
                forecast_steps, scenario_label, note, created_at
    """
    conditions = []
    params = []
    if indicator_code:
        conditions.append("indicator_code = %s")
        params.append(indicator_code)
    if dataset_id is not None:
        conditions.append("dataset_id = %s")
        params.append(dataset_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT forecast_id, indicator_code, dataset_id, frequency, arima_order,
               forecast_steps, scenario_label, note, created_at
        FROM arima_forecasts
        {where}
        ORDER BY created_at DESC
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


def delete_arima_forecast(forecast_id: int) -> None:
    """ARIMA予測結果を削除する"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM arima_forecasts WHERE forecast_id = %s", (forecast_id,))
        conn.commit()
    finally:
        conn.close()


def load_arima_forecast_data(forecast_id: int) -> pd.DataFrame:
    """指定 forecast_id の予測データを返す

    Returns
    -------
    pd.DataFrame
        カラム: forecast, lower, upper（インデックス=時点）
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT forecast_data, arima_order, indicator_code, frequency
                FROM arima_forecasts
                WHERE forecast_id = %s
            """, (forecast_id,))
            row = cur.fetchone()
            if row is None:
                return pd.DataFrame()
            fc_dict = row[0]  # psycopg2はJSONBをdictで返す
            # {"index": [...], "forecast": [...], "lower": [...], "upper": [...]}
            idx = pd.to_datetime(fc_dict["index"])
            df = pd.DataFrame({
                "forecast": fc_dict["forecast"],
                "lower": fc_dict["lower"],
                "upper": fc_dict["upper"],
            }, index=idx)
            return df
    finally:
        conn.close()


# ============================================================
# ECL結果（ecl_results）
# ============================================================

def save_ecl_result(ecl_dict: dict) -> int:
    """ECL計算結果をDBに保存し、ecl_id を返す

    Parameters
    ----------
    ecl_dict : dict
        必須キー: target_code, weight_base, weight_upside, weight_downside, results
        任意キー: model_config_id, target_dataset_id, segment_code,
                  fiscal_year_month, note

    Returns
    -------
    int
        登録されたecl_id
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ecl_results
                    (model_config_id, target_dataset_id, segment_code, target_code,
                     fiscal_year_month, weight_base, weight_upside, weight_downside,
                     results, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                RETURNING ecl_id
            """, (
                ecl_dict.get("model_config_id"),
                ecl_dict.get("target_dataset_id"),
                ecl_dict.get("segment_code", "all"),
                ecl_dict["target_code"],
                ecl_dict.get("fiscal_year_month"),
                ecl_dict["weight_base"],
                ecl_dict["weight_upside"],
                ecl_dict["weight_downside"],
                json.dumps(ecl_dict["results"]),
                ecl_dict.get("note", ""),
            ))
            ecl_id = cur.fetchone()[0]
        conn.commit()
        return ecl_id
    finally:
        conn.close()


def load_ecl_results(fiscal_year_month=None) -> pd.DataFrame:
    """保存済みECL計算結果一覧を返す

    Parameters
    ----------
    fiscal_year_month : date or str or None
        指定した場合はその決算年月のみ返す

    Returns
    -------
    pd.DataFrame
        カラム: ecl_id, target_code, segment_code, weight_base, weight_upside,
                weight_downside, fiscal_year_month, note, created_at,
                model_name, config_id
    """
    base_query = """
        SELECT
            er.ecl_id,
            er.target_code,
            er.segment_code,
            er.weight_base,
            er.weight_upside,
            er.weight_downside,
            er.fiscal_year_month,
            er.note,
            er.created_at,
            mc.model_name,
            mc.config_id
        FROM ecl_results er
        LEFT JOIN model_configs mc ON er.model_config_id = mc.config_id
    """
    if fiscal_year_month is not None:
        query = base_query + " WHERE er.fiscal_year_month = %s ORDER BY er.created_at DESC"
        params = (fiscal_year_month,)
    else:
        query = base_query + " ORDER BY er.created_at DESC"
        params = ()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            cols = [desc[0] for desc in cur.description]
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()


def list_ecl_fiscal_year_months() -> list:
    """保存済みECL結果に含まれる決算年月の一覧を返す（降順）"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT fiscal_year_month
                FROM ecl_results
                ORDER BY fiscal_year_month DESC
            """)
            return [row[0] for row in cur.fetchall()]
    finally:
        conn.close()


def delete_ecl_result(ecl_id: int) -> None:
    """ECL計算結果を削除する"""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ecl_results WHERE ecl_id = %s", (ecl_id,))
        conn.commit()
    finally:
        conn.close()


def load_ecl_result_detail(ecl_id: int) -> list | None:
    """ECL計算結果の詳細（results JSONB）を返す

    Returns
    -------
    list or None
        例: [{"period": "2026-12-31", "pd_base": 0.02, ...}, ...]
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT results FROM ecl_results WHERE ecl_id = %s", (ecl_id,))
            row = cur.fetchone()
        if row is None:
            return None
        results = row[0]
        if isinstance(results, str):
            results = json.loads(results)
        return results
    finally:
        conn.close()
