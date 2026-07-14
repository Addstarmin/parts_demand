from __future__ import annotations

import pandas as pd

from services.data_utils import normalize_id, read_csv


def get_factories_list() -> list[dict]:
    return read_csv("factory_master.csv").fillna("").to_dict(orient="records")


def get_parts_list() -> list[dict]:
    parts = read_csv("parts_master.csv").fillna("")
    current = read_csv("safety_stock_master.csv")
    if not current.empty:
        latest = current.sort_values("updated_at").drop_duplicates(["factory_id", "parts_id"], keep="last")
        latest = latest.groupby("parts_id", as_index=False)["safety_stock_quantity"].max()
        parts = parts.merge(latest, on="parts_id", how="left")
    return parts.fillna("").to_dict(orient="records")


def get_manufacturers() -> list[dict]:
    return read_csv("manufacturer_master.csv").fillna("").to_dict(orient="records")


def get_products(factory_id: str | None = None) -> list[dict]:
    products = read_csv("product_master.csv")
    manufacturers = read_csv("manufacturer_master.csv")
    if products.empty:
        return []
    if factory_id:
        products = products[products["factory_id"] == normalize_id(factory_id)]
    if not manufacturers.empty and "manufacturer_id" in products.columns:
        products = products.merge(manufacturers, on="manufacturer_id", how="left")
    return products.fillna("").to_dict(orient="records")


def get_product(product_id: str) -> dict | None:
    products = get_products()
    pid = normalize_id(product_id)
    for product in products:
        if product["product_id"] == pid:
            product["bom"] = get_product_bom(pid)
            return product
    return None


def get_product_bom(product_id: str) -> list[dict]:
    pid = normalize_id(product_id)
    bom = read_csv("bom_master.csv")
    parts = read_csv("parts_master.csv")
    if bom.empty:
        return []
    target = bom[bom["product_id"] == pid].copy()
    if parts.empty:
        return target.fillna("").to_dict(orient="records")
    target = target.merge(parts, on="parts_id", how="left")
    return target.fillna("").to_dict(orient="records")


def require_factory(factory_id: str) -> dict | None:
    fid = normalize_id(factory_id)
    for item in get_factories_list():
        if item["factory_id"] == fid:
            return item
    return None


def require_part(parts_id: str) -> dict | None:
    pid = normalize_id(parts_id)
    for item in get_parts_list():
        if item["parts_id"] == pid:
            return item
    return None


def product_manufacturer_mapping() -> pd.DataFrame:
    return read_csv("manufacturer_product_mapping.csv")
