from pathlib import Path

from fmd_seo import baselines
from fmd_seo.receipts import ReceiptBuilder, latest_receipt, load_receipt, write_receipt


def test_receipt_builder_blocks_accumulate():
    rb = ReceiptBuilder("verify")
    rb.check("a", "PASS")
    rb.check("b", "BLOCK", "bad claim")
    receipt = rb.finish()
    assert receipt.status == "BLOCK"
    assert receipt.blockers == ["b: bad claim"]


def test_receipt_write_load_latest(tmp_path):
    rb = ReceiptBuilder("preflight")
    rb.check("x", "PASS")
    rb.resume_point = "after-x"
    receipt = rb.finish()
    path = write_receipt(receipt, tmp_path)
    assert load_receipt(path) == receipt
    assert latest_receipt(tmp_path, "preflight").resume_point == "after-x"
    assert latest_receipt(tmp_path, "export") is None


def test_baseline_record_and_drift(tmp_path, git_repo):
    config = {"paths": {label: str(git_repo) for label in baselines.REPO_LABELS}}
    baselines.record(config, tmp_path)
    assert baselines.check_drift(tmp_path) == {}
    (git_repo / "file.txt").write_text("drifted\n")
    drift = baselines.check_drift(tmp_path)
    assert set(drift) == set(baselines.REPO_LABELS)
    assert "status changed" in drift["fresh_repo"]
