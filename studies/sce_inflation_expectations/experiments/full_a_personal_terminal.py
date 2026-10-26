"""Offline-first local Terminal runner for the one-arm, one-pass full-A batch.

This module consumes already frozen per-month prompts. It does not construct
prompts, load target truth, fit a scorer, or inspect credentials during prepare
and review. Every physical request is recorded in an fsynced immutable intent
ledger before dispatch; an intent without a reply is unknown and is never
replayed.
"""
from argparse import ArgumentParser
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from .frozen_batch import ROOT, OFFICIAL, dump, read_json, sha
from .monthly_main_background import atomic_json
from .monthly_main_resilient import POLICY as BASE_POLICY, recoverable
from .state_continuity_execution import live_sender
from . import frozen_message_queue as queue
from ..prior_belief_experiment import message_hash
from ..q9_normalization import response_point, response_view

ENTRY = ROOT / "scripts/run_sce_full_a_personal.py"
EVALUATION_ENTRY = ROOT / "scripts/analyze_sce_full_a_personal.py"
EVALUATION_MODULE = ROOT / "studies/sce_inflation_expectations/evaluation/full_a_personal.py"
EVALUATION_SOURCE_PATHS = (
    ROOT / "studies/sce_inflation_expectations/evaluation/monthly_reconstruction.py",
    ROOT / "studies/sce_inflation_expectations/evaluation/monthly_main_readout.py",
    ROOT / "studies/sce_inflation_expectations/evaluation/cognition.py",
    ROOT / "studies/sce_inflation_expectations/evaluation/state_continuity.py",
    ROOT / "studies/sce_inflation_expectations/evaluation/metrics.py",
    ROOT / "studies/sce_inflation_expectations/evaluation/aggregate_blend.py",
    ROOT / "studies/sce_inflation_expectations/scoring/sce_q9_frozen.py",
    ROOT / "studies/sce_inflation_expectations/scoring/beta_fit_kernel.py",
    ROOT / "studies/sce_inflation_expectations/prior_belief_preparation.py",
    ROOT / "studies/sce_inflation_expectations/experiments/state_continuity_inputs.py",
    ROOT / "studies/sce_inflation_expectations/q9_normalization.py",
)
RUNTIME_SOURCE_PATHS = (
    ROOT / "studies/sce_inflation_expectations/experiments/frozen_batch.py",
    ROOT / "studies/sce_inflation_expectations/experiments/monthly_main_background.py",
    ROOT / "studies/sce_inflation_expectations/prior_belief_experiment.py",
    ROOT / "studies/sce_inflation_expectations/model.py",
    ROOT / "studies/sce_inflation_expectations/model_counterfactual.py",
    ROOT / "studies/sce_inflation_expectations/news_label_trial.py",
)
METADATA = ROOT / "data/raw/mcp_checks/2026-10-21_v32_fullperiod_free_v1/deepseek_v32_endpoints.json"
FIRST_MONTH, LAST_MONTH = 201901, 202510
MONTHS = tuple(201901 + ((i // 12) * 100) + (i % 12) for i in range(82))
EXPECTED_PERSON_MONTHS = 41970
EXPECTED_EXCLUSIONS = 14
RAW_PER_MONTH = 512
ARM = "T0"
REPEAT = 1
MAX_OUTPUT_TOKENS = 1024
PRICE_INPUT_PER_MTOK = 0.259
PRICE_OUTPUT_PER_MTOK = 0.8
READY_STATUS = "ready"
INPUT_FILES = ("prompts.json", "contexts_private.json", "weights_private.json", "roster_private.json")
HISTORICAL_PACKAGE = ROOT / "outputs/sce_media_timing_package_20261025_v3"
HISTORICAL_RUN = ROOT / "outputs/sce_media_timing_terminal_20261025_v4"
HISTORICAL_MONTHS = (201905, 202009, 202106, 202109, 202112, 202206, 202312)


def _safe_output_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT / "outputs").resolve()):
        raise ValueError("Full-A input/run artifacts must be under outputs/")
    return path


def _positive_finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return float(value)


def _json_size(value):
    # Match the normal JSON serialization used by the already frozen callers;
    # retaining whitespace makes the fee reservation conservative.
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


def reserve(p, byte_count):
    """Conservative request fee reserve using frozen provider prices and max output."""
    return ((byte_count + 1024) * p["price_input_per_mtok"]
            + p["max_tokens"] * p["price_output_per_mtok"]) / 1e6


def _manifest_files(manifest):
    rows = manifest.get("files_sha256")
    if not isinstance(rows, dict) or not rows:
        raise ValueError("Input manifest files_sha256 is required")
    clean = {}
    for name, digest in rows.items():
        if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts
                or not isinstance(digest, str) or len(digest) != 64
                or any(ch not in "0123456789abcdef" for ch in digest)):
            raise ValueError("Malformed input manifest hash map")
        parts = {part.lower() for part in Path(name).parts}
        if (parts & {"truth", "evaluation", "target_answers", "current_answers"}
                or any(part.startswith(("truth_", "answer_private")) for part in parts)):
            raise ValueError("Execution input manifest must not include target-truth files")
        clean[name] = digest
    return clean


def _verify_input_manifest(input_dir):
    input_dir = _safe_output_path(input_dir)
    manifest_path = input_dir / "manifest.json"
    manifest = read_json(manifest_path)
    hashes = _manifest_files(manifest)
    # Hash only the inputs this executor is authorized to consume. The source
    # manifest may also pin prompt-building catalogs (for example public label
    # overlays); those are not opened during prepare or execution.
    selected = {name: digest for name, digest in hashes.items()
                if name in ("summary.json", "exclusions.json")
                or (len(Path(name).parts) == 2 and Path(name).parts[0].isdigit()
                    and Path(name).parts[1] in INPUT_FILES)}
    for name, digest in selected.items():
        path = (input_dir / name).resolve()
        if not path.is_relative_to(input_dir) or not path.is_file() or sha(path) != digest:
            raise ValueError("Full-A prepared input hash mismatch: " + name)
    return input_dir, manifest, sha(manifest_path), selected


def _as_id_map(value, label, *, eligible_only=False):
    """Read an ID-indexed private sidecar without assuming its outer wrapper."""
    if isinstance(value, dict):
        for key in ("rows", "persons", "people", "roster"):
            if isinstance(value.get(key), (dict, list)):
                value = value[key]
                break
    if isinstance(value, dict):
        result = value
    elif isinstance(value, list):
        result = {}
        for row in value:
            if not isinstance(row, dict):
                raise ValueError(f"{label} must contain object rows")
            aid = row.get("aid", row.get("agent_id"))
            if aid is None or str(aid) in result:
                raise ValueError(f"{label} has a missing or duplicate aid")
            if eligible_only and row.get("eligible") is not True:
                continue
            result[str(aid)] = row
    else:
        raise ValueError(f"{label} must be an ID-indexed object or row list")
    if eligible_only and isinstance(result, dict):
        result = {k: v for k, v in result.items()
                  if isinstance(v, dict) and v.get("eligible") is True}
    normalized = {str(k): v for k, v in result.items()}
    if len(normalized) != len(result) or not normalized:
        raise ValueError(f"{label} has duplicate/empty IDs")
    return normalized


def _month_counts(summary):
    value = summary.get("rows_by_month", summary.get("n_by_month"))
    if isinstance(value, list):
        return {str(row["month"]): int(row.get("rows", row.get("n"))) for row in value}
    if not isinstance(value, dict):
        raise ValueError("Input summary rows_by_month is required")
    return {str(k): int(v) for k, v in value.items()}


def _load_prompts(input_dir, month, expected_rows=None):
    blob = read_json(Path(input_dir) / str(month) / "prompts.json")
    if blob.get("month") not in (month, str(month)):
        raise ValueError(f"Prompt month mismatch for {month}")
    rows = blob.get("rows")
    if not isinstance(rows, dict) or not rows:
        raise ValueError(f"Prompt rows missing for {month}")
    normalized = {str(aid): row for aid, row in rows.items()}
    if len(normalized) != len(rows) or expected_rows is not None and len(normalized) != expected_rows:
        raise ValueError(f"Prompt count mismatch for {month}")
    return normalized


def _validate_input(input_dir):
    input_dir, manifest, manifest_sha, hashes = _verify_input_manifest(input_dir)
    summary_path = input_dir / "summary.json"
    exclusions_path = input_dir / "exclusions.json"
    for required in ("summary.json", "exclusions.json"):
        if required not in hashes:
            raise ValueError("Input manifest must pin " + required)
    summary = read_json(summary_path)
    if summary.get("status") != READY_STATUS:
        raise ValueError("Full-A inputs are not marked ready; no Terminal package created")
    months = summary.get("months")
    if not isinstance(months, list) or tuple(int(m) for m in months) != MONTHS:
        raise ValueError("Input months must be the complete 201901–202510 monthly window")
    counts = _month_counts(summary)
    if set(counts) != {str(m) for m in MONTHS}:
        raise ValueError("Input monthly roster summary differs from the frozen window")
    if any(counts[str(m)] < 1 for m in MONTHS) or sum(counts.values()) != EXPECTED_PERSON_MONTHS:
        raise ValueError("Input roster must contain exactly 41,970 retained person-months")
    eligible = summary.get("eligible_total", summary.get("person_months", summary.get("prompt_rows")))
    if eligible != EXPECTED_PERSON_MONTHS:
        raise ValueError("Input summary must report 41,970 eligible prompts")
    exclusions = read_json(exclusions_path)
    exclusion_rows = exclusions.get("rows", exclusions.get("exclusions", exclusions))
    if isinstance(exclusion_rows, list) and len(exclusion_rows) != EXPECTED_EXCLUSIONS:
        raise ValueError("Exactly 14 cross-month exclusions are required")
    if isinstance(exclusion_rows, dict) and len(exclusion_rows) != EXPECTED_EXCLUSIONS:
        raise ValueError("Exactly 14 cross-month exclusions are required")

    slots, max_prompt_bytes, max_prompt_chars, excluded_roster_n = [], 0, 0, 0
    max_prompt_content_bytes, max_serialized_chars, estimated_input_tokens = 0, 0, 0
    for month in MONTHS:
        relative_files = {name: f"{month}/{name}" for name in INPUT_FILES}
        if any(relative_files[name] not in hashes for name in INPUT_FILES):
            raise ValueError(f"Input manifest omits a required {month} sidecar")
        prompts = _load_prompts(input_dir, month, counts[str(month)])
        roster_raw = _as_id_map(read_json(input_dir / str(month) / "roster_private.json"), "roster")
        roster_eligible = _as_id_map(read_json(input_dir / str(month) / "roster_private.json"),
                                     "eligible roster", eligible_only=True)
        if len(roster_raw) != RAW_PER_MONTH or len(roster_eligible) != len(prompts):
            raise ValueError(f"Raw/eligible roster counts differ from the 512-person monthly draw for {month}")
        excluded_roster_n += len(roster_raw) - len(roster_eligible)
        for aid, row in roster_raw.items():
            if isinstance(row, dict) and row.get("agent_id") is not None and str(row["agent_id"]) != aid:
                raise ValueError(f"Roster key/agent_id mismatch for {month}/{aid}")
        sidecars = {
            "contexts_private.json": _as_id_map(read_json(input_dir / str(month) / "contexts_private.json"), "contexts"),
            "weights_private.json": _as_id_map(read_json(input_dir / str(month) / "weights_private.json"), "weights"),
            "roster_private.json": roster_eligible,
        }
        prompt_ids = set(prompts)
        if any(set(value) != prompt_ids for value in sidecars.values()):
            raise ValueError(f"Prompt/context/weight/roster ID sets differ for {month}")
        for aid, row in prompts.items():
            if not isinstance(row, dict) or not isinstance(row.get("messages"), list):
                raise ValueError(f"Malformed frozen message for {month}/{aid}")
            messages = row["messages"]
            digest = row.get("prompt_sha256")
            if not isinstance(digest, str) or message_hash(messages) != digest:
                raise ValueError(f"Frozen prompt hash mismatch for {month}/{aid}")
            if (len(messages) != 1 or messages[0].get("role") != "user"
                    or not isinstance(messages[0].get("content"), str)):
                raise ValueError(f"Expected one frozen user message for {month}/{aid}")
            byte_count = _json_size(messages)
            serialized_chars = len(json.dumps(messages, ensure_ascii=False))
            chars = len(messages[0]["content"])
            max_prompt_bytes = max(max_prompt_bytes, byte_count)
            max_prompt_chars = max(max_prompt_chars, chars)
            max_prompt_content_bytes = max(max_prompt_content_bytes, len(messages[0]["content"].encode("utf-8")))
            max_serialized_chars = max(max_serialized_chars, serialized_chars)
            estimated_input_tokens += math.ceil(serialized_chars / 4)
            key = f"{month}|{ARM}|{REPEAT}|{aid}"
            slots.append({"key": key, "month": month, "arm": ARM, "repeat": REPEAT,
                          "agent_id": aid, "prompt_sha256": digest,
                          "reserved_usd": reserve({"price_input_per_mtok": PRICE_INPUT_PER_MTOK,
                                                   "price_output_per_mtok": PRICE_OUTPUT_PER_MTOK,
                                                   "max_tokens": MAX_OUTPUT_TOKENS}, byte_count),
                          "prompt_bytes": byte_count, "prompt_chars": chars})
    if len(slots) != EXPECTED_PERSON_MONTHS or len({s["key"] for s in slots}) != len(slots):
        raise ValueError("Frozen full-A slot index is incomplete or duplicated")
    if excluded_roster_n != EXPECTED_EXCLUSIONS:
        raise ValueError("Monthly roster flags must identify exactly 14 excluded cross-month IDs")
    if "estimated_input_tokens_char_div_4" in summary:
        if summary["estimated_input_tokens_char_div_4"] != estimated_input_tokens:
            raise ValueError("Prompt-token estimate differs from ceil(serialized message characters / 4)")
    output_assumption = summary.get("estimated_output_tokens_assumed_per_prompt")
    if output_assumption is not None:
        if isinstance(output_assumption, bool) or not isinstance(output_assumption, (int, float)) or output_assumption < 0:
            raise ValueError("Invalid assumed output-token estimate")
    expected_input_cost = estimated_input_tokens * PRICE_INPUT_PER_MTOK / 1e6
    expected_output_cost = (output_assumption or 0) * len(slots) * PRICE_OUTPUT_PER_MTOK / 1e6
    for key, expected in (("estimated_input_cost_usd", expected_input_cost),
                          ("estimated_output_cost_usd", expected_output_cost),
                          ("estimated_total_cost_usd", expected_input_cost + expected_output_cost)):
        actual = summary.get(key)
        if actual is not None and (isinstance(actual, bool) or not isinstance(actual, (int, float))
                or not math.isfinite(actual) or abs(actual - expected) > max(1e-8, expected * 1e-6)):
            raise ValueError("Cost estimate does not reconcile with frozen prompt counts/prices: " + key)
    prompt_chars_summary = summary.get("prompt_characters_max")
    if prompt_chars_summary is not None and prompt_chars_summary not in (max_prompt_chars, max_serialized_chars):
        raise ValueError("Summary prompt_characters_max differs from frozen messages")
    prompt_bytes_summary = summary.get("prompt_utf8_bytes_max")
    if prompt_bytes_summary is not None and prompt_bytes_summary not in (max_prompt_bytes, max_prompt_content_bytes):
        raise ValueError("Summary prompt_utf8_bytes_max differs from frozen messages")
    estimate_metrics = {"serialized_prompt_characters_max": max_serialized_chars,
                        "prompt_content_characters_max": max_prompt_chars,
                        "serialized_prompt_utf8_bytes_max": max_prompt_bytes,
                        "prompt_content_utf8_bytes_max": max_prompt_content_bytes,
                        "estimated_input_tokens_char_div_4_recomputed": estimated_input_tokens,
                        "estimated_input_cost_usd_recomputed": expected_input_cost,
                        "estimated_output_cost_usd_recomputed": expected_output_cost}
    return (input_dir, manifest, manifest_sha, hashes, summary, slots,
            max_prompt_bytes, max_prompt_chars, estimate_metrics)


