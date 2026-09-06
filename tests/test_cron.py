import os
import shutil
import subprocess
from pathlib import Path


ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _cron_fixture(tmp_path: Path) -> tuple[Path, Path, Path, dict[str, str]]:
    root = tmp_path / "engine"
    bin_dir = root / "bin"
    state_dir = root / "state"
    bin_dir.mkdir(parents=True)
    state_dir.mkdir()
    shutil.copy2(ENGINE_ROOT / "bin" / "fmd-seo-cron", bin_dir / "fmd-seo-cron")
    shutil.copy2(ENGINE_ROOT / "state/source-switches.yaml", state_dir / "source-switches.yaml")
    notify_log = tmp_path / "notify.log"
    command_log = tmp_path / "commands.log"
    git_log = tmp_path / "git.log"
    (bin_dir / "notify-run").write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s|%s\\n' \"$*\" \"${NOTIFY_STATUS:-DELIVERED}\" >> \"$NOTIFY_LOG\"\n"
        "printf 'notification_status=%s\\n' \"${NOTIFY_STATUS:-DELIVERED}\"\n"
        "exit \"${NOTIFY_SCRIPT_CODE:-0}\"\n",
        encoding="utf-8",
    )
    home_bin = tmp_path / "home" / ".local" / "bin"
    home_bin.mkdir(parents=True)
    fake_python = home_bin / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"${1:-}\" == '-c' && \"${3:-}\" == *source-switches.yaml ]]; then\n"
        "  printf '%s\\n' \"${SOURCE_SWITCHES:-dataforseo=true semrush=true gsc=true ga4=true gbp=true site=true}\"\n"
        "  exit \"${SOURCES_CODE:-0}\"\n"
        "fi\n"
        "if [[ \"${1:-}\" == '-m' && \"${2:-}\" == 'fmd_seo' ]]; then\n"
        "  shift 2\n"
        "  printf '%s\\n' \"$*\" >> \"$COMMAND_LOG\"\n"
        "  command=${1:-}; shift || :\n"
        "  key=$command\n"
        "  if [[ \"$command\" == credential-check ]]; then\n"
        "    while (($#)); do [[ \"$1\" == --capability ]] && { shift; key=cred_${1:-}; break; }; shift; done\n"
        "  elif [[ \"$command\" == sync ]]; then\n"
        "    while (($#)); do [[ \"$1\" == --source ]] && { shift; key=sync_${1:-}; break; }; shift; done\n"
        "  elif [[ \"$command\" == serp-bulk ]]; then key=serp\n"
        "  elif [[ \"$command\" == geogrid ]]; then key=grid\n"
        "  fi\n"
        "  var=${key^^}; var=${var//-/_}; var=${var}_CODE\n"
        "  if [[ \"$command\" == assess ]]; then echo '{\"summary\":{\"critical\":1,\"high\":0,\"gate_drift\":false}}'\n"
        "  else printf '{\"command\":\"%s\"}\\n' \"$command\"; fi\n"
        "  exit \"${!var:-0}\"\n"
        "fi\n"
        "if [[ \"${1:-}\" == '-c' ]]; then echo 'summary'; exit 0; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    fake_date = home_bin / "date"
    fake_date.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$*\" == '-u +%u' ]]; then echo \"${WEEKDAY:-2}\"\n"
        "elif [[ \"$*\" == '-u +%Y%m%dT%H%M%SZ' ]]; then echo 20260814T120000Z\n"
        "else /bin/date \"$@\"; fi\n",
        encoding="utf-8",
    )
    fake_date.chmod(0o755)
    fake_git = home_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$GIT_LOG\"\n"
        "if [[ \"$*\" == 'rev-parse --git-dir' ]]; then echo \"$GIT_DIR_RESULT\"; exit 0; fi\n"
        "if [[ \"$*\" == 'rev-parse --git-common-dir' ]]; then echo \"$GIT_COMMON_DIR_RESULT\"; exit 0; fi\n"
        "if [[ \"$*\" == 'rev-parse --show-superproject-working-tree' ]]; then exit 0; fi\n"
        "if [[ \"$*\" == 'status --porcelain=v1 -z --untracked-files=all' ]]; then\n"
        "  count=$(cat \"$GIT_STATUS_COUNT\" 2>/dev/null || echo 0)\n"
        "  if [[ $count == 0 ]]; then printf '%b' \"${GIT_STATUS_INITIAL:-}\"; else printf '%b' \"${GIT_STATUS_FINAL:-}\"; fi\n"
        "  printf '%s' $((count + 1)) > \"$GIT_STATUS_COUNT\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == add ]]; then exit \"${GIT_ADD_CODE:-0}\"; fi\n"
        "if [[ \"$*\" == 'diff --cached --quiet' ]]; then exit \"${GIT_DIFF_CODE:-0}\"; fi\n"
        "if [[ \"$*\" == 'branch --show-current' ]]; then echo \"${GIT_BRANCH:-automation/fmd-seo-state}\"; exit 0; fi\n"
        "if [[ \" $* \" == *' pull '* ]]; then exit \"${GIT_PULL_CODE:-0}\"; fi\n"
        "if [[ \"${1:-}\" == push && \"$*\" == *state-recovery/* ]]; then exit \"${GIT_RECOVERY_PUSH_CODE:-0}\"; fi\n"
        "if [[ \"${1:-}\" == push ]]; then exit \"${GIT_PUSH_CODE:-0}\"; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    fake_sleep = home_bin / "sleep"
    fake_sleep.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_sleep.chmod(0o755)
    env = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "NOTIFY_LOG": str(notify_log),
        "COMMAND_LOG": str(command_log),
        "GIT_LOG": str(git_log),
        "GIT_STATUS_COUNT": str(tmp_path / "git-status-count"),
        "GIT_DIR_RESULT": str(tmp_path / ".git/worktrees/fmd-seo-state"),
        "GIT_COMMON_DIR_RESULT": str(tmp_path / ".git"),
        "FMD_SEO_SCHEDULER_BRANCH": "automation/fmd-seo-state",
    }
    return root, notify_log, command_log, env


