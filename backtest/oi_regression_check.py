from __future__ import annotations

from dataclasses import dataclass
import os
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKTEST_ROOT = PROJECT_ROOT / "backtest"
if str(BACKTEST_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKTEST_ROOT))
os.chdir(PROJECT_ROOT)

from optimizer import EntryStagedOptimizer
from kuegi_bot.bots.strategies.strategy_one_entry_modules import (
    CommonRuleOptions,
    Entry23Module,
    EntryExecutionContext,
    StrategyOneEntryContext,
    module_passes_common_rules,
)
from kuegi_bot.bots.strategies.strategy_one_entry_schema import get_entry_parameter_catalog


class _Logger:
    def info(self, *_args, **_kwargs):
        return None


@dataclass
class _Bar:
    open: float
    high: float
    low: float
    close: float


class _Strategy:
    def __init__(
        self,
        *,
        oi_ratio_4h: float,
        oi_4h: float,
        close_series: list[float] | None = None,
        oi_series: list[float] | None = None,
        funding_series: list[float] | None = None,
    ):
        if close_series is None:
            close_series = [100.0, 101.0, 102.0, 103.0]
        if oi_series is None:
            oi_series = [1000.0, 1010.0, 1020.0, 1030.0]
        if funding_series is None:
            funding_series = [0.0001, 0.0001, 0.0001, 0.0001]
        self.logger = _Logger()
        self.telegram = None
        self.longsAllowed = True
        self.open_calls = []
        self.ta_data_trend_strat = SimpleNamespace(
            highs_trail_4h_vec=[105.0, 95.0],
            rsi_4h_vec=[50.0],
            volume_sma_4h_vec=[100.0],
            atr_4h_vec=[10.0],
            rsi_d=50.0,
            natr_4h=1.0,
            atr_4h=10.0,
            volume_4h=100.0,
            oi_ratio_4h=oi_ratio_4h,
            oi_4h=oi_4h,
            oi_4h_vec=list(oi_series),
            funding_4h_vec=list(funding_series),
            talibbars=SimpleNamespace(close=list(close_series)),
        )

    def open_new_position(self, **kwargs):
        self.open_calls.append(dict(kwargs))


def _build_ctx(
    *,
    oi_ratio_4h: float,
    oi_4h: float,
    close_series: list[float] | None = None,
    oi_series: list[float] | None = None,
    funding_series: list[float] | None = None,
) -> EntryExecutionContext:
    strategy = _Strategy(
        oi_ratio_4h=oi_ratio_4h,
        oi_4h=oi_4h,
        close_series=close_series,
        oi_series=oi_series,
        funding_series=funding_series,
    )
    bars = [
        _Bar(open=111.0, high=114.0, low=108.0, close=112.0),  # bar[0]
        _Bar(open=103.0, high=112.0, low=100.0, close=110.0),  # bar[1]
        _Bar(open=102.0, high=106.0, low=99.0, close=104.0),
        _Bar(open=100.0, high=103.0, low=98.0, close=101.0),
        _Bar(open=98.0, high=101.0, low=96.0, close=99.0),
        _Bar(open=97.0, high=100.0, low=95.0, close=98.0),
    ]
    entry_context = StrategyOneEntryContext(
        std=5.0,
        std_vec=[5.0],
        atr=10.0,
        atr_trail_mix=10.0,
        natr_4h=1.0,
        atr_min=10.0,
        middleband=100.0,
        middleband_vec=[100.0],
        market_bullish=True,
        market_bearish=False,
        market_ranging=False,
        market_trending=False,
        range_limit=1,
        talibbars=None,
    )
    return EntryExecutionContext(
        strategy=strategy,
        bars=bars,
        account=None,
        open_positions={},
        direction_filter=0,
        entry_context=entry_context,
        longed=False,
        shorted=False,
    )


