"""Build the court register (justiceflow/courts.csv) from the Judiciary's public court map.

    python -m justiceflow.build_courts                 # rebuild from the saved snapshot
    python -m justiceflow.build_courts --fetch         # refresh the snapshot first

SOURCE: Judiciary of Tanzania court map (jmap.judiciary.go.tz), whose public data
service lists every court with its region, district and ward. The snapshot used is
saved in data/courts/. The map is incomplete in places, so a few courts are added from
the legal instruments that establish them (each row says which):
  * Court of Appeal registries: Tanzania Court of Appeal (Sub-registries) Order, GN 579 of
    2020, plus the main registry in Dar es Salaam;
  * Lindi region's High Court cases go to the Mtwara sub-registry: High Court Registries
    (Amendment) Rules 2023, GN 853A;
  * a Resident Magistrate's Court in every region: Magistrates' Courts Act schedule (the
    map lists none for Dodoma).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

API = "https://datahub.judiciary.go.tz:5050/jmap-connect/api/v1"
ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "courts" / "jmap_courts_snapshot.json"
OUT = Path(__file__).resolve().parent / "courts.csv"

# The regions modelled, and the region whose High Court / Court of Appeal serves each.
REGIONS = ["Dar es Salaam", "Arusha", "Mwanza", "Dodoma", "Kigoma", "Rukwa", "Lindi"]
SERVED_BY = {"Lindi": "Mtwara"}  # GN 853A of 2023; GN 579 of 2020

LEVEL_CODE = {"Primary": "PC", "District": "DC", "Resident Magistrate": "RM", "High Court": "HC",
              "Court of Appeal": "CA"}
DIVISIONS = {"Land": "Land", "Labour": "Labour", "Commercial": "Commercial",
             "Corruption and Economic Crimes": "Economic"}

# Courts the map does not list, from the instruments named above.
ADDED = [
    ("Dar es Salaam", "Ilala", "Court of Appeal", "Court of Appeal, Dar es Salaam (Main Registry)", "",
     "Appellate Jurisdiction Act; main registry"),
    ("Arusha", "Arusha", "Court of Appeal", "Arusha Court of Appeal", "", "GN 579 of 2020"),
    ("Kigoma", "Kigoma", "Court of Appeal", "Kigoma Court of Appeal", "", "GN 579 of 2020"),
    ("Rukwa", "Sumbawanga", "Court of Appeal", "Sumbawanga Court of Appeal", "", "GN 579 of 2020"),
    ("Lindi", "Mtwara", "Court of Appeal", "Mtwara Court of Appeal", "", "GN 579 of 2020"),
    ("Dodoma", "Dodoma", "Resident Magistrate", "Dodoma Resident Magistrate's Court", "",
     "Magistrates' Courts Act schedule (not on the court map)"),
]


def _level(name: str) -> str | None:
    n = name.lower()
    if "court of appeal" in n:
        return "Court of Appeal"
    if "high court" in n:
        return "High Court"
    if "resident magistrate" in n:
        return "Resident Magistrate"
    if "district court" in n:
        return "District"
    if "primar" in n:  # one entry is spelled "Primar Court"
        return "Primary"
    return None


def _clean(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\bPrimar Court\b", "Primary Court", name)
    name = re.sub(r"\bprimary Court\b", "Primary Court", name)
    if name.endswith("Resident Magistrate"):
        name += "'s Court"
    return name


def _division(name: str) -> str:
    for label, case_type in DIVISIONS.items():
        if label.lower() in name.lower():
            return case_type
    return ""


def fetch() -> dict:
    import urllib.request
    regions = json.load(urllib.request.urlopen(f"{API}/master-data/location/region/get-regions", timeout=60))["data"]
    ids = {r["name"]: r["id"] for r in regions}
    out = {}
    for name in REGIONS + sorted(set(SERVED_BY.values())):
        body = json.dumps({"id": "", "regionId": ids[name], "districtId": ""}).encode()
        req = urllib.request.Request(f"{API}/court/search-courts", data=body, headers={"Content-Type": "application/json"})
        out[name] = json.load(urllib.request.urlopen(req, timeout=60))["courts"]["rows"]
        time.sleep(1)  # be gentle with a public service
    snapshot = {"source": "Judiciary of Tanzania court map (jmap.judiciary.go.tz), public data service",
                "fetched": time.strftime("%Y-%m-%d"), "regions": out}
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
    return snapshot


def build(snapshot: dict) -> list[dict]:
    rows, seen = [], set()

    def add(region, district, level, name, division, source):
        key = (region, level, name)
        if key not in seen:
            seen.add(key)
            rows.append({"region": region, "district": district, "court_level": level, "court_name": name,
                         "division": division, "source": source})

    for region in REGIONS:
        for r in snapshot["regions"][region]:
            name, level = _clean(r["cfg_court"]["name"]), _level(r["cfg_court"]["name"])
            if level is None or (level in {"High Court", "Court of Appeal"} and region in SERVED_BY):
                continue
            add(region, (r.get("cfg_district") or {}).get("name", ""), level, name,
                _division(name) if level == "High Court" else "", "Judiciary court map")
        # High Court / Court of Appeal from the registry that serves this region.
        if region in SERVED_BY:
            for r in snapshot["regions"][SERVED_BY[region]]:
                name, level = _clean(r["cfg_court"]["name"]), _level(r["cfg_court"]["name"])
                if level in {"High Court", "Court of Appeal"}:
                    add(region, (r.get("cfg_district") or {}).get("name", ""), level, name, _division(name),
                        "Judiciary court map; GN 853A of 2023 (Mtwara sub-registry serves Lindi)")
    for row in ADDED:
        add(*row)

    # Short, stable codes for case numbers and bench IDs, e.g. PC-KARIAKOO, DC-ILALA.
    used = set()
    for r in rows:
        stem = re.sub(r"\b(Primary|District|High|Court|of|Appeal|Resident|Magistrate's|Division|Zone|Urban|At|One|Stop|Centre|Main|Registry|Commercial|Labour|Land|Corruption|and|Economic|Crimes)\b",
                      "", r["court_name"], flags=re.I)
        stem = re.sub(r"[^A-Za-z]", "", stem).upper()[:8] or "COURT"
        code = f"{LEVEL_CODE[r['court_level']]}-{stem}"
        if r["division"]:
            code += "-" + r["division"][:3].upper()
        base, n = code, 2
        while code in used:
            code, n = f"{base}{n}", n + 1
        used.add(code)
        r["code"] = code
    order = {lv: i for i, lv in enumerate(LEVEL_CODE)}
    rows.sort(key=lambda r: (REGIONS.index(r["region"]), order[r["court_level"]], r["district"], r["court_name"]))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true", help="refresh the snapshot from the court map first")
    a = ap.parse_args()
    snapshot = fetch() if a.fetch else json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    rows = build(snapshot)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["code", "region", "district", "court_level", "court_name", "division", "source"])
        w.writeheader()
        w.writerows(rows)
    by = {}
    for r in rows:
        by[r["court_level"]] = by.get(r["court_level"], 0) + 1
    print(f"{len(rows)} courts written to {OUT}: {by}")


if __name__ == "__main__":
    main()
