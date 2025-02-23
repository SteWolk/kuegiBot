import atexit
import json
import os
import signal
import sys
import threading
import traceback
from time import sleep, time
from typing import List

from kuegi_bot.bots.MultiStrategyBot import MultiStrategyBot
from kuegi_bot.bots.strategies.strategy_one import StrategyOne
from kuegi_bot.bots.strategies.entry_filters import DayOfWeekFilter
from kuegi_bot.bots.strategies.exit_modules import SimpleBE, ParaTrail, ExitModule, FixedPercentage, ATRrangeSL, TimedExit
from kuegi_bot.trade_engine import LiveTrading
from kuegi_bot.utils import log
from kuegi_bot.utils.telegram import TelegramBot
from kuegi_bot.utils.dotdict import dotdict
from kuegi_bot.utils.helper import load_settings_from_args


def start_bot(botSettings,telegram:TelegramBot=None):
    bot = MultiStrategyBot()
    originalSettings= dotdict(dict(botSettings))
    if "strategies" in botSettings.keys():
        risk_reference= 1
        if "RISK_REFERENCE" in botSettings.keys():
            risk_reference= botSettings.RISK_REFERENCE
        if risk_reference <= 0:
            logger.error("if you don't want to risk money, you shouldn't even run this bot!")
        bot.risk_reference= risk_reference
        strategies = dict(botSettings.strategies)
        del botSettings.strategies  # settings is now just the meta settings
        for stratId in strategies.keys():
            stratSettings = dict(botSettings)
            stratSettings = dotdict(stratSettings)
            stratSettings.update(strategies[stratId])
            if stratSettings.KB_RISK_FACTOR <= 0:
                logger.error("if you don't want to risk money, you shouldn't even run this bot!")
                continue

            if stratId == "strategyOne":
                strat = StrategyOne(
                    # Strategy One
                    # entry indicators
                    risk_ref=risk_reference,
                    reduceRisk=stratSettings.REDUCE_RISK,
                    max_r=stratSettings.MAX_R,
                    entry_1_atr_fac=stratSettings.ENTRY_1_ATR_FAC,
                    entry_1_vol_fac=stratSettings.ENTRY_1_VOL_FAC,
                    entry_2_max_natr=stratSettings.ENTRY_2_MAX_NATR,
                    entry_2_min_rsi_4h=stratSettings.ENTRY_2_MIN_RSI_4H,
                    entry_2_min_rsi_4h_short=stratSettings.ENTRY_2_MIN_RSI_4H_SHORT,
                    entry_2_min_rsi_d=stratSettings.ENTRY_2_MIN_RSI_D,
                    entry_2_min_rsi_d_short=stratSettings.ENTRY_2_MIN_RSI_D_SHORT,
                    entry_2_min_natr=stratSettings.ENTRY_2_MIN_NATR,
                    entry_3_max_natr=stratSettings.ENTRY_3_MAX_NATR,
                    entry_3_atr_fac=stratSettings.ENTRY_3_ATR_FAC,
                    entry_3_vol_fac=stratSettings.ENTRY_3_VOL_FAC,
                    entry_3_rsi_4h=stratSettings.ENTRY_3_RSI_4H,
                    entry_4_std_fac=stratSettings.ENTRY_4_STD_FAC,
                    entry_4_std_fac_reclaim=stratSettings.ENTRY_4_STD_FAC_RECLAIM,
                    entry_5_natr=stratSettings.ENTRY_5_NATR,
                    entry_5_rsi_d=stratSettings.ENTRY_5_RSI_D,
                    entry_5_rsi_4h=stratSettings.ENTRY_5_RSI_4H,
                    entry_5_atr_fac=stratSettings.ENTRY_5_ATR_FAC,
                    entry_5_trail_1_period=stratSettings.ENTRY_5_TRAIL_1_PERIOD,
                    entry_5_trail_2_period=stratSettings.ENTRY_5_TRAIL_2_PERIOD,
                    entry_5_vol_fac=stratSettings.ENTRY_5_VOL_FAC,
                    entry_6_rsi_4h_max=stratSettings.ENTRY_6_RSI_4H_MAX,
                    entry_6_atr_fac=stratSettings.ENTRY_6_ATR_FAC,
                    entry_6_max_natr=stratSettings.ENTRY_6_MAX_NATR,
                    entry_7_std_fac=stratSettings.ENTRY_7_STD_FAC,
                    entry_7_4h_rsi=stratSettings.ENTRY_7_4H_RSI,
                    entry_7_vol_fac=stratSettings.ENTRY_7_VOL_FAC,
                    entry_8_vol_fac=stratSettings.ENTRY_8_VOL_FAC,
                    entry_9_std=stratSettings.ENTRY_9_STD,
                    entry_9_4h_rsi=stratSettings.ENTRY_9_4H_RSI,
                    entry_9_atr=stratSettings.ENTRY_9_ATR,
                    entry_10_natr=stratSettings.ENTRY_10_NATR,
                    entry_10_natr_ath=stratSettings.ENTRY_10_NATR_ATH,
                    entry_10_rsi_4h=stratSettings.ENTRY_10_RSI_4H,
                    entry_11_vol=stratSettings.ENTRY_11_VOL,
                    entry_11_atr=stratSettings.ENTRY_11_ATR,
                    entry_11_natr=stratSettings.ENTRY_11_NATR,
                    entry_12_vol=stratSettings.ENTRY_12_VOL,
                    entry_12_rsi_4h=stratSettings.ENTRY_12_RSI_4H,
                    entry_12_atr=stratSettings.ENTRY_12_ATR,
                    h_highs_trail_period=stratSettings.H_HIGHS_TRAIL_PERIOD,
                    h_lows_trail_period=stratSettings.H_LOWS_TRAIL_PERIOD,
                    tp_fac_strat_one=stratSettings.TP_FAC_STRAT_ONE,
                    # long entries
                    entry_1=stratSettings.ENTRY_1,
                    entry_2=stratSettings.ENTRY_2,
                    entry_3=stratSettings.ENTRY_3,
                    entry_4=stratSettings.ENTRY_4,
                    entry_5=stratSettings.ENTRY_5,
                    entry_6=stratSettings.ENTRY_6,
                    entry_7=stratSettings.ENTRY_7,
                    entry_8=stratSettings.ENTRY_8,
                    entry_9=stratSettings.ENTRY_9,
                    entry_10=stratSettings.ENTRY_10,
                    entry_11=stratSettings.ENTRY_11,
                    entry_12=stratSettings.ENTRY_12,
                    # direction filter
                    longsAllowed=stratSettings.LONGS_ALLOWED,
                    shortsAllowed=stratSettings.SHORTS_ALLOWED,
                    # TrendStrategy
                    timeframe=stratSettings.TIMEFRAME,
                    ema_w_period=stratSettings.EMA_W_PERIOD,
                    highs_trail_4h_period=stratSettings.HIGHS_TRAIL_4H_PERIOD,
                    lows_trail_4h_period=stratSettings.LOWS_TRAIL_4H_PERIOD,
                    days_buffer_bear=stratSettings.DAYS_BUFFER_BEAR,
                    days_buffer_bull=stratSettings.DAYS_BUFFER_BULL,
                    trend_atr_fac=stratSettings.TREND_ATR_FAC,
                    atr_4h_period=stratSettings.ATR_4H_PERIOD,
                    natr_4h_period_slow=stratSettings.NATR_4H_PERIOD_SLOW,
                    bbands_4h_period=stratSettings.BBANDS_4H_PERIOD,
                    plotIndicators=stratSettings.PLOTINDICATORS,
                    rsi_4h_period=stratSettings.RSI_4H_PERIOD,
                    trend_var_1=stratSettings.TREND_VAR_1,
                    volume_sma_4h_period=stratSettings.VOLUME_SMA_4H_PERIOD,
                    # Risk
                    risk_with_trend=stratSettings.RISK_WITH_TREND*risk_reference,
                    risk_counter_trend=stratSettings.RISK_COUNTER_TREND*risk_reference,
                    risk_ranging=stratSettings.RISK_RANGING*risk_reference,
                    risk_fac_shorts=stratSettings.RISK_FAC_SHORTS,
                    # SL
                    sl_atr_fac=stratSettings.SL_ATR_FAC,
                    be_by_middleband=stratSettings.BE_BY_MIDDLEBAND,
                    be_by_opposite=stratSettings.BE_BY_OPPOSITE,
                    stop_at_middleband=stratSettings.STOP_AT_MIDDLEBAND,
                    tp_at_middleband=stratSettings.TP_AT_MIDDLEBAND,
                    atr_buffer_fac=stratSettings.ATR_BUFFER_FAC,
                    tp_on_opposite=stratSettings.TP_ON_OPPOSITE,
                    stop_at_new_entry=stratSettings.STOP_AT_NEW_ENTRY,
                    trail_sl_with_bband=stratSettings.TRAIL_SL_WITH_BBAND,
                    stop_short_at_middleband=stratSettings.STOP_SHORT_AT_MIDDLEBAND,
                    stop_at_trail=stratSettings.STOP_AT_TRAIL,
                    stop_at_lowerband=stratSettings.STOP_AT_LOWERBAND,
                    moving_sl_atr_fac=stratSettings.MOVING_SL_ATR_FAC,
                    sl_upper_bb_std_fac=stratSettings.SL_UPPER_BB_STD_FAC,
                    sl_lower_bb_std_fac=stratSettings.SL_LOWER_BB_STD_FAC,
                    ema_multiple_4_tp=stratSettings.EMA_MULTIPLE_4_TP,
                    # StrategyWithTradeManagement
                    maxPositions=stratSettings.MAXPOSITIONS,
                    consolidate=stratSettings.CONSOLIDATE,
                    close_on_opposite=stratSettings.CLOSE_ON_OPPOSITE,
                    bars_till_cancel_triggered=stratSettings.BARS_TILL_CANCEL_TRIGGERED,
                    limit_entry_offset_perc=stratSettings.LIMIT_ENTRY_OFFSET_PERC,
                    tp_fac=stratSettings.TP_FAC,
                    delayed_cancel=stratSettings.DELAYED_CANCEL,
                    cancel_on_filter=stratSettings.CANCEL_ON_FILTER
                    )
            else:
                strat = None
                logger.warning("unkown strategy: " + stratId)
            if strat is not None:
                strat.with_telegram(telegram)
                strat.withRM(risk_factor=stratSettings.KB_RISK_FACTOR*risk_reference,
                             risk_type=stratSettings.KB_RISK_TYPE,
                             max_risk_mul=stratSettings.KB_MAX_RISK_MUL,
                             atr_factor=stratSettings.KB_RISK_ATR_FAC)
                if "KB_BE_FACTOR" in stratSettings.keys():
                    strat.withExitModule(SimpleBE(factor=stratSettings.KB_BE_FACTOR,
                                                  bufferLongs=stratSettings.KB_BE_BUFFERLONGS,
                                                  bufferShorts=stratSettings.KB_BE_BUFFERSHORTS,
                                                  atrPeriod=stratSettings.KB_BE_ATR))
                for i in range(1,10):
                    factorKey= "KB_BE"+str(i)+"_FACTOR"
                    bufferLongsKey= "KB_BE"+str(i)+"_BUFFERLONGS"
                    bufferShortsKey = "KB_BE" + str(i) + "_BUFFERSHORTS"
                    atrKey = "KB_BE" + str(i) + "_ATR"
                    if factorKey in stratSettings.keys():
                        strat.withExitModule(SimpleBE(factor=stratSettings[factorKey],
                                                      bufferLongs=stratSettings[bufferLongsKey],
                                                      bufferShorts=stratSettings[bufferShortsKey],
                                                      atrPeriod=stratSettings[atrKey]))
                for i in range(1,10):
                    rangeFacTriggerKey= "RANGE_FAC_TRIGGER_"+str(i)
                    longRangefacSLKey = "LONG_RANGE_FAC_SL_" + str(i)
                    shortRangefacSLKey = "SHORT_RANGE_FAC_SL_" + str(i)
                    rangeATRfactorKey = "RANGE_ATR_FAC_" + str(i)
                    atrPeriodKey = "ATR_PERIOD_" + str(i)
                    if rangeFacTriggerKey in stratSettings.keys():
                        strat.withExitModule(ATRrangeSL(rangeFacTrigger=stratSettings[rangeFacTriggerKey],
                                                        longRangefacSL=stratSettings[longRangefacSLKey],
                                                        shortRangefacSL=stratSettings[shortRangefacSLKey],
                                                        rangeATRfactor=stratSettings[rangeATRfactorKey],
                                                        atrPeriod=stratSettings[atrPeriodKey]
                                                        ))
                if "EM_PARA_INIT" in stratSettings.keys():
                    resetToCurrent= False
                    if "EM_PARA_RESET" in stratSettings.keys():
                        resetToCurrent= stratSettings.EM_PARA_RESET
                    strat.withExitModule(ParaTrail(accInit=stratSettings.EM_PARA_INIT,
                                                   accInc=stratSettings.EM_PARA_INC,
                                                   accMax=stratSettings.EM_PARA_MAX,
                                                   resetToCurrent=resetToCurrent))
                if "SL_PERC" in stratSettings.keys():
                    strat.withExitModule(FixedPercentage(slPercentage = stratSettings.SL_PERC,
                                                         useInitialSLRange= stratSettings.USE_INIT_SL,
                                                         rangeFactor =stratSettings.RANGE_FAC))
                if "ATR_PERIOD_TIMED_EXIT" in stratSettings.keys():
                    strat.withExitModule(TimedExit(longs_min_to_exit = stratSettings.LONGS_MIN_TO_EXIT,
                                                   shorts_min_to_exit = stratSettings.SHORTS_MIN_TO_EXIT,
                                                   longs_min_to_breakeven =stratSettings.LONGS_MIN_TO_BE,
                                                   shorts_min_to_breakeven =stratSettings.SHORTS_MIN_TO_BE,
                                                   atrPeriod = stratSettings.ATR_PERIOD_TIMED_EXIT))
                if "FILTER_DAYWEEK" in stratSettings.keys():
                    strat.withEntryFilter(DayOfWeekFilter(allowedDaysMask=stratSettings.FILTER_DAYWEEK))
                bot.add_strategy(strat)
    else:
        logger.error("only multistrat bot supported")
    live = LiveTrading(settings=botSettings, trading_bot=bot,telegram=telegram)
    t = threading.Thread(target=live.run_loop)
    t.bot: LiveTrading = live
    t.originalSettings= originalSettings
    t.start()
    return t


