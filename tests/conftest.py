import subprocess
from datetime import date
from pathlib import Path

import pytest


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
