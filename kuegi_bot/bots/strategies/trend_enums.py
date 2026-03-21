from enum import Enum


class MarketRegime(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    RANGING = "RANGING"
    NONE = "NONE"


class MarketDynamic(Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    NONE = "NONE"

