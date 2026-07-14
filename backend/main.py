import os
from urllib.parse import quote

import pandas as pd
import requests
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fredapi import Fred
from pydantic import BaseModel, Field, field_validator

from services.data_utils import normalize_id
from services.download_service import actual_history_csv, forecast_csv, future_actual_template_csv
from services.forecast_service import calculate_forecast, calculate_jit_peaks, expand_product, run_simulation
from services.master_service import (
    get_factories_list,
    get_manufacturers,
    get_parts_list,
    get_product,
    get_product_bom,
    get_products,
    require_factory,
    require_part,
)
from services.product_forecast_service import get_product_forecast
from services.production_notice_service import (
    delete_production_notice_history,
    get_production_notice_history,
    run_production_notice_simulation,
)
from services.safety_stock_service import (
    build_safety_stock_preview,
    get_current_safety_stock,
    get_safety_stock_history,
    optimize_safety_stock,
    optimize_safety_stock_legacy_response,
    save_settings,
)
from services.scheduler_service import start_safety_stock_scheduler
from services.storage_service import get_settings, init_db

app = FastAPI(title="CMD-X サプライチェーン需要予測・在庫最適化 API", version="3.0.0")


def _cors_origins() -> list[str]:
    raw = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [item.strip() for item in raw.split(",") if item.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()
    start_safety_stock_scheduler()


class SimulationRequest(BaseModel):
    factory_id: str = Field(..., examples=["F-01"])
    parts_id: str = Field(..., examples=["PT-1002"])
    usd_jpy: float = Field(..., gt=0, lt=500)


class ProductForecastRequest(BaseModel):
    product_id: str
    forecast: int = Field(..., ge=0)


class ProductionNoticeRequest(BaseModel):
    factory_id: str
    manufacturer_id: str
    adjustment_rate: float = Field(..., ge=-50, le=50)
    target_type: str = Field(default="product")
    target_id: str | None = None


class ManufacturerAdjustmentRequest(BaseModel):
    client_manufacturer: str
    adjustment_rate: float = Field(..., ge=-1, le=1)
    target_product_id: str
    base_forecast_week: str | None = None
    factory_id: str = "F-02"


class SafetyStockSettingsRequest(BaseModel):
    evaluation_months: int = Field(..., ge=1, le=12)
    default_safety_factor: float = Field(..., ge=0.1, le=5.0)
    min_safety_stock: int = Field(..., ge=0)
    max_safety_stock: int = Field(..., ge=0)
    max_change_rate: float = Field(..., ge=0, le=1)
    review_threshold_rate: float = Field(..., ge=0, le=1)

    @field_validator("max_safety_stock")
    @classmethod
    def max_must_be_gte_min(cls, value, info):
        min_value = info.data.get("min_safety_stock")
        if min_value is not None and value < min_value:
            raise ValueError("max_safety_stockはmin_safety_stock以上で指定してください")
        return value


@app.get("/api/current-indicators")
def get_current_indicators():
    today_now = pd.Timestamp.now(tz="Asia/Tokyo")
    today_str = today_now.strftime("%Y-%m-%d")
    today_fx = 150.0
    try:
        fx_res = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=3).json()
        today_fx = float(fx_res.get("rates", {}).get("JPY", today_fx))
    except Exception:
        try:
            ticker = yf.Ticker("JPY=X")
            today_df = ticker.history(period="1d")
            if not today_df.empty:
                today_fx = float(today_df["Close"].iloc[-1])
        except Exception:
            pass
    today_temp = 22.0
    today_weather = "愛知県名古屋市付近の気象に異常なし"
    try:
        w_url = "https://api.open-meteo.com/v1/forecast?latitude=35.1814&longitude=136.9066&current=temperature_2m,weather_code&timezone=Asia/Tokyo"
        weather_now = requests.get(w_url, timeout=5).json()
        if "current" in weather_now:
            today_temp = float(weather_now["current"]["temperature_2m"])
            if int(weather_now["current"]["weather_code"]) >= 60:
                today_weather = "周辺で大雨・悪天候の警戒予報あり"
    except Exception:
        today_weather = "周辺気象の取得失敗（デモ用フォールバック表示）"
    today_pmi = 51.5
    today_pmi_date = today_str
    fred_key = os.getenv("FRED_API_KEY", "")
    if fred_key:
        try:
            pmi_now = Fred(api_key=fred_key).get_series("NAPM", observation_start="2024-01-01")
            pmi_clean = pmi_now.dropna()
            if not pmi_clean.empty:
                today_pmi = float(pmi_clean.iloc[-1])
                today_pmi_date = pmi_clean.index[-1].strftime("%Y-%m-%d")
        except Exception:
            pass
    return {
        "usd_jpy": round(today_fx, 1),
        "usd_jpy_date": today_str,
        "pmi": round(today_pmi, 1),
        "pmi_date": today_pmi_date,
        "temperature": round(today_temp, 1),
        "weather_message": today_weather,
        "weather_date": today_str,
    }


