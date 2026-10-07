#!/usr/bin/env python3
"""Archive missing weekly FRED GASREGW history separately; preserve original cache.

This downloads a current snapshot, not a certified historical vintage. Dates in
the series are observation dates and do not establish publication timestamps.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
from datetime import date, datetime, timezone
from pathlib import Path

import extend_sce_environment_sources as sources


def parse_snapshot(payload: bytes, start: str, end: str) -> dict[str, float]:
    rows = {}
    reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig")))
    if reader.fieldnames != ["observation_date", "GASREGW"]:
        raise ValueError("unexpected GASREGW CSV schema")
    for row in reader:
        day = date.fromisoformat(row["observation_date"]).isoformat()
        if not start <= day <= end or day in rows:
            raise ValueError("duplicate or out-of-request observation date")
        if row["GASREGW"] in ("", "."):
            continue
        value = float(row["GASREGW"])
        if not 0 < value < 20:
            raise ValueError("invalid gasoline price")
        rows[day] = value
    if not rows:
        raise ValueError("no valid GASREGW observations")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--proxy", default="")
    ap.add_argument("--response-csv", type=Path,
                    help="optional already-downloaded FRED response for offline consolidation")
    ap.add_argument("--base", type=Path, default=sources.ev.GAS_WEEKLY_CSV)
    args = ap.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    if start > end:
        raise ValueError("start after end")
    url = ("https://fred.stlouisfed.org/graph/fredgraph.csv?id=GASREGW"
           f"&cosd={start}&coed={end}")
    payload = (args.response_csv.read_bytes() if args.response_csv
               else sources.download_bytes(url, args.proxy))
    support = parse_snapshot(payload, str(start), str(end))
    with args.base.open() as handle:
        base = {r["observation_date"]: float(r["gasoline_retail_regular"])
                for r in csv.DictReader(handle)}
    for day, value in support.items():
        if day in base and abs(base[day] - value) > 1e-9:
            raise ValueError("conflicting base/support price")
    merged = {**base, **support}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = sources.ROOT / "data/raw/eia_gasoline_support" / stamp
    out.mkdir(parents=True, exist_ok=False)
    (out / "gasregw_response.csv").write_bytes(payload)
    path = out / "gasoline_retail_regular_consolidated.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["observation_date", "gasoline_retail_regular"])
        writer.writerows(sorted(merged.items()))
    sources.write_json(out / "manifest.json", {
        "source_url": url,
        "fetched_at": None if args.response_csv else datetime.now(timezone.utc).isoformat(),
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "requested_start": str(start), "requested_end": str(end),
        "retrieval_mode": "provided_response" if args.response_csv else "http_download",
        "support_observations": len(support), "merged_observations": len(merged),
        "base_file": str(args.base.resolve().relative_to(sources.ROOT)),
        "base_sha256": hashlib.sha256(args.base.read_bytes()).hexdigest(),
        "response_sha256": hashlib.sha256(payload).hexdigest(),
        "merged_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "vintage": "current_snapshot_unverified", "published_at": None,
        "original_cache_overwritten": False})
    print(path)


if __name__ == "__main__":
    main()
