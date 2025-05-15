from typing import List
#import math

from kuegi_bot.bots.strategies.strat_w_trade_man import StrategyWithTradeManagement
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.indicators.talibbars import TAlibBars
import talib
import plotly.graph_objects as go
from enum import Enum
import numpy as np
from datetime import datetime


class MarketRegime(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    RANGING = "RANGING"
    NONE = "NONE"


class MarketDynamic(Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    NONE = "NONE"


class DataTrendStrategy:
    def __init__(self):
        # non-TA Data of the Trend Strategy
        self.stopLong = None
        self.stopShort = None


class TrendStrategy(StrategyWithTradeManagement):
    def __init__(self,
                 # TrendStrategy
                 timeframe: int = 240, ema_w_period: int = 1, highs_trail_4h_period: int = 1, lows_trail_4h_period: int = 1,
                 days_buffer_bear: int = 2, days_buffer_bull: int = 0, atr_4h_period: int = 10, natr_4h_period_slow: int = 10,
                 bbands_4h_period: int = 10, rsi_4h_period: int = 10, volume_sma_4h_period: int = 100,
                 plotIndicators: bool = False, plot_RSI: bool = False, trend_atr_fac: float = 0.5,
                 trend_var_1: float = 0,
                 # Risk
                 risk_with_trend: float = 1, risk_counter_trend:float = 1, risk_ranging: float = 1, risk_fac_shorts: float = 1,
                 sl_upper_bb_std_fac: float = 1, sl_lower_bb_std_fac: float = 1,
                 # SL input parameters
                 be_by_middleband: bool = True, be_by_opposite: bool = True, stop_at_middleband: bool = True,
                 tp_at_middleband: bool = True, tp_on_opposite: bool = True, stop_at_new_entry: bool = False,
                 trail_sl_with_bband: bool = False, stop_short_at_middleband: bool = True, stop_at_trail: bool = False,
                 stop_at_lowerband: bool = False,
                 atr_buffer_fac: float = 0, moving_sl_atr_fac: float = 5, ema_multiple_4_tp:float = 10,
                 # Plots
                 use_shapes: bool = False, plotBackgroundColor4Trend: bool = False, plotTrailsAndEMAs: bool = False,
                 plotBBands: bool = False, plotATR:bool = False,
                 # StrategyWithTradeManagement
                 maxPositions: int = 100, consolidate: bool = False, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3,
                 limit_entry_offset_perc: float = -0.1, delayed_cancel: bool = False, cancel_on_filter: bool = True,
                 tp_fac: float = 0
                 ):
        super().__init__(
            # StrategyWithTradeManagement
            maxPositions = maxPositions, consolidate = consolidate, close_on_opposite = close_on_opposite, bars_till_cancel_triggered = bars_till_cancel_triggered,
            limit_entry_offset_perc = limit_entry_offset_perc, delayed_cancel = delayed_cancel, cancel_on_filter = cancel_on_filter,
            tp_fac = tp_fac)

        # local variables
        self.data_trend_strat = DataTrendStrategy()
        self.ta_trend_strat = TATrendStrategyIndicator(
            timeframe = timeframe, ema_w_period= ema_w_period, highs_trail_4h_period= highs_trail_4h_period,
            lows_trail_4h_period = lows_trail_4h_period, days_buffer_bear= days_buffer_bear, days_buffer_bull= days_buffer_bull,
            atr_4h_period= atr_4h_period, natr_4h_period_slow= natr_4h_period_slow, bbands_4h_period= bbands_4h_period,
            sl_upper_bb_std_fac = sl_upper_bb_std_fac,
            sl_lower_bb_std_fac = sl_lower_bb_std_fac, trend_var_1= trend_var_1, oversold_limit_w_rsi = 30, reset_level_of_oversold_rsi = 50,
            rsi_4h_period = rsi_4h_period, rsi_d_period = 14, volume_sma_4h_period= volume_sma_4h_period, trend_atr_fac = trend_atr_fac
        )
        self.plotIndicators = plotIndicators
        self.plot_RSI = plot_RSI
        # Risk
        self.risk_with_trend = risk_with_trend
        self.risk_counter_trend = risk_counter_trend
        self.risk_ranging = risk_ranging
        self.risk_fac_shorts = risk_fac_shorts
        # SL entry parameters
        self.be_by_middleband = be_by_middleband
        self.be_by_opposite = be_by_opposite
        self.stop_at_middleband = stop_at_middleband
        self.tp_at_middleband = tp_at_middleband
        self.tp_on_opposite = tp_on_opposite
        self.stop_at_new_entry = stop_at_new_entry
        self.trail_sl_with_bband = trail_sl_with_bband
        self.atr_buffer_fac = atr_buffer_fac
        self.moving_sl_atr_fac = moving_sl_atr_fac
        self.sl_upper_bb_std_fac = sl_upper_bb_std_fac
        self.sl_lower_bb_std_fac = sl_lower_bb_std_fac
        self.stop_short_at_middleband = stop_short_at_middleband
        self.stop_at_trail = stop_at_trail
        self.stop_at_lowerband = stop_at_lowerband
        self.ema_multiple_4_tp = ema_multiple_4_tp
        # Plots
        self.use_shapes = use_shapes
        self.plotBackgroundColor4Trend = plotBackgroundColor4Trend
        self.plotTrailsAndEMAs = plotTrailsAndEMAs
        self.plotBBands = plotBBands
        self.plotATR = plotATR

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        #self.logger.info(vars(self))

    def myId(self):
        return "TrendStrategy"

    def min_bars_needed(self) -> int:
        return self.ta_trend_strat.max_4h_history_candles+1

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            self.ta_trend_strat.taData_trend_strat.talibbars.on_tick(bars)
            self.ta_trend_strat.on_tick(bars)
            #self.logger.info('Current ta indicator values of trend strat:')
            #self.logger.info(vars(self.ta_trend_strat.taData_trend_strat))

    def get_ta_data_trend_strategy(self):
        return self.ta_trend_strat.taData_trend_strat

    def add_to_price_data_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_price_data_plot(fig, bars, time)

        # plot trend indicator
        if self.plotBackgroundColor4Trend and self.plotIndicators:
            if self.use_shapes:# is slow
                trend = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[3], bars))
                time_short = []
                trend_short = []
                time_short.append(time[0])
                trend_short.append(trend[0])
                last_trend = trend[0]

                for i, (t, d) in enumerate(zip(time, trend)):
                    if d != last_trend:
                        time_short.append(time[i])
                        trend_short.append(d)
                        last_trend = d

                time_short.append(time[-1])
                trend_short.append(trend[-1])

                i = 1
                while i < len(time_short):
                    if trend_short[i-1] == 1:
                        color = "lightgreen"
                    elif trend_short[i-1] == -1:
                        color = "orangered"
                    elif trend_short[i-1] == 0:
                        color = "steelblue"
                    elif trend_short[i-1] == 2:
                        color = "black"
                    else:
                        color = "blue"
                    fig.add_vrect(x0=time_short[i-1], x1=time_short[i], fillcolor=color, opacity=0.3, layer="below", line_width=0)
                    i+=1
            else:# use traces (faster)
                trend = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[3], bars))  # Trend
                time_short = [time[0]]
                trend_short = [trend[0]]
                last_trend = trend[0]

                for i, (t, d) in enumerate(zip(time, trend)):
                    if d != last_trend:
                        time_short.append(time[i - 1])
                        trend_short.append(last_trend)
                        time_short.append(time[i])
                        trend_short.append(d)
                        last_trend = d

                time_short.append(time[-1])
                trend_short.append(trend[-1])

                # Initialize highest_high and lowest_low with the first bar's high and low
                highest_high = bars[0].high
                lowest_low = bars[0].low

                # Iterate over the rest of the bars
                for bar in bars[1:]:
                    if bar.high > highest_high:
                        highest_high = bar.high
                    if bar.low < lowest_low:
                        lowest_low = bar.low

                color_map = {1: "rgba(144,238,144,0.3)", -1: "rgba(255,69,0,0.3)", 0: "rgba(70,130,180,0.3)",2: "rgba(0,0,0,0.3)"}
                for i in range(1, len(time_short)):
                    color = color_map.get(trend_short[i - 1], "rgba(0, 0, 255, 0.3)")

                    # Add a trace for the upper boundary
                    fig.add_trace(go.Scatter(
                        x=[time_short[i - 1], time_short[i]],
                        y=[highest_high, highest_high],
                        mode='lines',
                        line=dict(width=0, color='rgba(0, 0, 255, 0.3)'),
                        fill=None,  # No fill for the upper boundary
                        showlegend=False,
                        hoverinfo='none'
                    ))

                    # Add a trace for the lower boundary
                    fig.add_trace(go.Scatter(
                        x=[time_short[i - 1], time_short[i]],
                        y=[lowest_low, lowest_low],
                        mode='lines',
                        line=dict(width=0, color='rgba(0, 0, 255, 0.3)'),
                        fill='tonexty',
                        fillcolor=color,
                        opacity=0.5,
                        showlegend=False,
                        hoverinfo='none'
                    ))

        # get ta data settings
        styles = self.ta_trend_strat.get_line_styles()
        names = self.ta_trend_strat.get_line_names()
        offset = 0

        # plot ta data
        if self.plotTrailsAndEMAs and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[0], bars))   # W-EMA
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[0],
                            name=self.ta_trend_strat.id + "_" + names[0])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[1], bars))   # D-High
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[1],
                            name=self.ta_trend_strat.id + "_" + names[1])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[2], bars))   # D-Low
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[2],
                            name=self.ta_trend_strat.id + "_" + names[2])
            plotMidTrail = False
            if plotMidTrail:
                sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[4], bars))   # midTrail
                fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[4],
                                name=self.ta_trend_strat.id + "_" + names[4])

        # atr_4h
        if self.plotATR and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[5], bars))   # atr_4h + close
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[5],
                            name=self.ta_trend_strat.id + "_" + names[5])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[6], bars))   # fast natr_4h
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[6],
                            name=self.ta_trend_strat.id + "_" + names[6])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[7], bars))   # slow natr_4h
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[7],
                            name=self.ta_trend_strat.id + "_" + names[7])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[15], bars))  # atr_4h + Trail + close
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[15],
                            name=self.ta_trend_strat.id + "_" + names[15])

        # plot Bollinger Bands
        if self.plotBBands and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[8], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[8],
                            name=self.ta_trend_strat.id + "_" + names[8])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[9], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[9],
                            name=self.ta_trend_strat.id + "_" + names[9])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[10], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[10],
                            name=self.ta_trend_strat.id + "_" + names[10])

    def add_to_normalized_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_normalized_plot(fig, bars, time)

        # get ta data settings
        styles = self.ta_trend_strat.get_line_styles()
        names = self.ta_trend_strat.get_line_names()
        offset = 0

        # ATR
        sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[6], bars))  # fast natr_4h
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[6],
                        name=self.ta_trend_strat.id + "_" + names[6])
        sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[7], bars))  # slow natr_4h
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[7],
                        name=self.ta_trend_strat.id + "_" + names[7])
        sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[14], bars))  # natr + trail normalized
        fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[14],
                        name=self.ta_trend_strat.id + "_" + names[14])

        # RSI
        if self.plot_RSI:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[11], bars))  # 4H-RSI
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[11],
                            name=self.ta_trend_strat.id + "_" + names[11])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[12], bars))  # D-RSI
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[12],
                            name=self.ta_trend_strat.id + "_" + names[12])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[13], bars))  # W-RSI
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[13],
                            name=self.ta_trend_strat.id + "_" + names[13])

    def calc_pos_size(self, risk, entry, exitPrice, atr: float = 0):
        delta = entry - exitPrice

        if (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BULL and delta > 0) or \
                (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BEAR and delta < 0):
            risk = self.risk_with_trend
            if delta<0:
                risk = risk/self.risk_fac_shorts  # less risk for shorts
        elif (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BEAR and delta > 0) or \
                (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BULL and delta < 0):
            risk = self.risk_counter_trend
            if delta<0:
                risk = risk/2  # less risk for shorts
        else:
            risk = self.risk_ranging
            if delta<0:
                risk = risk/2  # less risk for shorts

        if not self.symbol.isInverse:
            amount = risk / delta
        else:
            amount = -risk / (1 / entry - 1 / (entry - delta))
        amount = self.symbol.normalizeSize(amount)
        return amount

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        is_new_bar = False
        if bars[0].open == bars[0].close:
            is_new_bar = True

        if is_new_bar:
            # Update SLs based on BBs
            orderType = TradingBot.order_type_from_order_id(order.id)
            if orderType == OrderType.SL:  # Manage Stop Losses
                new_trigger_price = order.trigger_price
                if new_trigger_price is not None and \
                        self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband is not None and \
                        self.ta_trend_strat.taData_trend_strat.bbands_4h.std is not None:
                    upper_band = self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband + self.ta_trend_strat.taData_trend_strat.bbands_4h.std * self.sl_upper_bb_std_fac
                    lower_band = self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband - self.ta_trend_strat.taData_trend_strat.bbands_4h.std * self.sl_lower_bb_std_fac
                    if order.amount > 0:  # SL for SHORTS
                        if self.be_by_middleband and \
                                bars[1].low < self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                            new_trigger_price = min(position.wanted_entry, new_trigger_price)
                        if self.be_by_opposite and \
                                bars[1].low < (lower_band + self.ta_trend_strat.taData_trend_strat.atr_4h * self.atr_buffer_fac):
                            new_trigger_price = min(position.wanted_entry, new_trigger_price)
                        if self.stop_at_new_entry and \
                                bars[1].low < self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                            new_trigger_price = min(upper_band, new_trigger_price)
                        if self.stop_short_at_middleband and \
                                bars[1].low < lower_band:
                            new_trigger_price = min(self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband - self.ta_trend_strat.taData_trend_strat.atr_4h, new_trigger_price)
                        if self.tp_on_opposite and \
                                bars[1].low < lower_band:
                            new_trigger_price = min(bars[0].open, new_trigger_price)
                        if self.tp_at_middleband and \
                                bars[0].open < self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                            new_trigger_price = min(self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband, new_trigger_price)
                        if self.trail_sl_with_bband:
                            new_trigger_price = min(upper_band, new_trigger_price)
                        if self.moving_sl_atr_fac > 0 and \
                            bars[1].low + self.ta_trend_strat.taData_trend_strat.atr_4h * self.moving_sl_atr_fac < new_trigger_price:
                            new_trigger_price = bars[1].low + self.ta_trend_strat.taData_trend_strat.atr_4h * self.moving_sl_atr_fac
                        if self.stop_at_trail:
                            new_trigger_price = min(self.ta_trend_strat.taData_trend_strat.highs_trail_4h + self.ta_trend_strat.taData_trend_strat.atr_4h*8, new_trigger_price)

                    elif order.amount < 0:  # SL for LONGs
                        if self.stop_at_trail:
                            new_trigger_price = max(self.ta_trend_strat.taData_trend_strat.lows_trail_4h - self.ta_trend_strat.taData_trend_strat.atr_4h, new_trigger_price)
                        if self.stop_at_lowerband:
                            new_trigger_price = max(lower_band, new_trigger_price)
                        if self.be_by_middleband and \
                                bars[1].high > self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                            new_trigger_price = max(position.wanted_entry, new_trigger_price)
                        if self.be_by_opposite and \
                                bars[1].high > (upper_band - self.ta_trend_strat.taData_trend_strat.atr_4h * self.atr_buffer_fac):
                            new_trigger_price = max(position.wanted_entry, new_trigger_price)
                        if self.stop_at_new_entry and \
                                bars[1].high > self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                            new_trigger_price = max(lower_band, new_trigger_price)
                        if self.stop_at_middleband and \
                                bars[1].high > (upper_band - self.ta_trend_strat.taData_trend_strat.atr_4h * self.atr_buffer_fac):
                            new_trigger_price = max(self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband, new_trigger_price)
                        if self.tp_on_opposite and \
                                bars[1].high > upper_band:
                            new_trigger_price = max(bars[0].open, new_trigger_price)
                        if self.tp_at_middleband and \
                                bars[0].open > self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband:
                            new_trigger_price = max(self.ta_trend_strat.taData_trend_strat.bbands_4h.middleband, new_trigger_price)
                        if self.trail_sl_with_bband:
                            new_trigger_price = max(lower_band, new_trigger_price)
                        if self.ema_multiple_4_tp != 0:
                            ema_multiple = self.ta_trend_strat.taData_trend_strat.ema_w * self.ema_multiple_4_tp
                            d_rsi_low = 90 < self.ta_trend_strat.taData_trend_strat.rsi_d
                            if bars[0].open > ema_multiple and d_rsi_low:
                                new_trigger_price = bars[0].open

                    if new_trigger_price != order.trigger_price:
                        order.trigger_price = new_trigger_price
                        to_update.append(order)


