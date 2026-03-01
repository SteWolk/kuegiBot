# StrategyTwo Mean-Reversion Spec (v1)

## Goal
Design a standalone **StrategyTwo** mean-reversion module that can run together with `StrategyOne` without changing `StrategyOne` behavior.

## Design principles
1. Keep `StrategyOne` untouched.
2. Use indicator families already present in current codebase (ATR/NATR, BBands, RSI, EMA, volume SMA, funding signal).
3. Focus on high-quality **fast-spike reversal** opportunities with explicit entry/exit rules.
4. Enforce evaluation criteria for **each individual StrategyTwo entry**:
   - profit `% >= 400`
   - max drawdown `% > -20`

---

## Proposed StrategyTwo architecture

### Shared regime filter (applies to all StrategyTwo entries)
- Prefer ranging/choppy conditions over strong staircase trends.
- Reject trades when trend strength is too high (NATR / MA-cross density / slope proxy).
- Directional bias can be asymmetric using market regime:
  - bullish bias: prioritize long reversals
  - bearish bias: prioritize short reversals
  - neutral/ranging: allow both

### Entry S2E1 — Fast Spike Reversal (primary)
**Intent**: Fade an outlier spike back to its origin when move is likely exhausted.

**Long setup**
1. Spike-down bar magnitude exceeds threshold (`abs(return_1bar) >= spike_atr_k * ATR`).
2. Volume impulse confirmed (`volume >= spike_vol_k * volume_sma`).
3. Price tags key support zone (swing low or lower BB zone).
4. Confirmation close back above micro-structure trigger (break-of-structure reclaim).
5. Optional RSI filter (`RSI_4h <= rsi_long_max`).

**Short setup** (symmetric)
1. Spike-up bar magnitude exceeds threshold.
2. Volume impulse confirmed.
3. Price tags key resistance zone (swing high or upper BB zone).
4. Confirmation close back below micro-structure trigger.
5. Optional RSI filter (`RSI_4h >= rsi_short_min`).

**Risk / exits**
- Stop-loss: spike extreme +/- ATR buffer.
- TP1: spike origin.
- TP2 (optional runner): middle band / opposite BB / trail module.
- Time stop: close if no mean-reversion progress after `N` bars.

### Entry S2E2 — Failed Breakout Reversal
**Intent**: Re-enter range after false break.

**Long setup**
1. Candle closes below support (breakout attempt).
2. Next candle closes back above support (failure).
3. Range width filter determines market vs limit entry style.

**Short setup**
1. Candle closes above resistance.
2. Next candle closes back below resistance.
3. Same width filter for execution style.

**Risk / exits**
- Stop near failed-break extreme.
- TP at opposite side of range or range midpoint depending volatility.

### Entry S2E3 — BBand/RSI Exhaustion Reclaim
**Intent**: Capture reversion when price overextends and reclaims fair zone.

**Long setup**
- Close below lower BB followed by reclaim close above lower BB,
- RSI in oversold regime,
- low trend-strength condition.

**Short setup**
- Close above upper BB followed by reclaim below upper BB,
- RSI in overbought regime,
- low trend-strength condition.

**Risk / exits**
- Stop beyond BB excursion extreme.
- TP at BB midline then optional opposite band partial.

---

## Parameter set (initial defaults)

### Regime and filters
- `s2_enable_longs=true`
- `s2_enable_shorts=true`
- `s2_max_trend_natr=1.4`
- `s2_min_ma_cross_density=0.15` (range proxy)
- `s2_funding_block_minutes=90`
- `s2_funding_max_r_fraction=0.10`

### S2E1 Fast Spike Reversal
- `s2e1_spike_atr_k=1.8`
- `s2e1_spike_vol_k=2.2`
- `s2e1_support_resistance_lookback=55`
- `s2e1_reclaim_bars_max=2`
- `s2e1_rsi_long_max=40`
- `s2e1_rsi_short_min=60`
- `s2e1_sl_atr_buffer=0.2`
- `s2e1_time_stop_bars=8`

### S2E2 Failed Breakout
- `s2e2_range_lookback=40`
- `s2e2_min_range_pct=1.5`
- `s2e2_market_entry_range_pct=3.0`
- `s2e2_sl_atr_buffer=0.15`
- `s2e2_tp_mode=opposite_range`

### S2E3 BBand/RSI Reclaim
- `s2e3_bb_period=200`
- `s2e3_bb_std=2.0`
- `s2e3_rsi_period=6`
- `s2e3_rsi_oversold=30`
- `s2e3_rsi_overbought=70`
- `s2e3_sl_atr_buffer=0.2`

---

## Independence requirements (StrategyOne + StrategyTwo)
To run both strategies simultaneously without cross-contamination:

1. Unique strategy ID/prefix for StrategyTwo order IDs and position IDs.
2. Unique indicator IDs/namespaces for any StrategyTwo-specific indicator writes.
3. No mutation of shared state owned by StrategyOne.
4. No reuse of StrategyOne flags/entry toggles; StrategyTwo has dedicated config keys.

---

## Backtest protocol (required)

### A) Baseline control
- Run StrategyOne exactly as-is (all current active entries) and snapshot metrics.

### B) StrategyTwo isolated entry tests
- Enable only one StrategyTwo entry at a time (`S2E1`, then `S2E2`, then `S2E3`).
- Keep all non-entry settings fixed.
- Pass criteria per entry:
  - `profit_pct >= 400`
  - `max_drawdown_pct > -20`

### C) Combined portfolio test
- Run StrategyOne + best StrategyTwo entries together.
- Verify combined DD remains controlled and does not degrade StrategyOne robustness profile.

### D) Stability checks
- Repeat B/C on short, medium, full windows.
- Apply bar-offset sensitivity checks to avoid overfitting.

---

## Deliverables checklist
- [ ] StrategyTwo class scaffold with independent IDs
- [ ] Three toggleable entries (`s2_entry_1..3`)
- [ ] Metrics export for per-entry evaluation
- [ ] Comparison table: StrategyOne baseline vs S2E1/S2E2/S2E3 vs combined
- [ ] Keep StrategyOne source and params unchanged


## Synthetic-data validation harness
To enable repeatable testing when exchange history is unavailable:

- `kuegi_bot/utils/synthetic_data.py` generates OHLCV bars with alternating trend/range regimes and injected spikes.
- `synthetic_backtest_strategy_two.py` runs `StrategyTwo` on synthetic bars through the existing `BackTest` engine.

Usage:

```bash
python synthetic_backtest_strategy_two.py
```

This is intended as a deterministic smoke/regression harness (via seed), not as a replacement for historical-market validation.
