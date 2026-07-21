from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.data_utils import DATA_DIR, DB_PATH, atomic_write_csv, data_path, now_jst_iso, read_csv, safe_int
from services.download_service import forecast_csv, future_actual_template_csv
from services.forecast_service import calculate_forecast
from services.product_forecast_service import get_product_forecast
from services.safety_stock_service import build_safety_stock_preview, optimize_safety_stock
from services.storage_service import get_connection, init_db

BACKUP_DIR = DATA_DIR / "backups"
IMPORT_DIR = DATA_DIR / ".imports"
MAX_UPLOAD_MB = int(os.getenv("CMDX_MAX_UPLOAD_MB", "20"))
BACKUP_RETENTION = int(os.getenv("CMDX_BACKUP_RETENTION", "10"))
DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@")


@dataclass(frozen=True)
class DatasetDefinition:
    filename: str
    label: str
    category: str
    primary_keys: list[str]
    date_columns: list[str]
    numeric_columns: list[str]
    non_negative_columns: list[str]
    positive_columns: list[str]
    allowed_modes: list[str]


DATASET_REGISTRY: dict[str, DatasetDefinition] = {
    "factory_master": DatasetDefinition("factory_master.csv", "工場マスタ", "master", ["factory_id"], [], [], [], [], ["upsert", "replace"]),
    "parts_master": DatasetDefinition("parts_master.csv", "部品マスタ", "master", ["parts_id"], [], ["lead_time_weeks", "safety_stock_days"], ["lead_time_weeks", "safety_stock_days"], ["lead_time_weeks"], ["upsert", "replace"]),
    "product_master": DatasetDefinition("product_master.csv", "製品マスタ", "master", ["product_id"], [], ["unit_price"], ["unit_price"], [], ["upsert", "replace"]),
    "bom_master": DatasetDefinition("bom_master.csv", "BOMマスタ", "master", ["product_id", "parts_id"], [], ["quantity_per_product"], ["quantity_per_product"], ["quantity_per_product"], ["upsert", "replace"]),
    "manufacturer_master": DatasetDefinition("manufacturer_master.csv", "メーカー マスタ", "master", ["manufacturer_id"], [], [], [], [], ["upsert", "replace"]),
    "manufacturer_product_mapping": DatasetDefinition("manufacturer_product_mapping.csv", "メーカー製品配分", "master", ["manufacturer_id", "product_id"], [], ["allocation_ratio"], ["allocation_ratio"], [], ["upsert", "replace"]),
    "product_demand_history": DatasetDefinition("product_demand_history.csv", "製品需要履歴", "history", ["week_start_date", "factory_id", "product_id"], ["week_start_date"], ["order_volume"], ["order_volume"], [], ["append", "upsert", "replace"]),
    "internal_performance_history": DatasetDefinition("internal_performance_history.csv", "部品実績履歴", "history", ["week_start_date", "factory_id", "parts_id"], ["week_start_date"], ["order_volume", "production_volume", "shipment_volume", "ending_stock"], ["order_volume", "production_volume", "shipment_volume", "ending_stock"], [], ["append", "upsert", "replace"]),
    "jit_shipment_history": DatasetDefinition("jit_shipment_history.csv", "JIT出荷履歴", "history", ["timestamp", "factory_id", "parts_id"], ["timestamp"], ["shipment_volume"], ["shipment_volume"], [], ["append", "upsert", "replace"]),
    "lead_time_history": DatasetDefinition("lead_time_history.csv", "リードタイム履歴", "history", ["recorded_date", "factory_id", "parts_id"], ["recorded_date"], ["lead_time_days"], ["lead_time_days"], ["lead_time_days"], ["append", "upsert", "replace"]),
    "forecast_accuracy_history": DatasetDefinition("forecast_accuracy_history.csv", "予測精度履歴", "ai", ["forecast_date", "factory_id", "parts_id"], ["forecast_date"], ["predicted_demand", "actual_demand", "error", "squared_error"], ["predicted_demand", "actual_demand", "squared_error"], [], ["append", "upsert", "replace"]),
    "safety_stock_master": DatasetDefinition("safety_stock_master.csv", "安全在庫マスタ", "ai", ["factory_id", "parts_id"], ["updated_at"], ["safety_stock_quantity", "previous_safety_stock", "safety_factor", "service_level", "rmse", "lead_time_days"], ["safety_stock_quantity", "previous_safety_stock", "safety_factor", "service_level", "rmse", "lead_time_days"], [], ["upsert", "replace"]),
    "dynamic_safety_stock": DatasetDefinition("dynamic_safety_stock.csv", "動的安全在庫履歴", "ai", ["calculation_month", "factory_id", "parts_id"], ["calculation_month"], ["ai_rmse", "lead_time_days", "calculated_safety_stock"], ["ai_rmse", "lead_time_days", "calculated_safety_stock"], [], ["append", "upsert", "replace"]),
}