@app.get("/api/factories")
def get_factories():
    return get_factories_list()


@app.get("/api/parts")
def get_parts():
    return get_parts_list()


@app.get("/api/manufacturers")
def manufacturers():
    return get_manufacturers()


@app.get("/api/products")
def products(factory_id: str | None = None):
    return get_products(factory_id)


@app.get("/api/products/{product_id}")
def product_detail(product_id: str):
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="指定された製品IDが存在しません")
    return product


@app.get("/api/products/{product_id}/bom")
def product_bom(product_id: str):
    product = get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="指定された製品IDが存在しません")
    return get_product_bom(product_id)


@app.get("/api/forecast")
def get_forecast(factory_id: str = Query(...), parts_id: str = Query(...)):
    norm_factory_id = normalize_id(factory_id)
    norm_parts_id = normalize_id(parts_id)
    if not require_factory(norm_factory_id):
        raise HTTPException(status_code=404, detail="指定された工場IDが存在しません")
    if not require_part(norm_parts_id):
        raise HTTPException(status_code=404, detail="指定された部品IDが存在しません")
    try:
        result = calculate_forecast(norm_factory_id, norm_parts_id)
        if result is None:
            raise HTTPException(status_code=404, detail="選択された工場・部品の実績データが存在しません")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/forecast/product")
def product_forecast(factory_id: str = Query(...), product_id: str = Query(...)):
    norm_factory_id = normalize_id(factory_id)
    norm_product_id = normalize_id(product_id)
    if not require_factory(norm_factory_id):
        raise HTTPException(status_code=404, detail="指定された工場IDが存在しません")
    result = get_product_forecast(norm_factory_id, norm_product_id)
    if result is None:
        raise HTTPException(status_code=404, detail="選択された工場・製品の需要履歴が存在しません")
    return result


@app.post("/api/simulate")
def simulate(payload: SimulationRequest):
    norm_factory_id = normalize_id(payload.factory_id)
    norm_parts_id = normalize_id(payload.parts_id)
    if not require_factory(norm_factory_id):
        raise HTTPException(status_code=404, detail="指定された工場IDが存在しません")
    if not require_part(norm_parts_id):
        raise HTTPException(status_code=404, detail="指定された部品IDが存在しません")
    result = run_simulation(norm_factory_id, norm_parts_id, payload.usd_jpy)
    if result is None:
        raise HTTPException(status_code=404, detail="選択された工場・部品の実績データが存在しません")
    return result


@app.get("/api/shipment-peak")
def shipment_peak(factory_id: str = Query(...), parts_id: str = Query(...), next_week_volume: int = Query(1758, ge=0)):
    norm_factory_id = normalize_id(factory_id)
    norm_parts_id = normalize_id(parts_id)
    if not require_factory(norm_factory_id):
        raise HTTPException(status_code=404, detail="指定された工場IDが存在しません")
    if not require_part(norm_parts_id):
        raise HTTPException(status_code=404, detail="指定された部品IDが存在しません")
    return calculate_jit_peaks(norm_factory_id, norm_parts_id, next_week_volume)


def _csv_response(content: str, filename: str) -> Response:
    encoded = quote(filename)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )


