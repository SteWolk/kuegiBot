# Backtest Folder Index

This folder stays flat for now, but files are grouped by role.

## Official entry points

- Private baseline runner: `py -3 settings/private/backtest_v2.py` (local-only)
- Entry staged optimizer (multi-entry): `py -3 backtest/optimizer.py --entry-id entry_23`
- Entry optimizer web GUI (local): `py -3 backtest/optimizer_gui_server.py`
- Truth regression gate: `py -3 backtest/truth_gate.py`

## Runners

- `backtest_v3.py`
- `v2_modules.py`
- `backtest_docker.py`

## Optimizers / search

- `optimizer.py` (staged optimizer for StrategyOne entry modules)
- `optimizer_gui_server.py` (local GUI launcher for staged optimizer)

## Gates / parity / compatibility

- `truth_gate.py`
- `truth_freeze.py`
- `truth_scenarios.py`
- `mode_parity.py`
- `module_parity.py`
- `registry_check.py`
- `schema_equiv.py`

## Benchmarks

- `mode_bench.py`

## Utilities / shared helpers

- `result_tools.py`
- `mode_common.py`
- `param_catalog.py`

## Notes / experiments

- `intrabar_track.md`

## Backup staging

- `_backup_candidates_20260401/` contains decoupled legacy optimizer scripts/results prepared for external backup/removal.

## Naming guidance for new files

Keep file names to max two words, with short role-oriented names:

- `run_*` for runners (example: `run_scan.py`)
- `opt_*` for optimizers (example: `opt_grid.py`)
- `*_gate.py` / `*_parity.py` for safety checks
- `*_bench.py` for benchmarks
- `*_tools.py` / `*_common.py` for shared helpers
