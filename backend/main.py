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

# CORS設定 (Reactデフォルトの開発環境ポート: 5173 からのアクセスを許可)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# シミュレーションAPI用のリクエストバリデーションスキーマ
class SimulationRequest(BaseModel):
    factory_id: str = Field(..., example="F-01")
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
    # 事前バリデーション: IDの存在チェック
    factories = [f["factory_id"] for f in get_factories_list()]
    parts = [p["parts_id"] for p in get_parts_list()]
    
    if factory_id not in factories:
        raise HTTPException(status_code=400, detail="指定された工場IDが存在しません")
    if parts_id not in parts:
        raise HTTPException(status_code=400, detail="指定された部品IDが存在しません")
        
    try:
        result = calculate_forecast(factory_id, parts_id)
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
        
    factories = [f["factory_id"] for f in get_factories_list()]
    parts = [p["parts_id"] for p in get_parts_list()]
    
    if payload.factory_id not in factories:
        raise HTTPException(status_code=400, detail="指定された factory_id が存在しません")
    if payload.parts_id not in parts:
        raise HTTPException(status_code=400, detail="指定された parts_id が存在しません")
        
    try:
        result = run_simulation(payload.factory_id, payload.parts_id, payload.usd_jpy)
        if result is None:
            raise HTTPException(status_code=400, detail="選択された工場・部品の実績データが存在しません")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# 5. F-07 JIT出荷ピーク予測取得API
# =====================================================================
@app.get("/api/shipment-peak")
def shipment_peak(
    factory_id: str = Query(..., description="工場ID"),
    parts_id: str = Query(..., description="部品ID"),
    next_week_volume: int = Query(1758, description="次週の予測出荷総数")
):
    factories = [f["factory_id"] for f in get_factories_list()]
    parts = [p["parts_id"] for p in get_parts_list()]
    
    if factory_id not in factories:
        raise HTTPException(status_code=400, detail="指定された工場IDが存在しません")
    if parts_id not in parts:
        raise HTTPException(status_code=400, detail="指定された部品IDが存在しません")
    if next_week_volume < 0:
        raise HTTPException(status_code=400, detail="予測出荷数は0以上の整数値を指定してください")

    try:
        return calculate_jit_peaks(factory_id, parts_id, next_week_volume)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)