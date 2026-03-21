def apply_trend_sl_rules(strategy, order, position, bars):
    """
    Non-functional extraction of TrendStrategy SL update rules.

    Returns the potentially updated trigger price.
    """
    new_trigger_price = order.trigger_price
    ta = strategy.ta_trend_strat.taData_trend_strat

    if (
        new_trigger_price is not None
        and ta.bbands_4h.middleband is not None
        and ta.bbands_4h.std is not None
    ):
        upper_band = ta.bbands_4h.middleband + ta.bbands_4h.std * strategy.sl_upper_bb_std_fac
        lower_band = ta.bbands_4h.middleband - ta.bbands_4h.std * strategy.sl_lower_bb_std_fac
        if order.amount > 0:  # SL for SHORTS
            if strategy.be_by_middleband and bars[1].low < ta.bbands_4h.middleband:
                new_trigger_price = min(position.wanted_entry, new_trigger_price)
            if strategy.be_by_opposite and bars[1].low < (lower_band + ta.atr_4h * strategy.atr_buffer_fac):
                new_trigger_price = min(position.wanted_entry, new_trigger_price)
            if strategy.stop_at_new_entry and bars[1].low < ta.bbands_4h.middleband:
                new_trigger_price = min(upper_band, new_trigger_price)
            if strategy.stop_short_at_middleband and bars[1].low < lower_band:
                new_trigger_price = min(ta.bbands_4h.middleband - ta.atr_4h, new_trigger_price)
            if strategy.tp_on_opposite and bars[1].low < lower_band:
                new_trigger_price = min(bars[0].open, new_trigger_price)
            if strategy.tp_at_middleband and bars[0].open < ta.bbands_4h.middleband:
                new_trigger_price = min(ta.bbands_4h.middleband, new_trigger_price)
            if strategy.trail_sl_with_bband:
                new_trigger_price = min(upper_band, new_trigger_price)
            if strategy.moving_sl_atr_fac > 0 and bars[1].low + ta.atr_4h * strategy.moving_sl_atr_fac < new_trigger_price:
                new_trigger_price = bars[1].low + ta.atr_4h * strategy.moving_sl_atr_fac
            if strategy.stop_at_trail:
                new_trigger_price = min(ta.highs_trail_4h + ta.atr_4h * 8, new_trigger_price)
            if True:
                middleband = ta.bbands_4h.middleband
                std = ta.bbands_4h.std
                cond_1 = new_trigger_price > (middleband + 0.5 * std)
                cond_2 = bars[1].low < middleband - 3 * std
                cond_3 = ta.rsi_w > 55
                if cond_1 and cond_2 and cond_3:
                    new_trigger_price = bars[1].close + 0.1 * ta.atr_4h

        elif order.amount < 0:  # SL for LONGs
            if strategy.stop_at_trail:
                new_trigger_price = max(ta.lows_trail_4h - ta.atr_4h, new_trigger_price)
            if strategy.stop_at_lowerband:
                new_trigger_price = max(lower_band, new_trigger_price)
            if strategy.be_by_middleband and bars[1].high > ta.bbands_4h.middleband:
                new_trigger_price = max(position.wanted_entry, new_trigger_price)
            if strategy.be_by_opposite and bars[1].high > (upper_band - ta.atr_4h * strategy.atr_buffer_fac):
                new_trigger_price = max(position.wanted_entry, new_trigger_price)
            if strategy.stop_at_new_entry and bars[1].high > ta.bbands_4h.middleband:
                new_trigger_price = max(lower_band, new_trigger_price)
            if strategy.stop_at_middleband and bars[1].high > (upper_band - ta.atr_4h * strategy.atr_buffer_fac):
                new_trigger_price = max(ta.bbands_4h.middleband, new_trigger_price)
            if strategy.tp_on_opposite and bars[1].high > upper_band:
                new_trigger_price = max(bars[0].open, new_trigger_price)
            if strategy.tp_at_middleband and bars[0].open > ta.bbands_4h.middleband:
                new_trigger_price = max(ta.bbands_4h.middleband, new_trigger_price)
            if strategy.trail_sl_with_bband:
                new_trigger_price = max(lower_band, new_trigger_price)
            if strategy.ema_multiple_4_tp != 0:
                ema_multiple = ta.ema_w * strategy.ema_multiple_4_tp
                d_rsi_low = 90 < ta.rsi_d
                if bars[0].open > ema_multiple and d_rsi_low:
                    new_trigger_price = bars[0].open

    return new_trigger_price

