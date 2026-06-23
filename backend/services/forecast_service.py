import os
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from fredapi import Fred
from prophet import Prophet
from xgboost import XGBRegressor

# 各種CSVファイルへのパス定義
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FACTORY_MASTER_PATH = os.path.join(BASE_DIR, "data", "factory_master.csv")
PARTS_MASTER_PATH = os.path.join(BASE_DIR, "data", "parts_master.csv")
HISTORY_PATH = os.path.join(BASE_DIR, "data", "internal_performance_history.csv")

FRED_API_KEY = "283de7b5f939d93f769a159d90328771"  # 本物のKEY、またはダミーのまま

def load_masters():
    df_f = pd.read_csv(FACTORY_MASTER_PATH)
    df_p = pd.read_csv(PARTS_MASTER_PATH)
    df_h = pd.read_csv(HISTORY_PATH)
    df_h['date'] = pd.to_datetime(df_h['week_start_date'])
    df_h = df_h.sort_values('date').reset_index(drop=True)
    df_h['demand'] = df_h['shipment_volume']
    return df_f, df_p, df_h

def get_factories_list():
    df_f, _, _ = load_masters()
    return df_f.to_dict(orient="records")

def get_parts_list():
    _, df_p, _ = load_masters()
    return df_p.to_dict(orient="records")

def _core_engine(df_selected, factory_location, safety_stock_days):
    """Prophet × XGBoost のハイブリッド予測エンジン内部コア"""
    start_date = df_selected['date'].min()
    end_date = df_selected['date'].max()
    data_length = len(df_selected)
    next_week_date = end_date + pd.Timedelta(weeks=1)
    
    # ジオコーディングにより座標取得
    lat, lon = 35.6895, 139.6917
    try:
        headers = {'User-Agent': 'sc_demand_forecast_web_api'}
        geo_url = f"https://nominatim.openstreetmap.org/search?q={factory_location}&format=json&limit=1"
        geo_res = requests.get(geo_url, headers=headers, timeout=5).json()
        if geo_res:
            lat = float(geo_res[0]['lat'])
            lon = float(geo_res[0]['lon'])
    except Exception:
        pass

    # 外部データ連携 (為替)
    ticker = yf.Ticker("JPY=X")
    df_fx = ticker.history(start=start_date, end=next_week_date)[['Close']].reset_index()
    df_fx.rename(columns={'Date': 'date', 'Close': 'usd_jpy'}, inplace=True)
    if not df_fx.empty:
        df_fx['date'] = pd.to_datetime(df_fx['date']).dt.tz_localize(None)
    
    # 外部データ連携 (PMI)
    try:
        fred = Fred(api_key=FRED_API_KEY)
        pmi_series = fred.get_series("NAPM", observation_start=start_date, observation_end=next_week_date)
        df_pmi = pd.DataFrame(pmi_series, columns=['pmi']).reset_index()
        df_pmi.rename(columns={'index': 'date'}, inplace=True)
        df_pmi['date'] = pd.to_datetime(df_pmi['date'])
    except Exception:
        pmi_dates = pd.date_range(start=start_date, end=next_week_date, freq='MS')
        df_pmi = pd.DataFrame({'date': pmi_dates, 'pmi': np.random.uniform(48, 53, len(pmi_dates))})
        
    # 天気予報連携
    weather_message = f"{factory_location}付近の気象に異常なし"
    try:
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,weather_code&timezone=Asia%2FTokyo"
        weather_res = requests.get(w_url, timeout=5).json()
        next_week_temp_pred = np.mean(weather_res['daily']['temperature_2m_max'])
        if max(weather_res['daily']['weather_code']) > 60:
            weather_message = f"{factory_location}周辺で大雨・悪天候の警戒予報あり"
    except Exception:
        next_week_temp_pred = 22.0

    df_selected['temperature'] = 20 + 10 * np.sin(2 * np.pi * df_selected['date'].dt.dayofyear / 365)
    df_fx_weekly = df_fx.groupby(pd.Grouper(key='date', freq='W-MON')).mean().reset_index()
    
    df_master = pd.merge(df_selected, df_fx_weekly, on='date', how='left')
    df_master = pd.merge(df_master, df_pmi, on='date', how='left')
    df_master['pmi'] = df_master['pmi'].ffill().bfill()
    df_master['usd_jpy'] = df_master['usd_jpy'].ffill().bfill()
    
    # 【修正箇所】予測の基準となる「実績データの最終日」の指標を取得
    latest_fx = df_master['usd_jpy'].iloc[-1] if not df_master.empty else 150.0
    latest_fx_date = df_master['date'].iloc[-1].strftime('%Y-%m-%d') if not df_master.empty else None

    latest_pmi = df_master['pmi'].iloc[-1] if not df_master.empty else 50.0
    latest_pmi_date = df_master['date'].iloc[-1].strftime('%Y-%m-%d') if not df_master.empty else None
    
    df_next_week = pd.DataFrame({
        'date': [next_week_date], 'demand': [np.nan], 'usd_jpy': [latest_fx],
        'pmi': [latest_pmi], 'temperature': [next_week_temp_pred]
    })
    
    df_all = pd.concat([df_master, df_next_week], ignore_index=True)
    df_all['month'] = df_all['date'].dt.month
    df_all['week_of_year'] = df_all['date'].dt.isocalendar().week.astype(int)
    
    train_df = df_all[df_all['demand'].notna()].copy()
    target_df = df_all[df_all['demand'].isna()].copy()
    
    # 1段目: Prophet
    prophet_train = train_df[['date', 'demand']].rename(columns={'date': 'ds', 'demand': 'y'})
    changepoints = max(1, min(5, int(data_length * 0.1)))
    model_prophet = Prophet(yearly_seasonality=False, weekly_seasonality=False, daily_seasonality=False, n_changepoints=changepoints)
    if data_length > 52:
        model_prophet.yearly_seasonality = True
    model_prophet.fit(prophet_train)
    
    train_df['prophet_pred'] = model_prophet.predict(prophet_train)['yhat'].values
    target_df['prophet_pred'] = model_prophet.predict(target_df[['date']].rename(columns={'date': 'ds'}))['yhat'].values
    
    # 2段目: XGBoost
    features = ['prophet_pred', 'usd_jpy', 'pmi', 'temperature', 'month', 'week_of_year']
    model_xgb = XGBRegressor(n_estimators=50, learning_rate=0.1, max_depth=3, random_state=42)
    model_xgb.fit(train_df[features], train_df['demand'])
    
    next_week_demand_pred = max(0, int(model_xgb.predict(target_df[features])[0]))
    train_df['fitted'] = model_xgb.predict(train_df[features]).astype(int)
    
    return (
        next_week_demand_pred,
        train_df,
        target_df,
        latest_fx,
        latest_fx_date,
        latest_pmi,
        latest_pmi_date,
        next_week_temp_pred,
        weather_message
    )

