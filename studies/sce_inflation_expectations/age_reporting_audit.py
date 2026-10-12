"""Evaluation-only age/rounding audit; no credentials, network or simulation providers.

Rounding transformations are measurement sensitivity scenarios, not inferred
human behaviour. All original questionnaires and the frozen scorer stay intact.
"""
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from .monthly_analysis import weighted_summary
from .scoring.sce_q9_frozen import score_q9_frozen, provenance

AGES = ("Under 40", "40 to 60", "Over 60")
FIELDS = ["date", "userid", "weight", "Q32", "_AGE_CAT", "_NUM_CAT",
          "_EDU_CAT", "_HH_INC_CAT", "Q9_mean", "Q9_iqr"] + [f"Q9_bin{i}" for i in range(1, 11)]
SOURCES = (("data/raw/sce_p_sources/micro_2017_2019.xlsx", 201701, 201912),
           ("data/raw/sce_audit_20260928/micro_2020_2024.xlsx", 202001, 202412),
           ("data/raw/sce_baselines_latest_20261007/micro_latest.xlsx", 202501, 202510))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def round_distribution(probabilities, unit=5, *, stochastic=False, rng=None):
    """Conserve 100 exactly. Deterministic largest remainder or unbiased pivotal rounding.

    For stochastic rounding, E[new bin | old vector] = old bin, independently
    of any scorer. This does not imply an unbiased fitted mean or group median.
    """
    p = np.asarray(probabilities, dtype=float)
    if p.shape != (10,) or not np.isfinite(p).all() or (p < 0).any() or (p > 100).any() or abs(p.sum()-100) > 1e-6:
        raise ValueError("requires valid ten-bin probabilities summing to 100")
    if unit <= 0 or abs(100 / unit - round(100 / unit)) > 1e-9:
        raise ValueError("unit must divide 100")
    scaled = p / unit
    low = np.floor(scaled + 1e-12).astype(int)
    frac = np.clip(scaled - low, 0, 1)
    if stochastic:
        if rng is None:
            raise ValueError("explicit RNG required")
        while True:
            active = np.flatnonzero((frac > 1e-10) & (frac < 1-1e-10))
            if len(active) < 2:
                break
            i, j = active[:2]
            plus, minus = min(1-frac[i], frac[j]), min(frac[i], 1-frac[j])
            if rng.random() < minus / (plus + minus):
                frac[i] += plus; frac[j] -= plus
            else:
                frac[i] -= minus; frac[j] += minus
        counts = low + np.rint(frac).astype(int)
    else:
        remainder = int(round(100 / unit)) - int(low.sum())
        # Equal remainders favour larger original mass, then stable bin identity.
        # That tie rule is an explicit mechanical convention, not a human trait.
        order = sorted(range(10), key=lambda i: (-frac[i], -p[i], i))
        counts = low.copy()
        if not 0 <= remainder <= 10:
            raise ValueError("invalid rounding remainder")
        counts[order[:remainder]] += 1
    result = counts.astype(float) * unit
    if (result < 0).any() or (result > 100).any() or abs(result.sum()-100) > 1e-8:
        raise ValueError("rounding failed conservation")
    return result.tolist()


