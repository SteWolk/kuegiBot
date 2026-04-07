import argparse
import concurrent.futures
import copy
import ctypes
import json
import logging
import math
import multiprocessing as mp
import os
import re
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import talib
import plotly.graph_objects as go
from plotly.subplots import make_subplots

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from kuegi_bot.backtest_engine import BackTest
from kuegi_bot.bots.MultiStrategyBot import MultiStrategyBot
from kuegi_bot.bots.strategies.entry_filters import DayOfWeekFilter
from kuegi_bot.bots.strategies.exit_modules import ATRrangeSL, FixedPercentage, TimedExit
from kuegi_bot.bots.strategies.strategy_one import StrategyOne
from kuegi_bot.bots.strategies.trend_indicator_engine import TATrendStrategyIndicator
from kuegi_bot.bots.strategies.trend_enums import (
    OIFundingState,
    OIPriceFlowState,
    oi_funding_state_from_metrics,
    oi_price_flow_state_from_returns,
)
from kuegi_bot.bots.strategies.trend_indicator_provider import build_trend_indicator_provider
from kuegi_bot.bots.strategies.strategy_one_entry_schema import ENTRY_IDS, get_entry_parameter_catalog
from kuegi_bot.utils import log as botlog
from kuegi_bot.utils.helper import load_bars, load_funding, load_open_interest
from kuegi_bot.utils.trading_classes import Symbol

DEFAULT_SL_ATR_MULT = 0.8
PREPARATION_TARGET_SWEEP_POINTS = 18
PREPARATION_MIN_SWEEP_POINTS = 16
PREPARATION_MAX_SWEEP_POINTS = 20

BASE_ENTRY_MODULE_CONFIG = {entry_id: False for entry_id in ENTRY_IDS}


def get_symbol(pair: str):
    if pair == "BTCUSD":
        return Symbol(baseCoin="BTC", symbol="BTCUSD", isInverse=True, tickSize=0.1, lotSize=1.0, makerFee=0.0002, takerFee=0.00055, quantityPrecision=2, pricePrecision=2)
    if pair == "XRPUSD":
        return Symbol(baseCoin="XRP", symbol="XRPUSD", isInverse=True, tickSize=0.0001, lotSize=0.01, makerFee=0.0002, takerFee=0.00055, quantityPrecision=2, pricePrecision=4)
    if pair == "ETHUSD":
        return Symbol(baseCoin="ETH", symbol="ETHUSD", isInverse=True, tickSize=0.05, lotSize=1.0, makerFee=0.0002, takerFee=0.00055, quantityPrecision=2, pricePrecision=2)
    if pair == "BTCUSDT":
        return Symbol(baseCoin="USDT", symbol="BTCUSDT", isInverse=False, tickSize=0.1, lotSize=0.001, makerFee=0.0002, takerFee=0.00055, quantityPrecision=3, pricePrecision=2)
    raise ValueError("Unsupported pair: " + pair)


def normalize_exchange(exchange: str, pair: str) -> str:
    if exchange == "bybit" and "USDT" in pair:
        return "bybit-linear"
    return exchange


def metric(metrics: Dict[str, Any], key: str, default: float = 0.0) -> float:
    if not isinstance(metrics, dict):
        return float(default)
    try:
        return float(metrics.get(key, default))
    except (TypeError, ValueError):
        return float(default)


def available_ram_gb() -> Optional[float]:
    try:
        if os.name == "nt":
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)) == 0:
                return None
            return float(stat.ullAvailPhys) / (1024.0 ** 3)

        pages = os.sysconf("SC_AVPHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return float(pages * page_size) / (1024.0 ** 3)
    except Exception:
        return None


def rsi_max_sweep_values() -> List[float]:
    values: List[float] = []
    v = 100.0
    while v >= 0.0 - 1e-12:
        values.append(round(v, 2))
        v -= 5.0
    return values


SL_REF_SOURCE_VALUES = ("off", "open", "close", "high", "low", "min_oc")
ENTRY_PARAM_CATALOG = get_entry_parameter_catalog()
DEFAULT_ENTRY_ID = "entry_23"
DISALLOWED_CLI_PARAM_KEYS = {
    "sl_ref_bar1_source",
    "sl_ref_bar2_source",
    "sl_ref_bar3_source",
    "sl_ref_bar4_source",
    "sl_ref_bar5_source",
    "stop_ref_bar_1_source",
    "stop_ref_bar_2_source",
    "stop_ref_bar_3_source",
    "stop_ref_bar_4_source",
    "stop_ref_bar_5_source",
}
VIRTUAL_DIMENSION_IDS = ("sl_ref_profile",)

OBJECTIVE_PROFIT = "profit"
OBJECTIVE_REL = "rel"
OBJECTIVE_REL2_SIGNED = "rel2_signed"
OBJECTIVE_PROFIT_FLOOR_DD = "profit_floor_dd"
OBJECTIVE_PROFIT_DD_SOFTCAP = "profit_dd_softcap"
OBJECTIVE_KEYS = (
    OBJECTIVE_PROFIT,
    OBJECTIVE_REL,
    OBJECTIVE_REL2_SIGNED,
    OBJECTIVE_PROFIT_FLOOR_DD,
    OBJECTIVE_PROFIT_DD_SOFTCAP,
)
OBJECTIVE_ALIASES = {
    "profit": OBJECTIVE_PROFIT,
    "rel": OBJECTIVE_REL,
    "rel2_signed": OBJECTIVE_REL2_SIGNED,
    "rel2-signed": OBJECTIVE_REL2_SIGNED,
    "signed_rel2": OBJECTIVE_REL2_SIGNED,
    "signed-rel2": OBJECTIVE_REL2_SIGNED,
    "profit_floor_dd": OBJECTIVE_PROFIT_FLOOR_DD,
    "profit-floor-dd": OBJECTIVE_PROFIT_FLOOR_DD,
    "profitddsoftcap": OBJECTIVE_PROFIT_DD_SOFTCAP,
    "profit_dd_softcap": OBJECTIVE_PROFIT_DD_SOFTCAP,
    "profit-dd-softcap": OBJECTIVE_PROFIT_DD_SOFTCAP,
}

DIM_CLASS_TOKEN_TO_SCHEMA = {
    "activation": "activation",
    "idea": "idea",
    "confirmation": "confirmation",
    "filter": "filters",
    "execution": "execution",
}
DIM_CLASS_SCHEMA_TO_TOKEN = {
    "activation": "activation",
    "idea": "idea",
    "confirmation": "confirmation",
    "filters": "filter",
    "execution": "execution",
}


def parse_scalar(raw: str) -> Any:
    txt = str(raw).strip()
    low = txt.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("none", "null"):
        return None
    if re.fullmatch(r"[+-]?\d+", txt):
        try:
            return int(txt)
        except Exception:
            pass
    if re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)", txt):
        try:
            return float(txt)
        except Exception:
            pass
    return txt


def sl_ref_profile_values() -> List[str]:
    values = ["off"]
    for lookback in range(1, 6):
        values.append(f"low_{lookback}")
        values.append(f"min_oc_{lookback}")
    return values


def _grid_relax_values(sweep: List[float], current: float, steps: int = 4) -> List[float]:
    if len(sweep) == 0:
        return []
    c = round(float(current), 2)
    if c in sweep:
        idx = sweep.index(c)
    else:
        idx = min(range(len(sweep)), key=lambda i: abs(sweep[i] - c))
    start = max(0, idx - int(steps))
    loosen_values = sweep[start : idx + 1]
    # Prefer loosen direction. If current is already at the loosest edge,
    # fall back to tightening so re-checks still evaluate alternatives.
    if len(loosen_values) > 1:
        return loosen_values
    end = min(len(sweep), idx + int(steps) + 1)
    return sweep[idx:end]


@dataclass
class TrialResult:
    metrics: Dict[str, Any]
    elapsed_s: float
    early_stopped: bool
    early_stop_reason: Optional[str]


@dataclass
class Benchmark:
    params: Dict[str, Any]
    metrics: Dict[str, Any]
    label: str


@dataclass
class ParameterConstraint:
    left_kind: str  # "dim" | "lit"
    left_value: Any
    op: str
    right_kind: str  # "dim" | "lit"
    right_value: Any
    raw: str


@dataclass
class MetricGate:
    metric_key: str
    op: str
    value: float
    raw: str