def ensure_data_management_db() -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS data_update_history (
                update_id TEXT PRIMARY KEY,
                executed_at TEXT NOT NULL,
                update_type TEXT NOT NULL,
                source TEXT,
                dataset_id TEXT,
                update_mode TEXT,
                status TEXT NOT NULL,
                added_rows INTEGER DEFAULT 0,
                updated_rows INTEGER DEFAULT 0,
                skipped_rows INTEGER DEFAULT 0,
                error_rows INTEGER DEFAULT 0,
                before_min_date TEXT,
                before_max_date TEXT,
                after_min_date TEXT,
                after_max_date TEXT,
                backup_id TEXT,
                duration_ms REAL DEFAULT 0,
                message TEXT,
                error_detail TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_update_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                settings_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        cur = conn.execute("SELECT COUNT(*) FROM weekly_update_settings WHERE id = 1")
        if cur.fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO weekly_update_settings (id, settings_json, updated_at) VALUES (1, ?, ?)",
                (json.dumps(default_weekly_settings(), ensure_ascii=False), now_jst_iso()),
            )
        conn.commit()


def default_weekly_settings() -> dict[str, Any]:
    return {
        "enabled": os.getenv("CMDX_ENABLE_WEEKLY_DATA_UPDATE", "false").lower() == "true",
        "day": os.getenv("CMDX_WEEKLY_UPDATE_DAY", "mon"),
        "hour": int(os.getenv("CMDX_WEEKLY_UPDATE_HOUR", "6")),
        "minute": int(os.getenv("CMDX_WEEKLY_UPDATE_MINUTE", "0")),
        "timezone": os.getenv("CMDX_WEEKLY_UPDATE_TIMEZONE", "Asia/Tokyo"),
        "source": os.getenv("CMDX_WEEKLY_UPDATE_SOURCE", "demo"),
        "directory": os.getenv("CMDX_WEEKLY_UPDATE_DIRECTORY", ""),
        "recalculate_forecast": True,
        "recalculate_safety_stock": True,
        "retry_count": 0,
        "last_run_at": None,
        "last_result": None,
    }


def dataset_def(dataset_id: str) -> DatasetDefinition:
    if dataset_id not in DATASET_REGISTRY:
        raise ValueError("許可されていないデータセットです")
    return DATASET_REGISTRY[dataset_id]


def _period(df: pd.DataFrame, dates: list[str]) -> tuple[str | None, str | None]:
    if df.empty or not dates:
        return None, None
    values = []
    for col in dates:
        if col in df.columns:
            values.append(pd.to_datetime(df[col], errors="coerce"))
    if not values:
        return None, None
    merged = pd.concat(values).dropna()
    if merged.empty:
        return None, None
    return merged.min().strftime("%Y-%m-%d"), merged.max().strftime("%Y-%m-%d")


def _file_updated_at(path: Path) -> str | None:
    if not path.exists():
        return None
    return pd.Timestamp(path.stat().st_mtime, unit="s", tz="Asia/Tokyo").isoformat()


def dataset_info(dataset_id: str) -> dict:
    definition = dataset_def(dataset_id)
    path = data_path(definition.filename)
    df = read_csv(definition.filename)
    start, end = _period(df, definition.date_columns)
    return {
        "dataset_id": dataset_id,
        "filename": definition.filename,
        "label": definition.label,
        "category": definition.category,
        "row_count": int(len(df)),
        "columns": list(df.columns) if not df.empty else _expected_columns(definition.filename),
        "date_start": start,
        "date_end": end,
        "last_updated_at": _file_updated_at(path),
        "allowed_modes": definition.allowed_modes,
        "primary_keys": definition.primary_keys,
        "date_columns": definition.date_columns,
    }


def list_datasets() -> list[dict]:
    return [dataset_info(dataset_id) for dataset_id in DATASET_REGISTRY]


def get_summary() -> dict:
    ensure_data_management_db()
    datasets = list_datasets()
    date_starts = [d["date_start"] for d in datasets if d["date_start"]]
    date_ends = [d["date_end"] for d in datasets if d["date_end"]]
    perf = read_csv("internal_performance_history.csv")
    jit = read_csv("jit_shipment_history.csv")
    settings = get_weekly_settings()
    return {
        "data_start": min(date_starts) if date_starts else None,
        "data_end": max(date_ends) if date_ends else None,
        "last_actual_week": perf["week_start_date"].max() if not perf.empty else None,
        "last_updated_at": max([d["last_updated_at"] for d in datasets if d["last_updated_at"]], default=None),
        "performance_rows": int(len(perf)),
        "jit_rows": int(len(jit)),
        "dataset_count": len(DATASET_REGISTRY),
        "weekly_update_enabled": settings["enabled"],
        "next_weekly_update_at": next_weekly_run_at(settings),
    }


def get_preview(dataset_id: str, limit: int = 20) -> dict:
    definition = dataset_def(dataset_id)
    df = read_csv(definition.filename).head(max(1, min(limit, 100)))
    return {"dataset": dataset_info(dataset_id), "rows": df.fillna("").to_dict(orient="records")}


def dataset_csv_bytes(dataset_id: str) -> bytes:
    definition = dataset_def(dataset_id)
    df = read_csv(definition.filename)
    if df.empty:
        df = pd.DataFrame(columns=_expected_columns(definition.filename))
    return df.to_csv(index=False).encode("utf-8-sig")


def export_all_zip() -> tuple[bytes, str]:
    generated_at = pd.Timestamp.now(tz="Asia/Tokyo")
    manifest = {"generated_at": generated_at.isoformat(), "files": []}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for dataset_id, definition in DATASET_REGISTRY.items():
            df = read_csv(definition.filename)
            start, end = _period(df, definition.date_columns)
            zf.writestr(definition.filename, dataset_csv_bytes(dataset_id))
            manifest["files"].append(
                {
                    "dataset_id": dataset_id,
                    "filename": definition.filename,
                    "row_count": int(len(df)),
                    "columns": list(df.columns),
                    "date_start": start,
                    "date_end": end,
                }
            )
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    name = f"cmdx_data_export_{generated_at.strftime('%Y%m%d_%H%M%S')}.zip"
    return buffer.getvalue(), name