def stop_all_and_exit():
    logger.info("closing bots")
    for t in activeThreads:
        t.bot.exit()

    logger.info("bye")
    atexit.unregister(stop_all_and_exit)
    sys.exit()


def term_handler(signum, frame):
    logger.info("got SIG %i" % signum)
    stop_all_and_exit()


def write_dashboard(dashboardFile):
    result = {}
    for thread in activeThreads:
        try:
            engine: LiveTrading = thread.bot
            if engine.alive:
                bot= engine.bot
                result[engine.id] = {
                    'alive': engine.alive,
                    "last_time": bot.last_time,
                    "last_tick": str(bot.last_tick_time),
                    "last_tick_tstamp": bot.last_tick_time.timestamp() if bot.last_tick_time is not None else None,
                    "equity": engine.account.equity,
                    "risk_reference":bot.risk_reference,
                    "max_equity":bot.max_equity,
                    "time_of_max_equity":bot.time_of_max_equity
                }
                data = result[engine.id]
                data['positions'] = []
                for pos in engine.bot.open_positions:
                    data['positions'].append(engine.bot.open_positions[pos].to_json())
                data['moduleData'] = {}
                data['moduleData'][engine.bars[0].tstamp] = ExitModule.get_data_for_json(engine.bars[0])
                data['moduleData'][engine.bars[1].tstamp] = ExitModule.get_data_for_json(engine.bars[1])

            else:
                result[engine.id] = {"alive": engine.alive}
        except Exception as e:
            logger.error("exception in writing dashboard: " + traceback.format_exc())
            thread.bot.alive= False

    try:
        os.makedirs(os.path.dirname(dashboardFile))
    except Exception:
        pass
    with open(dashboardFile, 'w') as file:
        json.dump(result, file, sort_keys=False, indent=4)

