from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.safety_stock_service import build_safety_stock_preview, update_dynamic_safety_stock


def main() -> None:
    parser = argparse.ArgumentParser(description="CMD-X dynamic safety stock batch")
    parser.add_argument("--preview", action="store_true", help="Preview only; do not update master")
    args = parser.parse_args()
    result = build_safety_stock_preview("cli_preview") if args.preview else update_dynamic_safety_stock()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
