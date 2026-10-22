#!/usr/bin/env python3
"""Batch materialization of monthly P/population deliveries (Codex priority 1).

Extends the phase-2 sample-month machinery to further coverage months WITHOUT
changing it: every per-month builder is imported from
scripts/build_sce_fullperiod_sample_data.py and called with the same
arguments the frozen samples used, so outputs are structurally identical to
the accepted samples (201906/202303/202606 stay untouched as the alignment
reference).

Scope order (Codex kimi_parallel_tasks_20261022.md):
  1. priority months for the final news trials and continuity acceptance:
     2020-09, 2022-06, 2024-10, 2025-05, 2025-06, 2025-07, 2025-09
     (all have micro truth -> build_real_month)
  2. remaining months only after Codex interface checks pass (--all).

Per month writes into outputs/sce_fullperiod_data_20261021_v1/<YYYYMM>/:
  population.json, population_state_private.json, belief_state_private.json,
  sampling_private.json, news_label_index.json, evaluation_truth/.
environment.json is intentionally NOT built here (E-side batch is a separate
script awaiting Codex's sample-alignment sign-off).

Also writes/updates delivery-root materialization_status.json (coverage.json
itself is NOT touched: its sha256 is frozen into existing label protocols).
Offline only; no API calls.

    python scripts/build_sce_fullperiod_batch_population.py            # priority
    python scripts/build_sce_fullperiod_batch_population.py --months 202101 202102
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_sce_fullperiod_sample_data as S  # noqa: E402
from studies.sce_inflation_expectations.news_selection_trial import (  # noqa: E402
    RULE_FILE, RecallRules)

PRIORITY = ["202009", "202206", "202410", "202505", "202506", "202507", "202509"]
SAMPLE_MONTHS = set(S.REAL_TARGETS) | {S.SYNTH_TARGET}
STATUS_FILE = S.OUT_DIR / "materialization_status.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", nargs="*", default=None,
                    help="YYYYMM list; default = priority months")
    args = ap.parse_args()
    targets = args.months or PRIORITY

    cov = json.loads((S.OUT_DIR / "coverage.json").read_text())
    by_month = {m["target_month"].replace("-", ""): m for m in cov["months"]}
    unknown = [t for t in targets if t not in by_month]
    if unknown:
        sys.exit(f"months not in coverage.json: {unknown}")
    overlap = [t for t in targets if t in SAMPLE_MONTHS]
    if overlap:
        sys.exit(f"refusing to touch frozen sample months: {overlap}")

    print("loading micro data (pandas)...", flush=True)
    df = S.load_micro()
    q43 = df[df["Q43"].notna()][["userid", "date", "Q43"]]
    q43_by_user = {int(u): dict(zip(g["date"], g["Q43"]))
                   for u, g in q43.groupby("userid")}
    d3 = df[df["D3"].notna()][["userid", "date", "D3"]]
    d3_by_user = {int(u): dict(zip(g["date"], g["D3"]))
                  for u, g in d3.groupby("userid")}
    labels = S.load_labels()
    rules = RecallRules(json.loads(RULE_FILE.read_text()))

    status = json.loads(STATUS_FILE.read_text()) if STATUS_FILE.exists() else {
        "note": "per-month materialization status; coverage.json is frozen "
                "by label-protocol hashes and intentionally not modified",
        "months": {}}
    for target in targets:
        c = by_month[target]
        tdir = S.OUT_DIR / target
        if tdir.exists():
            print(f"{target}: already materialized, skipping (never overwrite)")
            continue
        yyyymm = int(target)
        if c["micro_truth_available"]:
            S.build_real_month(target, yyyymm, df, q43_by_user, d3_by_user,
                               c["as_of"])
            S.build_evaluation_truth(target, yyyymm, df, synthetic=False)
            kind = "real"
        else:
            S.build_synth_month(target, df, q43_by_user, d3_by_user, c["as_of"])
            S.build_evaluation_truth(target, yyyymm, df, synthetic=True)
            kind = "synthetic_no_micro"
        S.build_news_index(target, labels, rules, c["as_of"])
        status["months"][target] = {
            "status": "materialized", "kind": kind,
            "at_utc": datetime.now(timezone.utc).isoformat(),
            "builder": "build_sce_fullperiod_sample_data.py (imported, unchanged)",
            "files": sorted(p.name if p.is_file() else p.name + "/"
                            for p in tdir.iterdir()),
        }
        STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2)
                               + "\n")
        print(f"{target}: done ({kind})", flush=True)
    print(json.dumps({"materialized": sorted(status["months"])},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