def _run(root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(root / "bin/fmd-seo-cron")],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def _commands(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def test_cron_runs_every_daily_stage_and_sunday_posts(tmp_path):
    root, notify_log, command_log, env = _cron_fixture(tmp_path)
    env["WEEKDAY"] = "7"

    result = _run(root, env)

    assert result.returncode == 0
    commands = _commands(command_log)
    for capability in ("dataforseo", "semrush", "gsc", "facts", "site"):
        assert f"credential-check --capability {capability}" in commands
    for command in (
        "tick",
        "sync --source semrush --source ga4 --source gbp --source site",
        "gsc-sync",
        "serp-bulk --post",
        "geogrid --post",
        "facts-check",
        "act --dry-run",
        "assess",
        "audit",
    ):
        assert command in commands
    assert "notification_status=DELIVERED" in result.stdout
    assert "DELIVERED" in notify_log.read_text(encoding="utf-8")


def test_cron_monday_collects_weekly_queues(tmp_path):
    root, _notify_log, command_log, env = _cron_fixture(tmp_path)
    env["WEEKDAY"] = "1"

    result = _run(root, env)

    assert result.returncode == 0
    commands = _commands(command_log)
    assert "serp-bulk --collect" in commands
    assert "geogrid --collect" in commands


def test_cron_skips_sync_source_when_matching_credential_fails(tmp_path):
    """cred_semrush failing used to still run `sync --source semrush`."""
    root, _notify_log, command_log, env = _cron_fixture(tmp_path)
    env["CRED_SEMRUSH_CODE"] = "4"

    result = _run(root, env)

    assert result.returncode == 4
    commands = _commands(command_log)
    assert "credential-check --capability semrush" in commands
    sync_commands = [command for command in commands if command.startswith("sync ")]
    assert sync_commands == ["sync --source ga4 --source gbp --source site"]


def test_cron_google_credential_failure_skips_ga4_and_gbp_sync(tmp_path):
    root, _notify_log, command_log, env = _cron_fixture(tmp_path)
    env["CRED_GSC_CODE"] = "4"

    result = _run(root, env)

    assert result.returncode == 4
    commands = _commands(command_log)
    sync_commands = [command for command in commands if command.startswith("sync ")]
    assert sync_commands == ["sync --source semrush --source site"]


def test_cron_source_switch_skips_only_disabled_source(tmp_path):
    root, _notify_log, command_log, env = _cron_fixture(tmp_path)
    env["SOURCE_SWITCHES"] = (
        "dataforseo=true semrush=false gsc=true ga4=true gbp=true site=true"
    )

    result = _run(root, env)

    assert result.returncode == 0
    commands = _commands(command_log)
    assert "credential-check --capability semrush" in commands
    sync_commands = [command for command in commands if command.startswith("sync ")]
    assert sync_commands == ["sync --source ga4 --source gbp --source site"]


def test_cron_missing_source_switch_fails_closed(tmp_path):
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)
    env["SOURCE_SWITCHES"] = "semrush=true gsc=true ga4=true gbp=true site=true"

    result = _run(root, env)

    assert result.returncode != 0
    assert "sources:failed" in result.stdout


