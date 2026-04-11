# KuegiBot

Algorithmic crypto futures trading and backtesting framework, focused on modular strategy research and staged parameter optimization.

This repository is a fork and derivative work of:
`https://github.com/kuegi/kuegiBot`

## License and Attribution

This project is distributed under the GNU General Public License v3.0 (GPL-3.0), consistent with the upstream project it was forked from.

- Upstream project: `kuegi/kuegiBot`
- Local license text: [LICENSE](LICENSE)

If you redistribute this code (modified or unmodified), you must comply with GPL-3.0 obligations.

## Scope and Risk

This is an expert-oriented codebase for research and execution. It is not investment advice and comes without warranty. Running live trading without deep code and risk understanding can lead to full capital loss.

## Repository Structure

- `kuegi_bot/`: core bot, strategy, exchange, and backtest engine logic
- `backtest/`: optimizer, parity/truth gates, and backtest tooling
- `settings/`: runtime configuration (defaults plus local/private variants)
- `history/`: local market history cache for backtests
- `codex/`: developer quality/parity gate scripts
- `docs/`: static project documentation assets

## Quick Start

### Option A: Docker

```bash
docker build -t kuegibot-dev .
docker run --rm -it kuegibot-dev
```

### Option B: Local Conda Environment

```bash
conda create -n botenv python=3.10 -y
conda activate botenv
conda install -c conda-forge ta-lib=0.4.19 numpy=1.26.0 pandas=2.2.1 -y
pip install -r requirements.txt
pip install -e .
```

## Data Collection

Backtests require local history data:

```bash
py -3 history_crawler.py bybit
```

Optional funding crawler:

```bash
py -3 funding_crawler.py
```

## Backtesting and Optimization

### Interactive Backtest Sandbox

```bash
py -3 -i backtest.py
```

### Staged Optimizer (Entry Modules)

```bash
py -3 backtest/optimizer.py --entry-id entry_23 --pair BTCUSD --exchange bybit --timeframe 240 --days 18000 --dry-run-config
```

See [backtest/README.md](backtest/README.md) for entry points and tooling index.

### Development Gate

```bash
py -3 codex/dev_gate.py
```

Full parity mode:

```bash
py -3 codex/dev_gate.py --full-parity
```

## Live / Paper Trading

Run with a settings file:

```bash
py -3 cryptobot.py settings/cryptobot_Testnet.json
```

Interactive Brokers is supported via `EXCHANGE=ib` (aliases: `ibkr`, `interactivebrokers`).
The IB adapter connects to local TWS/IB Gateway using `ib-insync`, with these optional bot-level settings:
`IB_HOST` (default `127.0.0.1`), `IB_PORT` (default `7496`, or `7497` when `IS_TEST=true`),
`IB_CLIENT_ID`, `IB_ACCOUNT`, `IB_SEC_TYPE` (`FUT`/`STK`/`FX`/`CFD`), `IB_EXCHANGE`, `IB_CURRENCY`,
and either `IB_CON_ID` or (for futures) `IB_LOCAL_SYMBOL` / `IB_LAST_TRADE_DATE_OR_CONTRACT_MONTH`.

`cryptobot.py` loads `settings/defaults.json` first, then overlays the file you pass as argument.

Use testnet/simulated configs first. Do not run live capital without independent validation, monitoring, and failure handling.
