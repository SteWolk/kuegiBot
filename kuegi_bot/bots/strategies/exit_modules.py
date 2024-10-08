
########
# some simple exit modules for reuse
##########
import math
from typing import List

from kuegi_bot.indicators.indicator import Indicator, clean_range
from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.trading_classes import Position, Bar, Symbol
from kuegi_bot.indicators.indicator import Indicator, calc_atr


class ExitModule:
    def __init__(self):
        self.logger = None
        self.symbol= None
        pass

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        pass

    def init(self, logger, symbol: Symbol):
        self.logger = logger
        self.symbol= symbol

    def got_data_for_position_sync(self, bars: List[Bar]) -> bool:
        return True

    def get_stop_for_unmatched_amount(self, amount: float, bars: List[Bar]):
        return None

    def get_data(self, bar: Bar, dataId):
        if 'modules' in bar.bot_data.keys() and dataId in bar.bot_data['modules'].keys():
            return bar.bot_data["modules"][dataId]
        else:
            return None

    def write_data(self, bar: Bar, dataId, data):
        if "modules" not in bar.bot_data.keys():
            bar.bot_data['modules'] = {}

        bar.bot_data["modules"][dataId] = data

    @staticmethod
    def get_data_for_json(bar:Bar):
        result= {}
        if bar is not None and bar.bot_data is not None and 'modules' in bar.bot_data.keys():
            for key in bar.bot_data['modules'].keys():
                if isinstance(bar.bot_data['modules'][key],dict):
                    result[key]= bar.bot_data['modules'][key]
                else:
                    result[key]= bar.bot_data['modules'][key].__dict__
        return result

    @staticmethod
    def set_data_from_json(bar:Bar,jsonData):
        if "modules" not in bar.bot_data.keys():
            bar.bot_data['modules'] = {}
        for key in jsonData.keys():
            if len(jsonData[key].keys()) > 0:
                bar.bot_data['modules'][key]= dotdict(jsonData[key])


class SimpleBE(ExitModule):
    ''' trails the stop to "break even" when the price move a given factor of the entry-risk in the right direction
        "break even" includes a buffer (multiple of the entry-risk).
    '''

    def __init__(self, factor, bufferLongs, bufferShorts, atrPeriod: int = 0):
        super().__init__()
        self.factor = factor
        self.bufferLongs = bufferLongs
        self.bufferShorts = bufferShorts
        self.atrPeriod = atrPeriod

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init BE %.2f %.2f %.2f %i" % (self.factor, self.bufferLongs, self.bufferShorts, self.atrPeriod))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if position is not None and self.factor > 0:
            # trail
            newStop = order.trigger_price
            refRange = 0
            if self.atrPeriod > 0:
                atrId = "atr_4h" + str(self.atrPeriod)
                refRange = Indicator.get_data_static(bars[1], atrId)
                if refRange is None:
                    refRange = clean_range(bars, offset=1, length=self.atrPeriod)
                    Indicator.write_data_static(bars[1], refRange, atrId)

            elif position.wanted_entry is not None and position.initial_stop is not None:
                refRange = (position.wanted_entry - position.initial_stop)

            if refRange != 0:
                ep = bars[0].high if position.amount > 0 else bars[0].low
                buffer = self.bufferLongs if position.amount > 0 else self.bufferShorts
                be = position.wanted_entry + refRange * buffer
                if newStop is not None:
                    if (ep - (position.wanted_entry + refRange * self.factor)) * position.amount > 0 \
                            and (be - newStop) * position.amount > 0:
                        newStop= self.symbol.normalizePrice(be, roundUp=position.amount < 0)

            if newStop != order.trigger_price:
                order.trigger_price = newStop
                to_update.append(order)


class QuickBreakEven(ExitModule):
    ''' trails the stop to "break even" within the provided time period as long as the stop is not in profit '''
    def __init__(self, seconds_to_BE: int = 999999, factor: float = 1.0):
        super().__init__()
        self.seconds_to_BE = seconds_to_BE
        self.factor = factor

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init QuickBreakEven %i" % (self.seconds_to_BE))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        newStop = order.trigger_price
        current_tstamp = bars[0].last_tick_tstamp if bars[0].last_tick_tstamp is not None else bars[0].tstamp

        refRange = abs(position.wanted_entry - position.initial_stop)
        seconds_since_entry = current_tstamp - position.entry_tstamp

        if self.seconds_to_BE is not None and self.seconds_to_BE != 0:
            equity_per_second = refRange / self.seconds_to_BE

            if (newStop < (position.wanted_entry + self.factor * refRange) and position.amount > 0) or \
                    (newStop > max((position.wanted_entry - refRange * self.factor),0) and position.amount < 0):
                if position.amount > 0:
                    newStop = position.initial_stop + equity_per_second * seconds_since_entry
                else:
                    newStop = position.initial_stop - equity_per_second * seconds_since_entry

                newStop = self.symbol.normalizePrice(newStop, roundUp=position.amount < 0)

            if newStop != order.trigger_price:
                order.trigger_price = newStop
                to_update.append(order)