def _safe_source_file(relative):
    if not isinstance(relative, str) or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Unsafe historical import source path")
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT.resolve()) or not path.is_file():
        raise ValueError("Historical import source is unavailable")
    return path


def _valid_historical_protocol(protocol):
    return (protocol.get("model") == "deepseek/deepseek-v3.2"
            and protocol.get("route") == "siliconflow/fp8"
            and protocol.get("expected_provider") == "SiliconFlow"
            and protocol.get("temperature") == 0.5
            and protocol.get("thinking") == "disabled"
            and protocol.get("response_format") == "json_object"
            and protocol.get("max_tokens") == MAX_OUTPUT_TOKENS
            and protocol.get("retry_max") == 0
            and protocol.get("provider_fallback") is False
            and protocol.get("price_input_per_mtok") == PRICE_INPUT_PER_MTOK
            and protocol.get("price_output_per_mtok") == PRICE_OUTPUT_PER_MTOK
            and protocol.get("request_extra_body") == {"provider": {"order": ["siliconflow/fp8"],
                "allow_fallbacks": False, "require_parameters": True,
                "max_price": {"prompt": PRICE_INPUT_PER_MTOK, "completion": PRICE_OUTPUT_PER_MTOK}},
                "reasoning": {"enabled": False}})


def _build_historical_import_plan(input_dir, slots):
    """Pin exact T0/r1 historical replies with complete valid Q8 and Q9 fields.

    This reads only frozen prompt rows and raw generation ledgers. It never
    opens scoring targets, evaluates responses, or chooses among valid replies.
    """
    package_rel = str(HISTORICAL_PACKAGE.resolve().relative_to(ROOT.resolve()))
    run_rel = str(HISTORICAL_RUN.resolve().relative_to(ROOT.resolve()))
    package_manifest_path = HISTORICAL_PACKAGE / "manifest.json"
    package_protocol_path = HISTORICAL_PACKAGE / "protocol.json"
    run_config_path = HISTORICAL_RUN / "config.json"
    run_receipt_path = HISTORICAL_RUN / "generation_receipt.json"
    package_manifest = read_json(package_manifest_path)
    package_protocol = read_json(package_protocol_path)
    run_config = read_json(run_config_path)
    run_receipt = read_json(run_receipt_path)
    if (not _valid_historical_protocol(package_protocol)
            or package_protocol.get("mechanism") != "v32_media_timing"
            or package_protocol.get("generation_repeats") != [1, 2]
            or package_protocol.get("destination") != "https://openrouter.ai/api/v1"
            or run_config.get("protocol_sha256") != sha(package_protocol_path)
            or run_config.get("manifest_sha256") != sha(package_manifest_path)
            or run_config.get("model") != package_protocol.get("model")
            or run_config.get("route") != package_protocol.get("route")
            or package_manifest.get("protocol_sha256") != sha(package_protocol_path)
            or run_receipt.get("protocol_sha256") != sha(package_protocol_path)
            or run_receipt.get("main_complete") is not True
            or run_receipt.get("main", {}).get("status") != "completed"
            or run_receipt.get("main", {}).get("actual_model_results") is not True
            or run_receipt.get("main", {}).get("attempts") != package_protocol.get("planned_calls")
            or run_receipt.get("main", {}).get("completed") != package_protocol.get("planned_calls")
            or run_receipt.get("repair_complete") is not True
            or run_receipt.get("repair", {}).get("actual_model_results") is not True
            or run_receipt.get("truth_opened") is not False):
        raise ValueError("Historical timing generation is not a complete matching actual-model source")

    source_hashes = {}
    for path in (package_manifest_path, package_protocol_path, run_config_path, run_receipt_path):
        source_hashes[str(path.resolve().relative_to(ROOT.resolve()))] = sha(path)
    prompt_rows = {}
    for month in HISTORICAL_MONTHS:
        rel = f"{month}/prompts_T0.json"
        path = HISTORICAL_PACKAGE / rel
        expected = package_manifest.get("prepared_file_sha256", {}).get(rel)
        if not expected or sha(path) != expected:
            raise ValueError("Historical T0 prompt is not covered by its package manifest")
        source_hashes[str(path.resolve().relative_to(ROOT.resolve()))] = expected
        blob = read_json(path)
        if blob.get("month") not in (month, str(month)) or not isinstance(blob.get("rows"), dict):
            raise ValueError("Malformed historical T0 prompt sidecar")
        for aid, row in blob["rows"].items():
            if (not isinstance(row, dict) or not isinstance(row.get("prompt_sha256"), str)
                    or not isinstance(row.get("messages"), list)
                    or message_hash(row["messages"]) != row["prompt_sha256"]):
                raise ValueError("Malformed historical T0 prompt hash")
            prompt_rows[(month, str(aid))] = row["prompt_sha256"]

    # Check all source segment manifests and their ledgers once here. The run
    # manifest pins them in the new package; resume checks hashes at its boundary.
    reply_rows = {}
    raw_main_n, raw_repair_n = 0, 0
    dispatch_main_n, dispatch_repair_n = 0, 0
    segments = [("main", path) for path in sorted(HISTORICAL_RUN.glob("round_*/segment_*"))]
    segments += [("repair", path) for path in sorted((HISTORICAL_RUN / "repair").glob("round_*/segment_*"))]
    for stage, segment in segments:
        manifest_path = segment / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = read_json(manifest_path)
        files = manifest.get("files_sha256", {})
        required = ("dispatch_private.jsonl", "calls_private.jsonl", "receipt.json")
        if any(name not in files for name in required):
            raise ValueError("Historical source segment does not pin its raw ledgers")
        for name in (*required, "manifest.json"):
            path = segment / name
            digest = files[name] if name in files else sha(path)
            if not path.is_file() or sha(path) != digest:
                raise ValueError("Historical source segment hash mismatch")
            relative = str(path.resolve().relative_to(ROOT.resolve()))
            source_hashes[relative] = digest
        dispatch_path = segment / "dispatch_private.jsonl"
        calls_path = segment / "calls_private.jsonl"
        dispatch = {}
        for row in queue.lines(dispatch_path):
            key = row.get("key")
            if not isinstance(key, str) or key in dispatch:
                raise ValueError("Duplicate historical dispatch key")
            dispatch[key] = row
        if stage == "main":
            dispatch_main_n += len(dispatch)
        else:
            dispatch_repair_n += len(dispatch)
        raw = calls_path.read_bytes().splitlines(keepends=True)
        if raw and not all(line.endswith(b"\n") for line in raw):
            raise ValueError("Historical source reply ledger has an incomplete line")
        for line in raw:
            row = json.loads(line)
            if stage == "main":
                raw_main_n += 1
            else:
                raw_repair_n += 1
            source_key = row.get("key")
            if source_key not in dispatch or source_key in reply_rows:
                raise ValueError("Historical reply is not uniquely paired with an intent")
            if row.get("prompt_sha256") != dispatch[source_key].get("prompt_sha256"):
                raise ValueError("Historical reply/dispatch prompt hash mismatch")
            normalized_key = source_key.removeprefix("repair1|") if stage == "repair" else source_key
            reply_rows[normalized_key] = {
                "stage": stage, "source_key": source_key, "row": row,
                "path": str(calls_path.resolve().relative_to(ROOT.resolve())),
                "file_sha256": files["calls_private.jsonl"],
                "record_sha256": hashlib.sha256(line).hexdigest(),
            }
    if (raw_main_n != run_receipt["main"].get("completed")
            or raw_repair_n != run_receipt["repair"].get("completed")
            or dispatch_main_n != run_receipt["main"].get("attempts")
            or dispatch_repair_n != run_receipt["repair"].get("attempts")):
        raise ValueError("Historical source raw reply counts differ from the pinned completion receipt")

    candidates = []
    imports = []
    ineligible_reasons = {}
    for slot in slots:
        month, aid = slot["month"], slot["agent_id"]
        if month not in HISTORICAL_MONTHS or prompt_rows.get((month, aid)) != slot["prompt_sha256"]:
            continue
        candidates.append(slot["key"])
        source = reply_rows.get(slot["key"])
        if source is None:
            ineligible_reasons["no_direct_v4_raw_reply"] = ineligible_reasons.get("no_direct_v4_raw_reply", 0) + 1
            continue
        row = source["row"]
        if (row.get("error") is not None or row.get("actual_model_results") is not True
                or row.get("returned_model") != package_protocol["model"]
                or row.get("returned_provider") != package_protocol["expected_provider"]
                or row.get("finish_reason") != "stop"
                or row.get("prompt_sha256") != slot["prompt_sha256"]
                or hashlib.sha256(row.get("raw_response_text", "").encode("utf-8")).hexdigest()
                   != row.get("raw_response_sha256")
                or not all(queue.fields(row).values())):
            ineligible_reasons["source_reply_failed_success_contract"] = (
                ineligible_reasons.get("source_reply_failed_success_contract", 0) + 1)
            continue
        imports.append({"key": slot["key"], "prompt_sha256": slot["prompt_sha256"],
            "source_stage": source["stage"], "source_key": source["source_key"],
            "source_reply_path": source["path"], "source_file_sha256": source["file_sha256"],
            "source_record_sha256": source["record_sha256"],
            "source_raw_response_sha256": row["raw_response_sha256"],
            "source_api_reported_cost_usd": row.get("api_reported_cost_usd")})
    # The first 64 live gate/probe slots must stay physical new requests.
    protected = {slot["key"] for slot in slots[:64]}
    if any(row["key"] in protected for row in imports):
        raise ValueError("Historical imports overlap the protected technical-gate slots")
    plan = {"schema": "sce_full_a_personal_historical_import_plan/v1",
        "source_package": package_rel, "source_run": run_rel,
        "source_protocol_sha256": sha(package_protocol_path),
        "source_generation_receipt_sha256": sha(run_receipt_path),
        "candidate_count": len(candidates), "eligible_import_count": len(imports),
        "ineligible_candidate_count": len(candidates) - len(imports),
        "ineligible_reason_counts": ineligible_reasons,
        "rows": imports, "new_api_calls_after_gate": len(slots) - len(imports),
        "first_64_imports": 0, "truth_opened": False}
    if len(candidates) != 189 or len(imports) != 182:
        raise ValueError("Historical import source no longer matches the audited 189/182 scope")
    return plan, source_hashes


