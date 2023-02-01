from typing import List
import math

from kuegi_bot.bots.strategies.strat_w_trade_man import StrategyWithTradeManagement
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position
from kuegi_bot.bots.trading_bot import TradingBot, PositionDirection
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.indicators.talibbars import TAlibBars
import talib
import plotly.graph_objects as go
from enum import Enum
import numpy as np


class MarketRegime(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    RANGING = "RANGING"
    NONE = "UNDEFINED"


class DataTrendStrategy:
    def __init__(self):
        # non-TA Data of the Trend Strategy
        self.stopLong = None
        self.stopShort = None


class TrendStrategy(StrategyWithTradeManagement):
    def __init__(self,
                 # TrendStrategy
                 timeframe: int = 240, w_ema_period: int = 1, d_highs_trail_period: int = 1, d_lows_trail_period: int = 1,
                 trend_d_period: int = 2, trend_w_period: int = 0, atr_period: int = 10, natr_period_slow: int = 10,
                 bbands_period: int = 10,
                 plotIndicators: bool = False,
                 # Risk
                 risk_with_trend: float = 1, risk_counter_trend:float = 1, risk_ranging: float = 1,
                 sl_upper_bb_std_fac: float = 1, sl_lower_bb_std_fac: float = 1, sl_atr_fac: float = 2,
                 # SL input parameters
                 be_by_middleband: bool = True, be_by_opposite: bool = True, stop_at_middleband: bool = True,
                 tp_at_middleband: bool = True, tp_on_opposite: bool = True, stop_at_new_entry: bool = False,
                 trail_sl_with_bband: bool = False, atr_buffer_fac: float = 0, moving_sl_atr_fac: float = 5,
                 # StrategyWithTradeManagement
                 maxPositions: int = 100, close_on_opposite: bool = False, bars_till_cancel_triggered: int = 3,
                 limit_entry_offset_perc: float = -0.1, delayed_cancel: bool = False, cancel_on_filter: bool = True
                 ):
        super().__init__(
            # StrategyWithTradeManagement
            maxPositions = maxPositions, close_on_opposite = close_on_opposite, bars_till_cancel_triggered = bars_till_cancel_triggered,
            limit_entry_offset_perc = limit_entry_offset_perc, delayed_cancel = delayed_cancel, cancel_on_filter = cancel_on_filter)

        # local variables
        self.data_trend_strat = DataTrendStrategy()
        self.ta_trend_strat = TATrendStrategyIndicator(
            timeframe = timeframe, w_ema_period= w_ema_period, d_highs_trail_period = d_highs_trail_period,
            d_lows_trail_period = d_lows_trail_period, trend_d_period = trend_d_period, trend_w_period = trend_w_period,
            atr_period = atr_period, natr_period_slow= natr_period_slow, bbands_period = bbands_period, sl_upper_bb_std_fac = sl_upper_bb_std_fac,
            sl_lower_bb_std_fac = sl_lower_bb_std_fac
        )
        self.plotIndicators = plotIndicators
        # Risk
        self.risk_with_trend = risk_with_trend
        self.risk_counter_trend = risk_counter_trend
        self.risk_ranging = risk_ranging
        # SL entry parameters
        self.be_by_middleband = be_by_middleband
        self.be_by_opposite = be_by_opposite
        self.stop_at_middleband = stop_at_middleband
        self.tp_at_middleband = tp_at_middleband
        self.tp_on_opposite = tp_on_opposite
        self.stop_at_new_entry = stop_at_new_entry
        self.trail_sl_with_bband = trail_sl_with_bband
        self.atr_buffer_fac = atr_buffer_fac
        self.sl_atr_fac = sl_atr_fac
        self.moving_sl_atr_fac = moving_sl_atr_fac
        self.sl_upper_bb_std_fac = sl_upper_bb_std_fac
        self.sl_lower_bb_std_fac = sl_lower_bb_std_fac

    def init(self, bars: List[Bar], account: Account, symbol: Symbol):
        super().init(bars, account, symbol)
        self.logger.info()

    def myId(self):
        return "TrendStrategy"

    def prep_bars(self, is_new_bar: bool, bars: list):
        if is_new_bar:
            self.ta_trend_strat.on_tick(bars)

    def get_ta_data_trend_strategy(self):
        return self.ta_trend_strat.taData_trend_strat

    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_plot(fig, bars, time)

        # get ta data settings
        styles = self.ta_trend_strat.get_line_styles()
        names = self.ta_trend_strat.get_line_names()
        offset = 0

        # plot ta data
        plotTrailsAndEMAs = True
        if plotTrailsAndEMAs and self.plotIndicators:
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

        # plot trend indicator
        plotBackgroundColor4Trend = True #TODO: check for offset
        if plotBackgroundColor4Trend and self.plotIndicators:
            trend = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[3], bars))      # Trend
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

        # ATR
        plotATR = False
        if plotATR and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[5], bars))   # ATR + close
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[5],
                            name=self.ta_trend_strat.id + "_" + names[5])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[6], bars))   # fast NATR
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[6],
                            name=self.ta_trend_strat.id + "_" + names[6])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[7], bars))  # slow NATR
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[7],
                            name=self.ta_trend_strat.id + "_" + names[7])

        # plot Bollinger Bands
        plotBBands = True
        if plotBBands and self.plotIndicators:
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[8], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[8],
                            name=self.ta_trend_strat.id + "_" + names[8])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[9], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[9],
                            name=self.ta_trend_strat.id + "_" + names[9])
            sub_data = list(map(lambda b: self.ta_trend_strat.get_data_for_plot(b)[10], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[10],
                            name=self.ta_trend_strat.id + "_" + names[10])
        # Plot strategy-generated data

    def calc_pos_size(self, risk, entry, exitPrice, atr: float = 0):
        delta = entry - exitPrice
        risk = self.risk_with_trend

        if (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BULL and delta > 0) or \
                (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BEAR and delta < 0):
            risk = self.risk_with_trend
        elif (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BEAR and delta > 0) or \
                (self.ta_trend_strat.taData_trend_strat.marketRegime == MarketRegime.BULL and delta < 0):
            risk = self.risk_counter_trend
        else:
            risk = self.risk_ranging

        if not self.symbol.isInverse:
            size = risk / delta
        else:
            size = -risk / (1 / entry - 1 / (entry - delta))
        size = self.symbol.normalizeSize(size)
        return size

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        super().manage_open_order(order, position, bars, to_update, to_cancel, open_positions)

        stop_at_trail = True
        stop_at_lowerband = False
        # Update SLs based on BBs
        orderType = TradingBot.order_type_from_order_id(order.id)
        if orderType == OrderType.SL:  # Manage Stop Losses
            new_stop_price = order.stop_price
            if new_stop_price is not None and \
                    self.ta_trend_strat.taData_trend_strat.bbands.middleband is not None and \
                    self.ta_trend_strat.taData_trend_strat.bbands.std is not None:
                upper_band = self.ta_trend_strat.taData_trend_strat.bbands.middleband + self.ta_trend_strat.taData_trend_strat.bbands.std * self.sl_upper_bb_std_fac
                lower_band = self.ta_trend_strat.taData_trend_strat.bbands.middleband - self.ta_trend_strat.taData_trend_strat.bbands.std * self.sl_lower_bb_std_fac
                if order.amount > 0:  # SL for SHORTS
                    if bars[1].low < self.ta_trend_strat.taData_trend_strat.bbands.middleband and self.be_by_middleband:
                        new_stop_price = min(position.wanted_entry, new_stop_price)
                    if bars[1].low < (
                            lower_band + self.ta_trend_strat.taData_trend_strat.ATR * self.atr_buffer_fac) and self.be_by_opposite:
                        new_stop_price = min(position.wanted_entry, new_stop_price)
                    if bars[1].low < self.ta_trend_strat.taData_trend_strat.bbands.middleband and self.stop_at_new_entry:
                        new_stop_price = min(upper_band, new_stop_price)
                    stop_short_at_middleband = True
                    if bars[1].low < lower_band and stop_short_at_middleband:
                        new_stop_price = min(self.ta_trend_strat.taData_trend_strat.bbands.middleband - self.ta_trend_strat.taData_trend_strat.ATR,
                                             new_stop_price)
                    if bars[1].low < lower_band and self.tp_on_opposite:
                        new_stop_price = min(bars[0].open, new_stop_price)
                    if bars[0].open < self.ta_trend_strat.taData_trend_strat.bbands.middleband and self.tp_at_middleband:
                        new_stop_price = min(self.ta_trend_strat.taData_trend_strat.bbands.middleband, new_stop_price)
                    if self.trail_sl_with_bband:
                        new_stop_price = min(upper_band, new_stop_price)
                    if bars[1].low + self.ta_trend_strat.taData_trend_strat.ATR * self.moving_sl_atr_fac < new_stop_price:
                        new_stop_price = bars[1].low + self.ta_trend_strat.taData_trend_strat.ATR * self.sl_atr_fac  # TODO moving_sl_atr_fac

                elif order.amount < 0:  # SL for LONGs
                    if stop_at_trail:
                        new_stop_price = max(self.ta_trend_strat.taData_trend_strat.d_lows_trail, new_stop_price)
                    if stop_at_lowerband:
                        new_stop_price = max(lower_band, new_stop_price)
                    if bars[1].high > self.ta_trend_strat.taData_trend_strat.bbands.middleband and self.be_by_middleband:
                        new_stop_price = max(position.wanted_entry, new_stop_price)
                    if bars[1].high > (
                            upper_band - self.ta_trend_strat.taData_trend_strat.ATR * self.atr_buffer_fac) and self.be_by_opposite:
                        new_stop_price = max(position.wanted_entry, new_stop_price)
                    if bars[1].high > self.ta_trend_strat.taData_trend_strat.bbands.middleband and self.stop_at_new_entry:
                        new_stop_price = max(lower_band, new_stop_price)
                    if bars[1].high > (
                            upper_band - self.ta_trend_strat.taData_trend_strat.ATR * self.atr_buffer_fac) and self.stop_at_middleband:
                        new_stop_price = max(self.ta_trend_strat.taData_trend_strat.bbands.middleband, new_stop_price)
                    if bars[1].high > upper_band and self.tp_on_opposite:
                        new_stop_price = max(bars[0].open, new_stop_price)
                    if bars[0].open > self.ta_trend_strat.taData_trend_strat.bbands.middleband and self.tp_at_middleband:
                        new_stop_price = max(self.ta_trend_strat.taData_trend_strat.bbands.middleband, new_stop_price)
                    if self.trail_sl_with_bband:
                        new_stop_price = max(lower_band, new_stop_price)

                if new_stop_price != order.stop_price:
                    order.stop_price = new_stop_price
                    to_update.append(order)


class BBands:
    def __init__(self, middleband:float = None, std:float = None):
        self.middleband = middleband
        self.std = std


class TAdataTrendStrategy:
    def __init__(self):
        ''' TA- / Indicator-data of the Trend Strategy '''
        self.talibbars = talibbars = TAlibBars()
        self.w_ema = None
        self.w_ema_vec = None
        self.d_highs_trail_vec = None
        self.d_lows_trail_vec = None
        self.d_highs_trail = None
        self.d_mid_trail = None
        self.d_lows_trail = None
        self.marketRegime = MarketRegime.NONE
        self.ATR_vec = None
        self.ATR = None
        self.NATR_vec = None
        self.NATR = None
        self.NATR_slow_vec = None
        self.NATR_slow = None
        self.bbands = BBands(None, None)


class TATrendStrategyIndicator(Indicator):
    ''' Run technical analysis here and store data in TAdataTrendStrategy '''

    def __init__(self,
                 timeframe: int = 240,
                 w_ema_period: int = 10,
                 d_highs_trail_period: int = 10,
                 d_lows_trail_period: int = 10,
                 trend_d_period: int = 2,
                 trend_w_period: int = 0,
                 atr_period: int = 10,
                 natr_period_slow: int = 10,
                 bbands_period: int = 10,
                 sl_upper_bb_std_fac: float = 2.0,
                 sl_lower_bb_std_fac: float = 2.0):
        super().__init__('TAtrend')
        # local data
        self.taData_trend_strat = TAdataTrendStrategy()
        self.ranging_buffer = 0
        self.bear_buffer = 0
        self.bullish_reversal = False
        # Input parameters
        self.bars_per_week = int(60*24*7 / timeframe)
        self.bars_per_day = int(60*24 / timeframe)
        self.trend_d_period = trend_d_period
        self.trend_w_period = trend_w_period
        self.w_ema_period = w_ema_period
        self.highs_trail_period = d_highs_trail_period
        self.lows_trail_period = d_lows_trail_period
        self.atr_period = atr_period
        self.natr_period_slow = natr_period_slow
        self.bbands_period = bbands_period
        self.sl_upper_bb_std_fac = sl_upper_bb_std_fac
        self.sl_lower_bb_std_fac = sl_lower_bb_std_fac

    def on_tick(self, bars: List[Bar]):
        self.taData_trend_strat.talibbars.on_tick(bars)
        self.run_ta_analysis()
        self.identify_trend()
        self.write_data_for_plot(bars)

    def get_ta_data(self):
        return self.taData_trend_strat

    def run_ta_analysis(self):
        # W-EMA
        temp_w_ema = talib.EMA(self.taData_trend_strat.talibbars.close, self.w_ema_period * self.bars_per_week)
        w_ema_vec = []
        for value in temp_w_ema:
            if not np.isnan(value):
                w_ema_vec.append(value)
        self.taData_trend_strat.w_ema_vec = w_ema_vec
        if self.taData_trend_strat.w_ema_vec is not None and len(self.taData_trend_strat.w_ema_vec)>0:
            if self.taData_trend_strat.w_ema_vec[-1] is not None:
                self.taData_trend_strat.w_ema = self.taData_trend_strat.w_ema_vec[-1]
            else:
                self.taData_trend_strat.w_ema = None

        # Trails
        temp_d_highs = talib.MAX(self.taData_trend_strat.talibbars.high, self.highs_trail_period * self.bars_per_day)
        temp_d_lows = talib.MIN(self.taData_trend_strat.talibbars.low, self.lows_trail_period * self.bars_per_day)
        d_highs_vec = []
        d_lows_vec = []
        for value_high, value_low in zip(temp_d_highs, temp_d_lows):
            if not np.isnan(value_high):
                d_highs_vec.append(value_high)
            if not np.isnan(value_low):
                d_lows_vec.append(value_low)
        self.taData_trend_strat.d_highs_trail_vec = d_highs_vec
        self.taData_trend_strat.d_lows_trail_vec = d_lows_vec

        if self.taData_trend_strat.d_highs_trail_vec is not None and len(self.taData_trend_strat.d_highs_trail_vec)>0:
            if self.taData_trend_strat.d_highs_trail_vec[-1] is not None:
                self.taData_trend_strat.d_highs_trail = self.taData_trend_strat.d_highs_trail_vec[-1]
            else:
                self.taData_trend_strat.d_highs_trail = None

        if self.taData_trend_strat.d_lows_trail_vec is not None and len(self.taData_trend_strat.d_lows_trail_vec)>0:
            if self.taData_trend_strat.d_lows_trail_vec[-1] is not None:
                self.taData_trend_strat.d_lows_trail = self.taData_trend_strat.d_lows_trail_vec[-1]
            else:
                self.taData_trend_strat.d_lows_trail = None

        if self.taData_trend_strat.d_lows_trail is not None and self.taData_trend_strat.d_highs_trail is not None:
            self.taData_trend_strat.d_mid_trail = (self.taData_trend_strat.d_highs_trail + self.taData_trend_strat.d_lows_trail) / 2
        else:
            self.taData_trend_strat.d_mid_trail = None

        # ATR & NATR
        self.taData_trend_strat.ATR_vec = talib.ATR(self.taData_trend_strat.talibbars.high, self.taData_trend_strat.talibbars.low,
                                                    self.taData_trend_strat.talibbars.close, self.atr_period)
        self.taData_trend_strat.ATR = self.taData_trend_strat.ATR_vec[-1] if not np.isnan(self.taData_trend_strat.ATR_vec[-1]) else None
        self.taData_trend_strat.NATR_vec = talib.NATR(self.taData_trend_strat.talibbars.high, self.taData_trend_strat.talibbars.low,
                                                      self.taData_trend_strat.talibbars.close, self.atr_period)
        self.taData_trend_strat.NATR = self.taData_trend_strat.NATR_vec[-1] if not np.isnan(self.taData_trend_strat.NATR_vec[-1]) else None
        self.taData_trend_strat.NATR_slow_vec = talib.NATR(self.taData_trend_strat.talibbars.high, self.taData_trend_strat.talibbars.low,
                                                           self.taData_trend_strat.talibbars.close, self.natr_period_slow)
        self.taData_trend_strat.NATR_slow = self.taData_trend_strat.NATR_slow_vec[-1] if not np.isnan(self.taData_trend_strat.NATR_slow_vec[-1]) else None

        # Bollinger Bands
        a, b, c = talib.BBANDS(self.taData_trend_strat.talibbars.close, timeperiod=self.bbands_period, nbdevup = 1, nbdevdn = 1)
        upperband = a[-1] if not math.isnan(a[-1]) else None
        self.taData_trend_strat.bbands.middleband = b[-1] if not math.isnan(b[-1]) else None
        if upperband is not None:
            self.taData_trend_strat.bbands.std = upperband - self.taData_trend_strat.bbands.middleband
        else:
            self.taData_trend_strat.bbands.std = None

    def identify_trend(self):
        # Trend based on W-EMA and trails
        if self.taData_trend_strat.w_ema is not None:
            if (self.taData_trend_strat.talibbars.low[-1] < self.taData_trend_strat.d_lows_trail_vec[-2] or \
                    self.taData_trend_strat.talibbars.low[-1] < self.taData_trend_strat.w_ema):# and \
                self.taData_trend_strat.marketRegime = MarketRegime.BEAR

                nmb_required_candles_w = self.trend_w_period * self.bars_per_week
                nmb_required_candles_d = self.trend_d_period * self.bars_per_day
                self.bear_buffer = max(nmb_required_candles_w, nmb_required_candles_d)
                self.ranging_buffer = 0
            elif self.taData_trend_strat.talibbars.close[-1] > self.taData_trend_strat.d_highs_trail_vec[-2] or \
                    self.taData_trend_strat.talibbars.close[-1] > self.taData_trend_strat.w_ema:
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

        atr_close = self.taData_trend_strat.talibbars.close[-1] + self.taData_trend_strat.ATR if self.taData_trend_strat.ATR is not None else self.taData_trend_strat.talibbars.close[-1]
        if self.taData_trend_strat.bbands.middleband is not None:
            upper_band = self.taData_trend_strat.bbands.middleband + self.taData_trend_strat.bbands.std * self.sl_upper_bb_std_fac
            lower_band = self.taData_trend_strat.bbands.middleband - self.taData_trend_strat.bbands.std * self.sl_lower_bb_std_fac
        else:
            upper_band = None
            lower_band = None

        plot_data = [self.taData_trend_strat.w_ema,
                     self.taData_trend_strat.d_highs_trail,
                     self.taData_trend_strat.d_lows_trail,
                     trend,
                     self.taData_trend_strat.d_mid_trail,
                     atr_close,
                     self.taData_trend_strat.NATR,
                     self.taData_trend_strat.NATR_slow,
                     upper_band,
                     self.taData_trend_strat.bbands.middleband,
                     lower_band
                    ]
        self.write_data(bars[0], plot_data)  # [0] because we only know about it after the candle is closed and processed

    def get_line_names(self):
        return ["%1.fW-EMA" % self.w_ema_period,
                "%1.fD-High" % self.highs_trail_period,
                "%1.fD-Low" % self.lows_trail_period,
                "Market Trend",
                "MidTrail",
                "1ATR+Close",
                "1NATR",
                "1slowNATR",
                "%.1fSTD_upperband" % self.sl_upper_bb_std_fac,         # Bollinger Bands
                "middleband",                                           # Bollinger Bands
                "%.1fSTD_lowerband" % self.sl_lower_bb_std_fac          # Bollinger Bands
                ]

    def get_number_of_lines(self):
        return 11

    def get_line_styles(self):
        return [
            {"width": 1, "color": "black"},                         # W-EMA
            {"width": 1, "color": "green"},                         # D-High
            {"width": 1, "color": "red"},                           # D-Low
            {"width": 1, "color": "black"},                         # Trend
            {"width": 1, "color": "blue", "dash": "dot"},           # Mid-Trail
            {"width": 1, "color": "purple", "dash": "dot"},         # ATR+Close
            {"width": 1, "color": "black"},                         # NATR
            {"width": 1, "color": "blue"},                          # slowNATR
            {"width": 1, "color": "dodgerblue"},                    # BBands
            {"width": 1, "color": "dodgerblue", "dash": "dot"},     # BBands
            {"width": 1, "color": "dodgerblue"}                     # BBands
               ]

    def get_data_for_plot(self, bar: Bar):
        plot_data = self.get_data(bar)
        if plot_data is not None:
            return plot_data
        else:
            return [bar.close, bar.close, bar.close, bar.close, bar.close, bar.close, bar.close, bar.close,
                    bar.close, bar.close, bar.close                 # Bollinger Bands
             ]
