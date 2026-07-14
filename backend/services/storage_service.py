from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from services.data_utils import DB_PATH, now_jst_iso

DEFAULT_SAFETY_SETTINGS = {
    "evaluation_months": 3,
    "default_safety_factor": 1.65,
    "min_safety_stock": 100,
    "max_safety_stock": 20000,
    "max_change_rate": 0.5,
    "review_threshold_rate": 0.2,
}


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS production_notice_history (
                simulation_id TEXT PRIMARY KEY,
                executed_at TEXT NOT NULL,
                factory_id TEXT NOT NULL,
                manufacturer_id TEXT NOT NULL,
                adjustment_rate REAL NOT NULL,
                target_type TEXT,
                target_id TEXT,
                normal_total INTEGER NOT NULL,
                adjusted_total INTEGER NOT NULL,
                difference INTEGER NOT NULL,
                calculation_time_ms REAL NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS safety_stock_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                settings_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS safety_stock_change_history (
                history_id TEXT PRIMARY KEY,
                executed_at TEXT NOT NULL,
                factory_id TEXT NOT NULL,
                parts_id TEXT NOT NULL,
                old_safety_stock INTEGER NOT NULL,
                new_safety_stock INTEGER NOT NULL,
                difference INTEGER NOT NULL,
                difference_rate REAL NOT NULL,
                rmse REAL NOT NULL,
                lead_time_days REAL NOT NULL,
                safety_factor REAL NOT NULL,
                execution_type TEXT NOT NULL,
                reason TEXT NOT NULL,
                needs_review INTEGER NOT NULL
            )
            """
        )
        cur = conn.execute("SELECT COUNT(*) FROM safety_stock_settings WHERE id = 1")
        if cur.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO safety_stock_settings (id, settings_json, updated_at) VALUES (1, ?, ?)",
                (json.dumps(DEFAULT_SAFETY_SETTINGS, ensure_ascii=False), now_jst_iso()),
            )
        conn.commit()
    finally:
        conn.close()


def get_settings() -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        row = conn.execute("SELECT settings_json FROM safety_stock_settings WHERE id = 1").fetchone()
    return json.loads(row["settings_json"]) if row else DEFAULT_SAFETY_SETTINGS.copy()


def update_settings(settings: dict[str, Any]) -> dict[str, Any]:
    init_db()
    with get_connection() as conn:
        conn.execute(
            "UPDATE safety_stock_settings SET settings_json = ?, updated_at = ? WHERE id = 1",
            (json.dumps(settings, ensure_ascii=False), now_jst_iso()),
        )
        conn.commit()
    return settings
