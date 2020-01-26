from kuegi_bot.trade_engine import TradingBot
from kuegi_bot.bots.trading_bot import PositionDirection
from kuegi_bot.utils.trading_classes import Position, Order, Account, Bar, Symbol, OrderType
from kuegi_bot.kuegi_channel import KuegiChannel, Data, clean_range
import plotly.graph_objects as go
import math
from typing import List
from datetime import datetime


class KuegiBot(TradingBot):

    def __init__(self, logger=None, directionFilter=0,
                 max_look_back: int = 13, threshold_factor: float = 2.5, buffer_factor: float = -0.0618,
                 max_dist_factor: float = 1, max_swing_length: int = 3,
                 max_channel_size_factor: float = 6, min_channel_size_factor: float = 0,
                 risk_factor: float = 0.01, max_risk_mul: float = 2, risk_type: int = 0,
                 entry_tightening=0, bars_till_cancel_triggered=3,
                 be_factor: float = 0, be_buffer: float= 0.1,  allow_trail_back: bool = False,
                 stop_entry: bool = False, trail_to_swing: bool = False, delayed_entry: bool = True,
                 delayed_cancel: bool = False):
        super().__init__(logger, directionFilter)
        self.myId = "KuegiBot_" + str(max_look_back) + '_' + str(threshold_factor) + '_' + str(
            buffer_factor) + '_' + str(max_dist_factor) + '_' + str(max_swing_length) + '__' + str(
            max_channel_size_factor) + '_' + str(
            int(stop_entry)) + '_' + str(int(trail_to_swing)) + '_' + str(int(delayed_entry))
        self.channel = KuegiChannel(max_look_back, threshold_factor, buffer_factor, max_dist_factor, max_swing_length)
        self.max_channel_size_factor = max_channel_size_factor
        self.min_channel_size_factor = min_channel_size_factor
        self.risk_factor = risk_factor
        self.stop_entry = stop_entry
        self.trail_to_swing = trail_to_swing
        self.delayed_entry = delayed_entry
        self.entry_tightening = entry_tightening
        self.bars_till_cancel_triggered = bars_till_cancel_triggered
        self.delayed_cancel = delayed_cancel
        self.be_factor = be_factor
        self.be_buffer = be_buffer
        self.allow_trail_back = allow_trail_back
        self.risk_type = risk_type  # 0= all equal, 1= 1 atr eq 1 R
        self.max_dist_factor = max_dist_factor
        self.max_risk_mul = max_risk_mul

    def uid(self) -> str:
        return self.myId

    def min_bars_needed(self):
        return self.channel.max_look_back + 1

    def init(self, bars: List[Bar], account: Account, symbol: Symbol, unique_id: str = ""):
        self.logger.info("started %s with %i %.1f %.3f %.1f %i %.0f %.1f %.3f %.1f %i %.1f %i %.1f %s %s %s %s %s" %
                         (unique_id,
                          self.channel.max_look_back, self.channel.threshold_factor, self.channel.buffer_factor,
                          self.channel.max_dist_factor, self.channel.max_swing_length,
                          self.max_channel_size_factor, self.min_channel_size_factor,
                          self.risk_factor, self.max_risk_mul, self.risk_type, self.entry_tightening,
                          self.bars_till_cancel_triggered, self.be_factor, self.allow_trail_back,
                          self.stop_entry, self.trail_to_swing, self.delayed_entry, self.delayed_cancel))
        self.channel.on_tick(bars)
        super().init(bars, account, symbol, unique_id)


    def prep_bars(self, bars: list):
        if self.is_new_bar:
            self.channel.on_tick(bars)

    def position_got_opened(self, position:Position, bars:List[Bar],account:Account):
        other_id = self.get_other_direction_id(position.id)
        if other_id in self.open_positions.keys():
            self.open_positions[other_id].markForCancel = bars[0].tstamp

        # add stop
        order = Order(orderId=self.generate_order_id(positionId=position.id,
                                                     type=OrderType.SL),
                      stop=position.initial_stop,
                      amount=-position.amount)
        self.order_interface.send_order(order)
        # added temporarily, cause sync with open orders is in the next loop and otherwise the orders vs
        # position check fails
        if order not in account.open_orders:  # outside world might have already added it
            account.open_orders.append(order)

    def got_data_for_position_sync(self, bars:List[Bar]):
        return self.channel.get_data(bars[1]) is not None

    def get_stop_for_unmatched_amount(self, amount:float,bars:List[Bar]):
        data= self.channel.get_data(bars[1])
        stopLong = int(max(data.shortSwing, data.longTrail) if data.shortSwing is not None else data.longTrail)
        stopShort = int(min(data.longSwing, data.shortTrail) if data.longSwing is not None else data.shortTrail)
        return (stopLong if amount > 0 else stopShort)

    def manage_open_orders(self, bars: List[Bar], account: Account):
        self.sync_executions(bars, account)

        to_cancel = []
        # check for triggered but not filled
        for order in account.open_orders:
            if order.stop_triggered:
                # clear other side
                posId = self.position_id_from_order_id(order.id)
                if posId not in self.open_positions.keys():
                    continue
                other_id = self.get_other_direction_id(posId=posId)
                if other_id in self.open_positions.keys():
                    self.open_positions[other_id].markForCancel = bars[0].tstamp

                position = self.open_positions[posId]
                position.status = "triggered"
                if not hasattr(position, 'waitingToFillSince'):
                    position.waitingToFillSince = bars[0].tstamp
                if (bars[0].tstamp - position.waitingToFillSince) > self.bars_till_cancel_triggered * (
                        bars[0].tstamp - bars[1].tstamp):
                    # cancel
                    position.status = "notFilled"
                    position.exit_tstamp = bars[0].tstamp
                    super().position_closed(position, account)
                    self.logger.info("canceling not filled position: " + position.id)
                    to_cancel.append(order)

        for o in to_cancel:
            self.order_interface.cancel_order(o)

        # cancel others
        to_cancel = []
        for p in self.open_positions.values():
            if hasattr(p, "markForCancel") and p.status == "pending" and (
                    not self.delayed_cancel or p.markForCancel < bars[0].tstamp):
                self.logger.info("canceling position caused marked for cancel: " + p.id)
                self.cancel_all_orders_for_position(p.id, account)
                to_cancel.append(p.id)

        for key in to_cancel:
            del self.open_positions[key]

        # check for BE

        if len(bars) < 5:
            return

        # trail stop only on new bar
        last_data: Data = self.channel.get_data(bars[2])
        data: Data = self.channel.get_data(bars[1])
        if data is not None:
            stopLong = data.longTrail
            stopShort = data.shortTrail
            if self.trail_to_swing and \
                    data.longSwing is not None and data.shortSwing is not None and \
                    (not self.delayed_entry or (last_data is not None and
                                                last_data.longSwing is not None and last_data.shortSwing is not None)):
                stopLong = max(data.shortSwing, stopLong)
                stopShort = min(data.longSwing, stopShort)

            to_update = []
            to_cancel = []
            for order in account.open_orders:
                posId = self.position_id_from_order_id(order.id)
                if posId not in self.open_positions.keys():
                    continue
                pos = self.open_positions[posId]
                orderType = self.order_type_from_order_id(order.id)
                if orderType == OrderType.SL:
                    # trail
                    newStop = order.stop_price
                    if order.amount < 0:
                        if self.is_new_bar and (newStop < stopLong or
                                                (self.allow_trail_back and
                                                 pos is not None and stopLong > pos.initial_stop)):
                            newStop = int(stopLong)
                        entry_diff= (pos.wanted_entry - pos.initial_stop)
                        if self.be_factor > 0 and \
                                pos.wanted_entry is not None and \
                                pos.initial_stop is not None and \
                                bars[0].high > pos.wanted_entry + entry_diff * self.be_factor \
                                and newStop < pos.wanted_entry + 1:
                            newStop = pos.wanted_entry + entry_diff*self.be_buffer

                    if order.amount > 0:
                        if self.is_new_bar and (newStop > stopShort or
                                                (self.allow_trail_back and
                                                 pos is not None and stopShort < pos.initial_stop)):
                            newStop = int(stopShort)
                        entry_diff= (pos.wanted_entry - pos.initial_stop)
                        if self.be_factor > 0 and \
                                pos.wanted_entry is not None and \
                                pos.initial_stop is not None and \
                                bars[0].low < pos.wanted_entry + entry_diff * self.be_factor \
                                and newStop > pos.wanted_entry - 1:
                            newStop = pos.wanted_entry +entry_diff*self.be_buffer

                    if newStop != order.stop_price:
                        order.stop_price = newStop
                        to_update.append(order)

                if orderType == OrderType.ENTRY and (data.longSwing is None or data.shortSwing is None):
                    if pos.status == "pending":  # don't delete if triggered
                        self.logger.info("canceling cause channel got invalid: " + pos.id)
                        to_cancel.append(order)
                        del self.open_positions[pos.id]

            for order in to_update:
                self.order_interface.update_order(order)
            for order in to_cancel:
                self.order_interface.cancel_order(order)

    def calc_pos_size(self, risk, entry, exit, data):
        if self.risk_type <= 2:
            delta = entry - exit
            if self.risk_type == 1:
                # use atr as delta reference, but max X the actual delta. so risk is never more than X times the
                # wanted risk
                delta = math.copysign(min(self.max_risk_mul * abs(delta), self.max_risk_mul * data.atr), delta)

            size = 0
            if not self.symbol.isInverse:
                size = risk / delta
            else:
                size = -int(risk / (1 / entry - 1 / (entry - delta)))
            return size

    def open_orders(self, bars: List[Bar], account: Account):
        if (not self.is_new_bar) or len(bars) < 5:
            return  # only open orders on beginning of bar

        last_data: Data = self.channel.get_data(bars[2])
        data: Data = self.channel.get_data(bars[1])
        if data is not None:
            self.logger.info("---- analyzing: %s atr: %.1f buffer: %.1f swings: %s/%s trails: %.1f/%.1f resets:%i/%i" %
                             (str(datetime.fromtimestamp(bars[0].tstamp)),
                              data.atr, data.buffer,
                              ("%.1f" % data.longSwing) if data.longSwing is not None else "-",
                              ("%.1f" % data.shortSwing) if data.shortSwing is not None else "-",
                              data.longTrail, data.shortTrail, data.sinceLongReset, data.sinceShortReset))
        if data is not None and last_data is not None and \
                data.shortSwing is not None and data.longSwing is not None and \
                (not self.delayed_entry or (last_data.shortSwing is not None and last_data.longSwing is not None)):
            swing_range = data.longSwing - data.shortSwing

            atr = clean_range(bars, offset=0, length=self.channel.max_look_back * 2)
            if atr * self.min_channel_size_factor < swing_range < atr * self.max_channel_size_factor:
                risk = self.risk_factor
                stopLong = int(max(data.shortSwing, data.longTrail))
                stopShort = int(min(data.longSwing, data.shortTrail))

                longEntry = int(max(data.longSwing, bars[0].high))
                shortEntry = int(min(data.shortSwing, bars[0].low))

                expectedEntrySplipagePerc = 0.0015 if self.stop_entry else 0
                expectedExitSlipagePerc = 0.0015

                # first check if we should update an existing one
                longAmount = self.calc_pos_size(risk=risk, exit=stopLong * (1 - expectedExitSlipagePerc),
                                                entry=longEntry * (1 + expectedEntrySplipagePerc),
                                                data=data)
                shortAmount = self.calc_pos_size(risk=risk, exit=stopShort * (1 + expectedExitSlipagePerc),
                                                 entry=shortEntry * (1 - expectedEntrySplipagePerc),
                                                 data=data)
                if longEntry < stopLong or shortEntry > stopShort:
                    self.logger.warn("can't put initial stop above entry")

                foundLong = False
                foundShort = False
                for position in self.open_positions.values():
                    if position.status == "pending":
                        if position.amount > 0:
                            foundLong = True
                            entry = longEntry
                            stop = stopLong
                            entryFac = (1 + expectedEntrySplipagePerc)
                            exitFac = (1 - expectedExitSlipagePerc)
                        else:
                            foundShort = True
                            entry = shortEntry
                            stop = stopShort
                            entryFac = (1 - expectedEntrySplipagePerc)
                            exitFac = (1 + expectedExitSlipagePerc)

                        for order in account.open_orders:
                            if self.position_id_from_order_id(order.id) == position.id:
                                newEntry = int(
                                    position.wanted_entry * (1 - self.entry_tightening) + entry * self.entry_tightening)
                                newStop = int(
                                    position.initial_stop * (1 - self.entry_tightening) + stop * self.entry_tightening)
                                amount = self.calc_pos_size(risk=risk, exit=newStop * exitFac,
                                                            entry=newEntry * entryFac, data=data)
                                if amount * order.amount < 0:
                                    self.logger.warn("updating order switching direction")
                                changed = False
                                changed = changed or order.stop_price != newEntry
                                order.stop_price = newEntry
                                if not self.stop_entry:
                                    changed = changed or order.limit_price != newEntry - math.copysign(1, amount)
                                    order.limit_price = newEntry - math.copysign(1, amount)
                                changed = changed or order.amount != amount
                                order.amount = amount
                                if changed:
                                    self.order_interface.update_order(order)
                                else:
                                    self.logger.info("order didn't change: %s" % order.print_info())

                                position.initial_stop = newStop
                                position.amount = amount
                                position.wanted_entry = newEntry
                                break

                # if len(self.open_positions) > 0:
                # return

                signalId = str(bars[0].tstamp)
                if not foundLong and self.directionFilter >= 0:
                    posId = self.full_pos_id(signalId, PositionDirection.LONG)
                    self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.ENTRY),
                                                          amount=longAmount, stop=longEntry,
                                                          limit=longEntry - 1 if not self.stop_entry else None))
                    self.open_positions[posId] = Position(id=posId, entry=longEntry, amount=longAmount, stop=stopLong,
                                                          tstamp=bars[0].tstamp)
                if not foundShort and self.directionFilter <= 0:
                    posId = self.full_pos_id(signalId, PositionDirection.SHORT)
                    self.order_interface.send_order(Order(orderId=self.generate_order_id(posId, OrderType.ENTRY),
                                                          amount=shortAmount, stop=shortEntry,
                                                          limit=shortEntry + 1 if not self.stop_entry else None))
                    self.open_positions[posId] = Position(id=posId, entry=shortEntry, amount=shortAmount,
                                                          stop=stopShort, tstamp=bars[0].tstamp)

    def add_to_plot(self, fig: go.Figure, bars: List[Bar], time):
        super().add_to_plot(fig, bars, time)
        lines = self.channel.get_number_of_lines()
        styles = self.channel.get_line_styles()
        names = self.channel.get_line_names()
        offset = 1  # we take it with offset 1
        self.logger.info("adding channel")
        for idx in range(0, lines):
            sub_data = list(map(lambda b: self.channel.get_data_for_plot(b)[idx], bars))
            fig.add_scatter(x=time, y=sub_data[offset:], mode='lines', line=styles[idx],
                            name=self.channel.id + "_" + names[idx])
