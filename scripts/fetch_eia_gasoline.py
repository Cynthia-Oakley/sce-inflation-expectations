#!/usr/bin/env python3
"""Fetch U.S. retail gasoline prices (E v2 data layer, D049c).

Downloads the weekly national retail gasoline price series published by the
U.S. Energy Information Administration (EIA), re-hosted by FRED (St. Louis
Fed) which allows keyless CSV access:

  GASREGW  U.S. Regular All Formulations Retail Gasoline Prices
           (dollars per gallon, weekly, Monday observation date)

Outputs
  data/raw/eia_gasoline/gasoline_retail_weekly.csv   raw weekly series
  data/raw/eia_gasoline/gasoline_retail_monthly.jsonl
      one row per calendar month: mean of the weekly Monday prices, the
      year-over-year percent change of that monthly mean, and provenance.

Weekly EIA petroleum marketing data are effectively final (not revised like
CPI), but each row still records fetched_at; the raw CSV carries a sha256
sidecar so later re-fetches are detectable.

    python scripts/fetch_eia_gasoline.py [--start 2019-01-01] [--end today]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SERIES = {
    "gasoline_retail_regular": {
        "fred_id": "GASREGW",
        "description": "U.S. Regular All Formulations Retail Gasoline Prices",
        "units": "dollars_per_gallon",
        "frequency": "weekly (Monday)",
        "original_source": "U.S. Energy Information Administration (EIA), "
                           "Petroleum Marketing Monthly / Weekly Petroleum Status",
    },
}
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}&coed={end}"


def fetch_weekly(fred_id: str, start: str, end: str) -> list[tuple[str, float]]:
    url = FRED_CSV.format(sid=fred_id, start=start, end=end)
    with urllib.request.urlopen(url, timeout=60) as resp:
        payload = resp.read().decode("utf-8")
    rows = []
    for rec in csv.DictReader(io.StringIO(payload)):
        if rec[fred_id] in ("", "."):
            continue  # FRED marks missing observations with "."
        rows.append((rec["observation_date"], float(rec[fred_id])))
    if not rows:
        sys.exit(f"no observations returned for {fred_id} ({url})")
    return rows


def aggregate_monthly(weekly: list[tuple[str, float]]) -> list[dict]:
    """Monthly mean of weekly prices + y/y % change of that mean."""
    by_month: dict[str, list[float]] = defaultdict(list)
    for d, v in weekly:
        by_month[d[:7]].append(v)
    out = []
    for month in sorted(by_month):
        y, m = (int(x) for x in month.split("-"))
        prev = by_month.get(f"{y - 1:04d}-{m:02d}")
        vals = by_month[month]
        mean = sum(vals) / len(vals)
        row = {"month": month, "price_mean": round(mean, 3), "n_weeks": len(vals)}
        if prev:
            prev_mean = sum(prev) / len(prev)
            row["yoy_pct"] = round((mean - prev_mean) / prev_mean * 100, 1)
        out.append(row)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2019-01-01",
                    help="first observation date (default 2019-01-01 so y/y exists "
                         "for the 2020+ reference months)")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--outdir", type=Path, default=ROOT / "data/raw/eia_gasoline")
    args = ap.parse_args(argv)

    args.outdir.mkdir(parents=True, exist_ok=True)
    fetched_at = date.today().isoformat()

    for signal_id, meta in SERIES.items():
        weekly = fetch_weekly(meta["fred_id"], args.start, args.end)

        csv_path = args.outdir / f"{signal_id}_weekly.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["observation_date", signal_id])
            w.writerows(weekly)
        digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
        (csv_path.parent / (csv_path.name + ".sha256")).write_text(
            f"{digest}  {csv_path.name}\n", encoding="utf-8")

        monthly_path = args.outdir / f"{signal_id}_monthly.jsonl"
        with monthly_path.open("w", encoding="utf-8") as fh:
            for row in aggregate_monthly(weekly):
                fh.write(json.dumps({
                    "signal_id": signal_id,
                    "unit": meta["units"],
                    "reference_period": row["month"],
                    "aggregation": "mean of weekly Monday observations",
                    **{k: v for k, v in row.items() if k != "month"},
                    "source": f"FRED {meta['fred_id']} ({meta['description']})",
                    "original_source": meta["original_source"],
                    "fetched_at": fetched_at,
                    "raw_file": str(csv_path.relative_to(ROOT)),
                    "raw_sha256": digest,
                }, ensure_ascii=False) + "\n")

        print(f"{signal_id}: {len(weekly)} weekly obs {weekly[0][0]}..{weekly[-1][0]}; "
              f"wrote {csv_path.name} (+sha256) and {monthly_path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
