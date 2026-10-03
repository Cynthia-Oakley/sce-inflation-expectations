#!/usr/bin/env python3
"""Extract evaluation-layer truth for the SCE main window from the microdata.

Evaluation layer only — nothing here ever enters P/E/B inputs (protocol §3):
per-person real answers (Q8v2 point, Q9 bins + official derived moments) and
full-sample monthly official aggregates are used exclusively to score and
compare simulation outputs.

    python scripts/build_sce_evaluation_truth.py \
        --panel-meta studies/sce_inflation_expectations/population/population_main2021_a73.sampling_meta.json \
        --months 202101..202112 --out data/evaluation/sce_truth_main2021.json

Outputs (gitignored data/evaluation/):
- per_person: rows for the sampled panel userids (userid, date, weight, Q8v2,
  Q9_bin1..10, official Q9_mean/cent25/cent50/cent75/iqr);
- monthly_full_sample: per-month official weighted aggregates over ALL
  respondents that month (weighted median of Q8v2 and Q9_mean, n, sum of weights);
- manifest: source file + SHA-256, extraction time, row counts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "studies" / "sce_inflation_expectations" / "scoring"))
from sce_q9 import weighted_empirical_quantile  # noqa: E402

SOURCE = ROOT / "data/raw/sce_audit_20260928/micro_2020_2024.xlsx"

FIELDS = (["date", "userid", "weight", "Q8v2", "Q9_mean", "Q9_cent25",
           "Q9_cent50", "Q9_cent75", "Q9_iqr"]
          + [f"Q9_bin{i}" for i in range(1, 11)])


def _parse_months(spec: str) -> list[int]:
    if ".." in spec:
        lo, hi = spec.split("..")
        out, y, m = [], int(lo[:4]), int(lo[4:])
        while (y, m) <= (int(hi[:4]), int(hi[4:])):
            out.append(y * 100 + m)
            m += 1
            if m == 13:
                y, m = y + 1, 1
        return out
    return [int(x) for x in spec.split(",")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel-meta", default=None,
                    help="sampling meta json whose sampled_userids define the panel extract")
    ap.add_argument("--months", required=True, help="e.g. 202101..202112 or 202101,202102")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    if not SOURCE.exists():
        sys.exit(f"microdata missing: {SOURCE} (gitignored data/raw; cannot extract here)")
    months = set(_parse_months(args.months))
    userids = None
    if args.panel_meta:
        meta = json.loads(Path(args.panel_meta).read_text(encoding="utf-8"))
        userids = set(meta["sampled_userids"])

    from openpyxl import load_workbook
    book = load_workbook(SOURCE, read_only=True, data_only=True)
    ws = book[book.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    next(it)  # FRBNY banner row
    header = list(next(it))
    ix = {k: header.index(k) for k in FIELDS}

    per_person: list[dict] = []
    monthly: dict[int, dict] = {}
    for row in it:
        date = row[ix["date"]]
        if date not in months:
            continue
        weight = row[ix["weight"]]
        q8 = row[ix["Q8v2"]]
        q9m = row[ix["Q9_mean"]]
        bucket = monthly.setdefault(date, {"n": 0, "w": [], "q8": [], "q9m": []})
        bucket["n"] += 1
        if isinstance(weight, (int, float)) and weight > 0:
            if isinstance(q8, (int, float)):
                bucket["w"].append(weight)
                bucket["q8"].append(q8)
                bucket["q9m"].append(q9m if isinstance(q9m, (int, float)) else None)
        if userids is not None and row[ix["userid"]] in userids:
            per_person.append({k: row[ix[k]] for k in FIELDS})
    book.close()

    monthly_full = {}
    for date in sorted(monthly):
        b = monthly[date]
        q8_vals = [(q, w) for q, w in zip(b["q8"], b["w"])]
        q9_vals = [(q, w) for q, w in zip(b["q9m"], b["w"]) if q is not None]
        monthly_full[str(date)] = {
            "n_respondents": b["n"],
            "q8v2_weighted_median": (weighted_empirical_quantile(
                [q for q, _ in q8_vals], [w for _, w in q8_vals], 0.5) if q8_vals else None),
            "q9_mean_weighted_median": (weighted_empirical_quantile(
                [q for q, _ in q9_vals], [w for _, w in q9_vals], 0.5) if q9_vals else None),
            "n_with_weight_q8": len(q8_vals),
            "n_with_weight_q9_mean": len(q9_vals),
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest": {
            "source": str(SOURCE.relative_to(ROOT)),
            "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "extracted_at_utc": datetime.now(timezone.utc).isoformat(),
            "months": sorted(months),
            "panel_meta": args.panel_meta,
            "n_per_person_rows": len(per_person),
            "layer": "evaluation_only",
            "note": "Real answers and official derived values; never enter P/E/B inputs.",
        },
        "monthly_full_sample": monthly_full,
        "per_person": per_person,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}: {len(per_person)} per-person rows, "
          f"{len(monthly_full)} months of full-sample aggregates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
