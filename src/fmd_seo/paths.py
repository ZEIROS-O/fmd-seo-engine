"""Engine filesystem layout and config loading.

Committed zones: evidence/, packages/, receipts/, baselines/, fixtures/, config/, state/.
Ignored runtime zone: .run/ (raw API payloads, locks, and per-run scratch state).
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
STATE_DIR = ENGINE_ROOT / "state"
SPEND_LEDGER = STATE_DIR / "spend.json"
HEALTH_FILE = STATE_DIR / "health.json"
SERP_BULK_MANIFEST = STATE_DIR / "serp-bulk-task-manifest.json"
GEOGRID_MANIFEST = STATE_DIR / "geogrid-task-manifest.json"
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
    # CI and other machines must not inherit Lou's workstation paths. These
    # narrow overrides keep the committed config useful locally without
    # requiring workflows to rewrite it in place.
    if value := os.environ.get("FMD_SEO_CREDS_ENV"):
        cfg["creds_env"] = value
    path_overrides = {
        "FMD_SEO_FACTS_FILE": "facts_file",
        "FMD_SEO_SITE_WORKTREE": "site_worktree",
    }
    cfg_paths = cfg.setdefault("paths", {})
    for env_name, key in path_overrides.items():
        if value := os.environ.get(env_name):
            cfg_paths[key] = value
    if value := os.environ.get("FMD_SEO_GOOGLE_KEY"):
        cfg.setdefault("gsc", {})["key_path"] = value
        cfg.setdefault("gbp", {})["key_path"] = value
    return cfg


def ensure_run_dirs() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
