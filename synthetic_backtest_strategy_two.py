import logging

from kuegi_bot.backtest_engine import BackTest
from kuegi_bot.bots.MultiStrategyBot import MultiStrategyBot
from kuegi_bot.bots.strategies.strategy_two import StrategyTwo
from kuegi_bot.utils import log
from kuegi_bot.utils.synthetic_data import generate_synthetic_bars
from kuegi_bot.utils.trading_classes import Symbol


def main():
    logger = log.setup_custom_logger(log_level=logging.INFO)

    bars = generate_synthetic_bars(n_bars=1800, start_price=25000, timeframe_seconds=60 * 60, seed=17)
    symbol = Symbol(symbol="BTCUSDT", isInverse=False, tickSize=0.1, lotSize=0.001,
                    makerFee=-0.00025, takerFee=0.00075, baseCoin="USDT", quantityPrecision=3, pricePrecision=2)

    bot = MultiStrategyBot(logger=logger, directionFilter=0)
    bot.add_strategy(
        StrategyTwo(
            lookback=24,
            level_lookback=55,
            spike_threshold=0.008,
            volume_spike_factor=1.2,
            min_quality_score=2,
            max_positions=50,
        ).withRM(risk_factor=1.0, max_risk_mul=1, risk_type=0, atr_factor=0)
    )

    bt = BackTest(bot, bars, symbol=symbol)
    bt.run()

    closed = len([p for p in bot.position_history if p.status.value == "closed"])
    print(f"synthetic bars={len(bars)}")
    print(f"closed_positions={closed}")
    print(f"maxDD={bt.maxDD:.4f}")
    print(f"final_equity={bt.account.equity:.4f}")


if __name__ == "__main__":
    main()
