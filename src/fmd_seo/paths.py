"""Engine filesystem layout and config loading.

Committed zones: evidence/, packages/, receipts/, baselines/, fixtures/, config/.
Ignored runtime zone: .run/ (raw API payloads, locks, spend ledger, controller state).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

ENGINE_ROOT = Path(os.environ.get("FMD_SEO_ROOT", Path(__file__).resolve().parents[2]))

CONFIG_FILE = ENGINE_ROOT / "config" / "engine.yaml"
RUN_DIR = ENGINE_ROOT / ".run"
RAW_DIR = RUN_DIR / "raw"
LOCK_FILE = RUN_DIR / "lock"
SPEND_LEDGER = RUN_DIR / "spend.json"
KILL_FILE = ENGINE_ROOT / "DISABLED"

EVIDENCE_DIR = ENGINE_ROOT / "evidence"
PACKAGES_DIR = ENGINE_ROOT / "packages"
RECEIPTS_DIR = ENGINE_ROOT / "receipts"
BASELINES_DIR = ENGINE_ROOT / "baselines"
FIXTURES_DIR = ENGINE_ROOT / "fixtures"


def load_config(path: Path | None = None) -> dict:
    with open(path or CONFIG_FILE, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict) or cfg.get("schema_version") != 1:
        raise ValueError(f"Unsupported engine config schema: {path or CONFIG_FILE}")
    return cfg


def ensure_run_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
