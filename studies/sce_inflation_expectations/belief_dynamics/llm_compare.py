"""Task A': same-metric comparison of LLM prior-trial arms against real people.

Both the real answers and the model arms are re-scored from the ten Q9 bins
with the frozen project scorer (score_q9_frozen); the official Q9_mean is
never mixed with the frozen approximation. A consistency note reports the
correlation between official Q9_mean and the frozen mean on the involved
person-months. All model metrics are descriptive, n=12 per month x repeat
cell (not weighted, not independent samples).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..scoring.sce_q9_frozen import provenance, score_q9_frozen
from .metrics import weighted_w1
from .data import previous_calendar_month
from .metrics import iqr, weighted_pearson

ARMS = ("no_prior", "own_previous", "permuted_previous")
EVAL_PATH = Path(__file__).resolve().parents[3] / "outputs" / "sce_prior_analysis_20261013_v1" / "paired_evaluation_private.json"
LINKS_PATH = Path(__file__).resolve().parents[3] / "outputs" / "sce_prior_trial_20261013_v2" / "evaluation_links_private.json"


def _center(bins):
    """Frozen-scored center (mean) of one ten-bin answer; None if unscorable."""
    if bins is None:
        return None
    try:
        score = score_q9_frozen([float(v) for v in bins])
    except Exception:
        return None
    mean = score.mean
    return float(mean) if mean is not None and np.isfinite(mean) else None


def _load_links():
    links = json.loads(LINKS_PATH.read_text())
    out = {}
    for row in links:
        agent_id = row["agent_id"]
        source = str(row["source_agent_id"])
        if not source.startswith("sce_u"):
            raise ValueError(f"unexpected source_agent_id: {source}")
        out[agent_id] = int(source[len("sce_u"):])
    return out


def build_person_month_table(reference: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """One row per (month, repeat, person) with real and arm frozen centers."""
    if not provenance()["live_matches_pinned"]:
        raise AssertionError("frozen scorer provenance: live sources do not match pinned hashes")
    eval_rows = json.loads(EVAL_PATH.read_text())
    links = _load_links()
    meta = reference.set_index(["userid", "date"])
    records = []
    n_prior_mismatch = 0
    for row in eval_rows:
        if row["measure"] != "Q9":
            continue
        agent_id = row["agent_id"]
        userid = links[agent_id]
        month = int(row["month"])
        prev_month = previous_calendar_month(month)
        cur = meta.loc[(userid, month)]
        prev = meta.loc[(userid, prev_month)]
        real_cur_bins = [float(cur[c]) for c in [f"Q9_bin{i}" for i in range(1, 11)]]
        real_prev_bins = [float(prev[c]) for c in [f"Q9_bin{i}" for i in range(1, 11)]]
        supplied_own = row["supplied_priors"]["own_previous"]
        if (supplied_own is None
                or max(abs(a - b) for a, b in zip(real_prev_bins, supplied_own)) > 1e-9):
            n_prior_mismatch += 1
        rec = {
            "month": month, "repeat": int(row["repeat"]), "agent_id": agent_id,
            "userid": userid, "weight": float(row["weight"]),
            "real_cur_center": _center(real_cur_bins),
            "real_prev_center": _center(real_prev_bins),
            "official_q9_mean_cur": float(cur["Q9_mean"]) if np.isfinite(cur["Q9_mean"]) else None,
            "official_q9_mean_prev": float(prev["Q9_mean"]) if np.isfinite(prev["Q9_mean"]) else None,
        }
        for arm in ARMS:
            rec[f"{arm}_center"] = _center(row["raw_answers"][arm])
            rec[f"{arm}_prior_center"] = _center(row["supplied_priors"][arm])
        records.append(rec)
    table = pd.DataFrame.from_records(records)
    note = {"n_q9_records": len(table),
            "n_prior_mismatch_vs_real_prev_bins": n_prior_mismatch,
            "prior_match_tolerance": 1e-9}
    return table, note


def _cell_metrics(cell: pd.DataFrame) -> dict:
    """Main metrics for one (month, repeat) cell of 12 persons, unweighted."""
    real_delta = (cell["real_cur_center"] - cell["real_prev_center"]).to_numpy(float)
    out = {
        "n": int(len(cell)),
        "real": {
            "mean_abs_delta": float(np.mean(np.abs(real_delta))),
            "share_abs_le_0_5pp": float(np.mean(np.abs(real_delta) <= 0.5)),
            "share_delta_positive": float(np.mean(real_delta > 0)),
            "share_delta_negative": float(np.mean(real_delta < 0)),
            "center_iqr_across_persons": iqr(cell["real_cur_center"]),
        },
        "w1_delta_vs_real": {
            "persistence_delta_zero": float(
                np.mean(np.abs(real_delta))),  # W1(point mass at 0, real delta)
        },
        "arms": {},
    }
    for arm in ARMS:
        arm_delta = (cell[f"{arm}_center"] - cell["real_prev_center"]).to_numpy(float)
        out["arms"][arm] = {
            "w1_delta_vs_real": _w1_unweighted(arm_delta, real_delta),
            "mean_abs_delta": float(np.mean(np.abs(arm_delta))),
            "share_abs_le_0_5pp": float(np.mean(np.abs(arm_delta) <= 0.5)),
            "share_delta_positive": float(np.mean(arm_delta > 0)),
            "share_delta_negative": float(np.mean(arm_delta < 0)),
            "center_iqr_across_persons": iqr(cell[f"{arm}_center"]),
        }
    out["identity_value_elasticity"] = _elasticity(cell)
    return out


def _w1_unweighted(a, b) -> float:
    return weighted_w1(a, b)


def _elasticity(cell: pd.DataFrame) -> dict:
    """Cross-person input diff (own - permuted prior centers) vs output diff."""
    input_diff = (cell["own_previous_prior_center"] - cell["permuted_previous_prior_center"]).to_numpy(float)
    output_diff = (cell["own_previous_center"] - cell["permuted_previous_center"]).to_numpy(float)
    ok = np.isfinite(input_diff) & np.isfinite(output_diff)
    if ok.sum() < 3 or np.std(input_diff[ok]) == 0:
        return {"n": int(ok.sum()), "slope": None, "pearson": None,
                "mean_input_diff_pp": None, "mean_output_diff_pp": None}
    slope = float(np.cov(input_diff[ok], output_diff[ok], ddof=0)[0, 1] / np.var(input_diff[ok]))
    return {
        "n": int(ok.sum()),
        "slope_output_per_input": slope,
        "pearson": float(np.corrcoef(input_diff[ok], output_diff[ok])[0, 1]),
        "mean_input_diff_pp": float(np.mean(input_diff[ok])),
        "mean_output_diff_pp": float(np.mean(output_diff[ok])),
    }


def _aggregate_cells(cells: dict) -> dict:
    """Average per-cell metrics across cells (month-equal over cells)."""
    arms_agg = {}
    for arm in ARMS:
        arms_agg[arm] = {
            "w1_delta_vs_real_mean": float(np.mean([c["arms"][arm]["w1_delta_vs_real"] for c in cells.values()])),
            "mean_abs_delta_mean": float(np.mean([c["arms"][arm]["mean_abs_delta"] for c in cells.values()])),
            "share_abs_le_0_5pp_mean": float(np.mean([c["arms"][arm]["share_abs_le_0_5pp"] for c in cells.values()])),
            "share_delta_positive_mean": float(np.mean([c["arms"][arm]["share_delta_positive"] for c in cells.values()])),
            "share_delta_negative_mean": float(np.mean([c["arms"][arm]["share_delta_negative"] for c in cells.values()])),
            "center_iqr_mean": float(np.nanmean([c["arms"][arm]["center_iqr_across_persons"] for c in cells.values()])),
        }
    agg = {
        "n_cells": len(cells),
        "real": {
            "mean_abs_delta_mean": float(np.mean([c["real"]["mean_abs_delta"] for c in cells.values()])),
            "share_abs_le_0_5pp_mean": float(np.mean([c["real"]["share_abs_le_0_5pp"] for c in cells.values()])),
            "share_delta_positive_mean": float(np.mean([c["real"]["share_delta_positive"] for c in cells.values()])),
            "share_delta_negative_mean": float(np.mean([c["real"]["share_delta_negative"] for c in cells.values()])),
            "center_iqr_mean": float(np.nanmean([c["real"]["center_iqr_across_persons"] for c in cells.values()])),
        },
        "persistence_delta_zero_w1_mean":
            float(np.mean([c["w1_delta_vs_real"]["persistence_delta_zero"] for c in cells.values()])),
        "arms": arms_agg,
        "identity_value_elasticity": {
            "slope_mean_over_cells": float(np.nanmean(
                [c["identity_value_elasticity"]["slope_output_per_input"] for c in cells.values()])),
            "pearson_mean_over_cells": float(np.nanmean(
                [c["identity_value_elasticity"]["pearson"] for c in cells.values()])),
        },
    }
    return agg


def run_comparison(output_dir: Path, reference: pd.DataFrame | None = None) -> dict:
    output_dir = Path(output_dir)
    if reference is None:
        from .data import load_reference_frame
        reference = load_reference_frame()
    table, note = build_person_month_table(reference)

    ok_rows = table[np.isfinite(table["real_cur_center"]) & np.isfinite(table["real_prev_center"])
                    & table[[f"{a}_center" for a in ARMS]].notna().all(axis=1)]
    cells = {}
    for (month, repeat), cell in ok_rows.groupby(["month", "repeat"]):
        cells[f"{month}_r{repeat}"] = _cell_metrics(cell)
    per_repeat = _aggregate_cells(cells)

    # Person-level: average the two repeats per (month, person), then recompute.
    person_level = ok_rows.groupby(["month", "userid"], as_index=False).agg(
        real_cur_center=("real_cur_center", "mean"),
        real_prev_center=("real_prev_center", "mean"),
        **{f"{a}_center": (f"{a}_center", "mean") for a in ARMS},
        own_previous_prior_center=("own_previous_prior_center", "mean"),
        permuted_previous_prior_center=("permuted_previous_prior_center", "mean"),
    )
    person_cells = {}
    for month, cell in person_level.groupby("month"):
        person_cells[str(month)] = _cell_metrics(cell)
    person_agg = _aggregate_cells(person_cells)

    # Consistency note: official Q9_mean vs frozen mean on involved person-months.
    official = []
    frozen = []
    for _, r in ok_rows.iterrows():
        if r["official_q9_mean_cur"] is not None and np.isfinite(r["official_q9_mean_cur"]):
            official.append(r["official_q9_mean_cur"])
            frozen.append(r["real_cur_center"])
    consistency = {
        "n_person_months": len(official),
        "pearson_official_q9_mean_vs_frozen_mean":
            float(np.corrcoef(official, frozen)[0, 1]) if len(official) > 2 else None,
        "note": ("Real and model centers are both recomputed from ten bins with the "
                 "frozen scorer; official Q9_mean appears only in this consistency note."),
    }

    summary = {
        "line": "SCE belief dynamics LLM same-metric comparison (task A')",
        "scorer_provenance": {k: v for k, v in provenance().items() if k != "pinned_sha256"},
        "inputs": {
            "paired_evaluation_private": str(EVAL_PATH),
            "evaluation_links_private": str(LINKS_PATH),
        },
        "prior_consistency_check": note,
        "n_person_months_valid": int(ok_rows.groupby(["month", "userid"]).ngroups),
        "n_cells_valid": len(cells),
        "per_month_repeat_cells": cells,
        "aggregate_over_cells": per_repeat,
        "person_level_two_repeat_averaged": {
            "n_person_months": int(len(person_level)),
            "cells": person_cells,
            "aggregate_over_months": person_agg,
            "note": ("Each person's two generation repeats were averaged before "
                     "recomputing the metrics; person-months are not independent samples."),
        },
        "consistency_note": consistency,
        "interpretation": (
            "Descriptive comparison on 4 trial months x 12 linked real persons x 2 "
            "repeats; unweighted n=12 per cell. W1 is the 1-Wasserstein distance "
            "between model-arm and real person-level delta distributions."),
    }
    (Path(output_dir) / "llm_comparison_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
