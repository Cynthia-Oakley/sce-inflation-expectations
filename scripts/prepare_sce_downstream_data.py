#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


SERIES = {
    "wage_growth_overall": "wages/wage_growth_overall.csv",
    "PCEDGC96": "durables/PCEDGC96.csv",
    "REVOLSL": "credit/REVOLSL.csv",
    "MICH": "expectations/MICH.csv",
    "UNRATE": "controls/UNRATE.csv",
    "JTSJOL": "controls/JTSJOL.csv",
    "DSPIC96": "controls/DSPIC96.csv",
    "CPIAUCSL": "controls/CPIAUCSL.csv",
    "CPILFESL": "controls/CPILFESL.csv",
    "UMCSENT": "controls/UMCSENT.csv",
    "FEDFUNDS": "controls/FEDFUNDS.csv",
    "TERMCBCCINTNS": "credit/TERMCBCCINTNS.csv",
    "TERMCBCCALLNS": "credit/TERMCBCCALLNS.csv",
}

VARIABLES = {
    "wage_growth_overall": {"role": "primary_outcome", "label": "Atlanta Fed Wage Growth Tracker Overall", "units": "percent", "frequency": "monthly", "note": "Three-month moving average of matched-CPS 12-month median wage growth."},
    "PCEDGC96": {"role": "primary_outcome", "label": "Real Personal Consumption Expenditures: Durable Goods", "units": "billions of chained 2017 dollars, SAAR", "frequency": "monthly"},
    "REVOLSL": {"role": "primary_outcome", "label": "Revolving Consumer Credit Owned and Securitized", "units": "millions of US dollars, SA", "frequency": "monthly", "note": "Outstanding balance, not gross new borrowing."},
    "MICH": {"role": "primary_outcome", "label": "University of Michigan: Inflation Expectation", "units": "percent, NSA", "frequency": "monthly"},
    "UNRATE": {"role": "control", "label": "Unemployment Rate", "units": "percent, SA", "frequency": "monthly"},
    "JTSJOL": {"role": "control", "label": "Job Openings: Total Nonfarm", "units": "thousands, SA", "frequency": "monthly"},
    "DSPIC96": {"role": "control", "label": "Real Disposable Personal Income", "units": "billions of chained 2017 dollars, SAAR", "frequency": "monthly"},
    "CPIAUCSL": {"role": "control", "label": "CPI All Items", "units": "index 1982-1984=100, SA", "frequency": "monthly"},
    "CPILFESL": {"role": "control", "label": "Core CPI", "units": "index 1982-1984=100, SA", "frequency": "monthly"},
    "UMCSENT": {"role": "control", "label": "University of Michigan: Consumer Sentiment", "units": "index 1966Q1=100, NSA", "frequency": "monthly"},
    "FEDFUNDS": {"role": "control", "label": "Federal Funds Effective Rate", "units": "percent, NSA", "frequency": "monthly"},
    "TERMCBCCINTNS": {"role": "credit_control_candidate", "label": "Credit Card Plans: Accounts Assessed Interest", "units": "percent, NSA", "frequency": "monthly grid with quarterly observations", "note": "Revolvers only; blank months are retained."},
    "TERMCBCCALLNS": {"role": "credit_control_candidate", "label": "Credit Card Plans: All Accounts", "units": "percent, NSA", "frequency": "monthly grid with quarterly observations", "note": "Includes transactor accounts; blank months are retained."},
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def expected_hashes(root):
    expected = {}
    wages = read_json(root / "wages/manifest.json")
    for group in ("raw_files", "derived_files"):
        for item in wages[group]:
            expected[root / "wages" / item["file"]] = item["sha256"]
    durables = read_json(root / "durables/manifest.json")
    expected[root / "durables/PCEDGC96.csv"] = durables["file"]["sha256"]
    expectations = read_json(root / "expectations/manifest.json")
    expected[root / "expectations/MICH.csv"] = expectations["file"]["sha256"]
    for group in ("credit", "controls"):
        manifest = read_json(root / group / "manifest.json")
        for item in manifest["series"].values():
            expected[root / group / item["file"]] = item["file_sha256"]
    return expected


def read_series(path):
    with path.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows or "date" not in rows[0] or "value" not in rows[0]:
        raise ValueError(f"Invalid series CSV: {path}")
    values = {}
    missing = []
    for row in rows:
        date = row["date"]
        if date in values:
            raise ValueError(f"Duplicate date {date} in {path}")
        value = row["value"].strip()
        if value:
            float(value)
        else:
            missing.append(date)
        values[date] = value
    return values, {"rows": len(rows), "first_date": min(values), "last_date": max(values), "missing_dates": missing}


def month_numbers(dates):
    return sorted({int(date[:4]) * 12 + int(date[5:7]) - 1 for date in dates})


def month_date(number):
    year, month = divmod(number, 12)
    return f"{year:04d}-{month + 1:02d}-01"


def run(raw_root, out):
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty output directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    hashes = expected_hashes(raw_root)
    for path, expected in sorted(hashes.items(), key=lambda item: str(item[0])):
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"Source hash mismatch: {path}: {actual} != {expected}")

    values = {}
    source_report = {}
    for name, relative in SERIES.items():
        path = raw_root / relative
        series, report = read_series(path)
        values[name] = series
        source_report[name] = {"file": relative, **report, "sha256": sha256(path)}

    dates = sorted({date for series in values.values() for date in series if date >= "2017-01-01"})
    months = [month_date(number) for number in range(month_numbers(dates)[0], month_numbers(dates)[-1] + 1)]
    with (out / "monthly_panel.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["date", *SERIES])
        writer.writeheader()
        for date in months:
            writer.writerow({"date": date, **{name: values[name].get(date, "") for name in SERIES}})

    coverage = {}
    for name in SERIES:
        missing = [date for date in months if not values[name].get(date, "")]
        coverage[name] = {"missing_count": len(missing), "missing_dates": missing, "non_missing_count": len(months) - len(missing)}
    dictionary = {"variables": VARIABLES, "panel": {"rows": len(months), "start": months[0], "end": months[-1], "missing_policy": "No imputation, interpolation, forward filling, scaling, or seasonal adjustment in this derived panel.", "vintage_policy": "Current public values at source-specific retrieval time; not point-in-time vintages."}}
    write_json(out / "variable_dictionary.json", dictionary)
    report = {"status": "completed_offline_data_assembly", "new_api_calls": 0, "source_files_verified": len(hashes), "panel": dictionary["panel"], "series": source_report, "coverage": coverage}
    write_json(out / "coverage_report.json", report)
    write_json(out / "manifest.json", {"status": "completed_offline_data_assembly", "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": {str(path.relative_to(raw_root)): digest for path, digest in sorted(hashes.items(), key=lambda item: str(item[0]))}, "derived_files": {path.name: sha256(path) for path in out.iterdir() if path.is_file()}})
    print(json.dumps({"status": "ok", "panel_rows": len(months), "panel_start": months[0], "panel_end": months[-1], "source_files_verified": len(hashes), "out": str(out)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.raw_root, args.out)


if __name__ == "__main__":
    main()
