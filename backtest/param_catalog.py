import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from kuegi_bot.bots.strategies.strategy_one_entry_schema import (
    ENTRY_IDS,
    PARAM_CLASSES,
    get_entry_parameter_catalog,
    iter_catalog_specs,
)


def main():
    parser = argparse.ArgumentParser(description="Export StrategyOne entry parameter catalog (schema-v1).")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent / "results" / "entry_parameter_catalog.json"))
    parser.add_argument("--entry-id", choices=ENTRY_IDS, default=None, help="Optional module filter.")
    parser.add_argument("--param-class", choices=PARAM_CLASSES, default=None, help="Optional class filter.")
    args = parser.parse_args()

    if args.entry_id is None and args.param_class is None:
        payload = {
            "schema_version": 1,
            "entry_catalog": get_entry_parameter_catalog(),
        }
    else:
        payload = {
            "schema_version": 1,
            "entry_id": args.entry_id,
            "param_class": args.param_class,
            "params": list(iter_catalog_specs(entry_id=args.entry_id, param_class=args.param_class)),
        }

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"ENTRY_CATALOG_WRITTEN={out_path}")


if __name__ == "__main__":
    main()