def test_cron_dataforseo_credential_skip_fails_serp_and_grid_gates(tmp_path):
    root, _notify_log, command_log, env = _cron_fixture(tmp_path)
    env["CRED_DATAFORSEO_CODE"] = "4"

    result = _run(root, env)

    assert result.returncode == 4
    commands = _commands(command_log)
    assert not any(command.startswith("serp-bulk") for command in commands)
    assert not any(command.startswith("geogrid") for command in commands)
    assert "dataforseo:failed" in result.stdout
    assert "serp:skipped" in result.stdout
    assert "grid:skipped" in result.stdout


def test_cron_propagates_required_stage_failure(tmp_path):
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)
    env["AUDIT_CODE"] = "5"

    result = _run(root, env)

    assert result.returncode == 5
    assert "audit:failed" in result.stdout


def test_cron_direct_execution_requires_executable_mode(tmp_path):
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)

    assert (root / "bin/fmd-seo-cron").stat().st_mode & 0o111
    assert _run(root, env).returncode == 0


def test_cron_persist_makes_local_commit_without_pull_or_push(tmp_path):
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)
    env["GIT_DIFF_CODE"] = "1"
    env["GIT_STATUS_FINAL"] = "?? receipts/20260814-sync.json\\0"

    result = _run(root, env)

    assert result.returncode == 0
    git_commands = (Path(env["GIT_LOG"])).read_text(encoding="utf-8").splitlines()
    assert any(command.startswith("commit ") for command in git_commands)
    assert not any(" pull " in f" {command} " for command in git_commands)
    assert not any(command.startswith("push ") for command in git_commands)


def test_cron_blocks_before_python_on_primary_or_wrong_branch(tmp_path):
    root, _notify_log, command_log, env = _cron_fixture(tmp_path)
    env["GIT_BRANCH"] = "main"

    result = _run(root, env)

    assert result.returncode == 4
    assert "dedicated scheduler branch" in result.stderr
    assert not command_log.exists()


def test_cron_stages_only_exact_machine_owned_paths_from_this_run(tmp_path):
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)
    env["GIT_DIFF_CODE"] = "1"
    env["GIT_STATUS_FINAL"] = (
        "?? brain/observations/sync.health/20260814.json\\0"
        "?? receipts/20260814-sync.json\\0"
        " M brain/state.yaml\\0"
        "?? evidence/gsc-query-footprint/20260814.json\\0"
        "?? brain/quarantine/seo.indexation/20260814.json\\0"
    )

    result = _run(root, env)

    assert result.returncode == 0
    git_commands = Path(env["GIT_LOG"]).read_text(encoding="utf-8").splitlines()
    add = [command for command in git_commands if command.startswith("add ")]
    assert add == [
        "add -- brain/observations/sync.health/20260814.json "
        "receipts/20260814-sync.json brain/state.yaml "
        "evidence/gsc-query-footprint/20260814.json "
        "brain/quarantine/seo.indexation/20260814.json"
    ]


