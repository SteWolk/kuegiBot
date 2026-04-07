import datetime as dt
import importlib.util
import json
import math
import subprocess
import sys
import threading
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OPTIMIZER_PATH = PROJECT_ROOT / "backtest" / "optimizer.py"
RESULTS_ROOT = PROJECT_ROOT / "backtest" / "results" / "entry_staged"
PRESETS_PATH = RESULTS_ROOT / "gui_presets.json"


def _load_optimizer_schema() -> Dict[str, Any]:
    spec = importlib.util.spec_from_file_location("entry_staged_optimizer_gui", str(OPTIMIZER_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load optimizer module from %s" % str(OPTIMIZER_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "get_optimizer_gui_schema"):
        raise RuntimeError("Optimizer module has no get_optimizer_gui_schema()")
    return dict(mod.get_optimizer_gui_schema())


def _utc_now() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _tail_lines(path: Path, limit: int = 250) -> List[str]:
    if not path.exists():
        return []
    out: deque = deque(maxlen=max(1, int(limit)))
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            out.append(line.rstrip("\n"))
    return list(out)


class RunRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._run: Optional[Dict[str, Any]] = None

    def active(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._run is None:
                return None
            self._refresh_locked()
            return dict(self._safe_public(self._run))

    def _safe_public(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "run_name": row.get("run_name"),
            "status": row.get("status"),
            "started_at": row.get("started_at"),
            "ended_at": row.get("ended_at"),
            "pid": row.get("pid"),
            "log_path": row.get("log_path"),
            "command_preview": row.get("command_preview"),
            "returncode": row.get("returncode"),
        }

    def _refresh_locked(self):
        if self._run is None:
            return
        proc = self._run.get("proc")
        if proc is None:
            return
        rc = proc.poll()
        if rc is None:
            self._run["status"] = "running"
            self._run["returncode"] = None
            return
        self._run["status"] = "completed" if int(rc) == 0 else "failed"
        self._run["returncode"] = int(rc)
        if self._run.get("ended_at") is None:
            self._run["ended_at"] = _utc_now()
        log_fh = self._run.get("log_fh")
        if log_fh is not None:
            try:
                log_fh.flush()
                log_fh.close()
            except Exception:
                pass
            self._run["log_fh"] = None

    def start(self, row: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            if self._run is not None and self._run.get("status") == "running":
                raise RuntimeError("A run is already active.")
            self._run = row
            return dict(self._safe_public(self._run))

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if self._run is None:
                raise RuntimeError("No run is registered.")
            self._refresh_locked()
            if self._run.get("status") != "running":
                return dict(self._safe_public(self._run))
            proc = self._run.get("proc")
            if proc is not None:
                proc.terminate()
            self._run["status"] = "stopping"
            return dict(self._safe_public(self._run))


def _load_presets() -> Dict[str, Any]:
    if not PRESETS_PATH.exists():
        return {}
    try:
        return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_presets(presets: Dict[str, Any]):
    PRESETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_PATH.write_text(json.dumps(presets, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_one(kind: str, value: Any):
    if kind == "bool":
        return bool(value)
    if kind == "int":
        if value in ("", None):
            return None
        return int(value)
    if kind == "float":
        if value in ("", None):
            return None
        return float(value)
    if kind == "list":
        if value is None:
            return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip() != ""]
        text = str(value)
        parts = [p.strip() for p in text.replace("\r", "").split("\n")]
        return [p for p in parts if p != ""]
    if value is None:
        return ""
    return str(value)


def _normalize_settings(schema: Dict[str, Any], raw: Dict[str, Any]) -> Dict[str, Any]:
    fields = list(schema.get("fields", []))
    out: Dict[str, Any] = {}
    for field in fields:
        dest = str(field["dest"])
        kind = str(field["kind"])
        default = field.get("default")
        if dest in raw:
            out[dest] = _normalize_one(kind, raw[dest])
        else:
            out[dest] = default
    return out


def _build_command(schema: Dict[str, Any], settings: Dict[str, Any]) -> Tuple[List[str], str]:
    fields = list(schema.get("fields", []))
    args: List[str] = []
    force = {"pair", "exchange", "timeframe", "days"}
    for field in fields:
        dest = str(field["dest"])
        flag = str(field["flag"])
        mode = str(field["mode"])
        kind = str(field["kind"])
        default = field.get("default")
        value = settings.get(dest, default)

        if mode == "store_true":
            if bool(value):
                args.append(flag)
            continue
        if mode == "store_false":
            if not bool(value):
                args.append(flag)
            continue
        if mode == "append":
            vals = value if isinstance(value, list) else []
            for item in vals:
                txt = str(item).strip()
                if txt == "":
                    continue
                args.extend([flag, txt])
            continue

        if value is None:
            continue
        if kind == "str":
            txt = str(value).strip()
            if txt == "":
                continue
            if txt == str(default) and dest not in force:
                continue
            args.extend([flag, txt])
            continue
        if value == default and dest not in force:
            continue
        args.extend([flag, str(value)])

    script_rel = "backtest/optimizer.py"
    preview = ("py -3 %s %s" % (script_rel, " ".join(args))).strip()
    cmd = [sys.executable, str(OPTIMIZER_PATH)] + args
    return cmd, preview


def _default_settings(schema: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for field in schema.get("fields", []):
        out[str(field["dest"])] = field.get("default")
    return out


def _format_seed_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "null"
        txt = "%0.12g" % float(value)
        if "e" not in txt and "E" not in txt and "." in txt:
            txt = txt.rstrip("0").rstrip(".")
        return txt
    return str(value)


def _resolve_final_json_path(raw_path: str) -> Path:
    token = str(raw_path or "").strip().strip('"').strip("'")
    if token == "":
        raise ValueError("path is required")
    p = Path(token)
    candidates: List[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(PROJECT_ROOT / p)
        candidates.append(RESULTS_ROOT / p)
    for cand in candidates:
        if cand.exists() and cand.is_file():
            return cand
    raise FileNotFoundError("final json file not found: %s" % token)


def _recent_final_files(limit: int = 30) -> List[str]:
    if not RESULTS_ROOT.exists():
        return []
    rows: List[Tuple[float, Path]] = []
    for path in RESULTS_ROOT.glob("*.final.json"):
        try:
            mtime = float(path.stat().st_mtime)
        except Exception:
            continue
        rows.append((mtime, path))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [str(row[1]) for row in rows[: max(1, int(limit))]]


def _build_settings_from_final(schema: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    benchmark = payload.get("benchmark", {})
    params = {}
    if isinstance(benchmark, dict):
        p0 = benchmark.get("params", {})
        if isinstance(p0, dict):
            params = dict(p0)
    if len(params) == 0:
        p1 = payload.get("best_params", {})
        if isinstance(p1, dict):
            params = dict(p1)
    if len(params) == 0:
        raise ValueError("final json has no benchmark.params / best_params")

    out = _default_settings(schema)
    if "pair" in payload:
        out["pair"] = str(payload.get("pair"))
    if "exchange" in payload:
        out["exchange"] = str(payload.get("exchange"))
    if "timeframe" in payload:
        out["timeframe"] = int(payload.get("timeframe"))
    if "days" in payload:
        out["days"] = int(payload.get("days"))

    seed_lines: List[str] = []
    for key in sorted(params.keys()):
        seed_lines.append("%s=%s" % (str(key), _format_seed_value(params.get(key))))
    out["seed_param"] = seed_lines
    return _normalize_settings(schema, out)


class OptimizerGuiHandler(BaseHTTPRequestHandler):
    schema_cache: Dict[str, Any] = _load_optimizer_schema()
    runs = RunRegistry()

    def _send_json(self, payload: Any, status: int = 200):
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _send_text(self, text: str, status: int = 200, content_type: str = "text/plain; charset=utf-8"):
        blob = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _read_json_body(self) -> Dict[str, Any]:
        raw_len = self.headers.get("Content-Length", "0").strip()
        try:
            length = int(raw_len)
        except Exception:
            length = 0
        body = self.rfile.read(max(0, length))
        if len(body) == 0:
            return {}
        try:
            return dict(json.loads(body.decode("utf-8")))
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            self._send_text(self._index_html(), content_type="text/html; charset=utf-8")
            return
        if path == "/api/schema":
            self._send_json(self.schema_cache)
            return
        if path == "/api/defaults":
            self._send_json(_default_settings(self.schema_cache))
            return
        if path == "/api/run":
            self._send_json({"run": self.runs.active()})
            return
        if path == "/api/log":
            active = self.runs.active()
            if active is None:
                self._send_json({"lines": []})
                return
            tail = 220
            try:
                tail = int((query.get("tail") or ["220"])[0])
            except Exception:
                tail = 220
            lines = _tail_lines(Path(active["log_path"]), limit=tail)
            self._send_json({"run": active, "lines": lines})
            return
        if path == "/api/presets":
            self._send_json({"presets": _load_presets()})
            return
        if path == "/api/finals":
            self._send_json({"files": _recent_final_files()})
            return

        self._send_json({"error": "not found"}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        data = self._read_json_body()

        if path == "/api/preview":
            settings = _normalize_settings(self.schema_cache, dict(data.get("settings", {})))
            _cmd, preview = _build_command(self.schema_cache, settings=settings)
            self._send_json({"preview": preview, "settings": settings})
            return

        if path == "/api/run":
            settings = _normalize_settings(self.schema_cache, dict(data.get("settings", {})))
            cmd, preview = _build_command(self.schema_cache, settings=settings)
            run_name = str(settings.get("run_name") or "").strip()
            if run_name == "":
                run_name = "optimizer_gui_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            run_id = "run_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
            log_path = RESULTS_ROOT / f"{run_name}.gui.log"
            log_fh = log_path.open("a", encoding="utf-8")
            log_fh.write("[%s] START %s\n" % (_utc_now(), preview))
            log_fh.flush()
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                text=True,
            )
            row = {
                "run_id": run_id,
                "run_name": run_name,
                "status": "running",
                "started_at": _utc_now(),
                "ended_at": None,
                "pid": int(proc.pid),
                "log_path": str(log_path),
                "command_preview": preview,
                "command_list": cmd,
                "proc": proc,
                "log_fh": log_fh,
            }
            try:
                active = self.runs.start(row)
            except Exception as exc:
                proc.terminate()
                log_fh.write("[%s] FAILED to register run: %s\n" % (_utc_now(), str(exc)))
                log_fh.flush()
                log_fh.close()
                self._send_json({"error": str(exc)}, status=409)
                return
            self._send_json({"run": active}, status=201)
            return

        if path == "/api/stop":
            try:
                state = self.runs.stop()
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=404)
                return
            self._send_json({"run": state})
            return

        if path == "/api/presets/save":
            name = str(data.get("name", "")).strip()
            if name == "":
                self._send_json({"error": "name is required"}, status=400)
                return
            settings = _normalize_settings(self.schema_cache, dict(data.get("settings", {})))
            presets = _load_presets()
            presets[name] = {"saved_at": _utc_now(), "settings": settings}
            _save_presets(presets)
            self._send_json({"ok": True, "presets": presets})
            return

        if path == "/api/load-final-json":
            try:
                final_path = _resolve_final_json_path(str(data.get("path", "")))
                payload = json.loads(final_path.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("final json payload must be an object")
                settings = _build_settings_from_final(self.schema_cache, payload)
                benchmark = payload.get("benchmark", {}) if isinstance(payload.get("benchmark", {}), dict) else {}
                metrics = benchmark.get("metrics", {}) if isinstance(benchmark.get("metrics", {}), dict) else {}
                self._send_json(
                    {
                        "ok": True,
                        "path": str(final_path),
                        "settings": settings,
                        "status": payload.get("status"),
                        "run_name": payload.get("run_name"),
                        "param_count": len(list(settings.get("seed_param", []))),
                        "best_metrics": {
                            "profit_abs": metrics.get("profit_abs"),
                            "max_drawdown_pct": metrics.get("max_drawdown_pct"),
                            "trades_closed": metrics.get("trades_closed"),
                            "relY_final": metrics.get("relY_final"),
                        },
                    }
                )
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=400)
            return

        self._send_json({"error": "not found"}, status=404)

    def log_message(self, fmt, *args):
        return

    @staticmethod
    def _index_html() -> str:
        return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Entry Optimizer GUI</title>
  <style>
    :root {
      --bg0: #f6f0e4;
      --bg1: #e6d9c1;
      --panel: #fffdf8;
      --panel-soft: #f5efe3;
      --text: #1e1e1e;
      --muted: #5f5f5f;
      --accent: #145f63;
      --accent2: #bc6d2e;
      --line: #d6c9b4;
      --ok: #176f3b;
      --warn: #8a4a14;
      --err: #9d1e1e;
    }
    html, body {
      margin: 0;
      padding: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      color: var(--text);
    }
    body { background: linear-gradient(135deg, var(--bg0), var(--bg1)); min-height: 100vh; }
    .wrap { max-width: 1380px; margin: 0 auto; padding: 18px; }
    .hero {
      background: linear-gradient(120deg, #0f4f58, #26706d 55%, #3f8777);
      color: #f7fffc;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 10px 24px rgba(16, 56, 59, 0.28);
    }
    .hero h1 { margin: 0 0 8px 0; font-size: 28px; letter-spacing: 0.01em; }
    .hero p { margin: 0; opacity: 0.92; }
    .hero-meta { margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }
    .grid { display: grid; grid-template-columns: 1.3fr 0.9fr; gap: 14px; margin-top: 14px; align-items: start; }
    .card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 5px 20px rgba(0, 0, 0, 0.05);
    }
    .console-card { position: sticky; top: 12px; }
    .card h2 { margin: 0 0 10px 0; font-size: 18px; }
    h3 { margin: 14px 0 8px 0; font-size: 13px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); }
    .settings-toolbar {
      display: grid;
      grid-template-columns: 1fr auto auto;
      gap: 8px;
      margin-bottom: 10px;
      align-items: center;
    }
    .field {
      display: grid;
      grid-template-columns: minmax(180px, 260px) minmax(280px, 1fr);
      gap: 10px;
      align-items: center;
    }
    .field label { font-size: 13px; font-weight: 600; color: #2f2f2f; }
    .field-row { padding: 8px 10px; border-radius: 10px; border: 1px solid transparent; background: #fff; }
    .field-row:hover { border-color: #e3d6c3; background: #fffcf7; }
    .hint { color: var(--muted); font-size: 11px; margin-top: 5px; line-height: 1.35; }
    input[type=text], input[type=number], textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      box-sizing: border-box;
      background: #fff;
      transition: border-color .18s ease, box-shadow .18s ease;
    }
    input[type=text]:focus, input[type=number]:focus, textarea:focus, select:focus {
      outline: none;
      border-color: #3a7f7c;
      box-shadow: 0 0 0 2px rgba(26, 100, 97, 0.15);
    }
    textarea { min-height: 74px; resize: vertical; }
    .check { display: flex; align-items: center; gap: 8px; min-height: 30px; }
    .btns { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .settings-actions {
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--line);
      position: sticky;
      bottom: 0;
      background: linear-gradient(180deg, rgba(255,253,248,0.72), rgba(255,253,248,1) 32%);
      backdrop-filter: blur(1px);
    }
    button {
      border: 0;
      border-radius: 8px;
      padding: 10px 14px;
      cursor: pointer;
      font-weight: 600;
      background: var(--accent); color: white;
      transition: transform .12s ease, filter .12s ease;
    }
    button:hover { filter: brightness(0.98); transform: translateY(-1px); }
    button:active { transform: translateY(0); }
    button.alt { background: var(--accent2); }
    button.ghost { background: #ece6db; color: #303030; border: 1px solid #d9cfbf; }
    button.danger { background: #8b2020; }
    pre {
      background: #121a1d;
      color: #ddf4f1;
      border-radius: 8px;
      padding: 10px;
      overflow-x: auto;
      margin: 0;
      min-height: 78px;
    }
    #logbox {
      min-height: 380px;
      max-height: 62vh;
      overflow: auto;
      white-space: pre-wrap;
      border: 1px solid #243439;
    }
    .row { display:flex; gap:8px; align-items: center; flex-wrap: wrap; }
    .badge { padding: 4px 9px; border-radius: 999px; font-size: 12px; background: #ece6db; border: 1px solid #ddd2bf; }
    .group-card {
      border: 1px solid var(--line);
      border-radius: 10px;
      margin: 0 0 9px 0;
      background: #fffdf9;
      overflow: hidden;
    }
    .group-card summary {
      list-style: none;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      cursor: pointer;
      padding: 9px 11px;
      background: var(--panel-soft);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .07em;
      color: #4c4c4c;
      user-select: none;
    }
    .group-card summary::-webkit-details-marker { display: none; }
    .group-meta { display: flex; align-items: center; gap: 8px; }
    .group-count { font-size: 11px; padding: 3px 7px; border-radius: 999px; background: #efe5d2; border: 1px solid #d9ceb9; }
    .group-body { padding: 8px; display: grid; gap: 6px; }
    .inline-toggles { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .console-meta { margin-top: 6px; color: var(--muted); font-size: 12px; }
    .section-block { border-top: 1px dashed #d9cfbe; margin-top: 14px; padding-top: 12px; }
    .kbd {
      font-family: "IBM Plex Mono", ui-monospace, monospace;
      font-size: 11px;
      border: 1px solid #d3c9b7;
      border-bottom-width: 2px;
      border-radius: 6px;
      padding: 2px 5px;
      background: #f7f2e8;
      color: #4a4a4a;
    }
    .ok { color: var(--ok); } .warn { color: var(--warn); } .err { color: var(--err); }
    @media (max-width: 1040px) {
      .grid { grid-template-columns: 1fr; }
      .field { grid-template-columns: 1fr; }
      .settings-toolbar { grid-template-columns: 1fr; }
      .console-card { position: static; }
      #logbox { max-height: 48vh; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>Entry Optimizer Control</h1>
      <p>Local web launcher for staged optimizer. CLI remains source of truth; GUI fields are generated from optimizer schema.</p>
    </div>

    <div class="grid">
      <section class="card">
        <h2>Settings</h2>
        <div class="settings-toolbar">
          <input id="field-filter" type="text" placeholder="Filter fields (e.g. gate, objective, natr, sweep)..." />
          <button id="btn-expand-all" class="ghost">Expand All</button>
          <button id="btn-collapse-all" class="ghost">Collapse All</button>
        </div>
        <div id="form"></div>
        <div class="settings-actions">
          <div class="btns">
            <button id="btn-preview">Preview Command</button>
            <button id="btn-run" class="alt">Start Run</button>
            <button id="btn-stop" class="danger">Stop Active Run</button>
          </div>
          <div class="hint">Shortcut: <span class="kbd">Ctrl</span> + <span class="kbd">Enter</span> starts a run.</div>
        </div>

        <div class="section-block">
          <h3>Presets</h3>
          <div class="row">
            <input id="preset-name" type="text" placeholder="preset name" style="max-width:280px;" />
            <button id="btn-save-preset" class="ghost">Save Preset</button>
            <select id="preset-select" style="max-width:380px;"></select>
            <button id="btn-load-preset" class="ghost">Load Preset</button>
          </div>
        </div>

        <div class="section-block">
          <h3>Final JSON Import</h3>
          <div class="row">
            <select id="final-select" style="max-width:520px;"></select>
            <button id="btn-refresh-finals" class="ghost">Refresh Finals</button>
            <button id="btn-load-final" class="ghost">Load Final</button>
          </div>
          <div class="row" style="margin-top:8px;">
            <input id="final-path" type="text" placeholder="absolute path or path under backtest/results/entry_staged" />
          </div>
        </div>
      </section>

      <section class="card console-card">
        <h2>Run Console</h2>
        <div class="row">
          <span>Status:</span>
          <span id="status" class="badge">idle</span>
          <span id="pid" class="badge"></span>
        </div>
        <div id="run-meta" class="console-meta">No active run.</div>
        <h3>Command</h3>
        <pre id="cmd"></pre>
        <div class="btns">
          <button id="btn-copy" class="ghost">Copy Command</button>
          <button id="btn-refresh" class="ghost">Refresh Log</button>
          <button id="btn-clear-log" class="ghost">Clear View</button>
        </div>
        <div class="inline-toggles" style="margin-top:8px;">
          <label class="check"><input id="auto-refresh" type="checkbox" checked /> auto refresh</label>
          <label class="check"><input id="log-follow" type="checkbox" checked /> follow log</label>
        </div>
        <h3>Live Log</h3>
        <pre id="logbox"></pre>
      </section>
    </div>
  </div>
<script>
const state = { schema: null, settings: {}, presets: {}, finals: [] };
const GROUP_ORDER = [
  "Data",
  "Stages",
  "Objectives",
  "Gates",
  "Sweep",
  "Overrides",
  "Workers",
  "Run",
  "Final Run",
  "Other",
];

function groupFor(dest) {
  if (["entry_id","pair","exchange","timeframe","days"].includes(dest)) return "Data";
  if ([
    "stage0_gate_min_trades",
    "skip_stage0_gate",
    "skip_stage1b_confirmation",
    "disable_stage2_rechecks",
    "disable_stage3_rechecks",
    "disable_preparation_phase",
    "preparation_with_plots",
    "preparation_plot_open_browser",
  ].includes(dest)) return "Stages";
  if (["stage1b_objective","stage2_objective","stage3_objective","objective_profit_floor_ratio","objective_dd_cap","objective_dd_penalty"].includes(dest)) return "Objectives";
  if (["stage1_gate","stage2_gate","stage3_gate","constraint"].includes(dest)) return "Gates";
  if (["stage1_sweep","stage2_sweep","stage3_sweep"].includes(dest)) return "Sweep";
  if (["fixed_param","seed_param","sweep_range"].includes(dest)) return "Overrides";
  if (["eval_workers","max_eval_workers","ram_aware_workers","ram_reserve_gb","worker_ram_gb"].includes(dest)) return "Workers";
  if (["final_confirmation_run","final_run_with_plots","final_run_open_browser"].includes(dest)) return "Final Run";
  if (["run_name","out_dir","log_level","control_file","no_console_progress","dry_run_config"].includes(dest)) return "Run";
  return "Other";
}

function el(tag, attrs = {}, text = null) {
  const node = document.createElement(tag);
  for (const [k,v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== null) node.textContent = text;
  return node;
}

function readField(field) {
  const id = "f_" + field.dest;
  const node = document.getElementById(id);
  if (!node) return field.default;
  if (field.kind === "bool") return !!node.checked;
  if (field.kind === "list") return String(node.value || "").split("\\n").map(s => s.trim()).filter(Boolean);
  if (field.kind === "int") return node.value === "" ? null : parseInt(node.value, 10);
  if (field.kind === "float") return node.value === "" ? null : parseFloat(node.value);
  return String(node.value || "");
}

function collectSettings() {
  const out = {};
  for (const field of state.schema.fields) out[field.dest] = readField(field);
  return out;
}

function setField(field, value) {
  const id = "f_" + field.dest;
  const node = document.getElementById(id);
  if (!node) return;
  if (field.kind === "bool") node.checked = !!value;
  else if (field.kind === "list") node.value = Array.isArray(value) ? value.join("\\n") : "";
  else node.value = value == null ? "" : String(value);
}

function buildFieldInput(f) {
  let input;
  if (f.kind === "bool") {
    input = el("input", { id: "f_" + f.dest, type: "checkbox" });
    input.checked = !!f.default;
    const wrap = el("div", { class: "check" });
    wrap.appendChild(input);
    wrap.appendChild(el("span", {}, "enabled"));
    return wrap;
  }
  if (f.kind === "list") {
    input = el("textarea", { id: "f_" + f.dest, placeholder: "one value per line" });
    input.value = Array.isArray(f.default) ? f.default.join("\\n") : "";
    return input;
  }
  if (f.choices && Array.isArray(f.choices)) {
    input = el("select", { id: "f_" + f.dest });
    for (const c of f.choices) {
      const opt = el("option", { value: String(c) }, String(c));
      if (String(c) === String(f.default)) opt.selected = true;
      input.appendChild(opt);
    }
    return input;
  }
  const type = (f.kind === "int" || f.kind === "float") ? "number" : "text";
  input = el("input", { id: "f_" + f.dest, type });
  if (f.kind === "int") input.step = "1";
  if (f.kind === "float") input.step = "any";
  input.value = f.default == null ? "" : String(f.default);
  return input;
}

function renderForm() {
  const host = document.getElementById("form");
  host.innerHTML = "";
  const groups = {};
  for (const f of state.schema.fields) {
    const g = groupFor(f.dest);
    if (!groups[g]) groups[g] = [];
    groups[g].push(f);
  }
  const ordered = [...GROUP_ORDER, ...Object.keys(groups).filter(g => !GROUP_ORDER.includes(g)).sort()];
  for (const group of ordered) {
    const fields = groups[group];
    if (!fields || fields.length === 0) continue;

    const details = el("details", { class: "group-card", "data-group": group });
    details.open = group !== "Other";
    const summary = el("summary");
    const label = el("span", {}, group);
    const meta = el("span", { class: "group-meta" });
    meta.appendChild(el("span", { class: "group-count" }, String(fields.length)));
    summary.appendChild(label);
    summary.appendChild(meta);
    details.appendChild(summary);
    const body = el("div", { class: "group-body" });

    for (const f of fields) {
      const rowWrap = el("div", {
        class: "field-row",
        "data-dest": String(f.dest || "").toLowerCase(),
        "data-search": (String(f.dest || "") + " " + String(f.help || "") + " " + String(f.flag || "")).toLowerCase(),
      });
      const row = el("div", { class: "field" });
      row.appendChild(el("label", { for: "f_" + f.dest }, f.dest));
      row.appendChild(buildFieldInput(f));
      rowWrap.appendChild(row);
      if (f.help) rowWrap.appendChild(el("div", { class: "hint" }, f.help));
      body.appendChild(rowWrap);
    }
    details.appendChild(body);
    host.appendChild(details);
  }
}

function applyFieldFilter() {
  const q = String(document.getElementById("field-filter").value || "").trim().toLowerCase();
  const groups = Array.from(document.querySelectorAll(".group-card"));
  for (const group of groups) {
    let anyVisible = false;
    const rows = Array.from(group.querySelectorAll(".field-row"));
    for (const row of rows) {
      const hay = String(row.getAttribute("data-search") || "").toLowerCase();
      const visible = q === "" || hay.includes(q);
      row.style.display = visible ? "" : "none";
      if (visible) anyVisible = true;
    }
    group.style.display = anyVisible ? "" : "none";
  }
}

function setAllGroups(open) {
  const groups = Array.from(document.querySelectorAll(".group-card"));
  for (const g of groups) g.open = !!open;
}

async function refreshPreview() {
  const settings = collectSettings();
  const res = await fetch("/api/preview", { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ settings }) });
  const payload = await res.json();
  document.getElementById("cmd").textContent = payload.preview || "";
}

async function refreshRun() {
  const res = await fetch("/api/run");
  const payload = await res.json();
  const run = payload.run;
  const st = document.getElementById("status");
  const pid = document.getElementById("pid");
  const meta = document.getElementById("run-meta");
  if (!run) {
    st.textContent = "idle";
    st.className = "badge";
    pid.textContent = "";
    meta.textContent = "No active run.";
    return;
  }
  st.textContent = run.status || "unknown";
  st.className = "badge " + (run.status === "running" ? "ok" : (run.status === "failed" ? "err" : "warn"));
  pid.textContent = run.pid ? ("pid " + run.pid) : "";
  const started = run.started_at ? String(run.started_at) : "-";
  const ended = run.ended_at ? String(run.ended_at) : "-";
  const code = run.returncode == null ? "-" : String(run.returncode);
  meta.textContent = "started: " + started + " | ended: " + ended + " | rc: " + code;
  if (run.command_preview) document.getElementById("cmd").textContent = run.command_preview;
}

async function refreshLog() {
  const logBox = document.getElementById("logbox");
  const follow = !!document.getElementById("log-follow").checked;
  const res = await fetch("/api/log?tail=260");
  const payload = await res.json();
  const lines = payload.lines || [];
  logBox.textContent = lines.join("\\n");
  if (follow) logBox.scrollTop = logBox.scrollHeight;
}

async function startRun() {
  await refreshPreview();
  const settings = collectSettings();
  const res = await fetch("/api/run", { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ settings }) });
  const payload = await res.json();
  if (!res.ok) {
    alert(payload.error || "Failed to start run.");
    return;
  }
  await refreshRun();
  await refreshLog();
}

async function stopRun() {
  const res = await fetch("/api/stop", { method:"POST", headers:{ "Content-Type":"application/json" }, body: "{}" });
  const payload = await res.json();
  if (!res.ok) alert(payload.error || "Stop failed.");
  await refreshRun();
}

async function loadPresets() {
  const res = await fetch("/api/presets");
  const payload = await res.json();
  state.presets = payload.presets || {};
  const sel = document.getElementById("preset-select");
  sel.innerHTML = "";
  const names = Object.keys(state.presets).sort();
  for (const name of names) sel.appendChild(el("option", { value: name }, name));
}

async function savePreset() {
  const name = String(document.getElementById("preset-name").value || "").trim();
  if (!name) {
    alert("Preset name required.");
    return;
  }
  const settings = collectSettings();
  const res = await fetch("/api/presets/save", { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ name, settings }) });
  const payload = await res.json();
  if (!res.ok) {
    alert(payload.error || "Save failed.");
    return;
  }
  await loadPresets();
  document.getElementById("preset-select").value = name;
}

function applyPreset(name) {
  const row = state.presets[name];
  if (!row || !row.settings) return;
  for (const f of state.schema.fields) setField(f, row.settings[f.dest]);
  applyFieldFilter();
}

async function loadFinalFiles() {
  const res = await fetch("/api/finals");
  const payload = await res.json();
  state.finals = Array.isArray(payload.files) ? payload.files : [];
  const sel = document.getElementById("final-select");
  sel.innerHTML = "";
  for (const path of state.finals) sel.appendChild(el("option", { value: path }, path));
  if (state.finals.length > 0 && !document.getElementById("final-path").value) {
    document.getElementById("final-path").value = state.finals[0];
  }
}

async function loadFinalSettings() {
  const pathField = document.getElementById("final-path");
  const path = String(pathField.value || "").trim();
  if (!path) {
    alert("Final json path required.");
    return;
  }
  const res = await fetch("/api/load-final-json", {
    method:"POST",
    headers:{ "Content-Type":"application/json" },
    body: JSON.stringify({ path })
  });
  const payload = await res.json();
  if (!res.ok) {
    alert(payload.error || "Load failed.");
    return;
  }
  for (const f of state.schema.fields) {
    if (Object.prototype.hasOwnProperty.call(payload.settings || {}, f.dest)) {
      setField(f, payload.settings[f.dest]);
    }
  }
  await refreshPreview();
}

async function boot() {
  const schemaRes = await fetch("/api/schema");
  state.schema = await schemaRes.json();
  renderForm();
  applyFieldFilter();
  await loadPresets();
  await loadFinalFiles();
  await refreshPreview();
  await refreshRun();
  await refreshLog();

  document.getElementById("btn-preview").onclick = refreshPreview;
  document.getElementById("btn-run").onclick = startRun;
  document.getElementById("btn-stop").onclick = stopRun;
  document.getElementById("btn-refresh").onclick = refreshLog;
  document.getElementById("btn-clear-log").onclick = () => { document.getElementById("logbox").textContent = ""; };
  document.getElementById("btn-save-preset").onclick = savePreset;
  document.getElementById("btn-load-preset").onclick = () => applyPreset(document.getElementById("preset-select").value);
  document.getElementById("btn-refresh-finals").onclick = loadFinalFiles;
  document.getElementById("btn-load-final").onclick = loadFinalSettings;
  document.getElementById("btn-expand-all").onclick = () => setAllGroups(true);
  document.getElementById("btn-collapse-all").onclick = () => setAllGroups(false);
  document.getElementById("field-filter").oninput = applyFieldFilter;
  document.getElementById("final-select").onchange = (ev) => {
    document.getElementById("final-path").value = String(ev.target.value || "");
  };
  document.getElementById("btn-copy").onclick = async () => {
    const txt = document.getElementById("cmd").textContent || "";
    try { await navigator.clipboard.writeText(txt); } catch (_) {}
  };
  document.addEventListener("keydown", async (ev) => {
    if (!(ev.ctrlKey && ev.key === "Enter")) return;
    ev.preventDefault();
    await startRun();
  });

  setInterval(async () => {
    if (!document.getElementById("auto-refresh").checked) return;
    await refreshRun();
    await refreshLog();
  }, 3000);
}
boot();
</script>
</body>
</html>
"""


def main():
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    host = "127.0.0.1"
    port = 8765
    httpd = ThreadingHTTPServer((host, port), OptimizerGuiHandler)
    print("Entry optimizer GUI listening on http://%s:%d" % (host, port))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
