#!/usr/bin/env python3
"""Score fresh SCE answers with the frozen offline evaluation pipeline.

Answers are model inputs, not truth. This adapter rebuilds all scores and
aggregate outputs from the supplied answer rows, cached exact-vector scores,
frozen public targets and the existing JointExpansion/metrics implementations.
It never makes network or model calls and never fills a fresh Normal bank from
archived answers.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import copy
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    # Also support ``python path/to/portable_evaluate.py`` from the source
    # workspace. The same module remains importable with ``python -m``.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from studies.sce_inflation_expectations.core_normal_joint import (
    JointAnswer,
    JointExpansion,
    PointAnswer,
)
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import (
    provenance,
    score_q9_frozen,
)


ROOT = Path(__file__).resolve().parents[3]
TASKS = ("A", "B", "monthly", "weekly")
NORMAL_RUNS = {"A_Normal": "A", "B_Normal": "B"}
NORMAL_TAU = 8.0
NORMAL_DRAW_SEED = 20261026
FIXED_A_EARLY48_MSE_ALPHA = 0.1339762571517809
SOURCE_FILES = (
    Path("studies/sce_inflation_expectations/submission_tools/portable_evaluate.py"),
    Path("studies/sce_inflation_expectations/core_normal_joint.py"),
    Path("studies/sce_inflation_expectations/evaluation/metrics.py"),
    Path("studies/sce_inflation_expectations/evaluation/monthly_reconstruction.py"),
    Path("studies/sce_inflation_expectations/evaluation/cognition.py"),
    Path("studies/sce_inflation_expectations/evaluation/state_continuity.py"),
    Path("studies/sce_inflation_expectations/scoring/sce_q9_frozen.py"),
    Path("studies/sce_inflation_expectations/scoring/sce_q9.py"),
    Path("studies/sce_inflation_expectations/scoring/beta_fit_kernel.py"),
    Path("studies/sce_inflation_expectations/model.py"),
    Path("studies/sce_inflation_expectations/experiments/frozen_batch.py"),
    Path("studies/sce_inflation_expectations/experiments/state_continuity_execution.py"),
    Path("studies/sce_inflation_expectations/experiments/state_continuity_inputs.py"),
    Path("studies/sce_inflation_expectations/prior_belief_preparation.py"),
)
EXPECTED_EVALUATION_FILES = (
    "expected.json",
    "A_paired_cases.jsonl.gz",
    "A_full_wave_targets.jsonl.gz",
    "density_cache.jsonl.gz",
    "normal_mechanism.jsonl.gz",
    "code_map.json",
)
UPDATED_SOURCES = {"main", "repair"}
RETAINED_SOURCES = {"retained_prior", "retained_input", "retained_previous", "initial_fallback"}
PERIOD_MONTH = re.compile(r"^\d{6}$")
PERIOD_WEEK = re.compile(r"^w\d{8}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _jsonl(path: Path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _jsonl_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _write_json(path: Path, value) -> None:
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl_gz(path: Path, rows) -> int:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with Path(path).open("xb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", filename="", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False,
                                            separators=(",", ":"), sort_keys=True) + "\n")
                    count += 1
    return count


def _write_csv(path: Path, rows, fieldnames) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _is_finite(value) -> bool:
    return (not isinstance(value, bool) and value is not None
            and isinstance(value, (int, float)) and math.isfinite(float(value)))


def _finite_float(value, label: str, *, minimum=None, maximum=None):
    if not _is_finite(value):
        raise ValueError(f"{label} must be a finite number")
    value = float(value)
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} is below its allowed range")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} is above its allowed range")
    return value


def _valid_bins(bins) -> bool:
    if not isinstance(bins, list) or len(bins) != 10:
        return False
    if not all(_is_finite(value) and 0 <= float(value) <= 100 for value in bins):
        return False
    return abs(round(sum(float(value) for value in bins), 6) - 100.0) <= 0.5


def _score_bins(bins, cache: dict, counts: Counter) -> dict:
    """Use frozen cached results only for exact vectors; score other vectors now."""
    if not _valid_bins(bins):
        counts["invalid_or_missing_vectors"] += 1
        return {
            "mean": None,
            "iqr": None,
            "zero_deflation": None,
            "scorer_status": "invalid_or_missing_bins",
            "validation_error": "Q9 requires ten finite probabilities in [0,100] summing to 100 within 0.5",
            "score_source": "not_scored",
        }
    vector = tuple(float(value) for value in bins)
    if vector in cache:
        score = copy.deepcopy(cache[vector])
        origin = score.pop("_portable_cache_origin", "exact_vector_frozen_cache")
        if origin == "same_run_fresh_score":
            counts["same_run_fresh_score_reuses"] += 1
            score["score_source"] = "same_run_fresh_score_reuse"
        else:
            counts["exact_cache_lookups"] += 1
            score["score_source"] = "exact_vector_frozen_cache"
        score.setdefault("zero_deflation", float(sum(vector[5:]) == 0))
        score.setdefault("scorer_status", score.get("status", "cached"))
        score.setdefault("validation_error", None)
        return score
    result = score_q9_frozen(vector)
    counts["new_frozen_scores"] += 1
    score = {
        "mean": float(result.mean) if _is_finite(result.mean) else None,
        "iqr": float(result.iqr) if _is_finite(result.iqr) else None,
        "zero_deflation": float(sum(vector[5:]) == 0),
        "scorer_status": result.status,
        "validation_error": None,
        "score_source": "fresh_frozen_scorer",
    }
    cache[vector] = {**score, "_portable_cache_origin": "same_run_fresh_score"}
    return score


def _normalise_data_root(data) -> Path:
    data = Path(data).expanduser().resolve()
    if all((data / name).is_file() for name in EXPECTED_EVALUATION_FILES):
        return data
    if all((data / "evaluation" / name).is_file() for name in EXPECTED_EVALUATION_FILES):
        return data / "evaluation"
    raise FileNotFoundError(f"Evaluation input directory is missing one or more files: {data}")


def _load_cache(path: Path) -> dict:
    cache = {}
    for row in _jsonl_gz(path):
        vector = tuple(float(value) for value in row["bins"])
        if vector in cache:
            old = cache[vector]
            new = row["score"]
            if any(old.get(key) != new.get(key) for key in ("mean", "iqr")):
                raise ValueError("Archived frozen density cache has conflicting exact vectors")
            continue
        cache[vector] = row["score"]
    return cache


def _prepare_answers(rows, code_map: dict, cache: dict):
    if not isinstance(code_map, dict) or not code_map:
        raise ValueError("A nonempty aliases-to-original-ID code map is required")
    original_by_alias = {str(alias): str(original) for alias, original in code_map.items()}
    source_by_answer = {}
    counters = Counter()
    seen = set()
    prepared = []
    allowed_sources = UPDATED_SOURCES | RETAINED_SOURCES | {"missing", "none"}
    for raw in rows:
        task = raw.get("task")
        if task not in TASKS:
            raise ValueError(f"Unknown answer task: {task}")
        period = str(raw.get("period", ""))
        if (task == "weekly" and not PERIOD_WEEK.fullmatch(period)) or (
            task != "weekly" and not PERIOD_MONTH.fullmatch(period)
        ):
            raise ValueError(f"Invalid {task} period: {period}")
        alias = str(raw.get("household", ""))
        original_id = str(raw.get("agent_id", ""))
        if alias not in original_by_alias:
            raise ValueError(f"Unknown household alias in code_map: {alias}")
        if original_by_alias[alias] != original_id:
            raise ValueError(f"Answer agent_id does not match the household alias: {alias}")
        weight = _finite_float(raw.get("weight"), "answer weight", minimum=0.0)
        if weight <= 0:
            raise ValueError("Answer weight must be positive")
        actual = raw.get("actual_model_results")
        if not isinstance(actual, bool):
            raise ValueError("actual_model_results must be an explicit boolean")
        field_sources = raw.get("field_sources")
        if not isinstance(field_sources, dict) or not {"q8", "q9"} <= set(field_sources):
            raise ValueError("field_sources must identify Q8 and Q9 provenance")
        sources = {key: str(field_sources[key]) for key in ("q8", "q9")}
        if set(sources.values()) - allowed_sources:
            raise ValueError(f"Unknown field_sources values: {sources}")
        key = (task, period, original_id)
        if key in seen:
            raise ValueError(f"Duplicate fresh answer: {task}/{period}/{alias}")
        seen.add(key)

        raw_q8 = raw.get("q8")
        if raw_q8 is not None:
            raw_q8 = _finite_float(raw_q8, "Q8", minimum=-100.0, maximum=100.0)
        model_q8 = raw_q8 if sources["q8"] in UPDATED_SOURCES else None
        before_q8 = raw.get("before_q8")
        if before_q8 is not None:
            before_q8 = _finite_float(before_q8, "before_q8", minimum=-100.0, maximum=100.0)
        operational_q8 = model_q8
        q8_fallback = False
        if operational_q8 is None:
            operational_q8 = before_q8 if before_q8 is not None else raw_q8
            q8_fallback = operational_q8 is not None

        raw_bins = raw.get("q9_bins")
        model_bins = raw_bins if sources["q9"] in UPDATED_SOURCES else None
        model_score = _score_bins(model_bins, cache, counters) if model_bins is not None else {
            "mean": None, "iqr": None, "zero_deflation": None,
            "scorer_status": "not_updated", "score_source": "not_model_output",
        }
        before_bins = raw.get("before_q9_bins")
        if before_bins is None and sources["q9"] in RETAINED_SOURCES:
            before_bins = raw_bins
        operational_score = model_score
        operational_bins = model_bins
        q9_fallback = False
        if sources["q9"] not in UPDATED_SOURCES:
            operational_bins = before_bins
            operational_score = _score_bins(operational_bins, cache, counters) if operational_bins is not None else {
                "mean": None, "iqr": None, "zero_deflation": None,
                "scorer_status": "retained_state_missing", "score_source": "not_scored",
            }
            q9_fallback = operational_score.get("mean") is not None
        elif model_score.get("mean") is None or model_score.get("iqr") is None:
            # Match full_a_personal.action_view: a valid model vector whose
            # frozen density cannot be fitted leaves the operational Q9 at the
            # prior state. It is never replaced by an archived model answer.
            if before_bins is not None:
                prior_score = _score_bins(before_bins, cache, counters)
                if prior_score.get("mean") is not None and prior_score.get("iqr") is not None:
                    operational_bins, operational_score = before_bins, prior_score
                    q9_fallback = True
                else:
                    operational_bins, operational_score = [], {
                        "mean": None, "iqr": None, "zero_deflation": None,
                        "scorer_status": "prior_fallback_unscorable", "score_source": "not_scored",
                    }
            else:
                operational_bins, operational_score = [], {
                    "mean": None, "iqr": None, "zero_deflation": None,
                    "scorer_status": "prior_fallback_unavailable", "score_source": "not_scored",
                }

        if operational_bins is None:
            operational_bins = []
        record = {
            "task": task,
            "period": period,
            "agent_id": original_id,
            "household": alias,
            "weight": weight,
            "actual_model_results": actual,
            "field_sources": sources,
            "model_q8": model_q8,
            "model_q9_bins": list(model_bins) if isinstance(model_bins, list) else [],
            "model_q9_mean": model_score.get("mean"),
            "model_q9_iqr": model_score.get("iqr"),
            "model_q9_zero_deflation": model_score.get("zero_deflation"),
            "model_q9_scorer_status": model_score.get("scorer_status"),
            "model_q9_score_source": model_score.get("score_source"),
            "q8": operational_q8,
            "q9_bins": list(operational_bins) if isinstance(operational_bins, list) else [],
            "q9_mean": operational_score.get("mean"),
            "q9_iqr": operational_score.get("iqr"),
            "q9_zero_deflation": operational_score.get("zero_deflation"),
            "q9_scorer_status": operational_score.get("scorer_status"),
            "q9_score_source": operational_score.get("score_source"),
            "q8_retained_fallback": q8_fallback,
            "q9_prior_fallback": q9_fallback,
        }
        prepared.append(record)
        source_by_answer[key] = record
        counters["answers"] += 1
        counters["actual_model_results_true"] += int(actual)
        counters["actual_model_results_false"] += int(not actual)
        counters[f"q8_source_{sources['q8']}"] += 1
        counters[f"q9_source_{sources['q9']}"] += 1
        counters["q8_retained_fallbacks"] += int(q8_fallback)
        counters["q9_prior_fallbacks"] += int(q9_fallback)
    prepared.sort(key=lambda row: (TASKS.index(row["task"]), row["period"], row["household"]))
    return prepared, source_by_answer, counters


def _month_value(value) -> str:
    return str(value).replace("-", "")


def _summary(values, weights):
    from studies.sce_inflation_expectations.evaluation.metrics import distribution_summary

    if not values:
        return None
    return distribution_summary(values, weights)


def _a_full_wave(answer_rows, targets):
    from studies.sce_inflation_expectations.evaluation.metrics import compare_distributions

    full_wave_by_month = defaultdict(list)
    for row in targets:
        full_wave_by_month[_month_value(row["month"])].append(row)
    answers_by_month = defaultdict(list)
    for row in answer_rows:
        if row["task"] == "A":
            answers_by_month[row["period"]].append(row)
    result = []
    for month, sample in sorted(answers_by_month.items()):
        truth = full_wave_by_month.get(month, [])
        fields = {}
        for field, sample_key, truth_key in (
            ("q9_mean", "q9_mean", "q9_mean"),
            ("q8_point", "q8", "q8"),
        ):
            model = [row for row in sample if _is_finite(row[sample_key]) and row["weight"] > 0]
            human = [row for row in truth if _is_finite(row.get(truth_key))
                     and _is_finite(row.get("weight")) and row["weight"] > 0]
            if not model or not human:
                fields[field] = None
                continue
            fields[field] = compare_distributions(
                [row[sample_key] for row in model], [row["weight"] for row in model],
                [row[truth_key] for row in human], [row["weight"] for row in human],
            )
        result.append({
            "month": month,
            "n_fresh_answers": len(sample),
            "n_q9_scored": sum(_is_finite(row["q9_mean"]) for row in sample),
            "n_q8_scored": sum(_is_finite(row["q8"]) for row in sample),
            "fields": fields,
            "status": "descriptive_A_full_wave_comparison",
        })
    return result


def _adapt_a_cases(answer_by_key, cases, expected):
    adapted = []
    for original in cases:
        period = _month_value(original["month"])
        original_id = str(original["_original_agent_id"])
        fresh = answer_by_key.get(("A", period, original_id))
        if fresh is None:
            continue
        case = copy.deepcopy(original)
        arm = case["arms"]["monthly_reconstruction"]
        arm.update(
            mean=fresh["q9_mean"],
            iqr=fresh["q9_iqr"],
            zero_deflation=fresh["q9_zero_deflation"],
            q9_bins=fresh["q9_bins"],
            point=fresh["q8"],
        )
        adapted.append(case)
    if not adapted:
        return {"status": "unavailable_no_matched_A_cases", "matched_cases": 0}, []

    from studies.sce_inflation_expectations.evaluation.monthly_reconstruction import summarize

    months = sorted({int(row["month"]) for row in adapted})
    weight_definition = expected.get("A", {}).get("weight_definition")
    if not weight_definition:
        weight_definition = "raw survey weight / actual within-cell SRS inclusion probability"
    paired = {}
    for label, baseline in (
        ("fixed_roster", "monthly_past_reference"),
        ("genuine_previous_only", "genuine_previous_only"),
    ):
        paired[label] = summarize(
            adapted,
            months,
            ["monthly_reconstruction", baseline],
            weight_definition=weight_definition,
        )
    paired["status"] = "fresh_A_paired_micro_evaluation"
    paired["matched_cases"] = len(adapted)
    return paired, adapted


def _conditional_groups(cases):
    from studies.sce_inflation_expectations.evaluation.metrics import compare_distributions

    dimensions = (
        "age_group",
        "education_group",
        "numeracy",
        "household_income_band",
        "region",
        "survey_entry_status",
        "grid54",
    )
    groups = []
    for dimension in dimensions:
        subsets = defaultdict(list)
        for case in cases:
            profile = case.get("profile", {})
            if dimension == "grid54":
                label = "|".join(
                    str(profile.get(key) or "unknown")
                    for key in ("education_group", "numeracy", "age_group", "household_income_band")
                )
            else:
                label = str(case.get(dimension, profile.get(dimension)) or "unknown")
            subsets[label].append(case)
        for value, subset in sorted(subsets.items()):
            by_month = defaultdict(list)
            for case in subset:
                by_month[_month_value(case["month"])].append(case)
            for month, rows in sorted(by_month.items()):
                paired = [
                    row for row in rows
                    if _is_finite(row["real"].get("q9_mean"))
                    and _is_finite(row["arms"]["monthly_reconstruction"].get("mean"))
                    and _is_finite(row["real"].get("q8_point"))
                    and _is_finite(row["arms"]["monthly_reconstruction"].get("point"))
                    and _is_finite(row.get("survey_weight"))
                    and row["survey_weight"] > 0
                ]
                metrics = {}
                for label, sim_key, real_key in (
                    ("q9_mean", "mean", "q9_mean"),
                    ("q8_point", "point", "q8_point"),
                ):
                    valid = [row for row in rows if _is_finite(row["real"].get(real_key))
                             and _is_finite(row["arms"]["monthly_reconstruction"].get(sim_key))
                             and _is_finite(row.get("survey_weight")) and row["survey_weight"] > 0]
                    if not valid:
                        metrics[label] = None
                        continue
                    weights = [row["survey_weight"] for row in valid]
                    metrics[label] = compare_distributions(
                        [row["arms"]["monthly_reconstruction"][sim_key] for row in valid], weights,
                        [row["real"][real_key] for row in valid], weights,
                    )
                weights = [row["survey_weight"] for row in paired]
                ess = (sum(weights) ** 2 / sum(weight**2 for weight in weights)) if weights else 0.0
                groups.append({
                    "dimension": dimension,
                    "level": value,
                    "month": month,
                    "n": len(paired),
                    "supported": len(paired) >= 20 and ess >= 10,
                    "survey_weight_ess": ess,
                    "metrics": metrics,
                })
    return groups


def _normal_people_and_core(normal):
    if normal["run"] == "A_Normal":
        inputs = normal["inputs"]
        people = inputs["people"]
        selected = inputs["selected"]
        core_ids = [str(row["id"]) for row in selected]
        core_weights = {str(row["id"]): float(row["poststratified_weight"]) for row in selected}
    elif normal["run"] == "B_Normal":
        people = normal["frame"]
        core_weights = {str(key): float(value) for key, value in normal["core_weights"].items()}
        core_ids = list(core_weights)
    else:
        raise ValueError(f"Unknown normal_mechanism run: {normal['run']}")
    return people, core_ids, core_weights


def _stable_posterior_draw(bank, uid: str, period: str):
    key_seed = int.from_bytes(hashlib.sha256(
        f"{NORMAL_DRAW_SEED}:{period}:{uid}".encode()
    ).digest()[:8], "big")
    probability = bank.conditional(bank.group_key(uid))[0]
    answer = bank.answers[int(__import__("numpy").random.default_rng(key_seed).choice(len(bank.answers), p=probability))]
    return str(answer.id), answer.payload()


def _build_normal(normal, period: str, task: str, answer_by_key, code_map, full_wave):
    from studies.sce_inflation_expectations.evaluation.metrics import (
        compare_distributions,
        distribution_summary,
    )

    people, core_ids, core_weights = _normal_people_and_core(normal)
    reverse_code = {str(alias): str(original) for alias, original in code_map.items()}
    core_by_original = {}
    unknown_aliases = []
    for alias in core_ids:
        original = reverse_code.get(alias)
        if original is None:
            unknown_aliases.append(alias)
        else:
            core_by_original[original] = alias
    present = {
        original: answer_by_key.get((task, period, original))
        for original in core_by_original
    }
    missing = sorted(original for original, row in present.items() if row is None)
    base = {
        "run": normal["run"],
        "period": period,
        "core_ids_expected": len(core_ids),
        "core_ids_present": len(present) - len(missing),
        "core_ids_missing": len(missing) + len(unknown_aliases),
        "population_rows": len(people),
        "population_mass": float(sum(float(row["weight"]) for row in people)),
        "tau": NORMAL_TAU,
        "status": "unavailable_incomplete_fresh_core_answers",
    }
    if missing or unknown_aliases:
        return {**base, "missing_core_original_ids": missing[:20], "unknown_core_aliases": unknown_aliases[:20]}, []

    q9_answers, q8_answers = [], []
    for original, alias in core_by_original.items():
        row = present[original]
        if not row["actual_model_results"]:
            continue
        if row["field_sources"]["q9"] in UPDATED_SOURCES and row["model_q9_mean"] is not None and row["model_q9_iqr"] is not None:
            q9_answers.append(JointAnswer(
                alias,
                tuple(float(value) for value in row["model_q9_bins"]),
                float(row["model_q9_mean"]),
                float(row["model_q9_iqr"]),
                row["model_q8"],
            ))
        if row["field_sources"]["q8"] in UPDATED_SOURCES and _is_finite(row["model_q8"]):
            q8_answers.append(PointAnswer(alias, float(row["model_q8"])))

    # These answers are generated only from the new run. No value in the
    # archived normal_mechanism answer bank is read or used as a substitute.
    if not q9_answers:
        return {**base, "status": "unavailable_no_fresh_scored_Q9_donors"}, []
    try:
        q9_bank = JointExpansion(people, core_ids, q9_answers, core_weights, prior_strength=NORMAL_TAU)
        q9_mass = q9_bank.atom_weights()
    except ValueError as error:
        return {**base, "status": "unavailable_Q9_bank_cannot_support_population", "detail": str(error)}, []
    expected_mass = base["population_mass"]
    if not math.isclose(float(q9_mass.sum()), expected_mass, rel_tol=1e-12, abs_tol=1e-8):
        raise ValueError(f"Normal Q9 population mass did not conserve for {normal['run']}/{period}")
    q9_values = [answer.q9_mean for answer in q9_bank.answers]
    q9_summary = distribution_summary(q9_values, q9_mass)

    q8_bank = None
    q8_summary = None
    q8_mass = None
    if q8_answers:
        try:
            q8_bank = JointExpansion(people, core_ids, q8_answers, core_weights, prior_strength=NORMAL_TAU)
            q8_mass = q8_bank.atom_weights()
            if not math.isclose(float(q8_mass.sum()), expected_mass, rel_tol=1e-12, abs_tol=1e-8):
                raise ValueError(f"Normal Q8 population mass did not conserve for {normal['run']}/{period}")
            q8_summary = distribution_summary([answer.q8 for answer in q8_bank.answers], q8_mass)
        except ValueError:
            q8_bank = None
            q8_summary = None
            q8_mass = None

    target_wave = full_wave.get(period, []) if normal["run"] == "A_Normal" else None
    full_wave_metrics = {}
    if target_wave:
        for key, values, weights, truth_key in (
            ("q9_mean", q9_values, q9_mass, "q9_mean"),
            ("q8_point", [answer.q8 for answer in q8_bank.answers] if q8_bank else [],
             q8_mass if q8_mass is not None else [], "q8"),
        ):
            valid = [row for row in target_wave if _is_finite(row.get(truth_key))
                     and _is_finite(row.get("weight")) and row["weight"] > 0]
            if values and weights is not None and valid:
                metric = compare_distributions(
                    values,
                    weights,
                    [row[truth_key] for row in valid],
                    [row["weight"] for row in valid],
                )
                full_wave_metrics[key] = metric
            else:
                full_wave_metrics[key] = None

    normal_rows = []
    q9_donor_ids = set(q9_bank._donor_index)
    q8_donor_ids = set(q8_bank._donor_index) if q8_bank else set()
    for person in people:
        uid = str(person["id"])
        is_core = uid in set(core_ids)
        if uid in q9_donor_ids:
            q9_answer = q9_bank.answers[q9_bank._donor_index[uid]]
            q9_payload = {"donor_id": uid, "source": "fresh_core_model_output", **q9_answer.payload()}
        else:
            donor, payload = _stable_posterior_draw(q9_bank, uid, period)
            q9_payload = {"donor_id": donor, "source": "fresh_posterior_draw", **payload}
        if q8_bank is not None:
            if uid in q8_donor_ids:
                q8_answer = q8_bank.answers[q8_bank._donor_index[uid]]
                q8_payload = {"donor_id": uid, "source": "fresh_core_model_output", **q8_answer.payload()}
            else:
                donor, payload = _stable_posterior_draw(q8_bank, uid, period)
                q8_payload = {"donor_id": donor, "source": "fresh_posterior_draw", **payload}
        else:
            q8_payload = {"donor_id": None, "source": "unavailable_no_fresh_Q8_donors", "q8": None}
        normal_rows.append({
            "run": normal["run"],
            "period": period,
            "household": uid,
            "role": "Core" if is_core else "statistical_Normal",
            "weight": float(person["weight"]),
            "profile": {key: value for key, value in person.items()
                        if key not in {"id", "weight", "entry"}},
            "q9_joint": q9_payload,
            "q8_marginal": q8_payload,
            "inspection_draw_only": uid not in q9_donor_ids,
        })
    return {
        **base,
        "status": "completed_fresh_joint_expansion",
        "valid_fresh_Q9_donors": len(q9_answers),
        "valid_fresh_Q8_donors": len(q8_answers),
        "q9_population_mass": float(q9_mass.sum()),
        "q8_population_mass": float(q8_mass.sum()) if q8_mass is not None else None,
        "q9": q9_summary,
        "q8": q8_summary,
        "full_wave_comparison": full_wave_metrics,
        "normal_draw_seed": NORMAL_DRAW_SEED,
        "normal_draws_are_inspection_only": True,
    }, normal_rows


def _expected_period_rows(expected):
    rows = {}
    a_rows = expected.get("A", {}).get("official_national", {}).get("monthly", [])
    rows["A"] = [{**row, "month": _month_value(row["month"])} for row in a_rows]
    rows["B"] = [{**row, "month": str(row["month"]).zfill(6)} for row in expected.get("B", [])]
    rows["monthly"] = [{**row, "month": str(row["month"]).zfill(6)} for row in expected.get("monthly", [])]
    rows["weekly"] = [dict(row) for row in expected.get("weekly", [])]
    return rows


def _direct_period_summaries(answer_rows, expected):
    results = []
    expected_rows = _expected_period_rows(expected)
    refs = {task: {str(row.get("step_key", row.get("month"))): row for row in rows}
            for task, rows in expected_rows.items()}
    grouped = defaultdict(list)
    for row in answer_rows:
        grouped[row["task"], row["period"]].append(row)
    for task in TASKS:
        for (found_task, period), rows in sorted(grouped.items()):
            if found_task != task:
                continue
            q9_valid = [row for row in rows if _is_finite(row["q9_mean"]) and row["weight"] > 0]
            q8_valid = [row for row in rows if _is_finite(row["q8"]) and row["weight"] > 0]
            q9 = _summary([row["q9_mean"] for row in q9_valid], [row["weight"] for row in q9_valid])
            q8 = _summary([row["q8"] for row in q8_valid], [row["weight"] for row in q8_valid])
            ref_key = period if task == "weekly" else period
            ref = refs[task].get(ref_key, {})
            results.append({
                "task": task,
                "period": period,
                "n_answers": len(rows),
                "actual_model_results_n": sum(row["actual_model_results"] for row in rows),
                "q9": q9,
                "q8": q8,
                "truth_pp": ref.get("truth_pp", ref.get("target_release_value_pp")),
                "anchor_pp": ref.get("anchor_pp"),
                "human_micro_evaluation": "A_only" if task == "A" else "not_available",
            })
    return results


def _reference_number(value):
    """Read frozen expected values that are numeric JSON values or CSV strings."""
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            value = float(value)
        except ValueError:
            return None
    return float(value) if _is_finite(value) else None


def _national_metrics(expected, direct_summaries, normal_summaries, answer_rows, alpha):
    """Score fresh national centers with the original strict headline metric.

    Target periods are fixed by the exported expected series. Missing model
    forecasts are surfaced as coverage gaps and never dropped before calling
    ``headline_errors``. Weekly main-score flags and the monthly root-reuse
    exclusion are carried forward from the frozen expected file.
    """
    from studies.sce_inflation_expectations.evaluation.metrics import headline_errors

    def month_key(value):
        return _month_value(value).zfill(6)

    direct_by_key = {(row["task"], row["period"]): row for row in direct_summaries}
    normal_by_key = {(row["run"], row["period"]): row for row in normal_summaries}
    answer_by_period = defaultdict(list)
    for row in answer_rows:
        answer_by_period[row["task"], row["period"]].append(row)

    a_targets = expected.get("A", {}).get("official_national", {}).get("monthly", [])
    b_targets = expected.get("B", [])
    monthly_targets = expected.get("monthly", [])
    weekly_all = expected.get("weekly", [])

    specs = {}
    specs["A"] = {
        "periods": [{"period": month_key(row["month"]),
                     "truth_pp": _reference_number(row.get("truth_pp")),
                     "anchor_pp": _reference_number(row.get("anchor_pp"))}
                    for row in a_targets],
        "forecast_task": "A",
        "normal_run": "A_Normal",
        "excluded_periods": [],
        "exclusion_reason": None,
    }
    specs["B"] = {
        "periods": [{"period": month_key(row["month"]),
                     "truth_pp": _reference_number(row.get("truth_pp")),
                     "anchor_pp": _reference_number(row.get("anchor_pp"))}
                    for row in b_targets],
        "forecast_task": "B",
        "normal_run": "B_Normal",
        "excluded_periods": [],
        "exclusion_reason": None,
    }
    monthly_kept, monthly_excluded = [], []
    for row in monthly_targets:
        item = {"period": month_key(row["month"]),
                "truth_pp": _reference_number(row.get("truth_pp")),
                "anchor_pp": _reference_number(row.get("anchor_pp"))}
        if item["period"] == "202511" or row.get("shared_reused_root") is True:
            monthly_excluded.append(item["period"])
        else:
            monthly_kept.append(item)
    specs["monthly"] = {
        "periods": monthly_kept,
        "forecast_task": "monthly",
        "normal_run": None,
        "excluded_periods": monthly_excluded,
        "exclusion_reason": "202511 uses the shared B root; not counted as a new monthly forecast",
    }
    weekly_kept, weekly_excluded = [], []
    for row in weekly_all:
        is_main = row.get("main_score_point") is True or str(row.get("main_score_point")).lower() == "true"
        item = {"period": str(row.get("step_key", row.get("month", ""))),
                "truth_pp": _reference_number(row.get("target_release_value_pp")),
                "anchor_pp": _reference_number(row.get("anchor_pp"))}
        if is_main:
            weekly_kept.append(item)
        else:
            weekly_excluded.append(item["period"])
    specs["weekly"] = {
        "periods": weekly_kept,
        "forecast_task": "weekly",
        "normal_run": None,
        "excluded_periods": weekly_excluded,
        "exclusion_reason": "only frozen main_score_point=True weekly targets are scored",
    }

    def field_coverage(task, period):
        rows = answer_by_period.get((task, period), [])
        q8_sources, q9_sources = Counter(), Counter()
        for row in rows:
            q8_sources[row["field_sources"]["q8"]] += 1
            q9_sources[row["field_sources"]["q9"]] += 1
        return {
            "answer_rows": len(rows),
            "actual_model_results_n": sum(bool(row["actual_model_results"]) for row in rows),
            "q8_scored_n": sum(_is_finite(row["q8"]) for row in rows),
            "q9_scored_n": sum(_is_finite(row["q9_mean"]) for row in rows),
            "q8_updated_n": sum(row["field_sources"]["q8"] in UPDATED_SOURCES for row in rows),
            "q9_updated_n": sum(row["field_sources"]["q9"] in UPDATED_SOURCES for row in rows),
            "q8_retained_or_fallback_n": sum(row["q8_retained_fallback"] for row in rows),
            "q9_prior_fallback_n": sum(row["q9_prior_fallback"] for row in rows),
            "q8_field_sources": dict(sorted(q8_sources.items())),
            "q9_field_sources": dict(sorted(q9_sources.items())),
        }

    def make_block(name, spec, *, normal=False):
        forecast_task = spec["forecast_task"]
        rows = []
        forecast_values, baseline_values, blend_values, truths = [], [], [], []
        raw_missing, baseline_missing, blend_missing = [], [], []
        for target in spec["periods"]:
            period = target["period"]
            truth = target["truth_pp"]
            anchor = target["anchor_pp"]
            if normal:
                summary = normal_by_key.get((spec["normal_run"], period))
                available = bool(summary and summary.get("status") == "completed_fresh_joint_expansion")
                prediction = summary.get("q9", {}).get("median_pp") if available else None
                q8_prediction = summary.get("q8", {}).get("median_pp") if available else None
                coverage = {
                    "normal_status": summary.get("status") if summary else "missing_normal_period",
                    "core_ids_expected": summary.get("core_ids_expected") if summary else 0,
                    "core_ids_present": summary.get("core_ids_present") if summary else 0,
                    "core_ids_missing": summary.get("core_ids_missing") if summary else None,
                    "valid_fresh_Q9_donors": summary.get("valid_fresh_Q9_donors", 0) if summary else 0,
                    "valid_fresh_Q8_donors": summary.get("valid_fresh_Q8_donors", 0) if summary else 0,
                    "q9_population_mass": summary.get("q9_population_mass") if summary else None,
                    "q8_population_mass": summary.get("q8_population_mass") if summary else None,
                    "answer_field_coverage": field_coverage(forecast_task, period),
                }
            else:
                summary = direct_by_key.get((forecast_task, period))
                prediction = summary.get("q9", {}).get("median_pp") if summary and summary.get("q9") else None
                q8_prediction = summary.get("q8", {}).get("median_pp") if summary and summary.get("q8") else None
                coverage = field_coverage(forecast_task, period)
                coverage["normal_status"] = "not_applicable"

            prediction = _reference_number(prediction)
            q8_prediction = _reference_number(q8_prediction)
            if prediction is None:
                raw_missing.append(period)
            else:
                forecast_values.append(prediction)
            if anchor is None:
                baseline_missing.append(period)
            else:
                baseline_values.append(anchor)
            blended = anchor + alpha * (prediction - anchor) if anchor is not None and prediction is not None else None
            if blended is None:
                blend_missing.append(period)
            else:
                blend_values.append(blended)
            if truth is not None:
                truths.append(truth)
            rows.append({
                "period": period,
                "truth_pp": truth,
                "anchor_pp": anchor,
                "fresh_q9_median_pp": prediction,
                "fresh_q8_median_pp_descriptive": q8_prediction,
                "fixed_A_early48_MSE_blend_pp": blended,
                "forecast_status": "covered" if prediction is not None else "missing_forecast",
                "coverage": coverage,
            })

        expected_n = len(spec["periods"])
        truth_missing = [row["period"] for row in spec["periods"] if row["truth_pp"] is None]

        def strict_metrics(values, missing):
            if missing or truth_missing or len(values) != expected_n:
                return None
            return headline_errors(values, truths)

        metrics = {
            "fresh_raw": strict_metrics(forecast_values, raw_missing),
            "baseline_anchor": strict_metrics(baseline_values, baseline_missing),
            "fixed_A_early48_MSE_blend": strict_metrics(blend_values, blend_missing),
        }
        return {
            "status": ("complete" if not raw_missing and not baseline_missing and not truth_missing
                       else "incomplete_forecast_or_reference_coverage"),
            "forecast_source": spec["normal_run"] if normal else forecast_task,
            "period_count": expected_n,
            "covered_forecast_periods": expected_n - len(raw_missing),
            "missing_forecast_periods": raw_missing,
            "missing_anchor_periods": baseline_missing,
            "missing_truth_periods": truth_missing,
            "excluded_periods": spec["excluded_periods"],
            "exclusion_reason": spec["exclusion_reason"],
            "fixed_blend_alpha": alpha,
            "metrics": metrics,
            "monthly": rows,
        }

    result = {
        "status": "fresh_national_headline_metrics",
        "metric_implementation": "studies.sce_inflation_expectations.evaluation.metrics.headline_errors",
        "fixed_blend_weight": alpha,
        "fixed_blend_weight_source": "frozen A early-48 MSE; never refit on fresh B/monthly/weekly outputs",
        "series": {},
    }
    for task, spec in specs.items():
        result["series"][task] = make_block(task, spec)
        if spec["normal_run"]:
            result["series"][spec["normal_run"]] = make_block(spec["normal_run"], spec, normal=True)
    return result


def _write_downstream_inputs(expected, normal_summaries, out: Path):
    alpha = FIXED_A_EARLY48_MSE_ALPHA
    a_alpha = expected.get("B_Normal", {}).get("simulation_blend_weight", alpha)
    if not math.isclose(float(a_alpha), alpha, rel_tol=0, abs_tol=1e-12):
        raise ValueError("Fresh downstream adapter requires the fixed A early-48 MSE blend weight")
    normal_by_run_month = {(row["run"], row["period"]): row for row in normal_summaries}
    a_rows, b_rows = [], []
    for ref in _expected_period_rows(expected)["A"]:
        month = ref["month"]
        normal = normal_by_run_month.get(("A_Normal", month), {})
        available = normal.get("status") == "completed_fresh_joint_expansion"
        simulated = normal.get("q9", {}).get("median_pp") if available else None
        anchor = float(ref["anchor_pp"])
        blend = anchor + alpha * (simulated - anchor) if simulated is not None else None
        a_rows.append({
            "month": month,
            "truth_pp": ref["truth_pp"],
            "CoreNormal_tau8_pure": simulated,
            "CoreNormal_tau8_blend_mse": blend,
        })
    for ref in _expected_period_rows(expected)["B"]:
        month = ref["month"]
        normal = normal_by_run_month.get(("B_Normal", month), {})
        available = normal.get("status") == "completed_fresh_joint_expansion"
        simulated = normal.get("q9", {}).get("median_pp") if available else None
        anchor = float(ref["anchor_pp"])
        blend = anchor + alpha * (simulated - anchor) if simulated is not None else None
        b_rows.append({
            "month": month,
            "truth_pp": ref["truth_pp"],
            "expanded_pp": simulated,
            "expanded_blend_pp": blend,
        })
    _write_csv(out / "monthly_predictions_public.csv", a_rows,
               ["month", "truth_pp", "CoreNormal_tau8_pure", "CoreNormal_tau8_blend_mse"])
    _write_csv(out / "monthly_national.csv", b_rows,
               ["month", "truth_pp", "expanded_pp", "expanded_blend_pp"])
    return {"alpha": alpha, "a_rows": len(a_rows), "b_rows": len(b_rows)}


def evaluate(answers, data, out, source_root=None):
    """Evaluate a fresh JSONL answer file without refitting or model calls.

    Parameters
    ----------
    answers:
        Path to the parent runner's ``answers.jsonl``.
    data:
        Path to ``data/evaluation`` or its runtime bundle root.
    out:
        New output directory. Existing outputs are never overwritten.
    source_root:
        Optional original-source workspace root for code-hash recording.
    """
    answers_path = Path(answers).expanduser().resolve()
    data_root = _normalise_data_root(data)
    source_root = Path(source_root).expanduser().resolve() if source_root is not None else ROOT
    out = Path(out).expanduser().resolve()
    if not answers_path.is_file():
        raise FileNotFoundError(answers_path)
    if out.exists():
        raise FileExistsError(f"Fresh evaluator output directory required: {out}")
    if not source_root.is_dir():
        raise FileNotFoundError(f"Source root does not exist: {source_root}")
    missing_source = [str(path) for path in SOURCE_FILES if not (source_root / path).is_file()]
    if missing_source:
        raise FileNotFoundError(f"Source root lacks evaluator modules: {missing_source}")

    scorer = provenance()
    if scorer.get("live_matches_pinned") is not True:
        raise ValueError("The original frozen Q9 scorer no longer matches its pinned source hashes")
    expected = _json(data_root / "expected.json")
    code_map = _json(data_root / "code_map.json")
    cache = _load_cache(data_root / "density_cache.jsonl.gz")
    raw_answers = _jsonl(answers_path)
    if not raw_answers:
        raise ValueError("The fresh answers file contains no answer rows")
    answer_rows, answer_by_key, score_counts = _prepare_answers(raw_answers, code_map, cache)
    cases = _jsonl_gz(data_root / "A_paired_cases.jsonl.gz")
    for case in cases:
        case["_original_agent_id"] = str(code_map.get(str(case["agent_id"]), ""))
        if not case["_original_agent_id"]:
            raise ValueError(f"A paired-case alias is missing from code_map: {case['agent_id']}")
    full_wave = defaultdict(list)
    for row in _jsonl_gz(data_root / "A_full_wave_targets.jsonl.gz"):
        full_wave[_month_value(row["month"])].append(row)
    normal_mechanism = _jsonl_gz(data_root / "normal_mechanism.jsonl.gz")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=False)
    scored_path = out / "scored_answers.jsonl.gz"
    _write_jsonl_gz(scored_path, [
        {key: value for key, value in row.items() if key != "agent_id"}
        for row in answer_rows
    ])
    full_wave_rows = _a_full_wave(answer_rows, _jsonl_gz(data_root / "A_full_wave_targets.jsonl.gz"))
    _write_json(out / "A_full_wave_monthly.json", {
        "status": "fresh_A_selected_roster_vs_frozen_full_wave_targets",
        "model_results_are_actual": score_counts["actual_model_results_false"] == 0,
        "monthly": full_wave_rows,
    })
    paired, adapted_cases = _adapt_a_cases(answer_by_key, cases, expected)
    _write_json(out / "A_paired_metrics.json", paired)
    groups = _conditional_groups(adapted_cases)
    _write_json(out / "A_conditional_groups.json", {
        "status": "fresh_A_conditional_metrics" if adapted_cases else "unavailable_no_matched_A_cases",
        "groups": groups,
    })

    normal_summaries = []
    normal_rows_path = out / "normal_rows.jsonl.gz"
    all_normal_rows = []
    normal_key_seen = set()
    for normal in normal_mechanism:
        run = normal["run"]
        if run not in NORMAL_RUNS:
            raise ValueError(f"Only frozen A_Normal and B_Normal frames are supported, found {run}")
        period = str(normal["period"])
        key = run, period
        if key in normal_key_seen:
            raise ValueError(f"Duplicate Normal population frame: {run}/{period}")
        normal_key_seen.add(key)
        summary, new_rows = _build_normal(
            normal,
            period,
            NORMAL_RUNS[run],
            answer_by_key,
            code_map,
            full_wave,
        )
        normal_summaries.append(summary)
        all_normal_rows.extend(new_rows)
    _write_jsonl_gz(normal_rows_path, all_normal_rows)
    _write_json(out / "normal_summary.json", {
        "status": "fresh_tau8_joint_expansion",
        "tau": NORMAL_TAU,
        "normal_draw_seed": NORMAL_DRAW_SEED,
        "monthly": normal_summaries,
        "unavailable_months": [row for row in normal_summaries if row["status"].startswith("unavailable")],
    })

    direct_summaries = _direct_period_summaries(answer_rows, expected)
    normal_map = {(row["run"], row["period"]): row for row in normal_summaries}
    for item in direct_summaries:
        normal_run = "A_Normal" if item["task"] == "A" else "B_Normal" if item["task"] == "B" else None
        normal = normal_map.get((normal_run, item["period"])) if normal_run else None
        item["normal_status"] = normal["status"] if normal else "not_applicable"
        item["normal_q9"] = normal.get("q9") if normal and normal.get("status") == "completed_fresh_joint_expansion" else None
        item["normal_q8"] = normal.get("q8") if normal and normal.get("status") == "completed_fresh_joint_expansion" else None
    national_metrics = _national_metrics(
        expected,
        direct_summaries,
        normal_summaries,
        answer_rows,
        FIXED_A_EARLY48_MSE_ALPHA,
    )
    _write_json(out / "national_metrics.json", national_metrics)
    _write_csv(
        out / "monthly_series.csv",
        [{
            "task": row["task"],
            "period": row["period"],
            "n_answers": row["n_answers"],
            "actual_model_results_n": row["actual_model_results_n"],
            "q9_median_pp": row["q9"].get("median_pp") if row["q9"] else None,
            "q9_iqr_pp": row["q9"].get("iqr_pp") if row["q9"] else None,
            "q8_median_pp": row["q8"].get("median_pp") if row["q8"] else None,
            "q8_iqr_pp": row["q8"].get("iqr_pp") if row["q8"] else None,
            "normal_status": row["normal_status"],
            "normal_q9_median_pp": row["normal_q9"].get("median_pp") if row["normal_q9"] else None,
            "normal_q8_median_pp": row["normal_q8"].get("median_pp") if row["normal_q8"] else None,
            "truth_pp": row["truth_pp"],
            "anchor_pp": row["anchor_pp"],
            "human_micro_evaluation": row["human_micro_evaluation"],
        } for row in direct_summaries],
        ["task", "period", "n_answers", "actual_model_results_n", "q9_median_pp", "q9_iqr_pp",
         "q8_median_pp", "q8_iqr_pp", "normal_status", "normal_q9_median_pp", "normal_q8_median_pp",
         "truth_pp", "anchor_pp", "human_micro_evaluation"],
    )
    downstream = _write_downstream_inputs(expected, normal_summaries, out)
    hashes = {
        name: _sha256(data_root / name)
        for name in EXPECTED_EVALUATION_FILES
    }
    code_hashes = {str(path): _sha256(source_root / path) for path in SOURCE_FILES}
    status = (
        "completed_fresh_model_evaluation"
        if score_counts["actual_model_results_false"] == 0
        else "completed_fixture_only_not_model_evidence"
    )
    output_hashes = {
        path.relative_to(out).as_posix(): _sha256(path)
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.name not in {"summary.json", "manifest.json"}
    }
    summary = {
        "status": status,
        "actual_model_results": score_counts["actual_model_results_false"] == 0,
        "answer_rows": len(answer_rows),
        "answer_counts_by_task": dict(Counter(row["task"] for row in answer_rows)),
        "scoring": {
            "frozen_scorer": scorer,
            "exact_vector_cache_lookups": score_counts["exact_cache_lookups"],
            "new_frozen_scorer_vectors": score_counts["new_frozen_scores"],
            "invalid_or_missing_vectors": score_counts["invalid_or_missing_vectors"],
            "operational_q9_prior_fallbacks": score_counts["q9_prior_fallbacks"],
        },
        "normal": {
            "tau": NORMAL_TAU,
            "fresh_answer_bank_only": True,
            "old_answer_bank_used": False,
            "available_months": sum(row["status"] == "completed_fresh_joint_expansion" for row in normal_summaries),
            "unavailable_months": sum(row["status"].startswith("unavailable") for row in normal_summaries),
            "alpha_mse_frozen_from_A_early48": downstream["alpha"],
        },
        "a_micro_evaluation": {
            "full_wave_months": len(full_wave_rows),
            "paired_case_count": len(adapted_cases),
            "conditional_group_rows": len(groups),
            "status": paired.get("status"),
        },
        "national_metrics": {
            "status": national_metrics["status"],
            "fixed_blend_weight": national_metrics["fixed_blend_weight"],
            "series": {
                name: {
                    "status": block["status"],
                    "period_count": block["period_count"],
                    "covered_forecast_periods": block["covered_forecast_periods"],
                    "missing_forecast_periods": block["missing_forecast_periods"],
                    "excluded_periods": block["excluded_periods"],
                    "metrics": block["metrics"],
                }
                for name, block in national_metrics["series"].items()
            },
        },
        "human_micro_evaluation": {
            "A": "full-wave and paired evaluation from frozen public targets",
            "B_monthly_weekly": "not performed; no human micro targets are supplied",
        },
        "downstream_compatible_outputs": {
            "A": "monthly_predictions_public.csv",
            "B": "monthly_national.csv",
            **downstream,
        },
        "new_model_or_network_calls": 0,
        "reference_value_assertions_on_fresh_results": False,
        "expected_data_usage": [
            "Fixed A/B truth and anchor fields for downstream CSV compatibility.",
            "Frozen A paired-metric weight definition.",
            "The fixed A-early48 MSE combination weight only.",
        ],
        "input_sha256": {"answers.jsonl": _sha256(answers_path), **hashes},
        "source_sha256": code_hashes,
        "output_sha256": output_hashes,
    }
    _write_json(out / "summary.json", summary)
    _write_json(out / "manifest.json", {
        "status": status,
        "new_model_or_network_calls": 0,
        "input_sha256": summary["input_sha256"],
        "source_sha256": code_hashes,
        "output_sha256": {
            path.relative_to(out).as_posix(): _sha256(path)
            for path in sorted(out.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        },
    })
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True,
                        help="Runtime bundle root or data/evaluation directory")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    result = evaluate(args.answers, args.data, args.out, source_root=args.source_root)
    print(json.dumps({"status": result["status"], "out": str(args.out.resolve()),
                      "answer_rows": result["answer_rows"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
