import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.data_management_service import (
    DATASET_REGISTRY,
    commit_demo_next_week,
    commit_import,
    create_backup,
    dataset_csv_bytes,
    export_all_zip,
    get_summary,
    list_backups,
    list_datasets,
    preview_demo_next_week,
    restore_backup,
    run_weekly_update_now,
    save_weekly_settings,
    validate_import,
)
from services.data_utils import read_csv


def test_data_management_lists_13_datasets_and_summary():
    datasets = list_datasets()
    assert len(datasets) == 13
    assert {item["dataset_id"] for item in datasets} == set(DATASET_REGISTRY)
    summary = get_summary()
    assert summary["dataset_count"] == 13
    assert summary["last_actual_week"]


def test_dataset_csv_download_and_zip_export():
    content = dataset_csv_bytes("factory_master")
    assert content.startswith(b"\xef\xbb\xbf")
    assert "factory_id" in content.decode("utf-8-sig")
    zip_bytes, filename = export_all_zip()
    assert filename.startswith("cmdx_data_export_")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert {definition.filename for definition in DATASET_REGISTRY.values()}.issubset(names)


def test_invalid_dataset_id_is_rejected():
    with pytest.raises(ValueError):
        dataset_csv_bytes("../secret")


def test_validate_import_detects_missing_columns_negative_ids_and_duplicates():
    missing = "factory_id,parts_id,order_volume\nF-02,PT-1002,10\n"
    result = validate_import("internal_performance_history", "append", missing, "bad.csv")
    assert not result["valid"]
    assert any("必須カラム" in err["message"] for err in result["errors"])

    bad = (
        "week_start_date,factory_id,parts_id,order_volume,production_volume,shipment_volume,ending_stock\n"
        "2026-07-13,F-02,PT-9999,-1,10,10,10\n"
        "2026-07-13,F-02,PT-9999,-1,10,10,10\n"
    )
    result = validate_import("internal_performance_history", "append", bad, "bad.csv")
    assert not result["valid"]
    messages = " ".join(err["message"] for err in result["errors"])
    assert "負の値" in messages
    assert "マスタに存在しません" in messages
    assert "主キーが重複" in messages


def test_append_upsert_replace_and_backup_restore_work():
    backup_id = create_backup("pytest_before_import", "factory_master", None, None, 0, "pytest")
    original = read_csv("factory_master.csv")
    try:
        append_csv = "factory_id,factory_name,location\nF-99,テスト工場,愛知県\n"
        validated = validate_import("factory_master", "upsert", append_csv, "factory.csv")
        assert validated["valid"]
        committed = commit_import(validated["session_id"])
        assert committed["added_rows"] == 1
        assert "F-99" in set(read_csv("factory_master.csv")["factory_id"])

        upsert_csv = "factory_id,factory_name,location\nF-99,更新工場,岐阜県\n"
        validated = validate_import("factory_master", "upsert", upsert_csv, "factory.csv")
        committed = commit_import(validated["session_id"])
        assert committed["updated_rows"] == 1
        assert read_csv("factory_master.csv").query("factory_id == 'F-99'")["factory_name"].iloc[0] == "更新工場"

        replace_csv = original.to_csv(index=False)
        validated = validate_import("factory_master", "replace", replace_csv, "factory.csv")
        with pytest.raises(ValueError):
            commit_import(validated["session_id"])
        committed = commit_import(validated["session_id"], confirm_replace=True)
        assert committed["new_row_count"] == len(original)
        assert list_backups()
    finally:
        restore_backup(backup_id)


def test_commit_requires_validation_session():
    with pytest.raises(ValueError):
        commit_import("IMP-NOTFOUND")


def test_backup_restore_creates_pre_restore_backup():
    backup_id = create_backup("pytest_restore", "parts_master", None, None, 0, "pytest")
    result = restore_backup(backup_id)
    assert result["restored_backup_id"] == backup_id
    assert result["pre_restore_backup_id"]


def test_weekly_demo_preview_and_commit_prevents_duplicate():
    preview = preview_demo_next_week()
    assert preview["next_week"]
    result = commit_demo_next_week(False, False)
    assert result["status"] in {"success", "warning"}
    after = preview_demo_next_week()
    assert after["next_week"] > preview["next_week"]


def test_weekly_settings_and_run_now():
    settings = save_weekly_settings({"enabled": False, "source": "demo", "day": "mon", "hour": 6, "minute": 0})
    assert settings["source"] == "demo"
    result = run_weekly_update_now()
    assert result["status"] in {"success", "warning"}