def calculate_forecast(factory_id: str, parts_id: str):
    df_f, df_p, df_h = load_masters()
    
    df_selected = df_h[(df_h['factory_id'] == factory_id) & (df_h['parts_id'] == parts_id)].copy()
    if len(df_selected) == 0:
        return None
        
    f_info = df_f[df_f['factory_id'] == factory_id].iloc[0]
    p_info = df_p[df_p['parts_id'] == parts_id].iloc[0]
    
    safety_stock_days = 7 if pd.isna(p_info['safety_stock_days']) else int(p_info['safety_stock_days'])
    current_stock = int(df_selected['ending_stock'].iloc[-1])
    
    # 予測エンジンの起動
    (
        next_week_demand_pred,
        train_df,
        target_df,
        fx,
        fx_date,
        pmi,
        pmi_date,
        temp,
        weather_msg
    ) = _core_engine(df_selected, f_info['location'], safety_stock_days)
    
    # 今日の外部指標取得（リアルタイム表示用）
    today_now = pd.Timestamp.now()
    today_str = today_now.strftime("%Y-%m-%d")
    
    # 1. 今日のドル円
    try:
        ticker = yf.Ticker("JPY=X")
        today_df = ticker.history(period="1d")
        today_fx = float(today_df["Close"].iloc[-1]) if not today_df.empty else fx
    except Exception:
        today_fx = fx

    # 2. 今日の気温・天気
    try:
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude=35.6895&longitude=139.6917&current=temperature_2m,weather_code&timezone=Asia/Tokyo"
        weather_now = requests.get(w_url, timeout=5).json()
        today_temp = float(weather_now["current"]["temperature_2m"])
        code = weather_now["current"]["weather_code"]
        today_weather = "現在、大雨警戒" if code >= 60 else "現在異常なし"
    except Exception:
        today_temp = 20.0
        today_weather = "取得失敗（モック表示）"

    # 3. 今日のPMI（最新公表値）
    # 【大幅修正】予測用データ（pmi変数）と完全に分離するため、独立した取得とフォールバックを実施
    try:
        fred = Fred(api_key=FRED_API_KEY)
        pmi_now = fred.get_series("NAPM", observation_start="2024-01-01")
        pmi_clean = pmi_now.dropna()
        today_pmi = float(pmi_clean.iloc[-1])
        today_pmi_date = pmi_clean.index[-1].strftime("%Y-%m-%d")
    except Exception:
        # APIエラー、またはキー未設定時は「今日の表示用」として独立した静的モック（51.5など）を生成
        # これにより予測ロジック側の `pmi` と数値が被るのを防ぎます
        today_pmi = 51.5 
        today_pmi_date = today_str

    safety_stock_vol = int((next_week_demand_pred / 7) * safety_stock_days)
    recommended_production = max(0, next_week_demand_pred + safety_stock_vol - current_stock)
    recommended_order = recommended_production
    recommended_shipping = next_week_demand_pred
    
    risk_level = "HEALTHY"
    risk_message = "在庫水準は安全閾値をキープしています"
    if current_stock < safety_stock_vol:
        risk_level = "CRITICAL"
        risk_message = "現在庫が安全在庫を割り込んでいます！緊急補充が必要です"
    elif current_stock < (next_week_demand_pred * 2):
        risk_level = "WARNING"
        risk_message = "3週間以内に在庫不足リスクが懸念されます。生産の調整を推奨します"

    forecast_chart = []
    for _, row in train_df.tail(2).iterrows():
        forecast_chart.append({
            "date": row['date'].strftime('%Y-%m-%d'),
            "actual": int(row['demand']),
            "forecast": None,
            "current_stock": int(row['ending_stock']),
            "safety_stock": safety_stock_vol
        })
    next_date_str = target_df['date'].iloc[0].strftime('%Y-%m-%d')
    forecast_chart.append({
        "date": next_date_str,
        "actual": None,
        "forecast": next_week_demand_pred,
        "current_stock": current_stock,
        "safety_stock": safety_stock_vol
    })
    
    return {
        "factory_id": factory_id,
        "factory_name": f_info['factory_name'],
        "parts_id": parts_id,
        "parts_name": p_info['parts_name'],
        "current_stock": current_stock,
        "safety_stock": safety_stock_vol,
        "next_week_forecast": next_week_demand_pred,
        "recommended_order": recommended_order,
        "recommended_production": recommended_production,
        "recommended_shipping": recommended_shipping,
        "risk_level": risk_level,
        "risk_message": risk_message,
        "forecast_chart": forecast_chart,
        "indicators": {
            "usd_jpy": round(fx, 1),
            "usd_jpy_date": fx_date,
            "pmi": round(pmi, 1),
            "pmi_date": pmi_date,
            "temperature": round(temp, 1),
            "weather_message": weather_msg
        },
        "current_indicators": {
            "usd_jpy": round(today_fx, 1) if today_fx is not None else None,
            "usd_jpy_date": today_str,
            "pmi": round(today_pmi, 1) if today_pmi is not None else None,
            "pmi_date": today_pmi_date,
            "temperature": round(today_temp, 1) if today_temp is not None else None,
            "weather_date": today_str,
            "weather_message": today_weather
        }
    }