def run(settings):
    signal.signal(signal.SIGTERM, term_handler)
    signal.signal(signal.SIGINT, term_handler)
    atexit.register(stop_all_and_exit)

    if not settings:
        print("error: no settings defined. nothing to do. exiting")
        sys.exit()
    if settings.TELEGRAM_BOT is not None:
      telegram_bot:TelegramBot = TelegramBot(logger=logger,settings=dotdict(settings.TELEGRAM_BOT))
    else:
      telegram_bot= None
    logger.info("###### loading %i bots #########" % len(settings.bots))
    if settings.bots is not None:
        sets = settings.bots[:]
        del settings.bots  # settings is now just the meta settings
        for botSetting in sets:
            usedSettings = dict(settings)
            usedSettings = dotdict(usedSettings)
            usedSettings.update(botSetting)
            if len(usedSettings.API_KEY) == 0 or len(usedSettings.API_SECRET) == 0:
                logger.error("You have to put in apiKey and secret before starting!")
            else:
                logger.info("starting " + usedSettings.id)
                try:
                    activeThreads.append(start_bot(botSettings=usedSettings, telegram=telegram_bot))
                except Exception as e:
                    if telegram_bot is not None:
                        telegram_bot.send_log("error in init of "+usedSettings.id)
                        telegram_bot.send_execution("error in init of "+usedSettings.id)
                    logger.error("exception in main loop:\n "+ traceback.format_exc())
                    stop_all_and_exit()

    logger.info("init done")
    if telegram_bot is not None:
        telegram_bot.send_log("init_done")
        telegram_bot.send_execution("init_done")

    if len(activeThreads) > 0:
        failures= 0
        lastError= 0
        while True:
            try:
                sleep(1)
                toRestart= []
                toRemove= []
                for thread in activeThreads:
                    if not thread.is_alive() or not thread.bot.alive:
                        logger.info("%s died. stopping" % thread.bot.id)
                        if telegram_bot is not None:
                            telegram_bot.send_log(thread.bot.id+" died. restarting")
                            telegram_bot.send_execution(thread.bot.id+" died. restarting")
                        toRestart.append(thread.originalSettings)
                        thread.bot.exit()
                        toRemove.append(thread)
                        failures = failures + 1
                        lastError= time()
                for thread in toRemove:
                    activeThreads.remove(thread)
                if time() - lastError > 60*15:
                    failures= 0 # reset errorCount after 15 minutes. only restart if more than 5 errors in 15 min
                if failures > 5:
                    logger.info("too many failures, restart the whole thing")
                    stop_all_and_exit()
                    break

                for usedSettings in toRestart:
                    logger.info("restarting " + usedSettings.id)
                    sleep(10)
                    activeThreads.append(start_bot(botSettings=usedSettings, telegram=telegram_bot))

                write_dashboard(settings.DASHBOARD_FILE)
            except Exception as e:
                logger.error("exception in main loop:\n "+ traceback.format_exc())
    else:
        logger.warn("no bots defined. nothing to do")


activeThreads: List[threading.Thread] = []
logger = None

if __name__ == '__main__':
    settings = load_settings_from_args()
    logger = log.setup_custom_logger("cryptobot",
                                     log_level=settings.LOG_LEVEL,
                                     logToConsole=settings.LOG_TO_CONSOLE,
                                     logToFile=settings.LOG_TO_FILE)
    run(settings)
else:
    logger = log.setup_custom_logger("cryptobot-pkg")
