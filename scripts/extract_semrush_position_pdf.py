#!/usr/bin/env python3
"""Extract the fixed-layout keyword table from a Semrush Position Tracking PDF.

Semrush's PDF export renders the keyword table as selectable text.  Ghostscript's
``txtwrite`` device preserves the column layout well enough to recover the 479
rows without consuming Semrush API units.  The script validates the recovered
FMD distribution against the summary printed in the same PDF.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROW_RE = re.compile(r"^ {8}(\d+)\.\s+(.*)$")
SKIP_PREFIXES = (
    "Generated on ",
    "Keyword Rankings",
    "Keyword",
    "Domain",
    "Rankings in ",
)

DOMAINS = {
    "fmd": "freshmobiledetail.com",
    "nathans": "nathansdetailing.com",
    "refresh": "refreshmobiledetailingcle.com",
    "atf": "allthingsfreshcardetailing.com",
    "rhino": "rhinomobiledetailing.com",
}

SUBURBS = (
    "mayfield heights", "beachwood", "solon", "pepper pike",
    "moreland hills", "chagrin falls", "shaker heights",
    "university heights", "highland heights", "lyndhurst", "gates mills",
    "orange village", "cleveland heights", "south euclid",
    "richmond heights", "mentor", "willoughby", "hudson", "twinsburg",
    "aurora", "streetsboro", "bedford", "warrensville", "euclid",
)

SERVICE_TERMS = (
    "detail", "car wash", "interior clean", "car clean", "vehicle clean",
    "ceramic", "paint correction", "odor", "pet hair", "seat shampoo",
    "headlight", "wax", "polish", "scratch", "stain", "rust proof",
)

INFO_PREFIXES = (
    "how ", "what ", "why ", "when ", "where ", "which ", "can ",
    "does ", "do ", "is ", "are ", "should ", "tips ",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_text(pdf: Path, output: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE",
            "-sDEVICE=txtwrite", f"-sOutputFile={output}", str(pdf),
        ],
        check=True,
    )
    text = output.read_text(encoding="utf-8", errors="replace")
    # In this export Ghostscript maps both the green plus glyph and red minus
    # glyph to NUL. Preserve that fact explicitly; never guess the direction.
    text = text.replace("\x00", "±").replace("\r", "")
    output.write_text(text, encoding="utf-8")
    return text


def _number(value: str, *, integer: bool = False):
    value = value.strip().replace(",", "")
    if not value or value in {"-", "n/a"}:
        return None
    try:
        return int(value) if integer else float(value)
    except ValueError:
        return None


def _change(value: str) -> tuple[int | None, str | None]:
    value = value.strip()
    if not value:
        return None, None
    if value == "0":
        return 0, "unchanged"
    if value.startswith("±"):
        return _number(value[1:], integer=True), "sign_not_preserved_by_text_extraction"
    parsed = _number(value, integer=True)
    if parsed is None:
        return None, None
    return abs(parsed), "improved" if parsed > 0 else "declined"


def _pair(segment: str) -> tuple[int | None, int | None, str | None]:
    values = segment.split()
    if not values or values == ["-"]:
        return None, None, None
    # Semrush can leave the current-position cell empty and print only a change
    # magnitude when a domain fell out of the top 100.
    if len(values) == 1 and values[0].startswith("±"):
        magnitude, direction = _change(values[0])
        return None, magnitude, direction
    position = _number(values[0], integer=True)
    magnitude, direction = _change(values[1]) if len(values) > 1 else (None, None)
    return position, magnitude, direction


def _parse_values(line: str, index: int) -> dict:
    # The first PDF table page is ten characters narrower than the remaining
    # pages.  Semrush repeats the wider header after that first page.
    if index <= 2:
        zones = {
            "kd": (42, 49), "fmd": (49, 68), "nathans": (68, 89),
            "refresh": (89, 108), "atf": (108, 130), "rhino": (130, 147),
            "cpc": (147, 158), "volume": (158, None),
        }
    else:
        zones = {
            "kd": (44, 53), "fmd": (53, 72), "nathans": (72, 92),
            "refresh": (92, 114), "atf": (114, 136), "rhino": (136, 155),
            "cpc": (155, 166), "volume": (166, None),
        }

    data: dict[str, object] = {
        "kd_percent": _number(line[slice(*zones["kd"])], integer=True),
        "cpc_usd": _number(line[slice(*zones["cpc"])]),
        "volume": _number(line[slice(*zones["volume"])], integer=True),
    }
    for key in DOMAINS:
        if key == "fmd" or key in {"nathans", "refresh", "atf", "rhino"}:
            position, magnitude, direction = _pair(line[slice(*zones[key])])
            data[f"{key}_position"] = position
            data[f"{key}_change_magnitude"] = magnitude
            data[f"{key}_change_direction"] = direction
    return data


def parse_rows(text: str) -> list[dict]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if "Keyword Rankings" in line)
    rows: list[dict] = []
    current: dict | None = None

    for line in lines[start + 1:]:
        match = ROW_RE.match(line)
        if match:
            index = int(match.group(1))
            metric_start = 42 if index <= 2 else 44
            keyword = re.sub(r"^\d+\.\s*", "", line[8:metric_start]).strip()
            current = {"campaign_row": index, "keyword": keyword}
            current.update(_parse_values(line, index))
            rows.append(current)
            continue

        if current is None or not line.startswith("        "):
            continue
        # Wrapped keywords begin exactly in the left keyword column. Repeated
        # page headers begin farther right and must never be appended.
        if len(line) <= 8 or line[8].isspace():
            continue
        value = line[8:].strip()
        if not value or value.startswith(SKIP_PREFIXES):
            continue
        if "SEMRUSH.COM" in value or "BOYLSTON STREET" in value:
            continue
        if any(domain.split(".")[0] in value for domain in DOMAINS.values()):
            continue
        if value in {"SERP", "Features", "%", "CPC Volume", "19 Jul"}:
            continue
        # Continuation lines contain only the wrapped keyword text.  Page
        # headers and table labels have already been excluded above.
        current["keyword"] = f"{current['keyword']} {value}".strip()

    expected = list(range(1, 480))
    observed = [row["campaign_row"] for row in rows]
    if observed != expected:
        missing = sorted(set(expected) - set(observed))
        duplicates = sorted({value for value in observed if observed.count(value) > 1})
        raise RuntimeError(
            f"expected campaign rows 1..479; got {len(rows)} rows; "
            f"missing={missing[:10]} duplicates={duplicates[:10]}"
        )
    return rows


def classify(keyword: str) -> dict[str, bool]:
    value = keyword.casefold()
    branded = value.startswith("fresh ") or "fresh mobile" in value
    near_me = bool(re.search(r"\bnear me\b|\bnearby\b|\bin my area\b|\baround me\b", value))
    cleveland = "cleveland" in value
    suburb = any(term in value for term in SUBURBS)
    service = any(term in value for term in SERVICE_TERMS)
    informational = (
        value.startswith(INFO_PREFIXES)
        or any(term in value for term in (" cost", " price", " prices", "best ", " vs ", "how much"))
    )
    return {
        "branded": branded,
        "non_branded": not branded,
        "near_me": near_me,
        "cleveland": cleveland,
        "suburb": suburb,
        "service": service,
        "informational": informational,
    }


def _rank_counts(rows: list[dict], field: str) -> dict:
    positions = [row[field] for row in rows if row[field] is not None]
    return {
        "top_3": sum(position <= 3 for position in positions),
        "top_10": sum(position <= 10 for position in positions),
        "top_20": sum(position <= 20 for position in positions),
        "top_100": sum(position <= 100 for position in positions),
        "unranked": len(rows) - len(positions),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--requested-keywords", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    text_path = args.output_dir / "position-tracking-extracted.txt"
    text = extract_text(args.pdf, text_path)
    rows = parse_rows(text)
    for row in rows:
        row.update(classify(row["keyword"]))

    requested: set[str] | None = None
    if args.requested_keywords:
        requested = {
            line.strip().casefold()
            for line in args.requested_keywords.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        for row in rows:
            row["in_requested_467"] = row["keyword"].casefold() in requested

    csv_path = args.output_dir / "position-tracking-keywords.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    campaign_keywords = {row["keyword"].casefold() for row in rows}
    summary = {
        "source": {
            "file_name": args.pdf.name,
            "sha256": _sha256(args.pdf),
            "generated_date": "2026-07-19",
            "tracking_target": "freshmobiledetail.com",
            "device": "desktop",
            "location": "United States",
            "volume_type": "National",
            "report_type": "Organic",
            "period": "2026-07-14 through 2026-07-19",
            "local_pack_enabled": True,
        },
        "campaign_rows": len(rows),
        "unique_campaign_keywords": len(campaign_keywords),
        "requested_keyword_rows": len(requested) if requested is not None else None,
        "requested_matches": (
            sum(row.get("in_requested_467", False) for row in rows)
            if requested is not None else None
        ),
        "requested_missing": (
            sorted(requested - campaign_keywords) if requested is not None else []
        ),
        "campaign_not_in_requested": (
            sorted(campaign_keywords - requested) if requested is not None else []
        ),
        "rank_counts": {
            key: _rank_counts(rows, f"{key}_position") for key in DOMAINS
        },
        "cuts": {
            cut: {
                "keywords": sum(bool(row[cut]) for row in rows),
                "fmd_ranked": sum(bool(row[cut]) and row["fmd_position"] is not None for row in rows),
            }
            for cut in (
                "branded", "non_branded", "near_me", "cleveland",
                "suburb", "service", "informational",
            )
        },
        "fmd_ranked_keywords": [
            {
                "keyword": row["keyword"],
                "position": row["fmd_position"],
                "change_magnitude": row["fmd_change_magnitude"],
                "change_direction": row["fmd_change_direction"],
            }
            for row in rows if row["fmd_position"] is not None
        ],
        "data_quality": {
            "validated_against_pdf_top_counts": _rank_counts(rows, "fmd_position") == {
                "top_3": 0, "top_10": 0, "top_20": 2, "top_100": 17,
                "unranked": 462,
            },
            "diamond_finish_row_positions_available": False,
            "landing_pages_available_in_pdf": False,
            "placement_type_available_in_extracted_text": False,
            "change_sign_available_in_extracted_text": False,
        },
    }
    (args.output_dir / "position-tracking-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "rows": len(rows),
        "csv": str(csv_path),
        "summary": str(args.output_dir / "position-tracking-summary.json"),
        "fmd": summary["rank_counts"]["fmd"],
        "validated": summary["data_quality"]["validated_against_pdf_top_counts"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