class MaxSLDiff(ExitModule):
    ''' trails the stop to a max dist in atr_4h from the extreme point '''

    def __init__(self, maxATRDiff: float , atrPeriod: int = 0):
        super().__init__()
        self.maxATRDiff = maxATRDiff
        self.atrPeriod = atrPeriod

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init maxATRDiff %.1f %i" % (self.maxATRDiff, self.atrPeriod))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if position is not None and self.maxATRDiff > 0 and self.atrPeriod > 0:
            # trail
            newStop = order.trigger_price
            atrId = "atr_4h" + str(self.atrPeriod)
            refRange = Indicator.get_data_static(bars[1], atrId)
            if refRange is None:
                refRange = clean_range(bars, offset=1, length=self.atrPeriod)
                Indicator.write_data_static(bars[1], refRange, atrId)

            if refRange != 0:
                ep = bars[0].high if position.amount > 0 else bars[0].low
                maxdistStop= ep - math.copysign(refRange*self.maxATRDiff,position.amount)
                if (maxdistStop - newStop) * position.amount > 0:
                    newStop= self.symbol.normalizePrice(maxdistStop, roundUp=position.amount < 0)

            if math.fabs(newStop - order.trigger_price) > 0.5*self.symbol.tickSize:
                order.trigger_price = newStop
                to_update.append(order)


class TimedExit(ExitModule):
    ''' time based breakeven and exit '''

    def __init__(self, longs_min_to_exit:int= 240, shorts_min_to_exit: int = 240, longs_min_to_breakeven: int = 2,
                 shorts_min_to_breakeven: int = 2, atrPeriod: int = 14):
        super().__init__()
        self.longs_min_to_exit = longs_min_to_exit
        self.shorts_min_to_exit = shorts_min_to_exit
        self.atrPeriod = atrPeriod
        self.longs_min_to_breakeven = longs_min_to_breakeven
        self.shorts_min_to_breakeven = shorts_min_to_breakeven

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info(vars(self))
        #self.logger.info(f"init timedExit with {self.longs_min_to_exit}, {self.atrPeriod}")

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if bars[0].open == bars[0].close: # new candle
            current_tstamp = bars[0].last_tick_tstamp if bars[0].last_tick_tstamp is not None else bars[0].tstamp
            if current_tstamp > position.entry_tstamp + self.longs_min_to_exit*60:
                if position.amount > 0 and order.trigger_price < position.wanted_entry:       # longs
                    if bars[0].close < position.wanted_entry:
                        order.trigger_price = position.wanted_entry
                        to_update.append(order)

            if current_tstamp > position.entry_tstamp + self.longs_min_to_breakeven*60:
                if position.amount > 0 and order.trigger_price < position.wanted_entry:       # longs
                    if bars[0].close > position.wanted_entry:
                        order.trigger_price = position.wanted_entry
                        to_update.append(order)

            if current_tstamp > position.entry_tstamp + self.shorts_min_to_exit * 60:
                if position.amount < 0 and (order.trigger_price > position.wanted_entry):       # shorts
                    if bars[0].close > position.wanted_entry:
                        order.trigger_price = position.wanted_entry
                        to_update.append(order)

            if current_tstamp > position.entry_tstamp + self.shorts_min_to_breakeven*60:
                if position.amount < 0 and (order.trigger_price > position.wanted_entry):       # shorts
                    if bars[0].open < position.wanted_entry:
                        order.trigger_price = position.wanted_entry
                        to_update.append(order)

            if order.trigger_price == 0 or position.wanted_entry == 0:
                print('something is wrong here in exit module')


class RsiExit(ExitModule):
    """ closes positions at oversold and overbougt RSI """
    def __init__(self, rsi_high_lim: float = 100, rsi_low_lim: int = 0):
        super().__init__()
        self.rsi_high_lim = rsi_high_lim
        self.rsi_low_lim = rsi_low_lim

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init RSI TP at high: %i and low %i" % (self.rsi_high_lim, self.rsi_low_lim))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        test = 1


