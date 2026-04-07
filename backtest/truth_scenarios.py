from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TruthScenario:
    scenario_id: str
    pair: str
    exchange: str
    timeframe: int
    days: int
    entry_module_overrides: Optional[Dict[str, object]] = None


DEFAULT_TRUTH_SCENARIOS: List[TruthScenario] = [
    TruthScenario(
        scenario_id="entry2_short",
        pair="BTCUSD",
        exchange="bybit",
        timeframe=240,
        days=200,
        entry_module_overrides={
            "entry_2": True,
            "entry_1": False,
            "entry_3": False,
            "entry_5": False,
            "entry_6": False,
            "entry_7": False,
            "entry_8": False,
            "entry_9": False,
            "entry_10": False,
            "entry_11": False,
            "entry_12": False,
        },
    ),
    TruthScenario(
        scenario_id="entry2_full",
        pair="BTCUSD",
        exchange="bybit",
        timeframe=240,
        days=3000,
        entry_module_overrides={
            "entry_2": True,
            "entry_1": False,
            "entry_3": False,
            "entry_5": False,
            "entry_6": False,
            "entry_7": False,
            "entry_8": False,
            "entry_9": False,
            "entry_10": False,
            "entry_11": False,
            "entry_12": False,
        },
    ),
    TruthScenario(
        scenario_id="entry7_short",
        pair="BTCUSD",
        exchange="bybit",
        timeframe=240,
        days=600,
        entry_module_overrides={
            "entry_1": False,
            "entry_2": False,
            "entry_3": False,
            "entry_5": False,
            "entry_6": False,
            "entry_7": True,
            "entry_8": False,
            "entry_9": False,
            "entry_10": False,
            "entry_11": False,
            "entry_12": False,
        },
    ),
    TruthScenario(
        scenario_id="entry11_long",
        pair="BTCUSD",
        exchange="bybit",
        timeframe=240,
        days=600,
        entry_module_overrides={
            "entry_1": False,
            "entry_2": False,
            "entry_3": False,
            "entry_5": False,
            "entry_6": False,
            "entry_7": False,
            "entry_8": False,
            "entry_9": False,
            "entry_10": False,
            "entry_11": True,
            "entry_12": False,
        },
    ),
    # High-SL-management scenario: multiple entries + ATR-based SL modules active.
    TruthScenario(
        scenario_id="multi_entries_sl_heavy",
        pair="BTCUSD",
        exchange="bybit",
        timeframe=240,
        days=1200,
        entry_module_overrides={
            "entry_1": True,
            "entry_2": True,
            "entry_3": True,
            "entry_5": True,
            "entry_6": True,
            "entry_7": True,
            "entry_8": True,
            "entry_9": True,
            "entry_10": True,
            "entry_11": True,
            "entry_12": True,
        },
    ),
]