def _protocol(months, counts, planned_calls, cap, max_prompt_bytes, max_prompt_chars, inputs_rel,
              import_plan):
    import_count = import_plan["eligible_import_count"]
    planned_api_calls = planned_calls - import_count
    p = {
        "schema": "sce_full_a_personal_terminal_protocol/v1",
        "mechanism": "full_a_personal_single_arm_single_pass",
        "input_package": inputs_rel, "input_package_path": str(ROOT / inputs_rel),
        "months": list(months), "n_by_month": {str(k): v for k, v in counts.items()},
        "eligible_person_months": planned_calls, "planned_calls": planned_calls,
        "arm": ARM, "generation_repeats": [REPEAT],
        "destination": "https://openrouter.ai/api/v1", "model": "deepseek/deepseek-v3.2",
        "route": "siliconflow/fp8", "expected_provider": "SiliconFlow", "temperature": 0.5,
        "thinking": "disabled", "response_format": "json_object", "max_tokens": MAX_OUTPUT_TOKENS,
        "timeout_s": 120, "retry_max": 0, "provider_fallback": False,
        "provider_metadata": str(METADATA.relative_to(ROOT)),
        "request_extra_body": {"provider": {"order": ["siliconflow/fp8"],
            "allow_fallbacks": False, "require_parameters": True,
            "max_price": {"prompt": PRICE_INPUT_PER_MTOK, "completion": PRICE_OUTPUT_PER_MTOK}},
            "reasoning": {"enabled": False}},
        "price_input_per_mtok": PRICE_INPUT_PER_MTOK,
        "price_output_per_mtok": PRICE_OUTPUT_PER_MTOK, "budget_cap_usd": cap,
        "max_prompt_bytes": max_prompt_bytes, "max_prompt_chars": max_prompt_chars,
        "technical_gate": {"initial_attempts": 32, "minimum_normal_returns": 16,
            "minimum_format_ratio": 0.95, "maximum_probe_attempts": 32,
            "format_validity": "both Q8 and Q9 parse with frozen response reader"},
        "concurrency": {"gate_workers": 8, "main_initial_workers": 32,
            "main_max_workers": 64, "main_scale_after_completed": 32,
            "repair_initial_workers": 16, "repair_max_workers": 32,
            "repair_scale_after_completed": 32, "batch_slots": min(planned_calls, 8192)},
        "repair": {"technical_failures_only": True, "max_attempts_per_main_slot": 1,
            "max_requests": planned_api_calls, "preserve_raw_main_response": True,
            "successful_main_fields_are_not_overwritten": True,
            "unknown_unresolved_intents_are_not_replayed": True},
        "historical_imports": {"plan_schema": import_plan["schema"],
            "planned_import_rows": import_count,
            "source_protocol_sha256": import_plan["source_protocol_sha256"],
            "selection": "exact T0/repeat1 prompt hash; same locked model/provider/temperature; raw actual success; both Q8 and Q9 valid; no outcome-based selection",
            "import_only_after_technical_gate": True,
            "protected_initial_gate_and_probe_slots": 64,
            "historical_source_charge_is_not_new_spend": True},
        "planned_new_api_calls": planned_api_calls,
        "historical_import_plan_sha256": None,
        "budget_mode": "shared_main_repair_spent_plus_inflight_reservation",
        "max_physical_attempts": 2 * planned_api_calls,
        "ledger_semantics": "fsynced_intent_before_dispatch; immutable raw append-only segment ledgers",
        "truth_opened_during_prepare": False, "evaluation_during_generation": False,
        "new_api_calls_during_prepare": 0,
    }
    return p


def _policy():
    p = deepcopy(BASE_POLICY)
    p.update(initial_workers=32, max_workers=64, min_workers=8, scale_up_after_completed=32,
             healthy_segment_min_successes=8, healthy_segment_min_ratio=0.95,
             max_unhealthy_recoveries=5, max_total_cooldown_seconds=1800,
             max_total_recoveries=None,
             recovery_accounting="No lifetime cycle-count stop; independent consecutive-unhealthy, no-progress, and total-cooldown bounds.")
    p["no_progress_recovery_limit"] = 3
    p["gate_workers"] = 8
    p["repair_initial_workers"] = 16
    p["repair_max_workers"] = 32
    p["repair_scale_after_completed"] = 32
    # A small number of immutable segments avoids reparsing all earlier raw
    # responses after each 1k calls without materializing the full corpus at once.
    p["batch_slots"] = min(EXPECTED_PERSON_MONTHS, 8192)
    return p


def prepare(input_dir, out, budget_cap_usd):
    """Freeze local execution plan; reads no keys, secrets, or target truth."""
    cap = _positive_finite(budget_cap_usd, "budget_cap_usd")
    (input_dir, input_manifest, input_manifest_sha, input_hashes, summary,
     slots, max_prompt_bytes, max_prompt_chars, estimate_metrics) = _validate_input(input_dir)
    import_plan, import_source_hashes = _build_historical_import_plan(input_dir, slots)
    import_keys = {row["key"] for row in import_plan["rows"]}
    planned_api_calls = len(slots) - len(import_keys)
    out = _safe_output_path(out)
    if out.exists() or out == input_dir or input_dir.is_relative_to(out):
        raise ValueError("Fresh run directory separate from its input package is required")
    counts = _month_counts(summary)
    p = _protocol(MONTHS, counts, len(slots), cap, max_prompt_bytes, max_prompt_chars,
                  str(input_dir.relative_to(ROOT)), import_plan)
    policy = _policy()
    total_reservation = sum(slot["reserved_usd"] for slot in slots if slot["key"] not in import_keys)
    estimated_cost = summary.get("estimated_total_cost_usd",
        summary.get("estimated_cost_usd", summary.get("estimated_api_cost_usd")))
    if estimated_cost is not None:
        estimated_cost = _positive_finite(estimated_cost, "input estimated_cost_usd")
    estimate_detail = {key: summary.get(key) for key in (
        "estimated_input_tokens_char_div_4", "estimated_output_tokens_assumed_per_prompt",
        "estimated_input_cost_usd", "estimated_output_cost_usd", "estimated_total_cost_usd",
        "price_input_per_million_tokens_usd", "price_output_per_million_tokens_usd",
        "prompt_characters_max", "prompt_utf8_bytes_max") if key in summary}
    for key in ("estimated_input_cost_usd", "estimated_output_cost_usd", "estimated_total_cost_usd"):
        if key in estimate_detail:
            value = estimate_detail[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Input cost estimate must be finite and nonnegative: " + key)
    if (estimate_detail.get("price_input_per_million_tokens_usd", PRICE_INPUT_PER_MTOK) != PRICE_INPUT_PER_MTOK
            or estimate_detail.get("price_output_per_million_tokens_usd", PRICE_OUTPUT_PER_MTOK) != PRICE_OUTPUT_PER_MTOK):
        raise ValueError("Input cost estimate uses different frozen provider prices")
    if (estimate_detail.get("prompt_characters_max") is not None
            and estimate_detail["prompt_characters_max"] not in
            (max_prompt_chars, estimate_metrics["serialized_prompt_characters_max"])):
        raise ValueError("Summary prompt_characters_max differs from frozen prompts")
    if (estimate_detail.get("prompt_utf8_bytes_max") is not None
            and estimate_detail["prompt_utf8_bytes_max"] not in
            (max_prompt_bytes, estimate_metrics["prompt_content_utf8_bytes_max"])):
        raise ValueError("Summary prompt_utf8_bytes_max differs from frozen prompts")
    estimate_detail.update(estimate_metrics)
    out.mkdir(parents=True, mode=0o700)
    dump(out / "historical_import_plan_private.json", import_plan)
    p["historical_import_plan_sha256"] = sha(out / "historical_import_plan_private.json")
    dump(out / "protocol.json", p)
    dump(out / "execution_policy.json", policy)
    dump(out / "slot_index_private.json", slots)
    dump(out / "config.json", {
        "schema": "sce_full_a_personal_terminal_config/v1", "run_dir": str(out),
        "python": sys.executable,
        "input_package": str(input_dir), "input_manifest_sha256": input_manifest_sha,
        "protocol_sha256": sha(out / "protocol.json"), "prepared_at_utc": queue.now(),
        "planned_calls": len(slots), "budget_cap_usd": cap,
        "planned_new_api_calls": planned_api_calls,
        "planned_historical_import_rows": len(import_keys),
        "historical_import_plan_sha256": p["historical_import_plan_sha256"],
        "historical_source_reported_cost_usd": sum(
            row["source_api_reported_cost_usd"] or 0.0 for row in import_plan["rows"]),
        "estimated_api_cost_usd": estimated_cost,
        "input_estimate_scope": "Full 41,970-prompt estimate before zero-new-fee historical imports.",
        "input_cost_estimate": estimate_detail,
        "cost_estimate_basis": "Input estimate uses ceil(serialized_prompt_characters/4), not tokenizer metering; executor reservation uses UTF-8 bytes and the full 1,024-token output bound.",
        "full_scope_conservative_reservation_usd": total_reservation,
        "maximum_repair_attempts": planned_api_calls,
        "maximum_physical_attempts": 2 * planned_api_calls,
        "destination": p["destination"], "model": p["model"], "route": p["route"],
        "prompt_scope_sha256": sha(out / "slot_index_private.json"),
        "truth_opened_during_prepare": False, "api_keys_read_during_prepare": False,
        "new_api_calls": 0,
    })
    source_hashes = {str((input_dir / relative).resolve().relative_to(ROOT)): digest
                     for relative, digest in input_hashes.items()}
    source_hashes[str((input_dir / "manifest.json").resolve().relative_to(ROOT))] = input_manifest_sha
    source_hashes.update(import_source_hashes)
    source_hashes[str(METADATA.relative_to(ROOT))] = sha(METADATA)
    for file in (Path(__file__), ENTRY, Path(queue.__file__),
                 Path(__import__("studies.sce_inflation_expectations.experiments.monthly_main_resilient",
                                 fromlist=["__file__"]).__file__),
                 Path(__import__("studies.sce_inflation_expectations.experiments.state_continuity_execution",
                                 fromlist=["__file__"]).__file__),
                 EVALUATION_ENTRY, EVALUATION_MODULE, *EVALUATION_SOURCE_PATHS,
                 *RUNTIME_SOURCE_PATHS):
        source_hashes[str(file.resolve().relative_to(ROOT))] = sha(file)
    prepared_hashes = {name: sha(out / name) for name in
                       ("protocol.json", "execution_policy.json", "slot_index_private.json",
                        "historical_import_plan_private.json", "config.json")}
    dump(out / "manifest.json", {"schema": "sce_full_a_personal_terminal_manifest/v1",
        "protocol_sha256": sha(out / "protocol.json"), "source_sha256": source_hashes,
        "prepared_file_sha256": prepared_hashes,
        "input_manifest_sha256": input_manifest_sha,
        "truth_in_execution_inputs": False, "new_api_calls": 0})
    return {"status": "prepared_not_started", "run_dir": str(out),
        "months": len(MONTHS), "planned_calls": len(slots), "arm": ARM,
        "repeat": REPEAT, "budget_cap_usd": cap,
        "input_estimated_api_cost_usd": estimated_cost,
        "input_cost_estimate": estimate_detail,
        "cost_estimate_basis": "Prompt character/4 estimate supplied by input prep; not tokenizer-verified.",
        "full_scope_conservative_reservation_usd": total_reservation,
        "planned_new_api_calls": planned_api_calls,
        "planned_historical_import_rows": len(import_keys),
        "historical_source_reported_cost_usd": sum(
            row["source_api_reported_cost_usd"] or 0.0 for row in import_plan["rows"]),
        "input_estimate_scope": "Full 41,970-prompt estimate before zero-new-fee historical imports.",
        "max_request_reservation_usd": max((s["reserved_usd"] for s in slots if s["key"] not in import_keys), default=0.0),
        "budget_may_stop_scope_early": cap < total_reservation,
        "maximum_repair_attempts": planned_api_calls,
        "maximum_physical_attempts": 2 * planned_api_calls,
        "new_api_calls": 0, "truth_opened": False, "api_keys_read": False}


def checked(folder, authorized=False):
    folder = _safe_output_path(folder)
    config = read_json(folder / "config.json")
    manifest = read_json(folder / "manifest.json")
    if sha(folder / "protocol.json") != manifest.get("protocol_sha256"):
        raise ValueError("Frozen protocol hash mismatch")
    for relative, expected in manifest.get("prepared_file_sha256", {}).items():
        if sha(folder / relative) != expected:
            raise ValueError("Prepared Terminal file changed: " + relative)
    for relative, expected in manifest.get("source_sha256", {}).items():
        if relative.startswith("/") or ".." in Path(relative).parts:
            raise ValueError("Unsafe pinned source path")
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT.resolve()) or not path.is_file() or sha(path) != expected:
            raise ValueError("Frozen source/input changed: " + relative)
    if config.get("protocol_sha256") != manifest.get("protocol_sha256"):
        raise ValueError("Config is attached to a different protocol")
    protocol = read_json(folder / "protocol.json")
    import_plan_path = folder / "historical_import_plan_private.json"
    import_plan = read_json(import_plan_path)
    import_keys = [row.get("key") for row in import_plan.get("rows", [])]
    if (import_plan.get("schema") != "sce_full_a_personal_historical_import_plan/v1"
            or len(import_keys) != len(set(import_keys))
            or import_plan.get("eligible_import_count") != len(import_keys)
            or import_plan.get("candidate_count") != 189
            or len(import_keys) != 182
            or any(not isinstance(key, str) for key in import_keys)
            or set(import_keys) & {slot["key"] for slot in _slot_index(folder)[:64]}
            or sha(import_plan_path) != protocol.get("historical_import_plan_sha256")
            or config.get("historical_import_plan_sha256") != protocol.get("historical_import_plan_sha256")
            or config.get("planned_historical_import_rows") != len(import_keys)
            or config.get("planned_new_api_calls") != protocol.get("planned_calls") - len(import_keys)
            or protocol.get("planned_new_api_calls") != protocol.get("planned_calls") - len(import_keys)
            or protocol.get("historical_imports", {}).get("planned_import_rows") != len(import_keys)
            or protocol.get("historical_imports", {}).get("source_protocol_sha256")
               != import_plan.get("source_protocol_sha256")):
        raise ValueError("Historical import plan differs from the pinned 189/182 exact-source contract")
    if (protocol.get("mechanism") != "full_a_personal_single_arm_single_pass"
            or protocol.get("months") != list(MONTHS) or protocol.get("arm") != ARM
            or protocol.get("generation_repeats") != [REPEAT]
            or protocol.get("planned_calls") != EXPECTED_PERSON_MONTHS
            or protocol.get("planned_new_api_calls") != EXPECTED_PERSON_MONTHS - 182
            or protocol.get("repair", {}).get("max_requests") != EXPECTED_PERSON_MONTHS - 182
            or protocol.get("max_physical_attempts") != 2 * (EXPECTED_PERSON_MONTHS - 182)
            or protocol.get("destination") != "https://openrouter.ai/api/v1"
            or protocol.get("model") != "deepseek/deepseek-v3.2"
            or protocol.get("route") != "siliconflow/fp8"
            or protocol.get("expected_provider") != "SiliconFlow"
            or protocol.get("temperature") != 0.5
            or protocol.get("thinking") != "disabled"
            or protocol.get("response_format") != "json_object"
            or protocol.get("max_tokens") != MAX_OUTPUT_TOKENS
            or protocol.get("timeout_s") != 120 or protocol.get("retry_max") != 0
            or protocol.get("provider_fallback") is not False
            or protocol.get("price_input_per_mtok") != PRICE_INPUT_PER_MTOK
            or protocol.get("price_output_per_mtok") != PRICE_OUTPUT_PER_MTOK
            or protocol.get("request_extra_body") != {"provider": {"order": ["siliconflow/fp8"],
                "allow_fallbacks": False, "require_parameters": True,
                "max_price": {"prompt": PRICE_INPUT_PER_MTOK, "completion": PRICE_OUTPUT_PER_MTOK}},
                "reasoning": {"enabled": False}}):
        raise ValueError("Full-A scientific or provider protocol differs from its fixed contract")
    _positive_finite(protocol.get("budget_cap_usd"), "budget_cap_usd")
    if sha(METADATA) != manifest["source_sha256"].get(str(METADATA.relative_to(ROOT))):
        raise ValueError("Fixed V3.2 provider metadata is not pinned")
    if authorized:
        auth = read_json(folder / "authorization.json")
        if (auth.get("approved") is not True or auth.get("config_sha256") != sha(folder / "config.json")
                or auth.get("protocol_sha256") != sha(folder / "protocol.json")
                or auth.get("prompt_scope_sha256") != config.get("prompt_scope_sha256")
                or auth.get("planned_new_api_calls") != protocol.get("planned_new_api_calls")
                or auth.get("planned_historical_import_rows") != protocol.get("historical_imports", {}).get("planned_import_rows")
                or auth.get("historical_import_plan_sha256") != protocol.get("historical_import_plan_sha256")
                or auth.get("main_max_requests") != protocol.get("planned_calls")
                or auth.get("repair_max_requests") != protocol.get("repair", {}).get("max_requests")
                or auth.get("maximum_physical_attempts") != protocol.get("max_physical_attempts")
                or auth.get("user_confirmation") != "--confirm-scope-and-budget"):
            raise ValueError("Authorization must match the exact full-A scope and budget")
    return config, protocol


