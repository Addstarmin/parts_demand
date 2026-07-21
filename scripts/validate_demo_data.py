from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "backend" / "data"
BACKEND_DIR = ROOT / "backend"
REQUIRED_COLUMNS = {
    "factory_master.csv": {"factory_id", "factory_name", "location"},
    "parts_master.csv": {"parts_id", "parts_name", "lead_time_weeks", "safety_stock_days"},
    "manufacturer_master.csv": {"manufacturer_id", "manufacturer_name", "description"},
    "product_master.csv": {"product_id", "product_name", "factory_id", "manufacturer_id", "unit_price", "description"},
    "manufacturer_product_mapping.csv": {"manufacturer_id", "product_id", "allocation_ratio"},
    "bom_master.csv": {"product_id", "parts_id", "quantity_per_product"},
    "product_demand_history.csv": {"week_start_date", "factory_id", "product_id", "manufacturer_id", "order_volume"},
    "internal_performance_history.csv": {"week_start_date", "factory_id", "parts_id", "order_volume", "production_volume", "shipment_volume", "ending_stock"},
    "forecast_accuracy_history.csv": {"forecast_date", "factory_id", "parts_id", "predicted_demand", "actual_demand", "error", "squared_error", "model_version"},
    "lead_time_history.csv": {"recorded_date", "factory_id", "parts_id", "lead_time_days"},
    "jit_shipment_history.csv": {"timestamp", "factory_id", "parts_id", "shipment_volume"},
    "safety_stock_master.csv": {"factory_id", "parts_id", "safety_stock_quantity", "previous_safety_stock", "safety_factor", "service_level", "rmse", "lead_time_days", "updated_at"},
    "dynamic_safety_stock.csv": {"calculation_month", "factory_id", "parts_id", "ai_rmse", "lead_time_days", "calculated_safety_stock", "updated_at"},
}


def fail(message: str) -> None:
    raise AssertionError(message)