def _expected_columns(filename: str) -> list[str]:
    path = data_path(filename)
    if path.exists():
        try:
            return list(pd.read_csv(path, nrows=0).columns)
        except Exception:
            return []
    return []


def _read_uploaded_csv(csv_text: str) -> pd.DataFrame:
    if len(csv_text.encode("utf-8", errors="ignore")) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"アップロード上限 {MAX_UPLOAD_MB}MB を超えています")
    text = csv_text.lstrip("\ufeff")
    if not text.strip():
        raise ValueError("空ファイルは取り込めません")
    try:
        return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except Exception as exc:
        raise ValueError("CSVとして解析できません") from exc


def _row_number(idx: int) -> int:
    return idx + 2


def _validate_dataframe(dataset_id: str, uploaded: pd.DataFrame, mode: str) -> dict:
    definition = dataset_def(dataset_id)
    if mode not in definition.allowed_modes:
        raise ValueError("このデータセットでは指定された更新方式を利用できません")
    current = read_csv(definition.filename)
    required = set(current.columns if not current.empty else _expected_columns(definition.filename))
    missing = sorted(required - set(uploaded.columns))
    errors: list[dict] = []
    warnings: list[dict] = []
    if missing:
        errors.append({"row": None, "message": f"必須カラムが不足しています: {', '.join(missing)}"})
    unknown = sorted(set(uploaded.columns) - required)
    if unknown:
        warnings.append({"row": None, "message": f"未定義カラムは反映時に無視されます: {', '.join(unknown)}"})
        uploaded = uploaded[[c for c in uploaded.columns if c in required]]
    if len(uploaded) == 0:
        errors.append({"row": None, "message": "空ファイルは取り込めません"})
    for col in required:
        if col in uploaded.columns:
            empty = uploaded[uploaded[col].astype(str).str.strip() == ""]
            if col in definition.primary_keys and not empty.empty:
                for idx in empty.index[:20]:
                    errors.append({"row": _row_number(idx), "message": f"{col}が空です"})
    for col in definition.date_columns:
        if col in uploaded.columns:
            parsed = pd.to_datetime(uploaded[col], errors="coerce")
            bad = uploaded[(uploaded[col].astype(str).str.strip() != "") & parsed.isna()]
            for idx in bad.index[:20]:
                errors.append({"row": _row_number(idx), "message": f"{col}の日付形式が不正です: {uploaded.at[idx, col]}"})
    for col in definition.numeric_columns:
        if col in uploaded.columns:
            values = pd.to_numeric(uploaded[col], errors="coerce")
            bad = uploaded[(uploaded[col].astype(str).str.strip() != "") & values.isna()]
            for idx in bad.index[:20]:
                errors.append({"row": _row_number(idx), "message": f"{col}に数値以外が入力されています: {uploaded.at[idx, col]}"})
            for idx in uploaded[(values < 0) & uploaded[col].astype(str).str.strip().ne("")].index[:20]:
                if col in definition.non_negative_columns:
                    errors.append({"row": _row_number(idx), "message": f"{col}に負の値が入力されています: {uploaded.at[idx, col]}"})
            for idx in uploaded[(values <= 0) & uploaded[col].astype(str).str.strip().ne("")].index[:20]:
                if col in definition.positive_columns:
                    errors.append({"row": _row_number(idx), "message": f"{col}は0より大きい値が必要です: {uploaded.at[idx, col]}"})
            q = values.dropna()
            if len(q) and q.max() > max(1000000, q.median() * 20):
                warnings.append({"row": None, "message": f"{col}に極端な外れ値の可能性があります: 最大 {q.max():.0f}"})
    if definition.primary_keys and all(col in uploaded.columns for col in definition.primary_keys):
        dup = uploaded[uploaded.duplicated(definition.primary_keys, keep=False)]
        for idx in dup.index[:20]:
            key = ", ".join(f"{col}={uploaded.at[idx, col]}" for col in definition.primary_keys)
            errors.append({"row": _row_number(idx), "message": f"主キーが重複しています: {key}"})
    full_dup = uploaded[uploaded.duplicated(keep=False)]
    if not full_dup.empty:
        warnings.append({"row": int(_row_number(full_dup.index[0])), "message": "完全重複行があります"})
    for col in uploaded.columns:
        if uploaded[col].astype(str).str.len().max() > 500:
            warnings.append({"row": None, "message": f"{col}に500文字を超える値があります"})
        dangerous = uploaded[uploaded[col].astype(str).str.startswith(DANGEROUS_FORMULA_PREFIXES, na=False)]
        if not dangerous.empty and col not in definition.numeric_columns:
            warnings.append({"row": int(_row_number(dangerous.index[0])), "message": f"{col}にCSV数式として解釈される可能性のある値があります"})
    _validate_references(dataset_id, uploaded, errors)
    before_min, before_max = _period(current, definition.date_columns)
    upload_min, upload_max = _period(uploaded, definition.date_columns)
    if upload_max and before_min and upload_max < before_min:
        warnings.append({"row": None, "message": "既存期間より古いデータのみが含まれています"})
    counts = _change_counts(current, uploaded, definition, mode) if not errors else {"added_rows": 0, "updated_rows": 0, "skipped_rows": 0}
    return {
        "valid": len(errors) == 0,
        "dataset_id": dataset_id,
        "update_mode": mode,
        "errors": errors,
        "warnings": warnings,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "before_period": {"start": before_min, "end": before_max},
        "after_period": {"start": min([x for x in [before_min, upload_min] if x], default=None), "end": max([x for x in [before_max, upload_max] if x], default=None)},
        "preview_rows": uploaded.head(20).fillna("").to_dict(orient="records"),
        **counts,
    }


