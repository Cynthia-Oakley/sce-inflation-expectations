"""Download public theory/context sources and retry BLS; no key or model API."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import requests

from .lifetime_sources import dump, sha

SOURCES = {
    "selective_memory_20240624.pdf": "https://shleifer.scholars.harvard.edu/sites/g/files/omnuum10626/files/shleifer/files/inflation_june24-1.pdf",
    "consumer_socialization_1999.pdf": "https://www.sfu.ca/media-lab/cmns320_06/readings/roedder_john_consumer_socialization.pdf",
    "public_event_memory_2016.html": "https://pubmed.ncbi.nlm.nih.gov/25529327/",
    "great_moderation.html": "https://www.federalreservehistory.org/essays/great-moderation",
    "treasury_fed_accord.html": "https://www.federalreservehistory.org/essays/treasury-fed-accord",
    "fomc_goal_20120125.html": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20120125c.htm",
    "fomc_pandemic_20211215.html": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20211215a.htm",
}
BLS_RETRY = {
    "bls_catalogue.html": "https://www.bls.gov/cpi/tables/supplemental-files/home.htm",
    "historical_cpi_u_202202.xlsx": "https://www.bls.gov/cpi/tables/supplemental-files/historical-cpi-u-202202.xlsx",
    "historical_cpi_u_202202.pdf": "https://www.bls.gov/cpi/tables/supplemental-files/historical-cpi-u-202202.pdf",
}


def fetch(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(root/"data/raw/lifetime_episodes"):
        raise ValueError("fresh source directory required")
    out.mkdir(parents=True)
    manifest = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "downloads": [],
                "new_llm_calls": 0, "paid_mcp_calls": 0, "VPN_settings_changed": False,
                "status": "downloading_public_sources"}
    for name, url in {**BLS_RETRY, **SOURCES}.items():
        row = {"url": url, "filename": name, "retrieved_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=25)
            row.update(http_status=response.status_code, content_type=response.headers.get("content-type"))
            valid = response.status_code == 200
            if name.endswith(".pdf"):
                valid = valid and response.content.startswith(b"%PDF-")
            if name.endswith(".xlsx"):
                valid = valid and response.content.startswith(b"PK")
            row["accepted_file"] = valid
            if valid:
                path = out/name
                path.write_bytes(response.content)
                row.update(file=str(path.relative_to(root)), sha256=sha(path), bytes=len(response.content))
        except requests.RequestException as exc:
            row.update(accepted_file=False, error_type=type(exc).__name__)
        manifest["downloads"].append(row)
        dump(out/"manifest.json", manifest)
        print(json.dumps({"source": name, "status": row.get("http_status", row.get("error_type")), "accepted": row["accepted_file"]}), flush=True)
    manifest["status"] = "download_attempts_complete"
    manifest["code_sha256"] = sha(__file__)
    dump(out/"manifest.json", manifest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    fetch(Path(__file__).resolve().parents[2], args.out)
