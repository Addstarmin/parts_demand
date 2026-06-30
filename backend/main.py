import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pandas as pd

from services.forecast_service import (
    get_factories_list,
    get_parts_list,
    calculate_forecast,
    run_simulation,
    calculate_jit_peaks
)

app = FastAPI(title="サプライチェーン需要予測・在庫最適化 API", version="2.0.0")

# =====================================================================
# CORS設定 (React: http://localhost:5173 からのアクセスを許可)
# =====================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IDの表記揺れを補正する共通ヘルパー関数
def normalize_id(id_str: str) -> str:
    if not id_str:
        return id_str
    id_clean = id_str.replace("-", "").strip().upper()
    
    # F001やF01などを F-01 へ正規化
    if id_clean.startswith("F"):
        try:
            num = int(id_clean[1:])
            return f"F-{num:02d}"
        except ValueError:
            pass
            
    # PT1002などを PT-1002 へ正規化
    if id_clean.startswith("PT"):
        try:
            num = int(id_clean[2:])
            return f"PT-{num}"
        except ValueError:
            pass
            
    return id_str

# シミュレーションAPI用のリクエストバリデーションスキーマ
class SimulationRequest(BaseModel):
    factory_id: str = Field(..., example="F001")
    parts_id: str = Field(..., example="PT-1002")
    usd_jpy: float = Field(..., example=158.0)

# =====================================================================
# 1. 工場一覧取得API
# =====================================================================
@app.get("/api/factories")
def get_factories():
    try:
        return get_factories_list()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# 2. 部品一覧取得API
# =====================================================================
@app.get("/api/parts")
def get_parts():
    try:
        return get_parts_list()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# 3. 需要予測取得API
# =====================================================================
@app.get("/api/forecast")
def get_forecast(
    factory_id: str = Query(..., description="工場ID"),
    parts_id: str = Query(..., description="部品ID")
):
    # IDの表記揺れを正規化 (F001 -> F-01 等)
    norm_factory_id = normalize_id(factory_id)
    norm_parts_id = normalize_id(parts_id)

    factories = [f["factory_id"] for f in get_factories_list()]
    parts = [p["parts_id"] for p in get_parts_list()]
    
    if norm_factory_id not in factories:
        raise HTTPException(status_code=400, detail=f"指定された工場IDが存在しません (入力: {factory_id} -> 正規化: {norm_factory_id})")
    if norm_parts_id not in parts:
        raise HTTPException(status_code=400, detail=f"指定された部品IDが存在しません (入力: {parts_id} -> 正規化: {norm_parts_id})")
        
    try:
        result = calculate_forecast(norm_factory_id, norm_parts_id)
        if result is None:
            raise HTTPException(status_code=400, detail="選択された工場・部品の実績データが存在しません")
        return result
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# 4. シミュレーションAPI
# =====================================================================
@app.post("/api/simulate")
def simulate(payload: SimulationRequest):
    if payload.usd_jpy <= 0:
        raise HTTPException(status_code=400, detail="ドル円レートは0より大きい値を入力してください")
    if payload.usd_jpy >= 500:
        raise HTTPException(status_code=400, detail="ドル円レートの入力値が異常です (500未満にしてください)")
        
    norm_factory_id = normalize_id(payload.factory_id)
    norm_parts_id = normalize_id(payload.parts_id)

    factories = [f["factory_id"] for f in get_factories_list()]
    parts = [p["parts_id"] for p in get_parts_list()]
    
    if norm_factory_id not in factories:
        raise HTTPException(status_code=400, detail="factory_id が存在しません")
    if norm_parts_id not in parts:
        raise HTTPException(status_code=400, detail="parts_id が存在しません")
        
    try:
        result = run_simulation(norm_factory_id, norm_parts_id, payload.usd_jpy)
        if result is None:
            raise HTTPException(status_code=400, detail="選択された工場・部品の実績データが存在しません")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# 5. JIT出荷ピーク予測API
# =====================================================================
@app.get("/api/shipment-peak")
def shipment_peak(
    factory_id: str,
    parts_id: str,
    next_week_volume: int = 1758
):
    norm_factory_id = normalize_id(factory_id)
    norm_parts_id = normalize_id(parts_id)
    return calculate_jit_peaks(norm_factory_id, norm_parts_id, next_week_volume)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)