def _assert_schema_has_oi_filters():
    catalog = get_entry_parameter_catalog()
    entry23 = catalog["entry_23"]
    names = {spec["name"] for class_specs in entry23.values() for spec in class_specs}
    required = {
        "entry_23_filter_oi_ratio_4h_min_enabled",
        "entry_23_oi_ratio_4h_min",
        "entry_23_filter_oi_ratio_4h_max_enabled",
        "entry_23_oi_ratio_4h_max",
        "entry_23_filter_oi_4h_min_enabled",
        "entry_23_oi_4h_min",
        "entry_23_filter_oi_above_sma_enabled",
        "entry_23_oi_flow_state",
        "entry_23_oi_flow_lookback",
        "entry_23_oi_flow_price_min_pct",
        "entry_23_oi_flow_oi_min_pct",
        "entry_23_oi_funding_state",
        "entry_23_oi_funding_lookback",
        "entry_23_oi_funding_oi_up_min_pct",
        "entry_23_oi_funding_oi_down_min_pct",
        "entry_23_oi_funding_pos_min",
        "entry_23_oi_funding_neg_min",
    }
    missing = sorted(required - names)
    assert len(missing) == 0, "Missing entry_23 OI params: %s" % ",".join(missing)


def _assert_optimizer_has_oi_prep_mapping():
    optimizer = EntryStagedOptimizer.__new__(EntryStagedOptimizer)
    empty = EntryStagedOptimizer._build_preparation_series_from_trend(optimizer, chrono=[])
    assert "oi_4h" in empty, "preparation series missing oi_4h"
    assert "oi_ratio_4h" in empty, "preparation series missing oi_ratio_4h"
    assert "oi_ret_pct" in empty, "preparation series missing oi_ret_pct"
    assert "oi_ret_signed_pct" in empty, "preparation series missing oi_ret_signed_pct"
    assert "ret_signed_pct" in empty, "preparation series missing ret_signed_pct"
    assert "funding_4h" in empty, "preparation series missing funding_4h"
    assert "funding_abs_4h" in empty, "preparation series missing funding_abs_4h"
    assert (
        EntryStagedOptimizer._preparation_series_key_for_dimension(
            optimizer, "entry_23.filter.oi_ratio_4h_min"
        )
        == "oi_ratio_4h"
    )
    assert (
        EntryStagedOptimizer._preparation_series_key_for_dimension(
            optimizer, "entry_23.filter.oi_4h_min"
        )
        == "oi_4h"
    )
    assert (
        EntryStagedOptimizer._preparation_series_key_for_dimension(
            optimizer, "entry_23.filter.oi_flow_oi_min_pct"
        )
        == "oi_ret_pct"
    )
    assert (
        EntryStagedOptimizer._preparation_series_key_for_dimension(
            optimizer, "entry_23.filter.oi_flow_price_min_pct"
        )
        == "ret_pct"
    )
    assert (
        EntryStagedOptimizer._preparation_series_key_for_dimension(
            optimizer, "entry_23.filter.oi_funding_oi_up_min_pct"
        )
        == "oi_ret_pct"
    )
    assert (
        EntryStagedOptimizer._preparation_series_key_for_dimension(
            optimizer, "entry_23.filter.oi_funding_pos_min"
        )
        == "funding_abs_4h"
    )


