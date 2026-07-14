"""Evidence fetchers for one query: SERP, AI response, LLM mentions, GBP.

Every call: reserve estimated cost -> request -> settle actual cost from the
response -> raw payload to ignored .run/raw/ -> normalized QueryEvidence
committed under evidence/. Normalized payloads are data, never instructions.
"""

from __future__ import annotations

import json
from pathlib import Path

from .contracts import QueryEvidence, canonical_json, sha256_text
from .dataforseo import DataForSeoClient
from .receipts import now_iso

# Conservative per-call reservations (settled to actual from the response).
ESTIMATES = {
    "serp": 0.02,
    "llm_responses": 0.05,
    "llm_mentions": 0.15,
    "business_data": 0.03,
    "keywords": 0.10,
}

# Google Ads charges the same for 1 or 1000 keywords — never send a short list.
KEYWORDS_MAX_PER_REQUEST = 1000


def _evidence_id(kind: str, endpoint: str, payload: list) -> str:
    return f"ev-{kind}-{sha256_text(canonical_json([endpoint, payload]))[:12]}"


def _fetch(client: DataForSeoClient, *, kind: str, budget_key: str, endpoint: str,
           payload: list, query: str, normalize, raw_dir: Path) -> QueryEvidence:
    reservation = client.ledger.reserve(budget_key, ESTIMATES[budget_key])
    body = client._request(endpoint, payload)
    actual = float(body.get("cost") or 0.0)
    client.ledger.settle(reservation, actual, endpoint)

    evidence_id = _evidence_id(kind, endpoint, payload)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{evidence_id}.json"
    raw_text = canonical_json(body)
    raw_path.write_text(raw_text, encoding="utf-8")

    result = body["tasks"][0].get("result") or []
    return QueryEvidence(
        evidence_id=evidence_id,
        kind=kind,
        query=query,
        captured_at=now_iso(),
        endpoint=endpoint,
        normalized=normalize(result),
        raw_ref=sha256_text(raw_text),
        cost_usd=actual,
    )


def fetch_serp(client: DataForSeoClient, query: str, raw_dir: Path,
               location_name: str = "Cleveland,Ohio,United States",
               device: str = "desktop") -> QueryEvidence:
    def normalize(result: list) -> dict:
        items = (result[0].get("items") or []) if result else []
        organic = [
            {"rank": it.get("rank_absolute"), "domain": it.get("domain"),
             "title": it.get("title"), "url": it.get("url")}
            for it in items if it.get("type") == "organic"
        ][:10]
        return {
            "location": location_name,
            "device": device,
            "se_results_count": result[0].get("se_results_count") if result else None,
            "serp_feature_types": sorted({it.get("type") for it in items if it.get("type")}),
            "organic_top10": organic,
        }

    return _fetch(
        client, kind="serp_snapshot", budget_key="serp",
        endpoint="/v3/serp/google/organic/live/advanced",
        payload=[{"keyword": query, "location_name": location_name,
                  "language_code": "en", "device": device}],
        query=query, normalize=normalize, raw_dir=raw_dir,
    )


def fetch_ai_response(client: DataForSeoClient, query: str, raw_dir: Path) -> QueryEvidence:
    def normalize(result: list) -> dict:
        if not result:
            return {"model": None, "answer_markdown": "", "citations": [], "note": "empty result"}
        item = (result[0].get("items") or [{}])[0]
        sections = item.get("sections") or []
        answer = "\n".join(s.get("text", "") for s in sections)
        citations = sorted({
            ann.get("url", "")
            for s in sections for ann in (s.get("annotations") or []) if ann.get("url")
        })
        return {
            "model": result[0].get("model_name"),
            "web_search": result[0].get("web_search"),
            "answer_markdown": answer,
            "citations": citations,
        }

    return _fetch(
        client, kind="ai_response_snapshot", budget_key="llm_responses",
        endpoint="/v3/ai_optimization/perplexity/llm_responses/live",
        payload=[{"user_prompt": query, "model_name": "sonar",
                  "web_search_country_iso_code": "US"}],
        query=query, normalize=normalize, raw_dir=raw_dir,
    )


