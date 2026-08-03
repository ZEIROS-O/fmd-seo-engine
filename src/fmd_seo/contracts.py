"""Versioned data contracts.

All contracts serialize to canonical JSON (sorted keys, no whitespace drift) so
hashes are stable. PagePackage IDs are content-addressed and immutable: writing
a package file that already exists with different content is an error.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

QUERY_EVIDENCE_KINDS = frozenset(
    {"serp_snapshot", "ai_response_snapshot", "llm_mentions_baseline",
     "stable_core_candidate", "gbp_snapshot", "keyword_volume"}
)
RECEIPT_STATUSES = frozenset({"DONE", "NO_OP", "PARTIAL", "BLOCK", "ERROR"})
PACKAGE_TIERS = frozenset({"money-page", "supporting-post"})


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class FactSnapshot:
    canonical_path: str
    source_hash: str
    source_last_updated: str
    reviewed_at: str
    review_after_days: int
    captured_at: str
    facts_used: dict[str, Any]  # dotted fact key -> value, only the keys used
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class QueryEvidence:
    evidence_id: str
    kind: str  # one of QUERY_EVIDENCE_KINDS
    query: str
    captured_at: str
    endpoint: str
    normalized: dict[str, Any]
    raw_ref: str  # hash of raw payload kept under .run/raw/
    cost_usd: float
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        if self.kind not in QUERY_EVIDENCE_KINDS:
            raise ContractError(f"Unknown QueryEvidence kind: {self.kind}")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class PagePackage:
    package_id: str
    intent_key: str
    tier: str  # one of PACKAGE_TIERS
    created_at: str
    fact_snapshot: dict[str, Any]
    evidence_refs: list[str]
    content: dict[str, Any]  # title, slug, meta, body_blocks, schema_jsonld
    internal_links: list[dict[str, str]]
    assets: list[dict[str, Any]]  # each with provenance
    verification: dict[str, str] = field(default_factory=dict)  # check -> verdict
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        if self.tier not in PACKAGE_TIERS:
            raise ContractError(f"Unknown PagePackage tier: {self.tier}")

    @staticmethod
    def derive_id(intent_key: str, tier: str, created_at: str, content: dict) -> str:
        core = canonical_json(
            {"intent_key": intent_key, "tier": tier, "created_at": created_at, "content": content}
        )
        return "pp-" + sha256_text(core)[:16]

    @classmethod
    def create(cls, *, intent_key, tier, created_at, fact_snapshot, evidence_refs,
               content, internal_links, assets) -> "PagePackage":
        return cls(
            package_id=cls.derive_id(intent_key, tier, created_at, content),
            intent_key=intent_key,
            tier=tier,
            created_at=created_at,
            fact_snapshot=fact_snapshot,
            evidence_refs=evidence_refs,
            content=content,
            internal_links=internal_links,
            assets=assets,
        )

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def content_hash(self) -> str:
        return sha256_text(canonical_json(self.to_dict()))


@dataclass(frozen=True)
class RunReceipt:
    run_id: str
    status: str  # one of RECEIPT_STATUSES; ERROR is an execution failure, not a refusal
    started_at: str
    ended_at: str
    command: str
    attempts: int
    checks: list[dict[str, str]]  # {name, verdict, detail}
    spend_usd: float
    blockers: list[str]
    resume_point: str | None
    commit_hashes: dict[str, str]  # repo label -> SHA
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        if self.status not in RECEIPT_STATUSES:
            raise ContractError(f"Unknown RunReceipt status: {self.status}")

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ExportManifest:
    package_id: str
    package_hash: str
    generated_files: list[str]
    canonical_url: str
    destination_commit: str
    rollback_base: str
    exported_at: str
    expected: dict[str, str] = dataclasses.field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


_CONTRACTS = {
    "FactSnapshot": FactSnapshot,
    "QueryEvidence": QueryEvidence,
    "PagePackage": PagePackage,
    "RunReceipt": RunReceipt,
    "ExportManifest": ExportManifest,
}


def from_dict(contract: str, data: dict):
    cls = _CONTRACTS[contract]
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(
            f"{contract} schema_version {data.get('schema_version')} != {SCHEMA_VERSION}"
        )
    return cls(**data)


def write_package(package: PagePackage, directory: Path) -> Path:
    """Write a PagePackage. Package files are immutable: an existing file with
    different content is a hard error, identical content is a no-op."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{package.package_id}.json"
    payload = canonical_json(package.to_dict())
    if path.exists():
        if path.read_text(encoding="utf-8") == payload:
            return path
        raise ContractError(f"Immutable package {package.package_id} already exists with different content")
    path.write_text(payload, encoding="utf-8")
    return path


def load_package(path: Path) -> PagePackage:
    data = json.loads(path.read_text(encoding="utf-8"))
    pkg = from_dict("PagePackage", data)
    expected = PagePackage.derive_id(pkg.intent_key, pkg.tier, pkg.created_at, pkg.content)
    if pkg.package_id != expected:
        raise ContractError(f"Package ID mismatch in {path.name}: stored {pkg.package_id}, derived {expected}")
    return pkg