def load_reference(root, out, reference_cache=None):
    registry = json.loads((root / "data/evaluation/sce_baselines_latest_20261007/micro_reference_sources.json").read_text())
    if reference_cache is not None:
        reference_cache = Path(reference_cache).resolve()
        if not reference_cache.is_relative_to(root / "outputs"):
            raise ValueError("reference cache must be an existing evaluation audit output")
        receipt = json.loads(reference_cache.with_name("extraction_receipt.json").read_text())
        if sha(reference_cache) != receipt["cache_sha256"]:
            raise ValueError("reference cache hash drift")
        for row in receipt["sources"]:
            if sha(root / row["path"]) != row["sha256"] or registry["sources"][row["path"]] != row["sha256"]:
                raise ValueError("cached official source drift")
        df = pd.read_parquet(reference_cache)
        if list(df.columns) != FIELDS or len(df) != receipt["rows"] or df.duplicated(["date", "userid"]).any():
            raise ValueError("cached extraction structure drift")
        dump(out / "reference_reuse_receipt.json", {"path": str(reference_cache.relative_to(root)), "sha256": sha(reference_cache), "original_extraction": receipt})
        return df, receipt["sources"]
    records, audit = [], []
    for name, start, end in SOURCES:
        source = root / name
        if sha(source) != registry["sources"][name]:
            raise ValueError("official workbook hash drift: " + name)
        book = load_workbook(source, read_only=True, data_only=True)
        it = book[book.sheetnames[0]].iter_rows(values_only=True)
        next(it); header = list(next(it))
        positions = {field: header.index(field) for field in FIELDS}
        selected = 0
        for row in it:
            month = row[positions["date"]]
            if not isinstance(month, (int, float)) or not start <= month <= end:
                continue
            records.append({k: row[v] for k, v in positions.items()}); selected += 1
        book.close()
        audit.append({"path": name, "sha256": registry["sources"][name], "partition": [start, end], "rows": selected})
        print("reference partition", start, end, selected, flush=True)
    df = pd.DataFrame(records, columns=FIELDS)
    if df.duplicated(["date", "userid"]).any():
        raise ValueError("duplicate respondent-month")
    df["date"] = df.date.astype(int)
    for name in ("weight", "Q32", "Q9_mean", "Q9_iqr") + tuple(f"Q9_bin{i}" for i in range(1, 11)):
        df[name] = pd.to_numeric(df[name], errors="coerce")
    df.to_parquet(out / "reference_private.parquet", index=False)
    return df, audit


