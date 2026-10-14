#!/usr/bin/env python
"""Run the preregistered personal-anchor update rules (belief dynamics, round 2).

Usage: python scripts/run_sce_anchor_baselines.py [output_dir]
Default output: outputs/sce_anchor_baselines_20261013_v1/
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from studies.sce_inflation_expectations.belief_dynamics.anchor import run_anchor_baselines


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "outputs/sce_anchor_baselines_20261013_v1")
    summary = run_anchor_baselines(out)
    for name, v in summary["variants"].items():
        val = v["val"]
        print(f"{name}: lambda={v['selected_lambda']:.2f} "
              f"val_deltaW1={val['delta_w1_month_equal']:.3f} "
              f"val_csW1={val['cross_section_w1_month_equal']:.3f} "
              f"val_medAE={val['median_abs_error_pp_month_equal']:.3f} "
              f"val_persMAE={val['mae_pp_month_equal_auxiliary']:.3f}")
    print(f"written: {out / 'anchor_summary.json'}")


if __name__ == "__main__":
    main()
