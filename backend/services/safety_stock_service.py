from __future__ import annotations

import math
import uuid

import pandas as pd

from services.data_utils import atomic_write_csv, now_jst_iso, read_csv, rmse, safe_int
from services.storage_service import get_connection, get_settings, init_db, update_settings


def validate_settings(settings: dict) -> dict:
    evaluation_months = int(settings.get("evaluation_months", 3))
    safety_factor = float(settings.get("default_safety_factor", settings.get("safety_factor", 1.65)))
    min_stock = int(settings.get("min_safety_stock", 100))
    max_stock = int(settings.get("max_safety_stock", 20000))
    max_change = float(settings.get("max_change_rate", 0.5))
    review_rate = float(settings.get("review_threshold_rate", 0.2))
    if not 1 <= evaluation_months <= 12:
        raise ValueError("evaluation_monthsは1〜12で指定してください")
    if not 0.1 <= safety_factor <= 5.0:
        raise ValueError("default_safety_factorは0.1〜5.0で指定してください")
    if min_stock < 0:
        raise ValueError("min_safety_stockは0以上で指定してください")
    if max_stock < min_stock:
        raise ValueError("max_safety_stockはmin_safety_stock以上で指定してください")
    if not 0 <= max_change <= 1:
        raise ValueError("max_change_rateは0〜1で指定してください")
    if not 0 <= review_rate <= 1:
        raise ValueError("review_threshold_rateは0〜1で指定してください")
    return {
        "evaluation_months": evaluation_months,
        "default_safety_factor": safety_factor,
        "min_safety_stock": min_stock,
        "max_safety_stock": max_stock,
        "max_change_rate": max_change,
        "review_threshold_rate": review_rate,
    }


def save_settings(settings: dict) -> dict:
    clean = validate_settings(settings)
    return update_settings(clean)


def _latest_stock_by_part() -> pd.DataFrame:
    history = read_csv("internal_performance_history.csv")
    if history.empty:
        return pd.DataFrame(columns=["factory_id", "parts_id", "current_stock"])
    history["date"] = pd.to_datetime(history["week_start_date"])
    latest = history.sort_values("date").drop_duplicates(["factory_id", "parts_id"], keep="last")
    return latest[["factory_id", "parts_id", "ending_stock"]].rename(columns={"ending_stock": "current_stock"})


def get_current_safety_stock() -> list[dict]:
    master = read_csv("safety_stock_master.csv")
    parts = read_csv("parts_master.csv")
    stock = _latest_stock_by_part()
    if master.empty:
        return []
    df = master.merge(parts, on="parts_id", how="left").merge(stock, on=["factory_id", "parts_id"], how="left")
    return df.fillna("").to_dict(orient="records")


def get_current_safety_stock_map(factory_id: str) -> dict[str, dict]:
    rows = get_current_safety_stock()
    return {row["parts_id"]: row for row in rows if row["factory_id"] == factory_id}


def _lead_time_days(factory_id: str, parts_id: str, evaluation_months: int) -> float:
    lt = read_csv("lead_time_history.csv")
    if lt.empty:
        parts = read_csv("parts_master.csv")
        row = parts[parts["parts_id"] == parts_id]
        return float(row["lead_time_weeks"].iloc[0] * 7) if not row.empty else 7.0
    lt["recorded_date"] = pd.to_datetime(lt["recorded_date"])
    cutoff = lt["recorded_date"].max() - pd.DateOffset(months=evaluation_months)
    target = lt[(lt["factory_id"] == factory_id) & (lt["parts_id"] == parts_id) & (lt["recorded_date"] >= cutoff)]
    if target.empty:
        return 7.0
    values = pd.to_numeric(target["lead_time_days"], errors="coerce")
    values = values[(values > 0) & values.notna()]
    return float(values.mean()) if len(values) else 7.0


