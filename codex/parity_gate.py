from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable, List, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUICK_SCENARIOS = ("entry2_short",)
TRUTH_GATE_SCRIPT = ROOT / "backtest" / "truth_gate.py"


def _run_command(cmd: Sequence[str]) -> int:
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False)
    return proc.returncode


def _scenario_args(scenarios: Iterable[str]) -> List[str]:
    result: List[str] = []
    for scenario_id in scenarios:
        result.extend(["--scenario-id", scenario_id])
    return result


def run_parity_gate(full: bool, tol: float, scenarios: Sequence[str]) -> int:
    if not TRUTH_GATE_SCRIPT.exists():
        print(f"PARITY_GATE: FAIL missing script {TRUTH_GATE_SCRIPT}")
        return 1

    selected_scenarios = list(scenarios)
    if not full and not selected_scenarios:
        selected_scenarios = list(DEFAULT_QUICK_SCENARIOS)

    scenario_flags = _scenario_args(selected_scenarios)
    failed = False

    for mode in ("incremental", "precomputed"):
        cmd = [
            sys.executable,
            str(TRUTH_GATE_SCRIPT),
            "--indicator-mode",
            mode,
            "--tol",
            str(tol),
            *scenario_flags,
        ]
        print(f"PARITY_GATE: running {mode} ...")
        start = time.perf_counter()
        exit_code = _run_command(cmd)
        elapsed = time.perf_counter() - start
        print(f"PARITY_GATE: {mode} exit={exit_code} elapsed={elapsed:.1f}s")
        if exit_code != 0:
            failed = True

    if failed:
        print("PARITY_GATE: FAIL")
        return 1

    print("PARITY_GATE: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run indicator-mode parity regression gate.")
    parser.add_argument("--full", action="store_true", help="Run full baseline scenarios.")
    parser.add_argument("--tol", type=float, default=1e-9)
    parser.add_argument("--scenario-id", action="append", default=[], help="Optional scenario filter. Repeatable.")
    args = parser.parse_args()
    return run_parity_gate(full=args.full, tol=args.tol, scenarios=args.scenario_id)


if __name__ == "__main__":
    raise SystemExit(main())
