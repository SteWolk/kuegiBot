from typing import List

import numpy as np
import talib

from kuegi_bot.bots.strategies.trend_enums import MarketDynamic, MarketRegime
from kuegi_bot.indicators.indicator import Indicator
from kuegi_bot.indicators.talibbars import TAlibBars
from kuegi_bot.utils.trading_classes import Bar


class BBands:
    def __init__(self, middleband: float = None, middleband_vec=[], std: float = None, std_vec=[]):
        self.middleband = middleband
        self.middleband_vec = middleband_vec
        self.std = std
        self.std_vec = std_vec


class TAdataTrendStrategy:
    def __init__(self):
        """TA-data of the Trend Strategy."""
        self.talibbars = TAlibBars()
        self.marketRegime = MarketRegime.NONE
        self.marketDynamic = MarketDynamic.NONE
        # 4h arrays
        self.bbands_4h = BBands(None, [], None, [])
        # self.bbands_talib = Talib_BBANDS(None, None, None)
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
        # self.rsi_d_vec = None
        self.rsi_d = None
        # weekly arrays
        # self.ema_w_vec = None
        self.ema_w = None
        # self.rsi_w_vec = None
        self.rsi_w = None
        # index of last bar
        self.last_4h_index = -1
        self.is_initialized = False


class TATrendStrategyIndicator(Indicator):
    """Run technical analysis calculations here and store data in TAdataTrendStrategy."""

    def __init__(
        self,
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
        trend_var_1: float = 0,
        indicator_id_suffix: str = "",
    ):
        suffix = indicator_id_suffix if indicator_id_suffix is not None else ""
        super().__init__("TAtrend" + suffix)
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
        self.max_4h_period = max(
            self.bbands_4h_period,
            self.atr_4h_period,
            self.natr_4h_period_slow,
            self.rsi_4h_period,
            self.highs_trail_4h_period,
            self.lows_trail_4h_period,
            self.volume_sma_4h_period,
            self.max_d_period * 6,
            (self.max_w_period + 2) * 7 * 6,
        )
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
        # self.taData_trend_strat.rsi_d_vec = np.full(self.max_d_period, np.nan)
        # Weekly arrays
        # self.taData_trend_strat.ema_w_vec = np.full(self.max_w_period, np.nan)
        # self.taData_trend_strat.rsi_w_vec = np.full(self.max_w_period, np.nan)

        # weekly:
        ema_w_vec = talib.EMA(
            self.taData_trend_strat.talibbars.close_weekly[-self.max_w_period :], timeperiod=self.ema_w_period
        )
        self.taData_trend_strat.ema_w = ema_w_vec[-1]

        # Set the initialized flag to True
        self.taData_trend_strat.is_initialized = True

    def update_4h_values(self):
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close
        high = talibbars.high
        low = talibbars.low
        volume = talibbars.volume

        if close is None or len(close) < self.max_4h_period + 1:
            return

        # Trails
        self.taData_trend_strat.highs_trail_4h_vec = talib.MAX(high[-self.max_4h_period :], self.highs_trail_4h_period)
        self.taData_trend_strat.lows_trail_4h_vec = talib.MIN(low[-self.max_4h_period :], self.lows_trail_4h_period)
        self.taData_trend_strat.highs_trail_4h = self.taData_trend_strat.highs_trail_4h_vec[-1]
        self.taData_trend_strat.lows_trail_4h = self.taData_trend_strat.lows_trail_4h_vec[-1]
        if (
            self.taData_trend_strat.highs_trail_4h is not None
            and self.taData_trend_strat.lows_trail_4h is not None
            and self.taData_trend_strat.lows_trail_4h != 0
        ):
            self.taData_trend_strat.mid_trail_4h = (
                0.5 * (self.taData_trend_strat.highs_trail_4h - self.taData_trend_strat.lows_trail_4h)
                + self.taData_trend_strat.lows_trail_4h
            )

        # Update Bollinger Bands arrays
        a, b, _c = talib.BBANDS(
            close[-self.max_4h_period - 1 :],
            timeperiod=self.bbands_4h_period,
            nbdevup=1,
            nbdevdn=1,
        )
        upperband = a[-1]
        self.taData_trend_strat.bbands_4h.middleband = b[-1]
        if not np.isnan(upperband) and not np.isnan(self.taData_trend_strat.bbands_4h.middleband):
            self.taData_trend_strat.bbands_4h.std = upperband - self.taData_trend_strat.bbands_4h.middleband
        else:
            self.taData_trend_strat.bbands_4h.std = np.nan

        self.taData_trend_strat.bbands_4h.middleband_vec = b
        self.taData_trend_strat.bbands_4h.std_vec = a - b

        # Update atr_4h & natr_4h arrays
        atr_4h_vec = talib.ATR(
            high[-self.max_4h_period - 1 :],
            low[-self.max_4h_period - 1 :],
            close[-self.max_4h_period - 1 :],
            self.atr_4h_period,
        )
        natr_4h_vec = talib.NATR(
            high[-self.max_4h_period - 1 :],
            low[-self.max_4h_period - 1 :],
            close[-self.max_4h_period - 1 :],
            self.atr_4h_period,
        )
        natr_slow_4h_vec = talib.NATR(
            high[-self.max_4h_period - 1 :],
            low[-self.max_4h_period - 1 :],
            close[-self.max_4h_period - 1 :],
            self.natr_4h_period_slow,
        )
        self.taData_trend_strat.atr_4h_vec = atr_4h_vec
        self.taData_trend_strat.natr_4h_vec = natr_4h_vec
        self.taData_trend_strat.natr_slow_4h_vec = natr_slow_4h_vec

        self.taData_trend_strat.atr_4h = atr_4h_vec[-1]
        self.taData_trend_strat.natr_4h = natr_4h_vec[-1]
        self.taData_trend_strat.natr_slow_4h = natr_slow_4h_vec[-1]
        self.taData_trend_strat.natr_trail_mix = (
            (
                self.taData_trend_strat.natr_4h
                + (
                    (self.taData_trend_strat.highs_trail_4h - self.taData_trend_strat.lows_trail_4h)
                    / self.taData_trend_strat.highs_trail_4h
                )
            )
            / 2
        )
        self.taData_trend_strat.atr_trail_mix = (
            self.taData_trend_strat.atr_4h
            + (self.taData_trend_strat.highs_trail_4h - self.taData_trend_strat.lows_trail_4h) / 5
        ) / 2

        # Update RSI for 4H timeframe
        self.taData_trend_strat.rsi_4h_vec = talib.RSI(
            close[-min(self.max_4h_period, 200 + self.rsi_4h_period) :],
            self.rsi_4h_period,
        )

        # Update Volume for 4H timeframe
        self.taData_trend_strat.volume_4h = volume[-1]
        self.taData_trend_strat.volume_sma_4h_vec = talib.MA(
            volume[-self.max_4h_period :], self.volume_sma_4h_period, 0
        )

    def update_daily_values(self):
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close_daily

        if close is None or len(close) < self.max_d_period + 1:
            return

        # Update RSI for daily timeframe
        rsi_daily = talib.RSI(close[-self.rsi_d_period - 1 :], self.rsi_d_period)[-1]
        self.taData_trend_strat.rsi_d = rsi_daily

    def update_weekly_values(self):
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close_weekly

        # Update EMA for weekly timeframe
        if close is None or len(close) < self.max_w_period + 1:
            return
        ema_w = talib.EMA(close[-self.ema_w_period :], timeperiod=self.ema_w_period)[-1]
        self.taData_trend_strat.ema_w = ema_w

        # Update RSI for weekly timeframe
        rsi_w = talib.RSI(close[-self.rsi_w_period - 1 :], timeperiod=self.rsi_w_period)[-1]
        self.taData_trend_strat.rsi_w = rsi_w

    def identify_trend(self):
        high_break = False
        low_break = False
        bull_buffer_length = self.days_buffer_bull * self.bars_per_day
        bear_buffer_length = self.days_buffer_bear * self.bars_per_day

        i = 1
        if self.taData_trend_strat.atr_4h is None:
            return

        delta = self.taData_trend_strat.atr_4h * self.trend_atr_fac
        delta_2 = self.taData_trend_strat.atr_4h * 0.2
        while i < len(self.taData_trend_strat.highs_trail_4h_vec) - 1:
            if self.taData_trend_strat.highs_trail_4h_vec[-i] > self.taData_trend_strat.highs_trail_4h_vec[-i - 1] + delta:
                high_break = True
                break
            if self.taData_trend_strat.lows_trail_4h_vec[-i] < self.taData_trend_strat.lows_trail_4h_vec[-i - 1] - delta_2:
                low_break = True
                break
            i += 1

        if i < bull_buffer_length and high_break:
            self.taData_trend_strat.marketRegime = MarketRegime.BULL
        elif i < bear_buffer_length and low_break:
            self.taData_trend_strat.marketRegime = MarketRegime.BEAR
        else:
            self.taData_trend_strat.marketRegime = MarketRegime.RANGING

        self.identifyMarketDynamics()

    def identifyMarketDynamics(self):
        # Average Directional Movement Index
        self.taData_trend_strat.marketDynamic = MarketDynamic.TRENDING
        talibbars = self.taData_trend_strat.talibbars
        close = talibbars.close
        high = talibbars.high
        low = talibbars.low
        period = 35
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
            upper_band = (
                self.taData_trend_strat.bbands_4h.middleband
                + self.taData_trend_strat.bbands_4h.std * self.sl_upper_bb_4h_std_fac
            )
            lower_band = (
                self.taData_trend_strat.bbands_4h.middleband
                - self.taData_trend_strat.bbands_4h.std * self.sl_lower_bb_4h_std_fac
            )
        else:
            upper_band = None
            lower_band = None

        plot_data = [
            self.taData_trend_strat.ema_w,
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
            self.taData_trend_strat.atr_trail_mix if self.taData_trend_strat.atr_trail_mix is not None else 0,
        ]
        self.write_data(bars[0], plot_data)

    def get_line_names(self):
        return [
            "%1.fW-EMA" % self.ema_w_period,
            "%1.fD-High" % self.highs_trail_4h_period,
            "%1.fD-Low" % self.lows_trail_4h_period,
            "Market Trend",
            "MidTrail",
            "ATR",
            "NATR",
            "slowNATR",
            "%.1fSTD_upperband" % self.sl_upper_bb_4h_std_fac,
            "middleband",
            "%.1fSTD_lowerband" % self.sl_lower_bb_4h_std_fac,
            "4H-RSI",
            "D-RSI",
            "W-RSI",
            "NATR + Trail",
            "ATR + Trail",
        ]

    def get_number_of_lines(self):
        return 16

    def get_line_styles(self):
        return [
            {"width": 1, "color": "black"},
            {"width": 1, "color": "green"},
            {"width": 1, "color": "red"},
            {"width": 1, "color": "black"},
            {"width": 1, "color": "blue", "dash": "dot"},
            {"width": 1, "color": "purple", "dash": "dot"},
            {"width": 1, "color": "black"},
            {"width": 1, "color": "blue"},
            {"width": 1, "color": "dodgerblue"},
            {"width": 1, "color": "dodgerblue", "dash": "dot"},
            {"width": 1, "color": "dodgerblue"},
            {"width": 1, "color": "green"},
            {"width": 1, "color": "blue"},
            {"width": 1, "color": "black"},
            {"width": 1, "color": "orange", "dash": "dot"},
            {"width": 1, "color": "orange"},
        ]

    def get_data_for_plot(self, bar: Bar):
        plot_data = self.get_data(bar)
        if plot_data is not None:
            return plot_data
        return [
            bar.close,
            bar.close,
            bar.close,
            bar.close,
            bar.close,
            0,
            0,
            0,
            bar.close,
            bar.close,
            bar.close,
            0,
            0,
            0,
            0,
            0,
        ]
