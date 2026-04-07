from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import talib

from kuegi_bot.bots.strategies.trend_enums import (
    MarketDynamic,
    MarketRegime,
    OIFundingState,
    OIPriceFlowState,
    oi_funding_state_from_metrics,
    oi_price_flow_state_from_returns,
)
from kuegi_bot.bots.strategies.trend_indicator_engine import TATrendStrategyIndicator
from kuegi_bot.utils.trading_classes import Bar


class TrendIndicatorProvider:
    def __init__(self, ta_indicator: TATrendStrategyIndicator):
        self.ta_indicator = ta_indicator

    def prepare_backtest(self, bars: List[Bar]):
        pass

    def on_new_bar(self, bars: List[Bar]):
        raise NotImplementedError

    def get_ta_data(self):
        return self.ta_indicator.taData_trend_strat


class IncrementalTrendIndicatorProvider(TrendIndicatorProvider):
    def on_new_bar(self, bars: List[Bar]):
        ta_data = self.ta_indicator.taData_trend_strat
        ta_data.talibbars.on_tick(bars)
        self.ta_indicator.on_tick(bars)


class PrecomputedTrendIndicatorProvider(TrendIndicatorProvider):
    def __init__(self, ta_indicator: TATrendStrategyIndicator):
        super().__init__(ta_indicator)
        self._fallback = IncrementalTrendIndicatorProvider(ta_indicator)
        self._ready = False
        self._signature: Optional[Tuple[int, int, int]] = None

        self._index_by_tstamp: Dict[int, int] = {}
        self._timestamps = np.array([], dtype=np.int64)
        self._open = np.array([], dtype=float)
        self._high = np.array([], dtype=float)
        self._low = np.array([], dtype=float)
        self._close = np.array([], dtype=float)
        self._volume = np.array([], dtype=float)

        self._daily_open = np.array([], dtype=float)
        self._daily_high = np.array([], dtype=float)
        self._daily_low = np.array([], dtype=float)
        self._daily_close = np.array([], dtype=float)
        self._daily_close_idx_4h = np.array([], dtype=np.int64)
        self._daily_count_by_4h_idx = np.array([], dtype=np.int64)

        self._weekly_open = np.array([], dtype=float)
        self._weekly_high = np.array([], dtype=float)
        self._weekly_low = np.array([], dtype=float)
        self._weekly_close = np.array([], dtype=float)
        self._weekly_close_idx_4h = np.array([], dtype=np.int64)
        self._weekly_count_by_4h_idx = np.array([], dtype=np.int64)

        self._highs_trail = np.array([], dtype=float)
        self._lows_trail = np.array([], dtype=float)
        self._atr = np.array([], dtype=float)
        self._natr = np.array([], dtype=float)
        self._natr_slow = np.array([], dtype=float)
        self._bb_middle = np.array([], dtype=float)
        self._bb_std = np.array([], dtype=float)
        self._rsi_4h = np.array([], dtype=float)
        self._volume_sma = np.array([], dtype=float)
        self._oi = np.array([], dtype=float)
        self._oi_sma = np.array([], dtype=float)
        self._funding = np.array([], dtype=float)
        self._adx = np.array([], dtype=float)
        self._plus_di = np.array([], dtype=float)
        self._minus_di = np.array([], dtype=float)

        self._rsi_d_by_idx: List[Optional[float]] = []
        self._ema_w_by_idx: List[Optional[float]] = []
        self._rsi_w_by_idx: List[Optional[float]] = []
        self._market_dynamic_by_idx: List[MarketDynamic] = []
        self._market_regime_by_idx: List[MarketRegime] = []

    def prepare_backtest(self, bars: List[Bar]):
        if bars is None or len(bars) < 2:
            self._ready = False
            return
        bar_count = len(bars)
        first_tstamp = int(bars[0].tstamp)
        last_tstamp = int(bars[-1].tstamp)
        signature = (bar_count, first_tstamp, last_tstamp)
        if self._ready and self._signature == signature:
            return
        self._build_precomputed_data(bars)
        self._signature = signature
        self._ready = True

    def on_new_bar(self, bars: List[Bar]):
        if len(bars) < 2:
            return
        if not self._ready:
            self._fallback.on_new_bar(bars)
            return

        idx = self._index_by_tstamp.get(int(bars[1].tstamp))
        if idx is None:
            self._fallback.on_new_bar(bars)
            return

        self._apply_snapshot(idx, bars)

    def _build_precomputed_data(self, bars: List[Bar]):
        chrono = list(reversed(bars))
        timestamps = [int(bar.tstamp) for bar in chrono]
        open_values = [float(bar.open) for bar in chrono]
        high_values = [float(bar.high) for bar in chrono]
        low_values = [float(bar.low) for bar in chrono]
        close_values = [float(bar.close) for bar in chrono]
        volume_values = [float(bar.volume) for bar in chrono]

        self._timestamps = np.array(timestamps, dtype=np.int64)
        self._open = np.array(open_values, dtype=float)
        self._high = np.array(high_values, dtype=float)
        self._low = np.array(low_values, dtype=float)
        self._close = np.array(close_values, dtype=float)
        self._volume = np.array(volume_values, dtype=float)

        self._index_by_tstamp = {int(ts): idx for idx, ts in enumerate(self._timestamps)}

        self._build_daily_and_weekly_candles()
        self._build_indicator_arrays()
        self._build_scalar_timelines()

    def _build_daily_and_weekly_candles(self):
        n = len(self._timestamps)
        daily_start = self._find_daily_start_index(self._timestamps)

        if daily_start is None:
            self._reset_calendar_arrays(n)
            return

        daily_open_idx = np.arange(daily_start, n, 6, dtype=np.int64)
        daily_close_idx = np.arange(daily_start + 5, n, 6, dtype=np.int64)
        complete_daily = min(len(daily_open_idx), len(daily_close_idx))
        daily_open_idx = daily_open_idx[:complete_daily]
        daily_close_idx = daily_close_idx[:complete_daily]

        self._daily_open = self._open[daily_open_idx]
        self._daily_close = self._close[daily_close_idx]
        self._daily_high = np.array([np.max(self._high[idx : idx + 6]) for idx in daily_open_idx], dtype=float)
        self._daily_low = np.array([np.min(self._low[idx : idx + 6]) for idx in daily_open_idx], dtype=float)
        self._daily_close_idx_4h = daily_close_idx
        self._daily_count_by_4h_idx = np.searchsorted(
            self._daily_close_idx_4h,
            np.arange(n, dtype=np.int64),
            side="right",
        )

        if len(daily_open_idx) == 0:
            self._reset_weekly_arrays(n)
            return

        daily_open_timestamps = self._timestamps[daily_open_idx]
        weekly_start_daily_idx = self._find_weekly_start_index(daily_open_timestamps)
        if weekly_start_daily_idx is None:
            self._reset_weekly_arrays(n)
            return

        weekly_open_daily_idx = np.arange(weekly_start_daily_idx, len(self._daily_open), 7, dtype=np.int64)
        weekly_close_daily_idx = np.arange(weekly_start_daily_idx + 6, len(self._daily_close), 7, dtype=np.int64)
        complete_weekly = min(len(weekly_open_daily_idx), len(weekly_close_daily_idx))
        weekly_open_daily_idx = weekly_open_daily_idx[:complete_weekly]
        weekly_close_daily_idx = weekly_close_daily_idx[:complete_weekly]

        self._weekly_open = self._daily_open[weekly_open_daily_idx]
        self._weekly_close = self._daily_close[weekly_close_daily_idx]
        self._weekly_high = np.array(
            [np.max(self._daily_high[idx : idx + 7]) for idx in weekly_open_daily_idx],
            dtype=float,
        )
        self._weekly_low = np.array(
            [np.min(self._daily_low[idx : idx + 7]) for idx in weekly_open_daily_idx],
            dtype=float,
        )
        self._weekly_close_idx_4h = self._daily_close_idx_4h[weekly_close_daily_idx]
        self._weekly_count_by_4h_idx = np.searchsorted(
            self._weekly_close_idx_4h,
            np.arange(n, dtype=np.int64),
            side="right",
        )

    def _build_indicator_arrays(self):
        indicator = self.ta_indicator
        self._highs_trail = talib.MAX(self._high, indicator.highs_trail_4h_period)
        self._lows_trail = talib.MIN(self._low, indicator.lows_trail_4h_period)
        self._atr = talib.ATR(self._high, self._low, self._close, indicator.atr_4h_period)
        self._natr = talib.NATR(self._high, self._low, self._close, indicator.atr_4h_period)
        self._natr_slow = talib.NATR(self._high, self._low, self._close, indicator.natr_4h_period_slow)
        bb_upper, bb_middle, _bb_lower = talib.BBANDS(
            self._close,
            timeperiod=indicator.bbands_4h_period,
            nbdevup=1,
            nbdevdn=1,
        )
        self._bb_middle = bb_middle
        self._bb_std = bb_upper - bb_middle
        self._rsi_4h = talib.RSI(self._close, indicator.rsi_4h_period)
        self._volume_sma = talib.MA(self._volume, indicator.volume_sma_4h_period, 0)
        self._oi = indicator.lookup_open_interest(self._timestamps)
        self._oi_sma = talib.MA(self._oi, indicator.oi_4h_sma_period, 0)
        self._funding = indicator.lookup_funding(self._timestamps)
        self._adx = talib.ADX(self._high, self._low, self._close, 35)
        self._plus_di = talib.PLUS_DI(self._high, self._low, self._close, 35)
        self._minus_di = talib.MINUS_DI(self._high, self._low, self._close, 35)

    def _build_scalar_timelines(self):
        n = len(self._close)
        indicator = self.ta_indicator

        self._rsi_d_by_idx = [None] * n
        self._ema_w_by_idx = [None] * n
        self._rsi_w_by_idx = [None] * n
        self._market_dynamic_by_idx = [MarketDynamic.NONE] * n
        self._market_regime_by_idx = [MarketRegime.NONE] * n

        bull_buffer_len = indicator.days_buffer_bull * indicator.bars_per_day
        bear_buffer_len = indicator.days_buffer_bear * indicator.bars_per_day

        for idx in range(n):
            adx_value = self._adx[idx]
            if np.isnan(adx_value):
                self._market_dynamic_by_idx[idx] = MarketDynamic.NONE
            elif adx_value > 20:
                self._market_dynamic_by_idx[idx] = MarketDynamic.TRENDING
            else:
                self._market_dynamic_by_idx[idx] = MarketDynamic.RANGING

            daily_count = self._prefix_count(self._daily_count_by_4h_idx, idx)
            if daily_count >= indicator.max_d_period + 1:
                daily_close = self._daily_close[:daily_count]
                self._rsi_d_by_idx[idx] = talib.RSI(
                    daily_close[-indicator.rsi_d_period - 1 :],
                    indicator.rsi_d_period,
                )[-1]

            weekly_count = self._prefix_count(self._weekly_count_by_4h_idx, idx)
            if weekly_count >= indicator.max_w_period + 1:
                weekly_close = self._weekly_close[:weekly_count]
                self._ema_w_by_idx[idx] = talib.EMA(
                    weekly_close[-indicator.ema_w_period :],
                    timeperiod=indicator.ema_w_period,
                )[-1]
                self._rsi_w_by_idx[idx] = talib.RSI(
                    weekly_close[-indicator.rsi_w_period - 1 :],
                    timeperiod=indicator.rsi_w_period,
                )[-1]

            atr_value = self._atr[idx]
            if atr_value is None:
                self._market_regime_by_idx[idx] = MarketRegime.NONE
                continue

            p = idx + 1
            start_4h = max(0, p - indicator.max_4h_period)
            highs_window = self._highs_trail[start_4h:p]
            lows_window = self._lows_trail[start_4h:p]

            high_break = False
            low_break = False
            delta = atr_value * indicator.trend_atr_fac
            delta_2 = atr_value * 0.2

            i = 1
            while i < len(highs_window) - 1:
                if highs_window[-i] > highs_window[-(i + 1)] + delta:
                    high_break = True
                    break
                if lows_window[-i] < lows_window[-(i + 1)] - delta_2:
                    low_break = True
                    break
                i += 1

            if i < bull_buffer_len and high_break:
                self._market_regime_by_idx[idx] = MarketRegime.BULL
            elif i < bear_buffer_len and low_break:
                self._market_regime_by_idx[idx] = MarketRegime.BEAR
            else:
                self._market_regime_by_idx[idx] = MarketRegime.RANGING

    def _apply_snapshot(self, idx: int, bars: List[Bar]):
        indicator = self.ta_indicator
        ta_data = indicator.taData_trend_strat
        talibbars = ta_data.talibbars

        p = idx + 1
        start_4h = max(0, p - indicator.max_4h_period)
        start_bb = max(0, p - indicator.max_4h_period - 1)
        start_rsi = max(0, p - min(indicator.max_4h_period, 200 + indicator.rsi_4h_period))

        talibbars.close = self._close[:p]
        talibbars.high = self._high[:p]
        talibbars.low = self._low[:p]
        talibbars.open = self._open[:p]
        talibbars.volume = self._volume[:p]
        talibbars.timestamps = self._timestamps[:p]

        daily_count = self._prefix_count(self._daily_count_by_4h_idx, idx)
        self._write_daily_snapshot(talibbars, daily_count)

        weekly_count = self._prefix_count(self._weekly_count_by_4h_idx, idx)
        self._write_weekly_snapshot(talibbars, weekly_count)

        highs_trail_4h = self._highs_trail[idx]
        lows_trail_4h = self._lows_trail[idx]
        mid_trail_4h = None
        if highs_trail_4h is not None and lows_trail_4h is not None and lows_trail_4h != 0:
            mid_trail_4h = 0.5 * (highs_trail_4h - lows_trail_4h) + lows_trail_4h

        atr_4h = self._atr[idx]
        natr_4h = self._natr[idx]
        natr_slow_4h = self._natr_slow[idx]

        trail_span = highs_trail_4h - lows_trail_4h
        trail_pct_of_high = trail_span / highs_trail_4h
        trail_atr_proxy = trail_span / 5
        natr_trail_mix = (natr_4h + trail_pct_of_high) / 2
        atr_trail_mix = (atr_4h + trail_atr_proxy) / 2

        ta_data.highs_trail_4h_vec = self._highs_trail[start_4h:p]
        ta_data.lows_trail_4h_vec = self._lows_trail[start_4h:p]
        ta_data.atr_4h_vec = self._atr[start_4h:p]
        ta_data.natr_4h_vec = self._natr[start_4h:p]
        ta_data.natr_slow_4h_vec = self._natr_slow[start_4h:p]
        ta_data.rsi_4h_vec = self._rsi_4h[start_rsi:p]
        ta_data.volume_sma_4h_vec = self._volume_sma[start_4h:p]

        ta_data.highs_trail_4h = highs_trail_4h
        ta_data.lows_trail_4h = lows_trail_4h
        ta_data.mid_trail_4h = mid_trail_4h
        ta_data.atr_4h = atr_4h
        ta_data.natr_4h = natr_4h
        ta_data.natr_slow_4h = natr_slow_4h
        ta_data.natr_trail_mix = natr_trail_mix
        ta_data.atr_trail_mix = atr_trail_mix
        ta_data.volume_4h = self._volume[idx]
        ta_data.adx_4h_vec = self._adx[start_4h:p]
        ta_data.plus_di_4h_vec = self._plus_di[start_4h:p]
        ta_data.minus_di_4h_vec = self._minus_di[start_4h:p]
        ta_data.oi_4h_vec = self._oi[start_4h:p]
        ta_data.oi_sma_4h_vec = self._oi_sma[start_4h:p]
        ta_data.funding_4h_vec = self._funding[start_4h:p]
        ta_data.oi_4h = self._oi[idx]
        ta_data.oi_sma_4h = self._oi_sma[idx]
        ta_data.funding_4h = self._funding[idx]
        if (
            np.isfinite(ta_data.oi_4h)
            and np.isfinite(ta_data.oi_sma_4h)
            and abs(ta_data.oi_sma_4h) > 1e-12
        ):
            ta_data.oi_ratio_4h = ta_data.oi_4h / ta_data.oi_sma_4h
        else:
            ta_data.oi_ratio_4h = np.nan

        lookback = max(1, int(getattr(indicator, "oi_flow_lookback_bars", 1)))
        price_ret = np.nan
        oi_ret = np.nan
        if idx >= lookback:
            prev_close = float(self._close[idx - lookback])
            curr_close = float(self._close[idx])
            if np.isfinite(prev_close) and np.isfinite(curr_close) and abs(prev_close) > 1e-12:
                price_ret = ((curr_close - prev_close) / abs(prev_close)) * 100.0

            prev_oi = float(self._oi[idx - lookback])
            curr_oi = float(self._oi[idx])
            if np.isfinite(prev_oi) and np.isfinite(curr_oi) and abs(prev_oi) > 1e-12:
                oi_ret = ((curr_oi - prev_oi) / abs(prev_oi)) * 100.0

        ta_data.price_ret_pct_4h = price_ret
        ta_data.oi_ret_pct_4h = oi_ret
        if np.isfinite(price_ret) and np.isfinite(oi_ret):
            ta_data.oi_price_flow_state = oi_price_flow_state_from_returns(
                price_ret_pct=float(price_ret),
                oi_ret_pct=float(oi_ret),
                price_min_pct=float(getattr(indicator, "oi_flow_price_min_pct", 0.0)),
                oi_min_pct=float(getattr(indicator, "oi_flow_oi_min_pct", 0.0)),
            )
        else:
            ta_data.oi_price_flow_state = OIPriceFlowState.NEUTRAL

        funding_now = np.nan
        if np.isfinite(ta_data.funding_4h):
            funding_now = float(ta_data.funding_4h)
        oi_funding_lookback = max(1, int(getattr(indicator, "oi_funding_lookback_bars", 1)))
        oi_ret_for_funding = np.nan
        if idx >= oi_funding_lookback:
            prev_oi = float(self._oi[idx - oi_funding_lookback])
            curr_oi = float(self._oi[idx])
            if np.isfinite(prev_oi) and np.isfinite(curr_oi) and abs(prev_oi) > 1e-12:
                oi_ret_for_funding = ((curr_oi - prev_oi) / abs(prev_oi)) * 100.0
        if np.isfinite(oi_ret_for_funding) and np.isfinite(funding_now):
            ta_data.oi_funding_state = oi_funding_state_from_metrics(
                oi_ret_pct=float(oi_ret_for_funding),
                funding_rate=float(funding_now),
                oi_up_min_pct=float(getattr(indicator, "oi_funding_oi_up_min_pct", 0.0)),
                oi_down_min_pct=float(getattr(indicator, "oi_funding_oi_down_min_pct", 0.0)),
                funding_pos_min=float(getattr(indicator, "oi_funding_pos_min", 0.0)),
                funding_neg_min=float(getattr(indicator, "oi_funding_neg_min", 0.0)),
            )
        else:
            ta_data.oi_funding_state = OIFundingState.NEUTRAL
        ta_data.adx_4h = self._adx[idx]
        ta_data.plus_di_4h = self._plus_di[idx]
        ta_data.minus_di_4h = self._minus_di[idx]
        ta_data.adx_4h_slope = self._safe_slope(self._adx, idx)

        ta_data.bbands_4h.middleband_vec = self._bb_middle[start_bb:p]
        ta_data.bbands_4h.std_vec = self._bb_std[start_bb:p]
        ta_data.bbands_4h.middleband = self._bb_middle[idx]
        ta_data.bbands_4h.std = self._bb_std[idx]

        ta_data.rsi_d = self._rsi_d_by_idx[idx]
        ta_data.ema_w = self._ema_w_by_idx[idx]
        ta_data.rsi_w = self._rsi_w_by_idx[idx]

        ta_data.marketDynamic = self._market_dynamic_by_idx[idx]
        ta_data.marketRegime = self._market_regime_by_idx[idx]
        ta_data.last_4h_index = idx
        ta_data.is_initialized = True

        self.ta_indicator.write_data_for_plot(bars)

    @staticmethod
    def _find_daily_start_index(timestamps: np.ndarray) -> Optional[int]:
        for idx, ts in enumerate(timestamps):
            if datetime.utcfromtimestamp(int(ts)).hour == 0:
                return idx
        return None

    @staticmethod
    def _find_weekly_start_index(daily_open_timestamps: np.ndarray) -> Optional[int]:
        for idx, ts in enumerate(daily_open_timestamps):
            if datetime.utcfromtimestamp(int(ts)).weekday() == 0:
                return idx
        return None

    def _reset_weekly_arrays(self, n: int):
        self._weekly_open = np.array([], dtype=float)
        self._weekly_high = np.array([], dtype=float)
        self._weekly_low = np.array([], dtype=float)
        self._weekly_close = np.array([], dtype=float)
        self._weekly_close_idx_4h = np.array([], dtype=np.int64)
        self._weekly_count_by_4h_idx = np.zeros(n, dtype=np.int64)

    def _reset_calendar_arrays(self, n: int):
        self._daily_open = np.array([], dtype=float)
        self._daily_high = np.array([], dtype=float)
        self._daily_low = np.array([], dtype=float)
        self._daily_close = np.array([], dtype=float)
        self._daily_close_idx_4h = np.array([], dtype=np.int64)
        self._daily_count_by_4h_idx = np.zeros(n, dtype=np.int64)
        self._reset_weekly_arrays(n)

    @staticmethod
    def _prefix_count(counts: np.ndarray, idx: int) -> int:
        if len(counts) == 0:
            return 0
        return int(counts[idx])

    @staticmethod
    def _safe_slope(values: np.ndarray, idx: int) -> float:
        if idx <= 0 or len(values) <= idx:
            return np.nan
        curr = values[idx]
        prev = values[idx - 1]
        if np.isnan(curr) or np.isnan(prev):
            return np.nan
        return curr - prev

    def _write_daily_snapshot(self, talibbars, daily_count: int):
        if daily_count > 0:
            talibbars.open_daily = self._daily_open[:daily_count]
            talibbars.high_daily = self._daily_high[:daily_count]
            talibbars.low_daily = self._daily_low[:daily_count]
            talibbars.close_daily = self._daily_close[:daily_count]
            return
        talibbars.open_daily = None
        talibbars.high_daily = None
        talibbars.low_daily = None
        talibbars.close_daily = None

    def _write_weekly_snapshot(self, talibbars, weekly_count: int):
        if weekly_count > 0:
            talibbars.open_weekly = self._weekly_open[:weekly_count]
            talibbars.high_weekly = self._weekly_high[:weekly_count]
            talibbars.low_weekly = self._weekly_low[:weekly_count]
            talibbars.close_weekly = self._weekly_close[:weekly_count]
            return
        talibbars.open_weekly = None
        talibbars.high_weekly = None
        talibbars.low_weekly = None
        talibbars.close_weekly = None


def build_trend_indicator_provider(ta_indicator: TATrendStrategyIndicator, mode: str) -> TrendIndicatorProvider:
    normalized_mode = (mode or "incremental").strip().lower()
    if normalized_mode == "precomputed":
        return PrecomputedTrendIndicatorProvider(ta_indicator)
    return IncrementalTrendIndicatorProvider(ta_indicator)
