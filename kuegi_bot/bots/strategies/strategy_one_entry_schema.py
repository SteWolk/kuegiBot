from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


ENTRY_IDS: List[str] = [
    "entry_1",
    "entry_2",
    "entry_3",
    "entry_4",
    "entry_5",
    "entry_6",
    "entry_7",
    "entry_8",
    "entry_9",
    "entry_10",
    "entry_11",
    "entry_12",
    "entry_15",
    "entry_16",
    "entry_17",
    "entry_18",
    "entry_19",
    "entry_20",
    "entry_21",
    "entry_22",
    "entry_23",
    "entry_23_secondary",
    "entry_24",
]


PARAM_CLASSES: List[str] = [
    "activation",
    "idea",
    "confirmation",
    "filters",
    "execution",
]

ENTRY_IDS_WITH_NATIVE_SL_SETTINGS = {
    "entry_2",
}


DEPRECATED_LEGACY_PARAMS = {
    "entry_2_min_natr",
    "entry_2_min_rsi_4h_short",
    "entry_2_min_rsi_d_short",
    "entry_3_vol_fac",
    "entry_7_std_fac",
    "entry_7_4h_rsi",
    "entry_7_vol_fac",
}


def _default_sl_module_enabled(entry_id: str) -> bool:
    return str(entry_id) not in ENTRY_IDS_WITH_NATIVE_SL_SETTINGS


@dataclass(frozen=True)
class EntryParamSpec:
    name: str
    param_class: str
    value_type: str
    default: Any
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[List[str]] = None
    description: str = ""


def _activation_specs(entry_id: str) -> List[EntryParamSpec]:
    return [
        EntryParamSpec(
            name=entry_id,
            param_class="activation",
            value_type="bool",
            default=False,
            description=f"Enable {entry_id}.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_allow_long",
            param_class="activation",
            value_type="bool",
            default=True,
            description="Allow long-side execution for this entry.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_allow_short",
            param_class="activation",
            value_type="bool",
            default=True,
            description="Allow short-side execution for this entry.",
        ),
    ]


def _execution_specs(entry_id: str) -> List[EntryParamSpec]:
    default_sl_module_enabled = _default_sl_module_enabled(entry_id)
    return [
        EntryParamSpec(
            name=f"{entry_id}_order_type",
            param_class="execution",
            value_type="enum",
            default="legacy",
            choices=["legacy", "Market", "Limit", "StopLimit", "StopLoss"],
            description="Order type override. legacy keeps historical module behavior.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_entry_offset_atr",
            param_class="execution",
            value_type="float",
            default=0.0,
            minimum=-3.0,
            maximum=3.0,
            step=0.05,
            description="Entry offset in ATR units.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_entry_offset_pct",
            param_class="execution",
            value_type="float",
            default=0.0,
            minimum=-0.05,
            maximum=0.05,
            step=0.0005,
            description="Entry offset in price percent.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_sl_module_enabled",
            param_class="execution",
            value_type="bool",
            default=default_sl_module_enabled,
            description="Enable generic SL module (decoupled from entry idea). Default is on for entries without native SL settings.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_sl_module_atr_mult",
            param_class="execution",
            value_type="float",
            default=1.2,
            minimum=0.0,
            maximum=10.0,
            step=0.05,
            description="Generic SL module distance in ATR from entry, opposite trade direction.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_mode",
            param_class="execution",
            value_type="enum",
            default="legacy",
            choices=["legacy", "atr_from_entry", "atr_from_bar_extreme", "swing_extreme", "fixed_price", "hybrid_minmax"],
            description="Stop placement mode. legacy keeps historical module behavior.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_atr_mult",
            param_class="execution",
            value_type="float",
            default=1.0,
            minimum=0.1,
            maximum=10.0,
            step=0.05,
            description="ATR multiplier for non-legacy stop modes.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_ref_bar_index",
            param_class="execution",
            value_type="int",
            default=1,
            minimum=1,
            maximum=10,
            step=1,
            description="Bar index for bar-referenced stop modes.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_buffer_atr",
            param_class="execution",
            value_type="float",
            default=0.0,
            minimum=0.0,
            maximum=5.0,
            step=0.05,
            description="Additional ATR stop buffer.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_ref_profile_enabled",
            param_class="execution",
            value_type="bool",
            default=False,
            description="Enable stop reference-profile mode using selected ref-bar sources.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_ref_bar_1_source",
            param_class="execution",
            value_type="enum",
            default="off",
            choices=["off", "open", "close", "high", "low", "min_oc"],
            description="Optional stop reference source from bar[1].",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_ref_bar_2_source",
            param_class="execution",
            value_type="enum",
            default="off",
            choices=["off", "open", "close", "high", "low", "min_oc"],
            description="Optional stop reference source from bar[2].",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_ref_bar_3_source",
            param_class="execution",
            value_type="enum",
            default="off",
            choices=["off", "open", "close", "high", "low", "min_oc"],
            description="Optional stop reference source from bar[3].",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_ref_bar_4_source",
            param_class="execution",
            value_type="enum",
            default="off",
            choices=["off", "open", "close", "high", "low", "min_oc"],
            description="Optional stop reference source from bar[4].",
        ),
        EntryParamSpec(
            name=f"{entry_id}_stop_ref_bar_5_source",
            param_class="execution",
            value_type="enum",
            default="off",
            choices=["off", "open", "close", "high", "low", "min_oc"],
            description="Optional stop reference source from bar[5].",
        ),
        EntryParamSpec(
            name=f"{entry_id}_secondary_enabled",
            param_class="execution",
            value_type="bool",
            default=False,
            description="Enable secondary order behavior for this module.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_secondary_entry_offset_atr",
            param_class="execution",
            value_type="float",
            default=0.0,
            minimum=-3.0,
            maximum=3.0,
            step=0.05,
            description="Secondary order entry offset in ATR.",
        ),
        EntryParamSpec(
            name=f"{entry_id}_secondary_stop_atr_mult",
            param_class="execution",
            value_type="float",
            default=1.0,
            minimum=0.1,
            maximum=10.0,
            step=0.05,
            description="Secondary order stop ATR multiplier.",
        ),
    ]


