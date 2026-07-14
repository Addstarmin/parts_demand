from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path
from typing import Iterable

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "cmdx.sqlite3"
TZ_NAME = "Asia/Tokyo"


def data_path(filename: str) -> Path:
    return DATA_DIR / filename


def read_csv(filename: str) -> pd.DataFrame:
    path = data_path(filename)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def atomic_write_csv(df: pd.DataFrame, filename: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    target = data_path(filename)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.stem}.", suffix=".tmp", dir=DATA_DIR)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        df.to_csv(tmp_path, index=False)
        tmp_path.replace(target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def now_jst_iso() -> str:
    return pd.Timestamp.now(tz=TZ_NAME).isoformat()


def normalize_id(id_str: str | None) -> str | None:
    if not id_str:
        return id_str
    raw = str(id_str).strip()
    clean = raw.replace("-", "").upper()
    if clean.startswith("F"):
        try:
            return f"F-{int(clean[1:]):02d}"
        except ValueError:
            return raw
    if clean.startswith("PT"):
        try:
            return f"PT-{int(clean[2:])}"
        except ValueError:
            return raw
    return raw.upper()


def safe_int(value: float | int | str | None, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def rmse(errors: Iterable[float]) -> float:
    vals = [float(v) for v in errors if v is not None and not pd.isna(v)]
    if not vals:
        return 0.0
    return math.sqrt(sum(v * v for v in vals) / len(vals))


def mae(errors: Iterable[float]) -> float:
    vals = [abs(float(v)) for v in errors if v is not None and not pd.isna(v)]
    if not vals:
        return 0.0
    return sum(vals) / len(vals)
