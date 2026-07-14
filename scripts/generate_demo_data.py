from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "data"
DB_PATH = DATA_DIR / "cmdx.sqlite3"
RNG = np.random.default_rng(42)


def write_csv(df: pd.DataFrame, name: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(DATA_DIR / name, index=False)


def seasonal_factor(date: pd.Timestamp) -> float:
    month = date.month
    factor = 1.0 + 0.08 * math.sin(2 * math.pi * (month - 1) / 12)
    if month == 5:
        factor *= 0.88
    if month == 8:
        factor *= 0.90
    if month in (12, 1):
        factor *= 0.93
    if month in (3, 9):
        factor *= 1.08
    return factor


def product_weekly_volume(base: int, date: pd.Timestamp, idx: int, manufacturer_bias: float) -> int:
    trend = 1 + idx * 0.0012
    temporary = 1.0
    if pd.Timestamp("2025-03-01") <= date <= pd.Timestamp("2025-05-31"):
        temporary *= 1.12
    if pd.Timestamp("2025-10-01") <= date <= pd.Timestamp("2025-11-30"):
        temporary *= 0.90
    noise = RNG.normal(0, base * 0.035)
    return max(20, int(round(base * trend * seasonal_factor(date) * temporary * manufacturer_bias + noise)))


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    factories = pd.DataFrame(
        [
            {"factory_id": "F-01", "factory_name": "名古屋第一工場", "location": "愛知県名古屋市"},
            {"factory_id": "F-02", "factory_name": "三河精密工場", "location": "愛知県豊田市"},
            {"factory_id": "F-03", "factory_name": "豊田アセンブリ工場", "location": "愛知県豊田市"},
        ]
    )
    parts = pd.DataFrame(
        [
            {"parts_id": "PT-1002", "parts_name": "キャブレターボルト", "lead_time_weeks": 1, "safety_stock_days": 7},
            {"parts_id": "PT-1003", "parts_name": "インテークマニホールド", "lead_time_weeks": 2, "safety_stock_days": 12},
            {"parts_id": "PT-2005", "parts_name": "制御基板", "lead_time_weeks": 3, "safety_stock_days": 14},
            {"parts_id": "PT-3001", "parts_name": "油圧バルブ", "lead_time_weeks": 2, "safety_stock_days": 10},
            {"parts_id": "PT-4002", "parts_name": "冷却ファン", "lead_time_weeks": 1, "safety_stock_days": 8},
            {"parts_id": "PT-5007", "parts_name": "センサーケーブル", "lead_time_weeks": 4, "safety_stock_days": 16},
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
    write_csv(factories, "factory_master.csv")
    write_csv(parts, "parts_master.csv")
    write_csv(manufacturers, "manufacturer_master.csv")
    write_csv(products, "product_master.csv")
    write_csv(bom, "bom_master.csv")
    write_csv(mapping, "manufacturer_product_mapping.csv")

    weeks = pd.date_range(end=pd.Timestamp("2026-07-06"), periods=156, freq="W-MON")
    product_rows = []
    bases = {"PROD-A": 820, "PROD-B": 620, "PROD-C": 480, "PROD-D": 540}
    bias = {"M-A": 1.10, "M-B": 0.95, "M-C": 1.02}
    for _, product in products.iterrows():
        for idx, week in enumerate(weeks):
            vol = product_weekly_volume(bases[product["product_id"]], week, idx, bias[product["manufacturer_id"]])
            product_rows.append(
                {
                    "week_start_date": week.strftime("%Y-%m-%d"),
                    "factory_id": product["factory_id"],
                    "product_id": product["product_id"],
                    "manufacturer_id": product["manufacturer_id"],
                    "order_volume": vol,
                }
            )
    product_history = pd.DataFrame(product_rows)
    write_csv(product_history, "product_demand_history.csv")

    part_rows = []
    stock = {(factory, part): 9000 + int(RNG.integers(0, 5000)) for factory in factories["factory_id"] for part in parts["parts_id"]}
    product_history_map = product_history.set_index(["week_start_date", "product_id"])
    for week in weeks:
        week_str = week.strftime("%Y-%m-%d")
        for factory in factories["factory_id"]:
            factory_products = products[products["factory_id"] == factory]["product_id"].tolist()
            for part in parts["parts_id"]:
                demand = 0
                for product_id in factory_products:
                    q_row = bom[(bom["product_id"] == product_id) & (bom["parts_id"] == part)]
                    if q_row.empty:
                        continue
                    demand += int(product_history_map.loc[(week_str, product_id), "order_volume"]) * int(q_row.iloc[0]["quantity_per_product"])
                if demand == 0:
                    demand = max(50, int(RNG.normal(280, 45)))
                production = max(0, int(demand + RNG.normal(120, 180)))
                key = (factory, part)
                stock[key] = max(0, stock[key] + production - demand)
                part_rows.append(
                    {
                        "week_start_date": week_str,
                        "factory_id": factory,
                        "parts_id": part,
                        "order_volume": demand,
                        "production_volume": production,
                        "shipment_volume": demand,
                        "ending_stock": stock[key],
                    }
                )
    write_csv(pd.DataFrame(part_rows), "internal_performance_history.csv")

    safety_rows = []
    latest_stock = pd.DataFrame(part_rows).sort_values("week_start_date").drop_duplicates(["factory_id", "parts_id"], keep="last")
    rmse_pattern = {"PT-1002": 70, "PT-1003": 230, "PT-2005": 160, "PT-3001": 280, "PT-4002": 90, "PT-5007": 180}
    for _, row in latest_stock.iterrows():
        rmse_value = rmse_pattern[row["parts_id"]]
        lt_days = int(parts[parts["parts_id"] == row["parts_id"]]["lead_time_weeks"].iloc[0] * 7)
        dynamic = int(math.ceil(1.65 * rmse_value * math.sqrt(lt_days / 7)))
        initial_multiplier = {
            "PT-1002": 1.0,
            "PT-1003": 0.72,
            "PT-2005": 0.78,
            "PT-3001": 0.82,
            "PT-4002": 1.45,
            "PT-5007": 1.0,
        }[row["parts_id"]]
        initial_stock = max(100, int(dynamic * initial_multiplier))
        safety_rows.append(
            {
                "factory_id": row["factory_id"],
                "parts_id": row["parts_id"],
                "safety_stock_quantity": initial_stock,
                "previous_safety_stock": max(100, int(initial_stock * 0.92)),
                "safety_factor": 1.65,
                "service_level": 0.95,
                "rmse": rmse_value,
                "lead_time_days": lt_days,
                "updated_at": "2026-07-01T00:00:00+09:00",
            }
        )
    write_csv(pd.DataFrame(safety_rows), "safety_stock_master.csv")

    months = pd.date_range(end=pd.Timestamp("2026-07-01"), periods=12, freq="MS")
    lt_rows = []
    acc_rows = []
    for factory in factories["factory_id"]:
        for part in parts["parts_id"]:
            base_lt = int(parts[parts["parts_id"] == part]["lead_time_weeks"].iloc[0] * 7)
            for month_idx, month in enumerate(months):
                lt_noise = RNG.normal(0, 1.0 if part != "PT-2005" else 4.0)
                lt = max(2, int(round(base_lt + lt_noise + (2 if part == "PT-2005" and month_idx % 4 == 0 else 0))))
                lt_rows.append({"recorded_date": month.strftime("%Y-%m-%d"), "factory_id": factory, "parts_id": part, "lead_time_days": lt})
                predicted = max(50, int(RNG.normal(900, 130)))
                error_scale = rmse_pattern[part]
                actual = max(0, int(predicted + RNG.normal(0, error_scale)))
                error = actual - predicted
                acc_rows.append(
                    {
                        "forecast_date": month.strftime("%Y-%m-%d"),
                        "factory_id": factory,
                        "parts_id": part,
                        "predicted_demand": predicted,
                        "actual_demand": actual,
                        "error": error,
                        "squared_error": error * error,
                        "model_version": "demo-ensemble-0.4-0.6",
                    }
                )
    write_csv(pd.DataFrame(lt_rows), "lead_time_history.csv")
    write_csv(pd.DataFrame(acc_rows), "forecast_accuracy_history.csv")

    acc_df = pd.DataFrame(acc_rows)
    lt_df = pd.DataFrame(lt_rows)
    tuned_safety_rows = []
    multipliers = {"PT-1002": 1.0, "PT-1003": 0.72, "PT-2005": 0.78, "PT-3001": 0.82, "PT-4002": 1.45, "PT-5007": 1.25}
    for _, row in latest_stock.iterrows():
        target_acc = acc_df[(acc_df["factory_id"] == row["factory_id"]) & (acc_df["parts_id"] == row["parts_id"])].tail(4)
        target_lt = lt_df[(lt_df["factory_id"] == row["factory_id"]) & (lt_df["parts_id"] == row["parts_id"])].tail(4)
        rmse_value = math.sqrt(float((target_acc["error"] ** 2).mean()))
        lt_days = float(target_lt["lead_time_days"].mean())
        dynamic = int(math.ceil(1.65 * rmse_value * math.sqrt(lt_days / 7)))
        initial_stock = max(100, int(dynamic * multipliers[row["parts_id"]]))
        tuned_safety_rows.append(
            {
                "factory_id": row["factory_id"],
                "parts_id": row["parts_id"],
                "safety_stock_quantity": initial_stock,
                "previous_safety_stock": max(100, int(initial_stock * 0.92)),
                "safety_factor": 1.65,
                "service_level": 0.95,
                "rmse": round(rmse_value, 2),
                "lead_time_days": round(lt_days, 2),
                "updated_at": "2026-07-01T00:00:00+09:00",
            }
        )
    write_csv(pd.DataFrame(tuned_safety_rows), "safety_stock_master.csv")

    jit_rows = []
    slots = ["06:30:00", "10:00:00", "15:30:00", "20:00:00"]
    for day in pd.date_range("2026-06-01", periods=28, freq="D"):
        for factory in factories["factory_id"]:
            for part in parts["parts_id"][:4]:
                for slot in slots:
                    weight = 1.35 if slot == "15:30:00" and day.weekday() in (0, 1) else 1.0
                    jit_rows.append(
                        {
                            "timestamp": f"{day.strftime('%Y-%m-%d')} {slot}",
                            "factory_id": factory,
                            "parts_id": part,
                            "shipment_volume": max(1, int(RNG.normal(70, 18) * weight)),
                        }
                    )
    write_csv(pd.DataFrame(jit_rows), "jit_shipment_history.csv")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS safety_stock_settings (id INTEGER PRIMARY KEY CHECK (id = 1), settings_json TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()
    print(f"CMD-X demo data generated under {DATA_DIR}")


if __name__ == "__main__":
    main()
