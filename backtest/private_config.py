import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PRIVATE_SETTINGS_PATH = PROJECT_ROOT / "settings" / "private" / "backtest_private_settings.json"


def get_private_settings_path() -> Path:
    configured = os.environ.get("BACKTEST_PRIVATE_SETTINGS_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_PRIVATE_SETTINGS_PATH


def load_private_section(section_name: str) -> dict:
    settings_path = get_private_settings_path()
    if not settings_path.exists():
        raise RuntimeError(
            f"Missing private settings file: {settings_path}. "
            f"Set BACKTEST_PRIVATE_SETTINGS_PATH or create the file locally."
        )

    with settings_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    section = data.get(section_name)
    if not isinstance(section, dict):
        raise RuntimeError(
            f"Missing or invalid private settings section '{section_name}' in {settings_path}."
        )
    return section
