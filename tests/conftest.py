import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest


LOCAL_SITE_SKIP_REASON = "site worktree not checked out (local-only contract)"


def _sitemap_script() -> Path:
    """Locate the site's sitemap generator via the engine's configured path.

    The site checkout is gitignored and shared across engine worktrees, so it is
    not at a fixed offset from this file.
    """
    from fmd_seo.paths import load_config

    worktree = (load_config().get("paths") or {}).get("site_worktree", "")
    return Path(worktree) / "scripts/generate-sitemap.mjs"


@pytest.fixture
def site_repo(tmp_path: Path) -> Path:
    """A minimal git-backed site whose sitemap the *real* generator script builds.

    The script under test is copied from the site worktree rather than
    reimplemented, so a change to the site's route-discovery rules surfaces here
    instead of silently invalidating what the engine's patch generator assumes.
    Route content is synthetic and deliberately small -- only the shapes the
    script reads (route filenames, `slug:` literals, blog JSON) matter.
    """
    script = _sitemap_script()
    if not script.is_file():
        pytest.skip(LOCAL_SITE_SKIP_REASON)
    if shutil.which("node") is None:
        pytest.fail("node is required when the local site worktree is present")

    repo = tmp_path / "site"
    (repo / "scripts").mkdir(parents=True)
    (repo / "src/routes").mkdir(parents=True)
    (repo / "src/components").mkdir(parents=True)
    (repo / "content/blog").mkdir(parents=True)
    (repo / "public").mkdir(parents=True)

    shutil.copy(script, repo / "scripts/generate-sitemap.mjs")
    for name in (
        "index", "mobile-detailing", "booking-confirmed",
        "privacy-policy", "terms-of-service", "cancellation-refund-policy",
    ):
        (repo / f"src/routes/{name}.tsx").write_text(f"export const {name!r};\n", encoding="utf-8")
    (repo / "src/routes/__root.tsx").write_text("root\n", encoding="utf-8")
    (repo / "src/routes/blog.$slug.tsx").write_text(
        'const posts = [\n  {\n    slug: "legacy-post",\n  },\n];\n', encoding="utf-8",
    )
    (repo / "src/components/CityPage.tsx").write_text(
        'const cities = [\n  {\n    slug: "beachwood",\n  },\n];\n', encoding="utf-8",
    )
    (repo / "content/blog/post.json").write_text(
        '{"slug": "first-post", "date_published": "2026-07-01"}\n', encoding="utf-8",
    )

    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    git("init", "-b", "main")
    git("config", "user.email", "test@test.local")
    git("config", "user.name", "test")
    git("add", ".")
    git("commit", "-m", "site")
    return repo


@pytest.fixture
def run_sitemap_generator():
    """Run the site's own generator and return the resulting <loc> set."""
    import re

    def run(repo: Path) -> set[str]:
        subprocess.run(
            ["node", "scripts/generate-sitemap.mjs"],
            cwd=repo, check=True, capture_output=True, text=True,
        )
        xml = (repo / "public/sitemap.xml").read_text(encoding="utf-8")
        return set(re.findall(r"<loc>([^<]+)</loc>", xml))

    return run


@pytest.fixture
def facts_file(tmp_path: Path) -> Path:
    path = tmp_path / "business-facts.yaml"
    today = date.today().isoformat()
    path.write_text(
        f"""\
schema_version: 1
business_id: fresh-mobile-detailing
source_last_updated: {today}
reviewed_at: {today}
review_after_days: 30
identity:
  name: Fresh Mobile Detailing
  phone: "(216) 359-1034"
service_area:
  base: Beachwood / Mayfield Heights
  radius_miles: 30
  places: [Beachwood, Mayfield Heights, Solon, Orange, Pepper Pike, Shaker Heights]
hours: {{days: [Monday, Tuesday, Wednesday, Thursday, Friday, Saturday], opens: "08:00", closes: "18:00"}}
services:
  duration_hours: {{min: 1.5, max: 4}}
  offered: [Full Interior Detail, Ultimate Interior Detail]
  exterior_add_on: à-la-carte exterior hand wash
  not_offered: [ceramic coating, PPF, paint correction]
fleet_discount: {{available: true, applies_to: [fleet, multi_car]}}
pricing:
  one_time:
    full_interior:
      price: 209
      duration_hours: 2
    ultimate_interior:
      price: 279
      duration_hours: 3
  membership_per_visit:
    monthly: 149
    bi_monthly: 169
    quarterly: 189
  neighbor_discount: 25
guarantee:
  name: Door-Open Guarantee
  summary: Wow when you open the door, or you do not pay
  remedy_window_hours: 24
equipment:
  steamer:
    owned: false
claim_gates:
  review_count_public_claim:
    allowed: false
autonomy:
  customer_contact: human_only
  posting: human_only
""",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    def git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    git("init", "-b", "main")
    git("config", "user.email", "test@test.local")
    git("config", "user.name", "test")
    (repo / "file.txt").write_text("hello\n")
    git("add", ".")
    git("commit", "-m", "init")
    return repo