def load(name: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if not path.exists():
        fail(f"{name}: 必須CSVが存在しません")
    df = pd.read_csv(path)
    missing = REQUIRED_COLUMNS[name] - set(df.columns)
    if missing:
        fail(f"{name}: 必須カラム不足 {sorted(missing)}")
    if df.empty:
        fail(f"{name}: グラフ/API用データが空です")
    if df.replace([np.inf, -np.inf], np.nan).isna().any().any():
        fail(f"{name}: NaNまたはInfinityを含みます")
    return df


def digest_csvs() -> str:
    h = hashlib.sha256()
    for name in sorted(REQUIRED_COLUMNS):
        h.update(name.encode())
        h.update((DATA_DIR / name).read_bytes())
    return h.hexdigest()


def check_references(data: dict[str, pd.DataFrame]) -> None:
    factories = set(data["factory_master.csv"]["factory_id"])
    parts = set(data["parts_master.csv"]["parts_id"])
    products = set(data["product_master.csv"]["product_id"])
    manufacturers = set(data["manufacturer_master.csv"]["manufacturer_id"])
    checks = [
        ("product_master.csv.factory_id", set(data["product_master.csv"]["factory_id"]), factories),
        ("product_master.csv.manufacturer_id", set(data["product_master.csv"]["manufacturer_id"]), manufacturers),
        ("bom_master.csv.product_id", set(data["bom_master.csv"]["product_id"]), products),
        ("bom_master.csv.parts_id", set(data["bom_master.csv"]["parts_id"]), parts),
        ("manufacturer_product_mapping.csv.product_id", set(data["manufacturer_product_mapping.csv"]["product_id"]), products),
        ("manufacturer_product_mapping.csv.manufacturer_id", set(data["manufacturer_product_mapping.csv"]["manufacturer_id"]), manufacturers),
        ("internal_performance_history.csv.factory_id", set(data["internal_performance_history.csv"]["factory_id"]), factories),
        ("internal_performance_history.csv.parts_id", set(data["internal_performance_history.csv"]["parts_id"]), parts),
    ]
    for label, values, master in checks:
        extra = values - master
        if extra:
            fail(f"{label}: 参照先が存在しないID {sorted(extra)}")


def check_non_negative(data: dict[str, pd.DataFrame]) -> None:
    numeric_targets = {
        "product_demand_history.csv": ["order_volume"],
        "internal_performance_history.csv": ["order_volume", "production_volume", "shipment_volume", "ending_stock"],
        "jit_shipment_history.csv": ["shipment_volume"],
        "forecast_accuracy_history.csv": ["predicted_demand", "actual_demand"],
        "safety_stock_master.csv": ["safety_stock_quantity", "previous_safety_stock"],
    }
    for name, cols in numeric_targets.items():
        for col in cols:
            negatives = data[name][data[name][col] < 0]
            if not negatives.empty:
                fail(f"{name}.{col}: 負値があります 例={negatives.head(1).to_dict(orient='records')[0]}")


def check_bom(data: dict[str, pd.DataFrame]) -> None:
    ph = data["product_demand_history.csv"]
    perf = data["internal_performance_history.csv"]
    bom = data["bom_master.csv"]
    products = data["product_master.csv"]
    week = ph["week_start_date"].max()
    for _, part_row in perf[perf["week_start_date"] == week].iterrows():
        factory_products = products[products["factory_id"] == part_row["factory_id"]]["product_id"]
        expected = 0
        for product_id in factory_products:
            q = bom[(bom["product_id"] == product_id) & (bom["parts_id"] == part_row["parts_id"])]
            if q.empty:
                continue
            demand = int(ph[(ph["week_start_date"] == week) & (ph["product_id"] == product_id)]["order_volume"].iloc[0])
            expected += demand * int(q.iloc[0]["quantity_per_product"])
        if expected > 0 and int(part_row["order_volume"]) != expected:
            fail(f"BOM必要数不一致: {part_row['factory_id']} {part_row['parts_id']} week={week} actual={part_row['order_volume']} expected={expected}")


def check_backend_behaviors() -> dict:
    sys.path.insert(0, str(BACKEND_DIR))
    from services.forecast_service import calculate_jit_peaks
    from services.product_forecast_service import get_product_forecast
    from services.production_notice_service import run_production_notice_simulation
    from services.safety_stock_service import build_safety_stock_preview

    product = get_product_forecast("F-02", "PROD-A")
    if not product:
        fail("代表製品予測が取得できません: F-02/PROD-A")
    component = next((item for item in product["component_forecasts"] if item["parts_id"] == "PT-1002"), None)
    if not component:
        fail("代表構成部品がありません: PT-1002")
    for field in ["parts_demand", "recommended_production", "recommended_order", "recommended_shipping"]:
        if component[field] <= 0:
            fail(f"代表KPIが0以下です: {field}={component[field]} current={component['current_stock']} safety={component['dynamic_safety_stock']}")

    jit = calculate_jit_peaks("F-02", "PT-1002", component["recommended_shipping"])
    ratio_sum = sum(item["ratio"] for item in jit["peak_data"])
    volume_sum = sum(item["volume"] for item in jit["peak_data"])
    if abs(ratio_sum - 1.0) >= 0.01:
        fail(f"JIT便比率合計が1.0から外れています: {ratio_sum}")
    if volume_sum != component["recommended_shipping"]:
        fail(f"JIT便数量合計不一致: actual={volume_sum} expected={component['recommended_shipping']}")
    if jit["peak_info"]["day"] != "火" or jit["peak_info"]["hour"] != "10:00":
        fail(f"JIT最大ピークが代表シナリオと異なります: {jit['peak_info']}")

    notice = run_production_notice_simulation(
        {"factory_id": "F-02", "manufacturer_id": "M-A", "adjustment_rate": -20, "target_type": "product", "target_id": "PROD-A"}
    )
    first_product = notice["affected_products"][0]
    first_future = next(point for point in first_product["forecast_chart"] if point["normal_forecast"] is not None)
    if first_future["adjusted_forecast"] >= first_future["normal_forecast"]:
        fail(f"完成車A社-20%で調整後予測が下がっていません: {first_future}")
    preview = build_safety_stock_preview()
    if preview["summary"]["increase"] <= 0 or preview["summary"]["decrease"] <= 0:
        fail(f"安全在庫最適化に増加/減少の両方がありません: {preview['summary']}")
    return {
        "component": component,
        "jit": jit,
        "notice_before": first_future["normal_forecast"],
        "notice_after": first_future["adjusted_forecast"],
        "safety_preview": preview,
    }


def check_reproducible() -> None:
    before = digest_csvs()
    with tempfile.TemporaryDirectory():
        subprocess.run([sys.executable, "-m", "scripts.generate_demo_data"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    after = digest_csvs()
    if before != after:
        fail(f"同一生成のハッシュが一致しません: before={before} after={after}")


def validate_demo_data(check_repro: bool = True) -> dict:
    data = {name: load(name) for name in REQUIRED_COLUMNS}
    check_references(data)
    check_non_negative(data)
    check_bom(data)
    summary = check_backend_behaviors()
    if check_repro:
        check_reproducible()
    print("CMD-X demo data validation passed")
    return summary


def main() -> None:
    validate_demo_data()


if __name__ == "__main__":
    main()
