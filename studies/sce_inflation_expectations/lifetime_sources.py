"""Archive public ALFRED vintages and neutral history sources; no LLM or keys."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re

import requests

MONTHS = ("202203", "202209", "202303", "202403")
ESSAYS = {
    "great_inflation": "https://www.federalreservehistory.org/essays/great-inflation",
    "recession_1981_82": "https://www.federalreservehistory.org/essays/recession-of-1981-82",
    "great_recession": "https://www.federalreservehistory.org/essays/great-recession-of-200709",
}
EVENTS = [
    {"id": "great_inflation", "start_year": 1965, "end_year": 1982,
     "source_id": "great_inflation", "fact": "U.S. inflation rose substantially during the late 1960s and 1970s, then declined in the early 1980s."},
    {"id": "tightening_1981_82", "start_year": 1981, "end_year": 1982,
     "source_id": "recession_1981_82", "fact": "The Federal Reserve maintained tight monetary policy in 1981-1982; inflation fell and the U.S. economy experienced a recession."},
    {"id": "crisis_2007_09", "start_year": 2007, "end_year": 2009,
     "source_id": "great_recession", "fact": "During the 2007-2009 recession, the Federal Reserve reduced its policy rate to a 0-0.25% target range in December 2008."},
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def fetch(root, dest):
    root, dest = Path(root).resolve(), Path(dest).resolve()
    if dest.exists() or not dest.is_relative_to(root / "data/raw/lifetime_experience"):
        raise ValueError("fresh lifetime raw directory required")
    plan_path = root / "outputs/sce_confidence_trial_20261011_v1/trial_manifest.json"
    plan = json.loads(plan_path.read_text())
    dest.mkdir(parents=True)
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(),
                "plan_sha256": sha(plan_path), "series": "CPIAUCNS",
                "units": "Index 1982-1984=100", "seasonal_adjustment": "NSA",
                "downloads": [], "vintages": {}, "events": EVENTS,
                "paid_api_calls": 0, "simulation_calls": 0,
                "bls_direct_download_attempts": "Catalog and 202202 XLSX/PDF returned HTTP 403; no substitute bytes accepted."}
    def get(url, name):
        record = {"url": url, "file": str((dest / name).relative_to(root)),
                  "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        response = requests.get(url, timeout=30)
        record.update(status_code=response.status_code, content_type=response.headers.get("content-type"))
        manifest["downloads"].append(record)
        dump(dest / "manifest.json", manifest)
        response.raise_for_status()
        (dest / name).write_bytes(response.content)
        record.update(sha256=sha(dest / name), bytes=len(response.content))
        return response
    # Metadata is archived independently of numerical response headers.
    get("https://alfred.stlouisfed.org/series?seid=CPIAUCNS", "alfred_series.html")
    for month in MONTHS:
        cutoff = plan["metadata"][month]["as_of"]
        date = cutoff[:10]
        url = "https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=CPIAUCNS&vintage_date=" + date
        response = get(url, "cpi_nsa_vintage_" + date + ".csv")
        reader = csv.DictReader(io.StringIO(response.text))
        column = "CPIAUCNS_" + date.replace("-", "")
        if reader.fieldnames != ["observation_date", column]:
            raise ValueError("requested vintage not echoed in CSV header")
        rows = list(reader)
        observed = [row for row in rows if row[column] not in ("", ".")]
        if not observed or max(row["observation_date"] for row in observed) >= date:
            raise ValueError("future observation in vintage response")
        manifest["vintages"][month] = {"as_of": cutoff, "requested_vintage_date": date,
            "response_column": column, "file": str((dest / ("cpi_nsa_vintage_" + date + ".csv")).relative_to(root)),
            "sha256": sha(dest / ("cpi_nsa_vintage_" + date + ".csv")),
            "observed_rows": len(observed), "first_observation": observed[0]["observation_date"],
            "last_observation": observed[-1]["observation_date"],
            "version_evidence": "ALFRED requested vintage echoed in response header; BLS release cross-check performed separately"}
        dump(dest / "manifest.json", manifest)
    # Negative boundary probe: day before the first CPI release cutoff.
    date = "2022-03-09"
    response = get("https://alfred.stlouisfed.org/graph/alfredgraph.csv?id=CPIAUCNS&vintage_date=" + date,
                   "cpi_nsa_boundary_2022-03-09.csv")
    reader = csv.DictReader(io.StringIO(response.text))
    if reader.fieldnames != ["observation_date", "CPIAUCNS_20220309"]:
        raise ValueError("boundary vintage not echoed")
    observed = [r for r in reader if r["CPIAUCNS_20220309"] not in ("", ".")]
    manifest["boundary_probe"] = {"requested_vintage_date": date,
        "last_observation": max(r["observation_date"] for r in observed)}
    for source_id, url in ESSAYS.items():
        response = get(url, source_id + ".html")
        # Page-level written-as-of is not proof of unchanged historical bytes.
        plain = re.sub(r"<[^>]*>", " ", response.text)
        match = re.search(r"Written as of\s+November\s+22,\s+2013", plain)
        if not match:
            raise ValueError("history essay date must be reviewed")
        manifest.setdefault("history_sources", {})[source_id] = {
            "url": url, "file": str((dest / (source_id + ".html")).relative_to(root)),
            "sha256": sha(dest / (source_id + ".html")), "written_as_of": "2013-11-22",
            "evidence_class": "retrospective_essay_current_bytes", "strict_B_byte_vintage_verified": False}
        dump(dest / "manifest.json", manifest)
    manifest["status"] = "downloaded_for_offline_source_validation"
    manifest["code_sha256"] = sha(__file__)
    dump(dest / "manifest.json", manifest)
    print(json.dumps({"vintages": len(manifest["vintages"]), "boundary_probe": manifest["boundary_probe"],
                      "history_sources": len(manifest["history_sources"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fetch", action="store_true", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    fetch(Path(__file__).resolve().parents[2], args.out)