def _generic_confirmation_specs(entry_id: str) -> List[EntryParamSpec]:
    return [
        EntryParamSpec(f"{entry_id}_confirm_rsi_4h_min_enabled", "confirmation", "bool", False, description="Enable generic minimum RSI-4H confirmation."),
        EntryParamSpec(f"{entry_id}_confirm_rsi_4h_min", "confirmation", "int", 0, 0, 100, 1, description="Generic minimum RSI-4H."),
        EntryParamSpec(f"{entry_id}_confirm_rsi_4h_max_enabled", "confirmation", "bool", False, description="Enable generic maximum RSI-4H confirmation."),
        EntryParamSpec(f"{entry_id}_confirm_rsi_4h_max", "confirmation", "int", 100, 0, 100, 1, description="Generic maximum RSI-4H."),
        EntryParamSpec(f"{entry_id}_confirm_rsi_d_min_enabled", "confirmation", "bool", False, description="Enable generic minimum RSI-D confirmation."),
        EntryParamSpec(f"{entry_id}_confirm_rsi_d_min", "confirmation", "int", 0, 0, 100, 1, description="Generic minimum RSI-D."),
        EntryParamSpec(f"{entry_id}_confirm_rsi_d_max_enabled", "confirmation", "bool", False, description="Enable generic maximum RSI-D confirmation."),
        EntryParamSpec(f"{entry_id}_confirm_rsi_d_max", "confirmation", "int", 100, 0, 100, 1, description="Generic maximum RSI-D."),
        EntryParamSpec(f"{entry_id}_confirm_natr_min_enabled", "confirmation", "bool", False, description="Enable generic minimum NATR confirmation."),
        EntryParamSpec(f"{entry_id}_confirm_natr_min", "confirmation", "float", 0.0, 0.0, 6.0, 0.1, description="Generic minimum NATR."),
        EntryParamSpec(f"{entry_id}_confirm_natr_max_enabled", "confirmation", "bool", False, description="Enable generic maximum NATR confirmation."),
        EntryParamSpec(f"{entry_id}_confirm_natr_max", "confirmation", "float", 10.0, 0.0, 10.0, 0.1, description="Generic maximum NATR."),
        EntryParamSpec(f"{entry_id}_confirm_vol_ratio_min_enabled", "confirmation", "bool", False, description="Enable generic minimum volume-ratio confirmation."),
        EntryParamSpec(f"{entry_id}_confirm_vol_ratio_min", "confirmation", "float", 0.0, 0.0, 10.0, 0.05, description="Generic minimum volume ratio (volume / volume_sma)."),
        EntryParamSpec(f"{entry_id}_confirm_vol_ratio_max_enabled", "confirmation", "bool", False, description="Enable generic maximum volume-ratio confirmation."),
        EntryParamSpec(f"{entry_id}_confirm_vol_ratio_max", "confirmation", "float", 10.0, 0.0, 10.0, 0.05, description="Generic maximum volume ratio (volume / volume_sma)."),
        EntryParamSpec(f"{entry_id}_confirm_require_green_body", "confirmation", "bool", False, description="Require prior candle to be green."),
        EntryParamSpec(f"{entry_id}_confirm_require_red_body", "confirmation", "bool", False, description="Require prior candle to be red."),
    ]


