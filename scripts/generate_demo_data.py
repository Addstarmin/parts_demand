from __future__ import annotations

import argparse
import math
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "data"
DB_PATH = DATA_DIR / "cmdx.sqlite3"
SEED = 42
BASE_DATE = pd.Timestamp("2026-07-06")
START_DATE = BASE_DATE - pd.Timedelta(weeks=155)
JST_UPDATED_AT = "2026-07-01T00:00:00+09:00"


@dataclass(frozen=True)
class ProductProfile:
    base: int
    trend: float
    volatility: float
    phase: float
    maker_bias: float


@dataclass(frozen=True)
class PartProfile:
    lead_time_weeks: int
    safety_stock_days: int
    lot_size: int
    stock_weeks: float
    supply_risk: float
    usage_type: str


PRODUCT_PROFILES = {
    "PROD-A": ProductProfile(base=1040, trend=0.00045, volatility=0.035, phase=0.1, maker_bias=1.05),
    "PROD-B": ProductProfile(base=650, trend=0.0012, volatility=0.045, phase=0.6, maker_bias=0.98),
    "PROD-C": ProductProfile(base=510, trend=0.00025, volatility=0.03, phase=1.2, maker_bias=1.02),
    "PROD-D": ProductProfile(base=560, trend=0.00065, volatility=0.05, phase=2.4, maker_bias=1.0),
}

PART_PROFILES = {
    "PT-1002": PartProfile(lead_time_weeks=1, safety_stock_days=7, lot_size=100, stock_weeks=0.82, supply_risk=0.9, usage_type="shared_stable"),
    "PT-1003": PartProfile(lead_time_weeks=2, safety_stock_days=12, lot_size=80, stock_weeks=1.35, supply_risk=1.05, usage_type="dedicated_mid"),
    "PT-2005": PartProfile(lead_time_weeks=3, safety_stock_days=14, lot_size=60, stock_weeks=0.9, supply_risk=1.35, usage_type="electronics_risk"),
    "PT-3001": PartProfile(lead_time_weeks=2, safety_stock_days=10, lot_size=120, stock_weeks=1.65, supply_risk=1.15, usage_type="machined"),
    "PT-4002": PartProfile(lead_time_weeks=1, safety_stock_days=8, lot_size=100, stock_weeks=1.1, supply_risk=0.75, usage_type="short_lt"),
    "PT-5007": PartProfile(lead_time_weeks=4, safety_stock_days=16, lot_size=50, stock_weeks=1.75, supply_risk=1.25, usage_type="shared_long_lt"),
}


def write_csv(df: pd.DataFrame, name: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_DIR / name, index=False)


def round_lot(value: float, lot_size: int) -> int:
    return int(math.ceil(max(0, value) / lot_size) * lot_size) if value > 0 else 0


def holiday_factor(week: pd.Timestamp) -> float:
    start = week
    end = week + pd.Timedelta(days=6)
    factor = 1.0
    windows = [
        (pd.Timestamp(f"{year}-01-01"), 0.56, 1.12, 1.05) for year in range(2024, 2027)
    ]
    windows += [
        (pd.Timestamp(f"{year}-05-03"), 0.62, 1.10, 1.06) for year in range(2024, 2027)
    ]
    windows += [
        (pd.Timestamp(f"{year}-08-13"), 0.52, 1.08, 1.07) for year in range(2024, 2027)
    ]
    windows += [
        (pd.Timestamp(f"{year}-12-29"), 0.58, 1.12, 1.04) for year in range(2024, 2027)
    ]
    for holiday, during, before, after in windows:
        if start <= holiday <= end:
            factor *= during
        elif start <= holiday - pd.Timedelta(days=7) <= end:
            factor *= before
        elif start <= holiday + pd.Timedelta(days=7) <= end:
            factor *= after
    return factor