def _assert_entry23_oi_filter_runtime():
    mod_ratio_min = Entry23Module(
        active=True,
        entry_23_filter_oi_ratio_4h_min_enabled=True,
        entry_23_oi_ratio_4h_min=1.05,
    )
    ctx_ratio_fail = _build_ctx(oi_ratio_4h=1.00, oi_4h=100.0)
    assert mod_ratio_min.is_ready(ctx_ratio_fail)
    mod_ratio_min.run(ctx_ratio_fail)
    assert len(ctx_ratio_fail.strategy.open_calls) == 0

    ctx_ratio_pass = _build_ctx(oi_ratio_4h=1.10, oi_4h=100.0)
    assert mod_ratio_min.is_ready(ctx_ratio_pass)
    mod_ratio_min.run(ctx_ratio_pass)
    assert len(ctx_ratio_pass.strategy.open_calls) == 1

    mod_oi_min = Entry23Module(
        active=True,
        entry_23_filter_oi_4h_min_enabled=True,
        entry_23_oi_4h_min=150.0,
    )
    ctx_oi_fail = _build_ctx(oi_ratio_4h=1.10, oi_4h=100.0)
    assert mod_oi_min.is_ready(ctx_oi_fail)
    mod_oi_min.run(ctx_oi_fail)
    assert len(ctx_oi_fail.strategy.open_calls) == 0

    ctx_oi_pass = _build_ctx(oi_ratio_4h=1.10, oi_4h=200.0)
    assert mod_oi_min.is_ready(ctx_oi_pass)
    mod_oi_min.run(ctx_oi_pass)
    assert len(ctx_oi_pass.strategy.open_calls) == 1

    mod_above_sma = Entry23Module(
        active=True,
        entry_23_filter_oi_above_sma_enabled=True,
    )
    ctx_above_fail = _build_ctx(oi_ratio_4h=0.95, oi_4h=100.0)
    assert mod_above_sma.is_ready(ctx_above_fail)
    mod_above_sma.run(ctx_above_fail)
    assert len(ctx_above_fail.strategy.open_calls) == 0

    ctx_above_pass = _build_ctx(oi_ratio_4h=1.00, oi_4h=100.0)
    assert mod_above_sma.is_ready(ctx_above_pass)
    mod_above_sma.run(ctx_above_pass)
    assert len(ctx_above_pass.strategy.open_calls) == 1


def _assert_common_oi_flow_filter_runtime():
    module = SimpleNamespace(
        common_rules=CommonRuleOptions(
            filter_oi_flow_state="trend_continuation",
            filter_oi_flow_lookback=2,
            filter_oi_flow_price_min_pct=0.5,
            filter_oi_flow_oi_min_pct=0.5,
        )
    )
    ctx_pass = _build_ctx(
        oi_ratio_4h=1.05,
        oi_4h=1000.0,
        close_series=[100.0, 101.0, 102.0, 103.0],
        oi_series=[1000.0, 1010.0, 1025.0, 1040.0],
    )
    assert module_passes_common_rules(module, ctx_pass), "trend_continuation should pass for price_up+oi_up"

    ctx_fail = _build_ctx(
        oi_ratio_4h=0.95,
        oi_4h=980.0,
        close_series=[100.0, 101.0, 102.0, 103.0],
        oi_series=[1000.0, 995.0, 990.0, 980.0],
    )
    assert not module_passes_common_rules(module, ctx_fail), "trend_continuation should fail for price_up+oi_down"


def _assert_common_oi_funding_filter_runtime():
    module = SimpleNamespace(
        common_rules=CommonRuleOptions(
            filter_oi_funding_state="long_crowded",
            filter_oi_funding_lookback=2,
            filter_oi_funding_oi_up_min_pct=0.5,
            filter_oi_funding_oi_down_min_pct=0.5,
            filter_oi_funding_pos_min=0.0001,
            filter_oi_funding_neg_min=0.0001,
        )
    )
    ctx_pass = _build_ctx(
        oi_ratio_4h=1.05,
        oi_4h=1040.0,
        oi_series=[1000.0, 1010.0, 1025.0, 1040.0],
        funding_series=[0.0001, 0.0002, 0.0003, 0.0005],
    )
    assert module_passes_common_rules(module, ctx_pass), "long_crowded should pass for oi_up + positive funding"

    ctx_fail = _build_ctx(
        oi_ratio_4h=1.05,
        oi_4h=1040.0,
        oi_series=[1000.0, 1010.0, 1025.0, 1040.0],
        funding_series=[-0.0003, -0.0004, -0.0005, -0.0006],
    )
    assert not module_passes_common_rules(module, ctx_fail), "long_crowded should fail for negative funding"


def main():
    _assert_schema_has_oi_filters()
    _assert_optimizer_has_oi_prep_mapping()
    _assert_entry23_oi_filter_runtime()
    _assert_common_oi_flow_filter_runtime()
    _assert_common_oi_funding_filter_runtime()
    print("oi_regression_check: PASS")


if __name__ == "__main__":
    main()
