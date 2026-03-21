from typing import List
import plotly.graph_objects as go

from kuegi_bot.bots.strategies.strat_w_trade_man import StrategyWithTradeManagement
from kuegi_bot.bots.strategies.trend_enums import MarketDynamic, MarketRegime
from kuegi_bot.bots.strategies.trend_indicator_engine import (
    BBands,
    TAdataTrendStrategy,
    TATrendStrategyIndicator,
)
from kuegi_bot.bots.strategies.trend_sl_rules import apply_trend_sl_rules
from kuegi_bot.utils.trading_classes import Bar, Account, Symbol, OrderType, Order, PositionStatus, Position
from kuegi_bot.bots.trading_bot import TradingBot


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
                 trend_indicator_id_suffix: str = "",
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
            rsi_4h_period = rsi_4h_period, rsi_d_period = 14, volume_sma_4h_period= volume_sma_4h_period, trend_atr_fac = trend_atr_fac,
            indicator_id_suffix=trend_indicator_id_suffix
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
        # new bar detection
        self._last_bar_tstamp = None

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
        # determine new bar by timestamp
        current_t = bars[0].tstamp
        is_new_bar = (current_t != self._last_bar_tstamp)
        if is_new_bar:
            self._last_bar_tstamp = current_t
            self.logger.info(
                f"[TrendStrategy] is_new_bar=True at t={bars[0].tstamp}, "
                f"open={bars[0].open}, close={bars[0].close}"
            )

        if is_new_bar:
            # Update SLs based on BBs
            orderType = TradingBot.order_type_from_order_id(order.id)
            if orderType == OrderType.SL:  # Manage Stop Losses
                new_trigger_price = apply_trend_sl_rules(
                    strategy=self,
                    order=order,
                    position=position,
                    bars=bars,
                )

                if new_trigger_price != order.trigger_price:
                    order.trigger_price = new_trigger_price
                    to_update.append(order)