def _slot_index(folder):
    return read_json(Path(folder) / "slot_index_private.json")


def _materialize(input_dir, metadata):
    """Load only the prompt rows needed for this segment, not all 41,970 at once."""
    by_month = {}
    input_dir = Path(input_dir)
    result = []
    for item in metadata:
        month = item["month"]
        if month not in by_month:
            by_month[month] = _load_prompts(input_dir, month)
        row = by_month[month].get(str(item["agent_id"]))
        if row is None or row.get("prompt_sha256") != item["prompt_sha256"]:
            raise ValueError("Current frozen prompt no longer matches the Terminal slot index")
        result.append({k: item[k] for k in ("key", "month", "arm", "repeat", "agent_id",
                                             "prompt_sha256", "reserved_usd")} |
                      {"messages": row["messages"]})
    return result


def _stage_next_segment(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rounds = sorted(root.glob("round_*"))
    round_dir = rounds[-1] if rounds else root / "round_0001"
    round_dir.mkdir(exist_ok=True)
    segments = sorted(round_dir.glob("segment_*"))
    return round_dir / f"segment_{len(segments) + 1:04d}"


def _normal_return(row):
    return row.get("error") is None and row.get("finish_reason") == "stop"


def technical_gate(intents, replies, protocol):
    gate_intents = intents[:32]
    by_key = {row["key"]: row for row in replies}
    selected_keys = [row["key"] for row in gate_intents]
    gate_rows = [by_key[key] for key in selected_keys if key in by_key]
    normal = [row for row in gate_rows if _normal_return(row)]
    probes = 0
    if len(gate_intents) >= 32 and len(normal) < 16:
        for intent in intents[32:64]:
            probes += 1
            row = by_key.get(intent["key"])
            if row:
                gate_rows.append(row)
                if _normal_return(row):
                    normal.append(row)
            if len(normal) >= 16:
                break
    usable = sum(all(queue.fields(row).values()) for row in normal)
    ratio = usable / len(normal) if normal else None
    ready = len(gate_intents) >= 32 and len(normal) >= 16
    passed = ready and ratio is not None and ratio >= protocol["technical_gate"]["minimum_format_ratio"]
    if not ready:
        reason = "insufficient_normal_returns" if len(gate_intents) >= 32 else "initial_gate_incomplete"
    elif not passed:
        reason = "format_ratio_below_threshold"
    else:
        reason = None
    return {"initial_attempts": len(gate_intents), "normal_returns": len(normal),
            "format_usable": usable, "format_ratio": ratio, "probe_attempts": probes,
            "minimum_normal_returns": 16, "minimum_format_ratio": .95,
            "passed": passed, "ready": ready, "reason": reason}


def _validate_main_archive(intents, replies, slots):
    slot_by_key = {row["key"]: row for row in slots}
    intent_by_key = {row.get("key"): row for row in intents}
    reply_by_key = {row.get("key"): row for row in replies}
    if len(slot_by_key) != len(slots) or len(intent_by_key) != len(intents):
        raise ValueError("Main scope/dispatch keys must be unique")
    if not set(intent_by_key) <= set(slot_by_key) or not set(reply_by_key) <= set(intent_by_key):
        raise ValueError("Main archive includes an unknown dispatch or reply")
    for key, row in intent_by_key.items():
        slot = slot_by_key[key]
        if row.get("prompt_sha256") != slot["prompt_sha256"] or row.get("reserved_usd") != slot["reserved_usd"]:
            raise ValueError("Main dispatch differs from the frozen slot")
    for key, row in reply_by_key.items():
        if row.get("prompt_sha256") != intent_by_key[key].get("prompt_sha256"):
            raise ValueError("Main response prompt differs from its intent")
    return slot_by_key


def _execute_tolerant_segment(protocol, slots, out, send, *, workers, max_workers, scale_after, policy,
                              prior_intents=(), prior_replies=(), publish=lambda _live: None,
                              engineering_only=True):
    """Durable one-attempt segment; tolerate isolated transport failures.

    Unlike the frozen generic queue, this new study-scoped adapter does not
    stop on every connection/timeout/5xx row. It continues until a hard error,
    explicit retry-after/429, three consecutive transport errors, a 25% rolling
    32-error window, or the shared budget boundary. The old queue/accounting
    implementation remains unchanged and consumes the same ledger format.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    prior = queue.account(prior_intents, prior_replies)
    registered = {slot["key"]: slot for slot in slots}
    if len(registered) != len(slots) or set(registered) & {row["key"] for row in prior_intents}:
        raise ValueError("Segment scope has duplicate or already-dispatched keys")
    sender = queue.safe_sender(send)
    spent, in_flight = prior["spent_or_reserved_usd"], 0.0
    intents, replies, active = [], [], {}
    cursor, peak, halted = 0, 0, None
    failures = deque(maxlen=32)
    consecutive_failures = 0
    started = time.monotonic()

    def one(slot):
        row = {key: slot[key] for key in ("key", "month", "arm", "repeat", "agent_id", "prompt_sha256")}
        row.update(error=None, fatal=False, raw_response_text="", finish_reason=None,
                   api_reported_cost_usd=None, request_reservation_usd=slot["reserved_usd"],
                   started_at_utc=queue.now(), attempt_idx=0,
                   actual_model_results=not engineering_only)
        try:
            row.update(sender(slot["messages"]))
            if row.get("returned_model") != protocol["model"] or row.get("returned_provider") != protocol["expected_provider"]:
                row.update(error="Locked model/provider mismatch", fatal=True)
            fee = row.get("api_reported_cost_usd")
            if fee is not None and (type(fee) not in (int, float) or not math.isfinite(fee)
                    or fee < 0 or fee > slot["reserved_usd"] + 1e-9):
                row.update(error="Invalid/excess reported charge", fatal=True)
        except Exception as exc:
            row.update(error=type(exc).__name__, error_http_status=getattr(exc, "status_code", None), fatal=True)
        # The execution mode, not untrusted sender return metadata, determines
        # whether these rows can enter the research evaluation path.
        row["actual_model_results"] = not engineering_only
        row.update(raw_response_sha256=hashlib.sha256(row["raw_response_text"].encode()).hexdigest(),
                   finished_at_utc=queue.now())
        row["field_usable"] = queue.fields(row)
        row["technical_usable"] = all(row["field_usable"].values())
        return row

    def write(stream, row):
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

    with ((out / "dispatch_private.jsonl").open("x", encoding="utf-8") as dispatch,
          (out / "calls_private.jsonl").open("x", encoding="utf-8") as log,
          ThreadPoolExecutor(max_workers=max_workers) as pool):
        while cursor < len(slots) or active:
            capacity = max_workers if len(replies) >= scale_after else workers
            while not halted and cursor < len(slots) and len(active) < capacity:
                slot = slots[cursor]
                if message_hash(slot["messages"]) != slot["prompt_sha256"]:
                    halted = "Frozen prompt mismatch"
                    break
                if spent + in_flight + slot["reserved_usd"] > protocol["budget_cap_usd"] + 1e-12:
                    halted = "Budget cap reached before dispatch"
                    break
                intent = {key: slot[key] for key in ("key", "prompt_sha256", "reserved_usd")}
                intent["at_utc"] = queue.now()
                write(dispatch, intent)
                intents.append(intent)
                active[pool.submit(one, slot)] = slot
                in_flight += slot["reserved_usd"]
                cursor += 1
                peak = max(peak, len(active))
            live = {"phase": "generation", "attempts": prior["attempts"] + len(intents),
                    "completed": prior["completed"] + len(replies), "in_flight": len(active),
                    "usable": prior["usable"] + sum(row["technical_usable"] for row in replies),
                    "reported_cost_usd": prior["reported_cost_usd"] + sum(
                        row["api_reported_cost_usd"] for row in replies
                        if type(row.get("api_reported_cost_usd")) in (int, float)
                        and math.isfinite(row["api_reported_cost_usd"]) and row["api_reported_cost_usd"] >= 0),
                    "spent_or_reserved_usd": spent + in_flight, "at_utc": queue.now()}
            publish(live)
            if not active:
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            finished = []
            for future in done:
                slot = active.pop(future)
                row = future.result()
                finished.append((row.get("finished_at_utc", ""), slot, row))
            for _finished_at, slot, row in sorted(finished, key=lambda item: item[0]):
                write(log, row)
                replies.append(row)
                in_flight -= slot["reserved_usd"]
                fee = row.get("api_reported_cost_usd")
                valid_fee = type(fee) in (int, float) and math.isfinite(fee) and fee >= 0
                spent += fee if valid_fee else slot["reserved_usd"]
                if row.get("error"):
                    failures.append(True)
                    consecutive_failures += 1
                    if not recoverable(row, policy):
                        halted = "hard_provider_or_account_error"
                    elif row.get("error_http_status") == 429:
                        halted = halted or "http_429_cooldown"
                    elif getattr(sender, "retry_after_s", 0.0) > 0:
                        halted = halted or "retry_after_cooldown"
                    elif consecutive_failures >= 3:
                        halted = halted or "consecutive_transport_failure_limit"
                else:
                    failures.append(False)
                    consecutive_failures = 0
                # Check after every completed request. The 32nd observation can
                # be a healthy reply even when the rolling window has crossed
                # its transport-error threshold on an earlier error.
                if len(failures) == 32 and sum(failures) >= 8:
                    halted = halted or "rolling_32_transport_failure_limit"
                if spent + in_flight > protocol["budget_cap_usd"] + 1e-9:
                    halted = halted or "Budget guard"
    result = queue.account([*prior_intents, *intents], [*prior_replies, *replies])
    result.update(halt_reason=halted, peak_in_flight=peak, seconds=time.monotonic() - started,
                  new_attempts=len(intents), actual_model_results=not engineering_only,
                  status="completed" if cursor == len(slots) and not halted else "stopped")
    dump(out / "receipt.json", result)
    dump(out / "manifest.json", {"files_sha256": {name: sha(out / name) for name in
         ("dispatch_private.jsonl", "calls_private.jsonl", "receipt.json")}})
    return result, intents, replies


def _recover_after_segment(folder, sender, rows, receipt, policy, *, stage, cool):
    hard = [row for row in rows if row.get("error") and not recoverable(row, policy)]
    if hard:
        return False, "hard_provider_or_account_error"
    recoverable_rows = [row for row in rows if row.get("error") and recoverable(row, policy)]
    if not recoverable_rows:
        return False, receipt.get("halt_reason") or "stopped_nonrecoverable"
    status_path = Path(folder) / f"{stage}_scheduler_status.json"
    previous = read_json(status_path) if status_path.exists() else {}
    global_path = Path(folder) / "recovery_limits.json"
    global_previous = read_json(global_path) if global_path.exists() else {}
    cycles = int(previous.get("recovery_cycles", 0)) + 1
    cooldown_s = float(previous.get("total_cooldown_seconds", 0.0))
    global_cooldown_s = float(global_previous.get("total_cooldown_seconds", 0.0))
    healthy = sum(not row.get("error") for row in rows)
    no_progress = int(previous.get("no_progress_cycles", 0)) + 1 if healthy == 0 else 0
    unhealthy_prior = int(previous.get("unhealthy_recoveries", 0))
    if healthy >= policy["healthy_segment_min_successes"] and healthy / max(1, len(rows)) >= policy["healthy_segment_min_ratio"]:
        unhealthy_prior = 0
    unhealthy = unhealthy_prior + 1
    if unhealthy > policy["max_unhealthy_recoveries"]:
        return False, "consecutive_unhealthy_recovery_limit_reached"
    if no_progress >= policy["no_progress_recovery_limit"]:
        return False, "no_progress_recovery_limit_reached"
    delay_index = min(unhealthy - 1, len(policy["cooldown_seconds"]) - 1)
    delay = max(float(policy["cooldown_seconds"][delay_index]),
                float(getattr(sender, "retry_after_s", 0.0)))
    if global_cooldown_s + delay > policy["max_total_cooldown_seconds"]:
        return False, "total_cooldown_cap_reached"
    until = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
    status = {"stage": stage, "recovery_cycles": cycles,
              "unhealthy_recoveries": unhealthy, "no_progress_cycles": no_progress,
              "total_cooldown_seconds": cooldown_s + delay,
              "last_error": receipt.get("halt_reason"), "cooldown_remaining_s": delay,
              "phase": stage + "_cooldown", "cooldown_until_utc": until,
              "at_utc": queue.now()}
    atomic_json(status_path, status)
    atomic_json(global_path, {"total_cooldown_seconds": global_cooldown_s + delay,
        "recovery_cycles": int(global_previous.get("recovery_cycles", 0)) + 1,
        "cooldown_remaining_s": delay, "cooldown_until_utc": until,
        "last_stage": stage, "last_error": receipt.get("halt_reason"), "at_utc": queue.now()})
    cool(delay, status_path, status)
    atomic_json(status_path, dict(status, cooldown_remaining_s=0, at_utc=queue.now()))
    atomic_json(global_path, {"total_cooldown_seconds": global_cooldown_s + delay,
        "recovery_cycles": int(global_previous.get("recovery_cycles", 0)) + 1,
        "cooldown_remaining_s": 0, "cooldown_until_utc": until,
        "last_stage": stage, "last_error": receipt.get("halt_reason"), "at_utc": queue.now()})
    return True, None


def _resume_pending_cooldown(folder, stage, cool):
    """Honor a cooldown interrupted by process exit before dispatching more slots."""
    path = Path(folder) / f"{stage}_scheduler_status.json"
    if not path.exists():
        return
    state = read_json(path)
    until = state.get("cooldown_until_utc")
    if not until or state.get("phase") not in (stage + "_cooldown", "network_cooldown"):
        return
    remaining = max(0.0, (datetime.fromisoformat(until) - datetime.now(timezone.utc)).total_seconds())
    if remaining > 0:
        cool(remaining, path, state)
    atomic_json(path, dict(state, phase=stage + "_ready", cooldown_remaining_s=0, at_utc=queue.now()))
    global_path = Path(folder) / "recovery_limits.json"
    if global_path.exists():
        global_state = read_json(global_path)
        atomic_json(global_path, dict(global_state, cooldown_remaining_s=0, at_utc=queue.now()))


def _main_status(slots, intents, replies, gate):
    attempted = {row["key"] for row in intents}
    all_attempted = len(attempted) == len(slots)
    unresolved = len(intents) - len(replies)
    if not gate["passed"]:
        return "stopped_technical_gate" if gate["ready"] or len(intents) >= 64 else "stopped_main_incomplete"
    if not all_attempted:
        return "stopped_main_incomplete"
    return "completed" if unresolved == 0 else "stopped_unresolved_unknown_intents"


def _stage_historical_imports(main_root, slots, import_plan, *, already_attempted=()):
    """Write source-pinned historical replies as one immutable, zero-spend segment."""
    slot_by_key = {row["key"]: row for row in slots}
    plan_rows = import_plan.get("rows", [])
    if (import_plan.get("schema") != "sce_full_a_personal_historical_import_plan/v1"
            or import_plan.get("eligible_import_count") != len(plan_rows)):
        raise ValueError("Historical import plan is missing or incomplete")
    wanted = {}
    attempted = set(already_attempted)
    for item in plan_rows:
        key = item.get("key")
        if (key not in slot_by_key or item.get("prompt_sha256") != slot_by_key[key]["prompt_sha256"]
                or key in wanted):
            raise ValueError("Historical import plan is outside the frozen Full-A slots")
        if key not in attempted:
            wanted[key] = item
    if set(wanted) & {row["key"] for row in slots[:64]}:
        raise ValueError("Historical import plan overlaps protected initial gate/probe slots")
    if not wanted:
        return {"status": "not_needed", "imported_rows": 0, "new_api_calls": 0,
                "new_reported_cost_usd": 0.0, "historical_source_reported_cost_usd": 0.0}

    source_rows = {}
    wanted_by_path = {}
    for item in plan_rows:
        relative = item["source_reply_path"]
        wanted_by_path.setdefault(relative, {})[item["source_key"]] = item
    for relative, expected_items in wanted_by_path.items():
        source = _safe_source_file(relative)
        expected_file_sha = next(iter(expected_items.values()))["source_file_sha256"]
        if sha(source) != expected_file_sha or any(
                item["source_file_sha256"] != expected_file_sha for item in expected_items.values()):
            raise ValueError("Historical import source ledger changed after prepare")
        for line in source.read_bytes().splitlines(keepends=True):
            if not line.endswith(b"\n"):
                raise ValueError("Historical import source ledger has a torn final row")
            row = json.loads(line)
            item = expected_items.get(row.get("key"))
            if item is None:
                continue
            if hashlib.sha256(line).hexdigest() != item["source_record_sha256"]:
                raise ValueError("Historical import raw source row changed after prepare")
            source_rows[item["key"]] = (item, row)
    if set(source_rows) != set(wanted):
        raise ValueError("Historical import plan could not resolve every pinned source row")

    dispatch_rows, call_rows = [], []
    for key, item in wanted.items():
        slot = slot_by_key[key]
        _pinned_item, original = source_rows[key]
        if (original.get("error") is not None or original.get("actual_model_results") is not True
                or original.get("returned_model") != "deepseek/deepseek-v3.2"
                or original.get("returned_provider") != "SiliconFlow"
                or original.get("finish_reason") != "stop"
                or original.get("prompt_sha256") != slot["prompt_sha256"]
                or original.get("raw_response_sha256") != item["source_raw_response_sha256"]
                or not all(queue.fields(original).values())):
            raise ValueError("Historical imported reply no longer meets the frozen success criteria")
        old_cost = original.get("api_reported_cost_usd")
        call = dict(original)
        call.update(key=key, execution_kind="historical_import", external_request_sent=False,
            source_api_reported_cost_usd=old_cost,
            source_request_reservation_usd=original.get("request_reservation_usd"),
            api_reported_cost_usd=0.0, request_reservation_usd=0.0,
            historical_source={"stage": item["source_stage"], "key": item["source_key"],
                "reply_path": item["source_reply_path"],
                "source_file_sha256": item["source_file_sha256"],
                "source_record_sha256": item["source_record_sha256"],
                "source_raw_response_sha256": item["source_raw_response_sha256"],
                "api_reported_cost_usd": old_cost})
        call_rows.append(call)
        dispatch_rows.append({"key": key, "prompt_sha256": slot["prompt_sha256"],
            "reserved_usd": slot["reserved_usd"], "execution_kind": "historical_import",
            "external_request_sent": False, "source_reply_path": item["source_reply_path"],
            "source_record_sha256": item["source_record_sha256"], "at_utc": queue.now()})

    segment = _stage_next_segment(main_root)
    segment.mkdir(parents=True, exist_ok=False)
    for name, rows in (("dispatch_private.jsonl", dispatch_rows), ("calls_private.jsonl", call_rows)):
        path = segment / name
        with path.open("x", encoding="utf-8") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    receipt = {"schema": "sce_full_a_personal_historical_import_segment/v1",
        "status": "completed", "imported_rows": len(call_rows),
        "new_api_calls": 0, "new_reported_cost_usd": 0.0,
        "historical_source_reported_cost_usd": sum(
            row.get("source_api_reported_cost_usd") or 0.0 for row in call_rows),
        "truth_opened": False, "at_utc": queue.now()}
    dump(segment / "receipt.json", receipt)
    manifest = {name: sha(segment / name) for name in
                ("dispatch_private.jsonl", "calls_private.jsonl", "receipt.json")}
    dump(segment / "manifest.json", {"segment_kind": "historical_import",
        "files_sha256": manifest})
    with (segment / "manifest.json").open("rb") as stream:
        os.fsync(stream.fileno())
    return receipt


def _imported_intents(intents):
    return [row for row in intents if row.get("execution_kind") == "historical_import"]


def _new_api_intent_count(intents):
    return len(intents) - len(_imported_intents(intents))


def _main_receipt_counts(result, intents, replies):
    result["historical_import_rows"] = len(_imported_intents(intents))
    result["new_api_calls"] = _new_api_intent_count(intents)
    result["historical_source_reported_cost_usd"] = sum(
        row.get("historical_source", {}).get("api_reported_cost_usd") or 0.0
        for row in replies if row.get("execution_kind") == "historical_import")
    return result


def run_main_segments(protocol, metadata, run_dir, send, policy, *, cool=queue.cooldown,
                      publish=lambda _stage, _live: None, engineering_only=True,
                      historical_import_plan=None):
    """Run the main one-attempt ledger; continue only never-dispatched slots."""
    run_dir = Path(run_dir)
    main_root = run_dir / "main"
    sender = queue.safe_sender(send)
    slot_by_key = {row["key"]: row for row in metadata}
    if len(slot_by_key) != len(metadata):
        raise ValueError("Main frozen slot keys are duplicated")
    while True:
        _resume_pending_cooldown(run_dir, "main", cool)
        intents, replies = queue.archive(main_root)
        _validate_main_archive(intents, replies, metadata)
        gate = technical_gate(intents, replies, protocol)
        if gate["ready"] and not gate["passed"]:
            dump(run_dir / "technical_gate.json", gate)
            return _main_receipt_counts({"status": "stopped_technical_gate", "halt_reason": gate["reason"],
                    "technical_gate": gate, **queue.account(intents, replies)}, intents, replies)
        if len(intents) >= 64 and not gate["ready"]:
            dump(run_dir / "technical_gate.json", gate)
            return _main_receipt_counts({"status": "stopped_technical_gate",
                    "halt_reason": "insufficient_normal_returns_after_bounded_probes",
                    "technical_gate": gate, **queue.account(intents, replies)}, intents, replies)
        if gate["passed"]:
            dump(run_dir / "technical_gate.json", gate)
        attempted = {row["key"] for row in intents}
        if gate["passed"] and not engineering_only:
            if historical_import_plan is None:
                import_path = run_dir / "historical_import_plan_private.json"
                historical_import_plan = read_json(import_path) if import_path.is_file() else None
            if historical_import_plan is not None:
                import_keys = {row.get("key") for row in historical_import_plan.get("rows", [])}
                live_attempts = {row["key"] for row in intents
                                 if row.get("execution_kind") != "historical_import"}
                if import_keys & live_attempts:
                    raise ValueError("A planned historical-import slot was already physically dispatched")
                pending_imports = [row for row in historical_import_plan.get("rows", [])
                                   if row.get("key") not in attempted]
                if pending_imports:
                    _stage_historical_imports(main_root, metadata, historical_import_plan,
                                              already_attempted=attempted)
                    continue
        pending_meta = [row for row in metadata if row["key"] not in attempted]
        if gate["passed"] and not pending_meta:
            status = _main_status(metadata, intents, replies, gate)
            result = {"status": status, "halt_reason": None, "technical_gate": gate,
                      "actual_model_results": bool(replies) and all(
                          row.get("actual_model_results") is True for row in replies),
                      **queue.account(intents, replies)}
            result = _main_receipt_counts(result, intents, replies)
            dump(run_dir / "main_receipt.json", result)
            return result
        if not pending_meta:
            dump(run_dir / "technical_gate.json", gate)
            result = {"status": "stopped_main_incomplete", "halt_reason": gate["reason"],
                      "technical_gate": gate, **queue.account(intents, replies)}
            result = _main_receipt_counts(result, intents, replies)
            dump(run_dir / "main_receipt.json", result)
            return result
        if len(intents) < 32:
            selected_meta = pending_meta[:min(32 - len(intents), 32)]
            workers = max_workers = 8
            scale_after = 33
        elif not gate["ready"]:
            selected_meta = pending_meta[:1]
            workers = max_workers = 8
            scale_after = 33
        elif not gate["passed"]:
            dump(run_dir / "technical_gate.json", gate)
            result = {"status": "stopped_technical_gate", "halt_reason": gate["reason"],
                      "technical_gate": gate, **queue.account(intents, replies)}
            result = _main_receipt_counts(result, intents, replies)
            dump(run_dir / "main_receipt.json", result)
            return result
        else:
            selected_meta = pending_meta[:policy["batch_slots"]]
            workers, max_workers = policy["initial_workers"], policy["max_workers"]
            scale_after = policy["scale_up_after_completed"]
        selected = _materialize(protocol["input_package_path"], selected_meta)
        all_intents, all_replies = queue.archive(main_root)
        segment = _stage_next_segment(main_root)
        sender.retry_after_s = 0.0
        receipt, _, rows = _execute_tolerant_segment(protocol, selected, segment, sender,
            workers=workers, max_workers=max_workers, scale_after=scale_after, policy=policy,
            prior_intents=all_intents, prior_replies=all_replies,
            publish=lambda live: publish("main", live), engineering_only=engineering_only)
        if receipt.get("halt_reason"):
            current_intents, current_replies = queue.archive(main_root)
            if (len(current_intents) == len(metadata)
                    and technical_gate(current_intents, current_replies, protocol)["passed"]
                    and receipt["halt_reason"] not in {"http_429_cooldown", "retry_after_cooldown",
                        "consecutive_transport_failure_limit", "rolling_32_transport_failure_limit"}):
                # The final segment may contain ordinary transport failures. There
                # is no never-dispatched work left to justify another cooldown.
                continue
            okay, stop_reason = _recover_after_segment(run_dir, sender, rows, receipt, policy,
                                                       stage="main", cool=cool)
            if not okay:
                current_intents, current_replies = queue.archive(main_root)
                _validate_main_archive(current_intents, current_replies, metadata)
                gate = technical_gate(current_intents, current_replies, protocol)
                result = {"status": "stopped_main_incomplete", "halt_reason": stop_reason,
                          "technical_gate": gate, **queue.account(current_intents, current_replies)}
                result = _main_receipt_counts(result, current_intents, current_replies)
                dump(run_dir / "main_receipt.json", result)
                return result


def _repair_targets(main_replies, slot_by_key, policy):
    by_key = {row.get("key"): row for row in main_replies}
    if len(by_key) != len(main_replies) or not set(by_key) <= set(slot_by_key):
        raise ValueError("Main replies contain duplicate or non-main keys")
    result = {}
    for key, row in by_key.items():
        if row.get("error"):
            if not recoverable(row, policy):
                raise ValueError("Hard provider/account failure cannot enter automatic repair")
            fields = ["q8", "q9"]
        elif row.get("finish_reason") != "stop":
            fields = ["q8", "q9"]
        else:
            fields = [field for field, valid in queue.fields(row).items() if not valid]
        if fields:
            result[key] = {"key": key, "prompt_sha256": slot_by_key[key]["prompt_sha256"],
                           "fields": fields, "main_error": row.get("error"),
                           "main_finish_reason": row.get("finish_reason")}
    return result


def _repair_slot(slot):
    return {**slot, "key": "repair1|" + slot["key"]}


def _validate_repair(intents, replies, targets, slot_by_key):
    intent_by_key = {row.get("key"): row for row in intents}
    reply_by_key = {row.get("key"): row for row in replies}
    if (len(intent_by_key) != len(intents) or len(reply_by_key) != len(replies)
            or not set(reply_by_key) <= set(intent_by_key)):
        raise ValueError("Repair ledger contains duplicate or unregistered keys")
    expected = {"repair1|" + key for key in targets}
    if not set(intent_by_key) <= expected:
        raise ValueError("Repair ledger is outside one-attempt technical-failure scope")
    for key, intent in intent_by_key.items():
        source_key = key.removeprefix("repair1|")
        slot = slot_by_key[source_key]
        if (intent.get("prompt_sha256") != slot["prompt_sha256"]
                or intent.get("reserved_usd") != slot["reserved_usd"]):
            raise ValueError("Repair dispatch differs from original frozen prompt/reservation")
    for key, row in reply_by_key.items():
        if row.get("prompt_sha256") != intent_by_key[key].get("prompt_sha256"):
            raise ValueError("Repair reply prompt differs from its intent")
    return intent_by_key, reply_by_key


def run_repair_segments(protocol, metadata, run_dir, main_intents, main_replies, send, policy, *,
                        cool=queue.cooldown, publish=lambda _stage, _live: None,
                        engineering_only=True):
    """Attempt each known new technical failure at most once; resume only untouched targets."""
    run_dir = Path(run_dir)
    main_root, repair_root = run_dir / "main", run_dir / "repair"
    slot_by_key = {row["key"]: row for row in metadata}
    targets = _repair_targets(main_replies, slot_by_key, policy)
    repair_root.mkdir(exist_ok=True)
    sender = queue.safe_sender(send)
    main_account = queue.account(main_intents, main_replies)
    while True:
        _resume_pending_cooldown(run_dir, "repair", cool)
        repair_intents, repair_replies = queue.archive(repair_root)
        attempted, answered = _validate_repair(repair_intents, repair_replies, targets, slot_by_key)
        repair_account = queue.account(repair_intents, repair_replies)
        if main_account["spent_or_reserved_usd"] + repair_account["spent_or_reserved_usd"] > protocol["budget_cap_usd"] + 1e-9:
            raise ValueError("Shared main plus repair budget cap exceeded")
        pending_keys = [key for key in targets if "repair1|" + key not in attempted]
        if not pending_keys:
            unresolved = repair_account["unresolved"]
            status = "not_needed" if not targets else ("completed" if unresolved == 0 else "stopped_unresolved_unknown_intents")
            all_results = [*main_replies, *repair_replies]
            result = {"status": status, "target_count": len(targets),
                      "actual_model_results": bool(all_results) and all(
                          row.get("actual_model_results") is True for row in all_results),
                      **repair_account}
            dump(run_dir / "repair_receipt.json", result)
            return result, repair_intents, repair_replies, targets
        pending_slots = [_repair_slot(slot_by_key[key]) for key in pending_keys[:policy["batch_slots"]]]
        # Materialize original prompts by their unprefixed main key.
        materialized = _materialize(protocol["input_package_path"], [slot_by_key[k] for k in pending_keys[:policy["batch_slots"]]])
        repair_slots = [{**slot, "messages": source["messages"]}
                        for slot, source in zip(pending_slots, materialized)]
        segment = _stage_next_segment(repair_root)
        sender.retry_after_s = 0.0
        prior_intents = [*main_intents, *repair_intents]
        prior_replies = [*main_replies, *repair_replies]
        receipt, _, rows = _execute_tolerant_segment(protocol, repair_slots, segment, sender,
            workers=policy["repair_initial_workers"], max_workers=policy["repair_max_workers"],
            scale_after=policy["repair_scale_after_completed"], policy=policy, prior_intents=prior_intents,
            prior_replies=prior_replies, publish=lambda live: publish("repair", live),
            engineering_only=engineering_only)
        if receipt.get("halt_reason"):
            if receipt["halt_reason"] in ("Budget cap reached before dispatch", "Budget guard"):
                result = {"status": "stopped_budget_guard", "target_count": len(targets),
                          "halt_reason": receipt["halt_reason"],
                          **queue.account(*queue.archive(repair_root))}
                dump(run_dir / "repair_receipt.json", result)
                return result, *queue.archive(repair_root), targets
            current_intents, _current_replies = queue.archive(repair_root)
            if len(current_intents) == len(targets):
                # All one-time repair attempts are already recorded. Never cool or
                # issue another request merely because the final repair failed.
                continue
            okay, stop_reason = _recover_after_segment(run_dir, sender, rows, receipt, policy,
                                                       stage="repair", cool=cool)
            if not okay:
                status = "stopped_hard_error" if stop_reason == "hard_provider_or_account_error" else "stopped_recoverable"
                result = {"status": status, "target_count": len(targets), "halt_reason": stop_reason,
                          **queue.account(*queue.archive(repair_root))}
                dump(run_dir / "repair_receipt.json", result)
                return result, *queue.archive(repair_root), targets


def _accounting(run_dir):
    main_i, main_r = queue.archive(Path(run_dir) / "main")
    repair_root = Path(run_dir) / "repair"
    repair_i, repair_r = queue.archive(repair_root) if repair_root.exists() else ([], [])
    main, repair = queue.account(main_i, main_r), queue.account(repair_i, repair_r)
    imported = _imported_intents(main_i)
    historical_source_cost = sum(
        row.get("historical_source", {}).get("api_reported_cost_usd") or 0.0
        for row in main_r if row.get("execution_kind") == "historical_import")
    return {"main_intents": main_i, "main_replies": main_r,
            "repair_intents": repair_i, "repair_replies": repair_r,
            "main": main, "repair": repair,
            "reported_cost_usd": main["reported_cost_usd"] + repair["reported_cost_usd"],
            "spent_or_reserved_usd": main["spent_or_reserved_usd"] + repair["spent_or_reserved_usd"],
            "unresolved_unknown_intents": main["unresolved"] + repair["unresolved"],
            "historical_import_rows": len(imported),
            "historical_source_reported_cost_usd": historical_source_cost,
            "new_api_calls": _new_api_intent_count(main_i) + len(repair_i)}


def review(folder):
    config, protocol = checked(folder)
    slots = _slot_index(folder)
    accounting = _accounting(folder)
    by_key = {row["key"]: row for row in slots}
    _validate_main_archive(accounting["main_intents"], accounting["main_replies"], slots)
    targets = _repair_targets(accounting["main_replies"], by_key, _policy())
    attempted, _ = _validate_repair(accounting["repair_intents"], accounting["repair_replies"], targets, by_key)
    if accounting["spent_or_reserved_usd"] > protocol["budget_cap_usd"] + 1e-9:
        raise ValueError("Shared budget cap exceeded")
    return {"status": "prepared_not_started" if not accounting["main_intents"] else "has_archived_attempts",
            "planned_calls": len(slots), "main": accounting["main"], "repair": accounting["repair"],
            "prompt_scope_sha256": config["prompt_scope_sha256"],
            "config_sha256": sha(Path(folder) / "config.json"),
            "protocol_sha256": sha(Path(folder) / "protocol.json"),
            "destination": protocol["destination"],
            "repair_targets": len(targets), "repair_attempts_remaining": len(targets) - len(attempted),
            "reported_cost_usd": accounting["reported_cost_usd"],
            "spent_or_reserved_usd": accounting["spent_or_reserved_usd"],
            "unknown_fee_reservation_usd": accounting["spent_or_reserved_usd"] - accounting["reported_cost_usd"],
            "budget_cap_usd": protocol["budget_cap_usd"],
            "input_estimated_api_cost_usd": config.get("estimated_api_cost_usd"),
            "input_cost_estimate": config.get("input_cost_estimate"),
            "cost_estimate_basis": config.get("cost_estimate_basis"),
            "full_scope_conservative_reservation_usd": config["full_scope_conservative_reservation_usd"],
            "maximum_two_attempt_conservative_reservation_usd": 2 * config["full_scope_conservative_reservation_usd"],
            "budget_may_stop_scope_early": protocol["budget_cap_usd"] < config["full_scope_conservative_reservation_usd"],
            "maximum_additional_main_attempts": max(0, protocol["planned_new_api_calls"]
                - _new_api_intent_count(accounting["main_intents"])),
            "maximum_repair_attempts": len(targets),
            "maximum_physical_attempts": protocol["max_physical_attempts"],
            "historical_import_rows": accounting["historical_import_rows"],
            "historical_source_reported_cost_usd": accounting["historical_source_reported_cost_usd"],
            "planned_new_api_calls": protocol["planned_new_api_calls"],
            "model": protocol["model"], "provider": protocol["route"], "new_api_calls": 0}


def _reply_references(run_dir, stage):
    """Map a registered reply to its immutable segment file without copying raw text."""
    root = Path(run_dir) / stage
    refs = {}
    for segment in sorted(root.glob("round_*/segment_*")):
        path = segment / "calls_private.jsonl"
        if not path.exists():
            continue
        relative = str(path.resolve().relative_to(Path(run_dir).resolve()))
        for row in queue.lines(path):
            key = row.get("key")
            if key in refs:
                raise ValueError("Duplicate raw reply reference")
            refs[key] = relative + "#key=" + str(key)
    return refs


def _dispatch_references(run_dir, stage):
    root = Path(run_dir) / stage
    refs = {}
    for segment in sorted(root.glob("round_*/segment_*")):
        path = segment / "dispatch_private.jsonl"
        if not path.exists():
            continue
        relative = str(path.resolve().relative_to(Path(run_dir).resolve()))
        for row in queue.lines(path):
            key = row.get("key")
            if key in refs:
                raise ValueError("Duplicate raw dispatch reference")
            refs[key] = relative + "#key=" + str(key)
    return refs


def write_logical_overlay(folder, protocol, slots, main_intents, main_replies,
                           repair_intents, repair_replies, main_result, repair_result):
    """Write a normalized, field-level main/repair union in a separate derived view.

    Raw call and dispatch JSONL files are never changed. A valid main field always
    wins; a repair may fill only a field that was invalid or absent in main.
    Initial-state fallback values stay in the private input package and are
    joined by the isolated evaluator.
    """
    folder = Path(folder)
    slot_by_key = {row["key"]: row for row in slots}
    main_intent_by_key = {row["key"]: row for row in main_intents}
    main_reply_by_key = {row["key"]: row for row in main_replies}
    repair_intent_by_key = {row["key"].removeprefix("repair1|"): row for row in repair_intents}
    repair_reply_by_key = {row["key"].removeprefix("repair1|"): row for row in repair_replies}
    if (len(slot_by_key) != len(slots) or len(main_intent_by_key) != len(main_intents)
            or len(main_reply_by_key) != len(main_replies)
            or len(repair_intent_by_key) != len(repair_intents)
            or len(repair_reply_by_key) != len(repair_replies)):
        raise ValueError("Cannot write logical overlay from duplicate ledger keys")
    main_reply_refs = _reply_references(folder, "main")
    repair_reply_refs = _reply_references(folder, "repair")
    main_dispatch_refs = _dispatch_references(folder, "main")
    repair_dispatch_refs = _dispatch_references(folder, "repair")
    if set(main_reply_refs) != set(main_reply_by_key):
        raise ValueError("Main raw reply references differ from parsed main ledger")
    if {key.removeprefix("repair1|") for key in repair_reply_refs} != set(repair_reply_by_key):
        raise ValueError("Repair raw reply references differ from parsed repair ledger")

    view_root = folder / "generation_views"
    view_root.mkdir(exist_ok=True)
    view_number = len(list(view_root.glob("view_*"))) + 1
    view = view_root / f"view_{view_number:04d}"
    view.mkdir(exist_ok=False)
    counts = {"planned": len(slots), "main_attempted": len(main_intents),
              "main_replied": len(main_replies), "repair_targets": len(repair_intents),
              "repair_replied": len(repair_replies), "q8_updated": 0, "q9_updated": 0,
              "q8_initial_fallback_needed": 0, "q9_initial_fallback_needed": 0,
              "both_fields_updated": 0, "unknown_main_intents": len(main_intents) - len(main_replies),
              "unknown_repair_intents": len(repair_intents) - len(repair_replies),
              "not_attempted_main": len(slots) - len(main_intents)}
    output = view / "logical_actions_private.jsonl"
    with output.open("x", encoding="utf-8") as dst:
        for key, slot in slot_by_key.items():
            main = main_reply_by_key.get(key)
            repair_key = "repair1|" + key
            repair = repair_reply_by_key.get(key)
            main_valid = queue.fields(main) if main is not None else {"q8": False, "q9": False}
            repair_valid = queue.fields(repair) if repair is not None else {"q8": False, "q9": False}
            sources, values, updated, fallback = {}, {}, {}, {}
            for field in ("q8", "q9"):
                if main_valid[field]:
                    sources[field] = "main"
                    chosen = main
                elif repair_valid[field]:
                    sources[field] = "repair"
                    chosen = repair
                else:
                    sources[field] = "initial_fallback"
                    chosen = None
                updated[field] = chosen is not None
                fallback[field] = chosen is None
                if chosen is None:
                    values[field] = None
                elif field == "q8":
                    values[field] = response_point(chosen["raw_response_text"])
                else:
                    try:
                        values[field] = response_view(chosen["raw_response_text"])["bins"]
                    except (TypeError, ValueError, KeyError):
                        values[field] = None
                        updated[field] = False
                        fallback[field] = True
                        sources[field] = "initial_fallback"
            counts["q8_updated"] += int(updated["q8"])
            counts["q9_updated"] += int(updated["q9"])
            counts["q8_initial_fallback_needed"] += int(fallback["q8"])
            counts["q9_initial_fallback_needed"] += int(fallback["q9"])
            counts["both_fields_updated"] += int(all(updated.values()))
            main_intent = main_intent_by_key.get(key)
            repair_intent = repair_intent_by_key.get(key)
            row = {
                "schema": "sce_full_a_personal_logical_action/v1",
                "key": key, "month": slot["month"], "agent_id": slot["agent_id"],
                "arm": ARM, "repeat": REPEAT, "prompt_sha256": slot["prompt_sha256"],
                "attempt_state": ("not_attempted" if main_intent is None else
                                  "unknown_main_intent" if main is None else "main_reply_received"),
                "main": {"intent_registered": main_intent is not None,
                    "reply_received": main is not None,
                    "execution_kind": (main.get("execution_kind", "live_api") if main else None),
                    "external_request_sent": (main.get("external_request_sent", True) if main else None),
                    "dispatch_ref": main_dispatch_refs.get(key),
                    "raw_reply_ref": main_reply_refs[key] if main is not None else None,
                    "historical_source": main.get("historical_source") if main else None,
                    "error": main.get("error") if main else None,
                    "finish_reason": main.get("finish_reason") if main else None,
                    "raw_response_sha256": main.get("raw_response_sha256") if main else None,
                    "field_valid": main_valid,
                    "returned_model": main.get("returned_model") if main else None,
                    "returned_provider": main.get("returned_provider") if main else None},
                "repair": {"intent_registered": repair_intent is not None,
                    "reply_received": repair is not None,
                    "dispatch_ref": repair_dispatch_refs.get(repair_key),
                    "raw_reply_ref": repair_reply_refs[repair_key] if repair is not None else None,
                    "error": repair.get("error") if repair else None,
                    "finish_reason": repair.get("finish_reason") if repair else None,
                    "raw_response_sha256": repair.get("raw_response_sha256") if repair else None,
                    "field_valid": repair_valid,
                    "returned_model": repair.get("returned_model") if repair else None,
                    "returned_provider": repair.get("returned_provider") if repair else None},
                "field_updated": updated, "field_source": sources,
                "needs_initial_fallback": fallback,
                "effective_q8": values["q8"], "effective_q9_bins": values["q9"],
                "q9_normalization": "proportional_nonnegative_v1" if values["q9"] is not None else None,
            }
            dst.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        dst.flush()
        os.fsync(dst.fileno())
    accounting = queue.account(main_intents, main_replies)
    repair_account = queue.account(repair_intents, repair_replies)
    main_complete = (main_result.get("status") == "completed"
                     and main_result.get("technical_gate", {}).get("passed") is True
                     and accounting["attempts"] == len(slots) and accounting["completed"] == len(slots))
    repair_complete = (repair_result.get("status") == "not_needed" and not repair_intents) or (
        repair_result.get("status") == "completed"
        and repair_account["attempts"] == repair_result.get("target_count")
        and repair_account["completed"] == repair_account["attempts"])
    completed = bool(main_complete and repair_complete)
    all_results = [*main_replies, *repair_replies]
    actual_results = bool(all_results) and all(
        row.get("actual_model_results") is True for row in all_results)
    historical_imports = _imported_intents(main_intents)
    physical_attempts = _new_api_intent_count(main_intents) + repair_account["attempts"]
    historical_source_cost = sum(
        row.get("historical_source", {}).get("api_reported_cost_usd") or 0.0
        for row in main_replies if row.get("execution_kind") == "historical_import")
    receipt = {"schema": "sce_full_a_personal_logical_overlay_receipt/v1",
        "status": ("completed" if completed and actual_results else
                   "completed_engineering_only" if completed else "partial_data_preserved"),
        "generation_completed": completed, "actual_model_results": actual_results,
        "evaluation_performed": False, "planned_calls": len(slots),
        "unknown_intents": counts["unknown_main_intents"] + counts["unknown_repair_intents"],
        "unknown": counts["unknown_main_intents"] + counts["unknown_repair_intents"],
        "not_attempted": counts["not_attempted_main"],
        "protocol_sha256": sha(folder / "protocol.json"),
        "input_manifest_sha256": read_json(folder / "config.json")["input_manifest_sha256"],
        "logical_actions_file": output.name, "logical_actions_sha256": sha(output),
        "main_complete": main_complete, "repair_complete": repair_complete,
        "main_status": main_result.get("status"), "repair_status": repair_result.get("status"),
        "counters": counts, "new_api_calls": physical_attempts if actual_results else 0,
        "historical_import_rows": len(historical_imports),
        "historical_source_reported_cost_usd": historical_source_cost,
        "simulated_dispatches": 0 if actual_results else physical_attempts,
        "reported_cost_usd": accounting["reported_cost_usd"] + repair_account["reported_cost_usd"],
        "spent_or_reserved_usd": accounting["spent_or_reserved_usd"] + repair_account["spent_or_reserved_usd"],
        "budget_cap_usd": protocol["budget_cap_usd"],
        "raw_ledger_manifests_sha256": {str(path.resolve().relative_to(folder.resolve())): sha(path)
            for stage in ("main", "repair") for path in sorted((folder / stage).glob("round_*/segment_*/manifest.json"))},
        "field_overlay_rule": "valid main fields preserved; valid repair fields fill only main-invalid fields; remaining fields use input initial state during isolated evaluation",
        "truth_opened": False}
    dump(view / "receipt.json", receipt)
    dump(view / "manifest.json", {"schema": "sce_full_a_personal_logical_overlay_manifest/v1",
        "files_sha256": {"logical_actions_private.jsonl": sha(output), "receipt.json": sha(view / "receipt.json")}})
    atomic_json(folder / "latest_generation_view.json", {"path": str(view.relative_to(folder)),
        "manifest_sha256": sha(view / "manifest.json"), "receipt_sha256": sha(view / "receipt.json")})
    return {"path": str(view), **receipt}


def _evaluation_allowed(overlay):
    """Only complete, explicitly actual-model generations may read evaluation targets."""
    return (overlay.get("generation_completed") is True
            and overlay.get("actual_model_results") is True)


def run_engineering_replay(input_dir, out, budget_cap_usd, *, fail_once_prompt_hashes=()):
    """Offline full-scope replay using a fixed fake sender; never authorizes or evaluates.

    `fail_once_prompt_hashes` injects one synthetic APIConnectionError for each
    selected unique prompt hash. Those rows become the normal single-repair
    targets. Every raw row and overlay is permanently marked engineering-only.
    """
    failures = set(fail_once_prompt_hashes)
    prepared = prepare(input_dir, out, budget_cap_usd)
    run_dir = Path(prepared["run_dir"])
    dump(run_dir / "engineering_only_replay.json", {
        "schema": "sce_full_a_engineering_replay_marker/v1",
        "actual_model_results": False, "external_api_calls": 0,
        "reason": "Synthetic sender replay; this directory must never be resumed live.",
        "injected_failure_prompt_hashes": sorted(failures)})
    _config, protocol = checked(run_dir)
    slots = _slot_index(run_dir)
    hash_counts = {}
    for slot in slots:
        digest = slot["prompt_sha256"]
        hash_counts[digest] = hash_counts.get(digest, 0) + 1
    if not failures <= set(hash_counts):
        raise ValueError("Injected failure plan includes a prompt outside the frozen scope")
    if any(hash_counts[digest] != 1 for digest in failures):
        raise ValueError("Fault injection requires unique prompt hashes for selected repair cases")
    injected, call_counts = set(), {}
    fake_raw = json.dumps({"point_pct": 3.5, "q9": {f"bin{i}": 10 for i in range(1, 11)}},
                          separators=(",", ":"))

    class APIConnectionError(Exception):
        pass

    def fake_sender(messages):
        digest = message_hash(messages)
        if digest not in hash_counts:
            raise ValueError("Engineering sender received a prompt outside the frozen scope")
        call_counts[digest] = call_counts.get(digest, 0) + 1
        if digest in failures and digest not in injected:
            injected.add(digest)
            raise APIConnectionError("Synthetic offline engineering fault")
        return {"returned_model": protocol["model"],
                "returned_provider": protocol["expected_provider"],
                "raw_response_text": fake_raw, "finish_reason": "stop",
                "api_reported_cost_usd": 0.0}

    policy = read_json(run_dir / "execution_policy.json")
    main = run_main_segments(protocol, slots, run_dir, fake_sender, policy,
                             engineering_only=True, cool=lambda *_args: None)
    main_intents, main_replies = queue.archive(run_dir / "main")
    gate = technical_gate(main_intents, main_replies, protocol)
    repair_result, repair_intents, repair_replies = {"status": "not_started"}, [], []
    main_scope_exhausted = len(main_intents) == len(slots)
    hard_main = any(row.get("error") and not recoverable(row, policy) for row in main_replies)
    if main_scope_exhausted and gate.get("passed") and not hard_main:
        repair_result, repair_intents, repair_replies, targets = run_repair_segments(
            protocol, slots, run_dir, main_intents, main_replies, fake_sender, policy,
            engineering_only=True, cool=lambda *_args: None)
    else:
        targets = _repair_targets(main_replies, {slot["key"]: slot for slot in slots}, policy)
    overlay = write_logical_overlay(run_dir, protocol, slots, main_intents, main_replies,
                                    repair_intents, repair_replies, main, repair_result)
    receipt = {"schema": "sce_full_a_personal_engineering_replay_receipt/v1",
        "status": ("completed_engineering_only" if overlay["generation_completed"]
                   else "partial_engineering_data_preserved"),
        "actual_model_results": False, "external_api_calls": 0,
        "simulated_dispatches": len(main_intents) + len(repair_intents),
        "injected_failure_prompt_hashes": sorted(failures),
        "injected_failures_consumed": sorted(injected),
        "main": main, "repair": repair_result, "technical_gate": gate,
        "repair_target_count": len(targets), "view_path": overlay["path"],
        "generation_completed": overlay["generation_completed"],
        "budget_cap_usd": protocol["budget_cap_usd"],
        "spent_or_reserved_usd": overlay["spent_or_reserved_usd"],
        "evaluation_performed": False, "authorization_written": False,
        "truth_opened": False}
    dump(run_dir / "engineering_replay_receipt.json", receipt)
    return receipt


def _publish_progress(folder, stage, live, main_baseline=None):
    path = Path(folder) / "progress.json"
    old = read_json(path) if path.exists() else {}
    data = dict(old, phase=stage, at_utc=queue.now(), in_flight=live.get("in_flight", 0))
    if stage == "main":
        data.update(main_attempts=live.get("attempts", 0), main_completed=live.get("completed", 0),
                    main_reported_cost_usd=live.get("reported_cost_usd", 0.0),
                    main_spent_or_reserved_usd=live.get("spent_or_reserved_usd", 0.0))
    else:
        base = main_baseline or {"attempts": 0, "completed": 0, "reported_cost_usd": 0.0,
                                 "spent_or_reserved_usd": 0.0}
        data.update(main_attempts=base["attempts"], main_completed=base["completed"],
                    main_reported_cost_usd=base["reported_cost_usd"],
                    main_spent_or_reserved_usd=base["spent_or_reserved_usd"],
                    repair_attempts=max(0, live.get("attempts", 0) - base["attempts"]),
                    repair_completed=max(0, live.get("completed", 0) - base["completed"]),
                    repair_reported_cost_usd=max(0.0, live.get("reported_cost_usd", 0.0) - base["reported_cost_usd"]),
                    repair_spent_or_reserved_usd=max(0.0, live.get("spent_or_reserved_usd", 0.0) - base["spent_or_reserved_usd"]))
    data["total_reported_cost_usd"] = data.get("main_reported_cost_usd", 0.0) + data.get("repair_reported_cost_usd", 0.0)
    data["total_spent_or_reserved_usd"] = data.get("main_spent_or_reserved_usd", 0.0) + data.get("repair_spent_or_reserved_usd", 0.0)
    data["unknown_fee_reservation_usd"] = max(0.0, data["total_spent_or_reserved_usd"] - data["total_reported_cost_usd"])
    atomic_json(path, data)


def _worker(folder, lock_fd):
    folder = Path(folder)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    wake = None
    try:
        if (folder / "engineering_only_replay.json").exists():
            raise ValueError("Engineering-only replay cannot enter the live worker")
        config, protocol = checked(folder, authorized=True)
        if sys.platform == "darwin":
            wake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        slots = _slot_index(folder)
        accounting = _accounting(folder)
        if accounting["spent_or_reserved_usd"] > protocol["budget_cap_usd"] + 1e-9:
            raise ValueError("Existing unknown/resolved charges exceed shared cap")
        policy = read_json(folder / "execution_policy.json")
        send = live_sender(protocol)
        main = run_main_segments(protocol, slots, folder, send, policy,
            publish=lambda stage, live: _publish_progress(folder, stage, live),
            engineering_only=False)
        main_intents, main_replies = queue.archive(folder / "main")
        main = _main_receipt_counts(main, main_intents, main_replies)
        gate = technical_gate(main_intents, main_replies, protocol)
        main_scope_exhausted = len(main_intents) == len(slots)
        hard_main = any(row.get("error") and not recoverable(row, policy) for row in main_replies)
        generation = {"schema": "sce_full_a_personal_generation_receipt/v1",
            "protocol_sha256": config["protocol_sha256"], "main": main,
            "main_scope_exhausted": main_scope_exhausted,
            "main_complete": main.get("status") == "completed" and gate.get("passed") is True,
            "technical_gate": gate, "truth_opened": False,
            "repair": {"status": "not_started"}, "evaluation": {"status": "not_run_isolated_stage_required"},
            "source_sha256": read_json(folder / "manifest.json")["source_sha256"],
            "new_api_calls": _new_api_intent_count(main_intents),
            "historical_import_rows": len(_imported_intents(main_intents)),
            "historical_source_reported_cost_usd": sum(
                row.get("historical_source", {}).get("api_reported_cost_usd") or 0.0
                for row in main_replies if row.get("execution_kind") == "historical_import")}
        dump(folder / "generation_receipt.json", generation)
        repair_result = generation["repair"]
        repair_intents, repair_replies = [], []
        if main_scope_exhausted and gate.get("passed") and not hard_main:
            baseline = queue.account(main_intents, main_replies)
            repair, repair_intents, repair_replies, targets = run_repair_segments(
                protocol, slots, folder, main_intents, main_replies, send, policy,
                publish=lambda stage, live: _publish_progress(folder, stage, live, baseline),
                engineering_only=False)
            generation.update(repair=repair, repair_targets=len(targets),
                repair_intents=len(repair_intents), repair_replies=len(repair_replies),
                repair_complete=repair["status"] in ("not_needed", "completed"),
                physical_api_attempts=_new_api_intent_count(main_intents) + len(repair_intents))
            repair_result = repair
        else:
            repair_root = folder / "repair"
            if repair_root.exists():
                repair_intents, repair_replies = queue.archive(repair_root)
        # This is a derived normalized field overlay, separate from immutable raw
        # call ledgers. Evaluation remains a later isolated process.
        overlay = write_logical_overlay(folder, protocol, slots, main_intents, main_replies,
            repair_intents, repair_replies, main, repair_result)
        generation.update(final_overlay=overlay["path"], generation_completed=overlay["generation_completed"],
                          actual_model_results=overlay["actual_model_results"],
                          status=("completed" if overlay["generation_completed"] and overlay["actual_model_results"]
                                  else "completed_engineering_only" if overlay["generation_completed"]
                                  else "partial_data_preserved"),
                          historical_import_rows=len(_imported_intents(main_intents)),
                          historical_source_reported_cost_usd=sum(
                              row.get("historical_source", {}).get("api_reported_cost_usd") or 0.0
                              for row in main_replies if row.get("execution_kind") == "historical_import"),
                          new_api_calls=_new_api_intent_count(main_intents) + len(repair_intents),
                          physical_api_attempts=_new_api_intent_count(main_intents) + len(repair_intents))
        dump(folder / "generation_receipt.json", generation)
        final_status = "generation_stopped_data_preserved"
        if _evaluation_allowed(overlay):
            eval_dirs = sorted(folder.glob("evaluation_round_*"))
            eval_out = folder / f"evaluation_round_{len(eval_dirs) + 1:04d}"
            command = [config["python"], "-u", str(EVALUATION_ENTRY), "--inputs",
                       config["input_package"], "--view", overlay["path"], "--out", str(eval_out)]
            generation["evaluation"] = {"status": "running_in_separate_process", "out": str(eval_out),
                                         "command": command, "started_at_utc": queue.now()}
            dump(folder / "generation_receipt.json", generation)
        elif overlay["generation_completed"]:
            generation["evaluation"] = {"status": "blocked_engineering_only_results"}
            dump(folder / "generation_receipt.json", generation)
            final_status = "generation_complete_engineering_only_no_evaluation"
            with (folder / f"evaluation_round_{len(eval_dirs) + 1:04d}.log").open("x") as log:
                code = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT).returncode
            if code == 0 and (eval_out / "summary.json").is_file():
                eval_summary = read_json(eval_out / "summary.json")
                if eval_summary.get("status") == "completed_full_a_personal_evaluation" and eval_summary.get("new_api_calls") == 0:
                    generation["evaluation"] = {"status": "completed_separate_process", "out": str(eval_out),
                        "summary_sha256": sha(eval_out / "summary.json"), "new_api_calls": 0}
                    final_status = "generation_and_separate_evaluation_complete"
                else:
                    generation["evaluation"] = {"status": "evaluation_failed_data_preserved",
                        "out": str(eval_out), "reason": "Unexpected evaluation receipt", "exit_code": code}
                    final_status = "evaluation_failed_data_preserved"
            else:
                generation["evaluation"] = {"status": "evaluation_failed_data_preserved",
                    "out": str(eval_out), "exit_code": code,
                    "log": str(folder / f"evaluation_round_{len(eval_dirs) + 1:04d}.log")}
                final_status = "evaluation_failed_data_preserved"
            dump(folder / "generation_receipt.json", generation)
        final = {"status": final_status, "receipt": generation,
                 "ended_at_utc": queue.now(), "evaluation_performed": False,
                 "automatic_repair_attempts": len(queue.archive(folder / "repair")[0]) if (folder / "repair").exists() else 0,
                 "automatic_retries_per_slot": 1, "automatic_process_restarts": 0}
        dump(folder / "worker_receipt.json", final)
        atomic_json(folder / "latest_receipt.json", final)
        return final
    except Exception as exc:
        final = {"status": "worker_failed_data_preserved", "error_type": type(exc).__name__,
                 "ended_at_utc": queue.now()}
        atomic_json(folder / "latest_receipt.json", final)
        raise
    finally:
        if wake is not None:
            wake.terminate()
            wake.wait()
        os.close(lock_fd)


def watch(folder, poll_seconds=10):
    folder = Path(folder)
    config, protocol = checked(folder)
    print("每10秒读取本地进度；Ctrl+C只退出观察，后台继续。", flush=True)
    try:
        while True:
            latest = folder / "latest_receipt.json"
            if latest.exists():
                result = read_json(latest)
                print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
                return result
            progress = read_json(folder / "progress.json") if (folder / "progress.json").exists() else {}
            scheduler = read_json(folder / "main_scheduler_status.json") if (folder / "main_scheduler_status.json").exists() else {}
            print(time.strftime("%H:%M:%S") + f" | {progress.get('phase', 'waiting')}"
                + f" | 主批 {progress.get('main_attempts', 0):,}/{protocol['planned_calls']:,} 回包 {progress.get('main_completed', 0):,}"
                + f" | 补批 {progress.get('repair_attempts', 0):,} 回包 {progress.get('repair_completed', 0):,}"
                + f" | 合计 ${progress.get('total_reported_cost_usd', 0):.4f} reported / "
                  f"${progress.get('total_spent_or_reserved_usd', 0):.4f} reserved of ${protocol['budget_cap_usd']:.2f}"
                + f" | in-flight {progress.get('in_flight', 0)}"
                + (f" | cooling {scheduler['cooldown_remaining_s']:.0f}s" if scheduler.get("cooldown_remaining_s", 0) else ""), flush=True)
            time.sleep(poll_seconds)
    except KeyboardInterrupt:
        print("\n已退出观察；后台执行继续。", flush=True)
        return {"status": "watch_interrupted_only"}


def run(folder, *, confirm=False, resume=False):
    if not confirm:
        raise ValueError("Review outbound scope and shared budget, then use --confirm-scope-and-budget")
    folder = Path(folder).resolve()
    if (folder / "engineering_only_replay.json").exists():
        raise ValueError("Engineering-only replay is permanently excluded from live run/resume")
    config, protocol = checked(folder)
    accounting = _accounting(folder)
    if accounting["spent_or_reserved_usd"] > protocol["budget_cap_usd"] + 1e-9:
        raise ValueError("Existing main/repair reservation exceeds the shared budget cap")
    has_attempts = bool(accounting["main_intents"] or accounting["repair_intents"])
    launches = sorted(folder.glob("launch_*/"))
    if has_attempts and not resume or not has_attempts and resume:
        raise ValueError("Use run for the first launch; use resume for an existing attempt ledger")
    if (folder / "latest_receipt.json").exists() and not has_attempts:
        raise ValueError("This Terminal run already completed; review its archived result")
    from ..news_label_trial import dotenv_values
    if not (os.environ.get("OPENROUTER_API_KEY") or dotenv_values(OFFICIAL / ".env").get("OPENROUTER_API_KEY")):
        raise ValueError("OpenRouter credential unavailable; never put it in the command line")
    if not (folder / "authorization.json").exists():
        dump(folder / "authorization.json", {"approved": True,
            "human_confirmation": "Operator explicitly invoked --confirm-scope-and-budget.",
            "user_confirmation": "--confirm-scope-and-budget", "config_sha256": sha(folder / "config.json"),
            "protocol_sha256": sha(folder / "protocol.json"),
            "prompt_scope_sha256": config["prompt_scope_sha256"],
            "destination": protocol["destination"], "model": protocol["model"], "route": protocol["route"],
            "main_max_requests": protocol["planned_calls"],
            "planned_new_api_calls": protocol["planned_new_api_calls"],
            "planned_historical_import_rows": protocol["historical_imports"]["planned_import_rows"],
            "historical_import_plan_sha256": protocol["historical_import_plan_sha256"],
            "repair_max_requests": protocol["repair"]["max_requests"],
            "maximum_physical_attempts": protocol["max_physical_attempts"],
            "shared_budget_cap_usd": protocol["budget_cap_usd"],
            "resume_policy": "never resend any registered intent, including unresolved unknown calls",
            "at_utc": queue.now()})
    checked(folder, authorized=True)
    lock_path = folder / "execution.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        number = len(list(folder.glob("launch_*"))) + 1
        launch_dir = folder / f"launch_{number:04d}"
        launch_dir.mkdir(exist_ok=False)
        dump(launch_dir / "launch_intent.json", {"operator_action": "resume" if resume else "run",
            "main_attempts_before": accounting["main"]["attempts"],
            "repair_attempts_before": accounting["repair"]["attempts"],
            "unresolved_unknown_intents": accounting["unresolved_unknown_intents"],
            "spent_or_reserved_usd": accounting["spent_or_reserved_usd"],
            "budget_cap_usd": protocol["budget_cap_usd"], "at_utc": queue.now()})
        print(f"逻辑主批 {protocol['planned_calls']:,} 个槽，其中 {protocol['historical_imports']['planned_import_rows']:,} 个历史合格答复零新增费导入，"
              f"预计新API主批 {protocol['planned_new_api_calls']:,} 次；技术失败最多补一次，"
              f"最大新API请求 {protocol['max_physical_attempts']:,} 次；"
              f"共享预算帽 ${protocol['budget_cap_usd']:.2f}，目前已计/预留 "
              f"${accounting['spent_or_reserved_usd']:.4f}。", flush=True)
        with (launch_dir / "worker.log").open("x") as log:
            child = subprocess.Popen([config["python"], "-u", str(ENTRY),
                "_worker", "--run-dir", str(folder), "--lock-fd", str(lock)], cwd=ROOT,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, pass_fds=(lock,))
        atomic_json(folder / "latest_launch.json", {"pid": child.pid, "launch_dir": str(launch_dir), "at_utc": queue.now()})
    finally:
        os.close(lock)
    return watch(folder)


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--inputs", type=Path, required=True)
    prep.add_argument("--run-dir", type=Path, required=True)
    prep.add_argument("--budget-cap-usd", type=float, required=True)
    for action in ("review", "run", "resume", "watch", "_worker"):
        command = sub.add_parser(action)
        command.add_argument("--run-dir", type=Path, required=True)
        if action in ("run", "resume"):
            command.add_argument("--confirm-scope-and-budget", action="store_true")
        if action == "_worker":
            command.add_argument("--lock-fd", type=int, required=True)
    args = parser.parse_args(argv)
    if args.action == "prepare":
        result = prepare(args.inputs, args.run_dir, args.budget_cap_usd)
    elif args.action == "review":
        result = review(args.run_dir)
    elif args.action in ("run", "resume"):
        result = run(args.run_dir, confirm=args.confirm_scope_and_budget, resume=args.action == "resume")
    elif args.action == "watch":
        result = watch(args.run_dir)
    else:
        result = _worker(args.run_dir, args.lock_fd)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