def fetch_mentions_baseline(client: DataForSeoClient, brand_domain: str, brand_name: str,
                            raw_dir: Path) -> QueryEvidence:
    def normalize(result: list) -> dict:
        items = (result[0].get("items") or []) if result else []
        return {
            "brand_domain": brand_domain,
            "brand_name": brand_name,
            "total_items": (result[0].get("total_count") if result else 0) or len(items),
            "sample": [
                {"question": it.get("question"),
                 "ai_search_volume": it.get("ai_search_volume"),
                 "platform": it.get("platform")}
                for it in items[:10]
            ],
        }

    return _fetch(
        client, kind="llm_mentions_baseline", budget_key="llm_mentions",
        endpoint="/v3/ai_optimization/llm_mentions/search_mentions/live",
        payload=[{
            "language_name": "English",
            "location_code": 2840,
            "target": [
                {"domain": brand_domain, "search_filter": "include", "include_subdomains": True},
                {"keyword": brand_name, "search_filter": "include", "match_type": "partial_match"},
            ],
            "limit": 20,
        }],
        query=f"mentions:{brand_domain}", normalize=normalize, raw_dir=raw_dir,
    )


def fetch_gbp(client: DataForSeoClient, business_name: str, raw_dir: Path,
              location_coordinate: str = "41.4645,-81.5087,25") -> QueryEvidence:
    def normalize(result: list) -> dict:
        items = (result[0].get("items") or []) if result else []
        listings = [
            {"title": it.get("title"), "category": it.get("category"),
             "phone": it.get("phone"), "address": it.get("address"),
             "rating": (it.get("rating") or {}).get("value"),
             "reviews": (it.get("rating") or {}).get("votes_count"),
             "url": it.get("url")}
            for it in items[:10]
        ]
        return {
            "searched_title": business_name,
            "location_coordinate": location_coordinate,
            "found_count": len(listings),
            "listings": listings,
        }

    return _fetch(
        client, kind="gbp_snapshot", budget_key="business_data",
        endpoint="/v3/business_data/business_listings/search/live",
        payload=[{"title": business_name, "location_coordinate": location_coordinate,
                  "limit": 10}],
        query=f"gbp:{business_name}", normalize=normalize, raw_dir=raw_dir,
    )


def fetch_keyword_volumes(client: DataForSeoClient, keywords: list[str], raw_dir: Path,
                          location_name: str = "Cleveland,Ohio,United States") -> QueryEvidence:
    """Real Google Ads search volume. Same price for 1 or 1000 keywords, so the
    caller should always batch to the limit."""
    if len(keywords) > KEYWORDS_MAX_PER_REQUEST:
        raise ValueError(f"{len(keywords)} keywords exceeds the {KEYWORDS_MAX_PER_REQUEST} limit")

    def normalize(result: list) -> dict:
        rows = []
        for item in result or []:
            rows.append({
                "keyword": item.get("keyword"),
                "search_volume": item.get("search_volume"),
                "competition": item.get("competition"),
                "cpc": item.get("cpc"),
                "low_top_of_page_bid": item.get("low_top_of_page_bid"),
            })
        rows.sort(key=lambda r: (r["search_volume"] or 0), reverse=True)
        return {
            "location": location_name,
            "requested": len(keywords),
            "returned": len(rows),
            "with_volume": sum(1 for r in rows if (r["search_volume"] or 0) > 0),
            "keywords": rows,
        }

    return _fetch(
        client, kind="keyword_volume", budget_key="keywords",
        endpoint="/v3/keywords_data/google_ads/search_volume/live",
        payload=[{"keywords": keywords, "location_name": location_name,
                  "language_code": "en"}],
        query=f"keyword_volume:{len(keywords)}", normalize=normalize, raw_dir=raw_dir,
    )


def write_evidence(evidence: QueryEvidence, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{evidence.evidence_id}.json"
    path.write_text(canonical_json(evidence.to_dict()), encoding="utf-8")
    return path


def load_evidence(path: Path):
    from .contracts import from_dict
    return from_dict("QueryEvidence", json.loads(path.read_text(encoding="utf-8")))
