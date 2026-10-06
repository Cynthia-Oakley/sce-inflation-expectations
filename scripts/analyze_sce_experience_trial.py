#!/usr/bin/env python3
"""Analyze the two-month, five-arm SCE price-experience pilot without API calls.

The trial manifest defines the runs and therefore the respondent IDs. This
script never chooses or filters IDs based on their observed answers. Q9 density
means for both simulated and real answers are computed with the same frozen
project scorer. All summaries are descriptive for a matched n=20 pilot.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import (  # noqa: E402
    provenance as scorer_provenance,
    score_q9_frozen,
)

ARMS = (
    "v2_baseline",
    "expression_shared",
    "basket_shared",
    "focus_only",
    "basket_focus",
)
ARM_ALIASES = {
    "baseline": "v2_baseline",
    "original_v2": "v2_baseline",
    "original_v2_baseline": "v2_baseline",
    "original_v2_abstract": "v2_baseline",
    "v2_abstract": "v2_baseline",
    "v2_abstract_baseline": "v2_baseline",
    "sce_q8_q9_v2_abstract": "v2_baseline",
}
CONTRASTS = (
    ("expression_shared", "v2_baseline"),
    ("basket_shared", "expression_shared"),
    ("focus_only", "expression_shared"),
    ("basket_focus", "expression_shared"),
    ("basket_focus", "basket_shared"),
    ("basket_focus", "focus_only"),
)
Q9_KEYS = [f"q9_bin{i}" for i in range(1, 11)]
Q9_SUM_TOLERANCE = 0.5  # The frozen run-time SCE syntax gate; no normalization.
QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _month_key(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"invalid month: {value!r}")
    if isinstance(value, (int, np.integer)):
        result = int(value)
    elif isinstance(value, float) and value.is_integer():
        result = int(value)
    else:
        digits = re.sub(r"\D", "", str(value))
        if len(digits) < 6:
            raise ValueError(f"month must identify YYYYMM: {value!r}")
        result = int(digits[:6])
    if result < 100000 or not 1 <= result % 100 <= 12:
        raise ValueError(f"invalid month: {value!r}")
    return result


def _canonical_arm(value: Any) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    key = ARM_ALIASES.get(key, key)
    if key not in ARMS:
        raise ValueError(f"unknown arm {value!r}; expected one of {', '.join(ARMS)}")
    return key


def _userid(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError(f"invalid respondent ID: {value!r}")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    match = re.fullmatch(r"(?:sce_u|u)?(\d+)", text, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"cannot map agent ID to SCE userid: {value!r}")
    return int(match.group(1))


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"expected a JSON object at {path}:{line_number}")
            rows.append(row)
    return rows


def _resolve_path(raw: str | Path, manifest_path: Path, project_root: Path) -> Path:
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    beside_manifest = (manifest_path.parent / path).resolve()
    beside_root = (project_root / path).resolve()
    if beside_manifest.exists():
        return beside_manifest
    return beside_root


def _payload_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("action_payload", "answer_payload", "payload", "answer", "action"):
        candidate = row.get(key)
        if isinstance(candidate, str):
            try:
                candidate = json.loads(candidate)
            except json.JSONDecodeError:
                continue
        if isinstance(candidate, dict):
            nested = candidate.get("action_payload")
            if isinstance(nested, dict):
                return nested
            return candidate
    if "point_pct" in row or any(k in row for k in Q9_KEYS):
        return row
    return None


def _flatten_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    q9 = result.get("q9")
    if isinstance(q9, dict):
        for i in range(1, 11):
            result.setdefault(f"q9_bin{i}", q9.get(f"bin{i}", q9.get(f"q9_bin{i}")))
    return result


def _records_from_rows(
    rows: Iterable[dict[str, Any]], month: int,
) -> dict[int, dict[str, Any]]:
    answers: dict[int, dict[str, Any]] = {}
    for row in rows:
        if _number(row.get("step")) == 0:
            continue
        payload = _payload_from_row(row)
        if payload is None:
            continue
        payload = _flatten_payload(payload)
        raw_month = payload.get("target_month", row.get("target_month", row.get("month")))
        if raw_month is not None and _month_key(raw_month) != month:
            continue
        raw_id = row.get("agent_id", payload.get("agent_id", row.get("userid")))
        if raw_id is None:
            raise ValueError("answer row has no agent_id/userid")
        uid = _userid(raw_id)
        if uid in answers:
            raise ValueError(f"duplicate answer for userid={uid}, month={month}")
        answers[uid] = {
            "agent_id": str(row.get("agent_id", f"sce_u{uid}")),
            "payload": payload,
        }
    return answers


def _duckdb_rows(path: Path) -> list[dict[str, Any]]:
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - exercised only without runtime dependency
        raise RuntimeError("reading DuckDB runs requires the project's duckdb dependency") from exc
    connection = duckdb.connect(str(path), read_only=True)
    try:
        columns = {row[0] for row in connection.execute("DESCRIBE panel").fetchall()}
        needed = {"agent_id", "step", "action_payload"}
        if not needed.issubset(columns):
            raise ValueError(f"DuckDB panel schema missing {sorted(needed - columns)}: {path}")
        action_kind = "action_kind" if "action_kind" in columns else "NULL AS action_kind"
        found = connection.execute(
            f"SELECT agent_id, step, {action_kind}, action_payload FROM panel "
            "WHERE step >= 1 ORDER BY step, agent_id"
        ).fetchall()
    finally:
        connection.close()
    result = []
    for agent_id, step, kind, payload in found:
        if kind not in (None, "sce_answer", "answer"):
            continue
        if isinstance(payload, str):
            payload = json.loads(payload)
        result.append({"agent_id": agent_id, "step": step, "action_payload": payload})
    return result


def _find_answer_source(
    output_dir: Path, run_manifest: dict[str, Any], project_root: Path,
) -> tuple[Path, str]:
    for relative in (
        "answers.jsonl",
        "answer_records.jsonl",
        "panel_live.jsonl",
        "trajectory/panel_live.jsonl",
    ):
        candidate = output_dir / relative
        if candidate.is_file():
            return candidate, "jsonl"

    db_candidates = [output_dir / "study.duckdb", output_dir / "trajectory" / f"{run_manifest.get('run_id', '')}.duckdb"]
    store_path = run_manifest.get("store_path")
    if store_path:
        stored = Path(store_path).expanduser()
        if not stored.is_absolute():
            stored = (project_root / stored).resolve()
        db_candidates.append(stored)
    for candidate in db_candidates:
        if candidate.is_file():
            return candidate.resolve(), "duckdb"
    raise FileNotFoundError(
        f"no answers.jsonl, panel_live.jsonl, or study.duckdb found for run directory {output_dir}"
    )


def _load_run_answers(
    record: dict[str, Any], manifest_path: Path, project_root: Path,
) -> tuple[dict[int, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    run_id = str(record["run_id"])
    month = _month_key(record["month"])
    arm = _canonical_arm(record["arm"])
    output_dir = _resolve_path(record["output_dir"], manifest_path, project_root)
    if not output_dir.is_dir():
        raise FileNotFoundError(f"run output_dir does not exist: {output_dir}")
    run_manifest_path = output_dir / "run_manifest.json"
    if not run_manifest_path.is_file():
        raise FileNotFoundError(f"run manifest missing: {run_manifest_path}")
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    if str(run_manifest.get("run_id")) != run_id:
        raise ValueError(
            f"trial run_id {run_id!r} does not match {run_manifest_path} run_id "
            f"{run_manifest.get('run_id')!r}"
        )
    answer_path, answer_kind = _find_answer_source(output_dir, run_manifest, project_root)
    answer_rows = _jsonl(answer_path) if answer_kind == "jsonl" else _duckdb_rows(answer_path)
    answers = _records_from_rows(answer_rows, month)
    run_meta = {
        "month": month,
        "arm": arm,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "run_manifest_path": str(run_manifest_path),
        "run_manifest_sha256": sha256_file(run_manifest_path),
        "run_manifest_declared_run_id": run_manifest.get("run_id"),
        "llm_kind": run_manifest.get("llm_kind"),
        "n_agents_declared": run_manifest.get("n_agents"),
        "n_answer_rows_extracted": len(answers),
        "answer_source": {
            "path": str(answer_path),
            "kind": answer_kind,
            "sha256": sha256_file(answer_path),
        },
        "effective_artifact_sha256": run_manifest.get("effective_artifact_sha256", {}),
        "source_snapshot_sha256": run_manifest.get("source_snapshot_sha256", {}),
    }
    for relative, expected_digest in run_manifest.get("effective_artifact_sha256", {}).items():
        source = output_dir / relative
        if source.is_file() and sha256_file(source) != expected_digest:
            raise ValueError(f"effective run artifact checksum mismatch: {source}")
    source_snapshot_audit = {}
    for relative, expected_digest in run_manifest.get("source_snapshot_sha256", {}).items():
        source = output_dir / relative
        exists = source.is_file()
        actual_digest = sha256_file(source) if exists else None
        source_snapshot_audit[relative] = {
            "declared_sha256": expected_digest,
            "actual_sha256": actual_digest,
            "exists": exists,
            "matches_declared": actual_digest == expected_digest if exists else None,
        }
        if exists and actual_digest != expected_digest:
            raise ValueError(f"run source snapshot checksum mismatch: {source}")
    run_meta["source_snapshot_audit"] = source_snapshot_audit
    return answers, run_meta, run_manifest


def _truth_index(path: Path) -> tuple[dict[tuple[int, int], dict[str, Any]], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("per_person")
    if not isinstance(rows, list):
        raise ValueError("truth file has no per_person list")
    truth: dict[tuple[int, int], dict[str, Any]] = {}
    for row in rows:
        month = _month_key(row.get("date", row.get("month", row.get("target_month"))))
        uid = _userid(row.get("userid", row.get("agent_id")))
        key = (month, uid)
        if key in truth:
            raise ValueError(f"duplicate truth key month={month}, userid={uid}")
        truth[key] = row
    return truth, len(rows)


def _extract_bins(payload: dict[str, Any]) -> list[float] | None:
    bins = [_number(payload.get(key)) for key in Q9_KEYS]
    if any(value is None for value in bins):
        return None
    return [float(value) for value in bins if value is not None]


def _truth_bins(row: dict[str, Any]) -> list[float] | None:
    bins = [_number(row.get(f"Q9_bin{i}")) for i in range(1, 11)]
    if any(value is None for value in bins):
        return None
    return [float(value) for value in bins if value is not None]


def _bins_legal(bins: list[float] | None) -> bool:
    return bool(
        bins is not None
        and len(bins) == 10
        and all(math.isfinite(v) and 0 <= v <= 100 for v in bins)
        and abs(sum(bins) - 100) <= Q9_SUM_TOLERANCE
    )


def _score_density(bins: list[float] | None) -> tuple[float | None, str | None]:
    if not _bins_legal(bins):
        return None, "invalid_bins"
    score = score_q9_frozen(bins or [])
    return (_number(score.mean), str(score.status))


def _summary(values: Iterable[float | None]) -> dict[str, Any]:
    array = np.asarray([float(v) for v in values if v is not None and math.isfinite(float(v))], dtype=float)
    if len(array) == 0:
        return {
            "n": 0, "mean": None, "median": None, "std": None,
            "iqr": None, "quantiles": {f"p{int(q * 100):02d}": None for q in QUANTILES},
            "min": None, "max": None,
        }
    quantiles = np.quantile(array, QUANTILES, method="linear")
    mapping = {f"p{int(q * 100):02d}": float(v) for q, v in zip(QUANTILES, quantiles)}
    return {
        "n": int(len(array)),
        "mean": float(np.mean(array)),
        "median": float(mapping["p50"]),
        "std": float(np.std(array, ddof=1)) if len(array) > 1 else 0.0,
        "iqr": float(mapping["p75"] - mapping["p25"]),
        "quantiles": mapping,
        "min": float(np.min(array)),
        "max": float(np.max(array)),
    }


def _empirical_wasserstein(left: list[float], right: list[float]) -> float | None:
    if not left or not right:
        return None
    try:
        from scipy.stats import wasserstein_distance
    except ImportError:  # pragma: no cover
        return None
    return float(wasserstein_distance(left, right))


def _distribution_difference(simulated: list[float], observed: list[float]) -> dict[str, Any]:
    sim_summary = _summary(simulated)
    real_summary = _summary(observed)
    deltas: dict[str, float | None] = {}
    for metric in ("mean", "median", "iqr"):
        a, b = sim_summary[metric], real_summary[metric]
        deltas[f"{metric}_simulated_minus_real"] = a - b if a is not None and b is not None else None
    qdelta = {}
    for key in sim_summary["quantiles"]:
        a, b = sim_summary["quantiles"][key], real_summary["quantiles"][key]
        qdelta[f"{key}_simulated_minus_real"] = a - b if a is not None and b is not None else None
    return {
        "n_matched": min(len(simulated), len(observed)),
        "simulated": sim_summary,
        "matched_real": real_summary,
        "summary_differences": deltas,
        "quantile_differences": qdelta,
        "wasserstein_1": _empirical_wasserstein(simulated, observed),
    }


def _q8_rounding(values: list[float]) -> dict[str, Any]:
    integer = half = tenth = other = 0
    for value in values:
        if abs(value - round(value)) <= 1e-6:
            integer += 1
        elif abs(value * 2 - round(value * 2)) <= 1e-6:
            half += 1
        elif abs(value * 10 - round(value * 10)) <= 1e-6:
            tenth += 1
        else:
            other += 1
    return {
        "n_values": len(values),
        "distinct_numeric_values": len({round(v, 8) for v in values}),
        "rounding_grid_counts": {
            "integer": integer,
            "half_point_only": half,
            "tenth_point_only": tenth,
            "finer_or_other": other,
        },
        "rounding_grid_shares": {
            "integer": integer / len(values) if values else None,
            "half_point_only": half / len(values) if values else None,
            "tenth_point_only": tenth / len(values) if values else None,
            "finer_or_other": other / len(values) if values else None,
        },
    }


def _q9_shape(bin_rows: list[list[float]]) -> dict[str, Any]:
    if not bin_rows:
        return {
            "n_legal_answers": 0,
            "nonzero_bin_count": _summary([]),
            "max_bin_mass_pct": _summary([]),
            "top_two_bin_mass_pct": _summary([]),
            "outer_tail_mass_pct": _summary([]),
            "unique_templates": 0,
            "duplicate_answers_beyond_first": 0,
            "reused_answer_share": None,
            "template_frequency_counts": {},
        }
    template_counts = Counter(tuple(round(v, 10) for v in bins) for bins in bin_rows)
    reused_rows = sum(n for n in template_counts.values() if n > 1)
    frequency_distribution = Counter(template_counts.values())
    return {
        "n_legal_answers": len(bin_rows),
        "nonzero_bin_count": _summary([sum(v > 0 for v in bins) for bins in bin_rows]),
        "max_bin_mass_pct": _summary([max(bins) for bins in bin_rows]),
        "top_two_bin_mass_pct": _summary([sum(sorted(bins, reverse=True)[:2]) for bins in bin_rows]),
        "outer_tail_mass_pct": _summary([bins[0] + bins[1] + bins[8] + bins[9] for bins in bin_rows]),
        "unique_templates": len(template_counts),
        "duplicate_answers_beyond_first": len(bin_rows) - len(template_counts),
        "reused_answer_share": reused_rows / len(bin_rows),
        "template_frequency_counts": {
            str(template_size): int(number_of_templates)
            for template_size, number_of_templates in sorted(frequency_distribution.items())
        },
    }


def _cell_metrics(
    month: int,
    arm: str,
    answers: dict[int, dict[str, Any]],
    truth: dict[tuple[int, int], dict[str, Any]],
    expected_ids: set[int],
    expected_n: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if set(answers) != expected_ids:
        missing = sorted(expected_ids - set(answers))
        extra = sorted(set(answers) - expected_ids)
        raise ValueError(f"{month}/{arm} answer ID mismatch; missing={missing}, extra={extra}")
    if len(answers) != expected_n:
        raise ValueError(f"{month}/{arm} has {len(answers)} answers; expected {expected_n}")

    person_rows: list[dict[str, Any]] = []
    q8_sim_all: list[float] = []
    q9_sim_all: list[float] = []
    q9_legal_bins: list[list[float]] = []
    q8_paired_sim: list[float] = []
    q8_paired_real: list[float] = []
    q9_paired_sim: list[float] = []
    q9_paired_real: list[float] = []
    status_counts: Counter[str] = Counter()
    q9_fit_counts: Counter[str] = Counter()
    q8_available = 0
    q9_legal = 0
    overall_valid = 0

    for uid in sorted(expected_ids):
        payload = answers[uid]["payload"]
        status_raw = payload.get("validation_status")
        status = str(status_raw).lower() if status_raw is not None else "unspecified"
        status_counts[status] += 1
        point = _number(payload.get("point_pct"))
        bins = _extract_bins(payload)
        # Q8 is independently retained for valid or Q9-invalid parsed replies;
        # error/not-answered rows often contain a synthetic zero placeholder.
        # For an invalid reply, keep its parsed Q8 only when the run's validator
        # explicitly says the Q9 bin gate was the failure (not a parse failure).
        llm_meta = payload.get("llm") if isinstance(payload.get("llm"), dict) else {}
        q9_error = str(llm_meta.get("error") or "")
        q9_gate_failure = q9_error == "bin_out_of_range" or q9_error.startswith("q9_sum_")
        q8_parseable_status = status in ("valid", "unspecified") or (status == "invalid" and q9_gate_failure)
        q8_is_legal = point is not None and q8_parseable_status
        q9_is_legal = _bins_legal(bins) and status in ("valid", "unspecified")
        if q8_is_legal:
            q8_available += 1
            q8_sim_all.append(float(point))
        if q9_is_legal:
            q9_legal += 1
            q9_legal_bins.append(bins or [])
        if status == "valid" and q8_is_legal and q9_is_legal:
            overall_valid += 1

        sim_q9, sim_fit_status = _score_density(bins if q9_is_legal else None)
        if sim_fit_status:
            q9_fit_counts[sim_fit_status] += 1
        if sim_q9 is not None:
            q9_sim_all.append(sim_q9)

        gt = truth[(month, uid)]
        real_q8 = _number(gt.get("Q8v2part2"))
        real_bins = _truth_bins(gt)
        real_q9, real_fit_status = _score_density(real_bins)
        q9_fit_counts[f"truth_{real_fit_status or 'missing'}"] += 1
        q8_abs_error = abs(float(point) - real_q8) if q8_is_legal and real_q8 is not None else None
        q9_abs_error = abs(sim_q9 - real_q9) if sim_q9 is not None and real_q9 is not None else None
        if q8_abs_error is not None:
            q8_paired_sim.append(float(point))
            q8_paired_real.append(float(real_q8))
        if q9_abs_error is not None:
            q9_paired_sim.append(float(sim_q9))
            q9_paired_real.append(float(real_q9))
        person_rows.append({
            "userid": uid,
            "agent_id": answers[uid]["agent_id"],
            "validation_status": status,
            "q8_simulated_pct": float(point) if q8_is_legal else None,
            "q8_real_pct": real_q8,
            "q8_absolute_error_pp": q8_abs_error,
            "q9_simulated_density_mean_pct": sim_q9,
            "q9_real_density_mean_pct": real_q9,
            "q9_absolute_error_pp": q9_abs_error,
            "q9_simulated_nonzero_bins": sum(v > 0 for v in bins) if q9_is_legal and bins else None,
            "q9_simulated_fit_status": sim_fit_status,
            "q9_real_fit_status": real_fit_status,
        })

    q8_abs = [r["q8_absolute_error_pp"] for r in person_rows if r["q8_absolute_error_pp"] is not None]
    q9_abs = [r["q9_absolute_error_pp"] for r in person_rows if r["q9_absolute_error_pp"] is not None]
    result = {
        "month": month,
        "arm": arm,
        "n_expected": expected_n,
        "n_answer_rows": len(answers),
        "valid_answer_rate": overall_valid / expected_n,
        "valid_answer_count": overall_valid,
        "validation_status_counts": dict(sorted(status_counts.items())),
        "q8": {
            "legal_n": q8_available,
            "legal_rate": q8_available / expected_n,
            "simulated_all_available": _summary(q8_sim_all),
            "matched_distribution_difference": _distribution_difference(q8_paired_sim, q8_paired_real),
            "absolute_error_pp": _summary(q8_abs),
            "rounding": _q8_rounding(q8_sim_all),
        },
        "q9": {
            "legal_n": q9_legal,
            "legal_rate": q9_legal / expected_n,
            "scored_density_n": len(q9_sim_all),
            "scored_density_rate": len(q9_sim_all) / expected_n,
            "density_simulated_all_scored": _summary(q9_sim_all),
            "matched_distribution_difference": _distribution_difference(q9_paired_sim, q9_paired_real),
            "absolute_error_pp": _summary(q9_abs),
            "fit_status_counts": dict(sorted(q9_fit_counts.items())),
            "answer_shape": _q9_shape(q9_legal_bins),
        },
    }
    return result, person_rows


def _paired_summary(values: list[float]) -> dict[str, Any]:
    return _summary(values)


def _contrast_metrics(
    month: int,
    treatment_arm: str,
    reference_arm: str,
    people: dict[str, dict[int, dict[str, Any]]],
) -> dict[str, Any]:
    treatment, reference = people[treatment_arm], people[reference_arm]
    paired: dict[str, dict[str, list[float]]] = {
        "q8": {"answer_delta": [], "absolute_error_change": []},
        "q9": {"answer_delta": [], "absolute_error_change": []},
    }
    individual = []
    for uid in sorted(set(treatment) & set(reference)):
        tr, ref = treatment[uid], reference[uid]
        person = {"userid": uid}
        for key, value_key, error_key in (
            ("q8", "q8_simulated_pct", "q8_absolute_error_pp"),
            ("q9", "q9_simulated_density_mean_pct", "q9_absolute_error_pp"),
        ):
            a, b = tr[value_key], ref[value_key]
            if a is not None and b is not None:
                delta = float(a - b)
                paired[key]["answer_delta"].append(delta)
                person[f"{key}_answer_delta_treatment_minus_reference"] = delta
            else:
                person[f"{key}_answer_delta_treatment_minus_reference"] = None
            ae, be = tr[error_key], ref[error_key]
            if ae is not None and be is not None:
                error_change = float(ae - be)
                paired[key]["absolute_error_change"].append(error_change)
                person[f"{key}_absolute_error_change_treatment_minus_reference"] = error_change
            else:
                person[f"{key}_absolute_error_change_treatment_minus_reference"] = None
        individual.append(person)
    return {
        "month": month,
        "treatment_arm": treatment_arm,
        "reference_arm": reference_arm,
        "q8": {
            "paired_n_answer": len(paired["q8"]["answer_delta"]),
            "answer_delta_pp": _paired_summary(paired["q8"]["answer_delta"]),
            "paired_n_absolute_error": len(paired["q8"]["absolute_error_change"]),
            "absolute_error_change_pp": _paired_summary(paired["q8"]["absolute_error_change"]),
        },
        "q9": {
            "paired_n_answer": len(paired["q9"]["answer_delta"]),
            "answer_delta_pp": _paired_summary(paired["q9"]["answer_delta"]),
            "paired_n_absolute_error": len(paired["q9"]["absolute_error_change"]),
            "absolute_error_change_pp": _paired_summary(paired["q9"]["absolute_error_change"]),
        },
        "per_person": individual,
    }


def _scorer_sources() -> dict[str, Any]:
    paths = {
        "frozen_dispatch": ROOT / "studies/sce_inflation_expectations/scoring/sce_q9_frozen.py",
        "base_scorer": ROOT / "studies/sce_inflation_expectations/scoring/sce_q9.py",
        "beta_fit_kernel": ROOT / "studies/sce_inflation_expectations/scoring/beta_fit_kernel.py",
    }
    try:
        status = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--short", "--", *[str(p.relative_to(ROOT)) for p in paths.values()]],
            check=False, capture_output=True, text=True,
        ).stdout.splitlines()
        git_status = {line[3:]: line[:2].strip() for line in status if len(line) >= 4}
    except OSError:  # pragma: no cover
        git_status = None
    return {
        "provenance": scorer_provenance(),
        "source_sha256": {name: sha256_file(path) for name, path in paths.items() if path.is_file()},
        "git_status": git_status,
        "review_note": (
            "The report records the live scorer bytes, including any local dirty dependency; "
            "a pending review state does not change or silently replace the scorer."
        ),
    }


def analyze_trial(
    trial_manifest_path: Path,
    truth_path: Path,
    *,
    project_root: Path = ROOT,
    expected_n: int = 20,
    required_months: tuple[int, ...] = (202105, 202106),
) -> dict[str, Any]:
    trial_manifest_path = trial_manifest_path.resolve()
    truth_path = truth_path.resolve()
    trial_payload = json.loads(trial_manifest_path.read_text(encoding="utf-8"))
    records = trial_payload.get("records")
    if not isinstance(records, list):
        raise ValueError("trial manifest must contain a records list")
    required_months = tuple(_month_key(v) for v in required_months)
    truth, truth_row_count = _truth_index(truth_path)

    seen_cells: set[tuple[int, str]] = set()
    run_payloads: dict[tuple[int, str], dict[int, dict[str, Any]]] = {}
    run_meta: dict[tuple[int, str], dict[str, Any]] = {}
    month_ids: dict[int, set[int]] = {}
    for record in records:
        for field in ("month", "arm", "run_id", "output_dir"):
            if field not in record:
                raise ValueError(f"trial record missing required field {field!r}: {record}")
        month, arm = _month_key(record["month"]), _canonical_arm(record["arm"])
        cell = (month, arm)
        if cell in seen_cells:
            raise ValueError(f"duplicate trial cell: {month}/{arm}")
        seen_cells.add(cell)
        answers, metadata, _ = _load_run_answers(record, trial_manifest_path, project_root)
        run_payloads[cell] = answers
        run_meta[cell] = metadata
        if len(answers) != expected_n:
            raise ValueError(f"{month}/{arm} contains {len(answers)} answer rows; expected {expected_n}")
        ids = set(answers)
        if month in month_ids and month_ids[month] != ids:
            raise ValueError(f"the five arms do not share the same IDs for month {month}")
        month_ids[month] = ids
        missing_truth = sorted(uid for uid in ids if (month, uid) not in truth)
        if missing_truth:
            raise ValueError(
                f"truth file lacks selected IDs for {month}: {missing_truth}; "
                "the analyzer will not substitute or select respondents"
            )

    actual_months = tuple(sorted({month for month, _ in seen_cells}))
    if actual_months != tuple(sorted(required_months)):
        raise ValueError(f"trial months are {actual_months}; expected {tuple(sorted(required_months))}")
    expected_cells = {(month, arm) for month in required_months for arm in ARMS}
    if seen_cells != expected_cells:
        missing = sorted(expected_cells - seen_cells)
        extra = sorted(seen_cells - expected_cells)
        raise ValueError(f"trial cell set mismatch; missing={missing}, extra={extra}")

    cells: dict[str, dict[str, Any]] = {}
    person_results: dict[int, dict[str, dict[int, dict[str, Any]]]] = {}
    for month in sorted(required_months):
        person_results[month] = {}
        cells[str(month)] = {}
        ids = month_ids[month]
        if len(ids) != expected_n:
            raise ValueError(f"month {month} contains {len(ids)} unique IDs; expected {expected_n}")
        for arm in ARMS:
            summary, per_person = _cell_metrics(
                month, arm, run_payloads[(month, arm)], truth, ids, expected_n,
            )
            cells[str(month)][arm] = {**summary, "run": run_meta[(month, arm)]}
            person_results[month][arm] = {row["userid"]: row for row in per_person}
            cells[str(month)][arm]["per_person"] = per_person

    contrasts = []
    for month in sorted(required_months):
        for treatment_arm, reference_arm in CONTRASTS:
            contrasts.append(_contrast_metrics(
                month, treatment_arm, reference_arm, person_results[month],
            ))

    script_path = Path(__file__).resolve()
    return {
        "schema_version": "sce-experience-trial-analysis-v1",
        "manifest": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "analysis_script": str(script_path),
            "analysis_script_sha256": sha256_file(script_path),
            "trial_manifest_path": str(trial_manifest_path),
            "trial_manifest_sha256": sha256_file(trial_manifest_path),
            "truth_path": str(truth_path),
            "truth_sha256": sha256_file(truth_path),
            "truth_row_count": truth_row_count,
            "project_root": str(project_root.resolve()),
            "expected_n_per_month_arm": expected_n,
            "months": list(sorted(required_months)),
            "arms": list(ARMS),
            "run_sources": [run_meta[(month, arm)] for month in sorted(required_months) for arm in ARMS],
            "scorer": _scorer_sources(),
        },
        "design_notes": [
            "Every arm is compared on the IDs present in its same-month sibling runs; IDs are never selected from truth.",
            "Q9 simulated and real answers are both scored with the same live frozen project scorer recorded above.",
            "The 20-person cells have limited power; estimates are descriptive and should not be treated as confirmatory.",
            "Higher simulated variance alone is not a success criterion.",
            "This pilot does not select a winning arm or provide independent validation; a separate held-out period is required.",
            "Q8 and Q9 availability masks are reported independently; invalid/error placeholders are excluded from that question's estimates.",
            "Q9 bins are never normalized; only syntactically legal ten-bin answers enter scoring and shape summaries.",
        ],
        "monthly_by_arm": cells,
        "paired_contrasts": contrasts,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-manifest", type=Path, required=True)
    parser.add_argument(
        "--truth", type=Path,
        default=ROOT / "data/evaluation/sce_truth_main2021.json",
        help="evaluation-only truth JSON built by build_sce_evaluation_truth.py",
    )
    parser.add_argument("--out", type=Path, required=True, help="write report JSON to this path")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--expected-n", type=int, default=20)
    parser.add_argument("--months", default="202105,202106", help="required comma-separated YYYYMM cells")
    args = parser.parse_args(argv)
    if args.expected_n < 1:
        parser.error("--expected-n must be positive")
    try:
        months = tuple(_month_key(part) for part in args.months.split(",") if part.strip())
        result = analyze_trial(
            args.trial_manifest, args.truth, project_root=args.project_root.resolve(),
            expected_n=args.expected_n, required_months=months,
        )
        out = args.out.expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError) as exc:
        parser.exit(2, f"analysis failed: {exc}\n")
    print(f"Analyzed {len(result['manifest']['months'])} months × {len(ARMS)} arms × "
          f"{args.expected_n} matched IDs; no model or MCP calls made.")
    print(out)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through CLI by users
    raise SystemExit(main())
