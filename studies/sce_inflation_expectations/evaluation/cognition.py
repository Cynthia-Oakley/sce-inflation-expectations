"""Offline evaluation for the three-arm SCE cognition presentation pilot.

The evaluator audits completed run artifacts, the pinned scored truth, and the
selected respondents' current ten-bin answers from a pinned evaluation cache.
It never calls a model or opens the original survey workbooks. Both model and
human density means/IQRs use the same frozen project fitter. Invalid
probabilities remain failures and are never clipped, normalized, or repaired.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

import duckdb
import numpy as np
from scipy.stats import spearmanr

from .metrics import quantile, wasserstein1
from ..cognition_runtime import ARMS
from ..model import parse_sce_response, validate_sce_bins
from ..prior_belief_experiment import message_hash
from ..revision_format_runtime import REPLY_MARKER
from ..scoring.sce_q9_frozen import provenance, score_q9_frozen

ROOT = Path(__file__).resolve().parents[3]
TRUTH = ROOT / "outputs/sce_information_update_evaluation_20261014_v1/cases_private.json"
REFERENCE = ROOT / "outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet"
EXPECTED_MONTH_COUNT = 4
EXPECTED_N_PER_MONTH = 24
EXPECTED_REPEATS = (1, 2)
VALIDITY_THRESHOLD = .99
BOOTSTRAP_SEED = 20261016
PRIMARY_METRIC = "individual_density_iqr_mae_pp"
PRIMARY_CONTRAST = ("faithful_paraphrase", "question_answer")
REGISTERED_CONTRASTS = (
    ("faithful_paraphrase", "question_answer"),
    ("question_answer", "label_only"),
    ("faithful_paraphrase", "label_only"),
)
Q9_METRICS = (
    "probability_tv_pct",
    "individual_density_iqr_mae_pp",
    "individual_density_iqr_bias_pp",
    "individual_density_iqr_mean_pp",
    "real_individual_density_iqr_mean_pp",
    "individual_density_mean_mae_pp",
    "individual_density_mean_bias_pp",
    "q9_center_mae_pp",
    "q9_center_bias_pp",
    "cross_section_w1_pp",
    "delta_w1_pp",
    "cross_person_iqr_pp",
    "real_cross_person_iqr_pp",
    "cross_person_iqr_gap_pp",
    "zero_deflation_rate",
    "real_zero_deflation_rate",
    "zero_deflation_rate_difference",
    "person_mean_spearman",
)
Q8_METRICS = (
    "q8_person_mae_pp",
    "q8_person_bias_pp",
    "q8_center_mae_pp",
    "q8_center_bias_pp",
    "q8_cross_section_w1_pp",
    "q8_person_spearman",
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _float_or_none(value):
    return float(value) if finite(value) else None


def _safe_relative(base: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe relative artifact path: {relative}")
    resolved_base = base.resolve()
    resolved = (resolved_base / path).resolve()
    if not resolved.is_relative_to(resolved_base):
        raise ValueError(f"Artifact escapes its root: {relative}")
    return resolved


def _read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _validate_protocol(protocol: dict, manifest: dict) -> tuple[list[int], list[int]]:
    arms = protocol.get("arms")
    if arms != list(ARMS):
        raise ValueError("Cognition arms differ from the registered three-arm design")
    months = protocol.get("months")
    if (not isinstance(months, list) or len(months) != EXPECTED_MONTH_COUNT
            or len(set(months)) != EXPECTED_MONTH_COUNT
            or any(isinstance(m, bool) or not isinstance(m, int) for m in months)):
        raise ValueError("Protocol must contain four distinct integer development months")
    if protocol.get("n_per_month") != EXPECTED_N_PER_MONTH:
        raise ValueError("Cognition pilot expects 24 respondents per month")
    repeats = protocol.get("generation_repeats")
    if not isinstance(repeats, list) or tuple(repeats) != EXPECTED_REPEATS:
        raise ValueError("Cognition pilot expects generation repeats [1, 2]")
    planned = EXPECTED_MONTH_COUNT * EXPECTED_N_PER_MONTH * len(ARMS) * len(repeats)
    if protocol.get("planned_calls") != planned or manifest.get("planned_calls") != planned:
        raise ValueError("Protocol/manifest planned-call count does not match 4×24×3×2")
    if protocol.get("primary_metric") != PRIMARY_METRIC:
        raise ValueError("Protocol primary metric differs from the registered IQR-MAE")
    contrast = str(protocol.get("primary_contrast", "")).lower()
    if not all(part in contrast for part in PRIMARY_CONTRAST):
        raise ValueError("Protocol primary contrast must be faithful_paraphrase minus question_answer")
    expected_secondary = ("question_answer minus label_only", "faithful_paraphrase minus label_only")
    if protocol.get("secondary_contrasts") != list(expected_secondary):
        raise ValueError("Protocol secondary contrasts differ from the registered design")
    if protocol.get("stratum_n") != {"high": 14, "low": 10}:
        raise ValueError("Cognition roster must use the registered 14 High/10 Low allocation")
    if "Low oversampled" not in str(protocol.get("sampling", "")):
        raise ValueError("Protocol must disclose the fixed Low-numeracy oversample")
    return list(months), list(repeats)


def _verify_declared_hashes(root: Path, hashes: dict, kind: str,
                            required_paths: set[str] | None = None) -> dict[str, str]:
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError(f"{kind} hash manifest is missing")
    if required_paths is not None and not required_paths.issubset(hashes):
        missing = sorted(required_paths - set(hashes))
        raise ValueError(f"{kind} manifest does not pin required evaluation inputs: {missing}")
    checked = {}
    # Source manifests also contain original survey workbooks. The evaluator
    # checks only its pinned evaluation truth/cache; it never opens or hashes
    # unrelated raw survey files.
    paths = hashes if required_paths is None else {p: hashes[p] for p in required_paths}
    for relative, expected in paths.items():
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"Malformed {kind} hash for {relative}")
        path = _safe_relative(root, relative)
        if not path.is_file():
            raise ValueError(f"Missing {kind} input: {relative}")
        actual = sha(path)
        if actual != expected:
            raise ValueError(f"{kind} hash mismatch: {relative}")
        checked[relative] = actual
    return checked


def _truth_lookup(path: Path):
    rows = _read_json(path)
    if not isinstance(rows, list):
        raise ValueError("Pinned truth must be a list of evaluation rows")
    fields = ("actual", "actual_iqr", "actual_zero_deflation", "actual_point", "previous",
              "previous_bins", "profile")
    truth = {}
    for row in rows:
        key = (int(row["month"]), str(row["agent_id"]))
        value = {field: row.get(field) for field in fields}
        value["userid"] = int(row["userid"])
        if key in truth and truth[key] != value:
            raise ValueError("Pinned truth differs across repeated-generation rows")
        truth[key] = value
    for target in truth.values():
        previous_bins = target.get("previous_bins")
        previous = target.get("previous")
        if isinstance(previous_bins, list) and len(previous_bins) == 10 and all(finite(v) for v in previous_bins):
            rescored = _score_bins([float(v) for v in previous_bins])
            if finite(previous) != finite(rescored["mean"]) or (finite(previous) and not _close(previous, rescored["mean"], atol=1e-6)):
                raise ValueError("Pinned previous-state bins do not reproduce the registered previous mean")
        elif finite(previous):
            raise ValueError("Pinned previous-state mean has no matching ten-bin probability vector")
    return truth


def _load_reference(rows: list[dict], path: Path) -> tuple[dict, dict]:
    """Read only the selected current-month identifiers and the required Q9 fields."""
    keys = sorted({(int(row["month"]), int(row["userid"])) for row in rows})
    if not keys:
        raise ValueError("Cannot load ten-bin truth without a selected roster")
    fields = [f'Q9_bin{i}' for i in range(1, 11)]
    projection = ", ".join(["date", "userid", *fields, "Q9_mean", "Q9_iqr"])
    predicate = " OR ".join(f"(date={month} AND userid={userid})" for month, userid in keys)
    connection = duckdb.connect()
    try:
        fetched = connection.execute(
            f"SELECT {projection} FROM read_parquet(?) WHERE {predicate}", [str(path)]
        ).fetchall()
    finally:
        connection.close()
    reference = {}
    for raw in fetched:
        month, userid = int(raw[0]), int(raw[1])
        key = month, userid
        if key in reference:
            raise ValueError("Ten-bin reference has duplicate respondent-month rows")
        bins = [_float_or_none(value) for value in raw[2:12]]
        reference[key] = {
            "q9_bins": bins,
            "official_q9_mean": _float_or_none(raw[12]),
            "official_q9_iqr": _float_or_none(raw[13]),
        }
    missing = set(keys) - set(reference)
    if missing:
        raise ValueError(f"Ten-bin reference omits {len(missing)} selected respondent-months")

    truth = {(int(row["month"]), int(row["userid"])): row for row in rows}
    if len(truth) != len(rows):
        raise ValueError("Evaluation roster has duplicate respondent-month keys")
    frozen_rescore_n = 0
    official_diff = {"q9_mean": [], "q9_iqr": []}
    invalid_or_missing_bins = 0
    for key, entry in reference.items():
        bins = entry["q9_bins"]
        target = truth[key]
        scored = _score_bins(bins) if all(finite(v) for v in bins) else {
            "mean": None, "iqr": None, "zero_deflation": None, "scorer_status": "missing_bins"
        }
        if finite(scored["mean"]) and finite(scored["iqr"]):
            frozen_rescore_n += 1
        else:
            invalid_or_missing_bins += 1
        for truth_field, score_field in (("actual", "mean"), ("actual_iqr", "iqr")):
            expected, actual = target.get(truth_field), scored.get(score_field)
            if finite(expected) != finite(actual) or (finite(expected) and not _close(expected, actual, atol=1e-6)):
                raise ValueError("Cached ten-bin truth does not reproduce pinned TRUTH with frozen scorer")
        for field, official_key, truth_key in (
                ("q9_mean", "official_q9_mean", "actual"),
                ("q9_iqr", "official_q9_iqr", "actual_iqr")):
            official, pinned = entry[official_key], target.get(truth_key)
            if finite(official) and finite(pinned):
                official_diff[field].append(abs(float(official) - float(pinned)))
    official_diagnostics = {}
    for field, differences in official_diff.items():
        official_diagnostics[field] = {
            "n_finite_paired": len(differences),
            "mean_absolute_difference": float(np.mean(differences)) if differences else None,
            "max_absolute_difference": float(np.max(differences)) if differences else None,
            "n_above_0_01": sum(value > .01 for value in differences),
            "interpretation": "Sensitivity diagnostic only; official summary fields do not replace ten-bin truth or frozen-scorer metrics.",
        }
    return reference, {
        "frozen_rescore_matches_pinned_truth_n": frozen_rescore_n,
        "missing_or_unscorable_bin_truth_n": invalid_or_missing_bins,
        "comparison_tolerance": 1e-6,
        "official_summary_field_differences": official_diagnostics,
    }


def _validate_links(folder: Path, months: list[int], truth: dict, protocol: dict):
    links = _read_json(folder / "evaluation_links_private.json")
    if not isinstance(links, list):
        raise ValueError("Private evaluation roster must be a list")
    expected_months = set(months)
    links_by_key = {}
    for link in links:
        month, agent_id = int(link["month"]), str(link["agent_id"])
        key = month, agent_id
        if month not in expected_months or key in links_by_key:
            raise ValueError("Roster has an unknown month or duplicate person-month")
        if key not in truth:
            raise ValueError("Pinned truth is missing a selected person-month")
        if int(link["userid"]) != truth[key]["userid"]:
            raise ValueError("Roster person does not match pinned truth")
        profile = link.get("profile")
        if not isinstance(profile, dict) or str(profile.get("numeracy", "")).lower() not in ("high", "low"):
            raise ValueError("Roster must carry a High/Low numeracy label for descriptive grouping")
        if profile != truth[key]["profile"]:
            raise ValueError("Roster profile differs from pinned truth")
        weight = link.get("survey_weight")
        if not finite(weight) or float(weight) <= 0:
            raise ValueError("Roster survey weight must be finite and positive")
        raw_weight = link.get("raw_parent_survey_weight")
        sampling_weight = link.get("sampling_weight")
        if (not finite(raw_weight) or float(raw_weight) <= 0
                or not finite(sampling_weight) or float(sampling_weight) <= 0
                or not _close(float(weight), float(raw_weight) * float(sampling_weight), atol=1e-8)):
            raise ValueError("Auxiliary survey weight must equal parent weight × inverse inclusion probability")
        links_by_key[key] = {**link, "month": month, "agent_id": agent_id,
                             "userid": int(link["userid"]), "survey_weight": float(weight),
                             "raw_parent_survey_weight": float(raw_weight),
                             "sampling_weight": float(sampling_weight)}
    if len(links_by_key) != len(months) * EXPECTED_N_PER_MONTH:
        raise ValueError("Roster must contain exactly 24 selected respondents per month")
    for month in months:
        rows = [r for (m, _), r in links_by_key.items() if m == month]
        if len(rows) != EXPECTED_N_PER_MONTH or len({r["userid"] for r in rows}) != EXPECTED_N_PER_MONTH:
            raise ValueError(f"Roster has duplicate/missing respondents in {month}")
        counts = Counter(str(r["profile"]["numeracy"]).lower() for r in rows)
        if counts != Counter({"high": 14, "low": 10}):
            raise ValueError(f"Roster does not match the registered 14 High/10 Low allocation in {month}")
        for label, n_sample in (("high", 14), ("low", 10)):
            stratum = [r for r in rows if str(r["profile"]["numeracy"]).lower() == label]
            factors = {round(r["sampling_weight"], 10) for r in stratum}
            if len(factors) != 1:
                raise ValueError(f"Sampling weights vary within the {label} stratum in {month}")
            parent_n = n_sample * stratum[0]["sampling_weight"]
            if parent_n < n_sample or abs(parent_n - round(parent_n)) > 1e-8:
                raise ValueError(f"Sampling weight does not encode a whole parent stratum in {month}")
    return links_by_key


def _validate_preview(folder: Path, month: int, arm: str, agent_ids: set[str]):
    path = folder / str(month) / f"preview_{arm}.json"
    rows = _read_json(path)
    if not isinstance(rows, list) or len(rows) != len(agent_ids):
        raise ValueError(f"Preview cardinality mismatch for {month}/{arm}")
    result = {}
    for row in rows:
        agent_id = str(row["agent_id"])
        messages = row.get("messages")
        digest = row.get("prompt_sha256")
        if agent_id in result or agent_id not in agent_ids:
            raise ValueError(f"Preview roster mismatch for {month}/{arm}")
        if not isinstance(messages, list) or message_hash(messages) != digest:
            raise ValueError(f"Preview message hash mismatch for {month}/{arm}/{agent_id}")
        result[agent_id] = {"prompt_sha256": digest, "messages": messages}
    if set(result) != agent_ids:
        raise ValueError(f"Preview omits selected agents for {month}/{arm}")
    return result


def _validate_shared_base_prompts(previews: dict, months: list[int], agent_ids_by_month: dict):
    """Verify all arms use identical prior/future prompt text around the inserted block."""
    for month in months:
        for agent_id in agent_ids_by_month[month]:
            baseline = previews[month, "label_only"][agent_id]["messages"]
            if not isinstance(baseline, list) or len(baseline) != 1 or baseline[0].get("role") != "user":
                raise ValueError("Cognition previews must contain the registered single user prompt")
            base_text = baseline[0].get("content")
            if not isinstance(base_text, str) or base_text.count(REPLY_MARKER) != 1:
                raise ValueError("Label-only preview has no unique response boundary")
            base_prefix, base_suffix = base_text.split(REPLY_MARKER, 1)
            for arm in ARMS:
                messages = previews[month, arm][agent_id]["messages"]
                if (not isinstance(messages, list) or len(messages) != 1
                        or messages[0].get("role") != "user"):
                    raise ValueError("Cognition preview shape changed across arms")
                text = messages[0].get("content")
                if not isinstance(text, str) or text.count(REPLY_MARKER) != 1:
                    raise ValueError("Cognition preview has no unique response boundary")
                prefix, suffix = text.split(REPLY_MARKER, 1)
                if suffix != base_suffix:
                    raise ValueError("Prior/future base prompt differs across cognition arms")
                if arm == "label_only":
                    if prefix != base_prefix:
                        raise ValueError("Label-only prompt differs from the registered base input")
                elif (not prefix.startswith(base_prefix)
                      or not prefix[len(base_prefix):].startswith("Your earlier survey responses:\n")):
                    raise ValueError("Detailed arm changed the base input or omitted its cognition block")


def _action_bins(payload: dict) -> list[float]:
    try:
        return [float(payload[f"q9_bin{i}"]) for i in range(1, 11)]
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Action is missing numeric Q9 bins") from exc


def _close(left, right, *, atol=1e-8):
    return finite(left) and finite(right) and abs(float(left) - float(right)) <= atol


def _audit_raw_reply(raw: str, call: dict, payload: dict, arm: str) -> tuple[dict | None, str | None]:
    """Rebuild Q8/Q9 from the original reply and bind it to the saved action."""
    parsed, parse_error = parse_sce_response(raw)
    status = payload.get("validation_status")
    if status not in ("valid", "invalid", "error"):
        raise ValueError("Unknown response validation status")
    bins = _action_bins(payload)
    point = payload.get("point_pct")
    if status == "valid":
        valid, _, _ = validate_sce_bins(parsed["bins"] if parsed is not None else [])
        if call.get("error") is not None or parse_error is not None or not valid:
            raise ValueError("Action is valid but original reply is not a legal answer")
        if not _close(round(parsed["point_pct"], 4), point) or not np.allclose(
                parsed["bins"], bins, rtol=0, atol=1e-8):
            raise ValueError("Original valid reply differs from DuckDB action")
        return parsed, None
    if status == "invalid":
        if call.get("error") is not None:
            raise ValueError("Invalid action is marked as an API-call error")
        if parsed is None:
            if not _close(point, 0.0) or not np.allclose(bins, np.zeros(10), rtol=0, atol=1e-12):
                raise ValueError("Unparseable reply differs from the runtime's invalid fallback")
        else:
            valid, _, _ = validate_sce_bins(parsed["bins"])
            if valid:
                raise ValueError("Action is invalid but original reply has legal Q9 probabilities")
            if not _close(round(parsed["point_pct"], 4), point) or not np.allclose(
                    parsed["bins"], bins, rtol=0, atol=1e-8):
                raise ValueError("Original invalid reply differs from DuckDB action")
        return parsed, parse_error
    # Completed cognition jobs should not normally contain provider errors, but
    # preserve and count them if present instead of converting them to forecasts.
    if call.get("error") is None and raw:
        raise ValueError("Error action has neither a call error nor an empty reply")
    return None, parse_error or str(call.get("error") or "call_error")


def _score_bins(bins: list[float]) -> dict:
    valid, reason, _ = validate_sce_bins(bins)
    if not valid:
        return {"mean": None, "iqr": None, "zero_deflation": None,
                "scorer_status": "invalid_bins", "validation_error": reason}
    result = score_q9_frozen(bins)
    return {
        "mean": _float_or_none(result.mean),
        "iqr": _float_or_none(result.iqr),
        "zero_deflation": float(sum(bins[5:]) == 0),
        "scorer_status": result.status,
        "validation_error": None,
    }


def load(folder: Path) -> dict:
    """Load, hash-check, and independently reconstruct a completed cognition trial."""
    folder = Path(folder).resolve()
    manifest_path, protocol_path = folder / "manifest.json", folder / "protocol.json"
    manifest, protocol = _read_json(manifest_path), _read_json(protocol_path)
    protocol_hash = sha(protocol_path)
    if manifest.get("protocol_sha256") != protocol_hash:
        raise ValueError("Protocol hash differs from the prepared manifest")
    if not provenance()["live_matches_pinned"]:
        raise ValueError("Frozen Q9 scorer has changed")
    months, repeats = _validate_protocol(protocol, manifest)
    prepared_hashes = _verify_declared_hashes(folder, manifest.get("prepared_file_sha256"), "prepared input")
    truth_relative = str(TRUTH.resolve().relative_to(ROOT.resolve()))
    declared_sources = manifest.get("source_sha256", {})
    reference_relative = str(REFERENCE.resolve().relative_to(ROOT.resolve()))
    verified_sources = _verify_declared_hashes(
        ROOT, declared_sources, "source", {truth_relative, reference_relative})
    truth = _truth_lookup(TRUTH)
    links = _validate_links(folder, months, truth, protocol)
    truth_for_roster = []
    for (month, agent_id), link in links.items():
        target = truth[month, agent_id]
        truth_for_roster.append({"month": month, "userid": link["userid"],
                                 "actual": target["actual"], "actual_iqr": target["actual_iqr"]})
    reference, reference_diagnostics = _load_reference(truth_for_roster, REFERENCE)
    agent_ids_by_month = {
        month: {agent_id for m, agent_id in links if m == month} for month in months
    }

    expected_jobs = {(month, arm, repeat) for month in months for arm in ARMS for repeat in repeats}
    jobs = manifest.get("jobs")
    jobs_by_key = {}
    for job in jobs or []:
        key = (int(job["month"]), str(job["arm"]), int(job["repeat"]))
        if key not in expected_jobs or key in jobs_by_key:
            raise ValueError("Manifest jobs contain an unknown or duplicate trial cell")
        run_id = job.get("run_id")
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
            raise ValueError("Unsafe or missing run identifier")
        jobs_by_key[key] = job
    if set(jobs_by_key) != expected_jobs:
        raise ValueError("Manifest does not contain all 4×3×2 registered jobs")

    previews = {
        (month, arm): _validate_preview(folder, month, arm, agent_ids_by_month[month])
        for month in months for arm in ARMS
    }
    _validate_shared_base_prompts(previews, months, agent_ids_by_month)
    actions = {}
    coverage = {arm: Counter() for arm in ARMS}
    scorable = Counter()
    source_hashes = {**verified_sources, **prepared_hashes}
    estimated_cost = 0.0
    raw_replies_reconstructed = 0

    for key in sorted(expected_jobs):
        month, arm, repeat = key
        job = jobs_by_key[key]
        run_dir = _safe_relative(ROOT / "outputs" / "local_runs", job["run_id"])
        run_path = run_dir / "run_manifest.json"
        db_path = run_dir / "study.duckdb"
        calls_path = run_dir / "llm_calls.jsonl"
        for path in (run_path, db_path, calls_path):
            if not path.is_file():
                raise ValueError(f"Missing completed-run artifact for {job['run_id']}: {path.name}")
            source_hashes[str(path.relative_to(ROOT))] = sha(path)
        run = _read_json(run_path)
        if (run.get("status") != "completed" or run.get("llm_kind") != "openai"
                or int(run.get("n", -1)) != EXPECTED_N_PER_MONTH
                or run.get("run_id") != job["run_id"]
                or run.get("arm") != arm or int(run.get("month", -1)) != month
                or int(run.get("repeat", -1)) != repeat
                or run.get("protocol_sha256") != protocol_hash
                or int(run.get("cost", {}).get("call_count", -1)) != EXPECTED_N_PER_MONTH):
            raise ValueError(f"Run manifest does not match the registered cell: {job['run_id']}")
        estimated_cost += float(run["cost"].get("estimated_cost_usd", 0.0))

        call_rows = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(call_rows) != EXPECTED_N_PER_MONTH:
            raise ValueError(f"Expected one original LLM call per respondent: {job['run_id']}")
        calls = {}
        for call in call_rows:
            agent_id = str(call["agent_id"])
            if agent_id in calls or agent_id not in agent_ids_by_month[month]:
                raise ValueError(f"LLM-call roster mismatch: {job['run_id']}")
            if (call.get("run_id") != job["run_id"] or int(call.get("attempt_idx", -1)) != 0
                    or call.get("target_month") != f"{month // 100:04d}-{month % 100:02d}"):
                raise ValueError(f"LLM-call metadata mismatch: {job['run_id']}")
            calls[agent_id] = call
        if set(calls) != agent_ids_by_month[month]:
            raise ValueError(f"LLM-call file omits a selected respondent: {job['run_id']}")

        db = duckdb.connect(str(db_path), read_only=True)
        try:
            rows = db.execute(
                "SELECT agent_id, action_payload FROM panel "
                "WHERE step=1 AND action_kind='sce_answer'"
            ).fetchall()
        finally:
            db.close()
        if len(rows) != EXPECTED_N_PER_MONTH:
            raise ValueError(f"DuckDB action cardinality mismatch: {job['run_id']}")
        payloads = {}
        for agent_id_value, payload_value in rows:
            agent_id = str(agent_id_value)
            payload = json.loads(payload_value) if isinstance(payload_value, str) else payload_value
            if agent_id in payloads or agent_id not in agent_ids_by_month[month] or not isinstance(payload, dict):
                raise ValueError(f"DuckDB action roster mismatch: {job['run_id']}")
            payloads[agent_id] = payload
            preview = previews[month, arm][agent_id]
            call = calls[agent_id]
            expected_hash = preview["prompt_sha256"]
            expected_text = json.dumps(preview["messages"], ensure_ascii=False)
            if (payload.get("cognition_arm") != arm
                    or payload.get("actual_messages_sha256") != expected_hash
                    or call.get("prompt_sha256") != expected_hash
                    or call.get("prompt_text") != expected_text):
                raise ValueError(f"Saved action/call does not match its exact preview: {job['run_id']}")
            raw = call.get("raw_response_text") or ""
            if hashlib.sha256(raw.encode("utf-8")).hexdigest() != call.get("raw_response_sha256"):
                raise ValueError(f"Original reply hash mismatch: {job['run_id']}")
            parsed, reply_error = _audit_raw_reply(raw, call, payload, arm)
            if parsed is not None:
                raw_replies_reconstructed += 1
            bins = _action_bins(payload)
            score = _score_bins(bins) if payload["validation_status"] == "valid" else {
                "mean": None, "iqr": None, "zero_deflation": None,
                "scorer_status": "not_scored_invalid_response", "validation_error": reply_error,
            }
            point = _float_or_none(payload.get("point_pct")) if parsed is not None else None
            result = {
                "validation_status": payload["validation_status"],
                "response_parsed": parsed is not None,
                "parse_error": reply_error,
                "point": point,
                "q9_bins": bins,
                **score,
            }
            actions[month, repeat, agent_id, arm] = result
            coverage[arm][payload["validation_status"]] += 1
            scorable[arm] += int(finite(result["mean"]) and finite(result["iqr"]))
        if set(payloads) != agent_ids_by_month[month]:
            raise ValueError("DuckDB action omits a selected respondent")

    cases = []
    for (month, agent_id), link in sorted(links.items()):
        target = truth[month, agent_id]
        reference_target = reference[month, link["userid"]]
        real = {
            "q9_mean": _float_or_none(target["actual"]),
            "q9_iqr": _float_or_none(target["actual_iqr"]),
            "q9_zero_deflation": _float_or_none(target["actual_zero_deflation"]),
            "q9_bins": reference_target["q9_bins"],
            "official_q9_mean": reference_target["official_q9_mean"],
            "official_q9_iqr": reference_target["official_q9_iqr"],
            "q8_point": _float_or_none(target["actual_point"]),
            "previous_q9_mean": _float_or_none(target["previous"]),
            "previous_q9_bins": target["previous_bins"],
        }
        for repeat in repeats:
            case = {
                "month": month, "repeat": repeat, "agent_id": agent_id,
                "userid": int(link["userid"]), "numeracy": str(link["profile"]["numeracy"]).title(),
                "survey_weight": float(link["survey_weight"]),
                "raw_parent_survey_weight": float(link["raw_parent_survey_weight"]),
                "sampling_weight": float(link["sampling_weight"]), "real": real,
                "arms": {arm: actions[month, repeat, agent_id, arm] for arm in ARMS},
            }
            cases.append(case)
    return {
        "folder": folder, "protocol": protocol, "manifest": manifest,
        "protocol_sha256": protocol_hash, "cases": cases,
        "coverage": {arm: dict(coverage[arm]) for arm in ARMS},
        "scorable_n": dict(scorable), "estimated_run_cost_usd": estimated_cost,
        "raw_replies_reconstructed_and_matched": raw_replies_reconstructed,
        "source_sha256": source_hashes,
        "reference_diagnostics": reference_diagnostics,
        "prepared_file_count": len(prepared_hashes),
        "months": months, "repeats": repeats,
        "scorer": provenance(),
    }


def _q9_cell_metrics(rows: list[dict], arm: str, weights: np.ndarray | None = None) -> dict:
    if not rows:
        return {key: None for key in Q9_METRICS}
    w = np.ones(len(rows), dtype=float) if weights is None else np.asarray(weights, float)
    if w.shape != (len(rows),) or not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0:
        return {key: None for key in Q9_METRICS}
    pred_mean = np.asarray([r["arms"][arm]["mean"] for r in rows], dtype=float)
    pred_iqr = np.asarray([r["arms"][arm]["iqr"] for r in rows], dtype=float)
    real_mean = np.asarray([r["real"]["q9_mean"] for r in rows], dtype=float)
    real_iqr = np.asarray([r["real"]["q9_iqr"] for r in rows], dtype=float)
    pred_zero = np.asarray([r["arms"][arm]["zero_deflation"] for r in rows], dtype=float)
    real_zero = np.asarray([r["real"]["q9_zero_deflation"] for r in rows], dtype=float)
    pred_bins = np.asarray([r["arms"][arm]["q9_bins"] for r in rows], dtype=float)
    real_bins = np.asarray([r["real"]["q9_bins"] for r in rows], dtype=float)
    individual_tv = .5 * np.abs(pred_bins - real_bins).sum(axis=1)
    mean_error = pred_mean - real_mean
    iqr_error = pred_iqr - real_iqr
    pred_cross_iqr = quantile(pred_mean, w, .75) - quantile(pred_mean, w, .25)
    real_cross_iqr = quantile(real_mean, w, .75) - quantile(real_mean, w, .25)
    prev_rows = [i for i, r in enumerate(rows) if finite(r["real"]["previous_q9_mean"])]
    if prev_rows:
        p = np.asarray([rows[i]["real"]["previous_q9_mean"] for i in prev_rows], dtype=float)
        delta_w1 = wasserstein1(pred_mean[prev_rows] - p, w[prev_rows], real_mean[prev_rows] - p, w[prev_rows])
    else:
        delta_w1 = None
    rho = spearmanr(pred_mean, real_mean).statistic if len(rows) > 1 else np.nan
    return {
        "probability_tv_pct": float(np.average(individual_tv, weights=w)),
        "individual_density_iqr_mae_pp": float(np.average(np.abs(iqr_error), weights=w)),
        "individual_density_iqr_bias_pp": float(np.average(iqr_error, weights=w)),
        "individual_density_iqr_mean_pp": float(np.average(pred_iqr, weights=w)),
        "real_individual_density_iqr_mean_pp": float(np.average(real_iqr, weights=w)),
        "individual_density_mean_mae_pp": float(np.average(np.abs(mean_error), weights=w)),
        "individual_density_mean_bias_pp": float(np.average(mean_error, weights=w)),
        "q9_center_mae_pp": abs(quantile(pred_mean, w, .5) - quantile(real_mean, w, .5)),
        "q9_center_bias_pp": quantile(pred_mean, w, .5) - quantile(real_mean, w, .5),
        "cross_section_w1_pp": wasserstein1(pred_mean, w, real_mean, w),
        "delta_w1_pp": delta_w1,
        "cross_person_iqr_pp": pred_cross_iqr,
        "real_cross_person_iqr_pp": real_cross_iqr,
        "cross_person_iqr_gap_pp": pred_cross_iqr - real_cross_iqr,
        "zero_deflation_rate": float(np.average(pred_zero, weights=w)),
        "real_zero_deflation_rate": float(np.average(real_zero, weights=w)),
        "zero_deflation_rate_difference": float(np.average(pred_zero - real_zero, weights=w)),
        "person_mean_spearman": float(rho) if finite(rho) else None,
    }


def _q8_cell_metrics(rows: list[dict], arm: str, weights: np.ndarray | None = None) -> dict:
    if not rows:
        return {key: None for key in Q8_METRICS}
    w = np.ones(len(rows), dtype=float) if weights is None else np.asarray(weights, float)
    if w.shape != (len(rows),) or not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0:
        return {key: None for key in Q8_METRICS}
    pred = np.asarray([r["arms"][arm]["point"] for r in rows], dtype=float)
    real = np.asarray([r["real"]["q8_point"] for r in rows], dtype=float)
    error = pred - real
    rho = spearmanr(pred, real).statistic if len(rows) > 1 else np.nan
    return {
        "q8_person_mae_pp": float(np.average(np.abs(error), weights=w)),
        "q8_person_bias_pp": float(np.average(error, weights=w)),
        "q8_center_mae_pp": abs(quantile(pred, w, .5) - quantile(real, w, .5)),
        "q8_center_bias_pp": quantile(pred, w, .5) - quantile(real, w, .5),
        "q8_cross_section_w1_pp": wasserstein1(pred, w, real, w),
        "q8_person_spearman": float(rho) if finite(rho) else None,
    }


def _common_person_months(cases: list[dict], arms: list[str], repeats: list[int], measure: str) -> set[tuple[int, int]]:
    grouped = defaultdict(list)
    for row in cases:
        grouped[row["month"], row["userid"]].append(row)
    result = set()
    for key, rows in grouped.items():
        by_repeat = {row["repeat"]: row for row in rows}
        if set(by_repeat) != set(repeats):
            continue
        complete = True
        for row in rows:
            if measure == "q9":
                complete &= (finite(row["real"]["q9_mean"]) and finite(row["real"]["q9_iqr"])
                             and finite(row["real"]["q9_zero_deflation"]))
                complete &= (len(row["real"].get("q9_bins", [])) == 10
                             and all(finite(v) for v in row["real"].get("q9_bins", [])))
                complete &= all(finite(row["arms"][a]["mean"]) and finite(row["arms"][a]["iqr"])
                                and finite(row["arms"][a]["zero_deflation"])
                                and len(row["arms"][a].get("q9_bins", [])) == 10
                                and all(finite(v) for v in row["arms"][a].get("q9_bins", []))
                                for a in arms)
            else:
                complete &= finite(row["real"]["q8_point"])
                complete &= all(finite(row["arms"][a]["point"]) for a in arms)
        if complete:
            result.add(key)
    return result


def _cell_rows(cases, month, repeat, support):
    return [r for r in cases if r["month"] == month and r["repeat"] == repeat
            and (r["month"], r["userid"]) in support]


def _aggregate_cells(cells: list[dict], keys: tuple[str, ...]) -> tuple[dict, dict]:
    aggregate, used = {}, {}
    for key in keys:
        values = [float(cell[key]) for cell in cells if finite(cell.get(key))]
        aggregate[key] = float(np.mean(values)) if values else None
        used[key] = len(values)
    return aggregate, used


def _summarize_arm(cases, arm, months, repeats, q9_support, q8_support):
    q9_cells, q8_cells, q9_weighted_cells, q8_weighted_cells = [], [], [], []
    for month in months:
        for repeat in repeats:
            q9_rows = _cell_rows(cases, month, repeat, q9_support)
            q8_rows = _cell_rows(cases, month, repeat, q8_support)
            q9_weights = np.asarray([row["survey_weight"] for row in q9_rows], dtype=float)
            q8_weights = np.asarray([row["survey_weight"] for row in q8_rows], dtype=float)
            q9_cells.append({"month": month, "repeat": repeat, "n_person_months": len(q9_rows),
                             **_q9_cell_metrics(q9_rows, arm)})
            q8_cells.append({"month": month, "repeat": repeat, "n_person_months": len(q8_rows),
                             **_q8_cell_metrics(q8_rows, arm)})
            q9_weighted_cells.append({"month": month, "repeat": repeat, "n_person_months": len(q9_rows),
                                      **_q9_cell_metrics(q9_rows, arm, q9_weights)})
            q8_weighted_cells.append({"month": month, "repeat": repeat, "n_person_months": len(q8_rows),
                                      **_q8_cell_metrics(q8_rows, arm, q8_weights)})
    q9_aggregate, q9_cells_used = _aggregate_cells(q9_cells, Q9_METRICS)
    q8_aggregate, q8_cells_used = _aggregate_cells(q8_cells, Q8_METRICS)
    q9_weighted_aggregate, q9_weighted_cells_used = _aggregate_cells(q9_weighted_cells, Q9_METRICS)
    q8_weighted_aggregate, q8_weighted_cells_used = _aggregate_cells(q8_weighted_cells, Q8_METRICS)
    expected_cells = len(months) * len(repeats)
    return {
        "q9": {"aggregate_equal_month_repeat_cells": q9_aggregate,
               "cells_used_by_metric": q9_cells_used,
               "expected_cells": expected_cells,
               "cells_complete": all(v == expected_cells for v in q9_cells_used.values()),
               "cells": q9_cells},
        "q8": {"aggregate_equal_month_repeat_cells": q8_aggregate,
               "cells_used_by_metric": q8_cells_used,
               "expected_cells": expected_cells,
               "cells_complete": all(v == expected_cells for v in q8_cells_used.values()),
               "cells": q8_cells},
        "auxiliary_survey_weighted": {
            "q9": {"aggregate_equal_month_repeat_cells": q9_weighted_aggregate,
                   "cells_used_by_metric": q9_weighted_cells_used,
                   "expected_cells": expected_cells,
                   "cells_complete": all(v == expected_cells for v in q9_weighted_cells_used.values()),
                   "cells": q9_weighted_cells},
            "q8": {"aggregate_equal_month_repeat_cells": q8_weighted_aggregate,
                   "cells_used_by_metric": q8_weighted_cells_used,
                   "expected_cells": expected_cells,
                   "cells_complete": all(v == expected_cells for v in q8_weighted_cells_used.values()),
                   "cells": q8_weighted_cells},
            "weight_definition": "Parent SCE survey weight × parent-stratum size / selected-stratum size; descriptive sensitivity only.",
        },
    }


def _numeracy_group_descriptions(cases, months, repeats, q9_support):
    groups = {}
    for label in ("High", "Low"):
        subset = [row for row in cases if row["numeracy"] == label]
        support = {(row["month"], row["userid"]) for row in subset
                   if (row["month"], row["userid"]) in q9_support}
        groups[label] = {
            "n_common_person_months": len(support),
            "descriptive_only": True,
            "sampled_person_months_by_month": {
                str(month): sum(row["month"] == month and row["numeracy"] == label
                                for row in cases) // len(repeats)
                for month in months
            },
            "implied_parent_stratum_n_by_month": {
                str(month): next((int(round(len([row for row in cases
                    if row["month"] == month and row["repeat"] == repeats[0]
                    and row["numeracy"] == label]) * row["sampling_weight"]))
                    for row in cases if row["month"] == month and row["repeat"] == repeats[0]
                    and row["numeracy"] == label), None)
                for month in months
            },
            "by_arm": {arm: _summarize_arm(subset, arm, months, repeats, support, set())["q9"]
                       for arm in ARMS},
        }
    return groups


def _monthly_mean_bin_distributions(cases, months, repeats, q9_support):
    """Cell-level mean ten-bin distributions for plotting, without synthetic cases."""
    cells = []
    for month in months:
        for repeat in repeats:
            rows = _cell_rows(cases, month, repeat, q9_support)
            if not rows:
                cells.append({"month": month, "repeat": repeat, "n_person_months": 0,
                              "equal_person": None, "auxiliary_survey_weighted": None})
                continue
            weights = np.asarray([row["survey_weight"] for row in rows], dtype=float)

            def distribution(weight_vector):
                actual_bins = np.average(np.asarray([row["real"]["q9_bins"] for row in rows], float),
                                         axis=0, weights=weight_vector).tolist()
                arm_bins = {}
                for arm in ARMS:
                    predicted = np.average(np.asarray([row["arms"][arm]["q9_bins"] for row in rows], float),
                                           axis=0, weights=weight_vector)
                    arm_bins[arm] = {
                        "mean_bins": predicted.astype(float).tolist(),
                        "mean_distribution_tv_pct": float(.5 * np.abs(predicted - np.asarray(actual_bins)).sum()),
                    }
                return {"actual_mean_bins": actual_bins, "arms": arm_bins}

            cells.append({"month": month, "repeat": repeat, "n_person_months": len(rows),
                          "equal_person": distribution(np.ones(len(rows))),
                          "auxiliary_survey_weighted": distribution(weights)})
    return {
        "unit": "probability percentage points by Q9 bin; each vector is an average across matched people",
        "cells": cells,
        "interpretation": "Cell-level mean-bin curves are descriptive plot inputs. They do not create pooled respondent answers; repeat cells remain separate.",
    }


def _weighted_iqr_mae(rows: list[dict], arm: str, weights: np.ndarray) -> float:
    pred = np.asarray([r["arms"][arm]["iqr"] for r in rows], dtype=float)
    real = np.asarray([r["real"]["q9_iqr"] for r in rows], dtype=float)
    return float(np.average(np.abs(pred - real), weights=weights))


def _paired_cluster_bootstrap(cases, months, repeats, q9_support, comparisons, draws, seed):
    if draws < 1:
        raise ValueError("draws must be positive")
    cell_keys = [(month, repeat) for month in months for repeat in repeats]
    cell_rows = {key: _cell_rows(cases, key[0], key[1], q9_support) for key in cell_keys}
    if any(not rows for rows in cell_rows.values()):
        return {f"{candidate}_minus_{baseline}": {"interval_95_unadjusted_pp": None,
                "draws_requested": draws, "draws_used": 0,
                "reason": "At least one registered month-repeat cell has no common scorable support."}
                for candidate, baseline in comparisons}
    people = sorted({row["userid"] for rows in cell_rows.values() for row in rows})
    person_index = {person: i for i, person in enumerate(people)}
    rng = np.random.default_rng(seed)
    samples = {pair: [] for pair in comparisons}
    attempts = 0
    max_attempts = max(draws * 20, draws)
    while len(next(iter(samples.values()))) < draws and attempts < max_attempts:
        attempts += 1
        multiplicities = np.bincount(rng.integers(0, len(people), size=len(people)), minlength=len(people))
        arm_scores = {pair: 0.0 for pair in comparisons}
        valid_draw = True
        for key in cell_keys:
            rows = cell_rows[key]
            weights = np.asarray([multiplicities[person_index[row["userid"]]] for row in rows], dtype=float)
            if weights.sum() <= 0:
                valid_draw = False
                break
            needed = {arm for pair in comparisons for arm in pair}
            score_by_arm = {arm: _weighted_iqr_mae(rows, arm, weights) for arm in needed}
            for pair in comparisons:
                arm_scores[pair] += (score_by_arm[pair[0]] - score_by_arm[pair[1]]) / len(cell_keys)
        if valid_draw:
            for pair in comparisons:
                samples[pair].append(arm_scores[pair])
    result = {}
    for candidate, baseline in comparisons:
        values = samples[(candidate, baseline)]
        result[f"{candidate}_minus_{baseline}"] = {
            "interval_95_unadjusted_pp": np.quantile(values, [.025, .975]).astype(float).tolist() if values else None,
            "draws_requested": draws,
            "draws_used": len(values),
            "empty_cell_draws": attempts - len(values),
            "seed": seed,
            "scope": "Exploratory paired respondent-cluster bootstrap; same person retains all months and both repeats; month and repeat cells equally weighted; no multiplicity adjustment.",
        }
    return result


def _comparison_changes(metrics_by_arm, candidate, baseline):
    q9a, q9b = metrics_by_arm[candidate]["q9"]["aggregate_equal_month_repeat_cells"], metrics_by_arm[baseline]["q9"]["aggregate_equal_month_repeat_cells"]
    q8a, q8b = metrics_by_arm[candidate]["q8"]["aggregate_equal_month_repeat_cells"], metrics_by_arm[baseline]["q8"]["aggregate_equal_month_repeat_cells"]
    keys = (*Q9_METRICS, *Q8_METRICS)
    changes = {}
    for key in keys:
        left, right = (q9a.get(key), q9b.get(key)) if key in Q9_METRICS else (q8a.get(key), q8b.get(key))
        changes[key] = float(left - right) if finite(left) and finite(right) else None
    return changes


def _comparison_results(metrics_by_arm, intervals):
    results = {}
    for candidate, baseline in REGISTERED_CONTRASTS:
        name = f"{candidate}_minus_{baseline}"
        q9a = metrics_by_arm[candidate]["q9"]["aggregate_equal_month_repeat_cells"]
        q9b = metrics_by_arm[baseline]["q9"]["aggregate_equal_month_repeat_cells"]
        iqr_change = (float(q9a[PRIMARY_METRIC] - q9b[PRIMARY_METRIC])
                      if finite(q9a.get(PRIMARY_METRIC)) and finite(q9b.get(PRIMARY_METRIC)) else None)
        results[name] = {
            "primary_metric": PRIMARY_METRIC,
            "primary_metric_difference_pp": iqr_change,
            **intervals.get(name, {"interval_95_unadjusted_pp": None}),
            "other_metric_point_changes": _comparison_changes(metrics_by_arm, candidate, baseline),
            "confirmatory_claim": False,
        }
    return results


def _pilot_gates(comparisons, coverage_ok):
    gates = {}
    for candidate in ("question_answer", "faithful_paraphrase"):
        name = f"{candidate}_minus_label_only"
        comparison = comparisons[name]
        interval = comparison.get("interval_95_unadjusted_pp")
        changes = comparison["other_metric_point_changes"]
        upper_below_zero = bool(interval is not None and interval[1] < 0)
        center_ok = finite(changes.get("q9_center_mae_pp")) and changes["q9_center_mae_pp"] <= 0
        w1_ok = finite(changes.get("cross_section_w1_pp")) and changes["cross_section_w1_pp"] <= 0
        passed = bool(coverage_ok and upper_below_zero and center_ok and w1_ok)
        gates[name] = {
            "pilot_continuation_gate_passed": passed,
            "coverage_gate_passed": coverage_ok,
            "primary_iqr_mae_upper_interval_below_zero": upper_below_zero,
            "center_error_point_change_nonworse": bool(center_ok),
            "cross_section_w1_point_change_nonworse": bool(w1_ok),
            "interpretation": "A pilot continuation screen only; not a confirmed or overall mechanism-success claim.",
        }
    return gates


def evaluate(folder: Path, out: Path, draws: int = 1000) -> dict:
    """Evaluate a completed cognition trial into a fresh ignored output folder."""
    root = ROOT.resolve()
    folder, out = Path(folder).resolve(), Path(out).resolve()
    outputs_root = (root / "outputs").resolve()
    if out.exists() or not out.is_relative_to(outputs_root):
        raise ValueError("Require a fresh output directory under the ignored outputs folder")
    if draws < 1:
        raise ValueError("draws must be positive")

    loaded = load(folder)
    protocol, cases = loaded["protocol"], loaded["cases"]
    months, repeats = loaded["months"], loaded["repeats"]
    planned_per_arm = len(months) * EXPECTED_N_PER_MONTH * len(repeats)
    coverage = loaded["coverage"]
    fractions = {}
    status_counts = {}
    for arm in ARMS:
        valid_n = coverage[arm].get("valid", 0)
        scorable_n = loaded["scorable_n"].get(arm, 0)
        fractions[arm] = {
            "planned": planned_per_arm,
            "valid_n": valid_n,
            "valid_fraction": valid_n / planned_per_arm,
            "scorable_n": scorable_n,
            "scorable_fraction": scorable_n / planned_per_arm,
            "validation_status_counts": coverage[arm],
        }
        status_counts[arm] = coverage[arm]
    coverage_ok = all(
        fractions[arm]["valid_fraction"] >= VALIDITY_THRESHOLD
        and fractions[arm]["scorable_fraction"] >= VALIDITY_THRESHOLD
        for arm in ARMS
    )

    q9_support = _common_person_months(cases, list(ARMS), repeats, "q9")
    q8_support = _common_person_months(cases, list(ARMS), repeats, "q8")
    expected_person_months = len(months) * EXPECTED_N_PER_MONTH
    metrics_by_arm = {
        arm: _summarize_arm(cases, arm, months, repeats, q9_support, q8_support) for arm in ARMS
    }
    comparisons_for_bootstrap = REGISTERED_CONTRASTS
    if coverage_ok:
        intervals = _paired_cluster_bootstrap(
            cases, months, repeats, q9_support, comparisons_for_bootstrap, draws,
            int(protocol.get("bootstrap_seed", BOOTSTRAP_SEED)),
        )
    else:
        intervals = {
            f"{candidate}_minus_{baseline}": {
                "interval_95_unadjusted_pp": None,
                "draws_requested": draws,
                "draws_used": 0,
                "reason": "At least one arm is below the registered 99% valid/scorable threshold; accuracy remains descriptive.",
            }
            for candidate, baseline in comparisons_for_bootstrap
        }
    comparison_results = _comparison_results(metrics_by_arm, intervals)
    gates = _pilot_gates(comparison_results, coverage_ok)

    grouped = _numeracy_group_descriptions(cases, months, repeats, q9_support)
    monthly_bin_distributions = _monthly_mean_bin_distributions(cases, months, repeats, q9_support)
    expected_generations = expected_person_months * len(repeats)
    q9_generation_rows = sum((month, userid) in q9_support for month, userid in
                             {(r["month"], r["userid"]) for r in cases}) * len(repeats)
    q8_generation_rows = sum((month, userid) in q8_support for month, userid in
                             {(r["month"], r["userid"]) for r in cases}) * len(repeats)
    out.mkdir(parents=True, exist_ok=False)
    code_root = Path(__file__).resolve().parents[3]
    evaluator_path = Path(__file__).resolve()
    cli_path = code_root / "scripts/analyze_sce_cognition_trial.py"
    summary = {
        "status": "completed_sce_cognition_development_pilot_evaluation",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": protocol,
        "protocol_sha256": loaded["protocol_sha256"],
        "primary_metric": PRIMARY_METRIC,
        "primary_contrast": "faithful_paraphrase minus question_answer",
        "metric_units": {
            "probability_tv_pct": "probability percentage points: 0.5 × sum of absolute differences across the ten Q9 bins; not inflation percentage points",
            "q9_density_mean_iqr_w1_center_metrics": "percentage points of inflation",
            "q8_point_metrics": "percentage points of inflation",
            "rates": "fractions from 0 to 1",
        },
        "secondary_contrasts": ["question_answer minus label_only", "faithful_paraphrase minus label_only"],
        "intervals_are_exploratory_only": True,
        "no_confirmatory_or_overall_mechanism_success_claim": True,
        "evaluation_api_calls": 0,
        "evaluated_llm_calls": int(protocol["planned_calls"]),
        "estimated_run_cost_usd_not_provider_bill": loaded["estimated_run_cost_usd"],
        "raw_replies_reconstructed_and_matched": loaded["raw_replies_reconstructed_and_matched"],
        "scorer_provenance": loaded["scorer"],
        "human_truth_scoring": "Current human ten-bin Q9 vectors are independently rescored with the same frozen approximate fitter used for model vectors; probability-TV compares the raw ten-bin vectors directly.",
        "reference_truth_verification": loaded["reference_diagnostics"],
        "coverage": fractions,
        "accuracy_is_descriptive_only_due_to_validity_gate": not coverage_ok,
        "common_support": {
            "registered_person_months": expected_person_months,
            "q9_common_scorable_person_months": len(q9_support),
            "q9_common_generation_rows": q9_generation_rows,
            "q9_assigned_generation_rows": expected_generations,
            "q9_excluded_generation_rows": expected_generations - q9_generation_rows,
            "q8_common_person_months": len(q8_support),
            "q8_common_generation_rows": q8_generation_rows,
            "q8_assigned_generation_rows": expected_generations,
            "q8_excluded_generation_rows": expected_generations - q8_generation_rows,
            "q8_uses_question_specific_common_mask": True,
            "support_definition": "Q9 requires all three arms and both repeats to have finite frozen-scorer density mean/IQR/zero-deflation and finite matched truth; Q8 uses an independent all-arm/all-repeat finite-point mask. No invalid response is repaired or treated as zero.",
        },
        "aggregation": "Each month×repeat cell is scored separately; cell summaries then receive equal weight. Repeats are not combined into synthetic respondent answers. Bootstrap resamples respondent clusters globally and carries all their months/repeats together.",
        "sampling_design": {
            "selected_per_month": {"High": 14, "Low": 10},
            "low_numeracy_oversampled": True,
            "reason": "Fixed in the protocol to ensure mechanism coverage because Low cases are scarce in the frozen 48-person parent rosters; selection did not use current Q8/Q9 outcomes.",
            "primary_analysis": "Unweighted paired person-month analysis with equal month and repeat cells; conditional on this selected roster, not a national estimate.",
            "auxiliary_weighting": "Descriptive sensitivity only: raw parent SCE survey weight multiplied by parent-stratum size / selected-stratum size. This does not create a nationally representative cognition sample.",
        },
        "arms": metrics_by_arm,
        "numeracy_group_descriptions": grouped,
        "monthly_mean_bin_distributions": monthly_bin_distributions,
        "paired_contrasts": comparison_results,
        "pilot_continuation_gates_by_detailed_vs_label": gates,
        "gate_scope": "A passing detailed-vs-label pilot gate is only a continuation signal; it is not a confirmed mechanism success. The primary paraphrase-vs-question-answer contrast is reported separately and has no adoption gate.",
        "source_sha256": loaded["source_sha256"],
        "prepared_file_count_verified": loaded["prepared_file_count"],
        "evaluator_sha256": {
            str(evaluator_path.relative_to(code_root)): sha(evaluator_path),
            str(cli_path.relative_to(code_root)): sha(cli_path) if cli_path.is_file() else None,
        },
        "bootstrap": {
            "draws_requested": draws,
            "seed": int(protocol.get("bootstrap_seed", BOOTSTRAP_SEED)),
            "person_clustered_across_months": True,
            "all_three_contrast_intervals_unadjusted_and_exploratory": True,
        },
        "limitations": [
            "Four previously inspected development months and a 24-person selected subsample per month; no independent validation or national inference.",
            "The observed-person Q9 IQR is itself produced by the frozen approximate density scorer; matching inherits its approximation error.",
            "The published Q9_mean/Q9_iqr cache fields can differ from the pinned frozen-scorer values; they are shown only as sensitivity diagnostics. The matched Q9 bin vectors are the direct truth for probability-TV and the same frozen scorer is applied to model and human bins for mean/IQR metrics.",
            "Q9 common-support accuracy is conditional on all arms and repeats being scorable; coverage is reported on every assigned call to expose selection.",
            "High/Low subgroup summaries are descriptive and have no significance tests.",
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                        encoding="utf-8")
    (out / "cases_private.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                             encoding="utf-8")
    return summary
