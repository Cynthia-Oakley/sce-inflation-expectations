#!/usr/bin/env python3
"""SCE preregistered empirical update baselines (B0-B4), train 201702-202112 /
validation 202201-202510. Design frozen in
docs/workstreams/20261013_behavior/kimi_progress.md section 5.

Zero-API, zero-network. Output:
    outputs/sce_belief_baselines_20261013_v1/baseline_summary.json
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from studies.sce_inflation_expectations.belief_dynamics.baselines import run_baselines  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "outputs" / "sce_belief_baselines_20261013_v1"


def main() -> None:
    if OUTPUT_DIR.exists():
        raise SystemExit(f"output directory already exists, refusing to overwrite: {OUTPUT_DIR}")
    summary = run_baselines(OUTPUT_DIR)
    for name, res in summary["baselines"].items():
        line = f"{name}: train MAE {res.get('train', {}).get('mae_pp_month_equal_auxiliary')} " \
               f"val MAE {res.get('val', {}).get('mae_pp_month_equal_auxiliary')}"
        if name == "B4" and not res["gate"]["triggered"]:
            line = f"{name}: skipped ({res['skipped_reason'][:60]}...)"
        print(line)
    print(f"wrote {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
