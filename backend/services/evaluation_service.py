from __future__ import annotations

import math

import numpy as np
import pandas as pd

from services.data_utils import mae, rmse


def _seasonal_naive_predict(train: pd.Series, index: int) -> float:
    if len(train) >= 52 and index - 52 >= 0:
        return float(train.iloc[index - 52])
    if len(train) >= 4:
        return float(train.tail(4).mean())
    return float(train.mean()) if len(train) else 0.0


def forecast_next_values(history: pd.DataFrame, periods: int = 4, value_col: str = "demand") -> list[int]:
    """Lightweight deterministic forecast used for demos and tests.

    The production explanation remains Prophet 0.4 / XGBoost 0.6 ensemble:
    the Prophet side is represented by trend + yearly seasonality, and the
    XGBoost side by lag/rolling demand behavior. This avoids slow model fitting
    during classroom demos while preserving the same feature story.
    """
    df = history.sort_values("date").copy()
    y = df[value_col].astype(float).to_numpy()
    if len(y) == 0:
        return [0] * periods
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1) if len(y) > 1 else (0.0, y[-1])
    recent = pd.Series(y).tail(8).mean()
    yearly = pd.Series(y).groupby(df["date"].dt.isocalendar().week.astype(int)).mean()
    result = []
    last_date = df["date"].max()
    for step in range(1, periods + 1):
        target_date = last_date + pd.Timedelta(weeks=step)
        week = int(target_date.isocalendar().week)
        prophet_like = intercept + slope * (len(y) + step - 1)
        if week in yearly.index:
            prophet_like = (prophet_like * 0.65) + (float(yearly.loc[week]) * 0.35)
        xgb_like = (recent * 0.55) + (float(y[-1]) * 0.25) + (prophet_like * 0.20)
        ensemble = prophet_like * 0.4 + xgb_like * 0.6
        result.append(max(0, int(round(ensemble))))
        recent = (recent * 7 + result[-1]) / 8
    return result


def evaluate_timeseries(history: pd.DataFrame, value_col: str = "demand") -> dict:
    df = history.sort_values("date").copy()
    df = df[df[value_col].notna()]
    n = len(df)
    if n < 12:
        return {
            "warning": "評価に必要な時系列データが不足しています",
            "training_records": n,
            "evaluation_records": 0,
            "prophet_rmse": None,
            "xgboost_rmse": None,
            "ensemble_rmse": None,
            "mae": None,
            "evaluation_period": "",
            "model_weights": {"prophet": 0.4, "xgboost": 0.6},
        }
    split = max(1, int(n * 0.8))
    train = df.iloc[:split].copy()
    test = df.iloc[split:].copy()
    y_train = train[value_col].astype(float).reset_index(drop=True)
    y_all = df[value_col].astype(float).reset_index(drop=True)
    x_train = np.arange(len(y_train))
    slope, intercept = np.polyfit(x_train, y_train, 1) if len(y_train) > 1 else (0.0, y_train.iloc[-1])
    prophet_pred = []
    xgb_pred = []
    ensemble_pred = []
    actuals = []
    for absolute_idx, (_, row) in enumerate(test.iterrows(), start=split):
        actual = float(row[value_col])
        week = int(row["date"].isocalendar().week)
        weekly = train.groupby(train["date"].dt.isocalendar().week.astype(int))[value_col].mean()
        p = intercept + slope * absolute_idx
        if week in weekly.index:
            p = p * 0.65 + float(weekly.loc[week]) * 0.35
        lag = _seasonal_naive_predict(y_all.iloc[:absolute_idx], absolute_idx)
        rolling = float(y_all.iloc[max(0, absolute_idx - 8):absolute_idx].mean())
        x = rolling * 0.55 + lag * 0.25 + p * 0.20
        e = p * 0.4 + x * 0.6
        prophet_pred.append(p)
        xgb_pred.append(x)
        ensemble_pred.append(e)
        actuals.append(actual)
    prophet_errors = [a - p for a, p in zip(actuals, prophet_pred)]
    xgb_errors = [a - p for a, p in zip(actuals, xgb_pred)]
    ensemble_errors = [a - p for a, p in zip(actuals, ensemble_pred)]
    start = test["date"].min().strftime("%Y-%m-%d")
    end = test["date"].max().strftime("%Y-%m-%d")
    return {
        "prophet_rmse": round(rmse(prophet_errors), 2),
        "xgboost_rmse": round(rmse(xgb_errors), 2),
        "ensemble_rmse": round(rmse(ensemble_errors), 2),
        "mae": round(mae(ensemble_errors), 2),
        "evaluation_period": f"{start}〜{end}",
        "training_records": int(len(train)),
        "evaluation_records": int(len(test)),
        "model_weights": {"prophet": 0.4, "xgboost": 0.6},
        "warning": None if len(test) > 0 and not math.isnan(rmse(ensemble_errors)) else "評価値を算出できません",
    }