def run_simulation(factory_id: str, parts_id: str, input_usd_jpy: float):
    df_f, df_p, df_h = load_masters()
    df_selected = df_h[(df_h['factory_id'] == factory_id) & (df_h['parts_id'] == parts_id)].copy()
    if len(df_selected) == 0:
        return None
        
    p_info = df_p[df_p['parts_id'] == parts_id].iloc[0]
    safety_stock_days = 7 if pd.isna(p_info['safety_stock_days']) else int(p_info['safety_stock_days'])
    current_stock = int(df_selected['ending_stock'].iloc[-1])
    
    base_forecast = calculate_forecast(factory_id, parts_id)
    base_demand = base_forecast["next_week_forecast"]
    base_fx = base_forecast["indicators"]["usd_jpy"]
    
    fx_diff_rate = (input_usd_jpy - base_fx) / base_fx
    demand_change_rate = int(fx_diff_rate * 100 * 0.3)
    
    new_forecast = max(0, int(base_demand * (1 + (demand_change_rate / 100))))
    new_safety = int((new_forecast / 7) * safety_stock_days)
    new_recommended_order = max(0, new_forecast + new_safety - current_stock)
    
    msg = f"為替が1ドル={input_usd_jpy}円へ変動した場合、需要は通常予測から約{demand_change_rate}%増加（または減少）するとシミュレートされます。"
    if demand_change_rate > 0:
        msg = f"ドル高トレンド（+{demand_change_rate}%）に伴い、部品調達および出荷需要が増交する見込みです。"

    return {
        "demand_change_rate": demand_change_rate,
        "message": msg,
        "new_forecast": new_forecast,
        "new_recommended_order": new_recommended_order
    }