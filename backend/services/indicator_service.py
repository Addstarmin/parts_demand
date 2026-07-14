from __future__ import annotations

import os

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from fredapi import Fred


def get_realtime_indicators(factory_location: str = "愛知県名古屋市") -> dict:
    today = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y-%m-%d")
    usd_jpy = 150.0
    usd_source = "fallback"
    try:
        res = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=3).json()
        usd_jpy = float(res.get("rates", {}).get("JPY", usd_jpy))
        usd_source = "exchangerate-api"
    except Exception:
        try:
            hist = yf.Ticker("JPY=X").history(period="1d")
            if not hist.empty:
                usd_jpy = float(hist["Close"].iloc[-1])
                usd_source = "yfinance"
        except Exception:
            pass

    pmi = 51.5
    pmi_date = today
    pmi_source = "fallback"
    fred_key = os.getenv("FRED_API_KEY", "")
    if fred_key:
        try:
            series = Fred(api_key=fred_key).get_series("NAPM", observation_start="2024-01-01").dropna()
            if not series.empty:
                pmi = float(series.iloc[-1])
                pmi_date = series.index[-1].strftime("%Y-%m-%d")
                pmi_source = "FRED"
        except Exception:
            pass

    temperature = 22.0
    weather_message = f"{factory_location}付近の気象に異常なし"
    weather_source = "fallback"
    try:
        res = requests.get(
            "https://api.open-meteo.com/v1/forecast?latitude=35.1814&longitude=136.9066&current=temperature_2m,weather_code&timezone=Asia/Tokyo",
            timeout=5,
        ).json()
        if "current" in res:
            temperature = float(res["current"]["temperature_2m"])
            if int(res["current"]["weather_code"]) >= 60:
                weather_message = f"{factory_location}周辺で大雨・悪天候の警戒予報あり"
            weather_source = "open-meteo"
    except Exception:
        day = pd.Timestamp.now(tz="Asia/Tokyo").dayofyear
        temperature = float(16.0 + 11.0 * np.sin(2 * np.pi * (day - 105) / 365))

    return {
        "usd_jpy": round(usd_jpy, 1),
        "usd_jpy_date": today,
        "usd_jpy_source": usd_source,
        "pmi": round(pmi, 1),
        "pmi_date": pmi_date,
        "pmi_source": pmi_source,
        "temperature": round(temperature, 1),
        "weather_message": weather_message,
        "weather_date": today,
        "weather_source": weather_source,
    }


def external_indicator_multiplier(indicators: dict) -> float:
    multiplier = 1.0
    if indicators.get("pmi", 50) >= 52:
        multiplier += 0.03
    elif indicators.get("pmi", 50) <= 48:
        multiplier -= 0.03
    if indicators.get("usd_jpy", 150) >= 155:
        multiplier += 0.02
    if "大雨" in indicators.get("weather_message", "") or "悪天候" in indicators.get("weather_message", ""):
        multiplier += 0.04
    return max(0.9, min(1.12, multiplier))
