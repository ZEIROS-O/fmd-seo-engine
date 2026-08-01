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
pricing:
  one_time:
    full_interior:
      price: 209
equipment:
  steamer:
    owned: false
autonomy:
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