class BBands:
    def __init__(self, middleband:float = None, middleband_vec = [], std:float = None, std_vec = []):
        self.middleband = middleband
        self.middleband_vec = middleband_vec
        self.std = std
        self.std_vec = std_vec


class TAdataTrendStrategy:
    def __init__(self):
        ''' TA-data of the Trend Strategy '''
        self.talibbars = TAlibBars()
        self.marketRegime = MarketRegime.NONE
        self.marketDynamic = MarketDynamic.NONE
        # 4h arrays
        self.bbands_4h = BBands(None, [],None, [])
        #self.bbands_talib = Talib_BBANDS(None, None, None)
        self.atr_4h_vec = None
        self.atr_4h = None
        self.natr_4h_vec = None
        self.natr_4h = None
        self.natr_slow_4h_vec = None
        self.natr_slow_4h = None
        self.highs_trail_4h_vec = None
        self.natr_trail_mix = None
        self.atr_trail_mix = None
        self.highs_trail_4h = None
        self.lows_trail_4h_vec = None
        self.lows_trail_4h = None
        self.mid_trail_4h = None
        self.rsi_4h_vec = None
        self.volume_4h = None
        self.volume_sma_4h_vec = None
        # daily arrays
        #self.rsi_d_vec = None
        self.rsi_d = None
        # weekly arrays
        #self.ema_w_vec = None
        self.ema_w = None
        #self.rsi_w_vec = None
        self.rsi_w = None
        # index of last bar
        self.last_4h_index = -1
        self.is_initialized = False