def _validate_references(dataset_id: str, df: pd.DataFrame, errors: list[dict]) -> None:
    refs = {
        "factory_id": set(read_csv("factory_master.csv").get("factory_id", [])),
        "parts_id": set(read_csv("parts_master.csv").get("parts_id", [])),
        "product_id": set(read_csv("product_master.csv").get("product_id", [])),
        "manufacturer_id": set(read_csv("manufacturer_master.csv").get("manufacturer_id", [])),
    }
    allowed_self = {
        "factory_master": {"factory_id"},
        "parts_master": {"parts_id"},
        "product_master": {"product_id"},
        "manufacturer_master": {"manufacturer_id"},
    }.get(dataset_id, set())
    for col, values in refs.items():
        if col in df.columns and col not in allowed_self:
            bad = df[(df[col].astype(str).str.strip() != "") & ~df[col].isin(values)]
            for idx in bad.index[:20]:
                errors.append({"row": _row_number(idx), "message": f'{col}「{df.at[idx, col]}」はマスタに存在しません'})


def _change_counts(current: pd.DataFrame, uploaded: pd.DataFrame, definition: DatasetDefinition, mode: str) -> dict:
    if mode == "replace" or current.empty:
        return {"added_rows": int(len(uploaded)), "updated_rows": 0, "skipped_rows": 0}
    key_cols = definition.primary_keys
    cur_keys = set(map(tuple, current[key_cols].astype(str).to_numpy())) if key_cols and all(c in current.columns for c in key_cols) else set()
    up_keys = list(map(tuple, uploaded[key_cols].astype(str).to_numpy())) if key_cols and all(c in uploaded.columns for c in key_cols) else []
    existing = sum(1 for key in up_keys if key in cur_keys)
    added = len(uploaded) - existing
    if mode == "append":
        return {"added_rows": int(added), "updated_rows": 0, "skipped_rows": int(existing)}
    return {"added_rows": int(added), "updated_rows": int(existing), "skipped_rows": 0}


