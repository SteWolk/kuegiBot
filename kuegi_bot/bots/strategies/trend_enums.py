from enum import Enum
from typing import Any, Dict


class MarketRegime(Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    RANGING = "RANGING"
    NONE = "NONE"


class MarketDynamic(Enum):
    TRENDING = "TRENDING"
    RANGING = "RANGING"
    NONE = "NONE"


class OIPriceFlowState(Enum):
    TREND_CONTINUATION = "trend_continuation"
    SHORT_COVER = "short_cover"
    BEARISH_CONTINUATION = "bearish_continuation"
    LONG_LIQUIDATION = "long_liquidation"
    NEUTRAL = "neutral"


_OI_PRICE_FLOW_ALIASES: Dict[str, str] = {
    "trend_continuation": OIPriceFlowState.TREND_CONTINUATION.value,
    "continuation": OIPriceFlowState.TREND_CONTINUATION.value,
    "price_up_oi_up": OIPriceFlowState.TREND_CONTINUATION.value,
    "short_cover": OIPriceFlowState.SHORT_COVER.value,
    "short_covering": OIPriceFlowState.SHORT_COVER.value,
    "price_up_oi_down": OIPriceFlowState.SHORT_COVER.value,
    "bearish_continuation": OIPriceFlowState.BEARISH_CONTINUATION.value,
    "price_down_oi_up": OIPriceFlowState.BEARISH_CONTINUATION.value,
    "long_liquidation": OIPriceFlowState.LONG_LIQUIDATION.value,
    "price_down_oi_down": OIPriceFlowState.LONG_LIQUIDATION.value,
    "neutral": OIPriceFlowState.NEUTRAL.value,
    "none": OIPriceFlowState.NEUTRAL.value,
    "off": "off",
}


def normalize_oi_price_flow_state(raw: Any, default: str = "off") -> str:
    if isinstance(raw, OIPriceFlowState):
        return raw.value
    txt = str(raw if raw is not None else "").strip().lower()
    txt = txt.replace("-", "_").replace(" ", "_")
    if txt == "":
        txt = str(default).strip().lower()
    return _OI_PRICE_FLOW_ALIASES.get(txt, str(default).strip().lower())


def oi_price_flow_state_from_returns(
    *,
    price_ret_pct: float,
    oi_ret_pct: float,
    price_min_pct: float = 0.0,
    oi_min_pct: float = 0.0,
) -> OIPriceFlowState:
    price_thr = max(0.0, float(price_min_pct))
    oi_thr = max(0.0, float(oi_min_pct))

    if price_ret_pct > price_thr:
        price_dir = 1
    elif price_ret_pct < -price_thr:
        price_dir = -1
    else:
        price_dir = 0

    if oi_ret_pct > oi_thr:
        oi_dir = 1
    elif oi_ret_pct < -oi_thr:
        oi_dir = -1
    else:
        oi_dir = 0

    if price_dir > 0 and oi_dir > 0:
        return OIPriceFlowState.TREND_CONTINUATION
    if price_dir > 0 and oi_dir < 0:
        return OIPriceFlowState.SHORT_COVER
    if price_dir < 0 and oi_dir > 0:
        return OIPriceFlowState.BEARISH_CONTINUATION
    if price_dir < 0 and oi_dir < 0:
        return OIPriceFlowState.LONG_LIQUIDATION
    return OIPriceFlowState.NEUTRAL


class OIFundingState(Enum):
    LONG_CROWDED = "long_crowded"
    SHORT_CROWDED = "short_crowded"
    DELEVERAGING = "deleveraging"
    NEUTRAL = "neutral"


_OI_FUNDING_ALIASES: Dict[str, str] = {
    "long_crowded": OIFundingState.LONG_CROWDED.value,
    "crowded_longs": OIFundingState.LONG_CROWDED.value,
    "short_crowded": OIFundingState.SHORT_CROWDED.value,
    "crowded_shorts": OIFundingState.SHORT_CROWDED.value,
    "deleveraging": OIFundingState.DELEVERAGING.value,
    "neutral": OIFundingState.NEUTRAL.value,
    "none": OIFundingState.NEUTRAL.value,
    "off": "off",
}


def normalize_oi_funding_state(raw: Any, default: str = "off") -> str:
    if isinstance(raw, OIFundingState):
        return raw.value
    txt = str(raw if raw is not None else "").strip().lower()
    txt = txt.replace("-", "_").replace(" ", "_")
    if txt == "":
        txt = str(default).strip().lower()
    return _OI_FUNDING_ALIASES.get(txt, str(default).strip().lower())


def oi_funding_state_from_metrics(
    *,
    oi_ret_pct: float,
    funding_rate: float,
    oi_up_min_pct: float = 0.0,
    oi_down_min_pct: float = 0.0,
    funding_pos_min: float = 0.0,
    funding_neg_min: float = 0.0,
) -> OIFundingState:
    up_thr = max(0.0, float(oi_up_min_pct))
    down_thr = max(0.0, float(oi_down_min_pct))
    pos_thr = max(0.0, float(funding_pos_min))
    neg_thr = max(0.0, float(funding_neg_min))

    if oi_ret_pct > up_thr and funding_rate >= pos_thr:
        return OIFundingState.LONG_CROWDED
    if oi_ret_pct > up_thr and funding_rate <= -neg_thr:
        return OIFundingState.SHORT_CROWDED
    if oi_ret_pct < -down_thr:
        return OIFundingState.DELEVERAGING
    return OIFundingState.NEUTRAL