class TATrendStrategyIndicator(Indicator):
    ''' Run technical analysis calculations here and store data in TAdataTrendStrategy '''

    def __init__(self,
                 timeframe: int = 240,
                 # 4h periods
                 bbands_4h_period: int = 10,
                 atr_4h_period: int = 10,
                 natr_4h_period_slow: int = 10,
                 highs_trail_4h_period: int = 10,
                 lows_trail_4h_period: int = 10,
                 rsi_4h_period: int = 10,
                 volume_sma_4h_period: int = 100,
                 # daily periods
                 days_buffer_bear: int = 2,
                 days_buffer_bull: int = 0,
                 trend_atr_fac: float = 0.5,
                 rsi_d_period: int = 14,
                 # weekly periods
                 ema_w_period: int = 10,
                 rsi_w_period: int = 14,
                 oversold_limit_w_rsi: int = 10,
                 reset_level_of_oversold_rsi: int = 90,
                 # stop loss bband factors
                 sl_upper_bb_std_fac: float = 2.0,
                 sl_lower_bb_std_fac: float = 2.0,
                 # debug variables
                 trend_var_1: float = 0):
        super().__init__('TAtrend')
        # local input data
        self.taData_trend_strat = TAdataTrendStrategy()
        # debug variables
        self.trend_var_1 = trend_var_1
        # Trend identification parameters
        self.bull_buffer = 0
        self.bull_rsi_locked = False
        self.ranging_buffer = 0
        self.bear_buffer = 0
        self.trend_atr_fac = trend_atr_fac
        self.bullish_reversal = False
        self.oversold_limit_w_rsi = oversold_limit_w_rsi
        self.reset_level_of_oversold_rsi = reset_level_of_oversold_rsi
        # Constant enabler parameters
        self.bars_per_week = int(60 * 24 * 7 / timeframe)
        self.bars_per_day = int(60 * 24 / timeframe)
        # 4H periods
        self.bbands_4h_period = bbands_4h_period
        self.atr_4h_period = atr_4h_period
        self.natr_4h_period_slow = natr_4h_period_slow
        self.rsi_4h_period = rsi_4h_period
        self.sl_upper_bb_4h_std_fac = sl_upper_bb_std_fac
        self.sl_lower_bb_4h_std_fac = sl_lower_bb_std_fac
        self.highs_trail_4h_period = highs_trail_4h_period
        self.lows_trail_4h_period = lows_trail_4h_period
        self.volume_sma_4h_period = volume_sma_4h_period
        # Daily periods
        self.days_buffer_bear = days_buffer_bear
        self.rsi_d_period = rsi_d_period
        # Weekly periods
        self.days_buffer_bull = days_buffer_bull
        self.ema_w_period = ema_w_period
        self.rsi_w_period = rsi_w_period
        # Max period variables
        self.max_d_period = max(self.days_buffer_bull, self.days_buffer_bear, self.rsi_d_period + 1)
        self.max_w_period = max(self.ema_w_period, self.rsi_w_period)
        self.max_4h_period = max(self.bbands_4h_period, self.atr_4h_period, self.natr_4h_period_slow,
                                 self.rsi_4h_period, self.highs_trail_4h_period, self.lows_trail_4h_period,
                                 self.volume_sma_4h_period, self.max_d_period * 6, (self.max_w_period+2) * 7 * 6)
        self.max_4h_history_candles = self.max_4h_period

    def on_tick(self, bars: List[Bar]):
        # Run TA calculations
        self.run_ta_analysis()
        self.identify_trend()
        self.write_data_for_plot(bars)

    def get_ta_data(self):
        return self.taData_trend_strat

    def run_ta_analysis(self):
        if not self.taData_trend_strat.is_initialized:
            # Initialize arrays only if not initialized yet
            self.initialize_arrays()

        # Update TA-indicators
        self.update_4h_values()
        self.update_daily_values()
        self.update_weekly_values()

    def initialize_arrays(self):
        # Initialize arrays with the provided lengths
        # 4H arrays
        self.taData_trend_strat.highs_trail_4h_vec = np.full(self.max_4h_period, np.nan)
        self.taData_trend_strat.lows_trail_4h_vec = np.full(self.max_4h_period, np.nan)
        self.taData_trend_strat.atr_4h_vec = np.full(self.max_4h_period, np.nan)
        self.taData_trend_strat.natr_4h_vec = np.full(self.max_4h_period, np.nan)
        self.taData_trend_strat.natr_slow_4h_vec = np.full(self.max_4h_period, np.nan)
        self.taData_trend_strat.rsi_4h_vec = np.full(self.max_4h_period, np.nan)
        self.taData_trend_strat.volume_sma_4h_vec = np.full(self.max_4h_period, np.nan)

        # Daily arrays
        #self.taData_trend_strat.rsi_d_vec = np.full(self.max_d_period, np.nan)
        # Weekly arrays
        #self.taData_trend_strat.ema_w_vec = np.full(self.max_w_period, np.nan)
        #self.taData_trend_strat.rsi_w_vec = np.full(self.max_w_period, np.nan)

        # weekly:
        #talibbars = self.taData_trend_strat.talibbars
        #len_weekly = len(talibbars.close_weekly)
        ema_w_vec = talib.EMA(self.taData_trend_strat.talibbars.close_weekly[-self.max_w_period:], timeperiod=self.ema_w_period)
        # self.taData_trend_strat.ema_w_vec[last_index] = ema_w
        self.taData_trend_strat.ema_w = ema_w_vec[-1]

        # Set the initialized flag to True
        self.taData_trend_strat.is_initialized = True

    def update_4h_values(self):
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close
        high = talibbars.high
        low = talibbars.low
        volume = talibbars.volume

        if close is None or len(close) < self.max_4h_period+1:
            return

        # Trails
        self.taData_trend_strat.highs_trail_4h_vec = talib.MAX(high[-self.max_4h_period:], self.highs_trail_4h_period)
        self.taData_trend_strat.lows_trail_4h_vec = talib.MIN(low[-self.max_4h_period:], self.lows_trail_4h_period)
        self.taData_trend_strat.highs_trail_4h = self.taData_trend_strat.highs_trail_4h_vec[-1]
        self.taData_trend_strat.lows_trail_4h = self.taData_trend_strat.lows_trail_4h_vec[-1]
        if self.taData_trend_strat.highs_trail_4h is not None and self.taData_trend_strat.lows_trail_4h is not None and \
                self.taData_trend_strat.lows_trail_4h != 0:
            self.taData_trend_strat.mid_trail_4h = 0.5*(self.taData_trend_strat.highs_trail_4h - self.taData_trend_strat.lows_trail_4h) + self.taData_trend_strat.lows_trail_4h

        # Update Bollinger Bands arrays
        a, b, c = talib.BBANDS(close[-self.max_4h_period-1:], timeperiod=self.bbands_4h_period, nbdevup=1, nbdevdn=1)
        upperband = a[-1]
        self.taData_trend_strat.bbands_4h.middleband = b[-1]
        if not np.isnan(upperband) and not np.isnan(self.taData_trend_strat.bbands_4h.middleband):
            self.taData_trend_strat.bbands_4h.std = upperband - self.taData_trend_strat.bbands_4h.middleband
        else:
            self.taData_trend_strat.bbands_4h.std = np.nan

        self.taData_trend_strat.bbands_4h.middleband_vec = b
        self.taData_trend_strat.bbands_4h.std_vec = a - b

        # Update atr_4h & natr_4h arrays
        atr_4h_vec = talib.ATR(high[- self.max_4h_period-1:],low[-self.max_4h_period-1:], close[- self.max_4h_period-1:], self.atr_4h_period)
        natr_4h_vec = talib.NATR(high[-self.max_4h_period-1:],low[-self.max_4h_period-1:], close[-self.max_4h_period-1:], self.atr_4h_period)
        natr_slow_4h_vec = talib.NATR(high[- self.max_4h_period-1:],low[- self.max_4h_period-1:], close[- self.max_4h_period-1:], self.natr_4h_period_slow)
        self.taData_trend_strat.atr_4h_vec = atr_4h_vec
        self.taData_trend_strat.natr_4h_vec = natr_4h_vec
        self.taData_trend_strat.natr_slow_4h_vec = natr_slow_4h_vec

        self.taData_trend_strat.atr_4h = atr_4h_vec[-1]
        self.taData_trend_strat.natr_4h = natr_4h_vec[-1]
        self.taData_trend_strat.natr_slow_4h = natr_slow_4h_vec[-1]
        self.taData_trend_strat.natr_trail_mix = (
                (self.taData_trend_strat.natr_4h+
                 ((self.taData_trend_strat.highs_trail_4h - self.taData_trend_strat.lows_trail_4h)/
                 self.taData_trend_strat.highs_trail_4h))/2)
        self.taData_trend_strat.atr_trail_mix = (self.taData_trend_strat.atr_4h + (self.taData_trend_strat.highs_trail_4h - self.taData_trend_strat.lows_trail_4h)/5)/2

        # Update RSI for 4H timeframe
        self.taData_trend_strat.rsi_4h_vec = talib.RSI(close[-min(self.max_4h_period,200+self.rsi_4h_period):], self.rsi_4h_period)

        # Update Volume for 4H timeframe
        self.taData_trend_strat.volume_4h = volume[-1]
        self.taData_trend_strat.volume_sma_4h_vec = talib.MA(volume[-self.max_4h_period:], self.volume_sma_4h_period,0)

    def update_daily_values(self):
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close_daily

        if close is None or len(close) < self.max_d_period+1:
            return

        # Update RSI for daily timeframe
        rsi_daily = talib.RSI(close[-self.rsi_d_period-1:], self.rsi_d_period)[-1]
        self.taData_trend_strat.rsi_d = rsi_daily

    def update_weekly_values(self):
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close_weekly

        # Update EMA for weekly timeframe
        if close is None or len(close) < self.max_w_period+1:
            return
        ema_w = talib.EMA(close[-self.ema_w_period:], timeperiod=self.ema_w_period)[-1]
        self.taData_trend_strat.ema_w = ema_w

        # Update RSI for weekly timeframe
        rsi_w = talib.RSI(close[-self.rsi_w_period-1:], timeperiod=self.rsi_w_period)[-1]
        self.taData_trend_strat.rsi_w = rsi_w

    def identify_trend_original(self):
        # Trend based on W-EMA and trails
        if self.taData_trend_strat.rsi_w is not None and self.taData_trend_strat.ema_w is not None:
            if self.taData_trend_strat.talibbars.low[-1] < self.taData_trend_strat.ema_w:
                self.taData_trend_strat.marketRegime = MarketRegime.BEAR
                self.bear_buffer = self.days_buffer_bear * self.bars_per_day
                self.ranging_buffer = self.days_buffer_bull * self.bars_per_day
            elif self.taData_trend_strat.talibbars.close[-1] > self.taData_trend_strat.ema_w:#self.taData_trend_strat.talibbars.close[-1] > self.taData_trend_strat.highs_trail_4h_vec[-2] or \
                self.bear_buffer -= 1
                if self.bear_buffer <= 0:
                    self.ranging_buffer -= 1
                    if self.ranging_buffer <= 0:
                        self.taData_trend_strat.marketRegime = MarketRegime.BULL
                    else:
                        self.taData_trend_strat.marketRegime = MarketRegime.RANGING
                else:
                    self.taData_trend_strat.marketRegime = MarketRegime.BEAR
            else:
                self.ranging_buffer -= 1
                if self.ranging_buffer <= 0:
                    self.taData_trend_strat.marketRegime = MarketRegime.RANGING
                else:
                    self.taData_trend_strat.marketRegime = MarketRegime.BEAR
        else:
            self.taData_trend_strat.marketRegime = MarketRegime.NONE

    def identify_trend_stateless(self):
        """
        Identifies market regime by analyzing historical data to determine buffer states.
        Uses 4H timeframe for all calculations including EMA.
        """
        # Calculate buffer lengths
        bear_buffer_length = self.days_buffer_bear * self.bars_per_day
        ranging_buffer_length = self.days_buffer_bull * self.bars_per_day
        max_buffer_length = bear_buffer_length + ranging_buffer_length
        period = self.ema_w_period * 7 * 6 -6#self.trend_var_1 # Convert weeks to 4H periods

        # Get price data and calculate EMA
        close = self.taData_trend_strat.talibbars.close
        lows = self.taData_trend_strat.talibbars.low

        # Calculate EMA using the required lookback period plus buffer lengths
        lookback_data = close[-(max_buffer_length + period):]
        w_ema_on_4H_vec = talib.EMA(lookback_data, timeperiod=period)

        # Immediate BEAR check using aligned latest values
        if lows[-1] < w_ema_on_4H_vec[-1]:
            self.taData_trend_strat.marketRegime = MarketRegime.BEAR
            return

        # Initialize counts for reconstructing buffer values
        bear_countdown = 0  # How many bars since bear buffer started counting
        ranging_countdown = 0  # How many bars since ranging buffer started counting
        found_bearish = False

        # Get the relevant sections of price data aligned with EMA length
        ema_length = len(w_ema_on_4H_vec)
        closes_section = close[-ema_length:]
        lows_section = lows[-ema_length:]

        # Walk backwards through history starting from second-to-last bar
        for i in range(ema_length - 2, -1, -1):
            if lows_section[i] < w_ema_on_4H_vec[i]:
                found_bearish = True
                break

            # Count how many bars would have decremented each buffer
            if closes_section[i] > w_ema_on_4H_vec[i]:
                bear_countdown += 1
                if bear_countdown >= bear_buffer_length:
                    ranging_countdown += 1  # Bear buffer depleted, decrease ranging buffer
            else:  # closes_section[i] <= w_ema_on_4H_vec[i] and lows_section[i] >= w_ema_on_4H_vec[i]
                ranging_countdown += 1  # This bar would have only decreased ranging buffer

        # Calculate effective buffer values
        if found_bearish:
            effective_bear_buffer = max(0, bear_buffer_length - bear_countdown)
            if bear_countdown >= bear_buffer_length:
                effective_ranging_buffer = max(0, ranging_buffer_length - ranging_countdown)
            else:
                effective_ranging_buffer = ranging_buffer_length
        else:
            # No bearish signal found in history - buffers must be depleted
            effective_bear_buffer = 0
            effective_ranging_buffer = 0

        # Determine current regime based on current bar and reconstructed buffer values
        if close[-1] > w_ema_on_4H_vec[-1]:
            if effective_bear_buffer > 0:
                self.taData_trend_strat.marketRegime = MarketRegime.BEAR
            elif effective_ranging_buffer > 0:
                self.taData_trend_strat.marketRegime = MarketRegime.RANGING
            else:
                self.taData_trend_strat.marketRegime = MarketRegime.BULL
        else:  # close[-1] <= w_ema_on_4H_vec[-1] and lows[-1] >= w_ema_on_4H_vec[-1]
            if effective_ranging_buffer > 0:
                self.taData_trend_strat.marketRegime = MarketRegime.BEAR
            else:
                self.taData_trend_strat.marketRegime = MarketRegime.RANGING

    def identify_trend(self):
        high_break = False
        low_break = False
        bull_buffer_length = self.days_buffer_bull * self.bars_per_day
        bear_buffer_length = self.days_buffer_bear * self.bars_per_day

        i = 1
        if self.taData_trend_strat.atr_4h is None:
            return

        delta= self.taData_trend_strat.atr_4h * self.trend_atr_fac
        while i < len(self.taData_trend_strat.highs_trail_4h_vec)-1:
            if self.taData_trend_strat.highs_trail_4h_vec[-i] > self.taData_trend_strat.highs_trail_4h_vec[-i - 1]+delta:
                high_break = True
                break
            elif self.taData_trend_strat.lows_trail_4h_vec[-i] < self.taData_trend_strat.lows_trail_4h_vec[-i - 1]:
                low_break = True
                break
            i += 1

        if i < bull_buffer_length and high_break:
            self.taData_trend_strat.marketRegime = MarketRegime.BULL
        elif i < bear_buffer_length and low_break:
            self.taData_trend_strat.marketRegime = MarketRegime.BEAR
        else:
            self.taData_trend_strat.marketRegime = MarketRegime.RANGING

        closes = self.taData_trend_strat.talibbars.close
        mid_line = self.taData_trend_strat.lows_trail_4h_vec[-1] + 0.5 * (self.taData_trend_strat.highs_trail_4h_vec[-1] - self.taData_trend_strat.lows_trail_4h_vec[-1])
        if self.taData_trend_strat.marketRegime == MarketRegime.BEAR and closes[-1] > mid_line:
            pass
        elif self.taData_trend_strat.marketRegime == MarketRegime.BULL and closes[-1] < mid_line:
            self.taData_trend_strat.marketRegime = MarketRegime.RANGING

        if closes[-1] < mid_line:
            self.taData_trend_strat.marketRegime = MarketRegime.BEAR

        self.identifyMarketDynamics()

    def identifyMarketDynamics(self):
        # Average Directional Movement Index
        self.taData_trend_strat.marketDynamic = MarketDynamic.TRENDING
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close
        high = talibbars.high
        low = talibbars.low
        period = 30
        adx = talib.ADX(high, low, close, period)[-1]
        if not np.isnan(adx):
            if adx > 20:
                self.taData_trend_strat.marketDynamic = MarketDynamic.TRENDING
            else:
                self.taData_trend_strat.marketDynamic = MarketDynamic.RANGING
        else:
            self.taData_trend_strat.marketDynamic = MarketDynamic.NONE

    def write_data_for_plot(self, bars: List[Bar]):
        if self.taData_trend_strat.marketRegime == MarketRegime.BULL:
            trend = 1
        elif self.taData_trend_strat.marketRegime == MarketRegime.BEAR:
            trend = -1
        elif self.taData_trend_strat.marketRegime == MarketRegime.RANGING:
            trend = 0
        elif self.taData_trend_strat.marketRegime == MarketRegime.NONE:
            trend = 2
        else:
            trend = 10

        if self.taData_trend_strat.bbands_4h.middleband is not None:
            upper_band = self.taData_trend_strat.bbands_4h.middleband + self.taData_trend_strat.bbands_4h.std * self.sl_upper_bb_4h_std_fac
            lower_band = self.taData_trend_strat.bbands_4h.middleband - self.taData_trend_strat.bbands_4h.std * self.sl_lower_bb_4h_std_fac
        else:
            upper_band = None
            lower_band = None

        plot_data = [self.taData_trend_strat.ema_w,
                     self.taData_trend_strat.highs_trail_4h,
                     self.taData_trend_strat.lows_trail_4h,
                     trend,
                     self.taData_trend_strat.mid_trail_4h,
                     self.taData_trend_strat.atr_4h if self.taData_trend_strat.atr_4h is not None else 0,
                     self.taData_trend_strat.natr_4h if self.taData_trend_strat.natr_4h is not None else 0,
                     self.taData_trend_strat.natr_slow_4h if self.taData_trend_strat.natr_slow_4h is not None else 0,
                     upper_band,
                     self.taData_trend_strat.bbands_4h.middleband,
                     lower_band,
                     self.taData_trend_strat.rsi_4h_vec[-1],
                     self.taData_trend_strat.rsi_d,
                     self.taData_trend_strat.rsi_w,
                     self.taData_trend_strat.natr_trail_mix if self.taData_trend_strat.natr_trail_mix is not None else 0,
                     self.taData_trend_strat.atr_trail_mix if self.taData_trend_strat.atr_trail_mix is not None else 0
                    ]
        self.write_data(bars[0], plot_data)  # [0] because we only know about it after the candle is closed and processed

    def get_line_names(self):
        return ["%1.fW-EMA" % self.ema_w_period,
                "%1.fD-High" % self.highs_trail_4h_period,
                "%1.fD-Low" % self.lows_trail_4h_period,
                "Market Trend",
                "MidTrail",
                "ATR",
                "NATR",
                "slowNATR",
                "%.1fSTD_upperband" % self.sl_upper_bb_4h_std_fac,  # Bollinger Bands SL
                "middleband",  # Bollinger Bands
                "%.1fSTD_lowerband" % self.sl_lower_bb_4h_std_fac,  # Bollinger Bands SL
                "4H-RSI",                                           # 4H RSI
                "D-RSI",                                            # D-RSI
                "W-RSI",                                            # W-RSI
                "NATR + Trail",                                     # NATR + Trail normalized
                "ATR + Trail"                                       # ATR + Trail
                ]

    def get_number_of_lines(self):
        return 16

    def get_line_styles(self):
        return [
            {"width": 1, "color": "black"},                         # W-EMA
            {"width": 1, "color": "green"},                         # D-High
            {"width": 1, "color": "red"},                           # D-Low
            {"width": 1, "color": "black"},                         # Trend
            {"width": 1, "color": "blue", "dash": "dot"},           # Mid-Trail
            {"width": 1, "color": "purple", "dash": "dot"},         # atr_4h
            {"width": 1, "color": "black"},                         # natr_4h
            {"width": 1, "color": "blue"},                          # slowNATR
            {"width": 1, "color": "dodgerblue"},                    # BBands SL
            {"width": 1, "color": "dodgerblue", "dash": "dot"},     # BBands
            {"width": 1, "color": "dodgerblue"},                    # BBands SL
            {"width": 1, "color": "green"},                         # 4H RSI
            {"width": 1, "color": "blue"},                          # D-RSI
            {"width": 1, "color": "black"},                         # W-RSI
            {"width": 1, "color": "orange", "dash": "dot"},         # natr + trail normalized
            {"width": 1, "color": "orange"},                        # atr + trail
               ]

    def get_data_for_plot(self, bar: Bar):
        plot_data = self.get_data(bar)
        if plot_data is not None:
            return plot_data
        else:
            return [bar.close,                                      # W-EMA
                    bar.close,                                      # D-High
                    bar.close,                                      # D-Low
                    bar.close,                                      # Trend
                    bar.close,                                      # Mid-Trail
                    0,                                              # ATR
                    0,                                              # NATR
                    0,                                              # # slow NATR
                    bar.close, bar.close, bar.close,                # Bollinger Bands
                    0,                                              # 4H-RSI
                    0,                                              # D-RSI
                    0,                                              # W-RSI
                    0,                                              # NATR + Trail
                    0                                               # ATR + Trail
             ]
