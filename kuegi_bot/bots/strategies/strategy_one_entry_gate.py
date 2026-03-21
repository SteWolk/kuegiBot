from kuegi_bot.bots.trading_bot import TradingBot
from kuegi_bot.bots.strategies.trend_enums import MarketRegime
from kuegi_bot.utils.trading_classes import OrderType


def entry_gate_passes(strategy, is_new_bar, bars, open_positions, all_open_pos):
    if not is_new_bar:
        return False

    if not strategy.entries_allowed(bars):
        strategy.logger.info("New entries not allowed")
        if strategy.telegram is not None:
            strategy.telegram.send_log("New entries not allowed")
        return False

    if strategy.ta_data_trend_strat.atr_4h is None:
        strategy.logger.info("atr not available")
        return False

    if strategy.ta_data_trend_strat.marketRegime == MarketRegime.NONE:
        strategy.logger.info("Market regime unknown")
        return False

    if len(all_open_pos) >= strategy.maxPositions and strategy.consolidate is False:
        strategy.logger.info("Reached max Positions: " + str(len(all_open_pos)))
        if strategy.telegram is not None:
            strategy.telegram.send_log("Reached max Positions")
        return False

    if strategy.reduceRisk:
        totalPos = 0
        totalWorstCase = 0
        for pos in open_positions.values():
            filled_entry = pos.filled_entry
            amount = pos.amount
            if filled_entry is not None:
                for o in pos.connectedOrders:
                    orderType = TradingBot.order_type_from_order_id(o.id)
                    if orderType == OrderType.SL:
                        initial_stop = pos.initial_stop
                        wanted_entry = pos.wanted_entry
                        sl = o.trigger_price
                        if strategy.symbol.isInverse:
                            worstCase = (1 / sl - 1 / filled_entry) / (1 / wanted_entry - 1 / initial_stop)
                            initialRisk = amount / initial_stop - amount / wanted_entry
                        else:
                            worstCase = (sl - filled_entry) / (wanted_entry - initial_stop)
                            initialRisk = amount * (wanted_entry - initial_stop)

                        totalPos += pos.amount
                        totalWorstCase += (worstCase * initialRisk)

        totalWorstCase = totalWorstCase / strategy.risk_ref
        if totalWorstCase < -strategy.max_r:
            strategy.logger.info("Too much active risk. No new entries.")
            if strategy.telegram is not None:
                strategy.telegram.send_log("Too much active risk. No new entries.")
                strategy.telegram.send_log("totalWorstCase:" + str(totalWorstCase))
            return False

    return True

