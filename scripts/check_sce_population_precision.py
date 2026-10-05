"""Offline development-month sampling check; no providers or simulation inputs.

Sample selection reads only profile strata. Actual answers are used afterwards
to measure sampling error against the complete monthly survey, not to pick a
favourable seed. This diagnostic does not estimate LLM error or B-line accuracy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROFILE_COLS = ["_AGE_CAT", "_EDU_CAT", "_HH_INC_CAT", "_REGION_CAT", "_NUM_CAT"]


def allocate(counts, n):
    """Proportional integer allocation, at least one per nonempty cell."""
    counts = np.asarray(counts, dtype=int)
    if np.any(counts <= 0) or not len(counts) <= n <= counts.sum():
        raise ValueError("sample must cover all nonempty cells and fit frame")
    ideal = n * counts / counts.sum()
    out = np.minimum(counts, np.maximum(1, np.floor(ideal).astype(int)))
    while out.sum() < n:
        eligible = out < counts
        k = int(np.argmax(np.where(eligible, ideal - out, -np.inf)))
        out[k] += 1
    while out.sum() > n:
        k = int(np.argmax(np.where(out > 1, out - ideal, -np.inf)))
        out[k] -= 1
    return out


def draw_sample(cells, n, rng, stratified):
    """Return positional indices and N_h/n_h design-weight multipliers."""
    cells = np.asarray(cells)
    if not 0 < n <= len(cells):
        raise ValueError("sample size outside frame")
    if not stratified:
        ix = rng.choice(len(cells), n, replace=False)
        return ix, np.full(n, len(cells) / n)
    names, counts = np.unique(cells, return_counts=True)
    take = allocate(counts, n)
    ix, multipliers = [], []
    for name, nh, total in zip(names, take, counts):
        chosen = rng.choice(np.flatnonzero(cells == name), int(nh), replace=False)
        ix.extend(chosen)
        multipliers.extend([float(total / nh)] * int(nh))
    return np.asarray(ix), np.asarray(multipliers)


def quantile(x, w, q):
    mask = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x, w = x[mask], w[mask]
    if not len(x):
        raise ValueError("no valid answers")
    order = np.argsort(x, kind="stable")
    x, w = x[order], w[order]
    k = np.searchsorted(np.cumsum(w), q * w.sum(), side="left")
    return float(x[min(k, len(x) - 1)])


def distribution(codes, weights):
    return np.bincount(codes, weights=weights) / weights.sum()


def tvd(codes, weights, target):
    observed = np.bincount(codes, weights=weights, minlength=len(target)) / weights.sum()
    return float(np.abs(observed - target).sum() / 2)


def stats(values):
    return {"mean": float(np.mean(values)), "median": float(np.median(values)),
            "p95": float(np.quantile(values, .95)), "max": float(np.max(values))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", default="202105,202106")
    ap.add_argument("--sizes", default="73,100,300,500")
    ap.add_argument("--repeats", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--source", type=Path, default=ROOT / "data/raw/sce_audit_20260928/micro_2020_2024.xlsx")
    args = ap.parse_args()
    if args.repeats < 1:
        ap.error("repeats must be positive")
    months = sorted(set(map(int, args.months.split(","))))
    sizes = sorted(set(map(int, args.sizes.split(","))))
    print("Reading local microdata; no API calls", flush=True)
    cols = ["date", "userid", "weight", "Q9_mean"] + PROFILE_COLS + [f"Q10_{i}" for i in range(1, 11)]
    df = pd.read_excel(args.source, skiprows=1, usecols=cols)
    # Coarse employment is a declared profile grouping, not an outcome grouping.
    df["employment_coarse"] = np.where((df.Q10_1 == 1) | (df.Q10_2 == 1),
                                       "employed", np.where(df.Q10_7 == 1, "retired", "other_or_unknown"))
    panel = json.loads((ROOT / "studies/sce_inflation_expectations/population/population_main2021_a73.sampling_meta.json").read_text())
    result = {"run_id": "population_precision_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8],
              "created_at_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "seed": args.seed, "repeats": args.repeats, "sizes": sizes,
              "purpose": "A-line population design diagnostic only; official Q9_mean used solely after selection",
              "strata": "age x education x coarse employment; proportional row-count allocation; survey_weight * inverse inclusion probability",
              "limitations": ["Finite-frame sampling error, not uncertainty about the US population or LLM accuracy", "Development months only; no claim of power for subgroup effects", "Does not validate a normal-layer projection or B-line population"],
              "months": {}}
    for month in months:
        g = df[df.date == month].reset_index(drop=True)
        if g.empty or g.userid.duplicated().any() or not (np.isfinite(g.weight) & (g.weight > 0)).all():
            raise ValueError("invalid monthly frame")
        w, y = g.weight.to_numpy(float), g.Q9_mean.to_numpy(float)
        profiles = g[PROFILE_COLS + ["employment_coarse"]].fillna("unknown").astype(str)
        cells = profiles[["_AGE_CAT", "_EDU_CAT", "employment_coarse"]].agg("|".join, axis=1).to_numpy()
        codes = {col: pd.factorize(profiles[col], sort=True)[0] for col in profiles}
        margins = {col: distribution(c, w) for col, c in codes.items()}
        median = quantile(y, w, .5)
        iqr = quantile(y, w, .75) - quantile(y, w, .25)
        fixed = g.userid.isin(panel["sampled_userids"]).to_numpy()
        record = {"frame_n": len(g), "q9_valid_n": int(np.isfinite(y).sum()), "nonempty_strata": len(np.unique(cells)),
                  "full_q9_official_mean_weighted_median_pp": median,
                  "fixed_panel_n": int(fixed.sum()),
                  "fixed_panel_median_error_pp": quantile(y[fixed], w[fixed], .5) - median,
                  "designs": {}}
        for n in sizes:
            for stratified in [False, True]:
                errors, iqrs, ess, marginal = [], [], [], {col: [] for col in codes}
                for rep in range(args.repeats):
                    rng = np.random.default_rng(np.random.SeedSequence([args.seed, month, n, int(stratified), rep]))
                    ix, mult = draw_sample(cells, n, rng, stratified)
                    sw = w[ix] * mult
                    errors.append(quantile(y[ix], sw, .5) - median)
                    iqrs.append(abs(quantile(y[ix], sw, .75) - quantile(y[ix], sw, .25) - iqr))
                    ess.append(sw.sum() ** 2 / (sw @ sw))
                    for col, c in codes.items():
                        marginal[col].append(tvd(c[ix], sw, margins[col]))
                name = ("stratified" if stratified else "simple_random") + f"_n{n}"
                record["designs"][name] = {"median_absolute_error_pp": stats(np.abs(errors)),
                                           "mean_signed_error_pp": float(np.mean(errors)),
                                           "iqr_absolute_error_pp": stats(iqrs), "effective_sample_size": stats(ess),
                                           "profile_tvd": {col: stats(v) for col, v in marginal.items()}}
        result["months"][str(month)] = record
        print(f"Completed month {month}: {len(g)} respondents", flush=True)
    out = ROOT / "outputs" / result["run_id"]
    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(out, flush=True)


if __name__ == "__main__":
    main()
