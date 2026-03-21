def calc_entry_and_exit(strategy, bars):
    # find swing highs and lows
    depth = 40
    foundSwingHigh = False
    foundSwingLow = False
    idxSwingHigh = 0
    idxSwingLow = 0
    for i in range(3, depth):
        condition_1 = bars[i + 2].close < bars[i].close
        condition_2 = bars[i + 1].close < bars[i].close
        condition_3 = bars[i - 2].close < bars[i].close > bars[i - 1].close
        condition_5 = bars[i + 3].close < bars[i].close
        if condition_1 and condition_2 and condition_3 and condition_5:
            foundSwingHigh = True
            idxSwingHigh = i
            break

    if foundSwingHigh:
        high_values = [bar.close for bar in bars[1:idxSwingHigh]]
        alreadyLonged = any(high > bars[idxSwingHigh].close for high in high_values)
    else:
        alreadyLonged = True

    for i in range(5, depth):
        cond_1 = bars[i + 2].close > bars[i + 1].close
        cond_2 = bars[i + 1].close > bars[i].close
        cond_3 = bars[i - 2].close > bars[i].close < bars[i - 1].close
        if cond_1 and cond_2 and cond_3:
            foundSwingLow = True
            idxSwingLow = i
            break
    if foundSwingLow:
        low_values = [bar.close for bar in bars[1:idxSwingLow]]
        alreadyShorted = any(low < bars[idxSwingLow].close for low in low_values)
    else:
        alreadyShorted = True

    if foundSwingHigh and not alreadyLonged and foundSwingLow and not alreadyShorted:
        # Calculate potential trade entries
        longEntry = strategy.symbol.normalizePrice(bars[idxSwingHigh].high + strategy.ta_data_trend_strat.atr_4h * 0.05, roundUp=True)
        shortEntry = strategy.symbol.normalizePrice(bars[idxSwingLow].low - strategy.ta_data_trend_strat.atr_4h * 0.05, roundUp=False)

        # Calculate stops
        stopLong = longEntry - strategy.ta_data_trend_strat.atr_4h * strategy.sl_atr_fac
        stopShort = shortEntry + strategy.ta_data_trend_strat.atr_4h * strategy.sl_atr_fac

        stopLong = strategy.symbol.normalizePrice(stopLong, roundUp=False)
        stopShort = strategy.symbol.normalizePrice(stopShort, roundUp=True)

        # amount
        expectedEntrySlippagePer = 0.0015 if strategy.limit_entry_offset_perc is None else 0
        expectedExitSlippagePer = 0.0015
        longAmount = strategy.calc_pos_size(
            risk=strategy.risk_factor,
            exitPrice=stopLong * (1 - expectedExitSlippagePer),
            entry=longEntry * (1 + expectedEntrySlippagePer),
            atr=0,
        )
        shortAmount = strategy.calc_pos_size(
            risk=strategy.risk_factor,
            exitPrice=stopShort * (1 + expectedExitSlippagePer),
            entry=shortEntry * (1 - expectedEntrySlippagePer),
            atr=0,
        )
    else:
        longEntry = None
        shortEntry = None
        stopLong = None
        stopShort = None
        longAmount = None
        shortAmount = None

    return longEntry, shortEntry, stopLong, stopShort, longAmount, shortAmount, alreadyLonged, alreadyShorted
