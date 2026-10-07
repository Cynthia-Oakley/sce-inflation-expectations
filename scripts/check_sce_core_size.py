"""Offline Core-size study: nested samples of observed responses, never an LLM run.

Uses official Q9 derived means to isolate population sampling/expansion error.
No size is selected by the program. IDs and true answers remain local.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import sys
import types
import uuid

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
# Load the statistical helpers as an isolated namespace package. Importing the
# study's normal __init__ registers engine/model providers and the dirty scorer;
# this offline diagnostic needs neither of them.
stat_package = types.ModuleType("_sce_core_size_statistics")
stat_package.__path__ = [str(ROOT / "studies/sce_inflation_expectations")]
sys.modules[stat_package.__name__] = stat_package
from _sce_core_size_statistics.monthly_population import PROFILE_COLUMNS, build_monthly_population
from _sce_core_size_statistics.core_normal import build_expansion
sys.path.insert(0, str(ROOT / "studies/sce_inflation_expectations"))
from evaluation.metrics import quantile as weighted_quantile, wasserstein1 as weighted_wasserstein


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def describe(values):
    a = np.asarray(values, float)
    return {"mean": float(a.mean()), "median": float(np.median(a)), "p95": float(np.quantile(a, .95))}


def metrics(x, w, truth_x, truth_w):
    median = weighted_quantile(x, w, .5)
    iqr = weighted_quantile(x, w, .75) - weighted_quantile(x, w, .25)
    tiqr = weighted_quantile(truth_x, truth_w, .75) - weighted_quantile(truth_x, truth_w, .25)
    return {"headline_absolute_error_pp": abs(median - weighted_quantile(truth_x, truth_w, .5)),
            "iqr_absolute_error_pp": abs(iqr - tiqr),
            "wasserstein_1_pp": weighted_wasserstein(x, w, truth_x, truth_w),
            "weighted_mean_bias_pp": float(np.average(x, weights=w) - np.average(truth_x, weights=truth_w))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile-cache", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--months", default=",".join(str(202100 + i) for i in range(1, 13)))
    ap.add_argument("--sizes", default="75,100,150,200,300")
    ap.add_argument("--repeats", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--prior-strength", type=float, default=5.)
    args = ap.parse_args()
    months = sorted(set(map(int, args.months.split(","))))
    sizes = sorted(set(map(int, args.sizes.split(","))))
    if args.repeats < 1 or min(sizes) < 1:
        raise ValueError("positive sizes and repeats required")
    # Verify profile-cache identity against its original reader contract.
    source_hash = sha(args.source)
    expected_cache = hashlib.sha256((source_hash + json.dumps(PROFILE_COLUMNS + ["weight", "survey_date"])).encode()).hexdigest()[:20]
    if args.profile_cache.name != f"monthly_profiles_{expected_cache}.parquet":
        raise ValueError("profile cache does not match source and whitelist")
    profiles = pd.read_parquet(args.profile_cache)
    response_cache = ROOT / "data/cache" / f"core_size_official_q9_{source_hash[:20]}.parquet"
    if not response_cache.exists():
        print("Reading date, userid, Q9_mean into an evaluation-only local cache", flush=True)
        answers = pd.read_excel(args.source, header=1, usecols=["date", "userid", "Q9_mean"])
        response_cache.parent.mkdir(parents=True, exist_ok=True)
        answers.to_parquet(response_cache, index=False)
    answers = pd.read_parquet(response_cache)
    if profiles.duplicated(["date", "userid"]).any() or answers.duplicated(["date", "userid"]).any():
        raise ValueError("duplicate person-month")
    out = ROOT / "outputs" / ("sce_core_size_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    # Stable user priorities within a repeat give nested sizes and the same
    # ranking across waves, matching production's stable-priority SRS design.
    userids = sorted(set(profiles.loc[profiles.date.isin(months), "userid"].astype(int)))
    priorities = [{uid: np.random.default_rng(np.random.SeedSequence([args.seed + repeat, uid])).random()
                   for uid in userids} for repeat in range(args.repeats)]
    records, coverage = [], []
    for month in months:
        population, meta = build_monthly_population(profiles, month)
        ids = sorted(p["agent_id"] for p in population["personas"])
        frame = profiles[profiles.date == month].set_index("userid")
        weights = {u: float(frame.loc[int(u.removeprefix("sce_u")), "weight"]) for u in ids}
        answer_rows = answers[answers.date == month].set_index("userid").Q9_mean
        values = {u: float(answer_rows.loc[int(u.removeprefix("sce_u"))]) for u in ids}
        valid = {u for u in ids if np.isfinite(values[u])}
        targets = sorted(valid)
        truth_x, truth_w = [values[u] for u in targets], [weights[u] for u in targets]
        coverage.append({"target_month": month, "frame_n": len(ids), "q9_mean_valid_n": len(valid)})
        if max(sizes) > len(ids):
            raise ValueError("Core size exceeds population frame")
        for repeat, ranks in enumerate(priorities):
            order = sorted(ids, key=lambda u: (ranks[int(u.removeprefix("sce_u"))], u))
            for size in sizes:
                # Selection uses no answers. Outcome validity is applied later.
                core = order[:size]
                donors = sorted(set(core) & valid)
                if not donors:
                    raise ValueError("no valid donor; stop rather than pick another sample")
                x, w = [values[u] for u in donors], [weights[u] for u in donors]
                plan = build_expansion(population, core, donors, weights, prior_strength=args.prior_strength)
                masses = plan.atom_weights(target_ids=valid)
                report = plan.report()
                records.append({"target_month": month, "repeat": repeat, "core_n": size,
                                "core_ids_sha256": hashlib.sha256(json.dumps(core).encode()).hexdigest(),
                                "valid_core_n": len(donors), "weight_ess": sum(w) ** 2 / sum(a * a for a in w),
                                "normal_without_fine_support_weight_fraction": report["normal_without_fine_support_weight_fraction"],
                                "normal_prior_mass_fraction": report["normal_prior_mass_fraction"],
                                "core_only": metrics(x, w, truth_x, truth_w),
                                "expanded": metrics(x, masses, truth_x, truth_w)})
        print(f"Core sizing {month}: {len(ids)} people, {args.repeats} paired draws complete", flush=True)
    by_size = {}
    for size in sizes:
        selected = [r for r in records if r["core_n"] == size]
        by_size[str(size)] = {"n_month_draws": len(selected), "weight_ess": describe([r["weight_ess"] for r in selected]),
            "normal_without_fine_support_weight_fraction": describe([r["normal_without_fine_support_weight_fraction"] for r in selected]),
            "normal_prior_mass_fraction": describe([r["normal_prior_mass_fraction"] for r in selected]),
            **{mode: {key: describe([r[mode][key] for r in selected]) for key in selected[0][mode]}
               for mode in ["core_only", "expanded"]}}
    monthly = {str(month): {str(size): {mode: describe([r[mode]["headline_absolute_error_pp"] for r in records
                 if r["target_month"] == month and r["core_n"] == size]) for mode in ["core_only", "expanded"]}
                 for size in sizes} for month in months}
    manifest = {"run_id": out.name, "purpose": "observed_Q9_oracle_sampling_and_expansion_not_LLM_accuracy",
                "model_api_calls": 0, "network_calls": 0, "months": months, "sizes": sizes,
                "repeats": args.repeats, "seed": args.seed, "prior_strength": args.prior_strength,
                "sampling": "stable_priority_srs_nested_sizes_and_shared_ranks_across_months",
                "selected_size": None, "inputs_sha256": {"source_workbook": source_hash, "profile_cache": sha(args.profile_cache), "official_q9_cache": sha(response_cache)},
                "code_sha256": {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / "studies/sce_inflation_expectations/core_normal.py", ROOT / "studies/sce_inflation_expectations/monthly_population.py", ROOT / "studies/sce_inflation_expectations/evaluation/metrics.py"]},
                "coverage": coverage, "by_size": by_size, "monthly_headline_error": monthly,
                "limitations": ["Official-provided Q9 means isolate sampling; no Agent behavioral error or scorer-fit validation",
                                "Q9-only valid donors are more permissive than production's joint Q8/Q9 donors",
                                "Repeated draws/months overlap; pooled p95 is not a confidence interval",
                                "Increased Normal count cannot create missing behavioral response support",
                                "Results now inspected cannot be used as an untouched final Agent test period"]}
    (out / "summary.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (out / "draw_metrics.jsonl").write_text("".join(json.dumps(r, allow_nan=False) + "\n" for r in records))
    print(out, flush=True)


if __name__ == "__main__":
    main()