def _forecast_rmse(factory_id: str, parts_id: str, evaluation_months: int) -> tuple[float, int, str]:
    acc = read_csv("forecast_accuracy_history.csv")
    if acc.empty:
        return 0.0, 0, "予測精度履歴が不足しています"
    acc["forecast_date"] = pd.to_datetime(acc["forecast_date"])
    cutoff = acc["forecast_date"].max() - pd.DateOffset(months=evaluation_months)
    target = acc[(acc["factory_id"] == factory_id) & (acc["parts_id"] == parts_id) & (acc["forecast_date"] >= cutoff)].copy()
    target["error"] = pd.to_numeric(target["actual_demand"], errors="coerce") - pd.to_numeric(target["predicted_demand"], errors="coerce")
    target = target[target["error"].notna()]
    target = target[target["actual_demand"] >= 0]
    if len(target) < 4:
        return rmse(target["error"]), int(len(target)), "評価期間内の有効データが4件未満です"
    return rmse(target["error"]), int(len(target)), ""


def calculate_dynamic_safety_stock(old_stock: int, rmse_value: float, lead_time_days: float, settings: dict) -> tuple[int, str]:
    factor = float(settings["default_safety_factor"])
    raw = math.ceil(max(0.0, factor * rmse_value * math.sqrt(max(lead_time_days, 0.0) / 7.0)))
    guarded = min(max(raw, int(settings["min_safety_stock"])), int(settings["max_safety_stock"]))
    if old_stock > 0 and settings["max_change_rate"] < 1:
        max_delta = math.ceil(old_stock * float(settings["max_change_rate"]))
        guarded = min(max(guarded, old_stock - max_delta), old_stock + max_delta)
    reasons = [f"RMSE {rmse_value:.1f}", f"LT {lead_time_days:.1f}日", f"安全係数 {factor:.2f}"]
    if guarded != raw:
        reasons.append("ガードレール適用")
    return int(max(0, guarded)), " / ".join(reasons)


def build_safety_stock_preview(execution_type: str = "preview") -> dict:
    init_db()
    settings = get_settings()
    master = read_csv("safety_stock_master.csv")
    if master.empty:
        return {"settings": settings, "items": [], "summary": {"total": 0, "increase": 0, "decrease": 0, "unchanged": 0}}
    items = []
    for _, row in master.iterrows():
        old_stock = safe_int(row["safety_stock_quantity"])
        rmse_value, records, warning = _forecast_rmse(row["factory_id"], row["parts_id"], settings["evaluation_months"])
        lt_days = _lead_time_days(row["factory_id"], row["parts_id"], settings["evaluation_months"])
        new_stock, reason = calculate_dynamic_safety_stock(old_stock, rmse_value, lt_days, settings)
        diff = new_stock - old_stock
        diff_rate = 0.0 if old_stock == 0 else diff / old_stock
        status = "変更なし"
        if diff > 0:
            status = "増加"
        elif diff < 0:
            status = "減少"
        items.append(
            {
                "factory_id": row["factory_id"],
                "parts_id": row["parts_id"],
                "old_safety_stock": old_stock,
                "new_safety_stock": new_stock,
                "difference": diff,
                "difference_rate": round(diff_rate, 4),
                "rmse": round(rmse_value, 2),
                "lead_time_days": round(lt_days, 2),
                "safety_factor": settings["default_safety_factor"],
                "status": status,
                "needs_review": abs(diff_rate) >= settings["review_threshold_rate"],
                "reason": f"{reason}{' / ' + warning if warning else ''}",
                "valid_records": records,
                "execution_type": execution_type,
            }
        )
    summary = {
        "total": len(items),
        "increase": sum(1 for i in items if i["difference"] > 0),
        "decrease": sum(1 for i in items if i["difference"] < 0),
        "unchanged": sum(1 for i in items if i["difference"] == 0),
    }
    return {"settings": settings, "items": items, "summary": summary, "last_executed_at": get_last_execution_at(), "next_run_at": next_run_at()}


