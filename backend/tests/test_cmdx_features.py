import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.data_utils import read_csv
from services.master_service import get_product_bom, get_products
from services.product_forecast_service import get_product_forecast
from services.production_notice_service import run_production_notice_simulation
from services.safety_stock_service import (
    build_safety_stock_preview,
    calculate_dynamic_safety_stock,
    optimize_safety_stock,
    optimize_safety_stock_legacy_response,
)
from services.forecast_service import calculate_forecast, calculate_jit_peaks
from services.download_service import actual_history_csv, forecast_csv, future_actual_template_csv


def test_products_and_bom_are_available():
    products = get_products("F-02")
    assert any(item["product_id"] == "PROD-A" for item in products)
    bom = get_product_bom("PROD-A")
    assert len(bom) >= 2
    assert {"parts_id", "parts_name", "quantity_per_product"}.issubset(bom[0].keys())


def test_missing_product_forecast_returns_none():
    assert get_product_forecast("F-02", "PROD-NOTFOUND") is None


def test_product_forecast_and_bom_required_quantity():
    result = get_product_forecast("F-02", "PROD-A")
    assert result["target_type"] == "product"
    assert len([p for p in result["forecast_chart"] if p["normal_forecast"] is not None]) == 4
    component = next(item for item in result["component_forecasts"] if item["parts_id"] == "PT-1002")
    next_product = next(point["normal_forecast"] for point in result["forecast_chart"] if point["normal_forecast"] is not None)
    assert component["next_week_required"] == next_product * component["quantity_per_product"]


def test_shared_part_exists_across_multiple_products():
    bom = read_csv("bom_master.csv")
    shared_counts = bom.groupby("parts_id")["product_id"].nunique()
    assert shared_counts.max() >= 2


@pytest.mark.parametrize("rate", [-50, 0, 50])
def test_production_notice_rate_boundaries(rate):
    result = run_production_notice_simulation(
        {"factory_id": "F-02", "manufacturer_id": "M-A", "adjustment_rate": rate, "target_type": "product", "target_id": "PROD-A"}
    )
    assert result["calculation_time_ms"] >= 0
    assert result["simulation_id"].startswith("SIM-")


def test_production_notice_rejects_out_of_range():
    with pytest.raises(ValueError):
        run_production_notice_simulation(
            {"factory_id": "F-02", "manufacturer_id": "M-A", "adjustment_rate": 51, "target_type": "product", "target_id": "PROD-A"}
        )


def test_production_notice_allocation_ratio_under_one():
    result = run_production_notice_simulation(
        {"factory_id": "F-03", "manufacturer_id": "M-A", "adjustment_rate": -20, "target_type": "product", "target_id": "PROD-C"}
    )
    product = result["affected_products"][0]
    assert product["allocation_ratio"] == 0.6
    assert product["difference"] < 0
    assert abs(product["difference"] / product["normal_total"]) < 0.2
    part = result["affected_parts"][0]
    assert sum(slot["adjusted_volume"] for slot in part["jit_peaks"]) == part["adjusted_next_week_volume"]


def test_unmapped_target_product_is_rejected():
    with pytest.raises(LookupError):
        run_production_notice_simulation(
            {"factory_id": "F-02", "manufacturer_id": "M-B", "adjustment_rate": 10, "target_type": "product", "target_id": "PROD-A"}
        )


def test_dynamic_safety_stock_formula_and_monotonicity():
    settings = {
        "default_safety_factor": 1.65,
        "min_safety_stock": 0,
        "max_safety_stock": 20000,
        "max_change_rate": 1,
    }
    base, _ = calculate_dynamic_safety_stock(100, 100, 7, settings)
    long_lt, _ = calculate_dynamic_safety_stock(100, 100, 28, settings)
    high_rmse, _ = calculate_dynamic_safety_stock(100, 300, 7, settings)
    assert base == 165
    assert long_lt > base
    assert high_rmse > base


def test_safety_stock_min_max_and_change_guardrail():
    settings = {
        "default_safety_factor": 1.65,
        "min_safety_stock": 100,
        "max_safety_stock": 20000,
        "max_change_rate": 0.5,
    }
    guarded, _ = calculate_dynamic_safety_stock(1000, 20000, 28, settings)
    assert guarded == 1500
    minimum, _ = calculate_dynamic_safety_stock(100, 1, 7, {**settings, "max_change_rate": 1})
    assert minimum == 100


def test_preview_does_not_update_master_and_optimize_does():
    before = read_csv("safety_stock_master.csv").copy()
    preview = build_safety_stock_preview()
    after_preview = read_csv("safety_stock_master.csv")
    assert before.equals(after_preview)
    result = optimize_safety_stock("pytest")
    after = read_csv("safety_stock_master.csv")
    assert result["summary"]["total"] > 0
    assert not after.empty


def test_jit_ratios_sum_and_volume_integrity():
    result = calculate_jit_peaks("F-02", "PT-1002", 1758)
    assert len(result["peak_data"]) == 28
    assert abs(sum(item["ratio"] for item in result["peak_data"]) - 1.0) < 0.01
    assert sum(item["volume"] for item in result["peak_data"]) == 1758


def test_forecast_returns_dashboard_risk_fields_only():
    result = calculate_forecast("F-02", "PT-1002")
    assert "risk_level" in result
    assert "risk_message" in result
    assert "alert_payload" not in result


def test_legacy_safety_stock_response_shape():
    result = optimize_safety_stock_legacy_response("pytest_legacy")
    assert result["status"] == "success"
    assert "optimization_summary" in result
    assert result["total_records_updated"] > 0


def test_csv_download_builders():
    history = actual_history_csv(factory_id="F-02", parts_id="PT-1002")
    assert "week_start_date" in history and "PT-1002" in history
    forecast = forecast_csv(factory_id="F-02", target_type="part", target_id="PT-1002")
    assert "recommended_order" in forecast
    template = future_actual_template_csv(factory_id="F-02", parts_id="PT-1002")
    assert "ending_stock" in template
