from dataclasses import dataclass
from typing import Any

from kuegi_bot.bots.strategies.trend_enums import MarketDynamic, MarketRegime


@dataclass(frozen=True)
class StrategyOneEntryContext:
    std: Any
    std_vec: Any
    atr: Any
    atr_trail_mix: Any
    natr_4h: Any
    atr_min: Any
    middleband: Any
    middleband_vec: Any
    market_bullish: bool
    market_bearish: bool
    market_ranging: bool
    market_trending: bool
    range_limit: int
    talibbars: Any


def build_entry_context(strategy) -> StrategyOneEntryContext:
    ta_data = strategy.ta_data_trend_strat
    atr = ta_data.atr_4h
    natr_4h = ta_data.natr_4h
    atr_min = atr
    if natr_4h < 1:
        atr_min = atr + atr * (1 - natr_4h)

    middleband_vec = ta_data.bbands_4h.middleband_vec
    return StrategyOneEntryContext(
        std=ta_data.bbands_4h.std,
        std_vec=ta_data.bbands_4h.std_vec,
        atr=atr,
        atr_trail_mix=ta_data.atr_trail_mix,
        natr_4h=natr_4h,
        atr_min=atr_min,
        middleband=ta_data.bbands_4h.middleband,
        middleband_vec=middleband_vec,
        market_bullish=ta_data.marketRegime == MarketRegime.BULL,
        market_bearish=ta_data.marketRegime == MarketRegime.BEAR,
        market_ranging=ta_data.marketRegime == MarketRegime.RANGING,
        market_trending=ta_data.marketDynamic == MarketDynamic.TRENDING,
        range_limit=len(middleband_vec),
        talibbars=strategy.ta_trend_strat.taData_trend_strat.talibbars,
    )

