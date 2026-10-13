"""Offline, same-cohort comparison of saved answers and past-only baselines.

No credentials, API client, or simulation engine are imported here. New answer
files are evaluation artifacts, not inputs to another simulation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from numbers import Real
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .metrics import quantile, wasserstein1
from ..reporting_behavior.mapping import cell_metrics
from ..scoring.sce_q9_frozen import provenance, score_q9_frozen

BIN_FIELDS = [f"Q9_bin{i}" for i in range(1, 11)]
MAIN = ("sample_center_mae_pp", "cross_section_w1_pp", "delta_w1_pp")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + "\n", encoding="utf-8")


def finite(value):
    return isinstance(value, Real) and not isinstance(value, bool) and bool(np.isfinite(value))


def previous_month(month):
    year, number = divmod(int(month), 100)
    if not 1 <= number <= 12:
        raise ValueError("Invalid calendar month")
    return (year - 1) * 100 + 12 if number == 1 else year * 100 + number - 1


@lru_cache(maxsize=None)
def _score(probabilities):
    p = np.asarray(probabilities, float)
    if (p.shape != (10,) or not np.isfinite(p).all() or (p < 0).any()
            or (p > 100).any() or abs(p.sum() - 100) > 1e-6):
        return {"mean": None, "iqr": None, "zero_deflation": None,
                "status": "invalid_bins"}
    result = score_q9_frozen(p.tolist())
    return {"mean": float(result.mean) if finite(result.mean) else None,
            "iqr": float(result.iqr) if finite(result.iqr) else None,
            "zero_deflation": float(p[5:].sum() == 0), "status": result.status}


def score(probabilities):
    try:
        return _score(tuple(probabilities))
    except (TypeError, ValueError):
        return _score(tuple([np.nan] * 10))


def history_baselines(reference, subjects, coefficient=.5):
    """Predictions use only the respondent's strictly earlier raw Q9 answers."""
    if not 0 <= coefficient <= 1:
        raise ValueError("Invalid fixed coefficient")
    if reference.duplicated(["userid", "date"]).any():
        raise ValueError("Duplicate reference person-month")
    result = []
    for subject in subjects:
        month, uid = int(subject["month"]), int(subject["userid"])
        history = reference[(reference.userid == uid) & (reference.date < month)]
        history = history.sort_values("date")
        values, previous = [], None
        for row in history.to_dict("records"):
            value = score([row[f] for f in BIN_FIELDS])["mean"]
            if finite(value):
                values.append(value)
                if int(row["date"]) == previous_month(month):
                    previous = value
        anchor = float(np.mean(values)) if len(values) >= 2 else None
        updated = (previous + coefficient * (anchor - previous)
                   if previous is not None and anchor is not None else previous)
        result.append({**subject, "history_n": len(values), "anchor": anchor,
                       "copy_previous": previous, "history_anchor_half": updated})
    return result


def import_extra(answer_path, manifest_path, subjects, protocol):
    """Accept registered aliases only; missing/invalid responses remain failures."""
    manifest = json.loads(Path(manifest_path).read_text())
    required = {"answers_sha256", "research_line", "months", "repeats", "arms",
                "model_requested", "temperature", "run_ids"}
    if required - manifest.keys():
        raise ValueError("Extra answer manifest missing required provenance")
    if sha(answer_path) != manifest["answers_sha256"]:
        raise ValueError("Extra answers hash mismatch")
    if (manifest["research_line"] != protocol["research_line"]
            or manifest["months"] != protocol["months"]
            or manifest["repeats"] != protocol["generation_repeats"]):
        raise ValueError("New results must use the registered cohort/time design")
    arms = manifest["arms"]
    reserved = set(protocol["llm_arms"] + protocol["baseline_arms"])
    if (not arms or len(set(arms)) != len(arms) or reserved.intersection(arms)
            or any(not isinstance(a, str) or not a for a in arms)):
        raise ValueError("New arm names duplicate/reserve existing conditions")
    if not manifest["run_ids"] or not manifest["model_requested"]:
        raise ValueError("Run/model provenance required")
    design = protocol.get("frozen_llm")
    if design and (manifest["model_requested"] != design["model_requested"]
                   or manifest["temperature"] != design["temperature"]):
        raise ValueError("New condition changes the registered model/temperature")
    allowed = {(int(s["month"]), s["agent_id"], r, arm)
               for s in subjects for r in protocol["generation_repeats"] for arm in arms}
    records = {}
    for line in Path(answer_path).read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        key = (int(row["month"]), row["agent_id"], int(row["repeat"]), row["arm"])
        if key not in allowed or key in records:
            raise ValueError("Unknown/duplicate person-month-repeat-arm in new answers")
        records[key] = row
    return records, arms, {**manifest, "manifest_sha256": sha(manifest_path),
                           "expected_rows": len(allowed), "present_rows": len(records),
                           "missing_rows": len(allowed) - len(records),
                           "scope": "hash/roster checks, not an independent engine execution audit"}