class FixedPercentage(ExitModule):
    """ trails the stop to a specified percentage from the highest high reached """
    def __init__(self, slPercentage: float= 0.0, useInitialSLRange: bool = False, rangeFactor: float = 1):
        super().__init__()
        self.slPercentage = min(slPercentage,1)     # trailing stop in fixed percentage
        self.useInitialSLRange = useInitialSLRange  # use initials SL range
        self.rangeFactor = abs(rangeFactor)         # SL range factor

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init Percentage Trail %.1f %s %.1f" % (self.slPercentage, self.useInitialSLRange, self.rangeFactor))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if order.trigger_price is None:
            return

        if position is not None:
            extremePoint = bars[0].high if position.amount > 0 else bars[0].low     # new highest/lowest price
            currentStop = sl_perc = sl_range= order.trigger_price                      # current SL price
            refRange = abs(position.wanted_entry - position.initial_stop)           # initial SL range in $
            refRangePercent = refRange/position.wanted_entry                        # initial SL range in %

            if position.amount > 0:
                sl1 = extremePoint * (1-self.slPercentage)                                      # SL in fixed percentage from extreme point
                sl2 = max(extremePoint * (1 - refRangePercent * self.rangeFactor),currentStop)  # SL in initial SL range percentage from extreme point
                if currentStop < sl1 and self.slPercentage > 0:
                    sl_perc = self.symbol.normalizePrice(sl1, roundUp=position.amount < 0)
                if currentStop < sl2 and self.useInitialSLRange:
                    sl_range = self.symbol.normalizePrice(sl2, roundUp=position.amount < 0)
                newStop = max(sl_perc,sl_range,currentStop)
            else:
                sl1 = extremePoint * (1 + self.slPercentage)
                sl2 = min(extremePoint * (1 + refRangePercent * self.rangeFactor),currentStop)
                if currentStop > sl1 and self.slPercentage > 0:
                    sl_perc = self.symbol.normalizePrice(sl1,roundUp=position.amount < 0)
                if currentStop > sl2 and self.useInitialSLRange:
                    sl_range = self.symbol.normalizePrice(sl2, roundUp=position.amount < 0)
                newStop = min(sl_perc, sl_range, currentStop)

            if newStop != order.trigger_price:
                self.logger.info("changing SL. Previous Stop: " + str(order.trigger_price) + "; New Stop: " + str(newStop))
                order.trigger_price = newStop
                to_update.append(order)


class ParaData:
    def __init__(self):
        self.acc = 0
        self.ep = 0
        self.stop = 0
        self.actualStop= None


class ParaTrail(ExitModule):
    '''
    trails the stop according to a parabolic SAR. ep is resetted on the entry of the position.
    lastEp and factor is stored in the bar data with the positionId
    '''

    def __init__(self, accInit, accInc, accMax, resetToCurrent= False):
        super().__init__()
        self.accInit = accInit
        self.accInc = accInc
        self.accMax = accMax
        self.resetToCurrent= resetToCurrent

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init ParaTrail %.2f %.2f %.2f %s" %
                         (self.accInit, self.accInc, self.accMax, self.resetToCurrent))

    def data_id(self,position:Position):
        return position.id + '_paraExit'

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        if position is None or order is None or order.trigger_price is None:
            return

        self.update_bar_data(position, bars)
        data = self.get_data(bars[0],self.data_id(position))
        newStop = order.trigger_price

        # trail
        if data is not None and (data.stop - newStop) * position.amount > 0:
            newStop= self.symbol.normalizePrice(data.stop, roundUp=position.amount < 0)

        if data is not None and data.actualStop != newStop:
            data.actualStop = newStop
            self.write_data(bar=bars[0], dataId=self.data_id(position), data=data)
        # if restart, the last actual is not set and we might miss increments cause of regular restarts.
        lastdata= self.get_data(bars[1],self.data_id(position))
        if lastdata is not None and lastdata.actualStop is None:
            lastdata.actualStop= order.trigger_price
            self.write_data(bar=bars[1], dataId=self.data_id(position), data=lastdata)

        if math.fabs(newStop - order.trigger_price) > 0.5*self.symbol.tickSize:
            order.trigger_price = newStop
            to_update.append(order)

    def update_bar_data(self, position: Position, bars: List[Bar]):
        if position.initial_stop is None or position.entry_tstamp is None or position.entry_tstamp == 0:
            return  # cant trail with no initial and not defined entry
        dataId = self.data_id(position)
        # find first bar with data (or entry bar)
        lastIdx = 1
        while self.get_data(bars[lastIdx], dataId) is None and bars[lastIdx].tstamp > position.entry_tstamp:
            lastIdx += 1
            if lastIdx == len(bars):
                break
        if self.get_data(bars[lastIdx - 1], dataId) is None and bars[lastIdx].tstamp > position.entry_tstamp:
            lastIdx += 1  # didn't see the current bar before: make sure we got the latest update on the last one too

        while lastIdx > 0:
            lastbar = bars[lastIdx]
            currentBar = bars[lastIdx - 1]
            last: ParaData = self.get_data(lastbar, dataId)
            prev: ParaData = self.get_data(currentBar, dataId)
            current: ParaData = ParaData()
            if last is not None:
                current.ep = max(last.ep, currentBar.high) if position.amount > 0 else min(last.ep, currentBar.low)
                current.acc = last.acc
                if current.ep != last.ep:
                    current.acc = min(current.acc + self.accInc, self.accMax)
                lastStop = last.stop
                if self.resetToCurrent and last.actualStop is not None and (last.actualStop - last.stop) * position.amount > 0:
                    lastStop= last.actualStop
                current.stop = lastStop + (current.ep - last.stop) * current.acc
            else:  # means its the first bar of the position
                current.ep = currentBar.high if position.amount > 0 else currentBar.low
                current.acc = self.accInit
                current.stop = position.initial_stop
            if prev is not None:
                current.actualStop = prev.actualStop # not to loose it
            self.write_data(bar=currentBar, dataId=dataId, data=current)
            lastIdx -= 1


