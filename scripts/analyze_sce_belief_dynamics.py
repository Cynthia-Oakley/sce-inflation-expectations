#!/usr/bin/env python3
"""SCE belief dynamics: task A (real panel update facts) + task A' (LLM same-
metric comparison). Zero-API, zero-network; reads only audited local caches.

Outputs (aggregate-only JSON + one private per-person parquet):
    outputs/sce_belief_dynamics_20261013_v1/analysis_summary.json
    outputs/sce_belief_dynamics_20261013_v1/llm_comparison_summary.json
    outputs/sce_belief_dynamics_20261013_v1/pairs_private.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from studies.sce_inflation_expectations.belief_dynamics.dynamics import run_analysis  # noqa: E402
from studies.sce_inflation_expectations.belief_dynamics.llm_compare import run_comparison  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "outputs" / "sce_belief_dynamics_20261013_v1"


def main() -> None:
    if OUTPUT_DIR.exists():
        raise SystemExit(f"output directory already exists, refusing to overwrite: {OUTPUT_DIR}")
    summary = run_analysis(OUTPUT_DIR)
    print(f"task A: valid pairs {summary['acceptance']['valid_q9_pairs']} / "
          f"adjacent {summary['acceptance']['adjacent_pairs']}; "
          f"monthly spearman mean {summary['ordering']['mean_monthly_spearman_unweighted']:.7f}")
    llm = run_comparison(OUTPUT_DIR)
    print(f"task A': {llm['n_person_months_valid']} valid person-months, "
          f"{llm['n_cells_valid']} month x repeat cells; prior mismatches "
          f"{llm['prior_consistency_check']['n_prior_mismatch_vs_real_prev_bins']}")
    print(f"wrote {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
