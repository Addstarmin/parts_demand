from __future__ import annotations

import os

from services.safety_stock_service import update_dynamic_safety_stock

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
    scheduler.start()
    _scheduler = scheduler
    return "running"
