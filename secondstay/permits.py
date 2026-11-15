"""Building permits from the City of Los Angeles open data portal, matched by parcel number.

LADBS publishes every building, mechanical and electrical permit since the 1990s on
data.lacity.org (Socrata), with the assessor parcel number (APN), the permit type and a
free-text work description. CoStar holds the APN of each building, so the two join exactly.

What we read from them, per building:

- which fire and life-safety systems have been permitted (sprinklers, fire alarm, standpipe,
  fire pump, emergency generator, smoke control), and elevators, stairs and seismic work
- on which floor or suite the work was done, read from the description
  ("SUITE 820", "15TH FLOOR", "2ND FLR THRU 7TH FLR")
- which stairs the permits name ("STAIR #1-2 AND #3")
- how many stories the permits say the building has ("EXISTING 16 STORY HIGH RISE")

Permits record work that was filed, not what is installed today. Every use says so.
Records are cached under data/raw/permits/, which is git-ignored.
"""

import json
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = REPO_ROOT / "data" / "raw" / "permits"
PORTAL = "https://data.lacity.org/resource/{}.json"
PORTAL_PAGE = "https://data.lacity.org/d/{}"

# LADBS permit datasets: (kind, period, dataset id). "Issued" datasets, so every record was issued.
DATASETS = [
    ("Building", "before 2010", "e67z-kt2n"),
    ("Building", "2010 to 2019", "dyxf-7hc4"),
    ("Building", "2020 to now", "pi9x-tg5x"),
    ("Mechanical", "before 2010", "mcip-sa6g"),
    ("Mechanical", "2010 to 2019", "5m3t-xjex"),
    ("Mechanical", "2020 to now", "67is-svtd"),
    ("Electrical", "before 2010", "h8me-eag6"),
    ("Electrical", "2010 to 2019", "yaaf-cyfa"),
    ("Electrical", "2020 to now", "ysqd-apz7"),
]

# Topic -> (label, pattern on the work description, permit type that always counts)
TOPICS = {
    "sprinklers": ("Fire sprinklers", r"SPRINKL|NFPA ?13\b", "FIRE SPRINKLER"),
    "alarm": ("Fire alarm", r"FIRE ?ALARM|\bFA SYSTEM|\bFACP\b|NFPA ?72|SMOKE DETECT|STROBE|PULL STATION", None),
    "standpipe": ("Standpipe", r"STANDPIPE", None),
    "fire_pump": ("Fire pump", r"FIRE PUMP", None),
    "generator": ("Emergency generator", r"GENERATOR", None),
    "smoke_control": ("Smoke control", r"SMOKE ?CONTROL|PRESSURI[SZ]", None),
    "stairs": ("Stairs", r"\bSTAIR", None),
    "elevator": ("Elevators", r"ELEVATOR", "ELEVATOR"),
    "seismic": ("Seismic work", r"SEISMIC|SOFT[- ]?STORY|NON[- ]?DUCTILE|EARTHQUAKE (?!VALVE)|STRUCTURAL RETROFIT", None),
    "change_of_use": ("Change of use", r"CHANGE (OF )?(USE|OCC)|ADAPTIVE REUSE", None),
}