def age_statistics(df):
    valid = df[np.isfinite(df.Q9_mean) & np.isfinite(df.weight) & (df.weight > 0) & df._AGE_CAT.isin(AGES)].copy()
    monthly = []
    for month, block in valid.groupby("date"):
        groups = {age: weighted_summary(block.loc[block._AGE_CAT == age, "Q9_mean"],
                    block.loc[block._AGE_CAT == age, "weight"]) for age in AGES}
        for age in AGES:
            cell = block.loc[block._AGE_CAT == age].sort_values("Q9_mean")
            values, weights = cell.Q9_mean.to_numpy(), cell.weight.to_numpy()
            cumulative = np.cumsum(weights)
            quartiles = [values[min(np.searchsorted(cumulative, q*cumulative[-1], side="left"), len(values)-1)] for q in (.25, .75)]
            groups[age]["weighted_IQR_pp"] = float(quartiles[1]-quartiles[0])
        monthly.append({"month": int(month), "groups": groups,
                        "old_minus_young_median_pp": groups[AGES[2]]["weighted_median_pp"] - groups[AGES[0]]["weighted_median_pp"]})
    yearly = []
    for year in sorted(valid.date.floordiv(100).unique()):
        part = [r for r in monthly if r["month"] // 100 == year]
        yearly.append({"year": int(year), "n_months": len(part), "groups": {age: {
            "average_monthly_weighted_median_pp": float(np.mean([r["groups"][age]["weighted_median_pp"] for r in part])),
            "respondent_months": sum(r["groups"][age]["n_valid"] for r in part)} for age in AGES},
            "average_old_minus_young_median_pp": float(np.mean([r["old_minus_young_median_pp"] for r in part]))})
    gaps = np.asarray([r["old_minus_young_median_pp"] for r in monthly])
    # A feasibility count only: no age/year is added to a model persona.
    seen, entry_available = {}, 0
    for row in df.sort_values(["date", "userid"])[["date", "userid", "Q32"]].itertuples(index=False, name=None):
        date, person, age = row
        index = int(date)//100*12 + int(date)%100
        if np.isfinite(age) and 18 <= age <= 110:
            seen[person] = index
        if person in seen and 0 <= index-seen[person] <= 12:
            entry_available += 1
    # Education-standardized descriptive contrasts: fixed shares, observed groups.
    education = ("High School", "Some College", "College")
    edref = valid[valid._EDU_CAT.isin(education)].copy()
    edref["mw"] = edref.weight / edref.groupby("date").weight.transform("sum")
    shares = {e: float(edref.loc[edref._EDU_CAT == e, "mw"].sum() / edref.mw.sum()) for e in education}
    standardized = []
    for month, block in edref.groupby("date"):
        per_age = {}
        for age in AGES:
            cells = [block[(block._AGE_CAT == age) & (block._EDU_CAT == e)] for e in education]
            if any(len(c) < 10 for c in cells):
                continue
            values = np.concatenate([c.Q9_mean.to_numpy() for c in cells])
            weights = np.concatenate([c.weight.to_numpy() / c.weight.sum() * shares[e] for c, e in zip(cells, education)])
            per_age[age] = weighted_summary(values, weights)["weighted_median_pp"]
        if set(per_age) == set(AGES):
            standardized.append({"month": int(month), "groups": per_age,
                                 "old_minus_young_median_pp": per_age[AGES[2]]-per_age[AGES[0]]})
    return {"rows": len(df), "valid_age_Q9_weight_rows": len(valid), "months": len(monthly),
            "date_range": [int(df.date.min()), int(df.date.max())], "monthly": monthly, "yearly": yearly,
            "old_minus_young_median_gap_average_pp": float(gaps.mean()),
            "old_below_young_month_share": float(np.mean(gaps < 0)),
            "age_group_median_range_month_average_pp": float(np.mean([
                max(r["groups"][a]["weighted_median_pp"] for a in AGES)-min(r["groups"][a]["weighted_median_pp"] for a in AGES) for r in monthly])),
            "education_standardization": {"fixed_shares": shares, "monthly": standardized,
                "average_old_minus_young_pp": float(np.mean([r["old_minus_young_median_pp"] for r in standardized]))},
            "direct_age_Q32_valid_rows": int(((df.Q32 >= 18) & (df.Q32 <= 110)).sum()),
            "past_entry_Q32_within_12months_available_rows": entry_available,
            "within_age_weighted_IQR_month_average_pp": {age: float(np.mean([r["groups"][age]["weighted_IQR_pp"] for r in monthly])) for age in AGES},
            "limits": ["Official derived Q9 means from current files; not frozen approximate refits.",
                       "Annual values are equal-month averages of subgroup monthly medians, not published annual SCE indices.",
                       "2025 covers January–October only. Repeated people are respondent-months, not independent people.",
                       "Age, generation and period are intertwined; differences do not identify lifetime-experience causality.",
                       "Fixed pooled education shares are descriptive, not a future-prediction population estimate."]}


def reporting_statistics(df):
    p = df[[f"Q9_bin{i}" for i in range(1, 11)]].to_numpy(float)
    ok = np.isfinite(p).all(axis=1) & (p >= 0).all(axis=1) & (p <= 100).all(axis=1) & (np.abs(p.sum(axis=1)-100) <= 1e-6)
    ok &= np.isfinite(df.weight.to_numpy()) & (df.weight.to_numpy() > 0)
    d = df.loc[ok].copy(); p = p[ok]
    allowed = {"_AGE_CAT": AGES, "_NUM_CAT": ("High", "Low"),
               "_EDU_CAT": ("High School", "Some College", "College"),
               "_HH_INC_CAT": ("Under 50k", "50k to 100k", "Over 100k")}
    for col, levels in allowed.items():
        d[col] = d[col].where(d[col].isin(levels))
    for unit in (1, 5, 10):
        d[f"grid{unit}"] = np.all(np.isclose(p/unit, np.rint(p/unit), atol=1e-8, rtol=0), axis=1)
    d["zero_deflation"] = p[:, 5:].sum(axis=1) == 0
    d["nonzero_bins"] = (p > 0).sum(axis=1)
    d["grid_class"] = np.where(d.grid10, "10", np.where(d.grid5, "5_only", "finer_than_5"))
    d["mw"] = d.weight / d.groupby("date").weight.transform("sum")
    features = ("grid5", "grid10", "zero_deflation", "nonzero_bins")
    groups = {}
    for col in ("_AGE_CAT", "_NUM_CAT", "_EDU_CAT", "_HH_INC_CAT"):
        groups[col] = {str(key): {"rows": len(b), **{k: float(np.average(b[k], weights=b.mw)) for k in features}} for key, b in d.groupby(col)}
    bases = {"_AGE_CAT": AGES[0], "_NUM_CAT": "High", "_EDU_CAT": "College", "_HH_INC_CAT": "Over 100k"}
    complete = d.dropna(subset=list(bases)).copy()
    arrays, names = [], []
    for col, base in bases.items():
        for level in sorted(set(complete[col]) - {base}):
            arrays.append((complete[col] == level).to_numpy(float)); names.append(col+":"+str(level))
    x = np.column_stack(arrays); y = complete.grid5.to_numpy(float, copy=True)
    weights = complete.weight.to_numpy(float, copy=True)
    dates = complete.date.to_numpy()
    for month in np.unique(dates):
        ix = dates == month; weights[ix] /= weights[ix].sum()
        x[ix] -= np.average(x[ix], axis=0, weights=weights[ix])
        y[ix] -= np.average(y[ix], weights=weights[ix])
    gram = x.T @ (weights[:, None]*x)
    beta = np.linalg.lstsq(gram, x.T @ (weights*y), rcond=None)[0]
    # Person-cluster sandwich, accounting for the rotating repeated panel.
    clusters, index = np.unique(complete.userid.to_numpy(), return_inverse=True)
    scores = weights[:, None] * x * (y-x@beta)[:, None]
    clustered = np.zeros((len(clusters), len(names)))
    np.add.at(clustered, index, scores)
    bread = np.linalg.pinv(gram)
    cov = bread @ (clustered.T @ clustered) @ bread
    se = np.sqrt(np.maximum(np.diag(cov), 0))
    adjusted = [{"term": name, "difference_percentage_points": float(100*b),
                 "approx_person_cluster_95_interval_pp": [float(100*(b-1.96*s)), float(100*(b+1.96*s))]}
                for name, b, s in zip(names, beta, se)]
    panel = d.sort_values(["userid", "date"]).copy()
    panel["month_index"] = panel.date.floordiv(100)*12 + panel.date.mod(100)
    panel["prior_month"] = panel.groupby("userid").month_index.shift()
    panel["prior_class"] = panel.groupby("userid").grid_class.shift()
    pairs = panel.loc[panel.month_index-panel.prior_month == 1]
    transition = pd.crosstab(pairs.prior_class, pairs.grid_class).reindex(index=["10", "5_only", "finer_than_5"], columns=["10", "5_only", "finer_than_5"], fill_value=0)
    t = transition.to_numpy(); same = float(np.trace(t)/t.sum())
    chance = float((t.sum(axis=1)/t.sum()) @ (t.sum(axis=0)/t.sum()))
    return {"valid_raw_rows": len(d), "invalid_or_weight_excluded_rows": len(df)-len(d), "groups": groups,
            "overall_equal_month": {k: float(np.average(d[k], weights=d.mw)) for k in features},
            "adjusted_grid5_linear_probability_model": {"bases": bases, "rows": len(complete), "person_clusters": len(clusters),
                "month_fixed_effects": True, "matrix_rank": int(np.linalg.matrix_rank(gram)), "parameters": len(names), "terms": adjusted,
                "within_month_R2": float(1 - np.sum(weights*(y-x@beta)**2)/np.sum(weights*y**2))},
            "adjacent_month_stability": {"pairs": len(pairs), "class_order": list(transition.index), "transition_counts": t.tolist(),
                "exact_grid_class_agreement": same, "chance_from_marginals": chance, "kappa": (same-chance)/(1-chance)},
            "limits": ["All bins lying on a 5/10 grid are a response pattern, not an identified psychological rounding type.",
                       "Shape/concentration of beliefs can itself create grid patterns; no causal numeracy effect is claimed.",
                       "Adjusted differences use a descriptive weighted linear probability model, not prediction or persona calibration.",
                       "Confidence intervals are asymptotic person-cluster diagnostics, not official survey design intervals."]}


@lru_cache(maxsize=12000)
def fit_cached(bins):
    return score_q9_frozen(list(bins))


def rounding_sensitivity(root, out):
    trial = root / "outputs/sce_confidence_trial_20261011_v1"
    analysis = root / "outputs/sce_confidence_analysis_20261011_v2"
    plan = json.loads((trial / "trial_manifest.json").read_text())
    result = json.loads((analysis / "summary.json").read_text())
    private = json.loads((analysis / "paired_evaluation_private.json").read_text())
    lookup = {(r["month"], r["repeat"], r["agent_id"]): r for r in private if r["measure"] == "Q9"}
    original_hashes = result["scorer"]["live_sha256"]
    if provenance()["live_sha256"] != original_hashes:
        raise ValueError("scorer changed since original analysis")
    scenarios = (("deterministic_5", 5, False), ("deterministic_10", 10, False), ("balanced_random_5", 5, True))
    rng = np.random.default_rng(104729)
    records, source_audit = [], []
    for job in plan["jobs"]:
        path = root / "outputs/local_runs" / job["run_id"] / "llm_calls.jsonl"
        prior = next(r for r in result["runs"] if all(r[k] == job[k] for k in ("month", "arm", "repeat")))
        if sha(path) != prior["llm_calls_sha256"]:
            raise ValueError("saved model answers changed")
        source_audit.append({"path": str(path.relative_to(root)), "sha256": sha(path)})
        for call in map(json.loads, path.read_text().splitlines()):
            q = json.loads(call["raw_response_text"])["q9"]
            p = [q[f"bin{i}"] for i in range(1, 11)]
            if abs(sum(p)-100) > 1e-6:
                continue
            original = fit_cached(tuple(p))
            ref = lookup[(job["month"], job["repeat"], call["agent_id"])]
            if original.status != "ok" or not np.isfinite(original.mean):
                continue
            if ref[job["arm"]] is not None and abs(original.mean-ref[job["arm"]]) > 1e-9:
                raise ValueError("original score did not reproduce")
            for scenario, unit, stochastic in scenarios:
                rounded = round_distribution(p, unit, stochastic=stochastic, rng=rng if stochastic else None)
                score = fit_cached(tuple(rounded))
                records.append({"month": job["month"], "arm": job["arm"], "repeat": job["repeat"], "scenario": scenario,
                    "private_agent_id": call["agent_id"], "weight": ref["weight"], "profile": ref["profile"],
                    "original_mean": original.mean, "original_density_median": original.p50,
                    "rounded_mean": score.mean, "rounded_density_median": score.p50, "status": score.status,
                    "original_family": original.family, "rounded_family": score.family,
                    "original_nonzero": sum(x > 0 for x in p), "rounded_nonzero": sum(x > 0 for x in rounded),
                    "L1_probability_change": float(np.abs(np.asarray(p)-rounded).sum()/100)})
        print("sensitivity cell", job["month"], job["arm"], job["repeat"], "cached fits", fit_cached.cache_info().currsize, flush=True)
    dump(out / "rounding_private.json", records)
    cells = []
    for job in plan["jobs"]:
        for scenario, _, _ in scenarios:
            subset = [r for r in records if all(r[k] == job[k] for k in ("month", "arm", "repeat")) and r["scenario"] == scenario]
            valid = [r for r in subset if r["status"] == "ok" and all(v is not None and np.isfinite(v) for v in (r["rounded_mean"], r["rounded_density_median"]))]
            a, b = np.asarray([r["original_mean"] for r in valid]), np.asarray([r["rounded_mean"] for r in valid])
            delta = b-a
            median_change = float(np.median(b)-np.median(a))
            w = [r["weight"] for r in valid]
            weighted_change = weighted_summary(b, w)["weighted_median_pp"]-weighted_summary(a, w)["weighted_median_pp"]
            cells.append({**{k: job[k] for k in ("month", "arm", "repeat")}, "scenario": scenario,
                "n_original_valid": len(subset), "n_paired_valid": len(valid), "fit_status_counts": dict(Counter(r["status"] for r in subset)),
                "group_median_shift_pp": median_change, "group_weighted_median_shift_auxiliary_pp": weighted_change,
                "individual_mean_abs_shift_median_pp": float(np.median(abs(delta))),
                "individual_mean_abs_shift_p95_pp": float(np.quantile(abs(delta), .95)),
                "individual_mean_abs_shift_max_pp": float(np.max(abs(delta))),
                "individual_density_median_abs_shift_median_pp": float(np.median([abs(r["rounded_density_median"]-r["original_density_median"]) for r in valid])),
                "family_change_share": float(np.mean([r["original_family"] != r["rounded_family"] for r in valid])),
                "nonzero_median_before": float(np.median([r["original_nonzero"] for r in valid])),
                "nonzero_median_after": float(np.median([r["rounded_nonzero"] for r in valid]))})
    aggregate = {}
    for scenario, _, _ in scenarios:
        rows = [r for r in cells if r["scenario"] == scenario]
        rec = [r for r in records if r["scenario"] == scenario and r["status"] == "ok"]
        aggregate[scenario] = {"cells": len(rows), "group_absolute_shift_mean_pp": float(np.mean([abs(r["group_median_shift_pp"]) for r in rows])),
            "group_absolute_shift_max_pp": float(np.max([abs(r["group_median_shift_pp"]) for r in rows])),
            "group_signed_shift_mean_pp": float(np.mean([r["group_median_shift_pp"] for r in rows])),
            "weighted_group_absolute_shift_mean_auxiliary_pp": float(np.mean([abs(r["group_weighted_median_shift_auxiliary_pp"]) for r in rows])),
            "individual_abs_mean_shift_median_pp": float(np.median([abs(r["rounded_mean"]-r["original_mean"]) for r in rec])),
            "individual_abs_mean_shift_p95_pp": float(np.quantile([abs(r["rounded_mean"]-r["original_mean"]) for r in rec], .95)),
            "individual_abs_mean_shift_max_pp": float(np.max([abs(r["rounded_mean"]-r["original_mean"]) for r in rec]))}
    return {"original_answers": 768, "original_invalid_sum_excluded": 1, "cells": cells, "aggregate": aggregate,
            "source_audit": source_audit, "seed": 104729, "scorer": provenance(),
            "limits": ["Mechanical changes to previously saved model answers, not a new LLM or human behaviour experiment.",
                       "Four selected months, 48 people per month, two generations are not a national population or independent new people.",
                       "Balanced random rounding is unbiased in each raw bin only; one seed does not estimate its expected fitted-score effect.",
                       "5/10-unit rounding is a sensitivity choice, not an estimated human style distribution.",
                       "Weighted medians are auxiliary same-sample summaries, not official headline reconstructions."]}


def plot(result, out):
    import os
    os.environ.setdefault("MPLCONFIGDIR", str(out / "matplotlib_cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": ["Arial Unicode MS", "PingFang SC", "sans-serif"],
                         "axes.unicode_minus": False, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(figsize=(11, 4.6), constrained_layout=True)
    dates = pd.to_datetime([str(r["month"]) for r in result["age"]["monthly"]], format="%Y%m")
    for age, name, color in zip(AGES, ("40岁以下", "40—60岁", "60岁以上"), ("#286c68", "#888888", "#a46032")):
        ax.plot(dates, [r["groups"][age]["weighted_median_pp"] for r in result["age"]["monthly"]], label=name, color=color)
    ax.set(title="不同年龄组的一年期通胀预期：按月比较", xlabel="调查月（2017-01至2025-10）", ylabel="个人密度均值的调查加权中位数（%）")
    ax.legend(); ax.grid(alpha=.15)
    fig.savefig(out / "age_monthly.png", dpi=160); plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4.5), constrained_layout=True)
    terms = result["reporting"]["adjusted_grid5_linear_probability_model"]["terms"]
    translations = {"_AGE_CAT:40 to 60": "40—60岁（对40岁以下）", "_AGE_CAT:Over 60": "60岁以上（对40岁以下）",
        "_NUM_CAT:Low": "低数理能力（对高）", "_EDU_CAT:High School": "高中教育组（对大学）",
        "_EDU_CAT:Some College": "部分大学教育（对大学）", "_HH_INC_CAT:50k to 100k": "收入5万—10万美元（对10万以上）",
        "_HH_INC_CAT:Under 50k": "收入5万美元以下（对10万以上）"}
    labels = [translations.get(r["term"], r["term"]) for r in terms]
    for i, row in enumerate(terms):
        lo, hi = row["approx_person_cluster_95_interval_pp"]
        ax.hlines(i, lo, hi, color="#286c68"); ax.scatter(row["difference_percentage_points"], i, color="#286c68")
    ax.set_yticks(range(len(terms)), labels); ax.invert_yaxis(); ax.axvline(0, linestyle="--", color="#999999")
    ax.set(title="全部概率落在5%网格上的比例：人口关联", xlabel="控制月份和图中其它特征后的比例差（百分点）；线为近似人员聚类95%区间")
    fig.savefig(out / "reporting_demographics.png", dpi=160); plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    scenarios = list(result["rounding"]["aggregate"])
    for j, key in enumerate(scenarios):
        rows = [r for r in result["rounding"]["cells"] if r["scenario"] == key]
        ax.scatter(np.arange(len(rows))+.13*(j-1), [r["group_median_shift_pp"] for r in rows], label=key, s=24)
    ax.axhline(0, color="#999999", linestyle="--")
    ax.set(title="概率取整后，群体指标并不保证不变", xlabel="16个原实验单元（四时期×两组×两次生成）", ylabel="取整后的群体中位数 − 原群体中位数（个百分点）")
    ax.legend(); ax.grid(alpha=.15)
    fig.savefig(out / "rounding_group_shifts.png", dpi=160); plt.close(fig)


def run(root, out, reference_cache=None):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("fresh ignored output directory required")
    protected = json.loads((root / "docs/sources/sol_handoff_protected_files_20261010.json").read_text())["files_sha256"]
    if any(sha(root/p) != h for p, h in protected.items()):
        raise ValueError("protected file drift")
    out.mkdir(parents=True)
    df, sources = load_reference(root, out, reference_cache)
    result = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "new_api_calls": 0, "new_api_cost_usd": 0,
              "official_sources": sources, "code_sha256": sha(Path(__file__)),
              "age": age_statistics(df), "reporting": reporting_statistics(df), "rounding": rounding_sensitivity(root, out)}
    dump(out / "summary.json", result)
    plot(result, out)
    if any(sha(root/p) != h for p, h in protected.items()):
        raise ValueError("protected file changed during audit")
    print(json.dumps({"age_months": result["age"]["months"], "rounding": result["rounding"]["aggregate"], "new_api_calls": 0}, ensure_ascii=False), flush=True)
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--reference-cache", type=Path)
    a = parser.parse_args()
    run(Path(__file__).resolve().parents[2], a.out, a.reference_cache)


if __name__ == "__main__":
    main()
