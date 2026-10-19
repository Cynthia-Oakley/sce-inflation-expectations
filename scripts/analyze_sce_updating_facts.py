#!/usr/bin/env python3
"""SCE updating micro facts F1-F6: inaction, lumpy revisions, information
rigidity (CG + mean reversion), heaping, trait stability, update-type
distribution. Zero-API, zero-network; reads only audited local caches.

Outputs (aggregate-only JSON + figures + one private per-person parquet):
    outputs/sce_updating_facts_20261019_v1/analysis_summary.json
    outputs/sce_updating_facts_20261019_v1/figures/*.png|.svg
    outputs/sce_updating_facts_20261019_v1/persons_private.parquet
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from studies.sce_inflation_expectations.belief_dynamics.updating_facts import (  # noqa: E402
    run_analysis,
)

OUTPUT_DIR = REPO_ROOT / "outputs" / "sce_updating_facts_20261019_v1"


def main() -> None:
    if OUTPUT_DIR.exists():
        raise SystemExit(f"output directory already exists, refusing to overwrite: {OUTPUT_DIR}")
    summary = run_analysis(OUTPUT_DIR)
    f1 = summary["F1_inaction"]["overall"]
    f3a = summary["F3a_cg_rigidity"]
    print(f"valid pairs {summary['acceptance']['valid_q9_pairs']}; "
          f"F1 exact-zero {f1['share_exact_zero_delta_unweighted']:.4f} (unweighted); "
          f"F3a CG slope {f3a['slope_pooled_month_fe_unweighted']:.4f} "
          f"(+/- {1.96 * f3a['se_clustered_by_userid']:.4f} clustered)")
    print(f"wrote {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
