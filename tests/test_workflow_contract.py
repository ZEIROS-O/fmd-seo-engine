import re
from pathlib import Path

import pytest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/daily.yml"
# The site lives in a separate repository, checked out here as a gitignored
# worktree. CI has only the engine, so this assertion is a local convenience --
# the binding contract is enforced by the site repo's own suite.
from fmd_seo.paths import load_config


SITE_SKIP_REASON = "site worktree not checked out (local-only contract)"
SITE_CI = Path(load_config()["paths"]["site_worktree"]) / ".github/workflows/ci.yml"


def test_daily_workflow_is_a_credential_free_read_only_watchdog():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "${{ secrets." not in text
    assert "credential-check" not in text
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "fmd-seo freshness" in text


def test_daily_workflow_has_only_checkout_install_and_freshness_steps():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert text.count("uses:") == 2
    assert text.count("run:") == 2
    assert "pip install -e ." in text
    assert "fmd-seo freshness" in text
    for removed in ("git add", "git push", "curl", "gh run list", "site_checkout"):
        assert removed not in text


def test_daily_workflow_never_reads_a_step_property_that_does_not_exist():
    # `steps.<id>.<name>` resolves to null for anything other than these three
    # properties. A null in an `if:` skips the step permanently and a null in
    # `[[ "" != true ]]` short-circuits the gate -- both render green while
    # doing nothing, which is the exact failure this guard exists to prevent.
    text = WORKFLOW.read_text(encoding="utf-8")
    valid = {"outputs", "outcome", "conclusion"}

    bad = sorted(
        {
            match.group(0)
            for match in re.finditer(r"steps\.[A-Za-z0-9_-]+\.([A-Za-z0-9_-]+)", text)
            if match.group(1) not in valid
        }
    )

    assert bad == [], f"invalid steps context references: {bad}"


@pytest.mark.skipif(not SITE_CI.exists(), reason=SITE_SKIP_REASON)
def test_site_ci_uses_wrangler_compatible_preview_flags():
    site_workflow = SITE_CI.read_text(encoding="utf-8")

    assert "bunx wrangler --cwd dist dev" in site_workflow
    assert "--compatibility-flags nodejs_compat --port 4173" in site_workflow
    assert "strictPort" not in site_workflow
    # A shallow checkout makes `git log` succeed with the boundary commit's date
    # for every path, fabricating <lastmod> instead of tripping the fallback.
    assert "fetch-depth: 0" in site_workflow
