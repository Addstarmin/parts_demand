from __future__ import annotations

import os

from services.safety_stock_service import update_dynamic_safety_stock
from services.data_management_service import get_weekly_settings, run_weekly_update_now

_scheduler = None


def start_safety_stock_scheduler() -> str:
    """Register monthly dynamic safety-stock optimization.

    Disabled by default to avoid double execution under development reload.
    Set CMDX_ENABLE_SCHEDULER=true when running a single backend process.
    """
    global _scheduler
    if os.getenv("CMDX_ENABLE_SCHEDULER", "false").lower() != "true":
        return "disabled"
    if _scheduler is not None and _scheduler.running:
        return "already_running"
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except Exception:
        return "apscheduler_not_installed"
    scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(
        update_dynamic_safety_stock,
        CronTrigger(day=1, hour=0, minute=0, timezone="Asia/Tokyo"),
        id="cmdx_dynamic_safety_stock_monthly",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    weekly = get_weekly_settings()
    if weekly.get("enabled"):
        day_map = {"mon": "mon", "tue": "tue", "wed": "wed", "thu": "thu", "fri": "fri", "sat": "sat", "sun": "sun"}
        scheduler.add_job(
            run_weekly_update_now,
            CronTrigger(
                day_of_week=day_map.get(weekly.get("day", "mon"), "mon"),
                hour=int(weekly.get("hour", 6)),
                minute=int(weekly.get("minute", 0)),
                timezone=weekly.get("timezone", "Asia/Tokyo"),
            ),
            id="cmdx_weekly_data_update",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.start()
    _scheduler = scheduler
    return "running"
