"""Non-secret capability checks used by local operators and CI."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


CAPABILITY_INPUTS: dict[str, tuple[str, ...]] = {
    "dataforseo": ("DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"),
    "semrush": ("SEMRUSH_API_KEY",),
    "gsc": ("GSC_SERVICE_ACCOUNT_JSON",),
    "facts": ("BUSINESS_FACTS_YAML",),
    "site": ("SITE_REPO_TOKEN",),
}


def check_capability(
    capability: str,
    *,
    environ: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> dict[str, object]:
    if capability not in CAPABILITY_INPUTS:
        raise ValueError(
            f"unknown capability {capability!r}; expected one of "
            f"{sorted(CAPABILITY_INPUTS)}"
        )
    values: dict[str, str] = {}
    if config is not None:
        creds_path = Path(str(config.get("creds_env", "")))
        if creds_path.is_file():
            try:
                lines = creds_path.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, _, value = stripped.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    supplied = environ if environ is not None else os.environ
    values.update({key: value for key, value in supplied.items() if value})

    if capability in {"dataforseo", "semrush"}:
        missing = [
            name for name in CAPABILITY_INPUTS[capability]
            if not values.get(name, "").strip()
        ]
    elif capability == "gsc" and config is not None:
        key_path = Path(str((config.get("gsc") or {}).get("key_path", "")))
        missing = [] if values.get("GSC_SERVICE_ACCOUNT_JSON", "").strip() or key_path.is_file() else ["gsc.key_path"]
    elif capability == "facts" and config is not None:
        facts_path = Path(str((config.get("paths") or {}).get("facts_file", "")))
        missing = [] if values.get("BUSINESS_FACTS_YAML", "").strip() or facts_path.is_file() else ["paths.facts_file"]
    elif capability == "site" and config is not None:
        site_path = Path(str((config.get("paths") or {}).get("site_worktree", "")))
        missing = [] if values.get("SITE_REPO_TOKEN", "").strip() or (site_path.is_dir() and (site_path / ".git").exists()) else ["paths.site_worktree"]
    else:
        missing = [
            name for name in CAPABILITY_INPUTS[capability]
            if not values.get(name, "").strip()
        ]
    return {
        "capability": capability,
        "status": "BLOCK" if missing else "DONE",
        "missing": missing,
    }


def check_capabilities(
    capabilities: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, object]]:
    selected = list(capabilities or CAPABILITY_INPUTS)
    return [
        check_capability(name, environ=environ, config=config)
        for name in selected
    ]