def _generic_filter_specs(entry_id: str) -> List[EntryParamSpec]:
    return [
        EntryParamSpec(f"{entry_id}_filter_forbid_market_bearish", "filters", "bool", False, description="Reject entries when market regime is bearish."),
        EntryParamSpec(f"{entry_id}_filter_forbid_market_bullish", "filters", "bool", False, description="Reject entries when market regime is bullish."),
        EntryParamSpec(f"{entry_id}_filter_require_market_bullish", "filters", "bool", False, description="Require market regime to be bullish (independent of market dynamic)."),
        EntryParamSpec(f"{entry_id}_filter_require_market_bearish", "filters", "bool", False, description="Require market regime to be bearish (independent of market dynamic)."),
        EntryParamSpec(f"{entry_id}_filter_forbid_market_trending", "filters", "bool", False, description="Reject entries when market is trending."),
        EntryParamSpec(f"{entry_id}_filter_require_market_ranging", "filters", "bool", False, description="Require market regime to be ranging."),
        EntryParamSpec(f"{entry_id}_filter_require_market_trending", "filters", "bool", False, description="Require market dynamic to be trending."),
        EntryParamSpec(f"{entry_id}_filter_natr_max_enabled", "filters", "bool", False, description="Enable generic maximum NATR filter."),
        EntryParamSpec(f"{entry_id}_filter_natr_max", "filters", "float", 10.0, 0.0, 10.0, 0.1, description="Generic maximum NATR."),
        EntryParamSpec(f"{entry_id}_filter_rsi_4h_max_enabled", "filters", "bool", False, description="Enable generic maximum RSI-4H filter."),
        EntryParamSpec(f"{entry_id}_filter_rsi_4h_max", "filters", "int", 100, 0, 100, 1, description="Generic maximum RSI-4H."),
        EntryParamSpec(f"{entry_id}_filter_rsi_d_min_enabled", "filters", "bool", False, description="Enable generic minimum RSI-D filter."),
        EntryParamSpec(f"{entry_id}_filter_rsi_d_min", "filters", "int", 0, 0, 100, 1, description="Generic minimum RSI-D."),
        EntryParamSpec(f"{entry_id}_filter_rsi_d_max_enabled", "filters", "bool", False, description="Enable generic maximum RSI-D filter."),
        EntryParamSpec(f"{entry_id}_filter_rsi_d_max", "filters", "int", 100, 0, 100, 1, description="Generic maximum RSI-D."),
        EntryParamSpec(f"{entry_id}_filter_vol_ratio_max_enabled", "filters", "bool", False, description="Enable generic maximum volume-ratio filter."),
        EntryParamSpec(f"{entry_id}_filter_vol_ratio_max", "filters", "float", 10.0, 0.0, 10.0, 0.05, description="Generic maximum volume ratio (volume / volume_sma)."),
        EntryParamSpec(f"{entry_id}_filter_oi_ratio_4h_min_enabled", "filters", "bool", False, description="Enable generic minimum OI/SMA ratio filter."),
        EntryParamSpec(f"{entry_id}_filter_oi_ratio_4h_min", "filters", "float", 0.0, 0.0, 10.0, 0.05, description="Generic minimum OI ratio (oi_4h / oi_sma_4h)."),
        EntryParamSpec(f"{entry_id}_filter_oi_ratio_4h_max_enabled", "filters", "bool", False, description="Enable generic maximum OI/SMA ratio filter."),
        EntryParamSpec(f"{entry_id}_filter_oi_ratio_4h_max", "filters", "float", 10.0, 0.0, 10.0, 0.05, description="Generic maximum OI ratio (oi_4h / oi_sma_4h)."),
        EntryParamSpec(f"{entry_id}_filter_oi_4h_min_enabled", "filters", "bool", False, description="Enable generic minimum raw OI filter."),
        EntryParamSpec(f"{entry_id}_filter_oi_4h_min", "filters", "float", 0.0, 0.0, 2000000000.0, 50000000.0, description="Generic minimum raw OI."),
        EntryParamSpec(f"{entry_id}_filter_oi_above_sma_enabled", "filters", "bool", False, description="Require oi_4h >= oi_sma_4h (equivalent to oi_ratio_4h >= 1)."),
        EntryParamSpec(f"{entry_id}_filter_atr_std_ratio_max_enabled", "filters", "bool", False, description="Enable generic maximum ATR/STD ratio filter."),
        EntryParamSpec(f"{entry_id}_filter_atr_std_ratio_max", "filters", "float", 50.0, 0.01, 50.0, 0.05, description="Generic maximum ATR/STD ratio."),
        EntryParamSpec(f"{entry_id}_filter_close_above_bb_max_enabled", "filters", "bool", False, description="Enable generic upper Bollinger max-close guard."),
        EntryParamSpec(f"{entry_id}_filter_close_above_bb_max_std", "filters", "float", 3.0, 0.0, 8.0, 0.1, description="Generic upper Bollinger multiplier for prior close."),
        EntryParamSpec(
            f"{entry_id}_filter_bar1_green_upper_wick_lt_body_enabled",
            "filters",
            "bool",
            False,
            description="Require on bar[1]: green body and |high-close| < |close-open|.",
        ),
        EntryParamSpec(f"{entry_id}_filter_body_expansion_enabled", "filters", "bool", False, description="Enable generic body-expansion filter: body(bar1) > body(bar[lookback])."),
        EntryParamSpec(f"{entry_id}_filter_body_compare_lookback", "filters", "int", 2, 2, 20, 1, description="Lookback bar index used by generic body-expansion filter."),
        EntryParamSpec(
            f"{entry_id}_filter_open_above_bar4_close_enabled",
            "filters",
            "bool",
            False,
            description="Require bar[1] open above bar[4] close.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_flow_state",
            "filters",
            "enum",
            "off",
            choices=[
                "off",
                "trend_continuation",
                "short_cover",
                "bearish_continuation",
                "long_liquidation",
                "neutral",
            ],
            description="Require OI/price flow state from lookback returns.",
        ),
        EntryParamSpec(
            f"{entry_id}_filter_forbid_oi_flow_state",
            "filters",
            "enum",
            "off",
            choices=[
                "off",
                "trend_continuation",
                "short_cover",
                "bearish_continuation",
                "long_liquidation",
                "neutral",
            ],
            description="Reject entries when OI/price flow state matches this value.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_flow_lookback",
            "filters",
            "int",
            3,
            1,
            48,
            1,
            description="Lookback bars used for OI/price flow return classification.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_flow_price_min_pct",
            "filters",
            "float",
            0.0,
            0.0,
            20.0,
            0.05,
            description="Minimum absolute price return % to classify up/down flow.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_flow_oi_min_pct",
            "filters",
            "float",
            0.0,
            0.0,
            20.0,
            0.05,
            description="Minimum absolute open-interest return % to classify up/down flow.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_funding_state",
            "filters",
            "enum",
            "off",
            choices=[
                "off",
                "long_crowded",
                "short_crowded",
                "deleveraging",
                "neutral",
            ],
            description="Require combined OI/funding state.",
        ),
        EntryParamSpec(
            f"{entry_id}_filter_forbid_oi_funding_state",
            "filters",
            "enum",
            "off",
            choices=[
                "off",
                "long_crowded",
                "short_crowded",
                "deleveraging",
                "neutral",
            ],
            description="Reject entries when OI/funding state matches this value.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_funding_lookback",
            "filters",
            "int",
            3,
            1,
            48,
            1,
            description="Lookback bars for OI return used by OI/funding state.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_funding_oi_up_min_pct",
            "filters",
            "float",
            0.0,
            0.0,
            20.0,
            0.05,
            description="Minimum positive OI return % to classify crowded states.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_funding_oi_down_min_pct",
            "filters",
            "float",
            0.0,
            0.0,
            20.0,
            0.05,
            description="Minimum negative OI return % to classify deleveraging state.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_funding_pos_min",
            "filters",
            "float",
            0.0,
            0.0,
            0.02,
            0.00005,
            description="Minimum positive funding rate to classify long_crowded.",
        ),
        EntryParamSpec(
            f"{entry_id}_oi_funding_neg_min",
            "filters",
            "float",
            0.0,
            0.0,
            0.02,
            0.00005,
            description="Minimum absolute negative funding rate to classify short_crowded.",
        ),
        EntryParamSpec(f"{entry_id}_filter_max_bar_range_atr_enabled", "filters", "bool", False, description="Enable max bar-range/ATR filter."),
        EntryParamSpec(f"{entry_id}_filter_max_bar_range_atr", "filters", "float", 10.0, 0.0, 10.0, 0.05, description="Maximum previous bar range in ATR units."),
        EntryParamSpec(f"{entry_id}_filter_min_bar_range_atr_enabled", "filters", "bool", False, description="Enable min bar-range/ATR filter."),
        EntryParamSpec(f"{entry_id}_filter_min_bar_range_atr", "filters", "float", 0.0, 0.0, 10.0, 0.05, description="Minimum previous bar range in ATR units."),
    ]


