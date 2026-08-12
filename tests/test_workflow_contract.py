from pathlib import Path

import pytest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/daily.yml"
# The site lives in a separate repository, checked out here as a gitignored
# worktree. CI has only the engine, so this assertion is a local convenience --
# the binding contract is enforced by the site repo's own suite.
SITE_CI = (
    Path(__file__).resolve().parents[1]
    / ".worktrees/fresh-site-v3/.github/workflows/ci.yml"
)


def test_daily_workflow_materializes_and_validates_semrush_key():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "SEMRUSH_API_KEY: ${{ secrets.SEMRUSH_API_KEY }}" in text
    assert "SEMRUSH_API_KEY=%s" in text
    assert 'test -n "$SEMRUSH_API_KEY"' in text


def test_daily_workflow_persists_every_durable_guard():
    text = WORKFLOW.read_text(encoding="utf-8")

    # brain/state.yaml carries GATE-1's counters and DISABLED is written by
    # killswitch.engage(); neither survives the runner unless it is staged.
    assert "git add -- state brain receipts evidence DISABLED" in text
    # A tracked file left unstaged makes `git pull --rebase` refuse, which would
    # discard the spend-ledger commit along with the runner.
    assert "rebase.autoStash=true" in text


def test_daily_workflow_gates_providers_on_credential_validation():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "steps.providers.outcome == 'success'" in text


def test_daily_workflow_runs_integrity_audit_after_assess_as_required_stage():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.index("id: assess") < text.index("id: audit")
    assert "run: fmd-seo audit" in text
    assert 'test "${{ steps.audit.outcome }}" = success' in text


@pytest.mark.skipif(not SITE_CI.exists(), reason="site worktree not checked out")
def test_site_ci_uses_wrangler_compatible_preview_flags():
    site_workflow = SITE_CI.read_text(encoding="utf-8")

    assert "bun run preview -- --port 4173" in site_workflow
    assert "strictPort" not in site_workflow
    # A shallow checkout makes `git log` succeed with the boundary commit's date
    # for every path, fabricating <lastmod> instead of tripping the fallback.
    assert "fetch-depth: 0" in site_workflow