ORDINAL_WORDS = {
    "GROUND": 1, "FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5, "SIXTH": 6, "SEVENTH": 7,
    "EIGHTH": 8, "NINTH": 9, "TENTH": 10, "ELEVENTH": 11, "TWELFTH": 12,
}
FLOOR_WORD = r"(?:FLOORS?|FLRS?|FL)\b\.?"
NUMBER_WORDS = {"TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6}


def apn_key(parcel: str) -> str:
    """CoStar writes APNs as 1234-567-890; the city portal as 1234567890."""
    return re.sub(r"\D", "", parcel or "")


# --- reading one description ------------------------------------------------------------------

def topics_of(record: dict) -> set:
    text = (record.get("work") or "").upper()
    kind = (record.get("type") or "").upper()
    return {
        key for key, (_, pattern, permit_type) in TOPICS.items()
        if re.search(pattern, text) or (permit_type and kind == permit_type)
    }


def floors_named(text: str, stories: Optional[int]) -> set:
    """Floors a work description names. Floors above the building's height are dropped."""
    text = (text or "").upper()
    found = set()
    for a, b in re.findall(
        r"(\d{1,3})(?:ST|ND|RD|TH)?\s*" + FLOOR_WORD + r"?\s*(?:-|THRU|THROUGH|TO)\s*(\d{1,3})(?:ST|ND|RD|TH)?\s*" + FLOOR_WORD, text
    ):
        lo, hi = int(a), int(b)
        if 0 < lo <= hi <= 150:
            found.update(range(lo, hi + 1))
    for a, b in re.findall(r"\b(?:FLOORS?|FLRS?|LEVELS?)\s*#?\s*(\d{1,3})(?:\s*(?:-|THRU|THROUGH|TO)\s*(\d{1,3}))?", text):
        lo = int(a)
        hi = int(b) if b else lo
        if 0 < lo <= hi <= 150:
            found.update(range(lo, hi + 1))
    for n in re.findall(r"\b(\d{1,3})(?:ST|ND|RD|TH)\s*" + FLOOR_WORD, text):
        found.add(int(n))
    for word, n in ORDINAL_WORDS.items():
        if re.search(rf"\b{word}\s+{FLOOR_WORD}", text):
            found.add(n)
    for suite in re.findall(r"\b(?:SUITES?|STE)\.?\s*#?\s*([A-Z]?\d{3,5})[A-Z]?\b", text):
        digits = re.sub(r"\D", "", suite)
        if len(digits) >= 3:
            found.add(int(digits[:-2]))
    return {f for f in found if f >= 1 and (not stories or f <= stories)}


def suites_named(text: str) -> set:
    return {s.lstrip("0") for s in re.findall(r"\b(?:SUITES?|STE)\.?\s*#?\s*([A-Z]?\d{2,5}[A-Z]?)\b", (text or "").upper())}


def stairs_named(text: str) -> set:
    """Stair labels a description names: "STAIR #1-2 AND #3" -> {"1", "2", "3"}; "STAIR B" -> {"B"}."""
    text = (text or "").upper()
    labels = set()
    for tail in re.findall(r"STAIR(?:WAY|WELL)?S?\b(?=([^.;:]{0,30}))", text):  # overlapping: every mention
        head = tail
        for a, b in re.findall(r"(?:#|NO\.?)\s*(\d{1,2})(?:\s*-\s*(\d{1,2}))?", head):
            lo, hi = int(a), int(b) if b else int(a)
            if 0 < lo <= hi <= 8:
                labels.update(str(n) for n in range(lo, hi + 1))
        letter = re.match(r"\s+([A-F])\b", tail)
        if letter:
            labels.add(letter.group(1))
    return labels


def stories_named(text: str) -> Optional[int]:
    found = [int(n) for n in re.findall(r"\b(\d{1,3})[- ]STOR(?:Y|IES)\b", (text or "").upper()) if 0 < int(n) <= 120]
    return max(found) if found else None


# --- fetching ---------------------------------------------------------------------------------

def _query(dataset: str, where: str) -> list:
    url = PORTAL.format(dataset) + "?" + urllib.parse.urlencode({"$where": where, "$limit": 50000})
    request = urllib.request.Request(url, headers={"User-Agent": "secondstay-precheck"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def _compact(row: dict, kind: str, period: str, dataset: str) -> dict:
    return {
        "number": row.get("permit_nbr") or "",
        "kind": kind,
        "type": row.get("permit_type") or "",
        "subtype": row.get("permit_sub_type") or "",
        "issued": (row.get("issue_date") or "")[:10],
        "status": row.get("status_desc") or "",
        "work": (row.get("work_desc") or "").strip(),
        "valuation": row.get("valuation"),
        "apn": row.get("apn") or "",
        "dataset": dataset,
        "period": period,
    }


def fetch_all(buildings: list, batch: int = 60) -> dict:
    """Permits for every building, by property id, in one pass over the nine datasets."""
    owner = {apn_key(p): b.property_id for b in buildings for p in b.parcel_numbers if apn_key(p)}
    keys = sorted(owner)

    def one(entry):
        kind, period, dataset = entry
        rows = []
        for i in range(0, len(keys), batch):
            where = "apn in (" + ",".join(f"'{k}'" for k in keys[i:i + batch]) + ")"
            rows += [_compact(r, kind, period, dataset) for r in _query(dataset, where)]
        return rows

    by_building = defaultdict(list)
    with ThreadPoolExecutor(max_workers=5) as pool:
        for rows in pool.map(one, DATASETS):
            for row in rows:
                if row["apn"] in owner:
                    by_building[owner[row["apn"]]].append(row)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    for b in buildings:
        if b.parcel_numbers:
            (CACHE_DIR / f"{b.property_id}.json").write_text(json.dumps(by_building.get(b.property_id, [])))
    return dict(by_building)


def cached(property_id) -> Optional[list]:
    path = CACHE_DIR / f"{property_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


# --- what the permits say about one building ---------------------------------------------------

def summarize(records: list, stories: Optional[int]) -> dict:
    """Per topic: how many permits, first and latest year, floors and suites named, and examples."""
    topics = {}
    stair_labels = set()
    story_counts = []
    for r in records:
        text = r.get("work") or ""
        stair_labels |= stairs_named(text)
        named = stories_named(text)
        if named:
            story_counts.append(named)
        for key in topics_of(r):
            t = topics.setdefault(key, {"label": TOPICS[key][0], "count": 0, "years": [], "floors": defaultdict(int),
                                         "suites": set(), "records": []})
            t["count"] += 1
            if r.get("issued"):
                t["years"].append(r["issued"][:4])
            for f in floors_named(text, stories):
                t["floors"][f] += 1
            t["suites"] |= suites_named(text)
            t["records"].append(r)
    out = {}
    for key, t in topics.items():
        recs = sorted(t["records"], key=lambda r: r.get("issued") or "", reverse=True)
        out[key] = {
            "label": t["label"],
            "count": t["count"],
            "first": min(t["years"]) if t["years"] else None,
            "latest": recs[0].get("issued") if recs else None,
            "floors": {str(f): n for f, n in sorted(t["floors"].items())},
            "suites": sorted(t["suites"]),
            "records": [
                {k: r.get(k) for k in ("number", "kind", "type", "issued", "status", "work", "dataset")}
                for r in recs[:40]
            ],
        }
    return {
        "total": len(records),
        "topics": out,
        "stairs_named": sorted(stair_labels, key=lambda s: (not s.isdigit(), s)),
        "stories_named": max(story_counts) if story_counts else None,
        "datasets": sorted({r.get("dataset") for r in records if r.get("dataset")}),
    }


def on_floor(summary: dict, topic: str, floor: Optional[int]) -> int:
    t = (summary or {}).get("topics", {}).get(topic)
    return t["floors"].get(str(floor), 0) if t and floor else 0


def in_suite(summary: dict, topic: str, suite: str) -> bool:
    t = (summary or {}).get("topics", {}).get(topic)
    return bool(t and suite and suite.lstrip("0").upper() in t["suites"])
