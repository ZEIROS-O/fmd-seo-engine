"""Resolve and verify observation provenance without mutating it."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .contracts import sha256_text

_API_HANDLE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*:[A-Za-z0-9_.-]+$")
_URL = re.compile(r"^https?://[^\s]+$")


@dataclass(frozen=True)
class SourceRef:
    kind: str
    path: Path | None = None


def resolve_source(source: str, root: Path) -> SourceRef:
    """Classify a source string; only paths rooted in the engine are files."""
    candidate = Path(source)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate.relative_to(root)
    except ValueError:
        pass
    else:
        if source.startswith(("evidence/", "state/", "brain/", "receipts/")) or candidate.exists():
            return SourceRef("file", candidate)
    if Path(source).is_absolute() and Path(source).exists():
        return SourceRef("file", Path(source))
    if _URL.fullmatch(source):
        return SourceRef("api")
    lowered = source.lower()
    if lowered.startswith("console:"):
        return SourceRef("console")
    if lowered.startswith("agent:"):
        return SourceRef("agent")
    if _API_HANDLE.fullmatch(source):
        return SourceRef("api")
    if "console" in lowered or "live " in lowered or "sitemap" in lowered:
        return SourceRef("console")
    return SourceRef("unknown")


def parse_file(path: Path) -> None:
    """Confirm a cited artifact is readable and structurally parseable when typed."""
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("empty source artifact")
    if path.suffix == ".json":
        json.loads(text)
    elif path.suffix in {".yaml", ".yml"}:
        yaml.safe_load(text)


def file_sha256(path: Path) -> str:
    return sha256_text(path.read_text(encoding="utf-8"))
