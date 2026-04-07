# Experimental Track: Event-Driven Intrabar Backtest

Status: scaffold only, not active in default backtester.

## Guardrails
- Must remain opt-in and isolated from truth engine.
- Must not replace `BackTest.run()` default path.
- Any candidate implementation must pass `truth_gate.py` on SL-heavy scenarios before usage.

## Planned milestones
1. Add experimental engine class in a separate script/module.
2. Implement event-queue intrabar execution for orders.
3. Add side-by-side parity harness against truth mode.
4. Only after strict parity, evaluate speed and decide whether to keep as screening-only mode.
