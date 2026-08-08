import yaml

from fmd_seo import paths
from fmd_seo.paths import load_config


def test_safety_state_is_committed_outside_run_dir():
    assert paths.SPEND_LEDGER == paths.STATE_DIR / "spend.json"
    assert paths.HEALTH_FILE == paths.STATE_DIR / "health.json"
    assert paths.SERP_BULK_MANIFEST == paths.STATE_DIR / "serp-bulk-task-manifest.json"
    assert paths.GEOGRID_MANIFEST == paths.STATE_DIR / "geogrid-task-manifest.json"


def test_load_config_applies_ci_path_overrides(tmp_path, monkeypatch):
    config_file = tmp_path / "engine.yaml"
    config_file.write_text(yaml.safe_dump({
        "schema_version": 1,
        "creds_env": "/home/local/.dataforseo.env",
        "paths": {
            "facts_file": "/mnt/local/business-facts.yaml",
            "site_worktree": "/home/local/site",
        },
        "gsc": {"key_path": "/home/local/google.json"},
        "gbp": {"key_path": "/home/local/google.json"},
        "ga4": {
            "key_path": "/home/local/google.json",
            "property_id": "541970582",
            "days": 28,
        },
    }), encoding="utf-8")
    monkeypatch.setenv("FMD_SEO_CREDS_ENV", "/ci/dataforseo.env")
    monkeypatch.setenv("FMD_SEO_FACTS_FILE", "/ci/business-facts.yaml")
    monkeypatch.setenv("FMD_SEO_SITE_WORKTREE", "/ci/site")
    monkeypatch.setenv("FMD_SEO_GOOGLE_KEY", "/ci/google.json")

    config = load_config(config_file)

    assert config["creds_env"] == "/ci/dataforseo.env"
    assert config["paths"]["facts_file"] == "/ci/business-facts.yaml"
    assert config["paths"]["site_worktree"] == "/ci/site"
    assert config["gsc"]["key_path"] == "/ci/google.json"
    assert config["gbp"]["key_path"] == "/ci/google.json"
    assert config["ga4"]["key_path"] == "/ci/google.json"
    assert config["ga4"]["property_id"] == "541970582"