class ATRrangeSL(ExitModule):
    ''' trails the stop to "to a new position" when the price moves a given factor of the entry-risk in the right direction
        "break even" includes a buffer (multiple of the entry-risk).
    '''

    def __init__(self, rangeFacTrigger, longRangefacSL, shortRangefacSL, rangeATRfactor: float = 0, atrPeriod: int = 10):
        super().__init__()
        self.rangeFacTrigger = rangeFacTrigger
        self.longRangefacSL = longRangefacSL
        self.shortRangefacSL = shortRangefacSL
        self.rangeATRfactor = rangeATRfactor
        self.atrPeriod = atrPeriod

    def init(self, logger,symbol):
        super().init(logger,symbol)
        self.logger.info("init ATRrangeSL %.2f %.2f %.2f %.2f %i" % (self.rangeFacTrigger, self.longRangefacSL, self.shortRangefacSL, self.rangeATRfactor, self.atrPeriod))

    def manage_open_order(self, order, position, bars, to_update, to_cancel, open_positions):
        # trail the stop to "break even" when the price move a given factor of the entry-risk in the right direction

        is_new_bar = False
        if bars[0].open == bars[0].close:
            is_new_bar = True

        entry = position.wanted_entry
        if order.trigger_price is None:
            return
        current_stop = order.trigger_price
        skip_trailing = False

        direction = 1 if position.amount > 0 else -1

        if direction == 1:
            if current_stop >= entry and not is_new_bar:
                skip_trailing = True
        else:
            if current_stop <= entry and not is_new_bar:
                skip_trailing = True

        if not skip_trailing:
            ep = bars[0].high if position.amount > 0 else bars[0].low
            newStop = order.trigger_price
            atrId = "ATR_" + str(self.atrPeriod)
            atr = Indicator.get_data_static(bars[1], atrId)
            if atr is None:
                atr = calc_atr(bars, offset=1, length= self.atrPeriod)
                Indicator.write_data_static(bars[1], atr, atrId)
            if self.rangeATRfactor > 0:
                refRange = self.rangeATRfactor * atr
            elif position.initial_stop is not None and position.wanted_entry is not None:
                refRange = abs(position.initial_stop - position.wanted_entry)
            else:
                refRange = None

            if newStop is not None and refRange is not None:
                rangeSLfac = self.longRangefacSL if position.amount > 0 else self.shortRangefacSL
                targetSL = position.wanted_entry + refRange * rangeSLfac * direction
                triggerPrice = position.wanted_entry + refRange * self.rangeFacTrigger * direction
                if ep < triggerPrice and position.amount < 0 and newStop > targetSL:
                    newStop = self.symbol.normalizePrice(targetSL, roundUp=position.amount < 0)
                elif ep > (position.wanted_entry + refRange * self.rangeFacTrigger) and position.amount > 0 and newStop < targetSL:
                    newStop = self.symbol.normalizePrice(targetSL, roundUp=position.amount < 0)

                if newStop > order.trigger_price and position.amount > 0 or newStop < order.trigger_price and position.amount < 0:
                    order.trigger_price = newStop
                    to_update.append(order)