import os
import shutil
import subprocess
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _cron_fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    root = tmp_path / "engine"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    shutil.copy2(ENGINE_ROOT / "bin" / "fmd-seo-cron", bin_dir / "fmd-seo-cron")
    notify_log = tmp_path / "notify.log"
    (bin_dir / "notify-run").write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s|%s\\n' \"${NOTIFY_OK_CODES:-}\" \"$*\" >> \"$NOTIFY_LOG\"\n",
        encoding="utf-8",
    )
    home_bin = tmp_path / "home" / ".local" / "bin"
    home_bin.mkdir(parents=True)
    fake_python = home_bin / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"${1:-}\" == '-m' && \"${2:-}\" == 'fmd_seo' ]]; then\n"
        "  case \"${3:-}\" in\n"
        "    sync) echo '{\"command\":\"sync\"}'; exit \"${SYNC_CODE:-0}\" ;;\n"
        "    gsc-sync) echo '{\"command\":\"gsc-sync\"}'; exit \"${GSC_CODE:-0}\" ;;\n"
        "    assess) echo '{\"summary\":{\"critical\":1,\"high\":0,\"gate_drift\":false}}'; exit \"${ASSESS_CODE:-0}\" ;;\n"
        "  esac\n"
        "fi\n"
        "if [[ \"${1:-}\" == '-c' ]]; then echo 'summary'; exit 0; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "NOTIFY_LOG": str(notify_log),
    }
    return root, notify_log, env


def test_cron_propagates_sync_failure_and_notifies_error(tmp_path):
    root, notify_log, env = _cron_fixture(tmp_path)
    env.update({"SYNC_CODE": "4", "GSC_CODE": "0", "ASSESS_CODE": "4"})

    result = subprocess.run(
        ["bash", str(root / "bin" / "fmd-seo-cron")],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )

    assert result.returncode == 4
    notification = notify_log.read_text(encoding="utf-8")
    assert notification.startswith("0|")
    assert "FMD-SEO 4" in notification


def test_cron_kill_switch_emits_killed_heartbeat(tmp_path):
    root, notify_log, env = _cron_fixture(tmp_path)
    (root / "DISABLED").write_text("halt\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(root / "bin" / "fmd-seo-cron")],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )

    assert result.returncode == 0
    assert "KILLED" in notify_log.read_text(encoding="utf-8")