@app.get("/api/download/actual-history.csv")
def download_actual_history(factory_id: str | None = None, parts_id: str | None = None, product_id: str | None = None):
    csv_text = actual_history_csv(factory_id=factory_id, parts_id=parts_id, product_id=product_id)
    target = product_id or parts_id or "all"
    return _csv_response(csv_text, f"cmdx_actual_history_{target}.csv")


@app.get("/api/download/forecast.csv")
def download_forecast(factory_id: str = Query(...), target_type: str = Query(...), target_id: str = Query(...)):
    if target_type not in {"part", "product"}:
        raise HTTPException(status_code=422, detail="target_typeはpartまたはproductを指定してください")
    csv_text = forecast_csv(factory_id=factory_id, target_type=target_type, target_id=target_id)
    return _csv_response(csv_text, f"cmdx_forecast_{target_type}_{target_id}.csv")


@app.get("/api/download/future-actual-template.csv")
def download_future_actual_template(factory_id: str | None = None, parts_id: str | None = None, product_id: str | None = None):
    csv_text = future_actual_template_csv(factory_id=factory_id, parts_id=parts_id, product_id=product_id)
    target = product_id or parts_id or "blank"
    return _csv_response(csv_text, f"cmdx_future_actual_template_{target}.csv")


@app.post("/api/product/forecast")
def legacy_product_forecast(req: ProductForecastRequest):
    return expand_product(normalize_id(req.product_id), req.forecast)


@app.post("/api/simulations/production-notice")
def production_notice(payload: ProductionNoticeRequest):
    try:
        return run_production_notice_simulation(payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/simulation/manufacturer-adjustment")
def manufacturer_adjustment_legacy(payload: ManufacturerAdjustmentRequest):
    manufacturer_alias = {
        "A社": "M-A",
        "B社": "M-B",
        "C社": "M-C",
        "完成車A社": "M-A",
        "完成車B社": "M-B",
        "完成車C社": "M-C",
    }
    manufacturer_id = manufacturer_alias.get(payload.client_manufacturer, normalize_id(payload.client_manufacturer))
    try:
        result = run_production_notice_simulation(
            {
                "factory_id": payload.factory_id,
                "manufacturer_id": manufacturer_id,
                "adjustment_rate": payload.adjustment_rate * 100,
                "target_type": "product",
                "target_id": payload.target_product_id,
            }
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    impacted_parts = [
        {
            "parts_id": part["parts_id"],
            "parts_name": part["parts_name"],
            "quantity_per_product": None,
            "original_next_week_volume": part["original_next_week_volume"],
            "adjusted_next_week_volume": part["adjusted_next_week_volume"],
            "jit_peaks": part["jit_peaks"],
        }
        for part in result["affected_parts"]
    ]
    return {
        "status": "success",
        "target_product_id": normalize_id(payload.target_product_id),
        "client_manufacturer": payload.client_manufacturer,
        "adjustment_rate": payload.adjustment_rate,
        "recalculated_at": result["executed_at"],
        "impacted_parts": impacted_parts,
    }


@app.get("/api/simulations/production-notice/history")
def production_notice_history():
    return get_production_notice_history(limit=20)


@app.delete("/api/simulations/production-notice/history/{simulation_id}")
def delete_production_notice(simulation_id: str):
    if not delete_production_notice_history(simulation_id):
        raise HTTPException(status_code=404, detail="指定されたシミュレーション履歴が存在しません")
    return {"deleted": True, "simulation_id": simulation_id}


@app.get("/api/safety-stock/settings")
def safety_stock_settings():
    return get_settings()


@app.put("/api/safety-stock/settings")
def put_safety_stock_settings(payload: SafetyStockSettingsRequest):
    try:
        return save_settings(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/safety-stock/current")
def safety_stock_current():
    return get_current_safety_stock()


@app.get("/api/safety-stock/history")
def safety_stock_history():
    return get_safety_stock_history(limit=100)


@app.get("/api/safety-stock/preview")
def safety_stock_preview():
    return build_safety_stock_preview()


@app.post("/api/safety-stock/optimize")
def safety_stock_optimize():
    return optimize_safety_stock(execution_type="manual")


@app.post("/api/inventory/optimize-safety-stock")
def inventory_optimize_safety_stock_legacy():
    return optimize_safety_stock_legacy_response(execution_type="manual_legacy_api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
