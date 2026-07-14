import json
import os

import pytest

from fmd_seo import killswitch
from fmd_seo.runstate import LockHeld, RunLock


def test_killswitch_cycle(tmp_path):
    assert not killswitch.engaged(tmp_path)
    killswitch.engage("test reason", tmp_path)
    assert killswitch.engaged(tmp_path)
    with pytest.raises(killswitch.KillSwitchEngaged, match="test reason"):
        killswitch.assert_not_engaged(tmp_path)


def test_lock_blocks_live_pid(tmp_path):
    lock_file = tmp_path / "lock"
    lock_file.write_text(json.dumps({"pid": os.getppid(), "run_id": "other"}))
    with pytest.raises(LockHeld):
        RunLock(lock_file).acquire("mine")


def test_stale_lock_recovered(tmp_path):
    lock_file = tmp_path / "lock"
    lock_file.write_text(json.dumps({"pid": 999999999, "run_id": "dead"}))
    lock = RunLock(lock_file)
    lock.acquire("mine")
    assert lock.stale_recovered
    assert json.loads(lock_file.read_text())["run_id"] == "mine"
    lock.release()
    assert not lock_file.exists()


def test_corrupt_lock_treated_as_stale(tmp_path):
    lock_file = tmp_path / "lock"
    lock_file.write_text("{not json")
    lock = RunLock(lock_file)
    lock.acquire("mine")
    assert lock.stale_recovered
