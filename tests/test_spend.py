import pytest

from fmd_seo.spend import BudgetExceeded, SpendLedger

CAPS = {"serp": 3.0, "probe": 0.05}


def test_reserve_settle_reconcile(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json", 10.0, CAPS)
    rid = ledger.reserve("serp", 0.5)
    assert ledger.total_spend() == 0.5  # open reservation counts at estimate
    ledger.settle(rid, 0.32)
    assert ledger.total_spend() == 0.32


def test_total_cap_enforced(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json", 1.0, {})
    ledger.reserve("serp", 0.9)
    with pytest.raises(BudgetExceeded):
        ledger.reserve("serp", 0.2)


def test_endpoint_subcap_enforced(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.json", 10.0, CAPS)
    ledger.reserve("probe", 0.04)
    with pytest.raises(BudgetExceeded):
        ledger.reserve("probe", 0.02)
    ledger.reserve("serp", 1.0)  # other endpoints unaffected


def test_ledger_persists_across_instances(tmp_path):
    path = tmp_path / "spend.json"
    first = SpendLedger(path, 10.0, CAPS)
    rid = first.reserve("serp", 1.5)
    first.settle(rid, 1.5)
    second = SpendLedger(path, 10.0, CAPS)
    assert second.total_spend() == 1.5