def prepare(root, protocol, extra_answers=None, extra_manifest=None):
    sources = {}
    for field in ("source_cache", "answers", "links"):
        path = root / protocol[field]
        if sha(path) != protocol[field + "_sha256"]:
            raise ValueError(f"Input changed: {field}")
        sources[protocol[field]] = sha(path)
    scorer = provenance()
    if not scorer["live_matches_pinned"]:
        raise ValueError("Frozen scorer changed")
    links = json.loads((root / protocol["links"]).read_text())
    subjects = [{"userid": int(r["source_agent_id"].removeprefix("sce_u")),
                 "agent_id": r["agent_id"], "month": int(r["month"])} for r in links]
    subjects.sort(key=lambda r: (r["month"], r["userid"]))
    keys = {(s["month"], s["agent_id"]): s for s in subjects}
    if len(keys) != len(subjects) or len(subjects) != protocol["expected_person_months"]:
        raise ValueError("Roster duplicate/size mismatch")
    reference = pd.read_parquet(root / protocol["source_cache"])
    states = history_baselines(reference, subjects, protocol["anchor_coefficient"])
    state_keys = {(s["month"], s["agent_id"]): s for s in states}
    lookup = reference.set_index(["userid", "date"])
    cached = json.loads((root / protocol["answers"]).read_text())
    tables = {q: {} for q in ("Q9", "Q8")}
    for row in cached:
        if row["measure"] in tables:
            key = (int(row["month"]), row["agent_id"], int(row["repeat"]))
            if key in tables[row["measure"]]:
                raise ValueError("Duplicate saved evaluation key")
            tables[row["measure"]][key] = row
    expected = {(m, aid, r) for m, aid in keys for r in protocol["generation_repeats"]}
    if any(set(table) != expected for table in tables.values()):
        raise ValueError("Saved answers do not cover the fixed roster/repeats")
    new, extra_arms, extra_info = {}, [], None
    if (extra_answers is None) != (extra_manifest is None):
        raise ValueError("New answers and manifest must be provided together")
    if extra_answers is not None:
        new, extra_arms, extra_info = import_extra(extra_answers, extra_manifest, subjects, protocol)
    rows = []
    for key in sorted(expected):
        month, aid, repeat = key
        state, old = state_keys[month, aid], tables["Q9"][key]
        actual = lookup.loc[state["userid"], month]
        fitted_real = score([actual[f] for f in BIN_FIELDS])
        old_fit = score([lookup.loc[state["userid"], previous_month(month)][f] for f in BIN_FIELDS])
        for measured, recorded in ((fitted_real["mean"], old["real"]),
                                   (old_fit["mean"], old["own_prior"])):
            if finite(measured) != finite(recorded) or (finite(measured) and abs(measured-recorded) > 1e-8):
                raise ValueError("Saved real/previous score mismatch")
        q9 = {"real": fitted_real["mean"], "previous": state["copy_previous"],
              "copy_previous": state["copy_previous"],
              "history_anchor_half": state["history_anchor_half"]}
        fits = {"real": fitted_real, "copy_previous": old_fit}
        for arm in protocol["llm_arms"]:
            fits[arm] = score(old["raw_answers"][arm])
            q9[arm] = fits[arm]["mean"]
            if finite(q9[arm]) != finite(old[arm]) or (finite(q9[arm]) and abs(q9[arm]-old[arm]) > 1e-8):
                raise ValueError("Saved model frozen score mismatch")
        point_row = tables["Q8"][key]
        q8 = {"real": point_row["real"], "previous": point_row["own_prior"],
              "copy_previous": point_row["own_prior"],
              **{arm: point_row[arm] for arm in protocol["llm_arms"]}}
        for arm in extra_arms:
            answer = new.get((month, aid, repeat, arm), {})
            fits[arm] = score(answer.get("q9_probabilities"))
            q9[arm] = fits[arm]["mean"]
            value = answer.get("q8_point_pct")
            q8[arm] = float(value) if finite(value) else None
        rows.append({"userid": state["userid"], "agent_id": aid, "month": month,
                     "repeat": repeat, "Q9": q9, "Q8": q8, "fits": fits})
    return rows, states, extra_arms, {"source_sha256": sources, "scorer": scorer,
                                     "extra_import": extra_info}