def calendar_factor(week: pd.Timestamp) -> float:
    month = week.month
    factor = 1.0
    factor *= 1 + 0.035 * math.sin(2 * math.pi * (week.dayofyear - 18) / 365)
    if month in (2, 3):
        factor *= 1.08 if month == 3 else 1.035
    if month == 4:
        factor *= 0.94
    if month == 6:
        factor *= 1.06
    if month == 7:
        factor *= 1.03
    if month == 9:
        factor *= 1.08
    if month in (10, 11):
        factor *= 1.0
    if month == 12 and week.day <= 15:
        factor *= 1.08
    return factor * holiday_factor(week)


def external_indicator_rows(weeks: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for idx, week in enumerate(weeks):
        usd_jpy = 148.0 + 3.5 * math.sin(idx / 12) + 0.018 * idx
        pmi = 50.5 + 1.4 * math.sin(idx / 10 + 0.6)
        temperature = 16 + 11 * math.sin(2 * math.pi * (week.dayofyear - 105) / 365)
        rows.append({"week_start_date": week, "usd_jpy": usd_jpy, "pmi": pmi, "temperature": temperature})
    return pd.DataFrame(rows)


def product_volume(product_id: str, week: pd.Timestamp, idx: int, rng: np.random.Generator, indicators: dict) -> int:
    p = PRODUCT_PROFILES[product_id]
    trend = 1 + p.trend * idx
    annual = 1 + 0.055 * math.sin(2 * math.pi * (week.dayofyear / 365) + p.phase)
    quarter = 1.045 if week.month in (3, 6, 9, 12) and week.day >= 15 else 1.0
    maker_event = 1.0
    if pd.Timestamp("2025-02-10") <= week <= pd.Timestamp("2025-03-17") and product_id in {"PROD-A", "PROD-C"}:
        maker_event *= 1.08
    if pd.Timestamp("2025-10-06") <= week <= pd.Timestamp("2025-10-27") and product_id == "PROD-B":
        maker_event *= 0.92
    if pd.Timestamp("2026-02-02") <= week <= pd.Timestamp("2026-02-16") and product_id == "PROD-D":
        maker_event *= 1.10
    product_shape = 1.0
    if product_id == "PROD-D" and week.month in (6, 7, 8):
        product_shape *= 1.16
    if product_id == "PROD-B":
        product_shape *= 1 + min(0.08, idx * 0.00035)
    macro = 1 + (indicators["pmi"] - 50) * 0.006 + max(0, indicators["usd_jpy"] - 152) * 0.002
    noise = rng.normal(0, p.base * p.volatility)
    demand = p.base * trend * annual * quarter * calendar_factor(week) * p.maker_bias * maker_event * product_shape * macro + noise
    return max(30, int(round(demand)))


def build_masters() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    factories = pd.DataFrame(
        [
            {"factory_id": "F-01", "factory_name": "名古屋第一工場", "location": "愛知県名古屋市"},
            {"factory_id": "F-02", "factory_name": "三河精密工場", "location": "愛知県豊田市"},
            {"factory_id": "F-03", "factory_name": "豊田アセンブリ工場", "location": "愛知県豊田市"},
        ]
    )
    parts = pd.DataFrame(
        [
            {"parts_id": pid, "parts_name": name, "lead_time_weeks": prof.lead_time_weeks, "safety_stock_days": prof.safety_stock_days}
            for pid, name, prof in [
                ("PT-1002", "キャブレターボルト", PART_PROFILES["PT-1002"]),
                ("PT-1003", "インテークマニホールド", PART_PROFILES["PT-1003"]),
                ("PT-2005", "制御基板", PART_PROFILES["PT-2005"]),
                ("PT-3001", "油圧バルブ", PART_PROFILES["PT-3001"]),
                ("PT-4002", "冷却ファン", PART_PROFILES["PT-4002"]),
                ("PT-5007", "センサーケーブル", PART_PROFILES["PT-5007"]),
            ]
        ]
    )
    manufacturers = pd.DataFrame(
        [
            {"manufacturer_id": "M-A", "manufacturer_name": "完成車A社", "description": "授業用の架空完成車メーカー"},
            {"manufacturer_id": "M-B", "manufacturer_name": "完成車B社", "description": "授業用の架空完成車メーカー"},
            {"manufacturer_id": "M-C", "manufacturer_name": "完成車C社", "description": "授業用の架空完成車メーカー"},
        ]
    )
    products = pd.DataFrame(
        [
            {"product_id": "PROD-A", "product_name": "キャブレターASSY", "factory_id": "F-02", "manufacturer_id": "M-A", "unit_price": 15000, "description": "小型エンジン向け吸気系アセンブリ"},
            {"product_id": "PROD-B", "product_name": "エンジン制御ASSY", "factory_id": "F-02", "manufacturer_id": "M-B", "unit_price": 22000, "description": "制御基板とセンサーを組み込んだ制御ユニット"},
            {"product_id": "PROD-C", "product_name": "ブレーキ制御ASSY", "factory_id": "F-03", "manufacturer_id": "M-A", "unit_price": 28000, "description": "複数メーカーへ配分納入する制御系アセンブリ"},
            {"product_id": "PROD-D", "product_name": "冷却ユニットASSY", "factory_id": "F-01", "manufacturer_id": "M-C", "unit_price": 18000, "description": "冷却ファンと配線を含む熱対策ユニット"},
        ]
    )
    bom = pd.DataFrame(
        [
            {"product_id": "PROD-A", "parts_id": "PT-1002", "quantity_per_product": 2},
            {"product_id": "PROD-A", "parts_id": "PT-1003", "quantity_per_product": 1},
            {"product_id": "PROD-A", "parts_id": "PT-2005", "quantity_per_product": 1},
            {"product_id": "PROD-B", "parts_id": "PT-2005", "quantity_per_product": 2},
            {"product_id": "PROD-B", "parts_id": "PT-3001", "quantity_per_product": 2},
            {"product_id": "PROD-B", "parts_id": "PT-5007", "quantity_per_product": 1},
            {"product_id": "PROD-C", "parts_id": "PT-1002", "quantity_per_product": 4},
            {"product_id": "PROD-C", "parts_id": "PT-3001", "quantity_per_product": 1},
            {"product_id": "PROD-C", "parts_id": "PT-5007", "quantity_per_product": 2},
            {"product_id": "PROD-D", "parts_id": "PT-4002", "quantity_per_product": 2},
            {"product_id": "PROD-D", "parts_id": "PT-5007", "quantity_per_product": 1},
        ]
    )
    mapping = pd.DataFrame(
        [
            {"manufacturer_id": "M-A", "product_id": "PROD-A", "allocation_ratio": 1.0},
            {"manufacturer_id": "M-A", "product_id": "PROD-C", "allocation_ratio": 0.6},
            {"manufacturer_id": "M-B", "product_id": "PROD-B", "allocation_ratio": 1.0},
            {"manufacturer_id": "M-C", "product_id": "PROD-C", "allocation_ratio": 0.4},
            {"manufacturer_id": "M-C", "product_id": "PROD-D", "allocation_ratio": 1.0},
        ]
    )
    return factories, parts, manufacturers, products, bom, mapping


def build_product_history(products: pd.DataFrame, weeks: pd.DatetimeIndex, rng: np.random.Generator) -> pd.DataFrame:
    indicators = external_indicator_rows(weeks).set_index("week_start_date")
    rows = []
    for _, product in products.iterrows():
        for idx, week in enumerate(weeks):
            ind = indicators.loc[week].to_dict()
            rows.append(
                {
                    "week_start_date": week.strftime("%Y-%m-%d"),
                    "factory_id": product["factory_id"],
                    "product_id": product["product_id"],
                    "manufacturer_id": product["manufacturer_id"],
                    "order_volume": product_volume(product["product_id"], week, idx, rng, ind),
                }
            )
    return pd.DataFrame(rows)


def factory_product_map(products: pd.DataFrame) -> dict[str, list[str]]:
    return products.groupby("factory_id")["product_id"].apply(list).to_dict()


def part_demand_for(factory_id: str, part_id: str, week_str: str, product_history: pd.DataFrame, products: pd.DataFrame, bom: pd.DataFrame) -> int:
    total = 0
    product_ids = products[products["factory_id"] == factory_id]["product_id"].tolist()
    for product_id in product_ids:
        qty = bom[(bom["product_id"] == product_id) & (bom["parts_id"] == part_id)]
        if qty.empty:
            continue
        demand = int(product_history[(product_history["week_start_date"] == week_str) & (product_history["product_id"] == product_id)]["order_volume"].iloc[0])
        total += demand * int(qty.iloc[0]["quantity_per_product"])
    return total


def build_internal_history(factories: pd.DataFrame, parts: pd.DataFrame, products: pd.DataFrame, bom: pd.DataFrame, product_history: pd.DataFrame, weeks: pd.DatetimeIndex, rng: np.random.Generator) -> pd.DataFrame:
    demand_lookup = {}
    for week in weeks:
        week_str = week.strftime("%Y-%m-%d")
        for factory_id in factories["factory_id"]:
            for part_id in parts["parts_id"]:
                demand_lookup[(week_str, factory_id, part_id)] = part_demand_for(factory_id, part_id, week_str, product_history, products, bom)

    rows = []
    stock = {}
    backlog = {}
    last_demands = {}
    for factory_id in factories["factory_id"]:
        for part_id in parts["parts_id"]:
            positive = [v for (w, f, p), v in demand_lookup.items() if f == factory_id and p == part_id and v > 0]
            avg = float(np.mean(positive[-12:])) if positive else 220.0
            profile = PART_PROFILES[part_id]
            multiplier = profile.stock_weeks
            if factory_id == "F-01":
                multiplier += 0.25
            if factory_id == "F-02" and part_id == "PT-1002":
                multiplier = 0.66
            if avg <= 0:
                multiplier = 0.8
            stock[(factory_id, part_id)] = max(80, int(avg * multiplier))
            backlog[(factory_id, part_id)] = 0
            last_demands[(factory_id, part_id)] = avg

    for week_idx, week in enumerate(weeks):
        week_str = week.strftime("%Y-%m-%d")
        workday_factor = holiday_factor(week)
        for factory_id in factories["factory_id"]:
            capacity_factor = {"F-01": 1.22, "F-02": 1.06, "F-03": 1.12}[factory_id]
            for part_id in parts["parts_id"]:
                demand = demand_lookup[(week_str, factory_id, part_id)]
                if demand == 0:
                    demand = max(0, int(rng.normal(70, 16))) if factory_id == "F-02" else max(0, int(rng.normal(35, 10)))
                profile = PART_PROFILES[part_id]
                key = (factory_id, part_id)
                recent = last_demands[key] * 0.65 + demand * 0.35
                target_stock = max(80, recent * profile.stock_weeks * profile.supply_risk)
                need = demand + 0.58 * (target_stock - stock[key]) + backlog[key]
                capacity = max(profile.lot_size, recent * capacity_factor * max(0.68, workday_factor))
                production = min(capacity, max(0, need + rng.normal(0, max(18, recent * 0.025))))
                production = round_lot(production, profile.lot_size)
                if production > capacity * 1.08:
                    production = round_lot(capacity, profile.lot_size)
                shipment = min(demand, max(0, stock[key] + production))
                if factory_id == "F-02":
                    shipment = min(max(0, stock[key] + production), int(round(demand * 0.99)))
                shortage = max(0, demand - shipment)
                backlog[key] = int(shortage * 0.45)
                variance = int(rng.normal(0, max(2, recent * 0.003)))
                stock[key] = max(0, int(stock[key] + production - shipment + variance))
                if factory_id == "F-02" and part_id == "PT-1002" and week_idx == len(weeks) - 1:
                    stock[key] = 1800
                rows.append(
                    {
                        "week_start_date": week_str,
                        "factory_id": factory_id,
                        "parts_id": part_id,
                        "order_volume": int(demand),
                        "production_volume": int(production),
                        "shipment_volume": int(shipment),
                        "ending_stock": int(stock[key]),
                    }
                )
                last_demands[key] = recent
    return pd.DataFrame(rows)


def build_safety_and_accuracy(factories: pd.DataFrame, parts: pd.DataFrame, internal: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    months = pd.date_range(end=pd.Timestamp("2026-07-01"), periods=12, freq="MS")
    latest = internal.sort_values("week_start_date").drop_duplicates(["factory_id", "parts_id"], keep="last")
    rmse_plan = {
        "PT-1002": [210, 170, 145, 118],
        "PT-1003": [125, 145, 172, 205],
        "PT-2005": [170, 210, 250, 310],
        "PT-3001": [260, 245, 230, 215],
        "PT-4002": [100, 90, 78, 64],
        "PT-5007": [155, 180, 220, 260],
    }
    lt_plan = {
        "PT-1002": [8, 8, 7, 6],
        "PT-1003": [13, 14, 15, 16],
        "PT-2005": [20, 22, 24, 27],
        "PT-3001": [15, 15, 14, 14],
        "PT-4002": [7, 7, 6, 6],
        "PT-5007": [27, 28, 30, 31],
    }
    old_multipliers = {"PT-1002": 1.5, "PT-1003": 0.75, "PT-2005": 0.72, "PT-3001": 1.0, "PT-4002": 1.25, "PT-5007": 0.78}
    acc_rows = []
    lt_rows = []
    dynamic_rows = []
    safety_rows = []
    for factory_id in factories["factory_id"]:
        for part_id in parts["parts_id"]:
            hist = internal[(internal["factory_id"] == factory_id) & (internal["parts_id"] == part_id)].copy()
            hist["week_start_date"] = pd.to_datetime(hist["week_start_date"])
            monthly_base = hist.groupby(pd.Grouper(key="week_start_date", freq="MS"))["order_volume"].mean()
            for idx, month in enumerate(months):
                actual_base = float(monthly_base.reindex(monthly_base.index.union([month])).interpolate().ffill().bfill().loc[month]) if len(monthly_base) else 300.0
                plan_idx = min(3, max(0, idx - 8))
                rmse_target = rmse_plan[part_id][plan_idx]
                sign = -1 if idx % 2 else 1
                error = int(sign * rmse_target * (0.82 + 0.08 * (idx % 3)))
                predicted = max(20, int(round(actual_base - error)))
                actual = max(0, predicted + error)
                acc_rows.append(
                    {
                        "forecast_date": month.strftime("%Y-%m-%d"),
                        "factory_id": factory_id,
                        "parts_id": part_id,
                        "predicted_demand": predicted,
                        "actual_demand": actual,
                        "error": actual - predicted,
                        "squared_error": (actual - predicted) ** 2,
                        "model_version": "demo-ensemble-0.4-0.6",
                    }
                )
                base_lt = lt_plan[part_id][plan_idx]
                lt = max(2, int(round(base_lt + rng.normal(0, 0.5))))
                lt_rows.append({"recorded_date": month.strftime("%Y-%m-%d"), "factory_id": factory_id, "parts_id": part_id, "lead_time_days": lt})
            recent_rmse = math.sqrt(np.mean([r["squared_error"] for r in acc_rows if r["factory_id"] == factory_id and r["parts_id"] == part_id][-4:]))
            recent_lt = np.mean([r["lead_time_days"] for r in lt_rows if r["factory_id"] == factory_id and r["parts_id"] == part_id][-4:])
            dynamic = int(math.ceil(1.65 * recent_rmse * math.sqrt(recent_lt / 7)))
            old_stock = max(100, int(dynamic * old_multipliers[part_id]))
            if factory_id == "F-02" and part_id == "PT-1002":
                dynamic = 360
                old_stock = 540
            safety_rows.append(
                {
                    "factory_id": factory_id,
                    "parts_id": part_id,
                    "safety_stock_quantity": old_stock,
                    "previous_safety_stock": max(100, int(old_stock * 1.04)),
                    "safety_factor": 1.65,
                    "service_level": 0.95,
                    "rmse": round(recent_rmse, 2),
                    "lead_time_days": round(recent_lt, 2),
                    "updated_at": JST_UPDATED_AT,
                }
            )
            dynamic_rows.append(
                {
                    "calculation_month": "2026-07",
                    "factory_id": factory_id,
                    "parts_id": part_id,
                    "ai_rmse": round(recent_rmse, 2),
                    "lead_time_days": round(recent_lt, 2),
                    "calculated_safety_stock": dynamic,
                    "updated_at": JST_UPDATED_AT,
                }
            )
    return pd.DataFrame(safety_rows), pd.DataFrame(lt_rows), pd.DataFrame(acc_rows), pd.DataFrame(dynamic_rows)


def build_jit_history(internal: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    slots = ["06:30:00", "10:00:00", "15:30:00", "20:00:00"]
    slot_ratio = {"06:30:00": 0.25, "10:00:00": 0.34, "15:30:00": 0.29, "20:00:00": 0.12}
    day_ratio = {0: 1.16, 1: 1.36, 2: 1.00, 3: 1.22, 4: 0.86, 5: 0.18, 6: 0.08}
    rows = []
    date_range = pd.date_range("2026-06-08", periods=28, freq="D")
    latest_week = internal["week_start_date"].max()
    for factory_id in sorted(internal["factory_id"].unique()):
        for part_id in sorted(internal["parts_id"].unique()):
            weekly = int(internal[(internal["week_start_date"] == latest_week) & (internal["factory_id"] == factory_id) & (internal["parts_id"] == part_id)]["shipment_volume"].fillna(0).sum())
            if weekly <= 0:
                continue
            stable_offset = sum(ord(ch) for ch in part_id) % 17
            part_scale = 1.0 if part_id == "PT-1002" else 0.88 + stable_offset / 100
            week_total = max(28, int(weekly * part_scale))
            for week_no in range(4):
                daily_week = date_range[week_no * 7 : week_no * 7 + 7]
                weights = []
                keys = []
                for day in daily_week:
                    for slot in slots:
                        boost = 1.0
                        if factory_id == "F-02" and part_id == "PT-1002" and day.weekday() == 1 and slot == "10:00:00":
                            boost = 1.22
                        if factory_id == "F-02" and part_id == "PT-1002" and day.weekday() == 3 and slot == "15:30:00":
                            boost = 1.14
                        weights.append(day_ratio[day.weekday()] * slot_ratio[slot] * boost * rng.uniform(0.95, 1.05))
                        keys.append((day, slot))
                total_weight = sum(weights)
                allocated = [int(round(week_total * w / total_weight)) for w in weights]
                diff = week_total - sum(allocated)
                max_idx = int(np.argmax(weights))
                allocated[max_idx] += diff
                for (day, slot), qty in zip(keys, allocated):
                    rows.append(
                        {
                            "timestamp": f"{day.strftime('%Y-%m-%d')} {slot}",
                            "factory_id": factory_id,
                            "parts_id": part_id,
                            "shipment_volume": max(0, int(qty)),
                        }
                    )
    return pd.DataFrame(rows)


def reset_sqlite() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS production_notice_history (
                simulation_id TEXT PRIMARY KEY,
                executed_at TEXT NOT NULL,
                factory_id TEXT NOT NULL,
                manufacturer_id TEXT NOT NULL,
                adjustment_rate REAL NOT NULL,
                target_type TEXT,
                target_id TEXT,
                normal_total INTEGER NOT NULL,
                adjusted_total INTEGER NOT NULL,
                difference INTEGER NOT NULL,
                calculation_time_ms REAL NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS safety_stock_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                settings_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS safety_stock_change_history (
                history_id TEXT PRIMARY KEY,
                executed_at TEXT NOT NULL,
                factory_id TEXT NOT NULL,
                parts_id TEXT NOT NULL,
                old_safety_stock INTEGER NOT NULL,
                new_safety_stock INTEGER NOT NULL,
                difference INTEGER NOT NULL,
                difference_rate REAL NOT NULL,
                rmse REAL NOT NULL,
                lead_time_days REAL NOT NULL,
                safety_factor REAL NOT NULL,
                execution_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                needs_review INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_update_history (
                update_id TEXT PRIMARY KEY,
                executed_at TEXT NOT NULL,
                update_type TEXT NOT NULL,
                source TEXT,
                dataset_id TEXT,
                update_mode TEXT,
                status TEXT NOT NULL,
                added_rows INTEGER DEFAULT 0,
                updated_rows INTEGER DEFAULT 0,
                skipped_rows INTEGER DEFAULT 0,
                error_rows INTEGER DEFAULT 0,
                before_min_date TEXT,
                before_max_date TEXT,
                after_min_date TEXT,
                after_max_date TEXT,
                backup_id TEXT,
                duration_ms REAL DEFAULT 0,
                message TEXT,
                error_detail TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_update_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                settings_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute("DELETE FROM production_notice_history")
        conn.execute("DELETE FROM safety_stock_change_history")
        conn.execute("DELETE FROM data_update_history")
        conn.execute(
            "INSERT OR REPLACE INTO safety_stock_settings (id, settings_json, updated_at) VALUES (1, ?, ?)",
            (
                '{"evaluation_months": 3, "default_safety_factor": 1.65, "min_safety_stock": 100, "max_safety_stock": 20000, "max_change_rate": 0.5, "review_threshold_rate": 0.2}',
                JST_UPDATED_AT,
            ),
        )
        conn.execute(
            "INSERT OR REPLACE INTO weekly_update_settings (id, settings_json, updated_at) VALUES (1, ?, ?)",
            (
                '{"enabled": false, "day": "mon", "hour": 6, "minute": 0, "timezone": "Asia/Tokyo", "source": "demo", "directory": "", "recalculate_forecast": true, "recalculate_safety_stock": true, "retry_count": 0, "last_run_at": null, "last_result": null}',
                JST_UPDATED_AT,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def generate_demo_data() -> None:
    random.seed(SEED)
    rng = np.random.default_rng(SEED)
    weeks = pd.date_range(start=START_DATE, end=BASE_DATE, freq="W-MON")
    factories, parts, manufacturers, products, bom, mapping = build_masters()
    product_history = build_product_history(products, weeks, rng)
    internal = build_internal_history(factories, parts, products, bom, product_history, weeks, rng)
    safety, lead_time, accuracy, dynamic = build_safety_and_accuracy(factories, parts, internal, rng)
    jit = build_jit_history(internal, rng)
    for df, name in [
        (factories, "factory_master.csv"),
        (parts, "parts_master.csv"),
        (manufacturers, "manufacturer_master.csv"),
        (products, "product_master.csv"),
        (bom, "bom_master.csv"),
        (mapping, "manufacturer_product_mapping.csv"),
        (product_history, "product_demand_history.csv"),
        (internal, "internal_performance_history.csv"),
        (safety, "safety_stock_master.csv"),
        (lead_time, "lead_time_history.csv"),
        (accuracy, "forecast_accuracy_history.csv"),
        (dynamic, "dynamic_safety_stock.csv"),
        (jit, "jit_shipment_history.csv"),
    ]:
        write_csv(df, name)
    reset_sqlite()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate", action="store_true", help="生成後にデモデータ検証を実行します")
    args = parser.parse_args()
    generate_demo_data()
    if args.validate:
        from scripts.validate_demo_data import validate_demo_data

        validate_demo_data()
    print(f"CMD-X demo data generated under {DATA_DIR}")


if __name__ == "__main__":
    main()
