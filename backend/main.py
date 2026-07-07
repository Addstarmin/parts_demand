import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import pandas as pd
import requests
import yfinance as yf
from fredapi import Fred

from services.forecast_service import (
    get_factories_list,
    get_parts_list,
    calculate_forecast,
    run_simulation,
    calculate_jit_peaks,
    FRED_API_KEY # forecast_serviceで定義されているAPIキーを使い回す
)

app = FastAPI(title="サプライチェーン需要予測・在庫最適化 API", version="2.0.0")

# =====================================================================
# CORS設定 (Reactデフォルトの開発環境ポート: 5173 からのアクセスを許可)
# =====================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    factory_id: str = Field(..., example="F-01")
    parts_id: str = Field(..., example="PT-1002")
    usd_jpy: float = Field(..., example=158.0)


# =====================================================================
# 0. 【新規追加】本日の外部環境データ取得API
# =====================================================================
@app.get("/api/current-indicators")
def get_current_indicators():
    """
    フロントエンドの「本日の指標」カードが直接読み込めるように
    リアルタイムの為替・PMI・気象データを返すエンドポイント
    """

    today_now = pd.Timestamp.now()
    today_str = today_now.strftime("%Y-%m-%d")
    
    # 1. 本日のドル円取得 (確実なリアルタイムレート取得)
    today_fx = 150.0  # デフォルト
    try:
        # 💡 yfinanceや海外APIが全滅しても動く、信頼性の高い無料為替API
        fx_url = "https://api.exchangerate-api.com/v4/latest/USD"
        fx_res = requests.get(fx_url, timeout=3).json()
        if fx_res and "rates" in fx_res and "JPY" in fx_res["rates"]:
            today_fx = float(fx_res["rates"]["JPY"])
    except Exception:
        # バックアッププラン：別のエンドポイント
        try:
            fx_url2 = "https://open.er-api.com/v6/latest/USD"
            fx_res2 = requests.get(fx_url2, timeout=3).json()
            if fx_res2 and "rates" in fx_res2 and "JPY" in fx_res2["rates"]:
                today_fx = float(fx_res2["rates"]["JPY"])
        except Exception:
            # 最終防衛ライン：yfinance
            try:
                ticker = yf.Ticker("JPY=X")
                today_df = ticker.history(period="1d")
                if not today_df.empty:
                    today_fx = float(today_df["Close"].iloc[-1])
            except Exception:
                pass

    # 2. 本日の気象（名古屋をターゲットに設定）
    today_temp = 22.0
    today_weather = "愛知県名古屋市付近の気象に異常なし"
    try:
        # 💡 相手のサーバーに拒否されないよう、headersを追加
        headers = {'User-Agent': 'Mozilla/5.0'}
        w_url = "https://api.open-meteo.com/v1/forecast?latitude=35.1814&longitude=136.9066&current=temperature_2m,weather_code&timezone=Asia/Tokyo"
        weather_now = requests.get(w_url, headers=headers, timeout=5).json() # timeoutを5秒に延長
        if "current" in weather_now:
            today_temp = float(weather_now["current"]["temperature_2m"])
            code = weather_now["current"]["weather_code"]
            if code >= 60:
                today_weather = "周辺で大雨・悪天候の警戒予報あり"
    except Exception:
        today_weather = "周辺気象の取得失敗（モック表示）"

    # 3. 最新のPMI取得
    today_pmi = 51.5 
    today_pmi_date = today_str
    if FRED_API_KEY and FRED_API_KEY.strip() != "":
        try:
            fred = Fred(api_key=FRED_API_KEY)
            pmi_now = fred.get_series("NAPM", observation_start="2024-01-01")
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
        "weather_date": today_str
    }


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
        raise HTTPException(status_code=400, detail=f"指定された factory_id が存在しません (入力: {payload.factory_id} -> 正規化: {norm_factory_id})")
    if norm_parts_id not in parts:
        raise HTTPException(status_code=400, detail=f"指定された parts_id が存在しません (入力: {payload.parts_id} -> 正規化: {norm_parts_id})")
        
    try:
        result = run_simulation(norm_factory_id, norm_parts_id, payload.usd_jpy)
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
    # IDの表記揺れを正規化
    norm_factory_id = normalize_id(factory_id)
    norm_parts_id = normalize_id(parts_id)

    factories = [f["factory_id"] for f in get_factories_list()]
    parts = [p["parts_id"] for p in get_parts_list()]
    
    if norm_factory_id not in factories:
        raise HTTPException(status_code=400, detail=f"指定された工場IDが存在しません (入力: {factory_id} -> 正規化: {norm_factory_id})")
    if norm_parts_id not in parts:
        raise HTTPException(status_code=400, detail=f"指定された部品IDが存在しません (入力: {parts_id} -> 正規化: {norm_parts_id})")
    if next_week_volume < 0:
        raise HTTPException(status_code=400, detail="予測出荷数は0以上の整数値を指定してください")

    try:
        return calculate_jit_peaks(norm_factory_id, norm_parts_id, next_week_volume)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)