def validate_import(dataset_id: str, update_mode: str, csv_text: str, original_filename: str = "upload.csv") -> dict:
    ensure_data_management_db()
    uploaded = _read_uploaded_csv(csv_text)
    validation = _validate_dataframe(dataset_id, uploaded, update_mode)
    session_id = f"IMP-{uuid.uuid4().hex[:12]}"
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "dataset_id": dataset_id,
        "update_mode": update_mode,
        "original_filename": Path(original_filename).name,
        "csv_text": csv_text,
        "validation": validation,
        "created_at": now_jst_iso(),
    }
    (IMPORT_DIR / f"{session_id}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"session_id": session_id, **validation, "commit_allowed": validation["valid"]}


def _load_import_session(session_id: str) -> dict:
    if not session_id.startswith("IMP-"):
        raise ValueError("不正な検証セッションです")
    path = IMPORT_DIR / f"{session_id}.json"
    if not path.exists():
        raise ValueError("検証済みセッションが見つかりません")
    return json.loads(path.read_text(encoding="utf-8"))


def _backup_manifest(backup_id: str, trigger: str, dataset_id: str | None, update_mode: str | None, original_filename: str | None, uploaded_rows: int, user_action: str) -> dict:
    files = []
    target_defs = [dataset_def(dataset_id)] if dataset_id else [d for d in DATASET_REGISTRY.values()]
    for definition in target_defs:
        path = data_path(definition.filename)
        checksum = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        df = read_csv(definition.filename)
        files.append({"filename": definition.filename, "row_count": int(len(df)), "checksum": checksum})
    return {
        "backup_id": backup_id,
        "created_at": now_jst_iso(),
        "trigger": trigger,
        "dataset_id": dataset_id,
        "update_mode": update_mode,
        "original_filename": original_filename,
        "original_row_count": files[0]["row_count"] if files else 0,
        "uploaded_row_count": uploaded_rows,
        "user_action": user_action,
        "files": files,
    }


def create_backup(trigger: str, dataset_id: str | None = None, update_mode: str | None = None, original_filename: str | None = None, uploaded_rows: int = 0, user_action: str = "") -> str:
    backup_id = pd.Timestamp.now(tz="Asia/Tokyo").strftime("%Y%m%d_%H%M%S") + f"_{uuid.uuid4().hex[:6]}"
    target = BACKUP_DIR / backup_id
    target.mkdir(parents=True, exist_ok=False)
    definitions = [dataset_def(dataset_id)] if dataset_id else [d for d in DATASET_REGISTRY.values()]
    for definition in definitions:
        src = data_path(definition.filename)
        if src.exists():
            shutil.copy2(src, target / definition.filename)
    if DB_PATH.exists():
        shutil.copy2(DB_PATH, target / "cmdx.sqlite3")
    manifest = _backup_manifest(backup_id, trigger, dataset_id, update_mode, original_filename, uploaded_rows, user_action)
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    prune_backups()
    return backup_id


def prune_backups() -> None:
    if not BACKUP_DIR.exists():
        return
    backups = sorted([p for p in BACKUP_DIR.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)
    for old in backups[BACKUP_RETENTION:]:
        shutil.rmtree(old, ignore_errors=True)


def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    rows = []
    for path in sorted([p for p in BACKUP_DIR.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True):
        manifest_path = path / "manifest.json"
        if manifest_path.exists():
            rows.append(json.loads(manifest_path.read_text(encoding="utf-8")))
    return rows


def _apply_update(current: pd.DataFrame, uploaded: pd.DataFrame, definition: DatasetDefinition, mode: str) -> pd.DataFrame:
    columns = list(current.columns) if not current.empty else _expected_columns(definition.filename)
    uploaded = uploaded[[c for c in columns if c in uploaded.columns]].copy()
    if mode == "replace" or current.empty:
        return uploaded[columns]
    if mode == "append":
        key_cols = definition.primary_keys
        if key_cols and all(c in current.columns for c in key_cols):
            cur_keys = set(map(tuple, current[key_cols].astype(str).to_numpy()))
            uploaded = uploaded[[tuple(row) not in cur_keys for row in uploaded[key_cols].astype(str).to_numpy()]]
        return pd.concat([current, uploaded], ignore_index=True)[columns]
    indexed = current.set_index(definition.primary_keys, drop=False)
    uploaded_indexed = uploaded.set_index(definition.primary_keys, drop=False)
    for key, row in uploaded_indexed.iterrows():
        indexed.loc[key, columns] = row[columns]
    return indexed.reset_index(drop=True)[columns]


def _coerce_for_write(df: pd.DataFrame, definition: DatasetDefinition) -> pd.DataFrame:
    result = df.copy()
    for col in definition.numeric_columns:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce").fillna(0)
            if (result[col] % 1 == 0).all():
                result[col] = result[col].astype(int)
    return result


def _record_history(**kwargs) -> None:
    ensure_data_management_db()
    fields = {
        "update_id": f"DUH-{uuid.uuid4().hex[:12]}",
        "executed_at": now_jst_iso(),
        "update_type": "manual",
        "source": "csv",
        "dataset_id": None,
        "update_mode": None,
        "status": "success",
        "added_rows": 0,
        "updated_rows": 0,
        "skipped_rows": 0,
        "error_rows": 0,
        "before_min_date": None,
        "before_max_date": None,
        "after_min_date": None,
        "after_max_date": None,
        "backup_id": None,
        "duration_ms": 0,
        "message": "",
        "error_detail": None,
    }
    fields.update(kwargs)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO data_update_history
            (update_id, executed_at, update_type, source, dataset_id, update_mode, status,
             added_rows, updated_rows, skipped_rows, error_rows, before_min_date, before_max_date,
             after_min_date, after_max_date, backup_id, duration_ms, message, error_detail)
            VALUES (:update_id, :executed_at, :update_type, :source, :dataset_id, :update_mode, :status,
             :added_rows, :updated_rows, :skipped_rows, :error_rows, :before_min_date, :before_max_date,
             :after_min_date, :after_max_date, :backup_id, :duration_ms, :message, :error_detail)
            """,
            fields,
        )
        conn.commit()


def commit_import(session_id: str, recalculate_forecast: bool = False, recalculate_safety_stock: bool = False, confirm_replace: bool = False) -> dict:
    started = time.perf_counter()
    session = _load_import_session(session_id)
    validation = session["validation"]
    if not validation["valid"]:
        raise ValueError("エラーがある検証結果は反映できません")
    dataset_id = session["dataset_id"]
    definition = dataset_def(dataset_id)
    mode = session["update_mode"]
    if mode == "replace" and not confirm_replace:
        raise ValueError("全件置換には確認が必要です")
    uploaded = _read_uploaded_csv(session["csv_text"])
    current = read_csv(definition.filename)
    backup_id = create_backup("import", dataset_id, mode, session.get("original_filename"), len(uploaded), "commit")
    updated = _apply_update(current, uploaded, definition, mode)
    updated = _coerce_for_write(updated, definition)
    atomic_write_csv(updated, definition.filename)
    reread = read_csv(definition.filename)
    if len(reread) != len(updated):
        raise RuntimeError("CSV更新後の再読込検証に失敗しました")
    safety_result = optimize_safety_stock("data_import") if recalculate_safety_stock else None
    recalculated_targets = _forecast_recalculation_count() if recalculate_forecast else 0
    after_start, after_end = _period(reread, definition.date_columns)
    _record_history(
        update_type="manual",
        source="csv",
        dataset_id=dataset_id,
        update_mode=mode,
        status="success",
        added_rows=validation["added_rows"],
        updated_rows=validation["updated_rows"],
        skipped_rows=validation["skipped_rows"],
        error_rows=0,
        before_min_date=validation["before_period"]["start"],
        before_max_date=validation["before_period"]["end"],
        after_min_date=after_start,
        after_max_date=after_end,
        backup_id=backup_id,
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        message="CSVを反映しました",
    )
    return {
        "status": "success",
        "dataset_id": dataset_id,
        "update_mode": mode,
        "backup_id": backup_id,
        "added_rows": validation["added_rows"],
        "updated_rows": validation["updated_rows"],
        "skipped_rows": validation["skipped_rows"],
        "new_row_count": int(len(reread)),
        "new_period": {"start": after_start, "end": after_end},
        "recalculated_targets": recalculated_targets,
        "forecast_success": recalculated_targets,
        "forecast_failed": 0,
        "safety_stock_updated": safety_result["summary"]["total"] if safety_result else 0,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def restore_backup(backup_id: str) -> dict:
    if "/" in backup_id or "\\" in backup_id or ".." in backup_id:
        raise ValueError("不正なバックアップIDです")
    source = BACKUP_DIR / backup_id
    if not source.exists():
        raise ValueError("バックアップが見つかりません")
    current_backup = create_backup("pre_restore", None, None, None, 0, "restore")
    for definition in DATASET_REGISTRY.values():
        src = source / definition.filename
        if src.exists():
            shutil.copy2(src, data_path(definition.filename))
    db_src = source / "cmdx.sqlite3"
    if db_src.exists():
        shutil.copy2(db_src, DB_PATH)
    _record_history(update_type="restore", source="backup", status="success", backup_id=current_backup, message=f"{backup_id}を復元しました")
    return {"status": "success", "restored_backup_id": backup_id, "pre_restore_backup_id": current_backup}


def _forecast_recalculation_count() -> int:
    products = read_csv("product_master.csv")
    parts = read_csv("parts_master.csv")
    factories = read_csv("factory_master.csv")
    return int(len(products) + len(parts) * len(factories))


def recalculate_forecast() -> dict:
    started = time.perf_counter()
    count = _forecast_recalculation_count()
    _record_history(update_type="recalculate", source="forecast", status="success", duration_ms=round((time.perf_counter() - started) * 1000, 2), message="予測はCSV再読込により次回API応答へ反映されます")
    return {"status": "success", "recalculated_targets": count, "forecast_success": count, "forecast_failed": 0, "duration_ms": round((time.perf_counter() - started) * 1000, 2)}


def recalculate_safety_stock() -> dict:
    started = time.perf_counter()
    result = optimize_safety_stock("data_management")
    _record_history(update_type="recalculate", source="safety_stock", status="success", duration_ms=round((time.perf_counter() - started) * 1000, 2), message="安全在庫を再計算しました")
    return {"status": "success", "safety_stock_updated": result["summary"]["total"], "summary": result["summary"], "duration_ms": round((time.perf_counter() - started) * 1000, 2)}


def recalculate_all() -> dict:
    f = recalculate_forecast()
    s = recalculate_safety_stock()
    return {"status": "success", **f, "safety_stock_updated": s["safety_stock_updated"], "safety_summary": s["summary"]}


def forecast_export_csv(factory_id: str | None = None, target_type: str | None = None, target_id: str | None = None) -> bytes:
    rows = []
    generated_at = now_jst_iso()
    products = read_csv("product_master.csv")
    parts = read_csv("parts_master.csv")
    if target_type == "product" and factory_id and target_id:
        text = forecast_csv(factory_id, "product", target_id)
        return text.encode("utf-8-sig")
    if target_type == "part" and factory_id and target_id:
        text = forecast_csv(factory_id, "part", target_id)
        return text.encode("utf-8-sig")
    for _, product in products.iterrows():
        if factory_id and product["factory_id"] != factory_id:
            continue
        result = get_product_forecast(product["factory_id"], product["product_id"])
        if not result:
            continue
        for point in result["forecast_chart"]:
            if point.get("normal_forecast") is None:
                continue
            rows.append(
                {
                    "forecast_week": point["date"],
                    "factory_id": result["factory_id"],
                    "product_id": result["product_id"],
                    "parts_id": "",
                    "predicted_demand": point["normal_forecast"],
                    "lower_bound": int(point["normal_forecast"] * 0.92),
                    "upper_bound": int(point["normal_forecast"] * 1.08),
                    "current_inventory": result["current_stock"],
                    "safety_stock": result["safety_stock"],
                    "recommended_production": result["recommended_production"],
                    "recommended_order": result["recommended_order"],
                    "recommended_shipment": result["recommended_shipping"],
                    "generated_at": generated_at,
                }
            )
    if not rows:
        rows = [{"forecast_week": "", "factory_id": factory_id or "", "product_id": "", "parts_id": "", "predicted_demand": "", "lower_bound": "", "upper_bound": "", "current_inventory": "", "safety_stock": "", "recommended_production": "", "recommended_order": "", "recommended_shipment": "", "generated_at": generated_at}]
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8-sig")


def future_template_csv(factory_id: str | None = None, parts_id: str | None = None, product_id: str | None = None) -> bytes:
    return future_actual_template_csv(factory_id=factory_id, parts_id=parts_id, product_id=product_id).encode("utf-8-sig")


def get_weekly_settings() -> dict:
    ensure_data_management_db()
    with get_connection() as conn:
        row = conn.execute("SELECT settings_json FROM weekly_update_settings WHERE id = 1").fetchone()
    settings = default_weekly_settings()
    if row:
        settings.update(json.loads(row["settings_json"]))
    settings["next_run_at"] = next_weekly_run_at(settings)
    return settings


def save_weekly_settings(settings: dict) -> dict:
    clean = default_weekly_settings()
    clean.update({k: settings[k] for k in settings if k in clean})
    clean["hour"] = max(0, min(23, int(clean["hour"])))
    clean["minute"] = max(0, min(59, int(clean["minute"])))
    if clean["source"] not in {"demo", "directory"}:
        raise ValueError("sourceはdemoまたはdirectoryを指定してください")
    ensure_data_management_db()
    with get_connection() as conn:
        conn.execute("UPDATE weekly_update_settings SET settings_json = ?, updated_at = ? WHERE id = 1", (json.dumps(clean, ensure_ascii=False), now_jst_iso()))
        conn.commit()
    clean["next_run_at"] = next_weekly_run_at(clean)
    return clean


def next_weekly_run_at(settings: dict) -> str:
    days = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
    now = pd.Timestamp.now(tz=settings.get("timezone", "Asia/Tokyo"))
    target = days.get(settings.get("day", "mon"), 0)
    delta = (target - now.weekday()) % 7
    candidate = (now + pd.Timedelta(days=delta)).replace(hour=int(settings.get("hour", 6)), minute=int(settings.get("minute", 0)), second=0, microsecond=0)
    if candidate <= now:
        candidate += pd.Timedelta(days=7)
    return candidate.isoformat()


def weekly_history(limit: int = 50) -> list[dict]:
    ensure_data_management_db()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM data_update_history ORDER BY executed_at DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


def _last_week() -> pd.Timestamp:
    perf = read_csv("internal_performance_history.csv")
    if perf.empty:
        return pd.Timestamp("2026-07-06")
    return pd.to_datetime(perf["week_start_date"]).max()


def _season_for_week(week: pd.Timestamp) -> float:
    factor = 1 + 0.04 * math.sin(2 * math.pi * week.dayofyear / 365)
    if week.month in (3, 6, 9, 12):
        factor *= 1.05
    if week.month in (1, 5, 8) and week.day < 15:
        factor *= 0.82
    return factor


def demo_next_week_frames() -> dict[str, pd.DataFrame]:
    rng_week = _last_week() + pd.Timedelta(weeks=1)
    seed = int(rng_week.strftime("%Y%m%d"))
    rng = np.random.default_rng(seed)
    product_hist = read_csv("product_demand_history.csv")
    products = read_csv("product_master.csv")
    bom = read_csv("bom_master.csv")
    internal = read_csv("internal_performance_history.csv")
    parts = read_csv("parts_master.csv")
    product_rows = []
    for _, product in products.iterrows():
        hist = product_hist[product_hist["product_id"] == product["product_id"]].tail(8)
        recent = float(hist["order_volume"].mean())
        trend = 0 if len(hist) < 2 else (float(hist["order_volume"].tail(4).mean()) - float(hist["order_volume"].head(4).mean())) / max(recent, 1)
        vol = max(1, int(round(recent * (1 + trend * 0.35) * _season_for_week(rng_week) + rng.normal(0, recent * 0.025))))
        product_rows.append({"week_start_date": rng_week.strftime("%Y-%m-%d"), "factory_id": product["factory_id"], "product_id": product["product_id"], "manufacturer_id": product["manufacturer_id"], "order_volume": vol})
    product_df = pd.DataFrame(product_rows)
    perf_rows = []
    latest_stock = internal.sort_values("week_start_date").drop_duplicates(["factory_id", "parts_id"], keep="last")
    for factory_id in products["factory_id"].unique():
        for part_id in parts["parts_id"]:
            demand = 0
            for _, product in products[products["factory_id"] == factory_id].iterrows():
                q = bom[(bom["product_id"] == product["product_id"]) & (bom["parts_id"] == part_id)]
                if q.empty:
                    continue
                demand += int(product_df[product_df["product_id"] == product["product_id"]]["order_volume"].iloc[0]) * int(q.iloc[0]["quantity_per_product"])
            if demand == 0:
                demand = max(0, int(rng.normal(60, 12)))
            stock_row = latest_stock[(latest_stock["factory_id"] == factory_id) & (latest_stock["parts_id"] == part_id)]
            begin_stock = int(stock_row["ending_stock"].iloc[0]) if not stock_row.empty else demand
            target_stock = max(80, demand * (0.8 + 0.4 * rng.random()))
            production = max(0, int(round(demand + 0.55 * (target_stock - begin_stock) + rng.normal(0, max(10, demand * 0.02)))))
            shipment = min(demand, begin_stock + production)
            ending = max(0, int(begin_stock + production - shipment + rng.normal(0, 3)))
            perf_rows.append({"week_start_date": rng_week.strftime("%Y-%m-%d"), "factory_id": factory_id, "parts_id": part_id, "order_volume": demand, "production_volume": production, "shipment_volume": shipment, "ending_stock": ending})
    perf_df = pd.DataFrame(perf_rows)
    jit_rows = []
    day_ratio = {0: 1.15, 1: 1.35, 2: 1.0, 3: 1.22, 4: 0.86, 5: 0.18, 6: 0.08}
    slots = {"06:30:00": 0.25, "10:00:00": 0.34, "15:30:00": 0.29, "20:00:00": 0.12}
    for _, row in perf_df.iterrows():
        weights = []
        keys = []
        for day in pd.date_range(rng_week, periods=7, freq="D"):
            for slot, sr in slots.items():
                boost = 1.2 if row["factory_id"] == "F-02" and row["parts_id"] == "PT-1002" and day.weekday() == 1 and slot == "10:00:00" else 1.0
                weights.append(day_ratio[day.weekday()] * sr * boost)
                keys.append((day, slot))
        total = sum(weights)
        allocated = [int(round(int(row["shipment_volume"]) * w / total)) for w in weights]
        allocated[int(np.argmax(weights))] += int(row["shipment_volume"]) - sum(allocated)
        for (day, slot), qty in zip(keys, allocated):
            jit_rows.append({"timestamp": f"{day.strftime('%Y-%m-%d')} {slot}", "factory_id": row["factory_id"], "parts_id": row["parts_id"], "shipment_volume": max(0, qty)})
    acc_rows = []
    for _, row in perf_df.iterrows():
        predicted = max(0, int(row["order_volume"] * rng.uniform(0.94, 1.06)))
        error = int(row["order_volume"]) - predicted
        acc_rows.append({"forecast_date": rng_week.strftime("%Y-%m-%d"), "factory_id": row["factory_id"], "parts_id": row["parts_id"], "predicted_demand": predicted, "actual_demand": int(row["order_volume"]), "error": error, "squared_error": error * error, "model_version": "weekly-demo"})
    return {
        "product_demand_history": product_df,
        "internal_performance_history": perf_df,
        "jit_shipment_history": pd.DataFrame(jit_rows),
        "forecast_accuracy_history": pd.DataFrame(acc_rows),
    }


def preview_demo_next_week() -> dict:
    frames = demo_next_week_frames()
    week = frames["product_demand_history"]["week_start_date"].iloc[0]
    exists = week in set(read_csv("product_demand_history.csv").get("week_start_date", []))
    return {"next_week": week, "already_exists": bool(exists), "datasets": {k: {"row_count": len(v), "preview_rows": v.head(10).to_dict(orient="records")} for k, v in frames.items()}}


def commit_demo_next_week(recalculate_forecast_flag: bool = True, recalculate_safety_stock_flag: bool = True) -> dict:
    preview = preview_demo_next_week()
    if preview["already_exists"]:
        return {"status": "warning", "message": "同じ週の実績はすでに存在します", **preview}
    backup_id = create_backup("weekly_demo", None, "append", None, 0, "demo_next_week")
    frames = demo_next_week_frames()
    added = 0
    for dataset_id, frame in frames.items():
        definition = dataset_def(dataset_id)
        current = read_csv(definition.filename)
        updated = pd.concat([current, frame], ignore_index=True)
        atomic_write_csv(_coerce_for_write(updated, definition), definition.filename)
        added += len(frame)
    safety_result = optimize_safety_stock("weekly_demo") if recalculate_safety_stock_flag else None
    forecast_count = _forecast_recalculation_count() if recalculate_forecast_flag else 0
    _record_history(update_type="weekly", source="demo", dataset_id="multiple", update_mode="append", status="success", added_rows=added, backup_id=backup_id, message=f"{preview['next_week']} のデモ実績を追加しました")
    return {"status": "success", "next_week": preview["next_week"], "added_rows": added, "backup_id": backup_id, "recalculated_targets": forecast_count, "safety_stock_updated": safety_result["summary"]["total"] if safety_result else 0}


def run_weekly_update_now() -> dict:
    settings = get_weekly_settings()
    if settings.get("source") == "directory":
        result = run_directory_update(settings)
    else:
        result = commit_demo_next_week(settings.get("recalculate_forecast", True), settings.get("recalculate_safety_stock", True))
    settings["last_run_at"] = now_jst_iso()
    settings["last_result"] = result.get("status")
    save_weekly_settings(settings)
    return result


def run_directory_update(settings: dict) -> dict:
    directory = Path(settings.get("directory") or "")
    if not directory.exists() or not directory.is_dir():
        raise ValueError("directory sourceのパスが存在しません")
    processed = directory / "processed"
    failed = directory / "failed"
    processed.mkdir(exist_ok=True)
    failed.mkdir(exist_ok=True)
    results = []
    for dataset_id, definition in DATASET_REGISTRY.items():
        src = directory / definition.filename
        if not src.exists():
            continue
        try:
            text = src.read_text(encoding="utf-8-sig")
            validation = validate_import(dataset_id, "upsert" if "upsert" in definition.allowed_modes else "append", text, definition.filename)
            if not validation["valid"]:
                raise ValueError(json.dumps(validation["errors"], ensure_ascii=False))
            commit = commit_import(validation["session_id"], settings.get("recalculate_forecast", True), settings.get("recalculate_safety_stock", True), confirm_replace=True)
            shutil.move(str(src), processed / definition.filename)
            results.append({"dataset_id": dataset_id, "status": "success", **commit})
        except Exception as exc:
            shutil.move(str(src), failed / definition.filename)
            (failed / f"{definition.filename}.error.log").write_text(str(exc), encoding="utf-8")
            results.append({"dataset_id": dataset_id, "status": "failed", "message": str(exc)})
    _record_history(update_type="weekly", source="directory", dataset_id="multiple", update_mode="upsert", status="success" if all(r["status"] == "success" for r in results) else "warning", added_rows=sum(r.get("added_rows", 0) for r in results), message="directory sourceを処理しました")
    return {"status": "success" if results else "warning", "results": results, "message": "処理対象CSVがありません" if not results else "directory sourceを処理しました"}
