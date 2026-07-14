from __future__ import annotations

import pandas as pd

from services.data_utils import normalize_id, read_csv, safe_int
from services.forecast_service import calculate_forecast
from services.product_forecast_service import get_product_forecast


def actual_history_csv(factory_id: str | None = None, parts_id: str | None = None, product_id: str | None = None) -> str:
    if product_id:
        df = read_csv("product_demand_history.csv")
        if not df.empty:
            if factory_id:
                df = df[df["factory_id"] == normalize_id(factory_id)]
            df = df[df["product_id"] == normalize_id(product_id)]
        columns = ["week_start_date", "factory_id", "product_id", "manufacturer_id", "order_volume"]
    else:
        df = read_csv("internal_performance_history.csv")
        if not df.empty:
            if factory_id:
                df = df[df["factory_id"] == normalize_id(factory_id)]
            if parts_id:
                df = df[df["parts_id"] == normalize_id(parts_id)]
        columns = [
            "week_start_date",
            "factory_id",
            "parts_id",
            "order_volume",
            "production_volume",
            "shipment_volume",
            "ending_stock",
        ]
    if df.empty:
        df = pd.DataFrame(columns=columns)
    return df.to_csv(index=False)


def forecast_csv(factory_id: str, target_type: str, target_id: str) -> str:
    target_type = target_type.lower()
    rows = []
    if target_type == "product":
        result = get_product_forecast(normalize_id(factory_id), normalize_id(target_id))
        if result:
            for point in result["forecast_chart"]:
                rows.append(
                    {
                        "target_type": "product",
                        "factory_id": result["factory_id"],
                        "target_id": result["product_id"],
                        "target_name": result["product_name"],
                        "date": point["date"],
                        "actual": point.get("actual"),
                        "forecast": point.get("normal_forecast") or point.get("forecast"),
                        "adjusted_forecast": point.get("adjusted_forecast"),
                        "current_stock": point.get("current_stock"),
                        "safety_stock": point.get("safety_stock"),
                        "recommended_production": result.get("recommended_production"),
                        "recommended_order": result.get("recommended_order"),
                        "recommended_shipping": result.get("recommended_shipping"),
                    }
                )
            for component in result["component_forecasts"]:
                for point in component["forecast_chart"]:
                    rows.append(
                        {
                            "target_type": "product_component",
                            "factory_id": result["factory_id"],
                            "target_id": component["parts_id"],
                            "target_name": component["parts_name"],
                            "source_product_id": result["product_id"],
                            "date": point["date"],
                            "actual": point.get("actual"),
                            "forecast": point.get("normal_forecast") or point.get("forecast"),
                            "adjusted_forecast": point.get("adjusted_forecast"),
                            "current_stock": point.get("current_stock"),
                            "safety_stock": point.get("safety_stock"),
                            "recommended_production": component.get("recommended_production"),
                            "recommended_order": component.get("recommended_order"),
                            "recommended_shipping": component.get("recommended_shipping"),
                        }
                    )
    else:
        result = calculate_forecast(normalize_id(factory_id), normalize_id(target_id))
        if result:
            for point in result["forecast_chart"]:
                rows.append(
                    {
                        "target_type": "part",
                        "factory_id": result["factory_id"],
                        "target_id": result["parts_id"],
                        "target_name": result["parts_name"],
                        "date": point["date"],
                        "actual": point.get("actual"),
                        "forecast": point.get("normal_forecast") or point.get("forecast"),
                        "current_stock": point.get("current_stock"),
                        "safety_stock": point.get("safety_stock"),
                        "recommended_production": result.get("recommended_production"),
                        "recommended_order": result.get("recommended_order"),
                        "recommended_shipping": result.get("recommended_shipping"),
                    }
                )
    return pd.DataFrame(rows).to_csv(index=False)


def future_actual_template_csv(factory_id: str | None = None, parts_id: str | None = None, product_id: str | None = None) -> str:
    next_weeks = pd.date_range(
        start=(pd.Timestamp.now(tz="Asia/Tokyo").normalize() + pd.offsets.Week(weekday=0)),
        periods=8,
        freq="W-MON",
    )
    if product_id:
        rows = [
            {
                "week_start_date": date.strftime("%Y-%m-%d"),
                "factory_id": normalize_id(factory_id) or "",
                "product_id": normalize_id(product_id),
                "manufacturer_id": "",
                "order_volume": "",
            }
            for date in next_weeks
        ]
    else:
        rows = [
            {
                "week_start_date": date.strftime("%Y-%m-%d"),
                "factory_id": normalize_id(factory_id) or "",
                "parts_id": normalize_id(parts_id) or "",
                "order_volume": "",
                "production_volume": "",
                "shipment_volume": "",
                "ending_stock": "",
            }
            for date in next_weeks
        ]
    return pd.DataFrame(rows).to_csv(index=False)