def optimize_safety_stock(execution_type: str = "manual") -> dict:
    preview = build_safety_stock_preview(execution_type=execution_type)
    master = read_csv("safety_stock_master.csv")
    if master.empty:
        return preview
    executed_at = now_jst_iso()
    with get_connection() as conn:
        for item in preview["items"]:
            mask = (master["factory_id"] == item["factory_id"]) & (master["parts_id"] == item["parts_id"])
            master.loc[mask, "safety_stock_quantity"] = item["new_safety_stock"]
            master.loc[mask, "safety_factor"] = item["safety_factor"]
            master.loc[mask, "updated_at"] = executed_at
            conn.execute(
                """
                INSERT INTO safety_stock_change_history
                (history_id, executed_at, factory_id, parts_id, old_safety_stock, new_safety_stock,
                 difference, difference_rate, rmse, lead_time_days, safety_factor, execution_type, reason, needs_review)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"SSH-{uuid.uuid4().hex[:12]}",
                    executed_at,
                    item["factory_id"],
                    item["parts_id"],
                    item["old_safety_stock"],
                    item["new_safety_stock"],
                    item["difference"],
                    item["difference_rate"],
                    item["rmse"],
                    item["lead_time_days"],
                    item["safety_factor"],
                    execution_type,
                    item["reason"],
                    1 if item["needs_review"] else 0,
                ),
            )
        conn.commit()
    atomic_write_csv(master, "safety_stock_master.csv")
    dynamic_rows = []
    calculation_month = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y-%m")
    for item in preview["items"]:
        dynamic_rows.append(
            {
                "calculation_month": calculation_month,
                "factory_id": item["factory_id"],
                "parts_id": item["parts_id"],
                "ai_rmse": item["rmse"],
                "lead_time_days": item["lead_time_days"],
                "calculated_safety_stock": item["new_safety_stock"],
                "updated_at": executed_at,
            }
        )
    atomic_write_csv(pd.DataFrame(dynamic_rows), "dynamic_safety_stock.csv")
    preview["executed_at"] = executed_at
    return preview


def optimize_safety_stock_legacy_response(execution_type: str = "manual") -> dict:
    result = optimize_safety_stock(execution_type=execution_type)
    items = result.get("items", [])
    total_before = sum(item["old_safety_stock"] for item in items)
    total_after = sum(item["new_safety_stock"] for item in items)
    reduction_rate = 0 if total_before == 0 else (total_before - total_after) / total_before
    updated_records = [
        {
            "factory_id": item["factory_id"],
            "parts_id": item["parts_id"],
            "old_safety_stock": item["old_safety_stock"],
            "new_safety_stock": item["new_safety_stock"],
            "ai_rmse": item["rmse"],
            "lead_time_days": item["lead_time_days"],
            "status": "REDUCED"
            if item["difference"] < 0
            else "INCREASED"
            if item["difference"] > 0
            else "NO_CHANGE",
        }
        for item in items
    ]
    return {
        "status": "success",
        "calculation_month": pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y-%m"),
        "total_records_updated": len(items),
        "warnings": [item["reason"] for item in items if item.get("needs_review")],
        "optimization_summary": {
            "total_safety_stock_volume_before": total_before,
            "total_safety_stock_volume_after": total_after,
            "reduction_rate": round(reduction_rate, 4),
            "estimated_cost_saving_yen": int(max(0, total_before - total_after) * 15),
        },
        "updated_records": updated_records,
    }


def get_safety_stock_history(limit: int = 100) -> list[dict]:
    init_db()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM safety_stock_change_history ORDER BY executed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_last_execution_at() -> str | None:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT MAX(executed_at) AS executed_at FROM safety_stock_change_history").fetchone()
    return row["executed_at"] if row and row["executed_at"] else None


def next_run_at() -> str:
    now = pd.Timestamp.now(tz="Asia/Tokyo")
    first_next_month = (now + pd.offsets.MonthBegin(1)).normalize()
    return first_next_month.isoformat()


def update_dynamic_safety_stock() -> dict:
    return optimize_safety_stock(execution_type="monthly_batch")
