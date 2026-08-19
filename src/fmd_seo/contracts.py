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
PAGE_PACKAGE_SCHEMA_VERSION = 2
PATCH_PACKAGE_SCHEMA_VERSION = 1

QUERY_EVIDENCE_KINDS = frozenset(
    {"serp_snapshot", "ai_response_snapshot", "llm_mentions_baseline",
     "stable_core_candidate", "gbp_snapshot", "keyword_volume",
     "serp_consensus", "aeo_response_panel",
     "review_language", "citation_source"}
)
RECEIPT_STATUSES = frozenset({"DONE", "NO_OP", "PARTIAL", "BLOCK", "ERROR"})
PACKAGE_TIERS = frozenset({"money-page", "supporting-post"})
INFORMATION_GAIN_KINDS = frozenset(
    {"data", "tool", "first_hand", "original_media", "comparison", "benchmark"}
)
PATCH_GENERATORS = frozenset(
    {"canonical", "sitemap", "schema", "internal-links", "copy"}
)


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
    # Optional per-query panel, not a QueryEvidence kind. The GSC footprint
    # itself is the bulk artifact at Observation.source; this kind was
    # declared and never constructed, so it was retired rather than wired.
    gsc_query_footprint: dict[str, Any] | None = None
    serp_consensus: dict[str, Any] | None = None
    aeo_response_panel: dict[str, Any] | None = None
    review_language: dict[str, Any] | None = None
    citation_source: dict[str, Any] | None = None

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
    information_gain: dict[str, str] | None = None
    verification: dict[str, str] = field(default_factory=dict)  # check -> verdict
    schema_version: int = PAGE_PACKAGE_SCHEMA_VERSION

    def __post_init__(self):
        if self.tier not in PACKAGE_TIERS:
            raise ContractError(f"Unknown PagePackage tier: {self.tier}")
        if self.schema_version not in {1, PAGE_PACKAGE_SCHEMA_VERSION}:
            raise ContractError(f"Unsupported PagePackage schema_version: {self.schema_version}")
        if self.schema_version == PAGE_PACKAGE_SCHEMA_VERSION:
            gain = self.information_gain
            if not isinstance(gain, dict) or not gain:
                raise ContractError("PagePackage v2 requires information_gain")
            if gain.get("kind") not in INFORMATION_GAIN_KINDS:
                raise ContractError(
                    "information_gain.kind must be one of "
                    + ", ".join(sorted(INFORMATION_GAIN_KINDS))
                )
            if not str(gain.get("description", "")).strip():
                raise ContractError("information_gain.description is required")
            evidence_ref = str(gain.get("evidence_ref", ""))
            if not evidence_ref or evidence_ref not in self.evidence_refs:
                raise ContractError(
                    "information_gain.evidence_ref must name an attached evidence_ref"
                )

    @staticmethod
    def derive_id(intent_key: str, tier: str, created_at: str, content: dict,
                  information_gain: dict[str, str] | None = None,
                  schema_version: int = PAGE_PACKAGE_SCHEMA_VERSION) -> str:
        values: dict[str, Any] = {
            "intent_key": intent_key,
            "tier": tier,
            "created_at": created_at,
            "content": content,
        }
        if schema_version >= 2:
            values["information_gain"] = information_gain
        core = canonical_json(values)
        return "pp-" + sha256_text(core)[:16]

    @classmethod
    def create(cls, *, intent_key, tier, created_at, fact_snapshot, evidence_refs,
               content, internal_links, assets, information_gain) -> "PagePackage":
        return cls(
            package_id=cls.derive_id(
                intent_key, tier, created_at, content, information_gain,
                PAGE_PACKAGE_SCHEMA_VERSION,
            ),
            intent_key=intent_key,
            tier=tier,
            created_at=created_at,
            fact_snapshot=fact_snapshot,
            evidence_refs=evidence_refs,
            content=content,
            internal_links=internal_links,
            assets=assets,
            information_gain=information_gain,
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


@dataclass(frozen=True)
class PatchPackage:
    package_id: str
    generator: str
    created_at: str
    site_base_commit: str
    fact_snapshot_hash: str
    evidence_refs: list[str]
    modifications: list[dict[str, str]]
    schema_version: int = PATCH_PACKAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != PATCH_PACKAGE_SCHEMA_VERSION:
            raise ContractError(
                f"PatchPackage schema_version {self.schema_version} != "
                f"{PATCH_PACKAGE_SCHEMA_VERSION}"
            )
        if self.generator not in PATCH_GENERATORS:
            raise ContractError(f"Unknown PatchPackage generator: {self.generator}")
        if len(self.site_base_commit) != 40 or any(
            c not in "0123456789abcdef" for c in self.site_base_commit.lower()
        ):
            raise ContractError("site_base_commit must be a full 40-character SHA")
        if not self.fact_snapshot_hash:
            raise ContractError("fact_snapshot_hash is required")
        if not self.evidence_refs:
            raise ContractError("PatchPackage requires evidence_refs")
        if not self.modifications:
            raise ContractError("PatchPackage requires at least one modification")
        seen: set[str] = set()
        for modification in self.modifications:
            if modification.get("operation") != "modify":
                raise ContractError("PatchPackage permits only modify operations")
            path = str(modification.get("path", ""))
            candidate = Path(path)
            if not path or candidate.is_absolute() or ".." in candidate.parts:
                raise ContractError(f"unsafe PatchPackage path: {path!r}")
            if path in seen:
                raise ContractError(f"duplicate PatchPackage path: {path}")
            seen.add(path)
            before = str(modification.get("before_sha256", ""))
            after = str(modification.get("after_sha256", ""))
            if any(len(value) != 64 for value in (before, after)):
                raise ContractError(f"modification hashes must be sha256 values: {path}")
            replacement = modification.get("replacement_content")
            if not isinstance(replacement, str):
                raise ContractError(f"replacement_content must be text: {path}")
            if sha256_text(replacement) != after:
                raise ContractError(f"after_sha256 does not match replacement_content: {path}")

    @staticmethod
    def derive_id(*, generator: str, created_at: str, site_base_commit: str,
                  fact_snapshot_hash: str, evidence_refs: list[str],
                  modifications: list[dict[str, str]]) -> str:
        core = canonical_json({
            "generator": generator,
            "created_at": created_at,
            "site_base_commit": site_base_commit,
            "fact_snapshot_hash": fact_snapshot_hash,
            "evidence_refs": evidence_refs,
            "modifications": modifications,
        })
        return "patch-" + sha256_text(core)[:16]

    @classmethod
    def create(cls, *, generator: str, created_at: str, site_base_commit: str,
               fact_snapshot_hash: str, evidence_refs: list[str],
               modifications: list[dict[str, str]]) -> "PatchPackage":
        return cls(
            package_id=cls.derive_id(
                generator=generator,
                created_at=created_at,
                site_base_commit=site_base_commit,
                fact_snapshot_hash=fact_snapshot_hash,
                evidence_refs=evidence_refs,
                modifications=modifications,
            ),
            generator=generator,
            created_at=created_at,
            site_base_commit=site_base_commit,
            fact_snapshot_hash=fact_snapshot_hash,
            evidence_refs=evidence_refs,
            modifications=modifications,
        )

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    def content_hash(self) -> str:
        return sha256_text(canonical_json(self.to_dict()))


_CONTRACTS = {
    "FactSnapshot": FactSnapshot,
    "QueryEvidence": QueryEvidence,
    "PagePackage": PagePackage,
    "RunReceipt": RunReceipt,
    "ExportManifest": ExportManifest,
    "PatchPackage": PatchPackage,
}


def from_dict(contract: str, data: dict):
    cls = _CONTRACTS[contract]
    allowed_versions = (
        {1, PAGE_PACKAGE_SCHEMA_VERSION}
        if contract == "PagePackage"
        else {PATCH_PACKAGE_SCHEMA_VERSION}
        if contract == "PatchPackage"
        else {SCHEMA_VERSION}
    )
    if data.get("schema_version") not in allowed_versions:
        raise ContractError(
            f"{contract} schema_version {data.get('schema_version')} not in "
            f"{sorted(allowed_versions)}"
        )
    if contract == "PagePackage" and data.get("schema_version") == 1:
        data = {**data, "information_gain": None}
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
    expected = PagePackage.derive_id(
        pkg.intent_key,
        pkg.tier,
        pkg.created_at,
        pkg.content,
        pkg.information_gain,
        pkg.schema_version,
    )
    if pkg.package_id != expected:
        raise ContractError(f"Package ID mismatch in {path.name}: stored {pkg.package_id}, derived {expected}")
    return pkg


def write_patch_package(package: PatchPackage, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{package.package_id}.json"
    payload = canonical_json(package.to_dict())
    if path.exists():
        if path.read_text(encoding="utf-8") == payload:
            return path
        raise ContractError(
            f"Immutable patch package {package.package_id} already exists with different content"
        )
    with path.open("x", encoding="utf-8") as handle:
        handle.write(payload)
    return path


def load_patch_package(path: Path) -> PatchPackage:
    data = json.loads(path.read_text(encoding="utf-8"))
    package = from_dict("PatchPackage", data)
    expected = PatchPackage.derive_id(
        generator=package.generator,
        created_at=package.created_at,
        site_base_commit=package.site_base_commit,
        fact_snapshot_hash=package.fact_snapshot_hash,
        evidence_refs=package.evidence_refs,
        modifications=package.modifications,
    )
    if package.package_id != expected:
        raise ContractError(
            f"PatchPackage ID mismatch in {path.name}: stored {package.package_id}, "
            f"derived {expected}"
        )
    return package
