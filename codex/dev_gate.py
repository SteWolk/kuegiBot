from __future__ import annotations

import argparse
from typing import Sequence

from parity_gate import run_parity_gate
from quality_gate import run_quality_gate


def run_dev_gate(
    *,
    scope: str,
    include: Sequence[str],
    max_line_length: int,
    max_complexity: int,
    check_semicolons: bool,
    full_parity: bool,
    parity_tol: float,
    parity_scenarios: Sequence[str],
) -> int:
    quality_code = run_quality_gate(
        scope=scope,
        include=include,
        max_line_length=max_line_length,
        max_complexity=max_complexity,
        check_semicolons=check_semicolons,
    )
    if quality_code != 0:
        print("DEV_GATE: FAIL (quality)")
        return quality_code

    parity_code = run_parity_gate(full=full_parity, tol=parity_tol, scenarios=parity_scenarios)
    if parity_code != 0:
        print("DEV_GATE: FAIL (parity)")
        return parity_code

    print("DEV_GATE: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run quality + parity gates.")
    parser.add_argument("--scope", choices=("changed", "all"), default="changed")
    parser.add_argument("--include", action="append", default=[], help="Optional path(s) relative to repository root.")
    parser.add_argument("--max-line-length", type=int, default=0)
    parser.add_argument("--max-complexity", type=int, default=80)
    parser.add_argument("--check-semicolons", action="store_true")
    parser.add_argument("--full-parity", action="store_true", help="Run full baseline parity suite.")
    parser.add_argument("--parity-tol", type=float, default=1e-9)
    parser.add_argument("--parity-scenario-id", action="append", default=[], help="Optional parity scenario filter.")
    args = parser.parse_args()

    return run_dev_gate(
        scope=args.scope,
        include=args.include,
        max_line_length=args.max_line_length,
        max_complexity=args.max_complexity,
        check_semicolons=args.check_semicolons,
        full_parity=args.full_parity,
        parity_tol=args.parity_tol,
        parity_scenarios=args.parity_scenario_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
