import math
from typing import List

import plotly.graph_objects as go
import numpy as np
import talib

from kuegi_bot.bots.strategies.trend_strategy import TrendStrategy
from kuegi_bot.bots.strategies.trend_indicator_engine import TAdataTrendStrategy
from kuegi_bot.bots.strategies.strategy_one_entry_gate import entry_gate_passes
from kuegi_bot.bots.strategies.strategy_one_entry_context import build_entry_context
from kuegi_bot.bots.strategies.strategy_one_entry_modules import (
    EntryExecutionContext,
    as_entry_module,
    default_entry_modules,
    module_name,
)
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Position
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position


class DataStrategyOne:
    def __init__(self):
        self.longEntry = None
        self.stopLong = None
        self.shortEntry = None
        self.stopShort = None


class StrategyOne(TrendStrategy):
    # Strategy description:
    def __init__(self,
                 # StrategyOne
                 var_1: float = 0, var_2: float = 0, risk_ref: float = 1, reduceRisk: bool = False, max_r: float = 20,
                 entry_module_config: dict = None,
                 h_highs_trail_period: int = 1, h_lows_trail_period: int = 1,
                 shortsAllowed: bool = False, longsAllowed: bool = False,
                 tp_fac_strat_one: float = 0,
                 plotStrategyOneData: bool = False, plotTrailsStatOne: bool = False,
                 # TrendStrategy
                 timeframe: int = 240, ema_w_period: int = 2, highs_trail_4h_period: int = 1, lows_trail_4h_period: int = 1,
                 days_buffer_bear: int = 2, days_buffer_bull: int = 0, atr_4h_period: int = 10, natr_4h_period_slow: int = 10,
                 bbands_4h_period: int = 10, rsi_4h_period: int = 10, volume_sma_4h_period: int = 100,
                 plotIndicators: bool = False, plot_RSI: bool = False, use_shapes: bool = False, plotBackgroundColor4Trend: bool = False,
                 plotTrailsAndEMAs: bool = False, plotBBands:bool=False, plotATR:bool=False, trend_atr_fac: float = 0.5,
                 trend_var_1: float = 0,
                 # Risk
                 risk_with_trend: float = 1, risk_counter_trend: float = 1, risk_ranging: float = 1, risk_fac_shorts = 1,
                 # SL
                 sl_atr_fac: float = 2, be_by_middleband: bool = True, be_by_opposite: bool = True, stop_at_middleband: bool = True,
                 tp_at_middleband: bool = True, atr_buffer_fac: float = 0, tp_on_opposite: bool = True, stop_at_new_entry: bool = False,
                 trail_sl_with_bband: bool = False, stop_short_at_middleband: bool = False, stop_at_trail: bool = False,
                 stop_at_lowerband: bool = False,
                 moving_sl_atr_fac: float = 5, sl_upper_bb_std_fac: float = 1, sl_lower_bb_std_fac: float = 1,
                 ema_multiple_4_tp: float = 10,
                 # StrategyWithTradeManagement
                 maxPositions: int = 100, consolidate: bool = False, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3,
                 limit_entry_offset_perc: float = -0.1, delayed_cancel: bool = False, cancel_on_filter: bool = True, tp_fac:float = 0
                 ):
        super().__init__(
            # TrendStrategy
            timeframe = timeframe, ema_w_period= ema_w_period, highs_trail_4h_period= highs_trail_4h_period,
            lows_trail_4h_period= lows_trail_4h_period, days_buffer_bear= days_buffer_bear, days_buffer_bull= days_buffer_bull,
            atr_4h_period= atr_4h_period, natr_4h_period_slow= natr_4h_period_slow, trend_atr_fac = trend_atr_fac,
            bbands_4h_period= bbands_4h_period, rsi_4h_period = rsi_4h_period,
            volume_sma_4h_period =volume_sma_4h_period,
            plotIndicators = plotIndicators, plot_RSI = plot_RSI,
            trend_var_1 = trend_var_1,
            # Risk
            risk_with_trend = risk_with_trend, risk_counter_trend = risk_counter_trend, risk_ranging = risk_ranging, risk_fac_shorts=risk_fac_shorts,
            # SL
            be_by_middleband = be_by_middleband, be_by_opposite = be_by_opposite,
            stop_at_middleband = stop_at_middleband, tp_at_middleband = tp_at_middleband,
            tp_on_opposite = tp_on_opposite, stop_at_new_entry = stop_at_new_entry, trail_sl_with_bband = trail_sl_with_bband,
            atr_buffer_fac = atr_buffer_fac, moving_sl_atr_fac = moving_sl_atr_fac,
            sl_upper_bb_std_fac = sl_upper_bb_std_fac, sl_lower_bb_std_fac = sl_lower_bb_std_fac,
            stop_short_at_middleband = stop_short_at_middleband, stop_at_trail = stop_at_trail, stop_at_lowerband = stop_at_lowerband,
            ema_multiple_4_tp = ema_multiple_4_tp,
            # Plots
            use_shapes = use_shapes, plotBackgroundColor4Trend = plotBackgroundColor4Trend, plotTrailsAndEMAs=plotTrailsAndEMAs,
            plotBBands = plotBBands, plotATR=plotATR,
            # StrategyWithTradeManagement
            maxPositions = maxPositions, consolidate = consolidate, close_on_opposite = close_on_opposite, bars_till_cancel_triggered = bars_till_cancel_triggered,
            limit_entry_offset_perc = limit_entry_offset_perc, delayed_cancel = delayed_cancel, cancel_on_filter = cancel_on_filter, tp_fac = tp_fac
            )
        self.ta_data_trend_strat = TAdataTrendStrategy()
        self.data_strat_one = DataStrategyOne()
        self.ta_strat_one = TAStrategyOne(timeframe = timeframe, h_highs_trail_period= h_highs_trail_period,
                                          h_lows_trail_period = h_lows_trail_period, ta_data_trend_strat = self.ta_data_trend_strat)
        # Backtest/risk variables
        self.var_1 = var_1
        self.var_2 = var_2
        self.max_r = max_r
        self.risk_ref = risk_ref
        self.reduceRisk = reduceRisk

        module_config = {} if entry_module_config is None else dict(entry_module_config)
        self.sl_atr_fac = sl_atr_fac
        self.shortsAllowed = shortsAllowed
        self.longsAllowed = longsAllowed
        self.tp_fac_strat_one = tp_fac_strat_one
        self.plotStrategyOneData = plotStrategyOneData
        self.plotTrailsStatOne = plotTrailsStatOne
        self.entryModules = default_entry_modules(module_config)

    def myId(self):
        return "strategyOne"

    def _find_entry_module_index(self, name: str):
        for idx, entry_module in enumerate(self.entryModules):
            if module_name(entry_module) == name:
                return idx
        return None

    def listEntryModules(self):
        return [module_name(entry_module) for entry_module in self.entryModules]

    def clearEntryModules(self):
        self.entryModules = []
        return self

    def withoutEntryModule(self, name: str):
        idx = self._find_entry_module_index(name)
        if idx is None:
            raise ValueError("Entry module not found: " + str(name))
        del self.entryModules[idx]
        return self

    def withEntryModule(self, module, before: str = None, after: str = None, replace: str = None):
        if before is not None and after is not None:
            raise ValueError("Use either 'before' or 'after', not both.")

        normalized = as_entry_module(module)
        normalized_name = module_name(normalized)

        if replace is not None:
            idx = self._find_entry_module_index(replace)
            if idx is None:
                raise ValueError("Entry module to replace not found: " + str(replace))
            self.entryModules[idx] = normalized
            return self

        if self._find_entry_module_index(normalized_name) is not None:
            raise ValueError("Entry module already registered: " + normalized_name)

        if before is not None:
            idx = self._find_entry_module_index(before)
            if idx is None:
                raise ValueError("Reference entry module not found: " + str(before))
            self.entryModules.insert(idx, normalized)
            return self

        if after is not None:
            idx = self._find_entry_module_index(after)
            if idx is None:
                raise ValueError("Reference entry module not found: " + str(after))
            self.entryModules.insert(idx + 1, normalized)
            return self

        self.entryModules.append(normalized)
        return self

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        self.logger.info(vars(self))
        super().init(bars, account, symbol)

    def min_bars_needed(self) -> int:
        min_bars = super().min_bars_needed()
        return min_bars

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            #print("processing new bar")
            super().prep_bars(is_new_bar, bars)
            self.ta_data_trend_strat = self.get_ta_data_trend_strategy()
            self.ta_strat_one.set_ta_data_trend_strat(self.ta_data_trend_strat)
            self.ta_strat_one.on_tick(bars)
            #self.logger.info('Current ta indicator values of strat one:')
            #self.logger.info(vars(self.ta_strat_one.taData_strat_one))

    def position_got_opened_or_changed(self, position: Position, bars: List[Bar], account: Account, open_positions):
        super().position_got_opened_or_changed(position, bars, account, open_positions)

        gotTp = False
        for order in account.open_orders:
            orderType = TradingBot.order_type_from_order_id(order.id)
            posId = TradingBot.position_id_from_order_id(order.id)
            if self.tp_fac_strat_one > 0 and orderType == OrderType.TP and posId == position.id:
                gotTp = True
                amount = self.symbol.normalizeSize(-position.current_open_amount + order.executed_amount)
                if abs(order.amount - amount) > self.symbol.lotSize / 2:
                    order.amount = amount
                    self.order_interface.update_order(order)

        if self.tp_fac_strat_one > 0 and not gotTp and self.ta_trend_strat.taData_trend_strat.talibbars.open is not None:
            condition_1 = position.amount < 0
            condition_2 = (self.ta_trend_strat.taData_trend_strat.talibbars.open[-1] <
                           self.ta_data_trend_strat.bbands_4h.middleband - self.ta_data_trend_strat.bbands_4h.std * 2)
            condition_3 = self.ta_data_trend_strat.rsi_d < 40
            if condition_1 and (condition_3 or condition_2):
                ref = position.filled_entry - position.initial_stop
                tp = max(0.0,position.filled_entry + ref * self.tp_fac_strat_one)
                order = Order(orderId=TradingBot.generate_order_id(positionId=position.id,type=OrderType.TP),
                              limit=tp,amount=-position.amount)
                self.order_interface.send_order(order)

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        result= super().got_data_for_position_sync(bars)
        return result

    def open_new_trades(self, is_new_bar, directionFilter, bars, account, open_positions, all_open_pos: dict):
        enter_position_NOW_1 = False
        if enter_position_NOW_1 and self.var_1 != 67 and self.symbol.symbol == 'BTCUSDT':
            entry = bars[0].close
            stop = entry + 2000
            self.open_new_position(entry=entry,
                                   stop=stop,
                                   open_positions=open_positions,
                                   bars=bars,
                                   direction=PositionDirection.SHORT,
                                   ExecutionType="Market")
            self.var_1 = 67

        enter_position_NOW_2 = False
        if enter_position_NOW_2 and self.var_2 != 89 and self.symbol.symbol == 'ETHUSDT':
            self.open_new_position(entry=bars[0].close,
                                   stop=3500,
                                   open_positions=open_positions,
                                   bars=bars,
                                   direction=PositionDirection.LONG,
                                   ExecutionType="Market")
            self.var_2 = 89

        if not entry_gate_passes(
            strategy=self,
            is_new_bar=is_new_bar,
            bars=bars,
            open_positions=open_positions,
            all_open_pos=all_open_pos,
        ):
            return

        self.logger.info("New bar. Checking for new entry options")
        self.logger.info("Market Regime: "+str(self.ta_data_trend_strat.marketRegime))
        if self.telegram is not None and "BTC" in self.symbol.symbol:
            self.telegram.send_log("Market Regime: "+str(self.ta_data_trend_strat.marketRegime)+ ", " + str(self.ta_data_trend_strat.marketDynamic))
            self.telegram.send_log("NATR: %.2f" % self.ta_data_trend_strat.natr_4h)

        longed = False
        shorted = False

        # Entries by Market Orders
        entry_context = build_entry_context(self)
        execution_context = EntryExecutionContext(
            strategy=self,
            bars=bars,
            account=account,
            open_positions=open_positions,
            direction_filter=directionFilter,
            entry_context=entry_context,
            longed=longed,
            shorted=shorted,
        )

        for idx, entry_module in enumerate(self.entryModules):
            if not hasattr(entry_module, "run") or not hasattr(entry_module, "enabled"):
                entry_module = as_entry_module(entry_module)
                self.entryModules[idx] = entry_module
            if entry_module.enabled(execution_context) and entry_module.is_ready(execution_context):
                entry_module.run(execution_context)

        longed = execution_context.longed
        shorted = execution_context.shorted

        if not self.longsAllowed:
            self.logger.info("Longs not allowed.")
            if self.telegram is not None:
                self.telegram.send_log("Longs not allowed.")
        if not self.shortsAllowed:
            self.logger.info("Shorts not allowed.")
            if self.telegram is not None:
                self.telegram.send_log("Shorts not allowed.")
        if not longed and not shorted and 'BTC' in self.symbol.symbol:
            self.logger.info("No new entries for now.")
            if self.telegram is not None:
                self.telegram.send_log("No new entries for now.")

    def constant_trail(self, periodStart, periodEnd, trail):
        is_constant = True
        for i in range(periodStart, periodEnd):
            if trail[-i] != trail[-(i + 1)]:
                is_constant = False
        return is_constant

    def higher_equal_h_trail(self, periodStart, periodEnd, trail):
        higher_equal = True
        for i in range(periodStart, periodEnd):
            if trail[-i] > trail[-(i + 1)]:
                higher_equal = False
        return higher_equal

    def lower_equal_h_trail(self, periodStart, periodEnd, trail):
        lower_equal = True
        for i in range(periodStart, periodEnd):
            if trail[-i] < trail[-(i + 1)]:
                lower_equal = False
        return lower_equal

    def manage_open_position(self, p, bars, account, pos_ids_to_cancel):
        super().manage_open_position(p, bars, account, pos_ids_to_cancel)
        # now local position management, if necessary

    def update_existing_entries(self, account, open_positions, longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount):
        foundLong, foundShort = super().update_existing_entries(account, open_positions, longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount)
        # now local updates, if necessary
        return foundLong, foundShort

    def get_data_for_plot(self, bar: Bar):
        plot_data = Indicator.get_data_static(bar, self.myId())
        if plot_data is not None:
            return plot_data
        else:
            return [bar.close, bar.close, bar.close, bar.close]

    def add_to_price_data_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_price_data_plot(fig, bars, time)

        # Plot TA-generated data
        offset = 0

        # Plot Strategy-generated Data
        if self.plotStrategyOneData and self.plotIndicators:
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[0], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "cyan"},
                            name=self.myId() + "_" + "Long_Entry")
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[1], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "mediumpurple"},
                            name=self.myId() + "_" + "Long_Stop")
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[2], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "cyan"},
                            name=self.myId() + "_" + "Short_Entry")
            sub_data = list(map(lambda b: self.get_data_for_plot(b)[3], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line={"width": 1, "color": "mediumpurple"},
                            name=self.myId() + "_" + "Short_Stop")

        # plot ta data
        # get ta data settings
        styles = self.ta_strat_one.get_line_styles()
        names = self.ta_strat_one.get_line_names()
        offset = 0

        if self.plotTrailsStatOne and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_strat_one.get_data_for_plot(b)[0], bars))  # 4H-High
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[0],
                            name=self.ta_strat_one.id + "_" + names[0])
            sub_data = list(map(lambda b: self.ta_strat_one.get_data_for_plot(b)[1], bars))  # 4H-Low
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[1],
                            name=self.ta_strat_one.id + "_" + names[1])

    def add_to_normalized_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_normalized_plot(fig, bars, time)


