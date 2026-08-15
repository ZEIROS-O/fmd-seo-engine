"""Draft-only citation and seasonal action queues."""

from __future__ import annotations

from typing import Any


def build_citation_queue(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue = []
    for source in sources:
        priority = (
            int(source["frequency"])
            * int(source["buyer_relevance"])
            * int(source["inclusion_feasibility"])
        )
        queue.append({
            **source,
            "priority": priority,
            "action_mode": "research_and_draft",
            "outreach_allowed": False,
            "submission_allowed": False,
        })
    return sorted(queue, key=lambda item: (-item["priority"], item["domain"]))


def build_seasonal_calendar(
    evidence: list[dict[str, Any]],
    *,
    gate1_state: str,
    owner: str,
    year: int,
) -> list[dict[str, Any]]:
    entries = []
    for item in evidence:
        closed = gate1_state != "OPEN"
        entries.append({
            "start_date": f"{year}-{int(item['month']):02d}-01",
            "evidence": item,
            "target_query": item["query"],
            "target_page": item["page"],
            "action": "existing_page_or_gbp_draft" if closed else "existing_page_review",
            "owner": owner,
            "gate_status": f"GATE-1 {gate1_state}",
            "new_url_allowed": False,
        })
    return sorted(entries, key=lambda item: item["start_date"])