def summarize(rows, conditions, measure):
    coverage = {arm: sum(finite(r[measure].get(arm)) for r in rows)
                for arm in ("real", "previous", *conditions)}
    common = [r for r in rows if all(finite(r[measure].get(a))
                                   for a in ("real", "previous", *conditions))]
    cells = sorted({(r["month"], r["repeat"]) for r in rows})
    groups = [[r for r in common if (r["month"], r["repeat"]) == cell] for cell in cells]
    if any(not group for group in groups):
        return {"status": "missing_common_cell", "coverage": coverage,
                "expected_rows": len(rows), "common_rows": len(common)}, common
    results = {}
    for arm in conditions:
        values = []
        for (month, repeat), group in zip(cells, groups):
            x = np.array([r[measure][arm] for r in group])
            y = np.array([r[measure]["real"] for r in group])
            old = np.array([r[measure]["previous"] for r in group])
            metrics = {k: float(v[0]) for k, v in cell_metrics(x, y, old).items()}
            metrics.update({"centered_w1_pp": wasserstein1(x-quantile(x, None, .5), None,
                                                           y-quantile(y, None, .5), None),
                            "spearman": float(spearmanr(x, y).statistic) if len(set(x)) > 1 and len(set(y)) > 1 else None,
                            "interpolated_iqr_pp": float(np.quantile(x, .75)-np.quantile(x, .25)),
                            "real_interpolated_iqr_pp": float(np.quantile(y, .75)-np.quantile(y, .25))})
            if measure == "Q9" and arm != "history_anchor_half":
                for name, field in (("personal_density_iqr_mean_pp", "iqr"),
                                    ("zero_deflation_fraction", "zero_deflation")):
                    metrics[name] = float(np.mean([r["fits"][arm][field] for r in group]))
            values.append({"month": month, "repeat": repeat, "n": len(group), **metrics})
        numeric = [k for k in values[0] if k not in ("month", "repeat", "n")]
        aggregate = {k: float(np.mean([v[k] for v in values]))
                     if all(finite(v[k]) for v in values) else None for k in numeric}
        results[arm] = {"aggregate": aggregate, "cells": values,
                       "by_repeat": {str(r): {k: float(np.mean([v[k] for v in values if v["repeat"] == r]))
                                               for k in MAIN}
                                     for r in sorted({c[1] for c in cells})}}
    return {"status": "evaluated", "expected_rows": len(rows), "coverage": coverage,
            "common_rows": len(common), "common_person_months": len({(r["userid"], r["month"]) for r in common}),
            "conditions": results,
            "exclusions": {"real_invalid": len(rows)-coverage["real"],
                           "common_excluded": len(rows)-len(common)}}, common


def paired_intervals(rows, comparisons, measure, config):
    """Fixed-month paired person bootstrap; duplicates are not new respondents."""
    people = sorted({r["userid"] for r in rows})
    index = {p: i for i, p in enumerate(people)}
    cells = [np.array([i for i, r in enumerate(rows) if (r["month"], r["repeat"]) == key])
             for key in sorted({(r["month"], r["repeat"]) for r in rows})]
    rng = np.random.default_rng(config["seed"])
    counts = rng.multinomial(len(people), np.full(len(people), 1/len(people)), size=config["draws"])
    weights = counts[:, [index[r["userid"]] for r in rows]]
    keep = np.logical_and.reduce([weights[:, idx].sum(axis=1) > 0 for idx in cells])
    weights = weights[keep]
    if not len(weights):
        raise ValueError("All paired bootstrap draws have an empty month")
    arms = sorted({a for pair in comparisons for a in pair})
    scores = {a: {k: np.zeros(len(weights)) for k in MAIN} for a in arms}
    points = {a: {k: 0. for k in MAIN} for a in arms}
    for idx in cells:
        real = [rows[i][measure]["real"] for i in idx]
        old = [rows[i][measure]["previous"] for i in idx]
        for arm in arms:
            pred = [rows[i][measure][arm] for i in idx]
            result = cell_metrics(pred, real, old, weights[:, idx])
            point = cell_metrics(pred, real, old)
            for k in MAIN:
                scores[arm][k] += result[k] / len(cells)
                points[arm][k] += point[k][0] / len(cells)
    contrasts = {}
    for candidate, baseline in comparisons:
        contrasts[f"{candidate}_minus_{baseline}"] = {
            k: {"difference_pp": float(points[candidate][k]-points[baseline][k]),
                "interval_95": np.quantile(scores[candidate][k]-scores[baseline][k], [.025, .975]).tolist()}
            for k in MAIN}
    return {"persons": len(people), "draws_requested": config["draws"],
            "draws_used": len(weights), "empty_cell_draws": int((~keep).sum()),
            "scope": config["scope"], "contrasts": contrasts}


