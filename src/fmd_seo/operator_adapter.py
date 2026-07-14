"""Read-only adapter over operator-agent's `fresh.draft` capability.

operator-agent is never modified. The adapter snapshots the repo's Git SHA and
working-tree status before and after any use and fails hard if either changed.
It exposes the voice/compliance verifier context (fmd-copywriting skill +
voice-conformance + compliance verifiers) for a fresh checker context.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

VERIFIER_FILES = [
    "SKILLS/fmd-copywriting/SKILL.md",
    "VERIFIERS/voice-conformance.md",
    "VERIFIERS/compliance.md",
]


class OperatorMutated(RuntimeError):
    pass


class OperatorUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RepoSnapshot:
    head_sha: str
    status_hash: str


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise OperatorUnavailable(f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}")
    return result.stdout


def snapshot(repo: Path) -> RepoSnapshot:
    head = _git(repo, "rev-parse", "HEAD").strip()
    status = _git(repo, "status", "--porcelain")
    return RepoSnapshot(head_sha=head, status_hash=hashlib.sha256(status.encode()).hexdigest())


class OperatorAdapter:
    def __init__(self, operator_repo: Path):
        self.repo = operator_repo
        self._start: RepoSnapshot | None = None

    def __enter__(self) -> "OperatorAdapter":
        if not (self.repo / ".git").exists():
            raise OperatorUnavailable(f"operator-agent repo not found at {self.repo}")
        self._start = snapshot(self.repo)
        return self

    def __exit__(self, *exc):
        end = snapshot(self.repo)
        if end != self._start:
            raise OperatorMutated(
                f"operator-agent changed during adapter use: "
                f"HEAD {self._start.head_sha[:10]} -> {end.head_sha[:10]}, "
                f"status hash {'changed' if end.status_hash != self._start.status_hash else 'same'}"
            )
        return False

    @property
    def start_snapshot(self) -> RepoSnapshot:
        if self._start is None:
            raise OperatorUnavailable("Adapter not entered")
        return self._start

    def verifier_context(self) -> dict[str, str]:
        """Read-only voice/compliance context for a fresh checker. An absent
        file is a hard error (never a degraded pass): the semantic layer must
        report BLOCK_SEMANTIC_UNAVAILABLE upstream."""
        context: dict[str, str] = {}
        for rel in VERIFIER_FILES:
            path = self.repo / rel
            if not path.exists():
                raise OperatorUnavailable(f"Verifier context file missing: {rel}")
            context[rel] = path.read_text(encoding="utf-8")
        return context