def test_cron_refuses_unowned_path_instead_of_committing_it(tmp_path):
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)
    env["GIT_DIFF_CODE"] = "1"
    env["GIT_STATUS_FINAL"] = " M README.md\\0"

    result = _run(root, env)

    assert result.returncode != 0
    assert "not machine-owned: README.md" in result.stdout
    git_commands = Path(env["GIT_LOG"]).read_text(encoding="utf-8").splitlines()
    assert not any(command.startswith("add ") for command in git_commands)


def test_cron_nonzero_persist_command_cannot_report_healthy(tmp_path):
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)
    env["GIT_ADD_CODE"] = "6"
    env["GIT_STATUS_FINAL"] = "?? receipts/20260814-sync.json\\0"

    result = _run(root, env)

    assert result.returncode == 6
    assert "persist:failed" in result.stdout


def test_cron_records_delivery_failure_without_failing_measurement(tmp_path):
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)
    env["NOTIFY_STATUS"] = "FAILED"

    result = _run(root, env)

    assert result.returncode == 0
    assert "notification_status=FAILED" in result.stdout


def test_cron_nonzero_notification_script_exit_is_not_reported_healthy(tmp_path):
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)
    env["NOTIFY_SCRIPT_CODE"] = "7"

    result = _run(root, env)

    assert result.returncode != 0
    assert "notify-script:failed" in result.stdout


def test_cron_notification_failure_cannot_downgrade_a_provider_failure(tmp_path):
    """The notifier reports on the run; it must never overwrite the run's verdict.

    `overall_code=$notify_code` was unconditional, so a failed Telegram ping
    replaced a real provider exit code with the notifier's own.
    """
    root, _notify_log, _command_log, env = _cron_fixture(tmp_path)
    env["SYNC_SEMRUSH_CODE"] = "4"
    env["NOTIFY_SCRIPT_CODE"] = "1"

    result = _run(root, env)

    assert result.returncode == 4, result.stdout
    assert "notify-script:failed" in result.stdout


def test_cron_kill_switch_emits_killed_heartbeat(tmp_path):
    root, notify_log, _command_log, env = _cron_fixture(tmp_path)
    (root / "DISABLED").write_text("halt\n", encoding="utf-8")

    result = _run(root, env)

    assert result.returncode == 0
    assert "KILLED" in notify_log.read_text(encoding="utf-8")


def test_notify_run_reports_delivered_status(tmp_path):
    home_bin = tmp_path / "home/.local/bin"
    home_bin.mkdir(parents=True)
    hermes = home_bin / "hermes"
    hermes.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    hermes.chmod(0o755)

    result = subprocess.run(
        ["bash", str(ENGINE_ROOT / "bin/notify-run"), "FMD-SEO", "0", "ok"],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path / "home")},
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "notification_status=DELIVERED"


def test_notify_run_reports_failed_delivery_but_remains_best_effort(tmp_path):
    home_bin = tmp_path / "home/.local/bin"
    home_bin.mkdir(parents=True)
    hermes = home_bin / "hermes"
    hermes.write_text("#!/usr/bin/env bash\nexit 9\n", encoding="utf-8")
    hermes.chmod(0o755)

    result = subprocess.run(
        ["bash", str(ENGINE_ROOT / "bin/notify-run"), "FMD-SEO", "0", "ok"],
        capture_output=True,
        text=True,
        env={**os.environ, "HOME": str(tmp_path / "home")},
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "notification_status=FAILED"
    assert "send failed (non-fatal)" in result.stderr
