from __future__ import annotations

import pandas as pd

from services.data_utils import normalize_id, read_csv, safe_int
from services.evaluation_service import evaluate_timeseries, forecast_next_values
from services.indicator_service import external_indicator_multiplier, get_realtime_indicators
from services.master_service import get_product, get_product_bom
from services.safety_stock_service import get_current_safety_stock_map


def _product_history(factory_id: str, product_id: str) -> pd.DataFrame:
    df = read_csv("product_demand_history.csv")
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["week_start_date"])
    df["demand"] = df["order_volume"]
    return df[(df["factory_id"] == factory_id) & (df["product_id"] == product_id)].copy()


def get_product_forecast(factory_id: str, product_id: str) -> dict | None:
    fid = normalize_id(factory_id)
    pid = normalize_id(product_id)
    product = get_product(pid)
    if not product or product["factory_id"] != fid:
        return None
    history = _product_history(fid, pid)
    if history.empty:
        return None
    indicators = get_realtime_indicators()
    multiplier = external_indicator_multiplier(indicators)
    forecasts = [safe_int(v * multiplier) for v in forecast_next_values(history, periods=4, value_col="demand")]
    last_date = history["date"].max()
    safety_map = get_current_safety_stock_map(fid)
    bom = get_product_bom(pid)
    product_current_stock_candidates = []
    product_safety_stock_candidates = []
    for item in bom:
        q = max(1, safe_int(item.get("quantity_per_product"), 1))
        part_safety = safety_map.get(item["parts_id"], {})
        product_current_stock_candidates.append(safe_int(part_safety.get("current_stock")) // q)
        product_safety_stock_candidates.append(safe_int(part_safety.get("safety_stock_quantity")) // q)
    product_current_stock = min(product_current_stock_candidates) if product_current_stock_candidates else 0
    product_safety_stock = max(product_safety_stock_candidates) if product_safety_stock_candidates else 0
    next_week_forecast = forecasts[0]
    recommended_product_production = max(0, next_week_forecast + product_safety_stock - product_current_stock)
    recommended_product_order = recommended_product_production
    recommended_product_shipping = next_week_forecast
    chart = []
    for _, row in history.tail(4).iterrows():
        chart.append(
            {
                "date": row["date"].strftime("%Y-%m-%d"),
                "actual": safe_int(row["demand"]),
                "normal_forecast": None,
                "forecast": None,
                "adjusted_forecast": None,
                "safety_stock": None,
                "current_stock": None,
            }
        )
    for idx, value in enumerate(forecasts, start=1):
        chart.append(
            {
                "date": (last_date + pd.Timedelta(weeks=idx)).strftime("%Y-%m-%d"),
                "actual": None,
                "normal_forecast": value,
                "forecast": value,
                "adjusted_forecast": None,
                "safety_stock": product_safety_stock,
                "current_stock": product_current_stock,
            }
        )
    component_forecasts = []
    for item in bom:
        q = safe_int(item.get("quantity_per_product"), 1)
        part_safety = safety_map.get(item["parts_id"], {})
        part_chart = []
        for point in chart:
            normal = point["normal_forecast"]
            part_chart.append(
                {
                    "date": point["date"],
                    "actual": None if point["actual"] is None else point["actual"] * q,
                    "normal_forecast": None if normal is None else normal * q,
                    "forecast": None if normal is None else normal * q,
                    "adjusted_forecast": None,
                    "safety_stock": part_safety.get("safety_stock_quantity"),
                    "current_stock": part_safety.get("current_stock"),
                }
            )
        next_week = forecasts[0] * q
        four_weeks = sum(forecasts) * q
        current_stock = safe_int(part_safety.get("current_stock"))
        safety_stock = safe_int(part_safety.get("safety_stock_quantity"))
        recommended_production = max(0, next_week + safety_stock - current_stock)
        component_forecasts.append(
            {
                "parts_id": item["parts_id"],
                "parts_name": item.get("parts_name", ""),
                "quantity_per_product": q,
                "next_week_forecast": next_week,
                "parts_demand": next_week,
                "recommended_production": recommended_production,
                "recommended_order": recommended_production,
                "recommended_shipping": next_week,
                "next_week_required": next_week,
                "four_week_required": four_weeks,
                "current_stock": current_stock,
                "dynamic_safety_stock": safety_stock,
                "shortage": max(0, next_week + safety_stock - current_stock),
                "lead_time_weeks": item.get("lead_time_weeks", ""),
                "forecast_chart": part_chart,
                "note": "選択製品由来の必要数です",
            }
        )
    return {
        "target_type": "product",
        "factory_id": fid,
        "product_id": pid,
        "product_name": product["product_name"],
        "manufacturer_id": product.get("manufacturer_id"),
        "manufacturer_name": product.get("manufacturer_name"),
        "next_week_forecast": next_week_forecast,
        "current_stock": product_current_stock,
        "safety_stock": product_safety_stock,
        "recommended_production": recommended_product_production,
        "recommended_order": recommended_product_order,
        "recommended_shipping": recommended_product_shipping,
        "risk_level": "CRITICAL"
        if product_current_stock < product_safety_stock
        else "WARNING"
        if product_current_stock > max(product_safety_stock * 8, next_week_forecast * 6)
        else "HEALTHY",
        "risk_message": "製品換算在庫が動的安全在庫を下回っています。"
        if product_current_stock < product_safety_stock
        else "製品換算在庫が倉庫上限目安を超える可能性があります。"
        if product_current_stock > max(product_safety_stock * 8, next_week_forecast * 6)
        else "製品換算在庫は安全範囲です。",
        "indicators": indicators,
        "current_indicators": indicators,
        "model_description": "外部API指標（ドル円、PMI、気象）を特徴量・補正係数として掛け合わせ、Prophet 0.4（中長期トレンド/季節性）とXGBoost 0.6（短期ラグ/外部指標）のアンサンブル思想で予測します。",
        "forecast_chart": chart,
        "component_forecasts": component_forecasts,
        "bom": bom,
        "model_evaluation": evaluate_timeseries(history, value_col="demand"),
    }