class EntryStagedOptimizer:
    def __init__(self, args):
        self.args = args
        self.entry_id = str(getattr(args, "entry_id", DEFAULT_ENTRY_ID) or "").strip().lower()
        if self.entry_id not in ENTRY_PARAM_CATALOG:
            raise ValueError(
                "Unsupported --entry-id '%s'. Allowed: %s"
                % (self.entry_id, ",".join(sorted(ENTRY_PARAM_CATALOG.keys())))
            )
        entry_catalog = ENTRY_PARAM_CATALOG[self.entry_id]
        self.entry_param_specs: Dict[str, Dict[str, Any]] = {}
        for class_name in ("activation", "idea", "confirmation", "filters", "execution"):
            for spec in entry_catalog.get(class_name, []):
                self.entry_param_specs[str(spec["name"])] = dict(spec)
        self.entry_has_idea = "idea" in entry_catalog
        self.entry_has_confirmation = len(list(entry_catalog.get("confirmation", []))) > 0
        if not self.entry_has_idea:
            raise ValueError(
                "Entry '%s' must define an idea class in strategy schema."
                % self.entry_id
            )

        self.out_dir = Path(args.out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.run_name = str(args.run_name).strip()
        if self.run_name == "":
            self.run_name = self.entry_id + "_staged_" + datetime.now().strftime("%Y%m%d_%H%M%S")

        self.events_path = self.out_dir / f"{self.run_name}.events.jsonl"
        self.final_path = self.out_dir / f"{self.run_name}.final.json"
        self.logger = self._build_logger()
        self.console_progress = not bool(getattr(args, "no_console_progress", False))
        control_arg = str(getattr(args, "control_file", "") or "").strip()
        self.control_path = Path(control_arg) if control_arg != "" else (self.out_dir / (self.entry_id + "_control.cmd"))

        self.symbol = get_symbol(args.pair)
        self.exchange = normalize_exchange(args.exchange, args.pair)
        self.funding = load_funding(self.exchange, args.pair)
        self.open_interest = load_open_interest(self.exchange, args.pair)
        self.bars = load_bars(
            days_in_history=int(args.days),
            wanted_tf=int(args.timeframe),
            start_offset_minutes=0,
            exchange=self.exchange,
            symbol=args.pair,
        )

        self.active_sweep_order: List[str] = []

        self.current_params = self._build_base_params()
        self.seed_param_overrides = self._parse_seed_params()
        self._apply_seed_overrides(self.current_params)
        self.fixed_param_overrides, self.fixed_dimensions = self._parse_fixed_params()
        self._apply_fixed_overrides(self.current_params)
        (
            self.stage_sweep_dims,
            self.stage_sweep_requested,
            inline_stage_range_overrides,
        ) = self._parse_stage_sweeps()
        self.sweep_range_overrides = dict(inline_stage_range_overrides)
        for dim_id, row in self._parse_sweep_range_overrides().items():
            self.sweep_range_overrides[dim_id] = row
        self.parameter_constraints = self._parse_parameter_constraints()
        confirmation_as_filter_gates = self._parse_metric_gates(
            raw_items=list(getattr(self.args, "stage1_gate", []) or []),
            flag_name="--stage1-gate",
        )
        filter_gates = self._parse_metric_gates(
            raw_items=list(getattr(self.args, "stage2_gate", []) or []),
            flag_name="--stage2-gate",
        )
        self.metric_gates = {
            # Confirmation gate layer is merged into filters.
            "confirmation": [],
            "filter": list(confirmation_as_filter_gates) + list(filter_gates),
            "sl": self._parse_metric_gates(
                raw_items=list(getattr(self.args, "stage3_gate", []) or []),
                flag_name="--stage3-gate",
            ),
        }
        self.prepared_dimension_ranges: Dict[str, List[Any]] = {}
        self.prepared_dimension_range_meta: Dict[str, Dict[str, Any]] = {}
        self.dry_run_config = bool(getattr(self.args, "dry_run_config", False))
        self.benchmark: Optional[Benchmark] = None
        self.final_confirmation_report: Optional[Dict[str, Any]] = None

    def _entry_param(self, suffix: str) -> str:
        return f"{self.entry_id}_{suffix}"

    def _entry_param_exists(self, suffix: str) -> bool:
        return self._entry_param(suffix) in self.entry_param_specs

    def _entry_param_if_exists(self, suffix: str) -> Optional[str]:
        key = self._entry_param(suffix)
        if key in self.entry_param_specs:
            return key
        return None

    def _stop_ref_profile_flag_key(self) -> Optional[str]:
        return self._entry_param_if_exists("stop_ref_profile_enabled")

    def _stop_ref_source_key(self, lookback: int) -> Optional[str]:
        return self._entry_param_if_exists(f"stop_ref_bar_{int(lookback)}_source")

    @staticmethod
    def _is_stop_ref_source_suffix(suffix: str) -> bool:
        txt = str(suffix).strip().lower()
        return re.fullmatch(r"stop_ref_bar_[1-5]_source", txt) is not None

    def _structured_dim_from_param_name(self, param_name: str) -> Optional[str]:
        pname = str(param_name).strip()
        if pname not in self.entry_param_specs:
            return None
        spec = self.entry_param_specs.get(pname, {})
        class_schema = str(spec.get("class", "")).strip().lower()
        class_token = DIM_CLASS_SCHEMA_TO_TOKEN.get(class_schema)
        if class_token is None:
            return None
        prefix = self.entry_id + "_"
        suffix = pname[len(prefix):] if pname.startswith(prefix) else pname
        return f"{self.entry_id}.{class_token}.{suffix}"

    def _structured_to_param_name(self, raw_key: str) -> Optional[str]:
        key_txt = str(raw_key).strip().lower()
        m = re.fullmatch(
            r"(entry_[a-z0-9_]+)\.(activation|idea|confirmation|filter|execution)\.([a-z0-9_]+)",
            key_txt,
        )
        if m is None:
            return None
        entry_txt, class_token, suffix = m.group(1), m.group(2), m.group(3)
        if entry_txt != self.entry_id:
            return None
        param_name = f"{self.entry_id}_{suffix}"
        if param_name not in self.entry_param_specs:
            return None
        spec = self.entry_param_specs.get(param_name, {})
        expected_class = DIM_CLASS_TOKEN_TO_SCHEMA.get(class_token)
        actual_class = str(spec.get("class", "")).strip().lower()
        if expected_class is None or actual_class != expected_class:
            return None
        return param_name

    def _canonical_dimension_token(self, raw_key: str) -> Optional[str]:
        token = str(raw_key).strip()
        if token == "":
            return None
        token_low = token.lower()
        if token_low in VIRTUAL_DIMENSION_IDS:
            if not self._virtual_dimension_supported(token_low):
                return None
            return token_low

        structured_param = self._structured_to_param_name(token_low)
        if structured_param is not None:
            sid = self._structured_dim_from_param_name(structured_param)
            if sid is not None:
                return sid
            return None
        return None

    def _parse_dimension_csv(self, raw_value: Any) -> List[str]:
        txt = str(raw_value if raw_value is not None else "").strip()
        if txt == "":
            return []
        out: List[str] = []
        for token in txt.split(","):
            item = str(token).strip()
            if item == "":
                continue
            if item not in out:
                out.append(item)
        return out

    def _dim_for_param(self, key: str) -> Optional[str]:
        k = str(key).strip()
        if k not in self.entry_param_specs:
            return None
        return self._structured_dim_from_param_name(k)

    def _dim_param_name(self, dim_id: str) -> Optional[str]:
        txt = str(dim_id).strip().lower()
        name = self._structured_to_param_name(txt)
        if name is None:
            return None
        if name in self.entry_param_specs:
            return name
        return None

    def _dim_param_class(self, dim_id: str) -> Optional[str]:
        pname = self._dim_param_name(dim_id)
        if pname is None:
            return None
        spec = self.entry_param_specs.get(pname)
        if not isinstance(spec, dict):
            return None
        return str(spec.get("class", "")).strip().lower() or None

    def _value_enable_param_name(self, param_name: str) -> Optional[str]:
        pname = str(param_name).strip()
        spec = self.entry_param_specs.get(pname)
        if not isinstance(spec, dict):
            return None
        value_type = str(spec.get("type", "")).strip().lower()
        if value_type in ("", "bool"):
            return None

        tail = pname[len(self.entry_id) + 1 :] if pname.startswith(self.entry_id + "_") else pname
        class_name = str(spec.get("class", "")).strip().lower()
        candidates: List[str] = []
        candidates.append(pname + "_enabled")
        if class_name == "filters":
            candidates.append(self._entry_param("filter_" + tail + "_enabled"))
            if tail.endswith("_std") and len(tail) > len("_std"):
                candidates.append(self._entry_param("filter_" + tail[: -len("_std")] + "_enabled"))
        if class_name == "confirmation":
            if tail.startswith("confirm_"):
                short_tail = tail[len("confirm_") :]
                candidates.append(self._entry_param("confirm_" + short_tail + "_enabled"))
                if short_tail.endswith("_std") and len(short_tail) > len("_std"):
                    candidates.append(self._entry_param("confirm_" + short_tail[: -len("_std")] + "_enabled"))
        if class_name == "execution":
            if tail == "sl_entry_atr_mult":
                candidates.append(self._entry_param("sl_use_entry_atr"))
            if self._is_stop_ref_source_suffix(tail):
                candidates.append(self._entry_param("stop_ref_profile_enabled"))
                candidates.append(self._entry_param("sl_use_entry_atr"))

        seen = set()
        for key in candidates:
            if key in seen:
                continue
            seen.add(key)
            flag_spec = self.entry_param_specs.get(key)
            if not isinstance(flag_spec, dict):
                continue
            if str(flag_spec.get("type", "")).strip().lower() == "bool":
                return key

        # Fallback: infer local class-level activation flags (e.g. use_vol_filter, use_min_natr, secondary_enabled).
        def _activation_token(bool_tail: str) -> Optional[str]:
            txt = str(bool_tail).strip().lower()
            if txt.endswith("_enabled"):
                token = txt[: -len("_enabled")]
                if token != "":
                    return token
            if txt.startswith("use_") and txt.endswith("_filter"):
                token = txt[len("use_") : -len("_filter")]
                if token != "":
                    return token
            if txt.startswith("use_"):
                token = txt[len("use_") :]
                if token != "":
                    return token
            return None

        best_key: Optional[str] = None
        best_score: float = -1.0
        for key, flag_spec in self.entry_param_specs.items():
            if key == pname:
                continue
            if str(flag_spec.get("type", "")).strip().lower() != "bool":
                continue
            if str(flag_spec.get("class", "")).strip().lower() != class_name:
                continue
            k_tail = key[len(self.entry_id) + 1 :] if key.startswith(self.entry_id + "_") else key
            token = _activation_token(k_tail)
            if token is None:
                continue

            score = -1.0
            if tail == token:
                score = 1000.0 + float(len(token))
            elif tail.startswith(token + "_"):
                score = 500.0 + float(len(token))
            elif token in tail:
                score = 100.0 + float(len(token))

            if score > best_score:
                best_score = score
                best_key = key

        if best_score > 0.0 and best_key is not None:
            return best_key
        return None

    def _virtual_dimension_supported(self, dim_id: str) -> bool:
        if dim_id == "sl_ref_profile":
            if self._stop_ref_profile_flag_key() is None:
                return False
            for lookback in range(1, 6):
                if self._stop_ref_source_key(lookback) is None:
                    return False
            return True
        return False

    def _build_numeric_sweep_from_spec(self, spec: Dict[str, Any]) -> List[Any]:
        value_type = str(spec.get("type", "")).strip().lower()
        min_v = spec.get("min")
        max_v = spec.get("max")
        step = spec.get("step")
        default = spec.get("default")
        if min_v is None or max_v is None or step in (None, 0):
            return [default]

        lo = float(min_v)
        hi = float(max_v)
        step_f = abs(float(step))
        if hi < lo:
            lo, hi = hi, lo

        values: List[float] = []
        v = lo
        max_points = 120
        while v <= hi + 1e-12 and len(values) < max_points:
            values.append(round(v, 8))
            v += step_f
        if len(values) == 0:
            values = [float(default)]

        if value_type == "int":
            ints = sorted({int(round(x)) for x in values})
            return list(reversed(ints))
        floats = sorted({round(float(x), 4) for x in values})
        return list(reversed(floats))

    @staticmethod
    def _is_rsi_0_100_numeric_spec(spec: Dict[str, Any]) -> bool:
        name = str(spec.get("name", "")).strip().lower()
        if "rsi" not in name:
            return False
        value_type = str(spec.get("type", "")).strip().lower()
        if value_type not in ("int", "float"):
            return False
        min_v = spec.get("min")
        max_v = spec.get("max")
        try:
            return abs(float(min_v) - 0.0) <= 1e-9 and abs(float(max_v) - 100.0) <= 1e-9
        except Exception:
            return False

    def _build_logger(self) -> logging.Logger:
        # Keep command-window output single-sourced via _progress() to avoid duplicates.
        logger = botlog.setup_custom_logger(
            name=self.entry_id + "_staged",
            log_level=int(self.args.log_level),
            logToConsole=False,
            logToFile=False,
        )
        # If a handler was attached elsewhere in-process, strip it to avoid double output.
        for h in list(logger.handlers):
            logger.removeHandler(h)
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        return logger

    def _record_event(self, event_type: str, payload: Dict[str, Any]):
        row = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "run_name": self.run_name,
            "event": event_type,
            "payload": payload,
        }
        with self.events_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def _progress(self, message: str):
        if not self.console_progress:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{ts} | {message}", flush=True)

    def _initialize_control_file(self):
        try:
            self.control_path.parent.mkdir(parents=True, exist_ok=True)
            # Reset stale command from previous runs.
            self.control_path.write_text("", encoding="utf-8")
        except Exception as exc:
            self._record_event(
                "control_command_error",
                {
                    "stage": "run_start",
                    "error": str(exc),
                    "control_file": str(self.control_path),
                },
            )
            self._progress("Control file init failed: %s" % str(exc))

    def _consume_control_command(self, stage: str) -> Optional[str]:
        try:
            if not self.control_path.exists():
                return None
            raw_text = str(self.control_path.read_text(encoding="utf-8"))
            lines = [str(line).strip().lower() for line in raw_text.splitlines()]
            commands = [line for line in lines if line != "" and (not line.startswith("#"))]
            raw = commands[0] if len(commands) > 0 else ""
            if raw == "":
                return None
        except Exception as exc:
            self._record_event(
                "control_command_error",
                {
                    "stage": stage,
                    "error": str(exc),
                    "control_file": str(self.control_path),
                },
            )
            return None

        aliases = {
            "accept_best": "accept_best",
            "best": "accept_best",
            "go_best": "accept_best",
            "continue_best": "accept_best",
            "skip_rest": "accept_best",
        }
        command = aliases.get(raw)
        if command is None:
            # Unknown input is cleared as requested.
            try:
                self.control_path.write_text("", encoding="utf-8")
            except Exception:
                pass
            self._record_event(
                "control_command_unknown",
                {"stage": stage, "raw": raw, "control_file": str(self.control_path)},
            )
            self._progress(
                "[%s] ignored unknown control command '%s' in %s"
                % (stage, raw, str(self.control_path))
            )
            return None

        # Consume known command by commenting it out (instead of deleting).
        try:
            self.control_path.write_text("# %s\n" % command, encoding="utf-8")
        except Exception:
            pass
        self._record_event(
            "control_command",
            {"stage": stage, "command": command, "raw": raw, "control_file": str(self.control_path)},
        )
        self._progress(
            "[%s] control command '%s' received; will continue with best completed candidate."
            % (stage, command)
        )
        return command

    @staticmethod
    def _round_up(x: float, step: float) -> float:
        if step <= 0:
            return float(x)
        return math.ceil(float(x) / float(step)) * float(step)

    @staticmethod
    def _round_down(x: float, step: float) -> float:
        if step <= 0:
            return float(x)
        return math.floor(float(x) / float(step)) * float(step)

    @staticmethod
    def _valid(arr: np.ndarray) -> np.ndarray:
        return arr[np.isfinite(arr)]

    @staticmethod
    def _trend_indicator_defaults(timeframe: int) -> Dict[str, Any]:
        tf = int(timeframe)
        return {
            "timeframe": tf,
            "ema_w_period": 3,
            "highs_trail_4h_period": 20 * 6,
            "lows_trail_4h_period": 20 * 6,
            "days_buffer_bear": 25,
            "days_buffer_bull": 10,
            "trend_atr_fac": 0.8,
            "atr_4h_period": 28,
            "natr_4h_period_slow": 200,
            "bbands_4h_period": 200,
            "rsi_4h_period": 6,
            "volume_sma_4h_period": 22,
            "trend_var_1": 0.0,
        }

    def _build_preparation_series_from_trend(self, chrono: List[Any]) -> Dict[str, np.ndarray]:
        n = len(chrono)
        if n <= 0:
            return {
                "natr": np.array([], dtype=float),
                "vol_ratio": np.array([], dtype=float),
                "oi_4h": np.array([], dtype=float),
                "oi_ratio_4h": np.array([], dtype=float),
                "oi_ret_pct": np.array([], dtype=float),
                "oi_ret_signed_pct": np.array([], dtype=float),
                "funding_4h": np.array([], dtype=float),
                "funding_abs_4h": np.array([], dtype=float),
                "rsi_4h": np.array([], dtype=float),
                "rsi_d": np.array([], dtype=float),
                "ret_pct": np.array([], dtype=float),
                "ret_signed_pct": np.array([], dtype=float),
                "bb_close_std": np.array([], dtype=float),
                "atr_std_ratio": np.array([], dtype=float),
            }

        close = np.array([float(b.close) for b in chrono], dtype=float)
        high = np.array([float(b.high) for b in chrono], dtype=float)
        low = np.array([float(b.low) for b in chrono], dtype=float)
        volume = np.array([float(b.volume) for b in chrono], dtype=float)

        def _local_fallback() -> Dict[str, np.ndarray]:
            natr = talib.NATR(high, low, close, 28)
            rsi_4h = talib.RSI(close, 6)
            rsi_d = np.full_like(close, np.nan)
            vol_sma = talib.MA(volume, 22, 0)
            vol_ratio = np.full_like(volume, np.nan)
            oi_4h = np.full_like(close, np.nan)
            oi_ratio_4h = np.full_like(close, np.nan)
            oi_ret_pct = np.full_like(close, np.nan)
            oi_ret_signed_pct = np.full_like(close, np.nan)
            funding_4h = np.full_like(close, np.nan)
            funding_abs_4h = np.full_like(close, np.nan)
            vol_ok = np.isfinite(vol_sma) & (np.abs(vol_sma) > 1e-12)
            vol_ratio[vol_ok] = volume[vol_ok] / vol_sma[vol_ok]
            bb_upper, bb_middle, _bb_lower = talib.BBANDS(
                close,
                timeperiod=200,
                nbdevup=1,
                nbdevdn=1,
            )
            bb_std = bb_upper - bb_middle
            bb_close_std = np.full_like(close, np.nan)
            bb_ok = np.isfinite(bb_std) & (np.abs(bb_std) > 1e-12)
            bb_close_std[bb_ok] = (close[bb_ok] - bb_middle[bb_ok]) / bb_std[bb_ok]
            atr = talib.ATR(high, low, close, 28)
            atr_std_ratio = np.full_like(close, np.nan)
            atr_ok = np.isfinite(atr) & np.isfinite(bb_std) & (np.abs(bb_std) > 1e-12)
            atr_std_ratio[atr_ok] = atr[atr_ok] / bb_std[atr_ok]
            ret_pct = np.full_like(close, np.nan)
            ret_signed_pct = np.full_like(close, np.nan)
            if len(close) > 1:
                prev_close = close[:-1]
                curr_close = close[1:]
                close_ok = np.isfinite(curr_close) & np.isfinite(prev_close)
                signed_step = np.full(len(curr_close), np.nan, dtype=float)
                signed_step[close_ok] = ((curr_close[close_ok] - prev_close[close_ok]) / np.maximum(np.abs(prev_close[close_ok]), 1e-12)) * 100.0
                ret_signed_pct[1:] = signed_step
                ret_pct[1:] = np.abs(signed_step)
            # no aligned OI in local fallback path; keep NaN placeholder
            return {
                "natr": natr,
                "vol_ratio": vol_ratio,
                "oi_4h": oi_4h,
                "oi_ratio_4h": oi_ratio_4h,
                "oi_ret_pct": oi_ret_pct,
                "oi_ret_signed_pct": oi_ret_signed_pct,
                "funding_4h": funding_4h,
                "funding_abs_4h": funding_abs_4h,
                "rsi_4h": rsi_4h,
                "rsi_d": rsi_d,
                "ret_pct": ret_pct,
                "ret_signed_pct": ret_signed_pct,
                "bb_close_std": bb_close_std,
                "atr_std_ratio": atr_std_ratio,
            }

        try:
            cfg = self._trend_indicator_defaults(timeframe=int(self.args.timeframe))
            ta_indicator = TATrendStrategyIndicator(
                timeframe=cfg["timeframe"],
                ema_w_period=cfg["ema_w_period"],
                highs_trail_4h_period=cfg["highs_trail_4h_period"],
                lows_trail_4h_period=cfg["lows_trail_4h_period"],
                days_buffer_bear=cfg["days_buffer_bear"],
                days_buffer_bull=cfg["days_buffer_bull"],
                atr_4h_period=cfg["atr_4h_period"],
                natr_4h_period_slow=cfg["natr_4h_period_slow"],
                bbands_4h_period=cfg["bbands_4h_period"],
                rsi_4h_period=cfg["rsi_4h_period"],
                volume_sma_4h_period=cfg["volume_sma_4h_period"],
                trend_atr_fac=cfg["trend_atr_fac"],
                trend_var_1=cfg["trend_var_1"],
                open_interest_by_tstamp=self.open_interest,
                funding_by_tstamp=self.funding,
                indicator_id_suffix="_prep",
            )
            provider = build_trend_indicator_provider(ta_indicator, mode="precomputed")
            provider.prepare_backtest(self.bars)

            close_arr = np.asarray(getattr(provider, "_close"), dtype=float)
            if len(close_arr) != n:
                raise ValueError("trend provider close length mismatch (%d vs %d)" % (len(close_arr), n))

            natr_arr = np.asarray(getattr(provider, "_natr"), dtype=float)
            rsi_4h_arr = np.asarray(getattr(provider, "_rsi_4h"), dtype=float)
            atr_arr = np.asarray(getattr(provider, "_atr"), dtype=float)
            bb_middle_arr = np.asarray(getattr(provider, "_bb_middle"), dtype=float)
            bb_std_arr = np.asarray(getattr(provider, "_bb_std"), dtype=float)
            volume_arr = np.asarray(getattr(provider, "_volume"), dtype=float)
            volume_sma_arr = np.asarray(getattr(provider, "_volume_sma"), dtype=float)
            oi_arr = np.asarray(getattr(provider, "_oi"), dtype=float)
            oi_sma_arr = np.asarray(getattr(provider, "_oi_sma"), dtype=float)
            funding_arr = np.asarray(getattr(provider, "_funding"), dtype=float)
            rsi_d_raw = list(getattr(provider, "_rsi_d_by_idx"))
            if len(rsi_d_raw) != n:
                raise ValueError("trend provider rsi_d length mismatch (%d vs %d)" % (len(rsi_d_raw), n))
            rsi_d_arr = np.array(
                [
                    float(v) if (v is not None and math.isfinite(float(v))) else np.nan
                    for v in rsi_d_raw
                ],
                dtype=float,
            )

            vol_ratio = np.full_like(volume_arr, np.nan)
            vol_ok = np.isfinite(volume_sma_arr) & (np.abs(volume_sma_arr) > 1e-12)
            vol_ratio[vol_ok] = volume_arr[vol_ok] / volume_sma_arr[vol_ok]
            oi_ratio_4h = np.full_like(oi_arr, np.nan)
            oi_ok = np.isfinite(oi_arr) & np.isfinite(oi_sma_arr) & (np.abs(oi_sma_arr) > 1e-12)
            oi_ratio_4h[oi_ok] = oi_arr[oi_ok] / oi_sma_arr[oi_ok]
            oi_ret_pct = np.full_like(oi_arr, np.nan)
            oi_ret_signed_pct = np.full_like(oi_arr, np.nan)
            if len(oi_arr) > 1:
                oi_prev = oi_arr[:-1]
                oi_curr = oi_arr[1:]
                oi_ok_ret = np.isfinite(oi_curr) & np.isfinite(oi_prev)
                oi_ret_step_signed = np.full(len(oi_curr), np.nan, dtype=float)
                oi_ret_step_signed[oi_ok_ret] = ((oi_curr[oi_ok_ret] - oi_prev[oi_ok_ret]) / np.maximum(np.abs(oi_prev[oi_ok_ret]), 1e-12)) * 100.0
                oi_ret_signed_pct[1:] = oi_ret_step_signed
                oi_ret_pct[1:] = np.abs(oi_ret_step_signed)
            funding_abs_arr = np.abs(funding_arr)

            bb_close_std = np.full_like(close_arr, np.nan)
            bb_ok = np.isfinite(bb_std_arr) & (np.abs(bb_std_arr) > 1e-12)
            bb_close_std[bb_ok] = (close_arr[bb_ok] - bb_middle_arr[bb_ok]) / bb_std_arr[bb_ok]

            atr_std_ratio = np.full_like(close_arr, np.nan)
            atr_ok = np.isfinite(atr_arr) & np.isfinite(bb_std_arr) & (np.abs(bb_std_arr) > 1e-12)
            atr_std_ratio[atr_ok] = atr_arr[atr_ok] / bb_std_arr[atr_ok]

            ret_pct = np.full_like(close_arr, np.nan)
            ret_signed_pct = np.full_like(close_arr, np.nan)
            if len(close_arr) > 1:
                prev_close = close_arr[:-1]
                curr_close = close_arr[1:]
                close_ok = np.isfinite(curr_close) & np.isfinite(prev_close)
                ret_step_signed = np.full(len(curr_close), np.nan, dtype=float)
                ret_step_signed[close_ok] = ((curr_close[close_ok] - prev_close[close_ok]) / np.maximum(np.abs(prev_close[close_ok]), 1e-12)) * 100.0
                ret_signed_pct[1:] = ret_step_signed
                ret_pct[1:] = np.abs(ret_step_signed)

            return {
                "natr": natr_arr,
                "vol_ratio": vol_ratio,
                "oi_4h": oi_arr,
                "oi_ratio_4h": oi_ratio_4h,
                "oi_ret_pct": oi_ret_pct,
                "oi_ret_signed_pct": oi_ret_signed_pct,
                "funding_4h": funding_arr,
                "funding_abs_4h": funding_abs_arr,
                "rsi_4h": rsi_4h_arr,
                "rsi_d": rsi_d_arr,
                "ret_pct": ret_pct,
                "ret_signed_pct": ret_signed_pct,
                "bb_close_std": bb_close_std,
                "atr_std_ratio": atr_std_ratio,
            }
        except Exception as exc:
            self._progress(
                "Preparation indicator sourcing from TrendStrategy failed (%s); using local TA fallback." % str(exc)
            )
            return _local_fallback()

    def _run_preparation_phase(self):
        if bool(getattr(self.args, "disable_preparation_phase", False)):
            self.logger.info("Preparation phase disabled by flag.")
            self._progress("Preparation phase disabled by flag.")
            self._record_event("preparation_phase", {"enabled": False, "reason": "disabled_by_flag"})
            return

        try:
            chrono = list(reversed(self.bars))
            if len(chrono) < 500:
                self.logger.info("Preparation phase skipped: too few bars (%d).", len(chrono))
                self._progress("Preparation phase skipped: too few bars (%d)." % len(chrono))
                self._record_event("preparation_phase", {"enabled": True, "reason": "too_few_bars", "bars": len(chrono)})
                return

            active_dims = set(self.active_sweep_order or [])
            selected_numeric_dims = [
                d
                for d in sorted(active_dims)
                if (d not in self.fixed_dimensions) and (self._dimension_numeric_kind(d) is not None)
            ]
            if len(selected_numeric_dims) == 0:
                self.prepared_dimension_ranges = {}
                self.prepared_dimension_range_meta = {}
                prep_plot_report = {
                    "enabled": bool(getattr(self.args, "preparation_with_plots", False)),
                    "plot_files": {},
                    "plot_errors": {},
                    "plotted_series": [],
                }
                if prep_plot_report["enabled"] and (
                    self._oi_flow_plot_requested() or self._oi_funding_plot_requested()
                ):
                    prep_series_raw = self._build_preparation_series_from_trend(chrono=chrono)
                    prep_plot_report = self._write_preparation_plots(
                        chrono=chrono,
                        prep_series_raw=prep_series_raw,
                        selected_numeric_dims=[],
                        prep_dim_status=[],
                    )
                self._record_event(
                    "preparation_phase",
                    {
                        "enabled": True,
                        "bars": len(chrono),
                        "selected_numeric_dims": 0,
                        "prepared_numeric_dims": 0,
                        "prepared_dim_ranges": {},
                        "preparation_plots": prep_plot_report,
                    },
                )
                if len(prep_plot_report.get("plotted_series", [])) > 0:
                    self._progress(
                        "Preparation phase complete | no numeric dimensions selected | plots=%d"
                        % int(len(prep_plot_report.get("plotted_series", [])))
                    )
                else:
                    self._progress("Preparation phase complete | no numeric dimensions selected.")
                return

            prep_series_raw = self._build_preparation_series_from_trend(chrono=chrono)

            prep_ctx = {
                "natr": self._valid(prep_series_raw.get("natr", np.array([], dtype=float))),
                "vol_ratio": self._valid(prep_series_raw.get("vol_ratio", np.array([], dtype=float))),
                "oi_4h": self._valid(prep_series_raw.get("oi_4h", np.array([], dtype=float))),
                "oi_ratio_4h": self._valid(prep_series_raw.get("oi_ratio_4h", np.array([], dtype=float))),
                "oi_ret_pct": self._valid(prep_series_raw.get("oi_ret_pct", np.array([], dtype=float))),
                "oi_ret_signed_pct": self._valid(prep_series_raw.get("oi_ret_signed_pct", np.array([], dtype=float))),
                "funding_4h": self._valid(prep_series_raw.get("funding_4h", np.array([], dtype=float))),
                "funding_abs_4h": self._valid(prep_series_raw.get("funding_abs_4h", np.array([], dtype=float))),
                "rsi_4h": self._valid(prep_series_raw.get("rsi_4h", np.array([], dtype=float))),
                "rsi_d": self._valid(prep_series_raw.get("rsi_d", np.array([], dtype=float))),
                "ret_pct": self._valid(prep_series_raw.get("ret_pct", np.array([], dtype=float))),
                "ret_signed_pct": self._valid(prep_series_raw.get("ret_signed_pct", np.array([], dtype=float))),
                "bb_close_std": self._valid(prep_series_raw.get("bb_close_std", np.array([], dtype=float))),
                "atr_std_ratio": self._valid(prep_series_raw.get("atr_std_ratio", np.array([], dtype=float))),
            }
            self.prepared_dimension_ranges = {}
            self.prepared_dimension_range_meta = {}
            prep_dim_status: List[Dict[str, Any]] = []
            for dim_id in selected_numeric_dims:
                if dim_id in self.sweep_range_overrides:
                    override = dict(self.sweep_range_overrides.get(dim_id, {}))
                    override_vals = list(override.get("values") or [])
                    override_min = min([float(v) for v in override_vals]) if len(override_vals) > 0 else override.get("min")
                    override_max = max([float(v) for v in override_vals]) if len(override_vals) > 0 else override.get("max")
                    prep_dim_status.append(
                        {
                            "dim": dim_id,
                            "status": "override",
                            "source": "sweep_range_override",
                            "count": len(override_vals),
                            "min": override_min,
                            "max": override_max,
                            "step": override.get("step"),
                        }
                    )
                    continue
                prepared_values = None
                source = "history_profile"
                prepared_meta: Dict[str, Any] = {}
                prepared_data = self._build_prepared_numeric_values(dim_id=dim_id, prep_ctx=prep_ctx)
                if prepared_data is not None:
                    prepared_values, source, prepared_meta = prepared_data
                if isinstance(prepared_values, list) and len(prepared_values) > 0:
                    effective_step = prepared_meta.get("effective_step", self._dimension_numeric_step(dim_id))
                    self.prepared_dimension_ranges[dim_id] = prepared_values
                    self.prepared_dimension_range_meta[dim_id] = {
                        "count": len(prepared_values),
                        "min": float(min([float(v) for v in prepared_values])),
                        "max": float(max([float(v) for v in prepared_values])),
                        "source": source,
                        "step": effective_step,
                        "base_step": prepared_meta.get("base_step"),
                        "target_points": prepared_meta.get("target_points"),
                        "min_points": prepared_meta.get("min_points"),
                        "max_points": prepared_meta.get("max_points"),
                    }
                    prep_dim_status.append(
                        {
                            "dim": dim_id,
                            "status": "prepared",
                            "source": source,
                            "count": len(prepared_values),
                            "min": float(min([float(v) for v in prepared_values])),
                            "max": float(max([float(v) for v in prepared_values])),
                            "step": effective_step,
                            "base_step": prepared_meta.get("base_step"),
                            "target_points": prepared_meta.get("target_points"),
                            "min_points": prepared_meta.get("min_points"),
                            "max_points": prepared_meta.get("max_points"),
                        }
                    )
                else:
                    prep_dim_status.append(
                        {
                            "dim": dim_id,
                            "status": "not_prepared",
                            "source": "no_range_generated",
                            "count": 0,
                            "min": None,
                            "max": None,
                            "step": self._dimension_numeric_step(dim_id),
                        }
                    )

            override_dims = [d.get("dim") for d in prep_dim_status if d.get("status") == "override"]
            prepared_dims = [d.get("dim") for d in prep_dim_status if d.get("status") == "prepared"]
            not_prepared_dims = [d.get("dim") for d in prep_dim_status if d.get("status") == "not_prepared"]
            prep_plot_report = self._write_preparation_plots(
                chrono=chrono,
                prep_series_raw=prep_series_raw,
                selected_numeric_dims=selected_numeric_dims,
                prep_dim_status=prep_dim_status,
            )

            summary = {
                "enabled": True,
                "bars": len(chrono),
                "sweep_lengths": {
                    "selected_numeric_dims": len(selected_numeric_dims),
                    "prepared_numeric_dims": len(self.prepared_dimension_ranges),
                    "override_numeric_dims": len(override_dims),
                    "not_prepared_numeric_dims": len(not_prepared_dims),
                },
                "selected_numeric_dim_ids": selected_numeric_dims,
                "override_numeric_dim_ids": override_dims,
                "not_prepared_numeric_dim_ids": not_prepared_dims,
                "prepared_dim_ranges": self.prepared_dimension_range_meta,
                "dim_status": prep_dim_status,
                "plots": prep_plot_report,
            }
            self._record_event("preparation_phase", summary)
            self.logger.info(
                "Preparation phase complete | selected_numeric_dims=%d prepared_numeric_dims=%d override_numeric_dims=%d not_prepared_numeric_dims=%d",
                len(selected_numeric_dims),
                len(self.prepared_dimension_ranges),
                len(override_dims),
                len(not_prepared_dims),
            )
            self._progress(
                "Preparation phase complete | selected_numeric_dims=%d prepared_numeric_dims=%d override_numeric_dims=%d not_prepared_numeric_dims=%d"
                % (
                    len(selected_numeric_dims),
                    len(self.prepared_dimension_ranges),
                    len(override_dims),
                    len(not_prepared_dims),
                )
            )
            if len(selected_numeric_dims) > 0:
                self._progress(
                    "Preparation selected numeric dims: %s"
                    % ", ".join([str(d) for d in selected_numeric_dims])
                )
            for row in prep_dim_status:
                status = str(row.get("status"))
                dim = str(row.get("dim"))
                source = str(row.get("source"))
                count = int(row.get("count", 0))
                min_v = row.get("min")
                max_v = row.get("max")
                step = row.get("step")
                self._progress(
                    "Preparation dim %s | status=%s source=%s count=%d range=[%s..%s] step=%s"
                    % (
                        dim,
                        status,
                        source,
                        count,
                        str(min_v),
                        str(max_v),
                        str(step),
                    )
                )
        except Exception as exc:
            self.logger.exception("Preparation phase failed; continuing with default sweeps.")
            self._progress("Preparation phase failed; continuing with default sweeps.")
            self._record_event("preparation_phase", {"enabled": True, "reason": "error", "error": str(exc)})

    @staticmethod
    def _build_strategy(
        entry_cfg: Dict[str, Any],
        timeframe: int,
        entry_id: str,
        open_interest_by_tstamp: Optional[Dict[int, float]] = None,
        funding_by_tstamp: Optional[Dict[int, float]] = None,
    ):
        entry_module_config = dict(BASE_ENTRY_MODULE_CONFIG)
        entry_module_config.update(entry_cfg)
        entry_module_config[str(entry_id)] = True
        allow_long = bool(entry_module_config.get(f"{entry_id}_allow_long", True))
        allow_short = bool(entry_module_config.get(f"{entry_id}_allow_short", False))
        trend_cfg = EntryStagedOptimizer._trend_indicator_defaults(timeframe=int(timeframe))
        return (
            StrategyOne(
                var_1=0,
                var_2=0,
                risk_ref=1,
                reduceRisk=True,
                max_r=10,
                entry_module_config=entry_module_config,
                h_highs_trail_period=55,
                h_lows_trail_period=55,
                tp_fac_strat_one=20,
                plotStrategyOneData=False,
                plotTrailsStatOne=False,
                longsAllowed=allow_long,
                shortsAllowed=allow_short,
                timeframe=trend_cfg["timeframe"],
                ema_w_period=trend_cfg["ema_w_period"],
                highs_trail_4h_period=trend_cfg["highs_trail_4h_period"],
                lows_trail_4h_period=trend_cfg["lows_trail_4h_period"],
                days_buffer_bear=trend_cfg["days_buffer_bear"],
                days_buffer_bull=trend_cfg["days_buffer_bull"],
                trend_atr_fac=trend_cfg["trend_atr_fac"],
                atr_4h_period=trend_cfg["atr_4h_period"],
                natr_4h_period_slow=trend_cfg["natr_4h_period_slow"],
                bbands_4h_period=trend_cfg["bbands_4h_period"],
                plotIndicators=True,
                plot_RSI=False,
                rsi_4h_period=trend_cfg["rsi_4h_period"],
                volume_sma_4h_period=trend_cfg["volume_sma_4h_period"],
                trend_var_1=trend_cfg["trend_var_1"],
                open_interest_by_tstamp=open_interest_by_tstamp,
                funding_by_tstamp=funding_by_tstamp,
                risk_with_trend=3.5,
                risk_ranging=2.5,
                risk_counter_trend=3.5,
                risk_fac_shorts=1,
                sl_atr_fac=0.8,
                be_by_middleband=False,
                be_by_opposite=False,
                stop_at_middleband=False,
                tp_at_middleband=False,
                atr_buffer_fac=0,
                tp_on_opposite=False,
                stop_at_new_entry=False,
                trail_sl_with_bband=False,
                stop_short_at_middleband=False,
                stop_at_trail=True,
                stop_at_lowerband=False,
                moving_sl_atr_fac=0,
                sl_upper_bb_std_fac=3,
                sl_lower_bb_std_fac=3,
                ema_multiple_4_tp=1.4,
                use_shapes=True,
                plotBackgroundColor4Trend=False,
                plotTrailsAndEMAs=False,
                plotBBands=True,
                plotATR=False,
                maxPositions=140,
                consolidate=False,
                close_on_opposite=False,
                bars_till_cancel_triggered=20,
                limit_entry_offset_perc=0.15,
                tp_fac=0,
                delayed_cancel=False,
                cancel_on_filter=True,
            )
            .withEntryFilter(DayOfWeekFilter(allowedDaysMask=63))
            .withRM(risk_factor=5, max_risk_mul=1, risk_type=3, atr_factor=0)
            .withExitModule(ATRrangeSL(rangeFacTrigger=0.15, longRangefacSL=-1.3, shortRangefacSL=-0.7, rangeATRfactor=1, atrPeriod=20))
            .withExitModule(ATRrangeSL(rangeFacTrigger=0.8, longRangefacSL=0.1, shortRangefacSL=-0.3, rangeATRfactor=1, atrPeriod=20))
            .withExitModule(ATRrangeSL(rangeFacTrigger=1.5, longRangefacSL=0.1, shortRangefacSL=-0.2, rangeATRfactor=1, atrPeriod=20))
            .withExitModule(ATRrangeSL(rangeFacTrigger=6.3, longRangefacSL=3.2, shortRangefacSL=0, rangeATRfactor=1, atrPeriod=20))
            .withExitModule(TimedExit(longs_min_to_exit=12 * 240, shorts_min_to_exit=0, longs_min_to_breakeven=6 * 240, shorts_min_to_breakeven=0, atrPeriod=20))
            .withExitModule(FixedPercentage(slPercentage=0.5, useInitialSLRange=False, rangeFactor=0))
        )

    def _build_bot(self, entry_cfg: Dict[str, Any], timeframe: int, logger: Optional[logging.Logger] = None):
        use_logger = logger if logger is not None else self.logger
        bot = MultiStrategyBot(logger=use_logger, directionFilter=0)
        bot.add_strategy(
            self._build_strategy(
                entry_cfg=entry_cfg,
                timeframe=timeframe,
                entry_id=self.entry_id,
                open_interest_by_tstamp=self.open_interest,
                funding_by_tstamp=self.funding,
            )
        )
        return bot

    def _build_base_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = dict(BASE_ENTRY_MODULE_CONFIG)
        entry_catalog = ENTRY_PARAM_CATALOG[self.entry_id]
        for class_name in ("activation", "idea", "confirmation", "filters", "execution"):
            for spec in entry_catalog.get(class_name, []):
                key = str(spec["name"])
                params[key] = copy.deepcopy(spec.get("default"))

        params[self.entry_id] = True

        if self.entry_id == "entry_23":
            # Keep entry_23 trigger semantics stable.
            params["entry_23_allow_long"] = True
            params["entry_23_allow_short"] = False
            stop_ref_profile_key = self._stop_ref_profile_flag_key()
            if stop_ref_profile_key is not None:
                params[stop_ref_profile_key] = False
            self._set_all_sl_ref_sources_off(params)

        return params

    def _dimension_from_key(self, key: str) -> Optional[str]:
        k = str(key).strip().lower()
        canonical = self._canonical_dimension_token(k)
        if canonical is not None:
            return canonical
        return None

    @staticmethod
    def _is_off_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, bool):
            return value is False
        if isinstance(value, str):
            return str(value).strip().lower() in ("off", "none", "null", "disable", "disabled")
        return False

    @staticmethod
    def _normalize_sl_ref_source(value: Any) -> str:
        if value is None:
            return "off"
        txt = str(value).strip().lower()
        if txt in ("", "none", "null", "disable", "disabled", "false"):
            txt = "off"
        if txt not in SL_REF_SOURCE_VALUES:
            raise ValueError(
                "Invalid SL bar source '%s'. Allowed: %s"
                % (str(value), ",".join(SL_REF_SOURCE_VALUES))
            )
        return txt

    @staticmethod
    def _normalize_sl_ref_profile(value: Any) -> str:
        txt = str(value).strip().lower()
        if txt in ("", "none", "null", "disable", "disabled", "off", "false"):
            return "off"
        m = re.fullmatch(r"(low|min_oc)_([1-5])", txt)
        if m is None:
            raise ValueError(
                "Invalid SL profile '%s'. Allowed examples: off, low_1, min_oc_3"
                % str(value)
            )
        return f"{m.group(1)}_{m.group(2)}"

    def _set_all_sl_ref_sources_off(self, params: Dict[str, Any]):
        for lookback in range(1, 6):
            source_key = self._stop_ref_source_key(lookback)
            if source_key is not None:
                params[source_key] = "off"

    def _ensure_cli_param_key_allowed(self, raw_key: str):
        key_txt = str(raw_key).strip().lower()
        structured_param = self._structured_to_param_name(key_txt)
        effective_key = structured_param if structured_param is not None else key_txt
        if key_txt in DISALLOWED_CLI_PARAM_KEYS:
            raise ValueError(
                "Explicit SL bar-source key '%s' is not allowed. Use --fixed-param/--seed-param sl_ref_profile=..."
                % str(raw_key)
            )
        if effective_key in DISALLOWED_CLI_PARAM_KEYS:
            raise ValueError(
                "Explicit SL bar-source key '%s' is not allowed. Use --fixed-param/--seed-param sl_ref_profile=..."
                % str(raw_key)
            )
        if re.fullmatch(
            rf"{re.escape(self.entry_id)}_stop_ref_bar_[1-5]_source",
            effective_key,
        ):
            raise ValueError(
                "Explicit SL bar-source key '%s' is not allowed. Use --fixed-param/--seed-param sl_ref_profile=..."
                % str(raw_key)
            )
        if re.fullmatch(
            rf"{re.escape(self.entry_id)}_stop_ref_bar_[1-5]_source",
            key_txt,
        ):
            raise ValueError(
                "Explicit SL bar-source key '%s' is not allowed. Use --fixed-param/--seed-param sl_ref_profile=..."
                % str(raw_key)
            )

    def _dimension_numeric_kind(self, dim_id: str) -> Optional[str]:
        param_name = self._dim_param_name(dim_id)
        if param_name is not None:
            spec = self.entry_param_specs.get(param_name, {})
            vtype = str(spec.get("type", "")).strip().lower()
            if vtype in ("int", "float"):
                return vtype
            return None
        return None

    @staticmethod
    def _build_numeric_values_from_range(
        min_v: float,
        max_v: float,
        step: float,
        value_type: str,
        ascending: bool,
    ) -> List[Any]:
        lo = float(min_v)
        hi = float(max_v)
        st = abs(float(step))
        if st <= 1e-12:
            raise ValueError("step must be > 0")
        if hi < lo:
            lo, hi = hi, lo

        values: List[float] = []
        v = lo
        guard = 0
        while v <= hi + 1e-12 and guard < 5000:
            values.append(float(v))
            v += st
            guard += 1
        if len(values) == 0:
            values = [lo]

        if value_type == "int":
            ints = sorted({int(round(x)) for x in values})
            return ints if ascending else list(reversed(ints))
        floats = sorted({round(float(x), 8) for x in values})
        out = floats if ascending else list(reversed(floats))
        return [round(float(x), 4) for x in out]

    def _dimension_prefers_ascending(self, dim_id: str) -> bool:
        param_name = self._dim_param_name(dim_id)
        if param_name is not None and param_name.endswith("_confirm_vol_ratio_min"):
            return True
        return False

    def _range_point_count_for_step(
        self,
        *,
        min_v: float,
        max_v: float,
        step: float,
        value_type: str,
    ) -> int:
        try:
            values = self._build_numeric_values_from_range(
                min_v=min_v,
                max_v=max_v,
                step=step,
                value_type=value_type,
                ascending=True,
            )
            return int(len(values))
        except Exception:
            return 0

    def _resolve_preparation_step(
        self,
        *,
        min_v: float,
        max_v: float,
        base_step: float,
        value_type: str,
    ) -> float:
        lo = float(min(min_v, max_v))
        hi = float(max(min_v, max_v))
        step = abs(float(base_step))
        if step <= 1e-12:
            return float(base_step)
        span = hi - lo
        if span <= 1e-12:
            return float(step)

        target_points = int(PREPARATION_TARGET_SWEEP_POINTS)
        min_points = int(PREPARATION_MIN_SWEEP_POINTS)
        max_points = int(PREPARATION_MAX_SWEEP_POINTS)
        if target_points < 2:
            target_points = 2
        if min_points < 2:
            min_points = 2
        if max_points < min_points:
            max_points = min_points

        desired_step = span / float(max(1, target_points - 1))
        if value_type == "int":
            step_i = max(int(round(step)), int(math.ceil(desired_step)))
            if step_i < 1:
                step_i = 1
            guard = 0
            while guard < 4096 and (
                self._range_point_count_for_step(
                    min_v=lo,
                    max_v=hi,
                    step=float(step_i),
                    value_type=value_type,
                )
                > max_points
            ):
                step_i += 1
                guard += 1
            guard = 0
            while guard < 4096 and step_i > int(round(step)):
                curr_count = self._range_point_count_for_step(
                    min_v=lo,
                    max_v=hi,
                    step=float(step_i),
                    value_type=value_type,
                )
                if curr_count >= min_points:
                    break
                candidate = step_i - 1
                candidate_count = self._range_point_count_for_step(
                    min_v=lo,
                    max_v=hi,
                    step=float(candidate),
                    value_type=value_type,
                )
                if candidate_count > max_points:
                    break
                step_i = candidate
                guard += 1
            return float(step_i)

        units = max(1, int(math.ceil(desired_step / step)))
        resolved_step = float(step * units)
        guard = 0
        while guard < 4096 and (
            self._range_point_count_for_step(
                min_v=lo,
                max_v=hi,
                step=resolved_step,
                value_type=value_type,
            )
            > max_points
        ):
            units += 1
            resolved_step = float(step * units)
            guard += 1
        guard = 0
        while guard < 4096 and units > 1:
            curr_count = self._range_point_count_for_step(
                min_v=lo,
                max_v=hi,
                step=resolved_step,
                value_type=value_type,
            )
            if curr_count >= min_points:
                break
            candidate_units = units - 1
            candidate_step = float(step * candidate_units)
            candidate_count = self._range_point_count_for_step(
                min_v=lo,
                max_v=hi,
                step=candidate_step,
                value_type=value_type,
            )
            if candidate_count > max_points:
                break
            units = candidate_units
            resolved_step = candidate_step
            guard += 1
        return float(resolved_step)

    def _dimension_numeric_bounds(self, dim_id: str) -> Optional[Tuple[float, float]]:
        param_name = self._dim_param_name(dim_id)
        if param_name is not None:
            spec = self.entry_param_specs.get(param_name, {})
            try:
                lo = float(spec.get("min"))
                hi = float(spec.get("max"))
                if math.isfinite(lo) and math.isfinite(hi):
                    return (min(lo, hi), max(lo, hi))
            except Exception:
                pass
            try:
                dv = float(spec.get("default"))
                if math.isfinite(dv):
                    return (dv, dv)
            except Exception:
                return None
            return None
        return None

    def _dimension_numeric_step(self, dim_id: str) -> Optional[float]:
        param_name = self._dim_param_name(dim_id)
        if param_name is not None:
            spec = self.entry_param_specs.get(param_name, {})
            value_type = str(spec.get("type", "")).strip().lower()
            try:
                step = float(spec.get("step"))
            except Exception:
                step = None
            if step is not None and math.isfinite(step) and abs(step) > 1e-12:
                return abs(step)
            if value_type == "int":
                return 1.0
            if value_type == "float":
                return 0.1
            return None
        return None

    def _preparation_series_key_for_dimension(self, dim_id: str) -> Optional[str]:
        name = str(dim_id).lower()
        if "oi_funding_oi_up_min_pct" in name or "oi_funding_oi_down_min_pct" in name:
            return "oi_ret_pct"
        if "oi_funding_pos_min" in name or "oi_funding_neg_min" in name:
            return "funding_abs_4h"
        if "oi_flow_oi_min_pct" in name or "oi_ret_pct" in name:
            return "oi_ret_pct"
        if "oi_flow_price_min_pct" in name:
            return "ret_pct"
        if "oi_ratio_4h" in name:
            return "oi_ratio_4h"
        if "oi_4h" in name:
            return "oi_4h"
        if "rsi_d" in name:
            return "rsi_d"
        if "rsi_4h" in name:
            return "rsi_4h"
        if "rsi" in name:
            return "rsi_4h"
        if "natr" in name:
            return "natr"
        if "vol_ratio" in name:
            return "vol_ratio"
        if "atr_std_ratio" in name:
            return "atr_std_ratio"
        if ("bb" in name) and ("std" in name):
            return "bb_close_std"
        if name.endswith("_pct") or "_pct" in name:
            return "ret_pct"
        return None

    def _prepare_series_for_dimension(self, dim_id: str, prep_ctx: Dict[str, np.ndarray]) -> Optional[np.ndarray]:
        series_key = self._preparation_series_key_for_dimension(dim_id)
        if series_key is None:
            return None
        return prep_ctx.get(series_key)

    def _seeded_numeric_values_by_dimension(self) -> Dict[str, float]:
        seeded_values: Dict[str, float] = {}
        for key, raw_value in list(self.seed_param_overrides or []):
            dim_id = self._dimension_from_key(key)
            if dim_id is None:
                continue
            if self._dimension_numeric_kind(dim_id) is None:
                continue
            try:
                value = float(raw_value)
            except Exception:
                continue
            if not math.isfinite(value):
                continue
            seeded_values[dim_id] = value
        return seeded_values

    def _selected_numeric_values_by_dimension(self, dims: List[str]) -> Dict[str, float]:
        selected_values: Dict[str, float] = {}
        for dim_id in dims:
            if self._dimension_numeric_kind(dim_id) is None:
                continue
            try:
                raw_value = self._dimension_current_value_from_params(params=self.current_params, dim_id=dim_id)
                value = float(raw_value)
            except Exception:
                continue
            if not math.isfinite(value):
                continue
            selected_values[dim_id] = value
        return selected_values

    def _oi_flow_plot_requested(self) -> bool:
        for dim_id in list(self.active_sweep_order or []):
            txt = str(dim_id).strip().lower()
            if ".oi_flow_state" in txt or ".oi_flow_" in txt:
                return True
        try:
            state_key = self._entry_param("oi_flow_state")
            state_value = str(self.current_params.get(state_key, "off")).strip().lower()
            if state_value not in ("", "off"):
                return True
        except Exception:
            pass
        return False

    def _current_oi_flow_plot_config(self) -> Optional[Dict[str, Any]]:
        if not self._entry_param_exists("oi_flow_state"):
            return None
        try:
            state = str(self.current_params.get(self._entry_param("oi_flow_state"), "off")).strip().lower()
            lookback = max(1, int(self.current_params.get(self._entry_param("oi_flow_lookback"), 3)))
            price_min_pct = max(0.0, float(self.current_params.get(self._entry_param("oi_flow_price_min_pct"), 0.0)))
            oi_min_pct = max(0.0, float(self.current_params.get(self._entry_param("oi_flow_oi_min_pct"), 0.0)))
            return {
                "state": state,
                "lookback": lookback,
                "price_min_pct": price_min_pct,
                "oi_min_pct": oi_min_pct,
            }
        except Exception:
            return None

    def _write_oi_flow_distribution_plot(
        self,
        *,
        chrono: List[Any],
        prep_series_raw: Dict[str, np.ndarray],
        payload: Dict[str, Any],
    ) -> None:
        if not self._oi_flow_plot_requested():
            return
        flow_cfg = self._current_oi_flow_plot_config()
        if not isinstance(flow_cfg, dict):
            return

        close_arr = np.array([float(getattr(b, "close")) for b in chrono], dtype=float)
        oi_arr = np.asarray(prep_series_raw.get("oi_4h", np.array([], dtype=float)), dtype=float)
        if len(close_arr) == 0 or len(oi_arr) != len(close_arr):
            payload["plot_errors"]["oi_flow_state"] = "series_length_mismatch"
            return

        lookback = int(flow_cfg.get("lookback", 3))
        price_thr = float(flow_cfg.get("price_min_pct", 0.0))
        oi_thr = float(flow_cfg.get("oi_min_pct", 0.0))
        time_axis = [datetime.fromtimestamp(float(getattr(b, "tstamp"))) for b in chrono]

        x_vals: List[datetime] = []
        state_values: List[str] = []
        for idx in range(lookback, len(close_arr)):
            prev_close = float(close_arr[idx - lookback])
            curr_close = float(close_arr[idx])
            prev_oi = float(oi_arr[idx - lookback])
            curr_oi = float(oi_arr[idx])
            if (
                (not math.isfinite(prev_close))
                or (not math.isfinite(curr_close))
                or (not math.isfinite(prev_oi))
                or (not math.isfinite(curr_oi))
            ):
                continue
            if abs(prev_close) <= 1e-12 or abs(prev_oi) <= 1e-12:
                continue
            price_ret = ((curr_close - prev_close) / abs(prev_close)) * 100.0
            oi_ret = ((curr_oi - prev_oi) / abs(prev_oi)) * 100.0
            state = oi_price_flow_state_from_returns(
                price_ret_pct=float(price_ret),
                oi_ret_pct=float(oi_ret),
                price_min_pct=price_thr,
                oi_min_pct=oi_thr,
            )
            x_vals.append(time_axis[idx])
            state_values.append(str(state.value))

        if len(state_values) == 0:
            payload["plot_errors"]["oi_flow_state"] = "no_classifiable_points"
            return

        state_order = [
            OIPriceFlowState.TREND_CONTINUATION.value,
            OIPriceFlowState.SHORT_COVER.value,
            OIPriceFlowState.BEARISH_CONTINUATION.value,
            OIPriceFlowState.LONG_LIQUIDATION.value,
            OIPriceFlowState.NEUTRAL.value,
        ]
        y_code = {name: idx + 1 for idx, name in enumerate(state_order)}
        y_vals = [y_code.get(name, y_code[OIPriceFlowState.NEUTRAL.value]) for name in state_values]
        counts = {name: int(sum(1 for s in state_values if s == name)) for name in state_order}

        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=False,
            vertical_spacing=0.10,
            row_heights=[0.62, 0.38],
            subplot_titles=(
                "OI flow state over time",
                "OI flow state distribution",
            ),
        )
        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="markers",
                name="flow_state",
                marker=dict(size=5, color=y_vals, colorscale="Viridis", showscale=False),
                text=state_values,
                hovertemplate="time=%{x}<br>state=%{text}<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Bar(
                x=state_order,
                y=[counts[name] for name in state_order],
                marker=dict(color=["#1f77b4", "#ff7f0e", "#d62728", "#9467bd", "#7f7f7f"]),
                name="count",
                text=[str(counts[name]) for name in state_order],
                textposition="outside",
            ),
            row=2,
            col=1,
        )
        fig.update_yaxes(
            row=1,
            col=1,
            tickmode="array",
            tickvals=[y_code[name] for name in state_order],
            ticktext=state_order,
            range=[0.5, len(state_order) + 0.5],
        )
        fig.update_layout(
            title=(
                "Preparation indicators | OI flow state "
                f"(lookback={lookback}, price_thr={round(price_thr, 4)}%, oi_thr={round(oi_thr, 4)}%, "
                f"selected={flow_cfg.get('state', 'off')})"
            ),
            height=820,
            showlegend=False,
            bargap=0.2,
        )

        out_path = self.out_dir / f"{self.run_name}.prep_oi_flow_state.html"
        try:
            fig.write_html(str(out_path), include_plotlyjs="cdn", full_html=True, auto_open=False)
            payload["plot_files"]["oi_flow_state"] = str(out_path)
            if "oi_flow_state" not in payload["plotted_series"]:
                payload["plotted_series"].append("oi_flow_state")
            self._progress("Preparation plot written (oi_flow_state): %s" % str(out_path))
            if bool(getattr(self.args, "preparation_plot_open_browser", False)):
                try:
                    webbrowser.open(str(out_path.resolve().as_uri()), new=2, autoraise=False)
                except Exception as open_exc:
                    payload["plot_errors"]["oi_flow_state"] = "open_browser_failed: %s" % str(open_exc)
        except Exception as exc:
            payload["plot_errors"]["oi_flow_state"] = str(exc)
            self._progress("Preparation plot failed (oi_flow_state): %s" % str(exc))

    def _oi_funding_plot_requested(self) -> bool:
        for dim_id in list(self.active_sweep_order or []):
            txt = str(dim_id).strip().lower()
            if ".oi_funding_state" in txt or ".oi_funding_" in txt:
                return True
        try:
            state_key = self._entry_param("oi_funding_state")
            state_value = str(self.current_params.get(state_key, "off")).strip().lower()
            if state_value not in ("", "off"):
                return True
        except Exception:
            pass
        return False

    def _current_oi_funding_plot_config(self) -> Optional[Dict[str, Any]]:
        if not self._entry_param_exists("oi_funding_state"):
            return None
        try:
            state = str(self.current_params.get(self._entry_param("oi_funding_state"), "off")).strip().lower()
            lookback = max(1, int(self.current_params.get(self._entry_param("oi_funding_lookback"), 3)))
            oi_up_min_pct = max(0.0, float(self.current_params.get(self._entry_param("oi_funding_oi_up_min_pct"), 0.0)))
            oi_down_min_pct = max(0.0, float(self.current_params.get(self._entry_param("oi_funding_oi_down_min_pct"), 0.0)))
            funding_pos_min = max(0.0, float(self.current_params.get(self._entry_param("oi_funding_pos_min"), 0.0)))
            funding_neg_min = max(0.0, float(self.current_params.get(self._entry_param("oi_funding_neg_min"), 0.0)))
            return {
                "state": state,
                "lookback": lookback,
                "oi_up_min_pct": oi_up_min_pct,
                "oi_down_min_pct": oi_down_min_pct,
                "funding_pos_min": funding_pos_min,
                "funding_neg_min": funding_neg_min,
            }
        except Exception:
            return None

    def _write_oi_funding_distribution_plot(
        self,
        *,
        chrono: List[Any],
        prep_series_raw: Dict[str, np.ndarray],
        payload: Dict[str, Any],
    ) -> None:
        if not self._oi_funding_plot_requested():
            return
        cfg = self._current_oi_funding_plot_config()
        if not isinstance(cfg, dict):
            return

        oi_arr = np.asarray(prep_series_raw.get("oi_4h", np.array([], dtype=float)), dtype=float)
        funding_arr = np.asarray(prep_series_raw.get("funding_4h", np.array([], dtype=float)), dtype=float)
        if len(oi_arr) == 0 or len(funding_arr) != len(oi_arr):
            payload["plot_errors"]["oi_funding_state"] = "series_length_mismatch"
            return

        lookback = int(cfg.get("lookback", 3))
        oi_up = float(cfg.get("oi_up_min_pct", 0.0))
        oi_down = float(cfg.get("oi_down_min_pct", 0.0))
        funding_pos = float(cfg.get("funding_pos_min", 0.0))
        funding_neg = float(cfg.get("funding_neg_min", 0.0))
        time_axis = [datetime.fromtimestamp(float(getattr(b, "tstamp"))) for b in chrono]

        x_vals: List[datetime] = []
        state_values: List[str] = []
        for idx in range(lookback, len(oi_arr)):
            prev_oi = float(oi_arr[idx - lookback])
            curr_oi = float(oi_arr[idx])
            funding_now = float(funding_arr[idx])
            if (not math.isfinite(prev_oi)) or (not math.isfinite(curr_oi)) or (not math.isfinite(funding_now)):
                continue
            if abs(prev_oi) <= 1e-12:
                continue
            oi_ret = ((curr_oi - prev_oi) / abs(prev_oi)) * 100.0
            state = oi_funding_state_from_metrics(
                oi_ret_pct=float(oi_ret),
                funding_rate=float(funding_now),
                oi_up_min_pct=oi_up,
                oi_down_min_pct=oi_down,
                funding_pos_min=funding_pos,
                funding_neg_min=funding_neg,
            )
            x_vals.append(time_axis[idx])
            state_values.append(str(state.value))

        if len(state_values) == 0:
            payload["plot_errors"]["oi_funding_state"] = "no_classifiable_points"
            return

        state_order = [
            OIFundingState.LONG_CROWDED.value,
            OIFundingState.SHORT_CROWDED.value,
            OIFundingState.DELEVERAGING.value,
            OIFundingState.NEUTRAL.value,
        ]
        y_code = {name: idx + 1 for idx, name in enumerate(state_order)}
        y_vals = [y_code.get(name, y_code[OIFundingState.NEUTRAL.value]) for name in state_values]
        counts = {name: int(sum(1 for s in state_values if s == name)) for name in state_order}

        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=False,
            vertical_spacing=0.10,
            row_heights=[0.62, 0.38],
            subplot_titles=(
                "OI + funding state over time",
                "OI + funding state distribution",
            ),
        )
        fig.add_trace(
            go.Scatter(
                x=x_vals,
                y=y_vals,
                mode="markers",
                name="oi_funding_state",
                marker=dict(size=5, color=y_vals, colorscale="Cividis", showscale=False),
                text=state_values,
                hovertemplate="time=%{x}<br>state=%{text}<extra></extra>",
            ),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Bar(
                x=state_order,
                y=[counts[name] for name in state_order],
                marker=dict(color=["#d62728", "#1f77b4", "#ff7f0e", "#7f7f7f"]),
                name="count",
                text=[str(counts[name]) for name in state_order],
                textposition="outside",
            ),
            row=2,
            col=1,
        )
        fig.update_yaxes(
            row=1,
            col=1,
            tickmode="array",
            tickvals=[y_code[name] for name in state_order],
            ticktext=state_order,
            range=[0.5, len(state_order) + 0.5],
        )
        fig.update_layout(
            title=(
                "Preparation indicators | OI+funding state "
                f"(lookback={lookback}, oi_up={round(oi_up, 4)}%, oi_down={round(oi_down, 4)}%, "
                f"funding_pos={round(funding_pos, 6)}, funding_neg={round(funding_neg, 6)}, "
                f"selected={cfg.get('state', 'off')})"
            ),
            height=820,
            showlegend=False,
            bargap=0.2,
        )

        out_path = self.out_dir / f"{self.run_name}.prep_oi_funding_state.html"
        try:
            fig.write_html(str(out_path), include_plotlyjs="cdn", full_html=True, auto_open=False)
            payload["plot_files"]["oi_funding_state"] = str(out_path)
            if "oi_funding_state" not in payload["plotted_series"]:
                payload["plotted_series"].append("oi_funding_state")
            self._progress("Preparation plot written (oi_funding_state): %s" % str(out_path))
            if bool(getattr(self.args, "preparation_plot_open_browser", False)):
                try:
                    webbrowser.open(str(out_path.resolve().as_uri()), new=2, autoraise=False)
                except Exception as open_exc:
                    payload["plot_errors"]["oi_funding_state"] = "open_browser_failed: %s" % str(open_exc)
        except Exception as exc:
            payload["plot_errors"]["oi_funding_state"] = str(exc)
            self._progress("Preparation plot failed (oi_funding_state): %s" % str(exc))

    def _write_preparation_plots(
        self,
        chrono: List[Any],
        prep_series_raw: Dict[str, np.ndarray],
        selected_numeric_dims: List[str],
        prep_dim_status: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "enabled": bool(getattr(self.args, "preparation_with_plots", False)),
            "plot_files": {},
            "plot_errors": {},
            "plotted_series": [],
        }
        if not payload["enabled"]:
            return payload

        status_by_dim = {str(row.get("dim")): dict(row) for row in prep_dim_status if row.get("dim") is not None}
        seeded_values = self._seeded_numeric_values_by_dimension()
        selected_values = self._selected_numeric_values_by_dimension(dims=selected_numeric_dims)
        time_axis = [datetime.fromtimestamp(float(getattr(b, "tstamp"))) for b in chrono]
        series_labels = {
            "natr": "NATR(28)",
            "vol_ratio": "Volume / MA(22)",
            "oi_4h": "Open Interest (4H aligned)",
            "oi_ratio_4h": "Open Interest / OI-SMA",
            "oi_ret_pct": "Abs OI Return %",
            "funding_4h": "Funding Rate (4H aligned)",
            "funding_abs_4h": "Abs Funding Rate",
            "rsi_4h": "RSI-4H (TrendStrategy)",
            "rsi_d": "RSI-D (TrendStrategy)",
            "ret_pct": "Abs Return %",
            "bb_close_std": "BB Close Std(200,1)",
            "atr_std_ratio": "ATR(28) / BB Std(200,1)",
        }

        keys_to_plot: List[str] = []
        for dim_id in selected_numeric_dims:
            key = self._preparation_series_key_for_dimension(dim_id)
            if key is None:
                continue
            if key not in keys_to_plot:
                keys_to_plot.append(key)

        for series_key in keys_to_plot:
            raw = prep_series_raw.get(series_key)
            if raw is None:
                payload["plot_errors"][series_key] = "series_not_available"
                continue
            try:
                values = np.asarray(raw, dtype=float)
            except Exception:
                payload["plot_errors"][series_key] = "series_cast_failed"
                continue
            if len(values) != len(time_axis):
                payload["plot_errors"][series_key] = "series_length_mismatch"
                continue

            finite_mask = np.isfinite(values)
            if int(np.sum(finite_mask)) == 0:
                payload["plot_errors"][series_key] = "no_finite_values"
                continue

            x = [time_axis[i] for i in range(len(time_axis)) if bool(finite_mask[i])]
            y = [float(values[i]) for i in range(len(values)) if bool(finite_mask[i])]
            y_min = float(min(y))
            y_max = float(max(y))
            pad = 0.03 * max(1e-9, y_max - y_min)

            fig = make_subplots(
                rows=2,
                cols=1,
                shared_xaxes=False,
                vertical_spacing=0.08,
                row_heights=[0.68, 0.32],
                subplot_titles=(
                    f"{series_labels.get(series_key, series_key)} over time",
                    f"{series_labels.get(series_key, series_key)} distribution",
                ),
            )
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    name=series_labels.get(series_key, series_key),
                    line=dict(color="#1f77b4", width=1.2),
                ),
                row=1,
                col=1,
            )
            fig.add_trace(
                go.Histogram(
                    x=y,
                    nbinsx=60,
                    name="hist",
                    marker=dict(color="#2ca02c"),
                    opacity=0.7,
                ),
                row=2,
                col=1,
            )

            q05 = float(np.percentile(y, 5))
            q50 = float(np.percentile(y, 50))
            q95 = float(np.percentile(y, 95))
            for q_value, q_name, q_color in (
                (q05, "q05", "#888888"),
                (q50, "q50", "#333333"),
                (q95, "q95", "#888888"),
            ):
                fig.add_hline(
                    y=q_value,
                    row=1,
                    col=1,
                    line_width=1,
                    line_dash="dot",
                    line_color=q_color,
                    annotation_text=q_name,
                    annotation_position="top left",
                )

            dims_for_series = [d for d in selected_numeric_dims if self._preparation_series_key_for_dimension(d) == series_key]
            for dim_id in dims_for_series:
                row = status_by_dim.get(dim_id, {})
                range_min = row.get("min")
                range_max = row.get("max")
                if range_min is not None and range_max is not None:
                    try:
                        range_min_f = float(range_min)
                        range_max_f = float(range_max)
                        lo = min(range_min_f, range_max_f)
                        hi = max(range_min_f, range_max_f)
                        fig.add_hrect(
                            y0=lo,
                            y1=hi,
                            row=1,
                            col=1,
                            fillcolor="#ff7f0e",
                            opacity=0.08,
                            line_width=0,
                            annotation_text=f"{dim_id} range",
                            annotation_position="top right",
                        )
                    except Exception:
                        pass
                seeded = seeded_values.get(dim_id)
                if seeded is not None and math.isfinite(seeded):
                    fig.add_hline(
                        y=float(seeded),
                        row=1,
                        col=1,
                        line_width=1.4,
                        line_dash="dash",
                        line_color="#d62728",
                        annotation_text=f"seed {dim_id}={round(float(seeded), 6)}",
                        annotation_position="bottom right",
                    )
                    fig.add_vline(
                        x=float(seeded),
                        row=2,
                        col=1,
                        line_width=1.2,
                        line_dash="dash",
                        line_color="#d62728",
                        annotation_text=f"seed {round(float(seeded), 6)}",
                        annotation_position="top right",
                    )
                selected = selected_values.get(dim_id)
                if selected is not None and math.isfinite(selected):
                    fig.add_hline(
                        y=float(selected),
                        row=1,
                        col=1,
                        line_width=1.6,
                        line_dash="solid",
                        line_color="#9467bd",
                        annotation_text=f"current {dim_id}={round(float(selected), 6)}",
                        annotation_position="bottom left",
                    )
                    fig.add_vline(
                        x=float(selected),
                        row=2,
                        col=1,
                        line_width=1.4,
                        line_dash="solid",
                        line_color="#9467bd",
                        annotation_text=f"current {round(float(selected), 6)}",
                        annotation_position="top left",
                    )

            fig.update_yaxes(range=[y_min - pad, y_max + pad], row=1, col=1)
            fig.update_layout(
                title=f"Preparation indicators | {series_labels.get(series_key, series_key)}",
                bargap=0.05,
                height=860,
                legend=dict(orientation="h"),
            )
            out_path = self.out_dir / f"{self.run_name}.prep_{series_key}.html"
            try:
                fig.write_html(str(out_path), include_plotlyjs="cdn", full_html=True, auto_open=False)
                payload["plot_files"][series_key] = str(out_path)
                payload["plotted_series"].append(series_key)
                self._progress("Preparation plot written (%s): %s" % (series_key, str(out_path)))
                if bool(getattr(self.args, "preparation_plot_open_browser", False)):
                    try:
                        webbrowser.open(str(out_path.resolve().as_uri()), new=2, autoraise=False)
                    except Exception as open_exc:
                        payload["plot_errors"][series_key] = "open_browser_failed: %s" % str(open_exc)
            except Exception as exc:
                payload["plot_errors"][series_key] = str(exc)
                self._progress("Preparation plot failed (%s): %s" % (series_key, str(exc)))

        self._write_oi_flow_distribution_plot(
            chrono=chrono,
            prep_series_raw=prep_series_raw,
            payload=payload,
        )
        self._write_oi_funding_distribution_plot(
            chrono=chrono,
            prep_series_raw=prep_series_raw,
            payload=payload,
        )
        return payload
        return None

    def _build_prepared_numeric_values(
        self,
        dim_id: str,
        prep_ctx: Dict[str, np.ndarray],
    ) -> Optional[Tuple[List[Any], str, Dict[str, Any]]]:
        numeric_kind = self._dimension_numeric_kind(dim_id)
        if numeric_kind is None:
            return None
        bounds = self._dimension_numeric_bounds(dim_id)
        step = self._dimension_numeric_step(dim_id)
        if bounds is None or step is None:
            return None
        lo_bound, hi_bound = bounds
        series = self._prepare_series_for_dimension(dim_id, prep_ctx=prep_ctx)
        source = "schema_bounds"
        if series is None or len(series) == 0:
            lo, hi = lo_bound, hi_bound
        else:
            source = "history_profile"
            q05 = float(np.percentile(series, 5))
            q95 = float(np.percentile(series, 95))
            spread = max(1e-9, q95 - q05)
            lo = max(lo_bound, q05 - 0.2 * spread)
            hi = min(hi_bound, q95 + 0.2 * spread)
            if hi < lo:
                lo, hi = lo_bound, hi_bound
            if hi - lo < 1e-12:
                lo, hi = lo_bound, hi_bound

        # Keep RSI thresholds coarse enough while still respecting prep point budget.
        if "rsi" in str(dim_id).lower():
            step = max(float(step), 5.0)
        lo = max(lo_bound, self._round_down(lo, step))
        hi = min(hi_bound, self._round_up(hi, step))
        if hi < lo:
            lo, hi = lo_bound, hi_bound

        effective_step = self._resolve_preparation_step(
            min_v=lo,
            max_v=hi,
            base_step=float(step),
            value_type=numeric_kind,
        )
        ascending = self._dimension_prefers_ascending(dim_id=dim_id)
        values = self._build_numeric_values_from_range(
            min_v=lo,
            max_v=hi,
            step=effective_step,
            value_type=numeric_kind,
            ascending=ascending,
        )
        if len(values) == 0:
            return None
        return (
            values,
            source,
            {
                "base_step": float(step),
                "effective_step": float(effective_step),
                "resolved_points": int(len(values)),
                "target_points": int(PREPARATION_TARGET_SWEEP_POINTS),
                "min_points": int(PREPARATION_MIN_SWEEP_POINTS),
                "max_points": int(PREPARATION_MAX_SWEEP_POINTS),
            },
        )

    def _parse_single_range_override(self, token: str, flag_name: str) -> Tuple[str, Dict[str, Any]]:
        raw = str(token).strip()
        if raw == "":
            raise ValueError("Invalid %s value (empty token)." % str(flag_name))
        if "=" not in raw:
            raise ValueError("Invalid %s '%s' (expected dim=min:max:step)." % (str(flag_name), raw))

        dim_raw, range_raw = raw.split("=", 1)
        dim_key = str(dim_raw).strip()
        if dim_key == "":
            raise ValueError("Invalid %s '%s' (empty dimension)." % (str(flag_name), raw))
        dim_id = self._dimension_from_key(dim_key)
        if dim_id is None:
            raise ValueError("Unknown dimension in %s: '%s'" % (str(flag_name), dim_key))

        parts = [p.strip() for p in str(range_raw).split(":")]
        if len(parts) != 3:
            raise ValueError("Invalid %s '%s' (expected min:max:step)." % (str(flag_name), raw))
        try:
            min_v = float(parts[0])
            max_v = float(parts[1])
            step_v = float(parts[2])
        except Exception:
            raise ValueError("Invalid %s '%s' (min/max/step must be numeric)." % (str(flag_name), raw))
        if (not math.isfinite(min_v)) or (not math.isfinite(max_v)) or (not math.isfinite(step_v)):
            raise ValueError("Invalid %s '%s' (min/max/step must be finite)." % (str(flag_name), raw))
        if step_v <= 0:
            raise ValueError("Invalid %s '%s' (step must be > 0)." % (str(flag_name), raw))

        value_type = self._dimension_numeric_kind(dim_id)
        if value_type is None:
            raise ValueError(
                "Invalid %s '%s': dimension '%s' is not numeric."
                % (str(flag_name), raw, dim_key)
            )
        ascending = self._dimension_prefers_ascending(dim_id)
        values = self._build_numeric_values_from_range(
            min_v=min_v,
            max_v=max_v,
            step=step_v,
            value_type=value_type,
            ascending=ascending,
        )
        if len(values) == 0:
            raise ValueError("Invalid %s '%s' produced empty values." % (str(flag_name), raw))

        source = "sweep_range"
        flag_txt = str(flag_name).strip().lower()
        if flag_txt in ("--stage1-sweep", "--stage2-sweep", "--stage3-sweep"):
            source = "stage_sweep_inline"

        return dim_id, {
            "min": min(min_v, max_v),
            "max": max(min_v, max_v),
            "step": float(step_v),
            "type": value_type,
            "ascending": bool(ascending),
            "values": values,
            "raw_dim": dim_key,
            "source": source,
            "raw_token": raw,
        }

    def _parse_sweep_range_overrides(self) -> Dict[str, Dict[str, Any]]:
        raw_items = list(getattr(self.args, "sweep_range", []) or [])
        overrides: Dict[str, Dict[str, Any]] = {}
        for raw_item in raw_items:
            token = str(raw_item).strip()
            if token == "":
                continue
            dim_id, row = self._parse_single_range_override(token=token, flag_name="--sweep-range")
            overrides[dim_id] = row
        return overrides

    def _default_stage_sweep_dimensions(self, stage_bucket: str) -> List[str]:
        # No implicit fallback sweeps: stages only run dimensions explicitly requested via --stageX-sweep.
        return []

    def _parse_stage_sweep_spec(
        self,
        raw_value: Any,
        stage_bucket: str,
        flag_name: str,
    ) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
        tokens = self._parse_dimension_csv(raw_value)
        if len(tokens) == 0:
            return self._default_stage_sweep_dimensions(stage_bucket=stage_bucket), {}

        dims: List[str] = []
        inline_overrides: Dict[str, Dict[str, Any]] = {}
        for token in tokens:
            token_txt = str(token).strip()
            if token_txt == "":
                continue
            if "=" in token_txt:
                dim_id, spec = self._parse_single_range_override(token=token_txt, flag_name=flag_name)
            else:
                dim_id = self._dimension_from_key(token_txt)
                if dim_id is None:
                    raise ValueError("Unknown dimension in %s: '%s'" % (flag_name, token_txt))
                spec = None

            bucket = self._dimension_stage_bucket(dim_id)
            if bucket != stage_bucket:
                raise ValueError(
                    "Dimension '%s' in %s belongs to stage '%s', not '%s'."
                    % (token_txt, flag_name, bucket, stage_bucket)
                )
            if dim_id in self.fixed_dimensions:
                raise ValueError(
                    "Dimension '%s' in %s is fixed via --fixed-param and cannot be swept."
                    % (dim_id, flag_name)
                )
            if dim_id not in dims:
                dims.append(dim_id)
            if spec is not None:
                inline_overrides[dim_id] = spec
        return dims, inline_overrides

    def _parse_stage_sweeps(self) -> Tuple[Dict[str, List[str]], Dict[str, str], Dict[str, Dict[str, Any]]]:
        legacy_stage1_raw = str(getattr(self.args, "stage1_sweep", "") or "").strip()
        if legacy_stage1_raw != "":
            raise ValueError(
                "Stage1 confirmation sweep is removed (confirmation merged into filters). Use --stage2-sweep."
            )
        stage_specs = [
            ("filter", "stage2_sweep", "--stage2-sweep"),
            ("sl", "stage3_sweep", "--stage3-sweep"),
        ]
        dims_by_stage: Dict[str, List[str]] = {}
        requested_raw: Dict[str, str] = {}
        inline_overrides: Dict[str, Dict[str, Any]] = {}
        for stage_bucket, arg_name, flag_name in stage_specs:
            raw_value = getattr(self.args, arg_name, "")
            requested_raw[stage_bucket] = str(raw_value if raw_value is not None else "").strip()
            dims, stage_inline = self._parse_stage_sweep_spec(
                raw_value=raw_value,
                stage_bucket=stage_bucket,
                flag_name=flag_name,
            )
            dims_by_stage[stage_bucket] = dims
            for dim_id, row in stage_inline.items():
                inline_overrides[dim_id] = row
        return dims_by_stage, requested_raw, inline_overrides

    @staticmethod
    def _split_condition_expr(expr: str) -> Tuple[str, str, str]:
        text = str(expr).strip()
        for op in ("<=", ">=", "==", "!=", "<", ">"):
            if op in text:
                left, right = text.split(op, 1)
                return left.strip(), op, right.strip()
        raise ValueError("Invalid expression '%s' (missing comparator)." % str(expr))

    @staticmethod
    def _compare_values(lhs: Any, op: str, rhs: Any) -> bool:
        def _to_float(v: Any) -> Optional[float]:
            try:
                fv = float(v)
            except Exception:
                return None
            if not math.isfinite(fv):
                return None
            return fv

        lf = _to_float(lhs)
        rf = _to_float(rhs)
        if lf is not None and rf is not None:
            if op == "<":
                return lf < rf
            if op == "<=":
                return lf <= rf
            if op == ">":
                return lf > rf
            if op == ">=":
                return lf >= rf
            if op == "==":
                return abs(lf - rf) <= 1e-9
            if op == "!=":
                return abs(lf - rf) > 1e-9
            raise ValueError("Unsupported comparator: %s" % str(op))

        if op in ("<", "<=", ">", ">="):
            raise ValueError("Comparator '%s' requires numeric operands." % str(op))

        lhs_txt = str(lhs).strip().lower()
        rhs_txt = str(rhs).strip().lower()
        if op == "==":
            return lhs_txt == rhs_txt
        if op == "!=":
            return lhs_txt != rhs_txt
        raise ValueError("Unsupported comparator: %s" % str(op))

    def _parse_parameter_constraints(self) -> List[ParameterConstraint]:
        raw_items = list(getattr(self.args, "constraint", []) or [])
        out: List[ParameterConstraint] = []
        for raw_item in raw_items:
            for token in self._parse_dimension_csv(raw_item):
                left_txt, op, right_txt = self._split_condition_expr(token)
                if left_txt == "" or right_txt == "":
                    raise ValueError("Invalid --constraint '%s' (empty operand)." % token)

                left_dim = self._dimension_from_key(left_txt)
                if left_dim is not None:
                    left_kind, left_val = "dim", left_dim
                else:
                    left_kind, left_val = "lit", parse_scalar(left_txt)

                right_dim = self._dimension_from_key(right_txt)
                if right_dim is not None:
                    right_kind, right_val = "dim", right_dim
                else:
                    right_kind, right_val = "lit", parse_scalar(right_txt)

                if left_kind == "lit" and right_kind == "lit":
                    raise ValueError(
                        "Invalid --constraint '%s' (at least one operand must be a dimension)." % token
                    )

                out.append(
                    ParameterConstraint(
                        left_kind=left_kind,
                        left_value=left_val,
                        op=op,
                        right_kind=right_kind,
                        right_value=right_val,
                        raw=token,
                    )
                )
        return out

    def _parse_metric_gates(self, raw_items: List[str], flag_name: str) -> List[MetricGate]:
        aliases = {
            "profit": "profit",
            "profit_pct": "profit",
            "dd": "dd",
            "max_dd": "dd",
            "drawdown": "dd",
            "max_drawdown_pct": "dd",
            "rel": "rel",
            "rel2": "rel2_signed",
            "rel2_signed": "rel2_signed",
            "trades": "trades",
            "trades_closed": "trades",
        }
        out: List[MetricGate] = []
        for raw_item in raw_items:
            for token in self._parse_dimension_csv(raw_item):
                left_txt, op, right_txt = self._split_condition_expr(token)
                metric_key = aliases.get(str(left_txt).strip().lower())
                if metric_key is None:
                    raise ValueError("Unknown metric in %s: '%s'" % (flag_name, left_txt))
                try:
                    value = float(parse_scalar(right_txt))
                except Exception:
                    raise ValueError("Invalid gate value in %s: '%s'" % (flag_name, token))
                if not math.isfinite(value):
                    raise ValueError("Invalid gate value in %s: '%s'" % (flag_name, token))
                out.append(MetricGate(metric_key=metric_key, op=op, value=float(value), raw=token))
        return out

    def _metric_value(self, metrics: Dict[str, Any], metric_key: str) -> float:
        key = str(metric_key).strip().lower()
        if key == "profit":
            return metric(metrics, "profit_pct")
        if key == "dd":
            return abs(metric(metrics, "max_drawdown_pct"))
        if key == "rel":
            return self._value_rel(metrics)
        if key == "rel2_signed":
            return self._value_rel2_signed(metrics)
        if key == "trades":
            return float(int(metric(metrics, "trades_closed")))
        raise ValueError("Unknown metric key: %s" % str(metric_key))

    def _metrics_pass_stage_gates(
        self,
        metrics: Dict[str, Any],
        stage_bucket: str,
    ) -> Tuple[bool, Optional[str]]:
        gates = list(self.metric_gates.get(stage_bucket, []))
        for gate in gates:
            lhs = self._metric_value(metrics=metrics, metric_key=gate.metric_key)
            if not self._compare_values(lhs, gate.op, gate.value):
                return False, gate.raw
        return True, None

    def _constraint_operand_value(self, params: Dict[str, Any], kind: str, value: Any) -> Any:
        if kind == "dim":
            return self._dimension_current_value_from_params(params=params, dim_id=str(value))
        return value

    def _params_pass_constraints(self, params: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        for constraint in self.parameter_constraints:
            lhs = self._constraint_operand_value(params=params, kind=constraint.left_kind, value=constraint.left_value)
            rhs = self._constraint_operand_value(params=params, kind=constraint.right_kind, value=constraint.right_value)
            try:
                ok = self._compare_values(lhs, constraint.op, rhs)
            except Exception as exc:
                return False, "%s (%s)" % (constraint.raw, str(exc))
            if not ok:
                return False, constraint.raw
        return True, None

    def _validate_sweep_configuration(
        self,
        stage1b_dims: List[str],
        filter_dims: List[str],
        sl_dims: List[str],
        skip_stage1b_confirmation: bool,
    ):
        selected_dims: List[str] = []
        if not skip_stage1b_confirmation:
            selected_dims.extend(stage1b_dims)
        selected_dims.extend(filter_dims)
        selected_dims.extend(sl_dims)
        selected_dims = [d for d in selected_dims if d not in self.fixed_dimensions]
        selected_set = set(selected_dims)

        for dim_id in self.sweep_range_overrides.keys():
            if dim_id in self.fixed_dimensions:
                raise ValueError(
                    "Dimension '%s' has both --fixed-param and a range override; remove one." % dim_id
                )
            if dim_id not in selected_set:
                raise ValueError(
                    "Dimension '%s' has a range override but is not selected for active stages."
                    % dim_id
                )

        errors: List[str] = []
        prep_required = not bool(getattr(self.args, "disable_preparation_phase", False))
        for dim_id in selected_dims:
            try:
                values = self._dimension_sweep_values(dim_id=dim_id)
            except Exception as exc:
                errors.append("%s: %s" % (dim_id, str(exc)))
                continue
            if len(values) == 0:
                errors.append("%s: resolved empty sweep values" % dim_id)
                continue
            numeric_kind = self._dimension_numeric_kind(dim_id)
            if numeric_kind is not None:
                if prep_required and dim_id not in self.sweep_range_overrides and dim_id not in self.prepared_dimension_ranges:
                    errors.append(
                        "%s: no preparation-derived range (add --sweep-range or enable data profile support)"
                        % dim_id
                    )
                    continue
                for v in values:
                    try:
                        fv = float(v)
                    except Exception:
                        errors.append("%s: non-numeric value '%s' in numeric sweep" % (dim_id, str(v)))
                        break
                    if not math.isfinite(fv):
                        errors.append("%s: non-finite value '%s' in numeric sweep" % (dim_id, str(v)))
                        break
        if len(errors) > 0:
            raise ValueError("Invalid sweep configuration: " + " | ".join(errors))

    def _parse_fixed_params(self) -> Tuple[List[Tuple[str, Any]], List[str]]:
        raw_items = list(getattr(self.args, "fixed_param", []) or [])
        overrides: List[Tuple[str, Any]] = []
        fixed_dims: List[str] = []
        for raw_item in raw_items:
            token = str(raw_item).strip()
            if token == "":
                continue
            if "=" not in token:
                raise ValueError("Invalid --fixed-param '%s' (expected key=value)." % token)
            key, raw_value = token.split("=", 1)
            k = str(key).strip()
            if k == "":
                raise ValueError("Invalid --fixed-param '%s' (empty key)." % token)
            self._ensure_cli_param_key_allowed(k)
            value = parse_scalar(raw_value)
            overrides.append((k, value))
            dim = self._dimension_from_key(k)
            if dim is None:
                raise ValueError(
                    "Unknown --fixed-param key '%s'. Use a structured dimension id like %s.filter.confirm_rsi_d_max."
                    % (k, self.entry_id)
                )
            if dim not in fixed_dims:
                fixed_dims.append(dim)
        return overrides, fixed_dims

    def _parse_seed_params(self) -> List[Tuple[str, Any]]:
        raw_items = list(getattr(self.args, "seed_param", []) or [])
        overrides: List[Tuple[str, Any]] = []
        for raw_item in raw_items:
            token = str(raw_item).strip()
            if token == "":
                continue
            if "=" not in token:
                raise ValueError("Invalid --seed-param '%s' (expected key=value)." % token)
            key, raw_value = token.split("=", 1)
            k = str(key).strip()
            if k == "":
                raise ValueError("Invalid --seed-param '%s' (empty key)." % token)
            self._ensure_cli_param_key_allowed(k)
            value = parse_scalar(raw_value)
            dim = self._dimension_from_key(k)
            if dim is None:
                raise ValueError(
                    "Unknown --seed-param key '%s'. Use a structured dimension id like %s.filter.confirm_rsi_d_max."
                    % (k, self.entry_id)
                )
            overrides.append((k, value))
        return overrides

    def _apply_seed_overrides(self, params: Dict[str, Any]):
        for key, value in self.seed_param_overrides:
            dim = self._dimension_from_key(key)
            if dim is not None:
                self._apply_dimension_value(params=params, dim_id=dim, value=value)
            else:
                raise ValueError("Unknown seed dimension key: %s" % str(key))

    def _apply_fixed_overrides(self, params: Dict[str, Any]):
        for key, value in self.fixed_param_overrides:
            dim = self._dimension_from_key(key)
            if dim is not None:
                self._apply_dimension_value(params=params, dim_id=dim, value=value)
            else:
                raise ValueError("Unknown fixed dimension key: %s" % str(key))

    def _apply_dimension_off(self, params: Dict[str, Any], dim_id: str):
        param_name = self._dim_param_name(dim_id)
        if param_name is not None:
            spec = self.entry_param_specs.get(param_name, {})
            value_type = str(spec.get("type", "")).strip().lower()
            if value_type == "bool":
                params[param_name] = False
            else:
                params[param_name] = copy.deepcopy(spec.get("default"))
            return
        if dim_id == "sl_ref_profile":
            stop_ref_profile_key = self._stop_ref_profile_flag_key()
            if stop_ref_profile_key is not None:
                params[stop_ref_profile_key] = False
            self._set_all_sl_ref_sources_off(params)
            return
        raise ValueError("Unknown sweep dimension: %s" % dim_id)

    def _apply_dimension_value(self, params: Dict[str, Any], dim_id: str, value: Any):
        param_name = self._dim_param_name(dim_id)
        if param_name is not None:
            spec = self.entry_param_specs.get(param_name, {})
            value_type = str(spec.get("type", "")).strip().lower()
            enable_param_name = self._value_enable_param_name(param_name)
            enable_dim_id = self._dim_for_param(enable_param_name) if enable_param_name is not None else None
            fixed_dims = list(getattr(self, "fixed_dimensions", []) or [])
            enable_is_fixed = enable_dim_id in fixed_dims if enable_dim_id is not None else False
            if enable_param_name is not None and (not enable_is_fixed) and self._is_off_value(value):
                params[enable_param_name] = False
                params[param_name] = copy.deepcopy(spec.get("default"))
                return
            if value_type == "bool":
                params[param_name] = not self._is_off_value(value)
            elif value_type == "int":
                params[param_name] = int(round(float(value)))
            elif value_type == "float":
                params[param_name] = float(value)
            else:
                params[param_name] = value
            if enable_param_name is not None and (not enable_is_fixed):
                params[enable_param_name] = True
            stop_ref_profile_key = self._stop_ref_profile_flag_key()
            sl_use_entry_atr_key = self._entry_param_if_exists("sl_use_entry_atr")
            sl_entry_atr_mult_key = self._entry_param_if_exists("sl_entry_atr_mult")
            if (
                sl_use_entry_atr_key is not None
                and param_name == sl_use_entry_atr_key
                and bool(params.get(param_name))
                and stop_ref_profile_key is not None
            ):
                params[stop_ref_profile_key] = False
            if (
                stop_ref_profile_key is not None
                and param_name == stop_ref_profile_key
                and bool(params.get(param_name))
                and sl_use_entry_atr_key is not None
            ):
                params[sl_use_entry_atr_key] = False
            if (
                sl_entry_atr_mult_key is not None
                and param_name == sl_entry_atr_mult_key
                and stop_ref_profile_key is not None
            ):
                params[stop_ref_profile_key] = False
            return
        if dim_id == "sl_ref_profile":
            sl_use_entry_atr_key = self._entry_param_if_exists("sl_use_entry_atr")
            stop_ref_profile_key = self._stop_ref_profile_flag_key()
            if sl_use_entry_atr_key is not None:
                params[sl_use_entry_atr_key] = False
            if stop_ref_profile_key is not None:
                params[stop_ref_profile_key] = True
            self._set_all_sl_ref_sources_off(params)
            profile = self._normalize_sl_ref_profile(value)
            if profile == "off":
                if stop_ref_profile_key is not None:
                    params[stop_ref_profile_key] = False
                return
            source, lookback_txt = profile.rsplit("_", 1)
            source_key = self._stop_ref_source_key(int(lookback_txt))
            if source_key is None:
                raise ValueError("sl_ref_profile requires stop_ref_bar_1..5_source execution params in schema.")
            params[source_key] = source
            return
        raise ValueError("Unknown sweep dimension: %s" % dim_id)

    def _dimension_sweep_values(self, dim_id: str) -> List[Any]:
        override = self.sweep_range_overrides.get(dim_id)
        if isinstance(override, dict):
            values = list(override.get("values") or [])
            if len(values) == 0:
                raise ValueError("Sweep range override for '%s' produced no values." % dim_id)
            return values
        prepared_values = self.prepared_dimension_ranges.get(dim_id)
        if isinstance(prepared_values, list) and len(prepared_values) > 0:
            return list(prepared_values)

        if dim_id == "sl_ref_profile":
            return sl_ref_profile_values()

        param_name = self._dim_param_name(dim_id)
        if param_name is not None:
            spec = self.entry_param_specs.get(param_name, {})
            value_type = str(spec.get("type", "")).strip().lower()
            if value_type == "bool":
                return ["off", "on"]
            if value_type == "enum":
                choices = list(spec.get("choices") or [])
                return choices if len(choices) > 0 else [spec.get("default")]
            if value_type in ("int", "float"):
                if self._is_rsi_0_100_numeric_spec(spec):
                    rsi_vals = rsi_max_sweep_values()
                    if value_type == "int":
                        return [int(round(v)) for v in rsi_vals]
                    return [round(float(v), 4) for v in rsi_vals]
                return self._build_numeric_sweep_from_spec(spec)
            return [spec.get("default")]
        raise ValueError("Unknown sweep dimension: %s" % dim_id)

    def _dimension_current_value_from_params(self, params: Dict[str, Any], dim_id: str) -> Any:
        if dim_id == "sl_ref_profile":
            stop_ref_profile_key = self._stop_ref_profile_flag_key()
            if stop_ref_profile_key is not None and (not bool(params.get(stop_ref_profile_key, False))):
                return "off"
            active: List[Tuple[int, str]] = []
            for lookback in range(1, 6):
                source_key = self._stop_ref_source_key(lookback)
                if source_key is None:
                    continue
                source = self._normalize_sl_ref_source(params.get(source_key, "off"))
                if source != "off":
                    active.append((lookback, source))
            if len(active) == 1 and active[0][1] in ("low", "min_oc"):
                lookback, source = active[0]
                return f"{source}_{lookback}"
            return "off"

        param_name = self._dim_param_name(dim_id)
        if param_name is not None:
            spec = self.entry_param_specs.get(param_name, {})
            return params.get(param_name, copy.deepcopy(spec.get("default")))
        raise ValueError("Unknown sweep dimension: %s" % dim_id)

    def _dimension_current_value(self, dim_id: str) -> Any:
        return self._dimension_current_value_from_params(params=self.current_params, dim_id=dim_id)

    def _dimension_relax_values(self, dim_id: str, current: Any) -> List[Any]:
        if dim_id == "sl_ref_profile":
            current_profile = self._normalize_sl_ref_profile(current)
            return [current_profile] + [v for v in sl_ref_profile_values() if v != current_profile]

        param_name = self._dim_param_name(dim_id)
        if param_name is not None:
            spec = self.entry_param_specs.get(param_name, {})
            value_type = str(spec.get("type", "")).strip().lower()
            if value_type == "bool":
                curr = "on" if (not self._is_off_value(current)) else "off"
                return [curr, ("off" if curr == "on" else "on")]
            if value_type == "enum":
                vals = self._dimension_sweep_values(dim_id=dim_id)
                curr = str(current)
                return [curr] + [v for v in vals if str(v) != curr]
            if value_type in ("int", "float"):
                sweep_vals = self._dimension_sweep_values(dim_id=dim_id)
                relaxed = _grid_relax_values(sweep=[float(v) for v in sweep_vals], current=float(current), steps=4)
                if value_type == "int":
                    return [int(round(v)) for v in relaxed]
                return [round(float(v), 4) for v in relaxed]
            return [current]
        raise ValueError("Unknown sweep dimension: %s" % dim_id)

    def _dimension_permissive_value(self, dim_id: str) -> Optional[Any]:
        if dim_id == "sl_ref_profile":
            return "off"
        if self._dim_param_name(dim_id) is not None:
            return None
        return None

    @staticmethod
    def _format_dimension_value(value: Any) -> str:
        if isinstance(value, bool):
            return "on" if value else "off"
        if isinstance(value, (int, float)):
            return "%.2f" % float(value)
        return str(value)

    @staticmethod
    def _normalize_objective(value: Any, default: str = OBJECTIVE_PROFIT) -> str:
        default_raw = str(default if default is not None else OBJECTIVE_PROFIT).strip().lower()
        default_key = OBJECTIVE_ALIASES.get(default_raw, default_raw)
        if default_key not in OBJECTIVE_KEYS:
            default_key = OBJECTIVE_PROFIT

        raw = str(value if value is not None else default_key).strip().lower()
        key = OBJECTIVE_ALIASES.get(raw, raw)
        if key not in OBJECTIVE_KEYS:
            return default_key
        return key

    def _stage_objective(self, stage_bucket: str) -> str:
        bucket = str(stage_bucket).strip().lower()
        if bucket == "confirmation":
            return self._normalize_objective(getattr(self.args, "stage2_objective", OBJECTIVE_PROFIT), default=OBJECTIVE_PROFIT)
        if bucket == "sl":
            return self._normalize_objective(getattr(self.args, "stage3_objective", OBJECTIVE_REL), default=OBJECTIVE_REL)
        return self._normalize_objective(getattr(self.args, "stage2_objective", OBJECTIVE_PROFIT), default=OBJECTIVE_PROFIT)

    def _objective_for_dimension(self, dim_id: str) -> str:
        return self._stage_objective(self._dimension_stage_bucket(dim_id))

    @staticmethod
    def _objective_label(objective: str) -> str:
        key = OBJECTIVE_ALIASES.get(str(objective).strip().lower(), str(objective).strip().lower())
        if key == OBJECTIVE_REL:
            return "best-rel(profit/|dd|)"
        if key == OBJECTIVE_REL2_SIGNED:
            return "best-rel2-signed(sign(p)*p^2/|dd|)"
        if key == OBJECTIVE_PROFIT_FLOOR_DD:
            return "best-profit-floor-dd"
        if key == OBJECTIVE_PROFIT_DD_SOFTCAP:
            return "best-profit-dd-softcap"
        return "best-profit"

    def _objective_profit_floor_ratio(self) -> float:
        raw = getattr(self.args, "objective_profit_floor_ratio", 0.85)
        try:
            ratio = float(raw)
        except Exception:
            ratio = 0.85
        if not math.isfinite(ratio):
            ratio = 0.85
        return min(1.0, max(0.01, ratio))

    def _objective_dd_cap(self) -> float:
        raw = getattr(self.args, "objective_dd_cap", 20.0)
        try:
            cap = float(raw)
        except Exception:
            cap = 20.0
        if not math.isfinite(cap):
            cap = 20.0
        return max(0.0, cap)

    def _objective_dd_penalty(self) -> float:
        raw = getattr(self.args, "objective_dd_penalty", 0.25)
        try:
            penalty = float(raw)
        except Exception:
            penalty = 0.25
        if not math.isfinite(penalty):
            penalty = 0.25
        return max(0.0, penalty)

    @staticmethod
    def _stage_uses_rel(stage: str) -> bool:
        txt = str(stage).lower()
        return "sl_" in txt

    def _dimension_stage_bucket(self, dim_id: str) -> str:
        if dim_id == "sl_ref_profile" or str(dim_id).startswith("sl_"):
            return "sl"
        param_class = self._dim_param_class(dim_id)
        if param_class == "confirmation":
            return "filter"
        if param_class == "execution":
            pname = (self._dim_param_name(dim_id) or "").lower()
            if "_sl_" in pname or "_stop_" in pname or pname.endswith("_stop") or pname.endswith("_stop_atr"):
                return "sl"
        return "filter"

    def _is_better_by_objective(self, lhs_metrics: Dict[str, Any], rhs_metrics: Dict[str, Any], objective: str) -> bool:
        objective_key = self._normalize_objective(objective, default=OBJECTIVE_PROFIT)
        if objective_key == OBJECTIVE_REL:
            return self._is_better_rel_result(lhs_metrics, rhs_metrics)
        if objective_key == OBJECTIVE_REL2_SIGNED:
            return self._is_better_rel2_signed_result(lhs_metrics, rhs_metrics)
        if objective_key == OBJECTIVE_PROFIT_FLOOR_DD:
            return self._is_better_profit_floor_dd_result(lhs_metrics, rhs_metrics)
        if objective_key == OBJECTIVE_PROFIT_DD_SOFTCAP:
            return self._is_better_profit_dd_softcap_result(lhs_metrics, rhs_metrics)
        return self._is_better_profit_result(lhs_metrics, rhs_metrics)

    def _is_not_worse_by_objective(self, lhs_metrics: Dict[str, Any], rhs_metrics: Dict[str, Any], objective: str) -> bool:
        objective_key = self._normalize_objective(objective, default=OBJECTIVE_PROFIT)
        if objective_key == OBJECTIVE_REL:
            return self._is_not_worse_rel_result(lhs_metrics, rhs_metrics)
        if objective_key == OBJECTIVE_REL2_SIGNED:
            return self._is_not_worse_rel2_signed_result(lhs_metrics, rhs_metrics)
        if objective_key == OBJECTIVE_PROFIT_FLOOR_DD:
            return self._is_not_worse_profit_floor_dd_result(lhs_metrics, rhs_metrics)
        if objective_key == OBJECTIVE_PROFIT_DD_SOFTCAP:
            return self._is_not_worse_profit_dd_softcap_result(lhs_metrics, rhs_metrics)
        return self._is_not_worse_profit_result(lhs_metrics, rhs_metrics)

    def _beats_benchmark_by_objective(self, candidate_metrics: Dict[str, Any], benchmark_metrics: Dict[str, Any], objective: str) -> bool:
        objective_key = self._normalize_objective(objective, default=OBJECTIVE_PROFIT)
        if objective_key == OBJECTIVE_REL:
            return self._is_better_rel_result(candidate_metrics, benchmark_metrics)
        if objective_key == OBJECTIVE_REL2_SIGNED:
            return self._is_better_rel2_signed_result(candidate_metrics, benchmark_metrics)
        if objective_key == OBJECTIVE_PROFIT_FLOOR_DD:
            return self._is_better_profit_floor_dd_result(candidate_metrics, benchmark_metrics)
        if objective_key == OBJECTIVE_PROFIT_DD_SOFTCAP:
            return self._is_better_profit_dd_softcap_result(candidate_metrics, benchmark_metrics)
        return self._is_better_profit_then_rel_result(candidate_metrics, benchmark_metrics)

    def _run_trial(
        self,
        params: Dict[str, Any],
        stage: str,
        label: str,
        early_stop_max_trades: Optional[int] = None,
    ) -> TrialResult:
        start = time.time()
        early_cfg = None
        if early_stop_max_trades is not None:
            early_cfg = {"max_trades_closed": int(early_stop_max_trades)}
        bt = BackTest(
            self._build_bot(entry_cfg=params, timeframe=int(self.args.timeframe)),
            bars=copy.deepcopy(self.bars),
            funding=self.funding,
            symbol=self.symbol,
            early_stop_config=early_cfg,
        ).run()
        elapsed = time.time() - start
        metrics = bt.metrics if isinstance(bt.metrics, dict) else {}
        result = TrialResult(
            metrics=metrics,
            elapsed_s=elapsed,
            early_stopped=bool(getattr(bt, "early_stopped", False)),
            early_stop_reason=str(getattr(bt, "early_stop_reason", "")) if getattr(bt, "early_stopped", False) else None,
        )
        self._record_event(
            "trial",
            {
                "stage": stage,
                "label": label,
                "elapsed_s": round(elapsed, 3),
                "profit_pct": metric(metrics, "profit_pct"),
                "max_drawdown_pct": metric(metrics, "max_drawdown_pct"),
                "trades_closed": int(metric(metrics, "trades_closed")),
                "early_stopped": result.early_stopped,
                "early_stop_reason": result.early_stop_reason,
                "params": params,
            },
        )
        rel_value = self._value_rel(metrics)
        self.logger.info(
            "[%s] %s | profit=%.2f dd=%.2f rel=%.2f trades=%d early=%s elapsed=%.1fs",
            stage,
            label,
            metric(metrics, "profit_pct"),
            metric(metrics, "max_drawdown_pct"),
            rel_value,
            int(metric(metrics, "trades_closed")),
            str(result.early_stopped),
            float(elapsed),
        )
        self._progress(
            "[%s] %s | profit=%.2f dd=%.2f rel=%.2f trades=%d early=%s elapsed=%.1fs"
            % (
                stage,
                label,
                metric(metrics, "profit_pct"),
                metric(metrics, "max_drawdown_pct"),
                rel_value,
                int(metric(metrics, "trades_closed")),
                str(result.early_stopped),
                float(elapsed),
            )
        )
        return result

    def _resolve_eval_workers(self, batch_size: int) -> Tuple[int, Dict[str, Any]]:
        details: Dict[str, Any] = {
            "requested_workers": int(getattr(self.args, "eval_workers", 0)),
            "cpu_count": int(os.cpu_count() or 1),
            "batch_size": int(max(1, batch_size)),
            "max_eval_workers": int(getattr(self.args, "max_eval_workers", 0)),
            "ram_aware": bool(getattr(self.args, "ram_aware_workers", True)),
            "ram_available_gb": None,
            "ram_limit_workers": None,
            "resolved_workers": 1,
        }

        requested = int(getattr(self.args, "eval_workers", 0))
        cpu = int(os.cpu_count() or 1)
        workers = requested if requested > 0 else max(1, cpu - 1)
        workers = max(1, min(int(workers), int(max(1, batch_size))))
        max_eval_workers = int(getattr(self.args, "max_eval_workers", 0))
        if max_eval_workers > 0:
            workers = max(1, min(int(workers), int(max_eval_workers)))

        if bool(getattr(self.args, "ram_aware_workers", True)):
            avail_gb = available_ram_gb()
            details["ram_available_gb"] = None if avail_gb is None else round(float(avail_gb), 3)
            if avail_gb is not None:
                reserve_gb = max(0.0, float(getattr(self.args, "ram_reserve_gb", 8.0)))
                per_worker_gb = max(0.1, float(getattr(self.args, "worker_ram_gb", 2.0)))
                usable_gb = max(0.0, float(avail_gb) - reserve_gb)
                ram_limit = int(max(1, math.floor(usable_gb / per_worker_gb))) if usable_gb > 0 else 1
                details["ram_limit_workers"] = int(ram_limit)
                workers = max(1, min(int(workers), int(ram_limit)))

        details["resolved_workers"] = int(workers)
        return int(workers), details

    def _run_trials_parallel(
        self,
        stage: str,
        candidates: List[Tuple[Any, Dict[str, Any], str]],
    ) -> List[Tuple[Any, Dict[str, Any], TrialResult]]:
        if len(candidates) == 0:
            return []

        workers, worker_details = self._resolve_eval_workers(batch_size=len(candidates))
        self._record_event(
            "parallel_batch_start",
            {
                "stage": stage,
                "candidate_count": len(candidates),
                **worker_details,
            },
        )
        self._progress(
            "[%s] candidates=%d workers=%d"
            % (stage, len(candidates), workers)
        )

        if workers <= 1:
            out: List[Tuple[Any, Dict[str, Any], TrialResult]] = []
            accept_best_requested = False
            for value, params, label in candidates:
                out.append((value, params, self._run_trial(params=params, stage=stage, label=label, early_stop_max_trades=None)))
                if self._consume_control_command(stage) == "accept_best":
                    accept_best_requested = True
                    break
            if accept_best_requested:
                self._record_event(
                    "parallel_batch_fast_forward",
                    {
                        "stage": stage,
                        "candidate_count": len(candidates),
                        "completed_count": len(out),
                        "skipped_count": max(0, len(candidates) - len(out)),
                        "workers": int(workers),
                    },
                )
                self._progress(
                    "[%s] fast-forward accepted; skipped %d pending candidates."
                    % (stage, max(0, len(candidates) - len(out)))
                )
            self._record_event(
                "parallel_batch_done",
                {
                    "stage": stage,
                    "candidate_count": len(candidates),
                    "completed_count": len(out),
                    "workers": int(workers),
                },
            )
            return out

        ordered: List[Optional[Tuple[Any, Dict[str, Any], TrialResult]]] = [None] * len(candidates)
        payload_common = {
            "pair": self.args.pair,
            "exchange": self.args.exchange,
            "timeframe": int(self.args.timeframe),
            "days": int(self.args.days),
            "entry_id": self.entry_id,
        }
        accept_best_requested = False
        fast_forward_logged = False
        skipped_unscheduled = 0
        fallback_used = False
        try:
            with concurrent.futures.ProcessPoolExecutor(max_workers=int(workers), mp_context=mp.get_context("spawn")) as pool:
                futures: Dict[concurrent.futures.Future, Tuple[int, Any, Dict[str, Any], str]] = {}

                def submit_candidate(idx: int):
                    value, params, label = candidates[idx]
                    payload = dict(payload_common)
                    payload["params"] = params
                    fut = pool.submit(_parallel_eval_trial, payload)
                    futures[fut] = (idx, value, params, label)

                next_idx = 0
                initial_submit = min(int(workers), len(candidates))
                for _ in range(initial_submit):
                    submit_candidate(next_idx)
                    next_idx += 1

                completed = 0
                while len(futures) > 0:
                    done, _pending = concurrent.futures.wait(
                        futures.keys(),
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                    for fut in done:
                        idx, value, params, label = futures.pop(fut)
                        completed += 1
                        try:
                            row = fut.result()
                        except Exception as exc:
                            self._record_event(
                                "trial_error",
                                {"stage": stage, "label": label, "error": str(exc)},
                            )
                            self._progress("[%s] worker error for %s: %s" % (stage, label, str(exc)))
                            row = None

                        if isinstance(row, dict) and row.get("error"):
                            self._record_event(
                                "trial_error",
                                {"stage": stage, "label": label, "error": str(row.get("error"))},
                            )
                            self._progress("[%s] worker error for %s: %s" % (stage, label, str(row.get("error"))))
                            row = None

                        if isinstance(row, dict):
                            metrics = dict(row.get("metrics", {}))
                            trial_result = TrialResult(
                                metrics=metrics,
                                elapsed_s=float(row.get("elapsed_s", 0.0)),
                                early_stopped=bool(row.get("early_stopped", False)),
                                early_stop_reason=row.get("early_stop_reason"),
                            )
                            ordered[idx] = (value, params, trial_result)

                            self._record_event(
                                "trial",
                                {
                                    "stage": stage,
                                    "label": label,
                                    "elapsed_s": round(float(trial_result.elapsed_s), 3),
                                    "profit_pct": metric(metrics, "profit_pct"),
                                    "max_drawdown_pct": metric(metrics, "max_drawdown_pct"),
                                    "trades_closed": int(metric(metrics, "trades_closed")),
                                    "early_stopped": trial_result.early_stopped,
                                    "early_stop_reason": trial_result.early_stop_reason,
                                    "params": params,
                                },
                            )
                            self._progress(
                                "[%s] %s | profit=%.2f dd=%.2f rel=%.2f trades=%d elapsed=%.1fs (%d/%d)"
                                % (
                                    stage,
                                    label,
                                    metric(metrics, "profit_pct"),
                                    metric(metrics, "max_drawdown_pct"),
                                    self._value_rel(metrics),
                                    int(metric(metrics, "trades_closed")),
                                    float(trial_result.elapsed_s),
                                    completed,
                                    len(candidates),
                                )
                            )

                        if not accept_best_requested and self._consume_control_command(stage) == "accept_best":
                            accept_best_requested = True
                            skipped_unscheduled = max(0, len(candidates) - next_idx)
                            if not fast_forward_logged:
                                self._record_event(
                                    "parallel_batch_fast_forward",
                                    {
                                        "stage": stage,
                                        "candidate_count": len(candidates),
                                        "completed_count": len([row for row in ordered if row is not None]),
                                        "skipped_count": skipped_unscheduled,
                                        "in_flight_count": len(futures),
                                        "workers": int(workers),
                                    },
                                )
                                self._progress(
                                    "[%s] fast-forward accepted; skipped %d unscheduled candidates, waiting for %d in-flight trials."
                                    % (stage, skipped_unscheduled, len(futures))
                                )
                                fast_forward_logged = True

                        if (not accept_best_requested) and next_idx < len(candidates):
                            submit_candidate(next_idx)
                            next_idx += 1
        except Exception as exc:
            fallback_used = True
            self._record_event(
                "parallel_batch_error",
                {
                    "stage": stage,
                    "error": str(exc),
                    "candidate_count": len(candidates),
                    "completed_count": len([row for row in ordered if row is not None]),
                    "workers": int(workers),
                },
            )
            self._progress(
                "[%s] parallel execution failed (%s); falling back to sequential for remaining candidates."
                % (stage, str(exc))
            )
            for idx, row in enumerate(ordered):
                if row is not None:
                    continue
                value, params, label = candidates[idx]
                try:
                    trial = self._run_trial(params=params, stage=stage, label=label, early_stop_max_trades=None)
                    ordered[idx] = (value, params, trial)
                except Exception as seq_exc:
                    self._record_event(
                        "trial_error",
                        {
                            "stage": stage,
                            "label": label,
                            "error": "sequential_fallback_error: %s" % str(seq_exc),
                        },
                    )
                    self._progress("[%s] sequential fallback error for %s: %s" % (stage, label, str(seq_exc)))
                if self._consume_control_command(stage) == "accept_best":
                    break

        out = [row for row in ordered if row is not None]
        self._record_event(
            "parallel_batch_done",
            {
                "stage": stage,
                "candidate_count": len(candidates),
                "completed_count": len(out),
                "workers": int(workers),
                "early_accept_best": bool(accept_best_requested),
                "skipped_unscheduled": int(skipped_unscheduled),
                "fallback_used": bool(fallback_used),
            },
        )
        return out

    @staticmethod
    def _is_better_profit_result(cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        cand_profit = metric(cand_metrics, "profit_pct")
        ref_profit = metric(ref_metrics, "profit_pct")
        cand_dd = metric(cand_metrics, "max_drawdown_pct")
        ref_dd = metric(ref_metrics, "max_drawdown_pct")
        cand_trades = int(metric(cand_metrics, "trades_closed"))
        ref_trades = int(metric(ref_metrics, "trades_closed"))

        if cand_profit > ref_profit + 1e-9:
            return True
        if abs(cand_profit - ref_profit) <= 1e-9:
            if cand_dd > ref_dd + 1e-9:
                return True
            if abs(cand_dd - ref_dd) <= 1e-9 and cand_trades > ref_trades:
                return True
        return False

    @classmethod
    def _is_better_profit_then_rel_result(cls, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        cand_profit = metric(cand_metrics, "profit_pct")
        ref_profit = metric(ref_metrics, "profit_pct")
        cand_rel = cls._value_rel(cand_metrics)
        ref_rel = cls._value_rel(ref_metrics)
        cand_dd = metric(cand_metrics, "max_drawdown_pct")
        ref_dd = metric(ref_metrics, "max_drawdown_pct")
        cand_trades = int(metric(cand_metrics, "trades_closed"))
        ref_trades = int(metric(ref_metrics, "trades_closed"))

        if cand_profit > ref_profit + 1e-9:
            return True
        if abs(cand_profit - ref_profit) <= 1e-9:
            if cand_rel > ref_rel + 1e-9:
                return True
            if abs(cand_rel - ref_rel) <= 1e-9:
                if cand_dd > ref_dd + 1e-9:
                    return True
                if abs(cand_dd - ref_dd) <= 1e-9 and cand_trades > ref_trades:
                    return True
        return False

    @classmethod
    def _is_not_worse_profit_result(cls, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        return cls._is_better_profit_result(cand_metrics, ref_metrics) or (
            abs(metric(cand_metrics, "profit_pct") - metric(ref_metrics, "profit_pct")) <= 1e-9
            and abs(metric(cand_metrics, "max_drawdown_pct") - metric(ref_metrics, "max_drawdown_pct")) <= 1e-9
            and int(metric(cand_metrics, "trades_closed")) == int(metric(ref_metrics, "trades_closed"))
        )

    @staticmethod
    def _value_rel(metrics: Dict[str, Any]) -> float:
        profit = metric(metrics, "profit_pct")
        dd_abs = abs(metric(metrics, "max_drawdown_pct"))
        if dd_abs <= 1e-9:
            if profit > 0:
                return float("inf")
            if profit < 0:
                return float("-inf")
            return 0.0
        return float(profit) / float(dd_abs)

    @classmethod
    def _is_better_rel_result(cls, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        cand_rel = cls._value_rel(cand_metrics)
        ref_rel = cls._value_rel(ref_metrics)
        cand_profit = metric(cand_metrics, "profit_pct")
        ref_profit = metric(ref_metrics, "profit_pct")
        cand_dd = metric(cand_metrics, "max_drawdown_pct")
        ref_dd = metric(ref_metrics, "max_drawdown_pct")
        cand_trades = int(metric(cand_metrics, "trades_closed"))
        ref_trades = int(metric(ref_metrics, "trades_closed"))

        if cand_rel > ref_rel + 1e-9:
            return True
        if abs(cand_rel - ref_rel) <= 1e-9:
            if cand_profit > ref_profit + 1e-9:
                return True
            if abs(cand_profit - ref_profit) <= 1e-9:
                if cand_dd > ref_dd + 1e-9:
                    return True
                if abs(cand_dd - ref_dd) <= 1e-9 and cand_trades > ref_trades:
                    return True
        return False

    @classmethod
    def _is_not_worse_rel_result(cls, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        return cls._is_better_rel_result(cand_metrics, ref_metrics) or (
            abs(cls._value_rel(cand_metrics) - cls._value_rel(ref_metrics)) <= 1e-9
            and abs(metric(cand_metrics, "profit_pct") - metric(ref_metrics, "profit_pct")) <= 1e-9
            and abs(metric(cand_metrics, "max_drawdown_pct") - metric(ref_metrics, "max_drawdown_pct")) <= 1e-9
            and int(metric(cand_metrics, "trades_closed")) == int(metric(ref_metrics, "trades_closed"))
        )

    @classmethod
    def _value_rel2_signed(cls, metrics: Dict[str, Any]) -> float:
        profit = metric(metrics, "profit_pct")
        rel = cls._value_rel(metrics)
        if abs(profit) <= 1e-9:
            return 0.0
        return float(profit) * float(rel)

    @classmethod
    def _is_better_rel2_signed_result(cls, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        cand_score = cls._value_rel2_signed(cand_metrics)
        ref_score = cls._value_rel2_signed(ref_metrics)
        cand_profit = metric(cand_metrics, "profit_pct")
        ref_profit = metric(ref_metrics, "profit_pct")
        cand_dd_abs = abs(metric(cand_metrics, "max_drawdown_pct"))
        ref_dd_abs = abs(metric(ref_metrics, "max_drawdown_pct"))
        cand_trades = int(metric(cand_metrics, "trades_closed"))
        ref_trades = int(metric(ref_metrics, "trades_closed"))

        if cand_score > ref_score + 1e-9:
            return True
        if abs(cand_score - ref_score) <= 1e-9:
            if cand_profit > ref_profit + 1e-9:
                return True
            if abs(cand_profit - ref_profit) <= 1e-9:
                if cand_dd_abs < ref_dd_abs - 1e-9:
                    return True
                if abs(cand_dd_abs - ref_dd_abs) <= 1e-9 and cand_trades > ref_trades:
                    return True
        return False

    @classmethod
    def _is_not_worse_rel2_signed_result(cls, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        return cls._is_better_rel2_signed_result(cand_metrics, ref_metrics) or (
            abs(cls._value_rel2_signed(cand_metrics) - cls._value_rel2_signed(ref_metrics)) <= 1e-9
            and abs(metric(cand_metrics, "profit_pct") - metric(ref_metrics, "profit_pct")) <= 1e-9
            and abs(metric(cand_metrics, "max_drawdown_pct") - metric(ref_metrics, "max_drawdown_pct")) <= 1e-9
            and int(metric(cand_metrics, "trades_closed")) == int(metric(ref_metrics, "trades_closed"))
        )

    @staticmethod
    def _value_dd_abs(metrics: Dict[str, Any]) -> float:
        return abs(metric(metrics, "max_drawdown_pct"))

    @staticmethod
    def _profit_floor_threshold(best_profit: float, ratio: float) -> float:
        rr = min(1.0, max(0.01, float(ratio)))
        if float(best_profit) >= 0.0:
            return float(best_profit) * rr
        return float(best_profit) / rr

    @classmethod
    def _profit_meets_floor(cls, profit: float, anchor_profit: float, ratio: float) -> bool:
        floor = cls._profit_floor_threshold(best_profit=anchor_profit, ratio=ratio)
        return float(profit) + 1e-9 >= floor

    @classmethod
    def _is_better_low_dd_result(cls, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        cand_dd_abs = cls._value_dd_abs(cand_metrics)
        ref_dd_abs = cls._value_dd_abs(ref_metrics)
        cand_profit = metric(cand_metrics, "profit_pct")
        ref_profit = metric(ref_metrics, "profit_pct")
        cand_trades = int(metric(cand_metrics, "trades_closed"))
        ref_trades = int(metric(ref_metrics, "trades_closed"))

        if cand_dd_abs < ref_dd_abs - 1e-9:
            return True
        if abs(cand_dd_abs - ref_dd_abs) <= 1e-9:
            if cand_profit > ref_profit + 1e-9:
                return True
            if abs(cand_profit - ref_profit) <= 1e-9 and cand_trades > ref_trades:
                return True
        return False

    def _value_profit_dd_softcap(self, metrics: Dict[str, Any]) -> float:
        profit = metric(metrics, "profit_pct")
        dd_abs = self._value_dd_abs(metrics)
        dd_cap = self._objective_dd_cap()
        dd_excess = max(0.0, dd_abs - dd_cap)
        penalty = self._objective_dd_penalty() * (dd_excess ** 2)
        return float(profit) - float(penalty)

    def _is_better_profit_dd_softcap_result(self, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        cand_score = self._value_profit_dd_softcap(cand_metrics)
        ref_score = self._value_profit_dd_softcap(ref_metrics)
        cand_profit = metric(cand_metrics, "profit_pct")
        ref_profit = metric(ref_metrics, "profit_pct")
        cand_dd_abs = self._value_dd_abs(cand_metrics)
        ref_dd_abs = self._value_dd_abs(ref_metrics)
        cand_trades = int(metric(cand_metrics, "trades_closed"))
        ref_trades = int(metric(ref_metrics, "trades_closed"))

        if cand_score > ref_score + 1e-9:
            return True
        if abs(cand_score - ref_score) <= 1e-9:
            if cand_profit > ref_profit + 1e-9:
                return True
            if abs(cand_profit - ref_profit) <= 1e-9:
                if cand_dd_abs < ref_dd_abs - 1e-9:
                    return True
                if abs(cand_dd_abs - ref_dd_abs) <= 1e-9 and cand_trades > ref_trades:
                    return True
        return False

    def _is_not_worse_profit_dd_softcap_result(self, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        return self._is_better_profit_dd_softcap_result(cand_metrics, ref_metrics) or (
            abs(self._value_profit_dd_softcap(cand_metrics) - self._value_profit_dd_softcap(ref_metrics)) <= 1e-9
            and abs(metric(cand_metrics, "profit_pct") - metric(ref_metrics, "profit_pct")) <= 1e-9
            and abs(self._value_dd_abs(cand_metrics) - self._value_dd_abs(ref_metrics)) <= 1e-9
            and int(metric(cand_metrics, "trades_closed")) == int(metric(ref_metrics, "trades_closed"))
        )

    def _is_better_profit_floor_dd_result(self, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        ratio = self._objective_profit_floor_ratio()
        cand_profit = metric(cand_metrics, "profit_pct")
        ref_profit = metric(ref_metrics, "profit_pct")
        if not self._profit_meets_floor(profit=cand_profit, anchor_profit=ref_profit, ratio=ratio):
            return False
        return self._is_better_low_dd_result(cand_metrics, ref_metrics)

    def _is_not_worse_profit_floor_dd_result(self, cand_metrics: Dict[str, Any], ref_metrics: Dict[str, Any]) -> bool:
        if self._is_better_profit_floor_dd_result(cand_metrics, ref_metrics):
            return True
        ratio = self._objective_profit_floor_ratio()
        cand_profit = metric(cand_metrics, "profit_pct")
        ref_profit = metric(ref_metrics, "profit_pct")
        return (
            self._profit_meets_floor(profit=cand_profit, anchor_profit=ref_profit, ratio=ratio)
            and abs(self._value_dd_abs(cand_metrics) - self._value_dd_abs(ref_metrics)) <= 1e-9
            and abs(cand_profit - ref_profit) <= 1e-9
            and int(metric(cand_metrics, "trades_closed")) == int(metric(ref_metrics, "trades_closed"))
        )

    def _select_best_trial_row_by_objective(
        self,
        trial_rows: List[Tuple[Any, Dict[str, Any], TrialResult]],
        objective: str,
    ) -> Optional[Tuple[Any, Dict[str, Any], TrialResult]]:
        objective_key = self._normalize_objective(objective, default=OBJECTIVE_PROFIT)
        candidates: List[Tuple[Any, Dict[str, Any], TrialResult]] = [
            row for row in trial_rows if int(metric(row[2].metrics, "trades_closed")) > 0
        ]
        if len(candidates) == 0:
            return None

        if objective_key == OBJECTIVE_PROFIT_FLOOR_DD:
            ratio = self._objective_profit_floor_ratio()
            best_profit = max(metric(row[2].metrics, "profit_pct") for row in candidates)
            floor = self._profit_floor_threshold(best_profit=best_profit, ratio=ratio)
            shortlist = [row for row in candidates if metric(row[2].metrics, "profit_pct") + 1e-9 >= floor]
            scoped_rows = shortlist if len(shortlist) > 0 else candidates
            best_row = scoped_rows[0]
            for row in scoped_rows[1:]:
                if self._is_better_low_dd_result(row[2].metrics, best_row[2].metrics):
                    best_row = row
            return best_row

        best_row = candidates[0]
        for row in candidates[1:]:
            if self._is_better_by_objective(row[2].metrics, best_row[2].metrics, objective_key):
                best_row = row
        return best_row

    def _set_benchmark(self, label: str, params: Dict[str, Any], metrics: Dict[str, Any]):
        old = self.benchmark
        self.benchmark = Benchmark(params=copy.deepcopy(params), metrics=copy.deepcopy(metrics), label=label)
        self.current_params = copy.deepcopy(params)
        if old is None:
            self.logger.info(
                "Benchmark initialized (%s): profit=%.2f dd=%.2f rel=%.2f trades=%d",
                label,
                metric(metrics, "profit_pct"),
                metric(metrics, "max_drawdown_pct"),
                self._value_rel(metrics),
                int(metric(metrics, "trades_closed")),
            )
            self._progress(
                "Benchmark initialized (%s): profit=%.2f dd=%.2f rel=%.2f trades=%d"
                % (
                    label,
                    metric(metrics, "profit_pct"),
                    metric(metrics, "max_drawdown_pct"),
                    self._value_rel(metrics),
                    int(metric(metrics, "trades_closed")),
                )
            )
        else:
            self.logger.info(
                "Benchmark updated (%s): profit %.2f -> %.2f | dd %.2f -> %.2f | rel %.2f -> %.2f | trades %d -> %d",
                label,
                metric(old.metrics, "profit_pct"),
                metric(metrics, "profit_pct"),
                metric(old.metrics, "max_drawdown_pct"),
                metric(metrics, "max_drawdown_pct"),
                self._value_rel(old.metrics),
                self._value_rel(metrics),
                int(metric(old.metrics, "trades_closed")),
                int(metric(metrics, "trades_closed")),
            )
            self._progress(
                "Benchmark updated (%s): profit %.2f -> %.2f | dd %.2f -> %.2f | rel %.2f -> %.2f | trades %d -> %d"
                % (
                    label,
                    metric(old.metrics, "profit_pct"),
                    metric(metrics, "profit_pct"),
                    metric(old.metrics, "max_drawdown_pct"),
                    metric(metrics, "max_drawdown_pct"),
                    self._value_rel(old.metrics),
                    self._value_rel(metrics),
                    int(metric(old.metrics, "trades_closed")),
                    int(metric(metrics, "trades_closed")),
                )
            )
        self._record_event(
            "benchmark_update",
            {
                "label": label,
                "profit_pct": metric(metrics, "profit_pct"),
                "max_drawdown_pct": metric(metrics, "max_drawdown_pct"),
                "trades_closed": int(metric(metrics, "trades_closed")),
                "params": params,
            },
        )

    def _resolved_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name in sorted(self.entry_param_specs.keys()):
            if name in params:
                out[name] = params.get(name)
        return out

    def _effective_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for name in sorted(self.entry_param_specs.keys()):
            if name not in params:
                continue
            spec = self.entry_param_specs.get(name, {})
            class_name = str(spec.get("class", "")).strip().lower()
            value = params.get(name)
            value_type = str(spec.get("type", "")).strip().lower()

            if class_name == "activation":
                out[name] = value
                continue

            if value_type == "bool":
                if str(name).endswith("_enabled"):
                    if bool(value):
                        out[name] = True
                elif bool(value):
                    out[name] = True
                continue

            if value_type == "enum":
                low = str(value).strip().lower()
                if low in ("off", "none", "null", "false", "", "legacy"):
                    continue

            # Hide dependent values when associated enable flags are off.
            hidden = False
            resolved_enable = self._value_enable_param_name(name)
            if resolved_enable is not None and resolved_enable in params and (not bool(params.get(resolved_enable))):
                hidden = True
            if hidden:
                continue
            tail = name[len(self.entry_id) + 1 :] if name.startswith(self.entry_id + "_") else name

            # Hide OI flow/funding threshold knobs when their state selector is effectively off.
            if tail.startswith("oi_flow_") and tail != "oi_flow_state":
                flow_state_key = self._entry_param_if_exists("oi_flow_state")
                flow_state = str(params.get(flow_state_key, "off")).strip().lower() if flow_state_key is not None else "off"
                if flow_state in ("", "off", "none", "null", "false"):
                    continue
            if tail.startswith("oi_funding_") and tail != "oi_funding_state":
                oi_funding_state_key = self._entry_param_if_exists("oi_funding_state")
                oi_funding_state = (
                    str(params.get(oi_funding_state_key, "off")).strip().lower()
                    if oi_funding_state_key is not None
                    else "off"
                )
                if oi_funding_state in ("", "off", "none", "null", "false"):
                    continue

            # Hide filter lookback knob unless body-expansion filter is enabled.
            body_expansion_key = self._entry_param_if_exists("filter_body_expansion_enabled")
            if tail == "filter_body_compare_lookback":
                if body_expansion_key is None or (not bool(params.get(body_expansion_key, False))):
                    continue

            # Hide SL-dependent execution params when their controlling mode is inactive.
            sl_use_entry_atr_key = self._entry_param_if_exists("sl_use_entry_atr")
            stop_ref_profile_key = self._stop_ref_profile_flag_key()
            sl_entry_atr_mult_key = self._entry_param_if_exists("sl_entry_atr_mult")
            sl_atr_mult_key = self._entry_param_if_exists("sl_atr_mult")
            sl_use_entry_atr = bool(params.get(sl_use_entry_atr_key, False)) if sl_use_entry_atr_key is not None else False
            sl_use_ref_profile = bool(params.get(stop_ref_profile_key, False)) if stop_ref_profile_key is not None else False
            if sl_entry_atr_mult_key is not None and name == sl_entry_atr_mult_key and ((not sl_use_entry_atr) or sl_use_ref_profile):
                continue
            if self._is_stop_ref_source_suffix(tail) and (not sl_use_ref_profile):
                continue
            if sl_atr_mult_key is not None and name == sl_atr_mult_key and (sl_use_entry_atr or sl_use_ref_profile):
                continue

            # Execution knobs with no effect in inactive branches.
            if class_name == "execution":
                stop_mode = str(params.get(self._entry_param_if_exists("stop_mode"), "legacy")).strip().lower()
                sl_module_enabled = bool(params.get(self._entry_param_if_exists("sl_module_enabled"), False))
                secondary_enabled = bool(params.get(self._entry_param_if_exists("secondary_enabled"), False))

                if tail in ("entry_offset_atr", "entry_offset_pct"):
                    if abs(float(value)) <= 1e-12:
                        continue
                if tail == "stop_buffer_atr":
                    if abs(float(value)) <= 1e-12:
                        continue
                if tail == "sl_module_atr_mult":
                    if (not sl_module_enabled) or stop_mode not in ("", "legacy") or sl_use_ref_profile:
                        continue
                if tail == "stop_atr_mult":
                    if stop_mode not in ("atr_from_entry", "atr_from_bar_extreme", "swing_extreme", "hybrid_minmax"):
                        continue
                if tail == "stop_ref_bar_index":
                    if stop_mode not in ("atr_from_bar_extreme", "swing_extreme", "hybrid_minmax"):
                        continue
                if tail == "fixed_stop_price":
                    if stop_mode != "fixed_price":
                        continue
                if tail in ("secondary_entry_offset_atr", "secondary_stop_atr_mult"):
                    if not secondary_enabled:
                        continue
                if self._is_stop_ref_source_suffix(tail):
                    if str(value).strip().lower() in ("off", "", "none", "null", "false"):
                        continue

            out[name] = value
        return out

    # Backward-compatible alias for existing summary/report integrations.
    def _active_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._effective_params(params)

    def _summary(self, status: str, reason: str):
        payload = {
            "run_name": self.run_name,
            "status": status,
            "reason": reason,
            "entry_id": self.entry_id,
            "pair": self.args.pair,
            "exchange": self.exchange,
            "timeframe": int(self.args.timeframe),
            "days": int(self.args.days),
            "benchmark": None,
            "final_confirmation": self.final_confirmation_report,
        }
        if self.benchmark is not None:
            resolved_params = self._resolved_params(self.benchmark.params)
            effective_params = self._effective_params(self.benchmark.params)
            payload["benchmark"] = {
                "label": self.benchmark.label,
                "params": self.benchmark.params,
                "resolved_params": resolved_params,
                "effective_params": effective_params,
                "active_params": effective_params,
                "metrics": self.benchmark.metrics,
            }
        self.final_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        self.logger.info("Final status: %s | %s", status, reason)
        self._progress("Final status: %s | %s" % (status, reason))
        if self.benchmark is not None:
            self.logger.info(
                "Best result: profit=%.2f dd=%.2f rel=%.2f trades=%d",
                metric(self.benchmark.metrics, "profit_pct"),
                metric(self.benchmark.metrics, "max_drawdown_pct"),
                self._value_rel(self.benchmark.metrics),
                int(metric(self.benchmark.metrics, "trades_closed")),
            )
            best_effective = self._effective_params(self.benchmark.params)
            self.logger.info("Best effective params: %s", json.dumps(best_effective, sort_keys=True))
            self._progress(
                "Best result: profit=%.2f dd=%.2f rel=%.2f trades=%d"
                % (
                    metric(self.benchmark.metrics, "profit_pct"),
                    metric(self.benchmark.metrics, "max_drawdown_pct"),
                    self._value_rel(self.benchmark.metrics),
                    int(metric(self.benchmark.metrics, "trades_closed")),
                )
            )
            self._progress("Best effective params: %s" % json.dumps(best_effective, sort_keys=True))
        self.logger.info("Wrote summary: %s", str(self.final_path))
        self._progress("Wrote summary: %s" % str(self.final_path))

    def _emit_dry_run_report(
        self,
        stage1b_dims: List[str],
        filter_dims: List[str],
        sl_dims: List[str],
        skip_stage1b_confirmation: bool,
    ):
        def sweep_map(dims: List[str]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            for dim in dims:
                try:
                    out[dim] = self._dimension_sweep_values(dim)
                except Exception as exc:
                    out[dim] = {"error": str(exc)}
            return out

        payload = {
            "entry_id": self.entry_id,
            "pair": self.args.pair,
            "exchange": self.exchange,
            "timeframe": int(self.args.timeframe),
            "days": int(self.args.days),
            "skip_stage1b_confirmation": bool(skip_stage1b_confirmation),
            "stage_objectives": {
                "stage1b": self._stage_objective("confirmation"),
                "stage2": self._stage_objective("filter"),
                "stage3": self._stage_objective("sl"),
            },
            "constraints": [c.raw for c in self.parameter_constraints],
            "metric_gates": {
                "stage1b": [g.raw for g in self.metric_gates.get("confirmation", [])],
                "stage2": [g.raw for g in self.metric_gates.get("filter", [])],
                "stage3": [g.raw for g in self.metric_gates.get("sl", [])],
            },
            "stage_dimensions": {
                "stage1b": list(stage1b_dims),
                "stage2": list(filter_dims),
                "stage3": list(sl_dims),
            },
            "effective_sweeps": {
                "stage1b": sweep_map(stage1b_dims),
                "stage2": sweep_map(filter_dims),
                "stage3": sweep_map(sl_dims),
            },
            "sweep_range_overrides": {
                dim: {
                    "min": spec.get("min"),
                    "max": spec.get("max"),
                    "step": spec.get("step"),
                    "type": spec.get("type"),
                    "raw_dim": spec.get("raw_dim"),
                    "source": spec.get("source"),
                }
                for dim, spec in self.sweep_range_overrides.items()
            },
        }
        self._record_event("dry_run", payload)
        self._progress("Dry-run resolved stage dimensions and sweep ranges.")
        self._summary(status="dry_run", reason="configuration-only run")

    def _run_final_confirmation(self):
        if self.benchmark is None:
            self.final_confirmation_report = {
                "enabled": False,
                "reason": "no_benchmark",
            }
            self._record_event("final_confirmation", self.final_confirmation_report)
            return

        if not bool(getattr(self.args, "final_confirmation_run", True)):
            self.final_confirmation_report = {
                "enabled": False,
                "reason": "disabled_by_flag",
            }
            self._record_event("final_confirmation", self.final_confirmation_report)
            self._progress("Final confirmation run skipped by flag.")
            return

        self._progress("=== ################################################################# ===")
        self._progress("=== final confirmation: re-run best parameters ===")
        self._progress("=== ################################################################# ===")
        final_params = copy.deepcopy(self.benchmark.params)
        started = time.time()
        try:
            bt = BackTest(
                self._build_bot(entry_cfg=final_params, timeframe=int(self.args.timeframe)),
                bars=copy.deepcopy(self.bars),
                funding=self.funding,
                symbol=self.symbol,
            ).run()
            elapsed_s = float(time.time() - started)
            metrics = bt.metrics if isinstance(getattr(bt, "metrics", None), dict) else {}
            if not isinstance(metrics, dict):
                metrics = {}

            self.final_confirmation_report = {
                "enabled": True,
                "elapsed_s": round(elapsed_s, 3),
                "metrics": metrics,
                "plots_enabled": bool(getattr(self.args, "final_run_with_plots", False)),
                "plot_files": {},
                "plot_errors": {},
            }
            self._progress(
                "Final confirmation result | profit=%.2f dd=%.2f rel=%.2f trades=%d"
                % (
                    metric(metrics, "profit_pct"),
                    metric(metrics, "max_drawdown_pct"),
                    self._value_rel(metrics),
                    int(metric(metrics, "trades_closed")),
                )
            )

            if bool(getattr(self.args, "final_run_with_plots", False)):
                plot_specs = [
                    ("price", bt.plot_price_data),
                    ("equity", bt.plot_equity_stats),
                    ("normalized", bt.plot_normalized_stats),
                ]
                for plot_name, builder in plot_specs:
                    try:
                        fig = builder()
                        out_path = self.out_dir / f"{self.run_name}.final_{plot_name}.html"
                        fig.write_html(str(out_path), include_plotlyjs="cdn", full_html=True, auto_open=False)
                        self.final_confirmation_report["plot_files"][plot_name] = str(out_path)
                        self._progress("Final plot written (%s): %s" % (plot_name, str(out_path)))
                        if bool(getattr(self.args, "final_run_open_browser", True)):
                            try:
                                webbrowser.open_new_tab(out_path.resolve().as_uri())
                            except Exception as exc:
                                self.final_confirmation_report["plot_errors"][plot_name] = (
                                    "browser_open_failed: %s" % str(exc)
                                )
                    except Exception as exc:
                        self.final_confirmation_report["plot_errors"][plot_name] = str(exc)
                        self._progress("Final plot failed (%s): %s" % (plot_name, str(exc)))

            self._record_event("final_confirmation", self.final_confirmation_report)
        except Exception as exc:
            elapsed_s = float(time.time() - started)
            self.final_confirmation_report = {
                "enabled": True,
                "elapsed_s": round(elapsed_s, 3),
                "error": str(exc),
            }
            self._record_event("final_confirmation", self.final_confirmation_report)
            self._progress("Final confirmation run failed: %s" % str(exc))

    def _stage0_and_baseline(self, enforce_trade_density_gate: bool = True) -> bool:
        self.logger.info("=== stage1a: idea-only baseline ===")
        self._progress("=== ################################################################# ===")
        self._progress("=== stage1a: idea-only baseline ===")
        self._progress("=== ################################################################# ===")
        baseline_ok, baseline_reason = self._params_pass_constraints(self.current_params)
        if not baseline_ok:
            reason = "stage1a failed: baseline violates constraints (%s)." % str(baseline_reason)
            self._record_event("stage1a_failed", {"reason": reason, "params": self.current_params})
            self._summary(status="stopped", reason=reason)
            return False
        result = self._run_trial(
            params=copy.deepcopy(self.current_params),
            stage="stage1a_idea_baseline",
            label="idea_only_baseline",
            early_stop_max_trades=None,
        )
        trades = int(metric(result.metrics, "trades_closed"))
        if trades <= 0:
            reason = "stage1a failed: idea baseline produced no closed trades."
            self._record_event("stage1a_failed", {"reason": reason, "metrics": result.metrics})
            self._summary(status="stopped", reason=reason)
            return False
        if enforce_trade_density_gate and (trades < int(self.args.stage0_gate_min_trades)):
            reason = (
                "stage0 trade-density gate failed: trades=%d below required=%d. "
                "Idea condition does not meet minimum trade density."
            ) % (trades, int(self.args.stage0_gate_min_trades))
            self._record_event("stage0_failed", {"reason": reason, "metrics": result.metrics})
            self._summary(status="stopped", reason=reason)
            return False
        self._set_benchmark("stage1a_idea_baseline", self.current_params, result.metrics)
        return True

    def _gate_sweep(
        self,
        stage: str,
        values: List[Any],
        apply_fn,
        parallel: bool = False,
        permissive_value: Optional[Any] = None,
        disable_fn=None,
        objective: str = OBJECTIVE_PROFIT,
        stage_bucket: Optional[str] = None,
    ) -> bool:
        if self.benchmark is None:
            raise RuntimeError("Benchmark must be initialized before gate sweeps.")
        if len(values) == 0:
            self.logger.info("[%s] no values to sweep.", stage)
            self._progress("[%s] no values to sweep." % stage)
            return False
        objective_key = self._normalize_objective(objective, default=OBJECTIVE_PROFIT)
        if objective_key not in OBJECTIVE_KEYS:
            raise ValueError("Unknown objective: %s" % str(objective))
        objective_label = self._objective_label(objective_key)

        base_metrics = copy.deepcopy(self.benchmark.metrics)
        trial_rows: List[Tuple[Any, Dict[str, Any], TrialResult]] = []
        if parallel:
            candidates: List[Tuple[Any, Dict[str, Any], str]] = []
            for value in values:
                trial_params = copy.deepcopy(self.current_params)
                apply_fn(trial_params, value)
                ok, reason = self._params_pass_constraints(trial_params)
                if not ok:
                    self._record_event(
                        "constraint_skip",
                        {
                            "stage": stage,
                            "label": f"value={value}",
                            "reason": reason,
                            "params": trial_params,
                        },
                    )
                    continue
                candidates.append((value, trial_params, f"value={value}"))
            trial_rows = self._run_trials_parallel(stage=stage, candidates=candidates)
        else:
            accept_best_requested = False
            for value in values:
                trial_params = copy.deepcopy(self.current_params)
                apply_fn(trial_params, value)
                ok, reason = self._params_pass_constraints(trial_params)
                if not ok:
                    self._record_event(
                        "constraint_skip",
                        {
                            "stage": stage,
                            "label": f"value={value}",
                            "reason": reason,
                            "params": trial_params,
                        },
                    )
                    continue
                result = self._run_trial(
                    params=trial_params,
                    stage=stage,
                    label=f"value={value}",
                    early_stop_max_trades=None,
                )
                trial_rows.append((value, trial_params, result))
                if self._consume_control_command(stage) == "accept_best":
                    accept_best_requested = True
                    break
            if accept_best_requested:
                skipped_count = max(0, len(values) - len(trial_rows))
                self._record_event(
                    "sequential_sweep_fast_forward",
                    {
                        "stage": stage,
                        "candidate_count": len(values),
                        "completed_count": len(trial_rows),
                        "skipped_count": skipped_count,
                    },
                )
                self._progress(
                    "[%s] fast-forward accepted; skipped %d pending candidates."
                    % (stage, skipped_count)
                )
        eligible_rows: List[Tuple[Any, Dict[str, Any], TrialResult]] = []
        gate_bucket = str(stage_bucket or "").strip().lower()
        if gate_bucket == "":
            gate_bucket = "filter"
        for value, trial_params, result in trial_rows:
            if int(metric(result.metrics, "trades_closed")) <= 0:
                continue
            pass_gate, gate_reason = self._metrics_pass_stage_gates(metrics=result.metrics, stage_bucket=gate_bucket)
            if not pass_gate:
                self._record_event(
                    "metric_gate_skip",
                    {
                        "stage": stage,
                        "label": f"value={value}",
                        "reason": gate_reason,
                        "metrics": result.metrics,
                    },
                )
                continue
            eligible_rows.append((value, trial_params, result))

        best_row = self._select_best_trial_row_by_objective(trial_rows=eligible_rows, objective=objective_key)
        if best_row is None:
            self.logger.info("[%s] no eligible candidate passed trades/gates; benchmark unchanged.", stage)
            self._progress("[%s] no eligible candidate passed trades/gates; benchmark unchanged." % stage)
            return False
        best_value, best_params, best_result = best_row

        chosen_value = best_value
        chosen_params = best_params
        chosen_result = best_result
        chosen_label = str(best_value)

        is_permissive = False
        if permissive_value is not None and chosen_value is not None:
            try:
                is_permissive = abs(float(chosen_value) - float(permissive_value)) <= 1e-9
            except Exception:
                is_permissive = chosen_value == permissive_value

        if is_permissive and disable_fn is not None:
            off_params = copy.deepcopy(self.current_params)
            disable_fn(off_params)
            off_ok, off_reason = self._params_pass_constraints(off_params)
            if not off_ok:
                self._record_event(
                    "constraint_skip",
                    {
                        "stage": f"{stage}_off_probe",
                        "label": "value=off",
                        "reason": off_reason,
                        "params": off_params,
                    },
                )
                off_result = None
            else:
                off_result = self._run_trial(
                    params=off_params,
                    stage=f"{stage}_off_probe",
                    label="value=off",
                    early_stop_max_trades=None,
                )
            if off_result is not None:
                pass_gate, gate_reason = self._metrics_pass_stage_gates(metrics=off_result.metrics, stage_bucket=gate_bucket)
                if not pass_gate:
                    self._record_event(
                        "metric_gate_skip",
                        {
                            "stage": f"{stage}_off_probe",
                            "label": "value=off",
                            "reason": gate_reason,
                            "metrics": off_result.metrics,
                        },
                    )
                    off_result = None
            if off_result is not None:
                self._record_event(
                    "best_profit_off_probe",
                    {
                        "stage": stage,
                        "value": chosen_value,
                        "off_profit_pct": metric(off_result.metrics, "profit_pct"),
                        "off_max_drawdown_pct": metric(off_result.metrics, "max_drawdown_pct"),
                        "off_trades_closed": int(metric(off_result.metrics, "trades_closed")),
                    },
                )
                if (
                    int(metric(off_result.metrics, "trades_closed")) > 0
                    and self._is_not_worse_by_objective(
                        off_result.metrics,
                        chosen_result.metrics,
                        objective_key,
                    )
                ):
                    chosen_value = "off"
                    chosen_params = off_params
                    chosen_result = off_result
                    chosen_label = "off"
                    self._progress(
                        "[%s] permissive %s value=%s; OFF probe is not worse, selecting OFF."
                        % (stage, objective_label, str(best_value))
                    )

        if not self._beats_benchmark_by_objective(chosen_result.metrics, base_metrics, objective_key):
            self._record_event(
                "best_objective_no_change",
                {
                    "stage": stage,
                    "value": chosen_value,
                    "profit_pct": metric(chosen_result.metrics, "profit_pct"),
                    "max_drawdown_pct": metric(chosen_result.metrics, "max_drawdown_pct"),
                    "trades_closed": int(metric(chosen_result.metrics, "trades_closed")),
                    "rel": self._value_rel(chosen_result.metrics),
                    "objective": objective_key,
                    "reason": "candidate did not improve benchmark by stage objective gate",
                },
            )
            self.logger.info("[%s] candidate did not beat current benchmark (%s gate); unchanged.", stage, objective_label)
            self._progress("[%s] candidate did not beat current benchmark (%s gate); unchanged." % (stage, objective_label))
            return False

        if chosen_params == self.current_params:
            self._record_event(
                "best_objective_no_change",
                {
                    "stage": stage,
                    "value": chosen_value,
                    "profit_pct": metric(chosen_result.metrics, "profit_pct"),
                    "max_drawdown_pct": metric(chosen_result.metrics, "max_drawdown_pct"),
                    "trades_closed": int(metric(chosen_result.metrics, "trades_closed")),
                    "objective": objective_key,
                },
            )
            self.logger.info("[%s] %s candidate equals current benchmark; unchanged.", stage, objective_label)
            self._progress("[%s] %s candidate equals current benchmark; unchanged." % (stage, objective_label))
            return False

        self.logger.info(
            "[%s] selected %s value=%s | profit %.2f -> %.2f | dd %.2f -> %.2f | trades %d -> %d | rel %.2f -> %.2f",
            stage,
            objective_label,
            chosen_label,
            metric(base_metrics, "profit_pct"),
            metric(chosen_result.metrics, "profit_pct"),
            metric(base_metrics, "max_drawdown_pct"),
            metric(chosen_result.metrics, "max_drawdown_pct"),
            int(metric(base_metrics, "trades_closed")),
            int(metric(chosen_result.metrics, "trades_closed")),
            self._value_rel(base_metrics),
            self._value_rel(chosen_result.metrics),
        )
        self._progress(
            "[%s] selected %s value=%s | profit %.2f -> %.2f | dd %.2f -> %.2f | trades %d -> %d | rel %.2f -> %.2f"
            % (
                stage,
                objective_label,
                chosen_label,
                metric(base_metrics, "profit_pct"),
                metric(chosen_result.metrics, "profit_pct"),
                metric(base_metrics, "max_drawdown_pct"),
                metric(chosen_result.metrics, "max_drawdown_pct"),
                int(metric(base_metrics, "trades_closed")),
                int(metric(chosen_result.metrics, "trades_closed")),
                self._value_rel(base_metrics),
                self._value_rel(chosen_result.metrics),
            )
        )
        summary_suffix = "best_%s" % objective_key
        self._set_benchmark(f"{stage}_{chosen_label}_{summary_suffix}", chosen_params, chosen_result.metrics)
        return True

    def _reset_sl_option_state(self, params: Dict[str, Any], anchor_params: Dict[str, Any]):
        sl_use_entry_atr_key = self._entry_param_if_exists("sl_use_entry_atr")
        if sl_use_entry_atr_key is not None:
            params[sl_use_entry_atr_key] = False
        stop_ref_profile_key = self._stop_ref_profile_flag_key()
        if stop_ref_profile_key is not None:
            params[stop_ref_profile_key] = False
        sl_entry_atr_mult_key = self._entry_param_if_exists("sl_entry_atr_mult")
        if sl_entry_atr_mult_key is not None:
            params[sl_entry_atr_mult_key] = float(
                anchor_params.get(sl_entry_atr_mult_key, DEFAULT_SL_ATR_MULT)
            )
        if self._entry_param_exists("stop_atr_mult"):
            params[self._entry_param("stop_atr_mult")] = float(
                anchor_params.get(self._entry_param("stop_atr_mult"), 1.0)
            )
        self._set_all_sl_ref_sources_off(params)

    def _run_sl_option_sequence(
        self,
        sl_dimensions: List[str],
        stage_label_base: str = "stage3",
        stage_offset: int = 0,
        objective: str = OBJECTIVE_REL,
    ) -> bool:
        if self.benchmark is None:
            raise RuntimeError("Benchmark must be initialized before SL option sweeps.")
        if len(sl_dimensions) == 0:
            return False

        objective_key = self._normalize_objective(objective, default=OBJECTIVE_REL)
        objective_label = self._objective_label(objective_key)
        base_metrics = copy.deepcopy(self.benchmark.metrics)
        anchor_params = copy.deepcopy(self.current_params)
        best_overall_row: Optional[Tuple[str, Any, Dict[str, Any], TrialResult]] = None

        for offset, dim_id in enumerate(sl_dimensions):
            stage_ord = int(stage_offset) + offset
            suffix_code = ord("a") + stage_ord
            stage_suffix = chr(suffix_code) if suffix_code <= ord("z") else "r%d" % (stage_ord + 1)
            stage_tag = "%s%s" % (str(stage_label_base), stage_suffix)
            stage_name = "%s_sweep_%s" % (stage_tag, dim_id)
            values = self._dimension_sweep_values(dim_id=dim_id)
            self._progress("=== ################################################################# ===")
            self._progress("=== %s: sweep %s (%s, OR-mode) ===" % (stage_tag, dim_id, objective_label))
            self._progress("=== ################################################################# ===")

            candidates: List[Tuple[Any, Dict[str, Any], str]] = []
            for value in values:
                trial_params = copy.deepcopy(anchor_params)
                self._reset_sl_option_state(trial_params, anchor_params=anchor_params)
                self._apply_dimension_value(params=trial_params, dim_id=dim_id, value=value)
                ok, reason = self._params_pass_constraints(trial_params)
                if not ok:
                    self._record_event(
                        "constraint_skip",
                        {
                            "stage": stage_name,
                            "label": "value=%s" % str(value),
                            "reason": reason,
                            "params": trial_params,
                        },
                    )
                    continue
                candidates.append((value, trial_params, "value=%s" % str(value)))

            rows = self._run_trials_parallel(stage=stage_name, candidates=candidates)
            eligible_rows: List[Tuple[Any, Dict[str, Any], TrialResult]] = []
            for value, trial_params, result in rows:
                if int(metric(result.metrics, "trades_closed")) <= 0:
                    continue
                pass_gate, gate_reason = self._metrics_pass_stage_gates(metrics=result.metrics, stage_bucket="sl")
                if not pass_gate:
                    self._record_event(
                        "metric_gate_skip",
                        {
                            "stage": stage_name,
                            "label": "value=%s" % str(value),
                            "reason": gate_reason,
                            "metrics": result.metrics,
                        },
                    )
                    continue
                eligible_rows.append((value, trial_params, result))

            stage_best = self._select_best_trial_row_by_objective(trial_rows=eligible_rows, objective=objective_key)
            if stage_best is None:
                self._progress("[%s] no candidate produced eligible closed trades." % stage_name)
                continue
            stage_best_value, stage_best_params, stage_best_result = stage_best
            stage_best_metrics = stage_best_result.metrics

            self._progress(
                "[%s] stage-best value=%s | profit=%.2f dd=%.2f rel=%.2f trades=%d"
                % (
                    stage_name,
                    str(stage_best_value),
                    metric(stage_best_metrics, "profit_pct"),
                    metric(stage_best_metrics, "max_drawdown_pct"),
                    self._value_rel(stage_best_metrics),
                    int(metric(stage_best_metrics, "trades_closed")),
                )
            )

            if best_overall_row is None or self._is_better_by_objective(
                stage_best_metrics,
                best_overall_row[3].metrics,
                objective_key,
            ):
                best_overall_row = (
                    dim_id,
                    stage_best_value,
                    stage_best_params,
                    stage_best_result,
                )

        if best_overall_row is None:
            self._progress("SL OR-sequence produced no closed-trade candidate; benchmark unchanged.")
            return False
        best_overall_dim, best_overall_value, best_overall_params, best_overall_result = best_overall_row
        best_overall_metrics = best_overall_result.metrics

        if not self._beats_benchmark_by_objective(best_overall_metrics, base_metrics, objective_key):
            self._progress(
                "SL OR-sequence best %s candidate did not beat current benchmark; unchanged."
                % objective_label
            )
            return False

        if best_overall_params == self.current_params:
            self._progress("SL OR-sequence best candidate equals current benchmark; unchanged.")
            return False

        self._progress(
            "SL OR-sequence selected %s option: %s=%s | profit=%.2f dd=%.2f rel=%.2f trades=%d"
            % (
                objective_label,
                str(best_overall_dim),
                str(best_overall_value),
                metric(best_overall_metrics, "profit_pct"),
                metric(best_overall_metrics, "max_drawdown_pct"),
                self._value_rel(best_overall_metrics),
                int(metric(best_overall_metrics, "trades_closed")),
            )
        )
        self._set_benchmark(
            "%s_selected_%s_%s_best_%s"
            % (
                str(stage_label_base),
                str(best_overall_dim),
                str(best_overall_value),
                objective_key,
            ),
            best_overall_params,
            best_overall_metrics,
        )
        return True

    def run(self):
        skip_stage0_gate = bool(getattr(self.args, "skip_stage0_gate", False))
        skip_stage1b_confirmation = True
        disable_stage2_rechecks = bool(getattr(self.args, "disable_stage2_rechecks", False))
        disable_stage3_rechecks = bool(getattr(self.args, "disable_stage3_rechecks", False))
        stage1b_dims: List[str] = []
        filter_dimensions = list(self.stage_sweep_dims.get("filter", []))
        sl_dimensions = list(self.stage_sweep_dims.get("sl", []))
        active_dims = list(dict.fromkeys(stage1b_dims + filter_dimensions + sl_dimensions))
        self.active_sweep_order = active_dims
        self._initialize_control_file()
        self._record_event(
            "run_start",
            {
                "entry_id": self.entry_id,
                "pair": self.args.pair,
                "exchange": self.exchange,
                "timeframe": int(self.args.timeframe),
                "days": int(self.args.days),
                "open_interest_loaded": bool(isinstance(self.open_interest, dict) and len(self.open_interest) > 0),
                "open_interest_points": int(len(self.open_interest) if isinstance(self.open_interest, dict) else 0),
                "stage0_gate_min_trades": int(self.args.stage0_gate_min_trades),
                "stage_model": "stage0_preparation -> stage1a_idea -> stage2_filters -> stage3_sl",
                "entry_has_idea_class": bool(self.entry_has_idea),
                "entry_has_confirmation_class": bool(self.entry_has_confirmation),
                "preparation_phase_enabled": not bool(getattr(self.args, "disable_preparation_phase", False)),
                "preparation_with_plots": bool(getattr(self.args, "preparation_with_plots", False)),
                "preparation_plot_open_browser": bool(getattr(self.args, "preparation_plot_open_browser", False)),
                "skip_stage0_gate": bool(skip_stage0_gate),
                "skip_stage1b_confirmation": True,
                "disable_stage2_rechecks": bool(disable_stage2_rechecks),
                "disable_stage3_rechecks": bool(disable_stage3_rechecks),
                "stage1_sweep_requested": "",
                "stage2_sweep_requested": self.stage_sweep_requested.get("filter", ""),
                "stage3_sweep_requested": self.stage_sweep_requested.get("sl", ""),
                "stage1_sweep": list(stage1b_dims),
                "stage2_sweep": list(filter_dimensions),
                "stage3_sweep": list(sl_dimensions),
                "active_sweep_order": active_dims,
                "sweep_range_overrides": {
                    dim: {
                        "min": spec.get("min"),
                        "max": spec.get("max"),
                        "step": spec.get("step"),
                        "type": spec.get("type"),
                        "raw_dim": spec.get("raw_dim"),
                        "source": spec.get("source"),
                    }
                    for dim, spec in self.sweep_range_overrides.items()
                },
                "fixed_dimensions": list(self.fixed_dimensions),
                "seed_param_overrides": [
                    {"key": str(key), "value": value} for key, value in self.seed_param_overrides
                ],
                "fixed_param_overrides": [
                    {"key": str(key), "value": value} for key, value in self.fixed_param_overrides
                ],
                "stage1b_objective": self._stage_objective("filter"),
                "stage2_objective": self._stage_objective("filter"),
                "stage3_objective": self._stage_objective("sl"),
                "stage1_gates": [],
                "stage2_gates": [g.raw for g in self.metric_gates.get("filter", [])],
                "stage3_gates": [g.raw for g in self.metric_gates.get("sl", [])],
                "constraints": [c.raw for c in self.parameter_constraints],
                "objective_profit_floor_ratio": self._objective_profit_floor_ratio(),
                "objective_dd_cap": self._objective_dd_cap(),
                "objective_dd_penalty": self._objective_dd_penalty(),
                "dry_run_config": bool(self.dry_run_config),
                "eval_workers": int(getattr(self.args, "eval_workers", 0)),
                "max_eval_workers": int(getattr(self.args, "max_eval_workers", 0)),
                "ram_aware_workers": bool(getattr(self.args, "ram_aware_workers", True)),
                "ram_reserve_gb": float(getattr(self.args, "ram_reserve_gb", 8.0)),
                "worker_ram_gb": float(getattr(self.args, "worker_ram_gb", 2.0)),
                "control_file": str(self.control_path),
                "control_command": "accept_best",
                "final_confirmation_run": bool(getattr(self.args, "final_confirmation_run", True)),
                "final_run_with_plots": bool(getattr(self.args, "final_run_with_plots", False)),
                "final_run_open_browser": bool(getattr(self.args, "final_run_open_browser", True)),
            },
        )
        self.logger.info(
            "Run start | entry=%s pair=%s exchange=%s timeframe=%d days=%d",
            self.entry_id,
            self.args.pair,
            self.exchange,
            int(self.args.timeframe),
            int(self.args.days),
        )
        self._progress(
            "Run start | entry=%s pair=%s exchange=%s timeframe=%d days=%d"
            % (
                self.entry_id,
                self.args.pair,
                self.exchange,
                int(self.args.timeframe),
                int(self.args.days),
            )
        )
        self._progress(
            "Control file: %s | write 'accept_best' to skip remaining candidates in the current sweep."
            % str(self.control_path)
        )
        self._progress("=== ################################################################# ===")
        self._progress("=== stage0: preparation ===")
        self._progress("=== ################################################################# ===")
        self._run_preparation_phase()
        self._validate_sweep_configuration(
            stage1b_dims=stage1b_dims,
            filter_dims=filter_dimensions,
            sl_dims=sl_dimensions,
            skip_stage1b_confirmation=skip_stage1b_confirmation,
        )
        if self.dry_run_config:
            self._emit_dry_run_report(
                stage1b_dims=stage1b_dims,
                filter_dims=filter_dimensions,
                sl_dims=sl_dimensions,
                skip_stage1b_confirmation=skip_stage1b_confirmation,
            )
            return

        def run_dimension_sweep(stage_name: str, dim_id: str, values: Optional[List[Any]] = None) -> bool:
            objective = self._objective_for_dimension(dim_id)
            stage_bucket = self._dimension_stage_bucket(dim_id)
            permissive_value = self._dimension_permissive_value(dim_id)
            disable_fn = None
            if permissive_value is not None:
                disable_fn = lambda params, _dim=dim_id: self._apply_dimension_off(params=params, dim_id=_dim)
            sweep_values = list(values) if values is not None else self._dimension_sweep_values(dim_id=dim_id)
            return self._gate_sweep(
                stage=stage_name,
                values=sweep_values,
                apply_fn=lambda params, v, _dim=dim_id: self._apply_dimension_value(
                    params=params, dim_id=_dim, value=v
                ),
                parallel=True,
                permissive_value=permissive_value,
                disable_fn=disable_fn,
                objective=objective,
                stage_bucket=stage_bucket,
            )

        if skip_stage0_gate:
            self._progress(
                "Stage0 trade-density gate disabled by --skip-stage0-gate; stage1a baseline still executed."
            )
        if not self._stage0_and_baseline(enforce_trade_density_gate=(not skip_stage0_gate)):
            return

        swept_non_sl_dimensions: List[str] = []

        self._progress("Stage1 confirmation sweep disabled: confirmation parameters are merged into stage2 filters.")

        if len(filter_dimensions) > 0:
            self._progress("=== ################################################################# ===")
            self._progress("=== stage2: filter conditions ===")
            self._progress("=== ################################################################# ===")
            for dim_idx, dim_id in enumerate(filter_dimensions):
                suffix_code = ord("a") + dim_idx
                stage_suffix = chr(suffix_code) if suffix_code <= ord("z") else "r%d" % (dim_idx + 1)
                stage_tag = "stage2%s" % stage_suffix
                objective_label = self._objective_label(self._objective_for_dimension(dim_id))
                self._progress("=== ################################################################# ===")
                self._progress("=== %s: sweep %s (%s) ===" % (stage_tag, dim_id, objective_label))
                self._progress("=== ################################################################# ===")

                stage_name = "%s_sweep_%s" % (stage_tag, dim_id)
                stage_changed = run_dimension_sweep(stage_name=stage_name, dim_id=dim_id)
                if dim_id not in swept_non_sl_dimensions:
                    swept_non_sl_dimensions.append(dim_id)

                if not stage_changed:
                    self._progress(
                        "%s (%s) had no %s improvement; skipping re-checks."
                        % (stage_tag, dim_id, objective_label)
                    )
                    continue

                if disable_stage2_rechecks:
                    self._progress("%s re-checks disabled by --disable-stage2-rechecks." % stage_tag)
                else:
                    recheck_dims = [d for d in reversed(swept_non_sl_dimensions[:-1]) if d not in self.fixed_dimensions]
                    for re_idx, prev_dim in enumerate(recheck_dims, start=1):
                        current_value = self._dimension_current_value(prev_dim)
                        relax_values = self._dimension_relax_values(dim_id=prev_dim, current=current_value)
                        current_label = self._format_dimension_value(current_value)
                        recheck_objective_label = self._objective_label(self._objective_for_dimension(prev_dim))
                        recheck_tag = "%sr%d" % (stage_tag, re_idx)
                        self._progress(
                            "=== %s: re-check %s around current=%s (%s) ==="
                            % (recheck_tag, prev_dim, current_label, recheck_objective_label)
                        )
                        run_dimension_sweep(
                            stage_name="%s_recheck_%s" % (recheck_tag, prev_dim),
                            dim_id=prev_dim,
                            values=relax_values,
                        )
        else:
            self._progress("Stage2 filter sweep has no dimensions selected; using current filter settings.")

        if len(sl_dimensions) > 0:
            stage3_objective = self._stage_objective("sl")
            self._progress("=== ################################################################# ===")
            self._progress("=== stage3: sl setting (%s) ===" % self._objective_label(stage3_objective))
            self._progress("=== ################################################################# ===")
            sl_changed = self._run_sl_option_sequence(
                sl_dimensions=sl_dimensions,
                stage_label_base="stage3",
                stage_offset=0,
                objective=stage3_objective,
            )
            if sl_changed and len(swept_non_sl_dimensions) > 0:
                if disable_stage3_rechecks:
                    self._progress("stage3 re-checks disabled by --disable-stage3-rechecks.")
                else:
                    self._progress(
                        "=== stage3r+: re-check previously selected confirmation/filter dimensions ==="
                    )
                    for re_idx, prev_dim in enumerate(reversed(swept_non_sl_dimensions), start=1):
                        if prev_dim in self.fixed_dimensions:
                            continue
                        current_value = self._dimension_current_value(prev_dim)
                        relax_values = self._dimension_relax_values(dim_id=prev_dim, current=current_value)
                        current_label = self._format_dimension_value(current_value)
                        recheck_objective_label = self._objective_label(self._objective_for_dimension(prev_dim))
                        recheck_tag = "stage3r%d" % re_idx
                        self._progress(
                            "=== %s: re-check %s around current=%s (%s) ==="
                            % (recheck_tag, prev_dim, current_label, recheck_objective_label)
                        )
                        run_dimension_sweep(
                            stage_name="%s_recheck_%s" % (recheck_tag, prev_dim),
                            dim_id=prev_dim,
                            values=relax_values,
                        )
        else:
            self._progress(
                "Stage3 SL sweep has no dimensions selected; keeping default/current SL setting."
            )

        self._run_final_confirmation()
        self._summary(
            status="completed",
            reason="configured sweep sequence finished.",
        )


_PARALLEL_WORKER_CACHE: Dict[Tuple[str, str, int, int], Dict[str, Any]] = {}


def _parallel_eval_trial(payload: Dict[str, Any]) -> Dict[str, Any]:
    started = time.time()
    try:
        # Keep worker processes silent in console.
        root_worker_logger = logging.getLogger("kuegi_bot")
        root_worker_logger.setLevel(logging.CRITICAL)
        root_worker_logger.propagate = False
        for h in list(root_worker_logger.handlers):
            root_worker_logger.removeHandler(h)
        if len(root_worker_logger.handlers) == 0:
            root_worker_logger.addHandler(logging.NullHandler())

        pair = str(payload["pair"])
        exchange = normalize_exchange(str(payload["exchange"]), pair)
        timeframe = int(payload["timeframe"])
        days = int(payload["days"])
        entry_id = str(payload.get("entry_id", DEFAULT_ENTRY_ID))
        params = dict(payload["params"])

        key = (exchange, pair, timeframe, days)
        cached = _PARALLEL_WORKER_CACHE.get(key)
        if cached is None:
            cached = {
                "symbol": get_symbol(pair),
                "funding": load_funding(exchange, pair),
                "open_interest": load_open_interest(exchange, pair),
                "bars": load_bars(
                    days_in_history=days,
                    wanted_tf=timeframe,
                    start_offset_minutes=0,
                    exchange=exchange,
                    symbol=pair,
                ),
            }
            _PARALLEL_WORKER_CACHE[key] = cached

        logger = logging.getLogger("entry_staged_worker")
        logger.setLevel(logging.CRITICAL)
        logger.propagate = False
        if len(logger.handlers) == 0:
            logger.addHandler(logging.NullHandler())

        bot = MultiStrategyBot(logger=logger, directionFilter=0)
        bot.add_strategy(
            EntryStagedOptimizer._build_strategy(
                entry_cfg=params,
                timeframe=timeframe,
                entry_id=entry_id,
                open_interest_by_tstamp=cached.get("open_interest"),
                funding_by_tstamp=cached.get("funding"),
            )
        )
        bt = BackTest(
            bot=bot,
            # Use fresh bar objects per trial to avoid cross-trial state bleed via bar.bot_data.
            bars=copy.deepcopy(cached["bars"]),
            funding=cached["funding"],
            symbol=cached["symbol"],
            market_slipage_percent=0.15,
        )
        bt.run()

        metrics = bt.metrics if isinstance(getattr(bt, "metrics", None), dict) else {}
        if not isinstance(metrics, dict):
            metrics = {}

        return {
            "metrics": metrics,
            "elapsed_s": float(time.time() - started),
            "early_stopped": bool(getattr(bt, "early_stopped", False)),
            "early_stop_reason": str(getattr(bt, "early_stop_reason", "")) if getattr(bt, "early_stopped", False) else None,
        }
    except Exception as exc:
        return {
            "error": str(exc),
            "elapsed_s": float(time.time() - started),
        }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic staged optimizer for StrategyOne entry modules.")
    parser.add_argument(
        "--entry-id",
        default=DEFAULT_ENTRY_ID,
        choices=sorted(list(ENTRY_PARAM_CATALOG.keys())),
        help="Entry module to optimize (e.g. entry_23).",
    )
    parser.add_argument("--pair", default="BTCUSD")
    parser.add_argument("--exchange", default="bybit")
    parser.add_argument("--timeframe", type=int, default=240)
    parser.add_argument("--days", type=int, default=3000 * 6, help="History window to evaluate on.")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "results" / "entry_staged"))
    parser.add_argument("--log-level", type=int, default=20, help="Python logging level (20=INFO).")

    parser.add_argument(
        "--stage0-gate-min-trades",
        dest="stage0_gate_min_trades",
        type=int,
        default=50,
        help="Minimum closed trades required by the stage0 trade-density gate.",
    )
    parser.add_argument(
        "--skip-stage0-gate",
        dest="skip_stage0_gate",
        action="store_true",
        help="Skip stage0 trade-density gate; stage1a idea baseline still runs.",
    )
    parser.add_argument(
        "--skip-stage1b-confirmation",
        dest="skip_stage1b_confirmation",
        action="store_true",
        help="Deprecated no-op: confirmation sweep stage is removed (merged into stage2 filters).",
    )
    parser.add_argument(
        "--disable-stage2-rechecks",
        dest="disable_stage2_rechecks",
        action="store_true",
        help="Disable stage2 post-improvement re-check sweeps over previously swept non-SL dimensions.",
    )
    parser.add_argument(
        "--disable-stage3-rechecks",
        dest="disable_stage3_rechecks",
        action="store_true",
        help="Disable stage3 post-improvement re-check sweeps over previously swept confirmation/filter dimensions.",
    )
    parser.add_argument(
        "--stage1b-objective",
        choices=list(OBJECTIVE_KEYS),
        default=OBJECTIVE_PROFIT,
        help="Deprecated alias for stage2 objective (confirmation is merged into filters).",
    )
    parser.add_argument(
        "--stage2-objective",
        choices=list(OBJECTIVE_KEYS),
        default=OBJECTIVE_PROFIT,
        help="Gate objective for stage2 filter sweeps and related re-checks.",
    )
    parser.add_argument(
        "--stage3-objective",
        choices=list(OBJECTIVE_KEYS),
        default=OBJECTIVE_REL,
        help="Gate objective for stage3 SL option sweeps.",
    )
    parser.add_argument(
        "--stage1-gate",
        action="append",
        default=[],
        help="Hard metric gate(s) merged into stage2 filters (legacy alias).",
    )
    parser.add_argument(
        "--stage2-gate",
        action="append",
        default=[],
        help="Hard metric gate(s) for stage2, e.g. --stage2-gate dd<=20.",
    )
    parser.add_argument(
        "--stage3-gate",
        action="append",
        default=[],
        help="Hard metric gate(s) for stage3, e.g. --stage3-gate rel>=1.2.",
    )
    parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help=(
            "Parameter constraints evaluated before trial execution, e.g. "
            "--constraint entry_23.filter.confirm_rsi_d_min<=entry_23.filter.confirm_rsi_d_max."
        ),
    )
    parser.add_argument(
        "--objective-profit-floor-ratio",
        type=float,
        default=0.85,
        help=(
            "Used by objective 'profit_floor_dd': keep candidates with profit >= ratio * best_profit, "
            "then prefer lowest absolute drawdown."
        ),
    )
    parser.add_argument(
        "--objective-dd-cap",
        type=float,
        default=20.0,
        help="Used by objective 'profit_dd_softcap': drawdown cap in percent before penalty applies.",
    )
    parser.add_argument(
        "--objective-dd-penalty",
        type=float,
        default=0.25,
        help="Used by objective 'profit_dd_softcap': penalty multiplier on (max(0, |dd|-dd_cap)^2).",
    )
    parser.add_argument(
        "--disable-preparation-phase",
        action="store_true",
        help="Disable indicator distribution scan that auto-adjusts sweep ranges before stage0.",
    )
    parser.add_argument(
        "--preparation-with-plots",
        action="store_true",
        help="Write preparation-phase indicator distribution HTML plots to the run output directory.",
    )
    parser.add_argument(
        "--preparation-plot-open-browser",
        action="store_true",
        help="When --preparation-with-plots is enabled, auto-open generated preparation plots in the browser.",
    )
    parser.add_argument(
        "--dry-run-config",
        action="store_true",
        help="Resolve stages/ranges/objectives and exit without running backtests.",
    )
    parser.add_argument(
        "--stage1-sweep",
        default="",
        help=(
            "Deprecated: stage1 confirmation sweep removed (confirmation merged into filters). "
            "Use --stage2-sweep."
        ),
    )
    parser.add_argument(
        "--stage2-sweep",
        default="",
        help=(
            "Comma-separated ordered stage2 filter dimensions to sweep. "
            "Each token can be dim or dim=min:max:step."
        ),
    )
    parser.add_argument(
        "--stage3-sweep",
        default="",
        help=(
            "Comma-separated ordered stage3 SL dimensions to sweep. "
            "Each token can be dim or dim=min:max:step."
        ),
    )
    parser.add_argument(
        "--sweep-range",
        action="append",
        default=[],
        help=(
            "Override numeric sweep range for a dimension as dim=min:max:step. "
            "Supports numeric structured entry parameter ids. "
            "If both --sweep-range and inline --stageX-sweep range are set for a dim, --sweep-range wins."
        ),
    )
    parser.add_argument(
        "--fixed-param",
        action="append",
        default=[],
        help=(
            "Pin a parameter and exclude its sweep dimension, e.g. "
            "--fixed-param entry_23.filter.confirm_rsi_d_max=70, "
            "or --fixed-param sl_ref_profile=min_oc_3."
        ),
    )
    parser.add_argument(
        "--seed-param",
        action="append",
        default=[],
        help=(
            "Set an initial parameter value without excluding it from sweeps, e.g. "
            "--seed-param entry_23.filter.confirm_rsi_d_max=75, --seed-param entry_23.filter.filter_max_bar_range_atr=1.5. "
            "If a value dimension has a companion *_enabled flag, setting the value auto-enables it."
        ),
    )
    parser.add_argument(
        "--eval-workers",
        type=int,
        default=0,
        help="Parallel workers for sweep stages. <=0 uses auto (cpu-1), then capped by RAM/batch.",
    )
    parser.add_argument(
        "--max-eval-workers",
        type=int,
        default=5,
        help="Hard upper cap for sweep workers. <=0 disables hard cap.",
    )
    parser.add_argument(
        "--disable-ram-aware-workers",
        dest="ram_aware_workers",
        action="store_false",
        help="Disable RAM-aware worker cap for parallel sweeps.",
    )
    parser.add_argument(
        "--ram-reserve-gb",
        type=float,
        default=8.0,
        help="RAM kept free before assigning parallel workers.",
    )
    parser.add_argument(
        "--worker-ram-gb",
        type=float,
        default=2.0,
        help="Estimated RAM per worker process used for RAM-aware cap.",
    )
    parser.add_argument(
        "--control-file",
        default="",
        help="Path for runtime control commands. Write 'accept_best' into this file to stop scheduling remaining candidates in current sweep.",
    )
    parser.add_argument(
        "--disable-final-confirmation-run",
        dest="final_confirmation_run",
        action="store_false",
        help="Skip final confirmation backtest with selected best parameters.",
    )
    parser.add_argument(
        "--final-run-with-plots",
        action="store_true",
        help="After final confirmation run, write price/equity/normalized HTML plots for final params.",
    )
    parser.add_argument(
        "--final-run-no-browser",
        dest="final_run_open_browser",
        action="store_false",
        help="When --final-run-with-plots is enabled, do not auto-open the generated HTML plots.",
    )
    parser.set_defaults(ram_aware_workers=True)
    parser.set_defaults(final_confirmation_run=True)
    parser.set_defaults(final_run_open_browser=True)
    parser.add_argument("--no-console-progress", action="store_true", help="Disable explicit stdout progress lines.")
    return parser


def get_optimizer_gui_schema() -> Dict[str, Any]:
    parser = build_arg_parser()

    def classify_action(action: argparse.Action) -> Tuple[str, str]:
        # kind, action_mode
        if isinstance(action, argparse._StoreTrueAction):
            return "bool", "store_true"
        if isinstance(action, argparse._StoreFalseAction):
            return "bool", "store_false"
        if isinstance(action, argparse._AppendAction):
            return "list", "append"
        if action.type in (int,):
            return "int", "store"
        if action.type in (float,):
            return "float", "store"
        return "str", "store"

    order = [
        "entry_id",
        "pair",
        "exchange",
        "timeframe",
        "days",
        "run_name",
        "out_dir",
        "log_level",
        "stage0_gate_min_trades",
        "skip_stage0_gate",
        "skip_stage1b_confirmation",
        "disable_stage2_rechecks",
        "disable_stage3_rechecks",
        "stage1b_objective",
        "stage2_objective",
        "stage3_objective",
        "stage1_gate",
        "stage2_gate",
        "stage3_gate",
        "constraint",
        "objective_profit_floor_ratio",
        "objective_dd_cap",
        "objective_dd_penalty",
        "disable_preparation_phase",
        "preparation_with_plots",
        "preparation_plot_open_browser",
        "dry_run_config",
        "stage1_sweep",
        "stage2_sweep",
        "stage3_sweep",
        "sweep_range",
        "fixed_param",
        "seed_param",
        "eval_workers",
        "max_eval_workers",
        "ram_aware_workers",
        "ram_reserve_gb",
        "worker_ram_gb",
        "control_file",
        "final_confirmation_run",
        "final_run_with_plots",
        "final_run_open_browser",
        "no_console_progress",
    ]

    fields: List[Dict[str, Any]] = []
    for action in parser._actions:
        if action.dest == "help":
            continue
        if not action.option_strings:
            continue
        kind, mode = classify_action(action)
        flag = action.option_strings[0]
        field: Dict[str, Any] = {
            "dest": action.dest,
            "flag": flag,
            "kind": kind,
            "mode": mode,
            "default": action.default,
            "help": action.help or "",
        }
        if action.choices is not None:
            field["choices"] = list(action.choices)
        fields.append(field)

    pos = {dest: idx for idx, dest in enumerate(order)}
    fields.sort(key=lambda f: pos.get(str(f.get("dest")), 10_000))

    return {
        "description": parser.description or "",
        "fields": fields,
        "sweep_dimensions": list(VIRTUAL_DIMENSION_IDS),
        "entry_ids": sorted(list(ENTRY_PARAM_CATALOG.keys())),
        "sl_ref_profile_values": sl_ref_profile_values(),
    }


def parse_args():
    parser = build_arg_parser()
    return parser.parse_args()


def main():
    args = parse_args()
    optimizer = EntryStagedOptimizer(args)
    optimizer.run()

if __name__ == "__main__":
    main()
