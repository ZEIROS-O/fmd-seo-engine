"""Budget ledger: reserve estimated cost before every API call, settle after,
enforce total and per-endpoint caps. Ledger lives in ignored .run/ state."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .receipts import now_iso


class BudgetExceeded(RuntimeError):
    pass


class SpendLedger:
    def __init__(self, ledger_file: Path, total_cap_usd: float, endpoint_caps_usd: dict[str, float]):
        self.ledger_file = ledger_file
        self.total_cap = float(total_cap_usd)
        self.endpoint_caps = {k: float(v) for k, v in endpoint_caps_usd.items()}
        self.entries: list[dict] = []
        if ledger_file.exists():
            self.entries = json.loads(ledger_file.read_text(encoding="utf-8"))

    def _save(self) -> None:
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_file.write_text(json.dumps(self.entries, indent=1), encoding="utf-8")

    def _committed(self, endpoint: str | None = None) -> float:
        total = 0.0
        for e in self.entries:
            if endpoint is not None and e["endpoint"] != endpoint:
                continue
            # Open reservations count at their estimate; settled ones at actual.
            total += e["actual_usd"] if e["actual_usd"] is not None else e["reserved_usd"]
        return total

    def total_spend(self) -> float:
        return round(self._committed(), 4)

    def reserve(self, endpoint: str, estimated_usd: float) -> str:
        estimated_usd = float(estimated_usd)
        if self._committed() + estimated_usd > self.total_cap:
            raise BudgetExceeded(
                f"Total cap ${self.total_cap:.2f} would be exceeded "
                f"(committed ${self._committed():.4f} + est ${estimated_usd:.4f})"
            )
        cap = self.endpoint_caps.get(endpoint)
        if cap is not None and self._committed(endpoint) + estimated_usd > cap:
            raise BudgetExceeded(
                f"Endpoint cap ${cap:.2f} for '{endpoint}' would be exceeded"
            )
        reservation_id = uuid.uuid4().hex[:12]
        self.entries.append({
            "id": reservation_id,
            "ts": now_iso(),
            "endpoint": endpoint,
            "reserved_usd": estimated_usd,
            "actual_usd": None,
            "note": "",
        })
        self._save()
        return reservation_id

    def settle(self, reservation_id: str, actual_usd: float, note: str = "") -> None:
        for e in self.entries:
            if e["id"] == reservation_id:
                e["actual_usd"] = float(actual_usd)
                e["note"] = note
                self._save()
                return
        raise KeyError(f"Unknown reservation {reservation_id}")