def screen_candidate(summary, candidate, baseline="own_previous"):
    """Project screening convention; no hypothesis-test or adoption claim."""
    if summary["status"] != "evaluated":
        return {"pilot_signal": False, "reason": "No complete common-month comparison"}
    c, b = summary["conditions"][candidate], summary["conditions"][baseline]
    repeat_pass = {r: (c["by_repeat"][r][MAIN[0]] < b["by_repeat"][r][MAIN[0]]
                      and c["by_repeat"][r][MAIN[1]] < b["by_repeat"][r][MAIN[1]]
                      and c["by_repeat"][r][MAIN[2]] <= b["by_repeat"][r][MAIN[2]])
                   for r in c["by_repeat"]}
    coverage_pass = summary["coverage"][candidate] >= summary["coverage"][baseline]
    return {"pilot_signal": bool(all(repeat_pass.values()) and coverage_pass),
            "by_repeat_pass": repeat_pass, "coverage_no_lower": coverage_pass,
            "formal_adoption": False,
            "reason": "Development screening only; independent months/scale/Route B still required"}


def run(root, out, protocol_path, extra_answers=None, extra_manifest=None):
    root, out, protocol_path = map(lambda p: Path(p).resolve(), (root, out, protocol_path))
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("Require a fresh ignored outputs directory")
    protocol = json.loads(protocol_path.read_text())
    rows, states, extras, meta = prepare(root, protocol, extra_answers, extra_manifest)
    code_paths = ["studies/sce_inflation_expectations/evaluation/behavior_comparison.py",
                  "studies/sce_inflation_expectations/evaluation/metrics.py",
                  "studies/sce_inflation_expectations/reporting_behavior/mapping.py",
                  "studies/sce_inflation_expectations/scoring/sce_q9_frozen.py",
                  "scripts/analyze_sce_behavior_comparison.py"]
    summary = {"version": protocol["version"], "completed_at": datetime.now(timezone.utc).isoformat(),
               "protocol_sha256": sha(protocol_path), "research_line": protocol["research_line"],
               "evaluator_sha256": {p: sha(root / p) for p in code_paths},
               "new_api_calls": 0, "new_cost_usd": 0, **meta,
               "roster_person_months": len(states), "history_anchor_coverage": sum(s["anchor"] is not None for s in states),
               "sample_scope": protocol["weighting"], "quantiles": protocol["quantiles"],
               "information_fairness": "Baselines use own past only; LLMs also use public E. Same cohort/scorer eliminates evaluation mismatch, not information-set mismatch. Oracle C1 and nationwide errors not ranked here.",
               "history_baseline_note": protocol["coefficient_origin"], "measures": {}}
    for measure in ("Q9", "Q8"):
        baselines = protocol["baseline_arms"] if measure == "Q9" else ["copy_previous"]
        conditions = protocol["llm_arms"] + baselines + extras
        result, common = summarize(rows, conditions, measure)
        comparisons = [(arm, b) for arm in protocol["llm_arms"]+extras for b in baselines]
        comparisons += [("own_previous", "no_prior"), ("own_previous", "permuted_previous")]
        comparisons += [(arm, "own_previous") for arm in extras]
        if result["status"] == "evaluated":
            result["paired_intervals"] = paired_intervals(common, comparisons, measure, protocol["bootstrap"])
            if measure == "Q9":
                result["candidate_screening"] = {a: screen_candidate(result, a) for a in extras}
        summary["measures"][measure] = result
    summary["limitations"] = ["Four disconnected months, small selected cohorts and repeat generations do not identify national performance or a continuous trajectory.",
                              "Q9 headline-style sample center is median of individual approximate density MEANS, not median of Q8 or individual density medians.",
                              "Individual level MAE and individual update MAE share the same errors when using the same previous value; they are not independent evidence.",
                              "Intervals resample persons conditional on fixed months, not future environments; no multiple-comparison correction or causal identification.",
                              "Anchor-only baseline predicts a center, not a full ten-bin probability density; no fabricated probability shape."]
    out.mkdir(parents=True)
    dump(out / "summary.json", summary)
    dump(out / "evaluation_rows_private.json", rows)
    dump(out / "history_states_private.json", states)
    dump(out / "protocol_snapshot.json", protocol)
    dump(out / "manifest.json", {"files_sha256": {p.name: sha(p) for p in sorted(out.iterdir()) if p.is_file()},
                                 "new_api_calls": 0})
    return summary