MODULE_CLASS_PARAMS: Dict[str, Dict[str, List[EntryParamSpec]]] = {
    "entry_1": {
        "idea": [
            EntryParamSpec("entry_1_trail_lookback_1", "idea", "int", 6, 1, 50, 1, "Primary trail lookback index for SFP check."),
            EntryParamSpec("entry_1_trail_lookback_2", "idea", "int", 7, 1, 50, 1, "Secondary trail lookback index for SFP check."),
        ],
        "confirmation": [
            EntryParamSpec("entry_1_vol_fac", "confirmation", "float", 2.0, 0.2, 6.0, 0.05, "Volume confirmation multiplier."),
            EntryParamSpec("entry_1_require_red_daily", "confirmation", "bool", True, description="Require daily candle to close red."),
        ],
        "filters": [
            EntryParamSpec("entry_1_require_market_bearish", "filters", "bool", True, description="Require bearish market regime."),
        ],
        "execution": [
            EntryParamSpec("entry_1_atr_fac", "execution", "float", 1.0, 0.1, 10.0, 0.05, "Legacy stop ATR multiplier."),
        ],
    },
    "entry_2": {
        "idea": [
            EntryParamSpec("entry_2_swing_depth", "idea", "int", 40, 8, 200, 1, "Swing scan depth used by the base trigger."),
            EntryParamSpec("entry_2_entry_buffer_atr", "idea", "float", 0.05, 0.0, 1.0, 0.01, "ATR buffer above/below swing levels for entry placement."),
        ],
        "confirmation": [],
        "filters": [
            EntryParamSpec("entry_2_max_natr", "filters", "float", 1.0, 0.2, 6.0, 0.1, "Maximum NATR filter."),
            EntryParamSpec("entry_2_min_rsi_4h", "filters", "int", 50, 0, 100, 1, "Upper RSI-4H threshold (legacy comparator <)."),
            EntryParamSpec("entry_2_min_rsi_d", "filters", "int", 80, 0, 100, 1, "Minimum daily RSI."),
            EntryParamSpec("entry_2_min_natr", "filters", "float", 1.0, 0.2, 6.0, 0.1, "Minimum NATR filter."),
            EntryParamSpec("entry_2_use_min_natr", "filters", "bool", False, description="Enable minimum-NATR gate for long branch."),
            EntryParamSpec("entry_2_enable_short", "filters", "bool", False, description="Enable short-side branch for entry_2."),
            EntryParamSpec("entry_2_min_rsi_4h_short", "filters", "int", 50, 0, 100, 1, "Short branch minimum RSI-4H."),
            EntryParamSpec("entry_2_min_rsi_d_short", "filters", "int", 50, 0, 100, 1, "Short branch minimum RSI-D."),
            EntryParamSpec("entry_2_require_not_bearish_long", "filters", "bool", True, description="Require non-bearish regime for long branch."),
            EntryParamSpec("entry_2_require_not_trending_long", "filters", "bool", True, description="Require non-trending market dynamic for long branch."),
            EntryParamSpec("entry_2_require_not_bullish_short", "filters", "bool", True, description="Require non-bullish regime for short branch."),
            EntryParamSpec("entry_2_require_not_trending_short", "filters", "bool", True, description="Require non-trending market dynamic for short branch."),
        ],
        "execution": [
            EntryParamSpec("entry_2_expected_exit_slippage_pct", "execution", "float", 0.0015, 0.0, 0.02, 0.0001, "Expected exit slippage used for stop-size recalculation."),
            EntryParamSpec("entry_2_expected_entry_slippage_pct", "execution", "float", 0.0015, 0.0, 0.02, 0.0001, "Expected entry slippage used for stop-size recalculation."),
        ],
    },
    "entry_3": {
        "idea": [],
        "confirmation": [
            EntryParamSpec("entry_3_use_vol_filter", "confirmation", "bool", False, description="Enable optional volume filter."),
            EntryParamSpec("entry_3_vol_fac", "confirmation", "float", 2.0, 0.2, 6.0, 0.05, "Volume confirmation multiplier."),
            EntryParamSpec("entry_3_require_red_trigger_bar", "confirmation", "bool", True, description="Require trigger candle to close red."),
        ],
        "filters": [
            EntryParamSpec("entry_3_rsi_4h", "filters", "int", 50, 0, 100, 1, "Minimum RSI-4H filter."),
            EntryParamSpec("entry_3_max_natr", "filters", "float", 2.0, 0.2, 6.0, 0.1, "Maximum NATR filter."),
            EntryParamSpec("entry_3_rsi_d_min", "filters", "int", 50, 0, 100, 1, "Minimum daily RSI filter."),
            EntryParamSpec("entry_3_max_std_atr", "filters", "float", 4.0, 0.2, 20.0, 0.1, "Maximum std/ATR ratio filter."),
            EntryParamSpec("entry_3_require_market_bullish", "filters", "bool", True, description="Require bullish market regime."),
            EntryParamSpec("entry_3_require_not_trending", "filters", "bool", True, description="Require non-trending market dynamic."),
        ],
        "execution": [
            EntryParamSpec("entry_3_atr_fac", "execution", "float", 1.0, 0.1, 10.0, 0.05, "Legacy ATR entry offset."),
            EntryParamSpec("entry_3_stop_atr_mult", "execution", "float", 1.0, 0.1, 10.0, 0.05, "Legacy ATR stop multiplier from entry."),
        ],
    },
    "entry_4": {
        "idea": [
            EntryParamSpec(
                "entry_4_breakout_atr_mult",
                "idea",
                "float",
                1.0,
                0.0,
                10.0,
                0.05,
                "Prior close must be above BB middle + ATR * multiplier.",
            ),
            EntryParamSpec(
                "entry_4_rearm_lookback",
                "idea",
                "int",
                300,
                20,
                4000,
                1,
                "Bars scanned backwards to find re-arm wick below BB middle.",
            ),
        ],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_5": {
        "idea": [
            EntryParamSpec("entry_5_trail_1_period", "idea", "int", 10, 2, 120, 1, "Breakdown lookback period."),
            EntryParamSpec("entry_5_trail_2_period", "idea", "int", 10, 2, 120, 1, "Open-above-trail lookback period."),
        ],
        "confirmation": [
            EntryParamSpec("entry_5_vol_fac", "confirmation", "float", 2.0, 0.2, 6.0, 0.05, "Volume confirmation multiplier."),
        ],
        "filters": [
            EntryParamSpec("entry_5_rsi_d", "filters", "int", 40, 0, 100, 1, "Maximum daily RSI filter."),
            EntryParamSpec("entry_5_rsi_4h", "filters", "int", 80, 0, 100, 1, "Maximum RSI-4H filter."),
        ],
        "execution": [
            EntryParamSpec("entry_5_atr_fac", "execution", "float", 0.8, 0.1, 10.0, 0.05, "Legacy ATR stop multiplier."),
        ],
    },
    "entry_6": {
        "idea": [
            EntryParamSpec("entry_6_swing_depth", "idea", "int", 40, 5, 200, 1, "Swing scan depth."),
        ],
        "confirmation": [
            EntryParamSpec("entry_6_short_max_bar_range_atr", "confirmation", "float", 1.0, 0.1, 10.0, 0.05, "Maximum short-trigger bar range in ATR units."),
        ],
        "filters": [
            EntryParamSpec("entry_6_rsi_4h_max", "filters", "int", 90, 0, 100, 1, "Upper RSI-4H threshold."),
            EntryParamSpec("entry_6_rsi_4h_min", "filters", "int", 75, 0, 100, 1, "Lower RSI-4H threshold."),
            EntryParamSpec("entry_6_max_natr", "filters", "float", 2.0, 0.2, 6.0, 0.1, "Maximum NATR filter."),
            EntryParamSpec("entry_6_require_not_bearish_long", "filters", "bool", True, description="Require non-bearish regime for long branch."),
            EntryParamSpec("entry_6_require_short_open_above_ema", "filters", "bool", True, description="Require short trigger bar open above EMA."),
        ],
        "execution": [
            EntryParamSpec("entry_6_atr_fac", "execution", "float", 5.0, 0.1, 10.0, 0.05, "Legacy ATR stop extension."),
        ],
    },
    "entry_7": {
        "idea": [],
        "confirmation": [
            EntryParamSpec("entry_7_use_std_filter", "confirmation", "bool", False, description="Enable optional body-vs-ATR filter."),
            EntryParamSpec("entry_7_use_rsi_filter", "confirmation", "bool", False, description="Enable optional RSI-4H filter."),
            EntryParamSpec("entry_7_use_vol_filter", "confirmation", "bool", False, description="Enable optional volume filter."),
            EntryParamSpec("entry_7_std_fac", "confirmation", "float", 1.0, 0.2, 4.0, 0.1, "Body-vs-ATR factor."),
            EntryParamSpec("entry_7_4h_rsi", "confirmation", "float", 2.5, 0.0, 100.0, 0.5, "RSI-4H threshold."),
            EntryParamSpec("entry_7_vol_fac", "confirmation", "float", 2.0, 0.2, 6.0, 0.05, "Volume confirmation multiplier."),
            EntryParamSpec("entry_7_require_prev_body_gt_lower_wick", "confirmation", "bool", True, description="Require previous candle body to exceed lower wick."),
            EntryParamSpec("entry_7_require_sfp_upper_wick_gt_body", "confirmation", "bool", True, description="Require SFP candle upper wick to exceed body."),
        ],
        "filters": [
            EntryParamSpec("entry_7_require_not_trending", "filters", "bool", True, description="Require non-trending market dynamic."),
        ],
        "execution": [],
    },
    "entry_8": {
        "idea": [],
        "confirmation": [
            EntryParamSpec("entry_8_vol_fac", "confirmation", "float", 2.0, 0.2, 6.0, 0.05, "Volume ratio cap multiplier."),
        ],
        "filters": [
            EntryParamSpec("entry_8_require_ranging_regime", "filters", "bool", True, description="Require ranging market dynamic."),
        ],
        "execution": [],
    },
    "entry_9": {
        "idea": [
            EntryParamSpec("entry_9_std", "idea", "float", 1.0, 0.2, 4.0, 0.1, "Reclaim level standard-deviation factor."),
        ],
        "confirmation": [
            EntryParamSpec("entry_9_require_lower_open", "confirmation", "bool", True, description="Require trigger candle open below prior open."),
        ],
        "filters": [
            EntryParamSpec("entry_9_4h_rsi", "filters", "int", 50, 0, 100, 1, "Maximum RSI-4H filter."),
            EntryParamSpec("entry_9_require_ranging_regime", "filters", "bool", True, description="Require ranging market dynamic."),
        ],
        "execution": [
            EntryParamSpec("entry_9_atr", "execution", "float", 2.0, 0.1, 10.0, 0.05, "Legacy ATR stop multiplier."),
        ],
    },
    "entry_10": {
        "idea": [],
        "confirmation": [],
        "filters": [
            EntryParamSpec("entry_10_natr", "filters", "float", 2.0, 0.2, 6.0, 0.1, "Maximum NATR filter."),
            EntryParamSpec("entry_10_natr_ath", "filters", "float", 2.0, 0.2, 6.0, 0.1, "Maximum NATR filter for ATH branch."),
            EntryParamSpec("entry_10_rsi_4h", "filters", "int", 50, 0, 100, 1, "Maximum RSI-4H filter."),
            EntryParamSpec("entry_10_rsi_d_min", "filters", "int", 50, 0, 100, 1, "Minimum daily RSI filter."),
            EntryParamSpec("entry_10_vol_cap_mult", "filters", "float", 2.6, 0.2, 8.0, 0.05, "Maximum volume cap multiplier (volume_sma * x > volume_now)."),
            EntryParamSpec("entry_10_require_body_expansion", "filters", "bool", True, description="Optional structural gate: require trigger candle body to exceed prior body."),
            EntryParamSpec("entry_10_require_open_above_bar4_close", "filters", "bool", True, description="Optional structural gate for ATH branch: require trigger open above bar-4 close."),
            EntryParamSpec("entry_10_require_not_bearish", "filters", "bool", True, description="Require non-bearish market regime."),
            EntryParamSpec("entry_10_require_not_trending", "filters", "bool", True, description="Require non-trending market dynamic."),
        ],
        "execution": [
            EntryParamSpec("entry_10_sl_atr_mult", "execution", "float", 0.2, 0.0, 5.0, 0.05, "Legacy stop offset from prior low in ATR units."),
        ],
    },
    "entry_11": {
        "idea": [
            EntryParamSpec("entry_11_atr", "idea", "float", 3.0, 0.1, 10.0, 0.05, "Body-size ATR threshold."),
        ],
        "confirmation": [
            EntryParamSpec("entry_11_vol", "confirmation", "float", 3.0, 0.2, 6.0, 0.05, "Volume ratio cap multiplier."),
        ],
        "filters": [
            EntryParamSpec("entry_11_natr", "filters", "float", 3.0, 0.2, 6.0, 0.1, "Maximum NATR filter."),
        ],
        "execution": [],
    },
    "entry_12": {
        "idea": [
            EntryParamSpec("entry_12_atr", "idea", "float", 3.0, 0.1, 10.0, 0.05, "Dump-candle ATR threshold."),
        ],
        "confirmation": [
            EntryParamSpec("entry_12_rsi_4h", "confirmation", "int", 3, 0, 100, 1, "Minimum RSI-4H alternative confirmation."),
            EntryParamSpec("entry_12_max_rsi_4h", "confirmation", "int", 90, 0, 100, 1, "Legacy naming; mapped to daily RSI threshold."),
            EntryParamSpec("entry_12_vol", "confirmation", "float", 3.0, 0.2, 6.0, 0.05, "Volume ratio cap multiplier."),
            EntryParamSpec("entry_12_require_structure_1", "confirmation", "bool", True, description="Require primary reversal structure pattern."),
            EntryParamSpec("entry_12_require_structure_2", "confirmation", "bool", True, description="Require secondary reversal structure pattern."),
        ],
        "filters": [
            EntryParamSpec("entry_12_require_not_trending", "filters", "bool", True, description="Require non-trending market dynamic."),
        ],
        "execution": [],
    },
    "entry_15": {
        "idea": [
            EntryParamSpec("entry_15_squeeze_lookback", "idea", "int", 6, 3, 20, 1, "Compression lookback window."),
            EntryParamSpec("entry_15_broad_core", "idea", "bool", False, description="Use broad core trigger only; move RSI/NATR/volume checks to optional confirmations/filters."),
            EntryParamSpec("entry_15_squeeze_range_atr", "idea", "float", 1.0, 0.2, 4.0, 0.05, "Maximum bar-range/ATR during squeeze window."),
            EntryParamSpec("entry_15_breakout_buffer_atr", "idea", "float", 0.1, 0.0, 2.0, 0.05, "ATR buffer above local high required for breakout."),
        ],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_16": {
        "idea": [
            EntryParamSpec("entry_16_dump_atr", "idea", "float", 2.0, 0.2, 8.0, 0.05, "Dump candle size in ATR units."),
            EntryParamSpec("entry_16_broad_core", "idea", "bool", False, description="Use broad core trigger only; move RSI/NATR/confirmation checks to optional confirmations/filters."),
            EntryParamSpec("entry_16_band_std", "idea", "float", 1.5, 0.2, 4.0, 0.1, "Lower-band overshoot in standard deviations."),
            EntryParamSpec("entry_16_reclaim_frac", "idea", "float", 0.5, 0.1, 1.0, 0.05, "Required reclaim fraction of dump candle."),
        ],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_17": {
        "idea": [
            EntryParamSpec("entry_17_break_lookback", "idea", "int", 6, 2, 20, 1, "Lookback for breakout/failure reference high."),
            EntryParamSpec("entry_17_fail_close_buffer_atr", "idea", "float", 0.1, 0.0, 2.0, 0.05, "ATR buffer below breakout level for failure close."),
            EntryParamSpec("entry_17_wick_excess_atr", "idea", "float", 0.2, 0.0, 3.0, 0.05, "Minimum wick excess in ATR units above breakout level."),
        ],
        "confirmation": [],
        "filters": [],
        "execution": [
            EntryParamSpec("entry_17_add_trigger_open_limit", "execution", "bool", False, description="Add a second trigger-open limit order."),
            EntryParamSpec("entry_17_limit_only_trigger_open", "execution", "bool", False, description="Open only via trigger-open order and skip base market leg."),
            EntryParamSpec(
                "entry_17_trigger_open_order_type",
                "execution",
                "enum",
                "Limit",
                choices=["legacy", "Market", "Limit", "StopLimit", "StopLoss"],
                description="Order type used for trigger-open leg.",
            ),
        ],
    },
    "entry_18": {
        "idea": [
            EntryParamSpec("entry_18_reject_lookback", "idea", "int", 4, 2, 20, 1, "Lookback for range-edge rejection reference low."),
            EntryParamSpec("entry_18_reclaim_buffer_atr", "idea", "float", 0.05, 0.0, 2.0, 0.05, "ATR reclaim buffer above rejected level."),
            EntryParamSpec("entry_18_tail_ratio_min", "idea", "float", 1.2, 0.5, 5.0, 0.05, "Minimum lower-tail/body ratio."),
        ],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_19": {
        "idea": [
            EntryParamSpec("entry_19_body_atr_min", "idea", "float", 1.0, 0.1, 6.0, 0.05, "Minimum impulse body in ATR units."),
            EntryParamSpec("entry_19_broad_core", "idea", "bool", False, description="Use broad core trigger only; move RSI/NATR/regime/volume checks to optional confirmations/filters."),
            EntryParamSpec("entry_19_breakout_lookback", "idea", "int", 5, 2, 30, 1, "Lookback for continuation breakout reference high."),
        ],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_20": {
        "idea": [
            EntryParamSpec("entry_20_break_lookback", "idea", "int", 6, 2, 30, 1, "Lookback for initial breakout reference high."),
            EntryParamSpec("entry_20_broad_core", "idea", "bool", False, description="Use broad core trigger only; move RSI/NATR/regime/volume checks to optional confirmations/filters."),
            EntryParamSpec("entry_20_pullback_max_atr", "idea", "float", 1.0, 0.1, 5.0, 0.05, "Maximum pullback depth in ATR after breakout."),
            EntryParamSpec("entry_20_reclaim_buffer_atr", "idea", "float", 0.1, 0.0, 2.0, 0.05, "ATR reclaim buffer around breakout level."),
        ],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_21": {
        "idea": [
            EntryParamSpec("entry_21_crush_lookback", "idea", "int", 8, 3, 30, 1, "Lookback window for low-volatility crush."),
            EntryParamSpec("entry_21_broad_core", "idea", "bool", False, description="Use broad core trigger only; move confirmation/regime/volume checks to optional confirmations/filters."),
            EntryParamSpec("entry_21_crush_range_atr", "idea", "float", 1.0, 0.1, 4.0, 0.05, "Maximum bar-range/ATR during crush."),
            EntryParamSpec("entry_21_crush_natr_max", "idea", "float", 1.2, 0.1, 6.0, 0.1, "Maximum NATR during crush setup."),
            EntryParamSpec("entry_21_fail_buffer_atr", "idea", "float", 0.1, 0.0, 2.0, 0.05, "ATR buffer for failed breakout close."),
        ],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_22": {
        "idea": [
            EntryParamSpec("entry_22_impulse_body_atr", "idea", "float", 1.5, 0.1, 8.0, 0.05, "Minimum bearish impulse body in ATR."),
            EntryParamSpec("entry_22_broad_core", "idea", "bool", False, description="Use broad core trigger only; move RSI/NATR/regime/volume checks to optional confirmations/filters."),
            EntryParamSpec("entry_22_absorption_reclaim_frac", "idea", "float", 0.5, 0.1, 1.0, 0.05, "Required reclaim fraction of impulse body."),
        ],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_23": {
        "idea": [],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_23_secondary": {
        "idea": [],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
    "entry_24": {
        "idea": [],
        "confirmation": [],
        "filters": [],
        "execution": [],
    },
}


def get_entry_parameter_catalog() -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    catalog: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for entry_id in ENTRY_IDS:
        module_filters = list(MODULE_CLASS_PARAMS.get(entry_id, {}).get("filters", []))
        module_confirmations = list(MODULE_CLASS_PARAMS.get(entry_id, {}).get("confirmation", []))
        generic_filters = list(_generic_filter_specs(entry_id))
        generic_confirmations = list(_generic_confirmation_specs(entry_id))
        classes = {
            "activation": list(_activation_specs(entry_id)),
            "idea": list(MODULE_CLASS_PARAMS.get(entry_id, {}).get("idea", [])),
            # Confirmation parameters are intentionally merged into filters.
            "confirmation": [],
            "filters": module_filters + module_confirmations + generic_filters + generic_confirmations,
            "execution": list(_execution_specs(entry_id)) + list(MODULE_CLASS_PARAMS.get(entry_id, {}).get("execution", [])),
        }
        catalog[entry_id] = {}
        for class_name in PARAM_CLASSES:
            specs = classes.get(class_name, [])
            catalog[entry_id][class_name] = [
                {
                    "name": spec.name,
                    "class": class_name,
                    "type": spec.value_type,
                    "default": spec.default,
                    "min": spec.minimum,
                    "max": spec.maximum,
                    "step": spec.step,
                    "choices": spec.choices,
                    "description": spec.description,
                }
                for spec in specs
            ]
    return catalog


def all_catalog_param_names() -> List[str]:
    names: List[str] = []
    for entry_catalog in get_entry_parameter_catalog().values():
        for class_specs in entry_catalog.values():
            for spec in class_specs:
                names.append(spec["name"])
    # dedupe + deterministic ordering
    return sorted(set(names))


def _is_schema_v1(config: Dict[str, Any]) -> bool:
    if "schema_version" in config:
        return True
    if "modules" in config:
        return True
    for key, value in config.items():
        if key in ENTRY_IDS and isinstance(value, dict):
            return True
    return False


def _flatten_schema_modules(modules: Dict[str, Any]) -> Dict[str, Any]:
    flat: Dict[str, Any] = {}
    for module_id, payload in modules.items():
        if module_id not in ENTRY_IDS or not isinstance(payload, dict):
            continue

        activation = payload.get("activation", {})
        if isinstance(activation, dict):
            if "enabled" in activation:
                flat[module_id] = activation["enabled"]
            if "allow_long" in activation:
                flat[f"{module_id}_allow_long"] = activation["allow_long"]
            if "allow_short" in activation:
                flat[f"{module_id}_allow_short"] = activation["allow_short"]

        for section_name in ("idea", "confirmation", "filters", "execution"):
            section = payload.get(section_name, {})
            if isinstance(section, dict):
                params = section.get("params", section)
                if isinstance(params, dict):
                    for key, value in params.items():
                        flat[key] = value
    return flat


def flatten_entry_module_config(config: Any) -> Dict[str, Any]:
    if config is None:
        return {}
    if not isinstance(config, dict):
        return {}

    if _is_schema_v1(config):
        modules: Dict[str, Any] = {}
        if isinstance(config.get("modules"), dict):
            modules.update(config["modules"])
        for entry_id in ENTRY_IDS:
            payload = config.get(entry_id)
            if isinstance(payload, dict):
                modules[entry_id] = payload
        flat = _flatten_schema_modules(modules)
        # allow explicit top-level legacy keys to override schema-derived values.
        for key, value in config.items():
            if key in ("schema_version", "modules"):
                continue
            if key in ENTRY_IDS and isinstance(value, dict):
                continue
            flat[key] = value
        return flat

    return dict(config)


def find_deprecated_legacy_keys(config: Dict[str, Any]) -> List[str]:
    flat = flatten_entry_module_config(config)
    return sorted([name for name in DEPRECATED_LEGACY_PARAMS if name in flat])


def iter_catalog_specs(entry_id: Optional[str] = None, param_class: Optional[str] = None) -> Iterable[Dict[str, Any]]:
    catalog = get_entry_parameter_catalog()
    entry_ids = [entry_id] if entry_id else ENTRY_IDS
    for module_id in entry_ids:
        entry_catalog = catalog.get(module_id, {})
        class_names = [param_class] if param_class else PARAM_CLASSES
        for class_name in class_names:
            for spec in entry_catalog.get(class_name, []):
                yield dict(spec)
