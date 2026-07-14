from __future__ import annotations

import json
import time
import uuid

import pandas as pd

from services.data_utils import normalize_id, now_jst_iso, safe_int
from services.forecast_service import calculate_jit_peaks
from services.master_service import get_manufacturers, get_product, get_product_bom, product_manufacturer_mapping
from services.product_forecast_service import get_product_forecast
from services.storage_service import get_connection, init_db


def _manufacturer_name(manufacturer_id: str) -> str | None:
    for item in get_manufacturers():
        if item["manufacturer_id"] == manufacturer_id:
            return item["manufacturer_name"]
    return None


def run_production_notice_simulation(payload: dict) -> dict:
    started = time.perf_counter()
    init_db()
    factory_id = normalize_id(payload["factory_id"])
    manufacturer_id = normalize_id(payload["manufacturer_id"])
    rate = float(payload["adjustment_rate"])
    if rate < -50 or rate > 50:
        raise ValueError("adjustment_rateは-50〜50で指定してください")
    target_type = payload.get("target_type") or "product"
    target_id = normalize_id(payload.get("target_id")) if payload.get("target_id") else None
    manufacturer_name = _manufacturer_name(manufacturer_id)
    if not manufacturer_name:
        raise LookupError("指定されたメーカーIDが存在しません")
    mapping = product_manufacturer_mapping()
    if mapping.empty:
        raise LookupError("メーカー製品マッピングが存在しません")
    mapping = mapping[mapping["manufacturer_id"] == manufacturer_id].copy()
    if target_id:
        mapping = mapping[mapping["product_id"] == target_id]
    if mapping.empty:
        raise LookupError("対象メーカーに紐づく製品がありません")
    affected_products = []
    parts_totals: dict[str, dict] = {}
    chart_by_date: dict[str, dict] = {}
    for _, map_row in mapping.iterrows():
        product_id = map_row["product_id"]
        product = get_product(product_id)
        if not product or product["factory_id"] != factory_id:
            continue
        allocation = float(map_row["allocation_ratio"])
        forecast = get_product_forecast(factory_id, product_id)
        if not forecast:
            continue
        product_chart = []
        normal_sum = 0
        adjusted_sum = 0
        for point in forecast["forecast_chart"]:
            normal = point.get("normal_forecast")
            if normal is None:
                product_chart.append({**point, "adjusted_forecast": None, "difference": None, "difference_rate": None})
                continue
            adjusted = round(normal * (1 - allocation) + normal * allocation * (1 + rate / 100))
            diff = adjusted - normal
            normal_sum += normal
            adjusted_sum += adjusted
            product_chart.append(
                {
                    **point,
                    "adjusted_forecast": adjusted,
                    "difference": diff,
                    "difference_rate": 0 if normal == 0 else round(diff / normal * 100, 2),
                }
            )
            chart_by_date.setdefault(point["date"], {"date": point["date"], "normal_forecast": 0, "adjusted_forecast": 0, "safety_stock": 0})
            chart_by_date[point["date"]]["normal_forecast"] += normal
            chart_by_date[point["date"]]["adjusted_forecast"] += adjusted
        affected_products.append(
            {
                "product_id": product_id,
                "product_name": product["product_name"],
                "allocation_ratio": allocation,
                "normal_total": normal_sum,
                "adjusted_total": adjusted_sum,
                "difference": adjusted_sum - normal_sum,
                "forecast_chart": product_chart,
            }
        )
        for bom in get_product_bom(product_id):
            q = safe_int(bom.get("quantity_per_product"), 1)
            key = bom["parts_id"]
            parts_totals.setdefault(
                key,
                {
                    "parts_id": key,
                    "parts_name": bom.get("parts_name", ""),
                    "normal_demand": 0,
                    "adjusted_demand": 0,
                    "difference": 0,
                    "source_products": [],
                },
            )
            normal_part = normal_sum * q
            adjusted_part = adjusted_sum * q
            parts_totals[key]["normal_demand"] += normal_part
            parts_totals[key]["adjusted_demand"] += adjusted_part
            parts_totals[key]["difference"] += adjusted_part - normal_part
            parts_totals[key]["source_products"].append(product_id)
    if not affected_products:
        raise LookupError("対象工場・メーカーに一致する製品予測がありません")
    for item in chart_by_date.values():
        item["difference"] = item["adjusted_forecast"] - item["normal_forecast"]
        item["difference_rate"] = 0 if item["normal_forecast"] == 0 else round(item["difference"] / item["normal_forecast"] * 100, 2)
    forecast_chart = sorted(chart_by_date.values(), key=lambda row: row["date"])
    affected_parts = sorted(parts_totals.values(), key=lambda row: row["parts_id"])
    next_week_product_chart = [
        point for product in affected_products for point in product["forecast_chart"] if point.get("normal_forecast") is not None
    ]
    next_week_scale = 1.0
    if next_week_product_chart:
        first_point = sorted(next_week_product_chart, key=lambda row: row["date"])[0]
        if first_point.get("normal_forecast"):
            next_week_scale = first_point["adjusted_forecast"] / first_point["normal_forecast"]
    for part in affected_parts:
        original_next_week = safe_int(part["normal_demand"] / 4)
        adjusted_next_week = safe_int(original_next_week * next_week_scale)
        original_jit = calculate_jit_peaks(factory_id, part["parts_id"], original_next_week)["peak_data"]
        adjusted_jit = calculate_jit_peaks(factory_id, part["parts_id"], adjusted_next_week)["peak_data"]
        adjusted_lookup = {(item["day"], item["hour"]): item for item in adjusted_jit}
        part["original_next_week_volume"] = original_next_week
        part["adjusted_next_week_volume"] = adjusted_next_week
        part["jit_peaks"] = [
            {
                "day": item["day"],
                "hour": item["hour"],
                "original_volume": item["volume"],
                "adjusted_volume": adjusted_lookup.get((item["day"], item["hour"]), {}).get("volume", 0),
            }
            for item in original_jit
        ]
    normal_total = sum(p["normal_total"] for p in affected_products)
    adjusted_total = sum(p["adjusted_total"] for p in affected_products)
    next_product = affected_products[0]
    next_normal = next_product["forecast_chart"][-4]["normal_forecast"] if len(next_product["forecast_chart"]) >= 4 else next_product["normal_total"]
    next_adjusted = next_product["forecast_chart"][-4]["adjusted_forecast"] if len(next_product["forecast_chart"]) >= 4 else next_product["adjusted_total"]
    direction = "増産" if rate > 0 else "減産" if rate < 0 else "変更なし"
    summary = (
        f"{manufacturer_name}から{abs(rate):.0f}%の{direction}内示を受けた場合、"
        f"{next_product['product_id']}の次週需要は{safe_int(next_normal):,}個から{safe_int(next_adjusted):,}個へ"
        f"{abs(safe_int(next_adjusted - next_normal)):,}個{'増加' if next_adjusted >= next_normal else '減少'}します。"
    )
    result = {
        "manufacturer_id": manufacturer_id,
        "manufacturer_name": manufacturer_name,
        "adjustment_rate": rate,
        "direction": direction,
        "calculation_time_ms": round((time.perf_counter() - started) * 1000, 2),
        "affected_products": affected_products,
        "affected_parts": affected_parts,
        "forecast_chart": forecast_chart,
        "normal_total": normal_total,
        "adjusted_total": adjusted_total,
        "difference": adjusted_total - normal_total,
        "summary": summary,
    }
    simulation_id = f"SIM-{uuid.uuid4().hex[:12]}"
    executed_at = now_jst_iso()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO production_notice_history
            (simulation_id, executed_at, factory_id, manufacturer_id, adjustment_rate, target_type, target_id,
             normal_total, adjusted_total, difference, calculation_time_ms, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                simulation_id,
                executed_at,
                factory_id,
                manufacturer_id,
                rate,
                target_type,
                target_id,
                normal_total,
                adjusted_total,
                adjusted_total - normal_total,
                result["calculation_time_ms"],
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
    result["simulation_id"] = simulation_id
    result["executed_at"] = executed_at
    return result


def get_production_notice_history(limit: int = 20) -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM production_notice_history ORDER BY executed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_production_notice_history(simulation_id: str) -> bool:
    init_db()
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM production_notice_history WHERE simulation_id = ?", (simulation_id,))
        conn.commit()
        return cur.rowcount > 0
