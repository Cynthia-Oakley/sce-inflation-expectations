"""Registered, offline personal reporting-grid sensitivity on saved answers.

Private histories only enter style assignment before scoring current outcomes.
Original answers, prior experiment configs and scorer sources remain unchanged.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .analysis import BIN_FIELDS, CLASS_NAMES, classify, dump, sha, state_keys
from ..evaluation.metrics import wasserstein1
from ..scoring.sce_q9_frozen import provenance, score_q9_frozen


METRICS = ("sample_center_mae_pp", "cross_section_w1_pp", "cross_person_iqr_gap_pp",
           "delta_w1_pp", "cross_person_iqr_pp", "real_cross_person_iqr_pp",
           "center_bias_pp", "individual_mae_pp")


def map_probabilities(probabilities, style):
    """Largest-remainder integer allocation, including a no-transformation style."""
    p = np.asarray(probabilities, float)
    ok, _ = classify(p.reshape(1, -1))
    if not ok[0] or style not in (0, 1, 2):
        raise ValueError("Invalid ten-bin answer or style")
    if style == 0:
        return p.copy()
    grid = (5, 10)[style - 1]
    units = p / p.sum() * (100 // grid)
    integers = np.floor(units).astype(int)
    left = 100 // grid - int(integers.sum())
    order = np.argsort(-(units - integers), kind="stable")
    integers[order[:left]] += 1
    result = (integers * grid).astype(float)
    if result.sum() != 100 or not ((result >= 0) & (result <= 100)).all():
        raise AssertionError("Probability conservation failed")
    return result


def history_profiles(reference, subjects, tables, prior_mass=3):
    """Target profiles read no target/future answers, demographics or weights."""
    if reference.duplicated(["userid", "date"]).any():
        raise ValueError("Duplicate reference person-month")
    records = []
    for subject in subjects:
        person, month = int(subject["userid"]), int(subject["month"])
        older = reference[(reference.userid == person) & (reference.date < month)].copy()
        valid, labels = classify(older[BIN_FIELDS].to_numpy(float))
        w = pd.to_numeric(older.weight, errors="coerce").to_numpy(float)
        mask = valid & np.isfinite(w) & (w > 0)
        older = older.loc[mask].assign(observed_class=labels[mask]).sort_values("date")
        counts = np.bincount(older.observed_class.to_numpy(int), minlength=3)
        if len(older):
            last = older.iloc[-1]
            bins = last[BIN_FIELDS].to_numpy(float)
            state = {"previous_nonzero": int((bins > 0).sum()),
                     "previous_Q9_iqr": float(last.Q9_iqr),
                     "previous_max_mass": float(bins.max())}
            previous_date = int(last.date)
        else:
            state = {k: np.nan for k in
                     ("previous_nonzero", "previous_Q9_iqr", "previous_max_mass")}
            previous_date = None
        key = state_keys(pd.DataFrame([state]), tables["cuts"]).iloc[0]
        base = np.asarray(tables["state"].get(key, tables["population"]), float)
        q = (prior_mass * base + counts) / (prior_mass + counts.sum())
        if not np.isclose(q.sum(), 1) or (q < 0).any():
            raise ValueError("Invalid style probabilities")
        records.append({**subject, "past_n": len(older), "previous_valid_date": previous_date,
                        "state_key": key, "history_counts": counts.tolist(),
                        "class_probabilities": q.tolist()})
    return records


def assign_styles(profiles, seed):
    result = []
    for profile in profiles:
        key = f"{seed}:{int(profile['userid'])}:reporting-style-v1".encode()
        integer = int.from_bytes(hashlib.sha256(key).digest()[:8], "big") >> 11
        uniform = integer / 2**53
        q = np.asarray(profile["class_probabilities"])
        result.append(min(int(np.searchsorted(q.cumsum(), uniform, side="right")), 2))
    return np.array(result, int)


def permute_styles(profiles, styles, draws, seed):
    rng = np.random.default_rng(seed)
    months = np.array([int(p["month"]) for p in profiles])
    result = np.tile(styles, (draws, 1))
    for row in result:
        for month in sorted(set(months)):
            idx = np.flatnonzero(months == month)
            row[idx] = rng.permutation(styles[idx])
            if not np.array_equal(np.bincount(row[idx], minlength=3),
                                  np.bincount(styles[idx], minlength=3)):
                raise AssertionError("Permutation changed style proportions")
    return result


def _quantile_rows(values, weights, fraction):
    order = np.argsort(values, kind="stable")
    cumulative = weights[:, order].cumsum(axis=1)
    thresholds = weights.sum(axis=1)[:, None] * fraction
    indices = np.argmax(cumulative >= thresholds, axis=1)
    return np.asarray(values)[order[indices]]


def _w1_rows(predicted, actual, weights):
    support = np.unique(np.r_[predicted, actual])
    if len(support) < 2:
        return np.zeros(len(weights))
    edges = support[:-1]
    difference = ((predicted[None, :] <= edges[:, None]).astype(float)
                  - (actual[None, :] <= edges[:, None]).astype(float))
    cdf_difference = weights @ difference.T / weights.sum(axis=1)[:, None]
    return np.abs(cdf_difference) @ np.diff(support)


def cell_metrics(predicted, actual, previous, weights=None):
    """Same-weight ECDF metrics, vectorized over respondent bootstrap draws."""
    predicted, actual, previous = map(lambda v: np.asarray(v, float),
                                      (predicted, actual, previous))
    if not (predicted.shape == actual.shape == previous.shape) or predicted.ndim != 1:
        raise ValueError("Require matched one-dimensional centers")
    if not all(np.isfinite(v).all() for v in (predicted, actual, previous)):
        raise ValueError("Nonfinite centers")
    w = np.ones((1, len(actual))) if weights is None else np.atleast_2d(weights).astype(float)
    if w.shape[1] != len(actual) or (w < 0).any() or (w.sum(axis=1) <= 0).any():
        raise ValueError("Invalid bootstrap weights")
    pred_median, real_median = (_quantile_rows(v, w, .5) for v in (predicted, actual))
    pred_iqr = _quantile_rows(predicted, w, .75) - _quantile_rows(predicted, w, .25)
    real_iqr = _quantile_rows(actual, w, .75) - _quantile_rows(actual, w, .25)
    return {
        "sample_center_mae_pp": np.abs(pred_median - real_median),
        "cross_section_w1_pp": _w1_rows(predicted, actual, w),
        "cross_person_iqr_gap_pp": np.abs(pred_iqr - real_iqr),
        "delta_w1_pp": _w1_rows(predicted - previous, actual - previous, w),
        "cross_person_iqr_pp": pred_iqr, "real_cross_person_iqr_pp": real_iqr,
        "center_bias_pp": pred_median - real_median,
        "individual_mae_pp": w @ np.abs(predicted - actual) / w.sum(axis=1),
    }


@lru_cache(maxsize=None)
def _fit(probabilities):
    p = np.asarray(probabilities, float)
    if p.shape != (10,) or not classify(p.reshape(1, -1))[0][0]:
        return {"mean": None, "iqr": None, "family": None, "status": "invalid_bins"}
    score = score_q9_frozen(p.tolist())
    return {"mean": None if score.mean is None or not np.isfinite(score.mean) else float(score.mean),
            "iqr": None if score.iqr is None or not np.isfinite(score.iqr) else float(score.iqr),
            "family": score.family, "status": score.status}


def _previous_month(month):
    year, number = divmod(int(month), 100)
    return (year - 1) * 100 + 12 if number == 1 else year * 100 + number - 1


def prepare_cases(root, protocol):
    for key in ("source_cache", "answers", "links", "fitted_tables"):
        if sha(root / protocol[key]) != protocol[key + "_sha256"]:
            raise ValueError(f"Source drift: {key}")
    parent = json.loads((root / protocol["parent_protocol"]).read_text())
    if parent["train"] != protocol["training"] or parent["personal_prior_mass"] != 3:
        raise ValueError("Parent training specification changed")
    reference = pd.read_parquet(root / protocol["source_cache"])
    links = json.loads((root / protocol["links"]).read_text())
    subjects = []
    for link in links:
        source = str(link["source_agent_id"])
        if not source.startswith("sce_u"):
            raise ValueError("Unexpected link identifier")
        subjects.append({"userid": int(source[5:]), "month": int(link["month"]),
                         "agent_id": link["agent_id"]})
    subjects.sort(key=lambda p: (p["month"], p["userid"]))
    if len(subjects) != protocol["expected_person_months_before_eligibility"]:
        raise ValueError("Roster size changed")
    keys = {(p["month"], p["agent_id"]): i for i, p in enumerate(subjects)}
    if len(keys) != len(subjects):
        raise ValueError("Duplicate roster link")
    tables = json.loads((root / protocol["fitted_tables"]).read_text())
    profiles = history_profiles(reference, subjects, tables, parent["personal_prior_mass"])
    lookup = reference.set_index(["userid", "date"])
    rows = [r for r in json.loads((root / protocol["answers"]).read_text()) if r["measure"] == "Q9"]
    if sorted({int(r["month"]) for r in rows}) != protocol["months"] or sorted({r["repeat"] for r in rows}) != protocol["generation_repeats"]:
        raise ValueError("Target months or repeats changed")
    rows.sort(key=lambda r: (int(r["month"]), r["repeat"], keys[int(r["month"]), r["agent_id"]]))
    cases, mapped = [], []
    for row in rows:
        subject_idx = keys[int(row["month"]), row["agent_id"]]
        person = subjects[subject_idx]["userid"]
        month = int(row["month"])
        real = lookup.loc[person, month][BIN_FIELDS].to_numpy(float)
        previous = lookup.loc[person, _previous_month(month)][BIN_FIELDS].to_numpy(float)
        actual, old = _fit(tuple(real)), _fit(tuple(previous))
        record = {"userid": person, "month": month, "repeat": int(row["repeat"]),
                  "subject_idx": subject_idx, "real_mean": actual["mean"],
                  "previous_mean": old["mean"], "real_bins": real.tolist(),
                  "eligible": actual["mean"] is not None and old["mean"] is not None}
        for arm in protocol["model_arms"]:
            raw = row["raw_answers"][arm]
            fitted = []
            for mode in range(3):
                transformed = None if raw is None else map_probabilities(raw, mode)
                score = _fit(tuple(transformed)) if transformed is not None else _fit(tuple([np.nan] * 10))
                fitted.append(score)
                mapped.append({"case_index": len(cases), "userid": person, "month": month,
                               "repeat": int(row["repeat"]), "arm": arm, "style": mode,
                               "probabilities": None if transformed is None else transformed.tolist(), **score})
            record[arm] = fitted
            record["eligible"] &= all(s["mean"] is not None for s in fitted)
            if fitted[0]["mean"] is not None and row[arm] is not None and abs(fitted[0]["mean"] - row[arm]) > 1e-8:
                raise AssertionError("Native frozen score changed")
        cases.append(record)
    if len({(r["month"], r["repeat"], r["userid"]) for r in cases}) != len(cases):
        raise ValueError("Duplicate evaluation case")
    return profiles, cases, mapped


def _condition_summary(cases, centers, per_case_styles, mode_records, arm):
    cells = []
    for month, repeat in sorted({(r["month"], r["repeat"]) for r in cases}):
        idx = np.array([i for i, r in enumerate(cases) if (r["month"], r["repeat"]) == (month, repeat)])
        real = np.array([cases[i]["real_mean"] for i in idx])
        previous = np.array([cases[i]["previous_mean"] for i in idx])
        pred = centers[idx]
        metrics = {key: float(value[0]) for key, value in cell_metrics(pred, real, previous).items()}
        fitted = [mode_records[i][arm][int(per_case_styles[i])] for i in idx]
        bins = np.array([s["probabilities"] for s in fitted])
        _, labels = classify(bins)
        metrics.update({"month": month, "repeat": repeat, "n": len(idx),
                        "observed_grid_proportions": (np.bincount(labels, minlength=3) / len(labels)).tolist(),
                        "zero_deflation_fraction": float(np.mean(bins[:, 5:].sum(axis=1) == 0)),
                        "mean_nonzero_bins": float(np.mean((bins > 0).sum(axis=1))),
                        "personal_density_iqr_mean_pp": float(np.mean([s["iqr"] for s in fitted])),
                        "family_change_fraction": float(np.mean([s["family"] != mode_records[i][arm][0]["family"] for i, s in zip(idx, fitted)])),
                        "spearman": None if len(np.unique(pred)) < 2 or len(np.unique(real)) < 2 else float(spearmanr(pred, real).statistic),
                        "centered_w1_pp": wasserstein1(pred - np.sort(pred)[(len(pred) - 1) // 2], None,
                                                       real - np.sort(real)[(len(real) - 1) // 2], None)})
        cells.append(metrics)
    aggregate = {key: float(np.mean([c[key] for c in cells])) for key in METRICS}
    for key in ("zero_deflation_fraction", "mean_nonzero_bins", "personal_density_iqr_mean_pp", "family_change_fraction", "centered_w1_pp"):
        aggregate[key] = float(np.mean([c[key] for c in cells]))
    valid_spearman = [c["spearman"] for c in cells if c["spearman"] is not None]
    aggregate["spearman"] = float(np.mean(valid_spearman)) if valid_spearman else None
    aggregate["observed_grid_proportions"] = np.mean([c["observed_grid_proportions"] for c in cells], axis=0).tolist()
    return {"aggregate": aggregate, "cells": cells}


def bootstrap_contrasts(cases, matrices, protocol):
    """Whole-person paired bootstrap; predictions fixed, both repeats retained."""
    people = sorted({r["userid"] for r in cases})
    pi = {p: i for i, p in enumerate(people)}
    rng = np.random.default_rng(protocol["bootstrap"]["seed"])
    repetitions = protocol["bootstrap"]["draws"]
    counts = rng.multinomial(len(people), np.full(len(people), 1 / len(people)), size=repetitions)
    case_counts = counts[:, [pi[r["userid"]] for r in cases]]
    cells = [np.array([i for i, r in enumerate(cases) if (r["month"], r["repeat"]) == key])
             for key in sorted({(r["month"], r["repeat"]) for r in cases})]
    keep = np.logical_and.reduce([case_counts[:, idx].sum(axis=1) > 0 for idx in cells])
    case_counts = case_counts[keep]
    contrasts = {"personal_minus_native": {}, "personal_minus_permutation_mean": {}}
    accumulated = {condition: {k: np.zeros(len(case_counts)) for k in METRICS}
                   for condition in matrices}
    for idx in cells:
        actual = np.array([cases[i]["real_mean"] for i in idx])
        previous = np.array([cases[i]["previous_mean"] for i in idx])
        for condition, predictions in matrices.items():
            draws = np.atleast_2d(predictions)
            for prediction in draws:
                result = cell_metrics(prediction[idx], actual, previous, case_counts[:, idx])
                for key in METRICS:
                    accumulated[condition][key] += result[key] / (len(cells) * len(draws))
    for label, baseline in (("personal_minus_native", "native"),
                            ("personal_minus_permutation_mean", "permutation")):
        for key in METRICS:
            difference = accumulated["personal"][key] - accumulated[baseline][key]
            contrasts[label][key] = {"interval_95": np.quantile(difference, [.025, .975]).tolist()}
    return {"persons": len(people), "draws_requested": repetitions, "draws_used": len(case_counts),
            "discarded_empty_month_draws": int((~keep).sum()), "contrasts": contrasts,
            "scope": protocol["bootstrap"]["unit"]}


def run(root, out, protocol_path):
    root, out, protocol_path = Path(root).resolve(), Path(out).resolve(), Path(protocol_path).resolve()
    if out.exists():
        raise FileExistsError("Use a fresh result directory")
    protocol = json.loads(protocol_path.read_text())
    scorer = provenance()
    if not scorer["live_matches_pinned"]:
        raise ValueError("Frozen scorer source drift")
    registry = json.loads((root / "docs/sources/sol_handoff_protected_files_20261010.json").read_text())["files_sha256"]
    if any(sha(root / path) != digest for path, digest in registry.items()):
        raise ValueError("Protected files changed")
    profiles, full_cases, mapped = prepare_cases(root, protocol)
    out.mkdir(parents=True)
    dump(out / "protocol_snapshot.json", protocol)
    dump(out / "style_profiles_private.json", profiles)
    dump(out / "mapped_variants_private.json", mapped)
    indices = [i for i, r in enumerate(full_cases) if r["eligible"]]
    cases = [full_cases[i] for i in indices]
    record_index = {(r["case_index"], r["arm"], r["style"]): r for r in mapped}
    mode_records = [{arm: [record_index[i, arm, mode] for mode in range(3)]
                     for arm in protocol["model_arms"]} for i in indices]
    subject_idx = np.array([r["subject_idx"] for r in cases])
    centers = {arm: np.array([[s["mean"] for s in r[arm]] for r in cases])
               for arm in protocol["model_arms"]}
    seed_results, assignments, bootstrap_input = {}, [], None
    for seed in protocol["style_seeds"]:
        styles = assign_styles(profiles, seed)
        permuted = permute_styles(profiles, styles, protocol["permutation"]["draws_per_style_seed"],
                                 protocol["permutation"]["seed"] + seed)
        assignments.extend({"seed": seed, "userid": p["userid"], "month": p["month"], "style": int(s)}
                           for p, s in zip(profiles, styles))
        conditions = {}
        for arm in protocol["model_arms"]:
            c = centers[arm]
            selected = styles[subject_idx]
            predictions = c[np.arange(len(cases)), selected]
            native = c[:, 0]
            records = {}
            for name, style in (("native", np.zeros(len(cases), int)),
                                ("personal_history_mapping", selected),
                                ("uniform_grid_5", np.ones(len(cases), int)),
                                ("uniform_grid_10", np.full(len(cases), 2, int))):
                records[name] = _condition_summary(cases, c[np.arange(len(cases)), style], style, mode_records, arm)
            shuffled_scores, shuffled_centers = [], []
            for draw in permuted:
                style = draw[subject_idx]
                prediction = c[np.arange(len(cases)), style]
                shuffled_centers.append(prediction)
                shuffled_scores.append(_condition_summary(cases, prediction, style, mode_records, arm)["aggregate"])
            records["permuted_history_mapping"] = {
                "aggregate": {key: float(np.mean([r[key] for r in shuffled_scores])) for key in METRICS},
                "per_draw_metrics": [{key: r[key] for key in METRICS} for r in shuffled_scores],
                "assignment_change_fraction": float(np.mean(permuted[:, subject_idx] != selected)),
            }
            for key in ("zero_deflation_fraction", "mean_nonzero_bins", "family_change_fraction"):
                records["permuted_history_mapping"]["aggregate"][key] = float(np.mean([r[key] for r in shuffled_scores]))
            records["permuted_history_mapping"]["aggregate"]["observed_grid_proportions"] = np.mean([r["observed_grid_proportions"] for r in shuffled_scores], axis=0).tolist()
            conditions[arm] = records
            if seed == protocol["primary_style_seed"] and arm == protocol["primary_model_arm"]:
                bootstrap_input = {"native": native, "personal": predictions,
                                   "permutation": np.array(shuffled_centers)}
        seed_results[str(seed)] = {"assigned_roster_style_counts": np.bincount(styles, minlength=3).tolist(),
                                   "arms": conditions}
        print(f"Completed predeclared style seed {seed}", flush=True)
    dump(out / "style_assignments_private.json", assignments)
    bootstrap = bootstrap_contrasts(cases, bootstrap_input, protocol)
    primary = seed_results[str(protocol["primary_style_seed"])]["arms"][protocol["primary_model_arm"]]
    for label, baseline in (("personal_minus_native", "native"),
                            ("personal_minus_permutation_mean", "permuted_history_mapping")):
        for key in METRICS:
            bootstrap["contrasts"][label][key]["difference"] = primary["personal_history_mapping"]["aggregate"][key] - primary[baseline]["aggregate"][key]
    summary = {"status": "completed_offline", "completed_at": datetime.now(timezone.utc).isoformat(),
               "protocol": protocol, "source_hashes": {str(p.relative_to(root)): sha(p) for p in
                    [root / protocol[k] for k in ("source_cache", "answers", "links", "fitted_tables", "parent_protocol")] + [protocol_path]},
               "code_hashes": {str(Path(__file__).resolve().relative_to(root)): sha(__file__)},
               "scorer": scorer, "protected_files_verified": len(registry),
               "coverage": {"roster_person_months": len(profiles), "input_q9_rows": len(full_cases),
                            "valid_q9_rows": len(cases), "valid_person_months": len({(r['userid'], r['month']) for r in cases}),
                            "persons": len({r['userid'] for r in cases}),
                            "excluded_rows": len(full_cases) - len(cases),
                            "mapping_only_failures": sum(r['real_mean'] is not None and r['previous_mean'] is not None and all(r[a][0]['mean'] is not None for a in protocol['model_arms']) and not r['eligible'] for r in full_cases)},
               "history": {"past_n_min": min(p['past_n'] for p in profiles),
                           "past_n_max": max(p['past_n'] for p in profiles),
                           "no_history_person_months": sum(p['past_n'] == 0 for p in profiles)},
               "results_by_seed": seed_results, "primary_bootstrap": bootstrap,
               "new_api_calls": 0, "api_cost_usd": 0,
               "original_answers_preserved": sha(root / protocol['answers']) == protocol['answers_sha256'],
               "q8_changed": False}
    dump(out / "summary.json", summary)
    print(json.dumps({"output": str(out), "coverage": summary["coverage"],
                      "primary": {k: v["aggregate"] for k, v in primary.items()}, "new_api_calls": 0}), flush=True)
    return summary