class DataTAStrategyOne:
    def __init__(self):
        self.h_highs_trail_vec = None
        self.h_lows_trail_vec = None
        self.h_body_lows_trail_vec = None
        self.h_highs_trail = None
        self.h_lows_trail = None


class TAStrategyOne(Indicator):
    ''' Run technical analysis here and store data in TAdataTrendStrategy '''

    def __init__(self,
                 timeframe: int = 240,
                 h_highs_trail_period: int = 10,
                 h_lows_trail_period: int = 10,
                 ta_data_trend_strat: TAdataTrendStrategy() = None
                 ):
        super().__init__('TAStrategyOne')
        # parant data
        self.ta_data_trend_strat = ta_data_trend_strat
        # local data
        self.taData_strat_one = DataTAStrategyOne()
        self.ranging_buffer = 0
        # Input parameters
        self.bars_per_week = int(60*24*7 / timeframe)
        self.bars_per_day = int(60*24 / timeframe)
        self.h_highs_trail_period = h_highs_trail_period
        self.h_lows_trail_period = h_lows_trail_period

    def on_tick(self, bars: List[Bar]):
        #print("TA analysis StrategyOne")
        self.run_ta_analysis()
        self.write_data_for_plot(bars)

    def set_ta_data_trend_strat(self, ta_data_trend_strat = None):
        self.ta_data_trend_strat = ta_data_trend_strat

    def get_ta_data(self):
        return self.taData_strat_one

    def run_ta_analysis(self):
        # Trails
        self.taData_strat_one.h_highs_trail_vec = talib.MAX(self.ta_data_trend_strat.talibbars.high, self.h_highs_trail_period)
        self.taData_strat_one.h_lows_trail_vec = talib.MIN(self.ta_data_trend_strat.talibbars.low, self.h_lows_trail_period)
        self.taData_strat_one.h_body_lows_trail_vec = talib.MIN(self.ta_data_trend_strat.talibbars.close, self.h_lows_trail_period)

        self.taData_strat_one.h_highs_trail = self.taData_strat_one.h_highs_trail_vec[-1] if not np.isnan(self.taData_strat_one.h_highs_trail_vec[-1]) else None
        self.taData_strat_one.h_lows_trail = self.taData_strat_one.h_lows_trail_vec[-1] if not np.isnan(self.taData_strat_one.h_lows_trail_vec[-1]) else None

    def write_data_for_plot(self, bars: List[Bar]):
        plot_data = [self.taData_strat_one.h_highs_trail,
                     self.taData_strat_one.h_lows_trail
                    ]
        self.write_data(bars[0], plot_data)  # [0] because we only know about it after the candle is closed and processed

    def get_line_names(self):
        return ["%1.fx4H-High" % self.h_highs_trail_period,         # 4H-High
                "%1.fx4H-Low" % self.h_lows_trail_period            # 4H-Low
                ]

    def get_number_of_lines(self):
        return 2

    def get_line_styles(self):
        return [
            {"width": 1, "color": "green", "dash": "dot"},          # 4H-High
            {"width": 1, "color": "red", "dash": "dot"},            # 4H-Low
               ]

    def get_data_for_plot(self, bar: Bar):
        plot_data = self.get_data(bar)
        if plot_data is not None:
            return plot_data
        else:
            return [bar.close, bar.close                            # 4H-Trails
             ]
