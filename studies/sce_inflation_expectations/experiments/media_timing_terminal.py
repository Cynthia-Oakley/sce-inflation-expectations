"""Offline-first Terminal controller for the personal-date × warning 2×2.

The package is independently verified because its roster is 96 for six months
and 95 for 202206. Only new, deduplicated request slots enter the queue. Old
attempted failures remain spent and are never submitted again.
"""
from argparse import ArgumentParser
from copy import deepcopy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from .frozen_batch import ROOT, OFFICIAL, dump, read_json, sha
from .monthly_main_background import atomic_json
from .monthly_main_resilient import POLICY
from .state_continuity_execution import live_sender, reserve
from . import frozen_message_queue as queue
from ..prior_belief_experiment import message_hash

ENTRY = ROOT / "scripts/run_sce_media_timing.py"
METADATA = ROOT / "data/raw/mcp_checks/2026-10-21_v32_fullperiod_free_v1/deepseek_v32_endpoints.json"
OLD_RUN_REL = "outputs/sce_media_mechanism_terminal_20261025_v2"
EVALUATION_PACKAGE_REL = "outputs/sce_media_mechanism_v3_20261025_v1"
MONTHS = (201905, 202009, 202106, 202109, 202112, 202206, 202312)
N_BY_MONTH = {month: (95 if month == 202206 else 96) for month in MONTHS}
ARMS = ("C0", "C1", "T0", "T1")
REFERENCE_ARMS = ("O0",)
REPEATS = (1, 2)
POSITION_STATUSES = {
    "reuse_exact_success",
    "hold_old_attempted_failure",
    "new_request",
    "reuse_same_new_prompt",
}
TRUTH_REL = "evaluation_truth/cases_private.json"
LINKS_REL = "evaluation_links_private.json"
CORE_UNITS = {(m, a, r) for m in MONTHS for a in ARMS for r in REPEATS}
REQUIRED_PACKAGE_FILES = {
    "new_requests_private.json",
    "positions_private.json",
    "engineering_checks.json",
    *(f"{month}/prompts_{arm}.json" for month in MONTHS for arm in ARMS),
}


def _safe_root_path(relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe ROOT-relative path: {relative}")
    result = (ROOT / path).resolve()
    if not result.is_relative_to(ROOT.resolve()):
        raise ValueError(f"Path escapes repository root: {relative}")
    return result


def _safe_package_path(package, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe package-relative path: {relative}")
    base = Path(package).resolve()
    result = (base / path).resolve()
    if not result.is_relative_to(base):
        raise ValueError(f"Path escapes package: {relative}")
    return result


def _truth_source_path(relative, evaluation_package_rel):
    """True only for evaluation-layer files, which prepare/run must not read."""
    prefix = evaluation_package_rel.rstrip("/") + "/"
    return relative == prefix + LINKS_REL or relative == prefix + TRUTH_REL


def _digest_map(value, label):
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} hash map is missing")
    result = {}
    for relative, digest in value.items():
        if not isinstance(relative, str) or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"Malformed {label} hash entry")
        if any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"Malformed {label} SHA-256: {relative}")
        result[relative] = digest
    return result


def _validate_protocol(protocol):
    if protocol.get("mechanism") != "v32_media_timing":
        raise ValueError("Only the registered v32_media_timing mechanism is supported")
    if protocol.get("months") != list(MONTHS):
        raise ValueError("Protocol months differ from the seven-month frozen window")
    if protocol.get("n_by_month") != {str(m): n for m, n in N_BY_MONTH.items()} and protocol.get("n_by_month") != N_BY_MONTH:
        raise ValueError("Protocol roster must be 96 per month except 95 in 202206")
    if protocol.get("arms") != list(ARMS) or protocol.get("reference_arms") != list(REFERENCE_ARMS):
        raise ValueError("Protocol must contain C0/C1/T0/T1 and reference arm O0")
    if protocol.get("generation_repeats") != list(REPEATS):
        raise ValueError("Protocol generation repeats must be [1, 2]")
    if protocol.get("old_run") != OLD_RUN_REL:
        raise ValueError("The archived V3 terminal run must be the registered old_run")
    if protocol.get("evaluation_package") != EVALUATION_PACKAGE_REL:
        raise ValueError("The evaluation package must be the registered V3 package")
    fixed = {
        "destination": "https://openrouter.ai/api/v1",
        "model": "deepseek/deepseek-v3.2",
        "route": "siliconflow/fp8",
        "expected_provider": "SiliconFlow",
        "temperature": 0.5,
        "thinking": "disabled",
        "response_format": "json_object",
        "max_tokens": 1024,
        "timeout_s": 120,
        "retry_max": 0,
        "provider_fallback": False,
        "price_input_per_mtok": 0.259,
        "price_output_per_mtok": 0.8,
        "provider_metadata": str(METADATA.relative_to(ROOT)),
    }
    for key, expected in fixed.items():
        if protocol.get(key) != expected:
            raise ValueError(f"Protocol locked setting differs: {key}")
    extra = protocol.get("request_extra_body")
    expected_extra = {
        "provider": {"order": ["siliconflow/fp8"], "allow_fallbacks": False,
                     "require_parameters": True,
                     "max_price": {"prompt": 0.259, "completion": 0.8}},
        "reasoning": {"enabled": False},
    }
    if extra != expected_extra:
        raise ValueError("Protocol provider/reasoning request body differs from frozen V3")
    cap = protocol.get("budget_cap_usd")
    if isinstance(cap, bool) or not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap <= 0:
        raise ValueError("A positive finite budget_cap_usd is required")
    planned = protocol.get("planned_calls")
    if isinstance(planned, bool) or not isinstance(planned, int) or planned < 32:
        raise ValueError("planned_calls must be the unique new request count and at least 32")
    if (isinstance(protocol.get("max_prompt_chars"), bool)
            or not isinstance(protocol.get("max_prompt_chars"), int)
            or protocol["max_prompt_chars"] <= 0):
        raise ValueError("A positive max_prompt_chars cap is required")


def _load_manifest(package):
    package = Path(package).resolve()
    outputs = (ROOT / "outputs").resolve()
    if not package.is_relative_to(outputs) or not package.is_dir():
        raise ValueError("Package must be an existing ignored directory under outputs/")
    manifest = read_json(package / "manifest.json")
    protocol = read_json(package / "protocol.json")
    _validate_protocol(protocol)
    if manifest.get("protocol_sha256") != sha(package / "protocol.json"):
        raise ValueError("Package protocol hash mismatch")
    if manifest.get("planned_calls", protocol["planned_calls"]) != protocol["planned_calls"]:
        raise ValueError("Manifest planned_calls differs from protocol")
    prepared = _digest_map(manifest.get("prepared_file_sha256"), "prepared_file_sha256")
    source = _digest_map(manifest.get("source_sha256"), "source_sha256")
    if any(relative.endswith(TRUTH_REL) or relative.endswith(LINKS_REL) for relative in prepared):
        raise ValueError("Target truth and links must stay in the evaluation package")
    missing = REQUIRED_PACKAGE_FILES - set(prepared)
    if missing:
        raise ValueError(f"Prepared manifest omits required files: {sorted(missing)}")
    for relative, expected in prepared.items():
        path = _safe_package_path(package, relative)
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f"Prepared package file hash mismatch: {relative}")
    evaluation_rel = protocol["evaluation_package"]
    for relative, expected in source.items():
        if _truth_source_path(relative, evaluation_rel):
            continue  # Target rows are only opened by the separate evaluator.
        path = _safe_root_path(relative)
        if not path.is_file() or sha(path) != expected:
            raise ValueError(f"Prepared source hash mismatch: {relative}")
    if source.get(str(METADATA.relative_to(ROOT))) != sha(METADATA):
        raise ValueError("The fixed V3 provider metadata must be source-pinned")
    return package, manifest, protocol, prepared, source


def _old_archive(protocol):
    old_rel = protocol["old_run"]
    old = _safe_root_path(old_rel)
    if not old.is_dir():
        raise ValueError("Registered V3 terminal archive is missing")
    old_config = read_json(old / "config.json")
    if old_config.get("package") != str(_safe_root_path(EVALUATION_PACKAGE_REL)):
        raise ValueError("Old terminal archive is attached to a different V3 package")
    if old_config.get("planned_calls") != 6720:
        raise ValueError("Old terminal archive does not match the complete V3 request grid")
    auth = read_json(old / "authorization.json")
    if auth.get("config_sha256") != sha(old / "config.json"):
        raise ValueError("Old V3 terminal configuration authorization hash mismatch")
    slots = read_json(old / "slot_index_private.json")
    slot_by_key = {s.get("key"): s for s in slots}
    if len(slot_by_key) != 6720 or None in slot_by_key:
        raise ValueError("Old V3 slot index is incomplete or duplicated")
    intents, replies = queue.archive(old)
    intent_by_key = {r["key"]: r for r in intents}
    reply_by_key = {r["key"]: r for r in replies}
    if len(intent_by_key) != len(intents) or set(intent_by_key) != set(reply_by_key) and not set(reply_by_key) <= set(intent_by_key):
        raise ValueError("Old V3 archive contains duplicate or unregistered attempts")
    if set(intent_by_key) != set(slot_by_key):
        raise ValueError("Old V3 archive does not contain one archived attempt per frozen slot")
    for key, intent in intent_by_key.items():
        slot = slot_by_key[key]
        if (intent.get("prompt_sha256") != slot.get("prompt_sha256")
                or intent.get("reserved_usd") != slot.get("reserved_usd")):
            raise ValueError("Old V3 archive intent differs from its frozen slot index")
    if queue.account(intents, replies)["attempts"] != 6720:
        raise ValueError("Old V3 archive attempt count is incomplete")
    return old, slots, intent_by_key, reply_by_key


def _validate_engineering(package, manifest, protocol):
    checks = read_json(package / "engineering_checks.json")
    if not isinstance(checks, list) or len(checks) != len(CORE_UNITS):
        raise ValueError("All 56 official Core offline units are required")
    seen = set()
    source_hashes = manifest["source_sha256"]
    for check in checks:
        key = (check.get("month"), check.get("arm"), check.get("repeat"))
        if key not in CORE_UNITS or key in seen:
            raise ValueError("Engineering checks have a duplicate or unknown unit")
        seen.add(key)
        n = N_BY_MONTH[key[0]]
        if check.get("n") != n or type(check.get("exit_code")) is not int or check["exit_code"] != 0:
            raise ValueError("Core check exit code or roster size differs")
        if not isinstance(check.get("run_id"), str) or not check["run_id"]:
            raise ValueError("Engineering run_id is required")
        relative = check.get("receipt_file")
        if not isinstance(relative, str):
            raise ValueError("Engineering receipt_file must be ROOT-relative")
        receipt_path = _safe_root_path(relative)
        if source_hashes.get(relative) != check.get("receipt_sha256"):
            raise ValueError("Engineering receipt must be source-pinned by the package manifest")
        if not receipt_path.is_file() or sha(receipt_path) != check["receipt_sha256"]:
            raise ValueError("Engineering receipt hash mismatch")
        receipt = read_json(receipt_path)
        cost = receipt.get("cost") or {}
        if (receipt.get("run_id") not in (check["run_id"], check["run_id"] + "-engineering")
                or receipt.get("month") != key[0]
                or receipt.get("arm") != key[1] or receipt.get("repeat") != key[2]
                or receipt.get("n") != n or receipt.get("status") != "completed"
                or receipt.get("llm_kind") != "scripted" or cost.get("call_count") != 0
                or receipt.get("actual_input_hashes_match") is not True
                or receipt.get("protocol_sha256") != check.get("protocol_sha256")):
            raise ValueError("Official Core receipt does not satisfy the offline acceptance contract")
    if seen != CORE_UNITS:
        raise ValueError("Engineering checks do not cover every month × arm × repeat")
    return checks


def _load_prompts(package, protocol):
    prompts = {}
    for month in MONTHS:
        month_rows = {}
        for arm in ARMS:
            relative = f"{month}/prompts_{arm}.json"
            bundle = read_json(_safe_package_path(package, relative))
            rows = bundle.get("rows") if isinstance(bundle, dict) else None
            if not isinstance(rows, dict):
                raise ValueError(f"Prompt bundle has no rows map: {relative}")
            if len(rows) != N_BY_MONTH[month]:
                raise ValueError(f"Prompt roster size differs: {relative}")
            for aid, row in rows.items():
                messages, digest = row.get("messages"), row.get("prompt_sha256")
                if not isinstance(messages, list) or message_hash(messages) != digest:
                    raise ValueError(f"Prompt hash mismatch: {relative}/{aid}")
                month_rows[arm, str(aid)] = (messages, digest)
        arm_rosters = [{aid for a, aid in month_rows if a == arm} for arm in ARMS]
        if any(roster != arm_rosters[0] for roster in arm_rosters[1:]):
            raise ValueError(f"Four prompt arms do not share a roster in {month}")
        prompts[month] = month_rows
    return prompts


def _validate_slots(raw_slots, protocol, prompts, old_slots):
    if not isinstance(raw_slots, list):
        raise ValueError("new_requests_private.json must contain the complete slot list")
    slots, by_key, prompt_signatures = [], {}, set()
    for raw in raw_slots:
        if not isinstance(raw, dict):
            raise ValueError("New request slots must be objects")
        required = ("key", "month", "arm", "repeat", "agent_id", "prompt_sha256", "messages", "reserved_usd")
        if any(k not in raw for k in required):
            raise ValueError("New request slot lacks a standard queue field")
        month, arm, repeat, aid = raw["month"], raw["arm"], raw["repeat"], str(raw["agent_id"])
        key = f"{month}|{arm}|{repeat}|{aid}"
        if raw["key"] != key or month not in MONTHS or arm not in ARMS or repeat not in REPEATS:
            raise ValueError("New request key is not the standard month|arm|repeat|agent_id key")
        if (arm, aid) not in prompts[month]:
            raise ValueError(f"New request is outside its prepared prompt roster: {key}")
        messages, digest = raw["messages"], raw["prompt_sha256"]
        if not isinstance(messages, list) or message_hash(messages) != digest:
            raise ValueError(f"New request prompt hash mismatch: {key}")
        if len(messages) != 1 or not isinstance(messages[0].get("content"), str):
            raise ValueError(f"Frozen prompt must retain one user message: {key}")
        if len(messages[0]["content"]) > protocol["max_prompt_chars"]:
            raise ValueError(f"New request exceeds max_prompt_chars: {key}")
        byte_count = len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))
        reserved = raw["reserved_usd"]
        if (isinstance(reserved, bool) or not isinstance(reserved, (int, float))
                or not math.isfinite(reserved)
                or abs(float(reserved) - reserve(protocol, byte_count)) > 1e-12):
            raise ValueError(f"New request reservation differs from the frozen pricing rule: {key}")
        if prompts[month][arm, aid] != (messages, digest):
            raise ValueError(f"New request does not match its prompt bundle: {key}")
        if key in by_key:
            raise ValueError(f"Duplicate new request key: {key}")
        if (repeat, digest) in prompt_signatures:
            raise ValueError("Duplicate same-repeat request was not deduplicated into one prompt slot")
        if any(s.get("repeat") == repeat and s.get("prompt_sha256") == digest for s in old_slots):
            raise ValueError("Previously attempted exact prompt must be reused or held, never requested again")
        prompt_signatures.add((repeat, digest))
        slot = dict(raw)
        slots.append(slot)
        by_key[key] = slot
    if len(slots) != protocol["planned_calls"]:
        raise ValueError("planned_calls must equal the unique new request slot count")
    import hashlib as _hashlib
    slots.sort(key=lambda s: _hashlib.sha256(("media_timing_terminal_v1|" + s["key"]).encode()).digest())
    return slots, by_key


def _validate_positions(raw_positions, protocol, prompts, new_slots, old_slots, old_intents, old_replies):
    if not isinstance(raw_positions, list):
        raise ValueError("positions_private.json must contain the complete logical position list")
    old_slot_by_key = {s["key"]: s for s in old_slots}
    expected = {(m, a, r, aid) for m in MONTHS for a in (*REFERENCE_ARMS, *ARMS)
                for r in REPEATS for aid in (
                    sorted({aid for arm, aid in prompts[m] if arm == ARMS[0]}))}
    mapped, refs = {}, {key: [] for key in new_slots}
    new_primaries = {key: 0 for key in new_slots}
    for pos in raw_positions:
        if not isinstance(pos, dict):
            raise ValueError("Logical position must be an object")
        month, arm, repeat, aid = pos.get("month"), pos.get("arm"), pos.get("repeat"), str(pos.get("agent_id"))
        key = (month, arm, repeat, aid)
        if key not in expected or key in mapped:
            raise ValueError("Logical positions contain an unknown or duplicate row")
        digest = pos.get("prompt_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("Logical position prompt_sha256 is malformed")
        status = pos.get("status")
        if status not in POSITION_STATUSES:
            raise ValueError(f"Unknown logical position status: {status}")
        if arm in ARMS and digest != prompts[month][arm, aid][1]:
            raise ValueError(f"Position prompt hash differs from the arm bundle: {key}")
        if arm == "O0":
            expected_old_key = f"{month}|Q3|{repeat}|{aid}"
            old_slot = old_slot_by_key.get(expected_old_key)
            if old_slot is None or old_slot.get("prompt_sha256") != digest:
                raise ValueError(f"O0 must map the exact archived V3 Q3 prompt: {key}")
        if status in ("reuse_exact_success", "hold_old_attempted_failure"):
            if "source_key" not in pos or "new_request_key" in pos:
                raise ValueError("Old-position status requires source_key only")
            source_key = pos["source_key"]
            intent, source = old_intents.get(source_key), old_slot_by_key.get(source_key)
            if intent is None or source is None or intent.get("prompt_sha256") != digest:
                raise ValueError(f"Old position source does not have the exact prompt hash: {key}")
            if arm == "O0" and source_key != expected_old_key:
                raise ValueError("O0 must source the original month/person/repeat Q3 request")
            reply = old_replies.get(source_key)
            is_success = bool(reply and not reply.get("error") and reply.get("finish_reason") == "stop"
                               and all(queue.fields(reply).values()))
            if status == "reuse_exact_success" and not is_success:
                raise ValueError("reuse_exact_success points to an unsuccessful or invalid old reply")
            if status == "hold_old_attempted_failure" and is_success:
                raise ValueError("A fully valid old success must be classified as reuse_exact_success")
        else:
            if "new_request_key" not in pos or "source_key" in pos:
                raise ValueError("New-position status requires new_request_key only")
            request_key = pos["new_request_key"]
            slot = new_slots.get(request_key)
            if slot is None or slot.get("prompt_sha256") != digest:
                raise ValueError(f"New position does not map to the exact frozen request: {key}")
            fields = request_key.split("|")
            if (len(fields) != 4 or int(fields[0]) != month or int(fields[2]) != repeat
                    or fields[3] != aid or fields[1] not in ARMS):
                raise ValueError("New request key does not identify the same month/repeat/respondent")
            if status == "new_request":
                if (slot["month"], slot["arm"], slot["repeat"], str(slot["agent_id"])) != key:
                    raise ValueError("new_request primary position must match its slot key")
                new_primaries[request_key] += 1
            refs[request_key].append((key, status))
        mapped[key] = pos
    if set(mapped) != expected:
        raise ValueError(f"Logical position grid is incomplete: expected {len(expected)}, got {len(mapped)}")
    if any(count != 1 for count in new_primaries.values()):
        raise ValueError("Each new request must have exactly one new_request primary position")
    for request_key, aliases in refs.items():
        primary = next(row for row in raw_positions if row.get("status") == "new_request"
                       and row.get("new_request_key") == request_key)
        primary_hash = primary["prompt_sha256"]
        if any(row["prompt_sha256"] != primary_hash for row in raw_positions
               if row.get("new_request_key") == request_key):
            raise ValueError("reuse_same_new_prompt alias does not match its primary prompt")
    return mapped


def _old_archive_pin_paths(old_run):
    paths = [old_run / "config.json", old_run / "authorization.json", old_run / "slot_index_private.json"]
    for segment in sorted(old_run.glob("round_*/segment_*")):
        manifest_path = segment / "manifest.json"
        if not manifest_path.is_file():
            continue
        paths.append(manifest_path)
        manifest = read_json(manifest_path)
        for name in manifest.get("files_sha256", {}):
            paths.append(_safe_package_path(segment, name))
    return paths


def _package_context(package, *, check_engineering=True):
    package, manifest, protocol, prepared, source = _load_manifest(package)
    old_run, old_slots, old_intents, old_replies = _old_archive(protocol)
    prompts = _load_prompts(package, protocol)
    raw_slots = read_json(package / "new_requests_private.json")
    slots, slot_by_key = _validate_slots(raw_slots, protocol, prompts, old_slots)
    raw_positions = read_json(package / "positions_private.json")
    positions = _validate_positions(raw_positions, protocol, prompts, slot_by_key, old_slots, old_intents, old_replies)
    if check_engineering:
        _validate_engineering(package, manifest, protocol)
    return dict(package=package, manifest=manifest, protocol=protocol, prepared=prepared, source=source,
                old_run=old_run, old_slots=old_slots, old_intents=old_intents, old_replies=old_replies,
                prompts=prompts, slots=slots, slot_by_key=slot_by_key, positions=positions)


def _runtime_source_paths():
    base = ROOT / "studies/sce_inflation_expectations"
    paths = [
        ENTRY,
        Path(__file__),
        Path(queue.__file__),
        ROOT / "studies/sce_inflation_expectations/experiments/frozen_batch.py",
        ROOT / "studies/sce_inflation_expectations/experiments/monthly_main_resilient.py",
        ROOT / "studies/sce_inflation_expectations/experiments/monthly_main_background.py",
        ROOT / "studies/sce_inflation_expectations/experiments/state_continuity_execution.py",
        ROOT / "studies/sce_inflation_expectations/experiments/media_timing_inputs.py",
        ROOT / "studies/sce_inflation_expectations/evaluation/media_timing.py",
        ROOT / "studies/sce_inflation_expectations/evaluation/media_mechanism_terminal.py",
        ROOT / "studies/sce_inflation_expectations/evaluation/cognition.py",
        ROOT / "studies/sce_inflation_expectations/evaluation/metrics.py",
        ROOT / "studies/sce_inflation_expectations/q9_normalization.py",
        ROOT / "studies/sce_inflation_expectations/model_counterfactual.py",
        ROOT / "studies/sce_inflation_expectations/model.py",
        ROOT / "studies/sce_inflation_expectations/prior_belief_experiment.py",
        ROOT / "studies/sce_inflation_expectations/scoring/sce_q9_frozen.py",
        ROOT / "studies/sce_inflation_expectations/scoring/beta_fit_kernel.py",
        ROOT / "studies/sce_inflation_expectations/news_label_trial.py",
        METADATA,
    ]
    return [path for path in paths if path.is_file()]


def _merge_pin(pins, relative, digest):
    old = pins.get(relative)
    if old is not None and old != digest:
        raise ValueError(f"Conflicting source pin: {relative}")
    pins[relative] = digest


def _output_pin_map(ctx):
    pins = {}
    for relative, digest in ctx["source"].items():
        if not _truth_source_path(relative, ctx["protocol"]["evaluation_package"]):
            _merge_pin(pins, relative, digest)
    for relative, digest in ctx["prepared"].items():
        path = _safe_package_path(ctx["package"], relative)
        _merge_pin(pins, str(path.relative_to(ROOT)), digest)
    _merge_pin(pins, str((ctx["package"] / "protocol.json").relative_to(ROOT)), sha(ctx["package"] / "protocol.json"))
    _merge_pin(pins, str((ctx["package"] / "manifest.json").relative_to(ROOT)), sha(ctx["package"] / "manifest.json"))
    eval_manifest = _safe_root_path(ctx["protocol"]["evaluation_package"]) / "manifest.json"
    if not eval_manifest.is_file():
        raise ValueError("Registered evaluation package manifest is missing")
    _merge_pin(pins, str(eval_manifest.relative_to(ROOT)), sha(eval_manifest))
    for path in _old_archive_pin_paths(ctx["old_run"]):
        if path.is_file():
            _merge_pin(pins, str(path.resolve().relative_to(ROOT)), sha(path))
    for path in _runtime_source_paths():
        _merge_pin(pins, str(path.resolve().relative_to(ROOT)), sha(path))
    return pins


def prepare(package, out):
    ctx = _package_context(package, check_engineering=True)
    p = ctx["protocol"]
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to((ROOT / "outputs").resolve()):
        raise ValueError("Fresh ignored Terminal directory under outputs/ required")
    policy = deepcopy(POLICY)
    policy.update(initial_workers=32, max_workers=64, min_workers=8, scale_up_after_completed=256,
                  max_total_recoveries=15, max_unhealthy_recoveries=5,
                  max_total_cooldown_seconds=1800)
    policy.update({
        "technical_gate": {
            "initial_attempts": 32, "minimum_normal_returns": 16,
            "minimum_format_ratio": 0.95, "maximum_probe_attempts": 32,
            "probe_only_when_normal_returns_below_minimum": True,
            "normal_return": "error is null and finish_reason is stop",
            "format_valid": "both Q8 and Q9 parse under the frozen response reader",
            "transport_failures_excluded_from_format_denominator": True,
        },
        "repair": {
            "eligible_failures": ["transport", "non_stop_finish_reason", "q8_format", "q9_format"],
            "max_attempts_per_main_slot": 1, "maximum_requests": p["planned_calls"],
            "initial_workers": 16, "max_workers": 32, "scale_up_after_completed": 32,
            "preserve_successful_fields": True, "repair_old_attempted_failures": False,
            "repair_by_score_or_truth": False,
        },
        "shared_budget_mode": "main_plus_repair_spent_plus_inflight_reservation",
        "maximum_physical_attempts": 2 * p["planned_calls"],
        "total_cooldown_and_recoveries_are_bounded": True,
    })
    out.mkdir(parents=True, mode=0o700)
    dump(out / "execution_policy.json", policy)
    index = [{k: v for k, v in slot.items() if k != "messages"} for slot in ctx["slots"]]
    dump(out / "slot_index_private.json", index)
    pins = _output_pin_map(ctx)
    _merge_pin(pins, str((out / "execution_policy.json").relative_to(ROOT)), sha(out / "execution_policy.json"))
    _merge_pin(pins, str((out / "slot_index_private.json").relative_to(ROOT)), sha(out / "slot_index_private.json"))
    p = ctx["protocol"]
    total_reserve = sum(float(slot["reserved_usd"]) for slot in ctx["slots"])
    dump(out / "config.json", {
        "schema": "sce_media_timing_terminal_config/v1",
        "package": str(ctx["package"]),
        "run_dir": str(out),
        "python": sys.executable,
        "protocol_sha256": sha(ctx["package"] / "protocol.json"),
        "manifest_sha256": sha(ctx["package"] / "manifest.json"),
        "prepared_at_utc": queue.now(),
        "planned_calls": p["planned_calls"],
        "budget_cap_usd": p["budget_cap_usd"],
        "estimated_reserved_usd": total_reserve,
        "destination": p["destination"],
        "model": p["model"],
        "route": p["route"],
        "old_run": p["old_run"],
        "evaluation_package": p["evaluation_package"],
        "maximum_main_attempts": p["planned_calls"],
        "maximum_repair_attempts": p["planned_calls"],
        "maximum_physical_attempts": 2 * p["planned_calls"],
        "automatic_retries_per_failed_new_slot": 1,
        "old_attempted_failures_repaired": False,
        "provider_fallbacks": 0,
        "source_sha256": pins,
        "truth_opened_during_prepare": False,
        "new_api_calls": 0,
    })
    shutil.copyfile(Path(queue.__file__), out / "frozen_message_queue.py")
    shutil.copyfile(Path(__file__), out / "media_timing_terminal.py")
    return review(out)


def checked(folder, authorized=False):
    folder = Path(folder).resolve()
    outputs = (ROOT / "outputs").resolve()
    if not folder.is_relative_to(outputs):
        raise ValueError("Terminal run directory must be under outputs/")
    c = read_json(folder / "config.json")
    for relative, digest in _digest_map(c.get("source_sha256"), "runtime source").items():
        path = _safe_root_path(relative)
        if not path.is_file() or sha(path) != digest:
            raise ValueError("Frozen source/input changed: " + relative)
    package = Path(c["package"]).resolve()
    ctx = _package_context(package, check_engineering=True)
    if (sha(package / "protocol.json") != c["protocol_sha256"]
            or sha(package / "manifest.json") != c["manifest_sha256"]
            or str(ctx["old_run"].relative_to(ROOT)) != c["old_run"]
            or ctx["protocol"]["evaluation_package"] != c["evaluation_package"]):
        raise ValueError("Frozen package/configuration changed")
    p = dict(ctx["protocol"], budget_mode="spent_plus_inflight_reservation")
    if authorized:
        auth = read_json(folder / "authorization.json")
        if (auth.get("approved") is not True or auth.get("config_sha256") != sha(folder / "config.json")
                or auth.get("user_confirmation") != "--confirm-scope-and-budget"):
            raise ValueError("Exact terminal authorization required")
    return c, p


def _load_frozen_slots(folder, p):
    c = read_json(Path(folder) / "config.json")
    ctx = _package_context(Path(c["package"]), check_engineering=True)
    if len(ctx["slots"]) != p["planned_calls"]:
        raise ValueError("Frozen new-request slot count differs from config")
    return ctx["slots"], ctx


def _normal_return(row):
    return row.get("error") is None and row.get("finish_reason") == "stop"


def technical_gate_result(rows, *, minimum_normal=16, minimum_format_ratio=0.95):
    """Evaluate transport and formatting separately; transport errors do not dilute format quality."""
    normal = [row for row in rows if _normal_return(row)]
    valid = sum(all(queue.fields(row).values()) for row in normal)
    ratio = valid / len(normal) if normal else None
    passed = len(normal) >= minimum_normal and ratio is not None and ratio >= minimum_format_ratio
    if len(normal) < minimum_normal:
        reason = "insufficient_normal_returns"
    elif not passed:
        reason = "format_ratio_below_threshold"
    else:
        reason = None
    return {"attempted": len(rows), "normal_returns": len(normal), "format_usable": valid,
            "format_ratio": ratio, "minimum_normal_returns": minimum_normal,
            "minimum_format_ratio": minimum_format_ratio, "passed": passed, "reason": reason}


def _failed_new_fields(row, policy):
    """Technical failures only; hard provider/account failures are never auto-repaired."""
    if row.get("error"):
        if row.get("fatal") and not queue.recoverable(row, policy):
            raise ValueError("Hard main failure cannot enter automatic repair")
        if not queue.recoverable(row, policy):
            raise ValueError("Nonrecoverable main error cannot enter automatic repair")
        return ["q8", "q9"]
    if row.get("finish_reason") != "stop":
        return ["q8", "q9"]
    return [field for field, valid in queue.fields(row).items() if not valid]


def _repair_targets(main_replies, slot_by_key, policy):
    """Only failed fields of new request slots qualify; old held failures are absent by construction."""
    by_key = {row.get("key"): row for row in main_replies}
    if len(by_key) != len(main_replies) or not set(by_key) <= set(slot_by_key):
        raise ValueError("Main replies contain duplicate or non-new-request keys")
    targets = {}
    for key, row in by_key.items():
        fields = _failed_new_fields(row, policy)
        if fields:
            targets[key] = {"key": key, "prompt_sha256": slot_by_key[key]["prompt_sha256"],
                            "fields": fields, "main_error": row.get("error"),
                            "main_finish_reason": row.get("finish_reason")}
    return targets


def _repair_slot(slot):
    row = dict(slot)
    row["key"] = "repair1|" + slot["key"]
    return row


def _repair_target_key(repair_key):
    prefix = "repair1|"
    if not isinstance(repair_key, str) or not repair_key.startswith(prefix):
        raise ValueError("Repair key lacks its distinct one-time repair namespace")
    return repair_key[len(prefix):]


def _validate_repair_ledger_shape(intents, replies, slot_by_key, main_replies, p):
    intent_by_key = {row.get("key"): row for row in intents}
    reply_by_key = {row.get("key"): row for row in replies}
    if len(intent_by_key) != len(intents) or len(reply_by_key) != len(replies):
        raise ValueError("Repair ledger contains duplicate keys")
    if len(intents) > p["planned_calls"]:
        raise ValueError("Repair attempts exceed the once-per-new-slot scope")
    if not set(reply_by_key) <= set(intent_by_key):
        raise ValueError("Repair replies contain an unregistered attempt")
    targets = _repair_targets(main_replies, slot_by_key, POLICY)
    if not set(intent_by_key) <= {"repair1|" + key for key in targets}:
        raise ValueError("Repair ledger includes an old failure, successful field, or out-of-scope key")
    for repair_key, intent in intent_by_key.items():
        target_key = _repair_target_key(repair_key)
        slot = slot_by_key[target_key]
        if (intent.get("prompt_sha256") != slot.get("prompt_sha256")
                or intent.get("reserved_usd") != slot.get("reserved_usd")):
            raise ValueError("Repair intent changed the original prompt hash or reservation")
    for repair_key, row in reply_by_key.items():
        if row.get("prompt_sha256") != intent_by_key[repair_key].get("prompt_sha256"):
            raise ValueError("Repair response prompt hash differs from its intent")
        if row.get("error") is None and (row.get("returned_model") != p["model"]
                                           or row.get("returned_provider") != p["expected_provider"]):
            raise ValueError("Repair response differs from the locked model/provider")
    return targets, intent_by_key, reply_by_key


def _account_both(main_intents, main_replies, repair_intents, repair_replies):
    main = queue.account(main_intents, main_replies)
    repair = queue.account(repair_intents, repair_replies)
    return {"main": main, "repair": repair,
            "total_reported_cost_usd": main["reported_cost_usd"] + repair["reported_cost_usd"],
            "total_spent_or_reserved_usd": main["spent_or_reserved_usd"] + repair["spent_or_reserved_usd"]}


def _cool_after_recoverable(folder, sender, rows, receipt, policy, *, cool, stage):
    hard = [row for row in rows if row.get("error") and not queue.recoverable(row, policy)]
    if hard:
        return False, "hard_provider_or_account_error"
    recoverable = [row for row in rows if row.get("error") and queue.recoverable(row, policy)]
    reason = receipt.get("halt_reason")
    if reason and (not recoverable or reason in ("Budget cap reached before dispatch", "Budget guard")):
        return False, reason
    if not recoverable:
        return True, None
    status_path = Path(folder) / f"{stage}_scheduler_status.json"
    prior = read_json(status_path) if status_path.exists() else {}
    recoveries = int(prior.get("recovery_cycles", 0))
    cooldown_s = float(prior.get("total_cooldown_seconds", 0.0))
    healthy = sum(not row.get("error") for row in rows)
    healthy_ratio = healthy / len(rows) if rows else 0.0
    previous_unhealthy = int(prior.get("unhealthy_recoveries", 0))
    if (healthy >= policy["healthy_segment_min_successes"]
            and healthy_ratio >= policy["healthy_segment_min_ratio"]):
        previous_unhealthy = 0
    unhealthy = previous_unhealthy + 1
    if recoveries >= policy["max_total_recoveries"] or unhealthy > policy["max_unhealthy_recoveries"]:
        return False, "bounded_recovery_limit_reached"
    delay_index = min(unhealthy - 1, len(policy["cooldown_seconds"]) - 1)
    delay = max(float(policy["cooldown_seconds"][delay_index]), float(getattr(sender, "retry_after_s", 0.0)))
    if cooldown_s + delay > policy["max_total_cooldown_seconds"]:
        return False, "cooldown_cap_reached"
    new_status = {"phase": stage + "_cooldown", "recovery_cycles": recoveries + 1,
                  "unhealthy_recoveries": unhealthy, "total_cooldown_seconds": cooldown_s + delay,
                  "last_error": reason or recoverable[-1].get("error"), "cooldown_remaining_s": delay,
                  "at_utc": queue.now()}
    atomic_json(status_path, new_status)
    cool(delay, status_path, new_status)
    atomic_json(status_path, dict(new_status, phase=stage + "_ready", cooldown_remaining_s=0,
                                  at_utc=queue.now()))
    return True, None


def _main_gate(intents, replies, policy):
    keys = [row["key"] for row in intents]
    gate_keys = keys[:policy["technical_gate"]["initial_attempts"]]
    by_reply = {row["key"]: row for row in replies}
    gate_rows = [by_reply[key] for key in gate_keys if key in by_reply]
    if len(gate_keys) >= policy["technical_gate"]["initial_attempts"]:
        # If the first 32 had fewer than 16 normal returns, use only fresh probe rows
        # until 16 normal returns have been observed; never dispatch a prior key again.
        gate_result = technical_gate_result(gate_rows,
            minimum_normal=policy["technical_gate"]["minimum_normal_returns"],
            minimum_format_ratio=policy["technical_gate"]["minimum_format_ratio"])
        for key in keys[len(gate_keys):len(gate_keys) + policy["technical_gate"]["maximum_probe_attempts"]]:
            if gate_result["normal_returns"] >= policy["technical_gate"]["minimum_normal_returns"]:
                break
            if key in by_reply:
                gate_rows.append(by_reply[key])
                gate_result = technical_gate_result(gate_rows,
                    minimum_normal=policy["technical_gate"]["minimum_normal_returns"],
                    minimum_format_ratio=policy["technical_gate"]["minimum_format_ratio"])
    else:
        gate_result = technical_gate_result(gate_rows,
            minimum_normal=policy["technical_gate"]["minimum_normal_returns"],
            minimum_format_ratio=policy["technical_gate"]["minimum_format_ratio"])
    gate_result["probe_attempts"] = max(0, len(gate_rows) - policy["technical_gate"]["initial_attempts"])
    return gate_result


def run_main_segments(p, slots, folder, round_dir, send, policy, *, publish=lambda _value: None,
                      engineering_only=False, cool=queue.cooldown):
    """Main queue with 8-worker gate, transport-aware 32/16 gate, then 32→64 workers."""
    folder, round_dir = Path(folder), Path(round_dir)
    sender = queue.safe_sender(send)
    slot_by_key = {slot["key"]: slot for slot in slots}
    if len(slot_by_key) != len(slots):
        raise ValueError("Main slot keys must be unique")
    while True:
        intents, replies = queue.archive(folder)
        intent_by_key = {row["key"]: row for row in intents}
        reply_by_key = {row["key"]: row for row in replies}
        if len(intent_by_key) != len(intents) or not set(intent_by_key) <= set(slot_by_key):
            raise ValueError("Main archive has duplicate or out-of-scope attempts")
        for row in intents:
            slot = slot_by_key[row["key"]]
            if row.get("prompt_sha256") != slot["prompt_sha256"] or row.get("reserved_usd") != slot["reserved_usd"]:
                raise ValueError("Main archive differs from the frozen slot")
        gate = _main_gate(intents, replies, policy)
        gate_calls = policy["technical_gate"]["initial_attempts"]
        gate_attempts = min(len(intents), gate_calls + policy["technical_gate"]["maximum_probe_attempts"])
        gate_ready = len(intents) >= gate_calls and gate["normal_returns"] >= policy["technical_gate"]["minimum_normal_returns"]
        if gate_ready and not gate["passed"]:
            result = {"status": "stopped_technical_gate", "halt_reason": gate["reason"],
                      "technical_gate": gate, **queue.account(intents, replies)}
            dump(round_dir / "main_receipt.json", result)
            return result
        if gate_ready:
            atomic_json(Path(folder) / "technical_gate.json", gate)
        if len(intents) >= gate_calls and not gate_ready and gate_attempts >= gate_calls + policy["technical_gate"]["maximum_probe_attempts"]:
            result = {"status": "stopped_technical_gate", "halt_reason": "insufficient_normal_returns_after_bounded_probes",
                      "technical_gate": gate, **queue.account(intents, replies)}
            dump(round_dir / "main_receipt.json", result)
            return result
        attempted = set(intent_by_key)
        pending = [slot for slot in slots if slot["key"] not in attempted]
        if gate_ready and gate["passed"] and not pending:
            if set(reply_by_key) != attempted:
                result = {"status": "main_incomplete_unresolved_intent", "technical_gate": gate,
                          **queue.account(intents, replies)}
                dump(round_dir / "main_receipt.json", result)
                return result
            result = {"status": "completed", "technical_gate": gate,
                      "actual_model_results": not engineering_only, **queue.account(intents, replies)}
            dump(round_dir / "main_receipt.json", result)
            return result
        if not pending:
            result = {"status": "stopped_main_incomplete", "technical_gate": gate,
                      **queue.account(intents, replies)}
            dump(round_dir / "main_receipt.json", result)
            return result
        if len(intents) < gate_calls:
            batch_size = min(gate_calls - len(intents), len(pending))
            workers = max_workers = 8
            scale_after = gate_calls + 1
        elif not gate_ready:
            batch_size = 1
            workers = max_workers = 8
            scale_after = gate_calls + 1
        else:
            batch_size = len(pending)
            workers, max_workers = 32, 64
            scale_after = policy["scale_up_after_completed"]
        selected = pending[:batch_size]
        segments = sorted(round_dir.glob("segment_*"))
        segment_dir = round_dir / f"segment_{len(segments) + 1:04d}"
        sender.retry_after_s = 0.0
        receipt, new_intents, rows = queue.execute_segment(
            p, selected, segment_dir, sender, workers=workers, max_workers=max_workers,
            scale_after=scale_after, prior_intents=intents, prior_replies=replies,
            publish=publish, engineering_only=engineering_only)
        if receipt.get("halt_reason"):
            okay, stop_reason = _cool_after_recoverable(folder, sender, rows, receipt, policy,
                                                         cool=cool, stage="main")
            if not okay:
                result = {"status": "stopped_main_incomplete", "halt_reason": stop_reason,
                          "segment_receipt": receipt, "technical_gate": gate,
                          **queue.account(*queue.archive(folder))}
                dump(round_dir / "main_receipt.json", result)
                return result


def run_repair_segments(p, slots, folder, main_intents, main_replies, send, policy, *,
                        publish=lambda _value: None, engineering_only=False, cool=queue.cooldown):
    """One distinct-key repair attempt per failed new slot; all costs share the main cap."""
    folder = Path(folder)
    slot_by_key = {slot["key"]: slot for slot in slots}
    targets = _repair_targets(main_replies, slot_by_key, policy)
    repair_root = folder / "repair"
    repair_root.mkdir(exist_ok=True)
    sender = queue.safe_sender(send)
    while True:
        repair_intents, repair_replies = queue.archive(repair_root)
        targets, attempted, _ = _validate_repair_ledger_shape(
            repair_intents, repair_replies, slot_by_key, main_replies, p)
        ledger = _account_both(main_intents, main_replies, repair_intents, repair_replies)
        if ledger["total_spent_or_reserved_usd"] > p["budget_cap_usd"] + 1e-9:
            raise ValueError("Cumulative main/repair shared budget cap exceeded")
        pending_targets = [key for key in targets if "repair1|" + key not in attempted]
        if not pending_targets:
            status = "not_needed" if not targets else "completed"
            return {"status": status, "target_count": len(targets), "actual_model_results": not engineering_only,
                    **queue.account(repair_intents, repair_replies)}, repair_intents, repair_replies, targets
        pending = [_repair_slot(slot_by_key[key]) for key in pending_targets]
        rounds = sorted(repair_root.glob("round_*"))
        round_dir = repair_root / f"round_{len(rounds) + 1:04d}"
        round_dir.mkdir()
        segments = sorted(round_dir.glob("segment_*"))
        segment_dir = round_dir / f"segment_{len(segments) + 1:04d}"
        sender.retry_after_s = 0.0
        receipt, _new_intents, rows = queue.execute_segment(
            p, pending, segment_dir, sender, workers=16, max_workers=32, scale_after=32,
            prior_intents=[*main_intents, *repair_intents],
            prior_replies=[*main_replies, *repair_replies], publish=publish,
            engineering_only=engineering_only)
        if receipt.get("halt_reason"):
            if receipt["halt_reason"] in ("Budget cap reached before dispatch", "Budget guard"):
                return {"status": "stopped_budget_guard", "target_count": len(targets),
                        "halt_reason": receipt["halt_reason"], **queue.account(*queue.archive(repair_root))}, \
                       *queue.archive(repair_root), targets
            okay, stop_reason = _cool_after_recoverable(folder, sender, rows, receipt, policy,
                                                         cool=cool, stage="repair")
            if not okay:
                if stop_reason == "hard_provider_or_account_error":
                    return {"status": "stopped_hard_error", "target_count": len(targets),
                            "halt_reason": stop_reason, **queue.account(*queue.archive(repair_root))}, \
                           *queue.archive(repair_root), targets
                # A bounded cooldown stop leaves failed fields missing; never retry a repair key.
                return {"status": "stopped_recoverable", "target_count": len(targets),
                        "halt_reason": stop_reason, **queue.account(*queue.archive(repair_root))}, \
                       *queue.archive(repair_root), targets


def _publish_cost_progress(folder, phase, live=None):
    main_intents, main_replies = queue.archive(folder)
    repair_intents, repair_replies = queue.archive(Path(folder) / "repair") if (Path(folder) / "repair").exists() else ([], [])
    accounting = _account_both(main_intents, main_replies, repair_intents, repair_replies)
    main, repair = accounting["main"], accounting["repair"]
    in_flight = live.get("in_flight", 0) if live else 0
    if live and phase == "main":
        main_attempts, main_completed = live.get("attempts", main["attempts"]), live.get("completed", main["completed"])
        main_reported = live.get("reported_cost_usd", main["reported_cost_usd"])
        main_reserved = live.get("spent_or_reserved_usd", main["spent_or_reserved_usd"])
        repair_attempts, repair_completed = repair["attempts"], repair["completed"]
        repair_reported, repair_reserved = repair["reported_cost_usd"], repair["spent_or_reserved_usd"]
    elif live:
        main_attempts, main_completed = main["attempts"], main["completed"]
        main_reported, main_reserved = main["reported_cost_usd"], main["spent_or_reserved_usd"]
        repair_attempts = max(0, live.get("attempts", main["attempts"] + repair["attempts"]) - main["attempts"])
        repair_completed = max(0, live.get("completed", main["completed"] + repair["completed"]) - main["completed"])
        repair_reported = max(0.0, live.get("reported_cost_usd", accounting["total_reported_cost_usd"]) - main_reported)
        repair_reserved = max(0.0, live.get("spent_or_reserved_usd", accounting["total_spent_or_reserved_usd"]) - main_reserved)
    else:
        main_attempts, main_completed = main["attempts"], main["completed"]
        main_reported, main_reserved = main["reported_cost_usd"], main["spent_or_reserved_usd"]
        repair_attempts, repair_completed = repair["attempts"], repair["completed"]
        repair_reported, repair_reserved = repair["reported_cost_usd"], repair["spent_or_reserved_usd"]
    atomic_json(Path(folder) / "progress.json", {
        "phase": phase, "at_utc": queue.now(),
        "main_attempts": main_attempts, "main_completed": main_completed,
        "main_reported_cost_usd": main_reported, "main_spent_or_reserved_usd": main_reserved,
        "repair_attempts": repair_attempts, "repair_completed": repair_completed,
        "repair_reported_cost_usd": repair_reported, "repair_spent_or_reserved_usd": repair_reserved,
        "total_reported_cost_usd": main_reported + repair_reported,
        "total_spent_or_reserved_usd": main_reserved + repair_reserved,
        "unknown_fee_reservation_usd": max(0., main_reserved - main_reported) + max(0., repair_reserved - repair_reported),
        "in_flight": in_flight,
    })
    return accounting


def review(folder):
    c, p = checked(folder)
    intents, replies = queue.archive(folder)
    expected_slots, ctx = _load_frozen_slots(folder, p)
    by_key = {s["key"]: s for s in expected_slots}
    if len(intents) > len(by_key) or any(r["key"] not in by_key for r in intents):
        raise ValueError("Archived Terminal attempts exceed the frozen new-request scope")
    for intent in intents:
        slot = by_key[intent["key"]]
        if intent.get("prompt_sha256") != slot["prompt_sha256"] or intent.get("reserved_usd") != slot["reserved_usd"]:
            raise ValueError("Archived attempt differs from frozen slot")
    statuses = {status: 0 for status in POSITION_STATUSES}
    for pos in ctx["positions"].values():
        statuses[pos["status"]] += 1
    main_account = queue.account(intents, replies)
    repair_root = Path(folder) / "repair"
    repair_intents, repair_replies = queue.archive(repair_root) if repair_root.exists() else ([], [])
    _validate_repair_ledger_shape(repair_intents, repair_replies, by_key, replies, p)
    repair_account = queue.account(repair_intents, repair_replies)
    combined_spent = main_account["spent_or_reserved_usd"] + repair_account["spent_or_reserved_usd"]
    if combined_spent > p["budget_cap_usd"] + 1e-9:
        raise ValueError("Cumulative main/repair shared budget cap exceeded")
    return dict(status="prepared_not_started" if not intents else "has_archived_attempts",
        planned_calls=p["planned_calls"], **main_account,
        main_account=main_account, repair_account=repair_account,
        total_spent_or_reserved_usd=combined_spent,
        maximum_repair_attempts=p["planned_calls"], maximum_physical_attempts=2*p["planned_calls"],
        estimated_reserved_usd=c["estimated_reserved_usd"], budget_cap_usd=p["budget_cap_usd"],
        months=p["months"], arms=p["arms"], reference_arms=p["reference_arms"],
        repeats=p["generation_repeats"], positions=len(ctx["positions"]), position_status_counts=statuses,
        destination=p["destination"], model=p["model"], route=p["route"],
        automatic_retries_per_failed_new_slot=1, provider_fallbacks=0, prompt_bytes_unchanged=True,
        new_api_calls=0, authorization_exists=(Path(folder) / "authorization.json").exists())


def _worker(folder, round_dir, lock_fd):
    folder, round_dir = Path(folder), Path(round_dir)
    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    wake = None
    try:
        c, p = checked(folder, authorized=True)
        if sys.platform == "darwin":
            wake = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(os.getpid())],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        slots, ctx = _load_frozen_slots(folder, p)
        old_intents, old_replies = queue.archive(folder)
        slot_by_key = {s["key"]: s for s in slots}
        if any(r["key"] not in slot_by_key or r.get("prompt_sha256") != slot_by_key[r["key"]]["prompt_sha256"]
               or r.get("reserved_usd") != slot_by_key[r["key"]]["reserved_usd"] for r in old_intents):
            raise ValueError("Continuation intent differs from frozen new-request scope")
        policy = read_json(folder / "execution_policy.json")
        if any(r.get("error") and not queue.recoverable(r, policy) for r in old_replies):
            raise ValueError("Prior hard failure requires explicit reconciliation")
        send = live_sender(p)

        def publish(value):
            _publish_cost_progress(folder, "main", value)

        main = run_main_segments(p, slots, folder, round_dir, send, policy, publish=publish)
        main_intents, main_replies = queue.archive(folder)
        main_complete = (main.get("status") == "completed"
                         and len(main_intents) == p["planned_calls"]
                         and len(main_replies) == len(main_intents)
                         and main.get("technical_gate", {}).get("passed") is True)
        generation = {"schema": "sce_media_timing_generation_receipt/v2",
                      "protocol_sha256": c["protocol_sha256"], "main": main,
                      "main_complete": main_complete, "truth_opened": False,
                      "repair": {"status": "not_started"}, "new_api_calls": len(main_intents)}
        dump(round_dir / "generation_receipt.json", generation)
        dump(folder / "generation_receipt.json", generation)
        if main_complete:
            repair, repair_intents, repair_replies, targets = run_repair_segments(
                p, slots, folder, main_intents, main_replies, send, policy,
                publish=lambda value: _publish_cost_progress(folder, "repair", value))
            hard_repair = repair.get("status") == "stopped_hard_error"
            generation.update(repair=repair, repair_targets=len(targets),
                repair_intents=len(repair_intents), repair_replies=len(repair_replies),
                repair_complete=repair.get("status") in ("not_needed", "completed", "stopped_budget_guard", "stopped_recoverable"),
                main_complete=True)
            dump(round_dir / "generation_receipt.json", generation)
            dump(folder / "generation_receipt.json", generation)
            if not hard_repair:
                _publish_cost_progress(folder, "evaluation")
                with (round_dir / "evaluation.log").open("x") as log:
                    code = subprocess.run([c["python"], "-u", str(ENTRY), "evaluate", "--run-dir", str(folder),
                                           "--out", str(round_dir / "evaluation")], cwd=ROOT,
                                          stdout=log, stderr=subprocess.STDOUT).returncode
                status = "generation_and_evaluation_complete" if code == 0 else "evaluation_failed_data_preserved"
            else:
                code, status = 0, "repair_hard_error_evaluation_not_started"
        else:
            code, status = 0, "generation_stopped_data_preserved"
        final = dict(status=status, receipt=generation, exit_code=code, ended_at_utc=queue.now(),
                     generation_backend="local_frozen_message_adapter_after_official_Core_offline_acceptance",
                     automatic_repair_attempts=len(queue.archive(Path(folder) / "repair")[0]) if (Path(folder) / "repair").exists() else 0,
                     automatic_retries_per_slot=1, automatic_process_restarts=0)
        dump(round_dir / "worker_receipt.json", final)
        atomic_json(folder / "latest_receipt.json", dict(final, round_dir=str(round_dir)))
    except Exception as exc:
        final = dict(status="worker_failed_data_preserved", error_type=type(exc).__name__, ended_at_utc=queue.now())
        dump(round_dir / "worker_receipt.json", final)
        atomic_json(folder / "latest_receipt.json", dict(final, round_dir=str(round_dir)))
        raise
    finally:
        if wake is not None:
            wake.terminate()
            wake.wait()
        os.close(lock_fd)


def watch(folder):
    folder = Path(folder)
    c, p = checked(folder)
    print("每10秒读取本地进度；Ctrl+C只退出观察，后台继续。", flush=True)
    try:
        while True:
            launch = read_json(folder / "latest_launch.json") if (folder / "latest_launch.json").exists() else None
            if launch and (Path(launch["round_dir"]) / "worker_receipt.json").exists():
                result = read_json(Path(launch["round_dir"]) / "worker_receipt.json")
                print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
                return result
            value = read_json(folder / "progress.json") if (folder / "progress.json").exists() else {}
            extra = read_json(folder / "scheduler_status.json") if (folder / "scheduler_status.json").exists() else {}
            age = ""
            if value.get("at_utc"):
                from datetime import datetime, timezone
                seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(value["at_utc"])).total_seconds()
                if seconds > 60:
                    age = f" | 进度{seconds:.0f}秒未刷新，请查看日志"
            print(time.strftime("%H:%M:%S") + f" | {value.get('phase', '等待初始化')}"
                + f" | 主批 {value.get('main_attempts', 0):,}/{p['planned_calls']:,} 回包 {value.get('main_completed', 0):,}"
                + f" ${value.get('main_reported_cost_usd', 0):.4f}报/ ${value.get('main_spent_or_reserved_usd', 0):.4f}计及预留"
                + f" | 补批 {value.get('repair_attempts', 0):,} 回包 {value.get('repair_completed', 0):,}"
                + f" ${value.get('repair_reported_cost_usd', 0):.4f}报/ ${value.get('repair_spent_or_reserved_usd', 0):.4f}计及预留"
                + f" | 合计 ${value.get('total_reported_cost_usd', 0):.4f}报/ ${value.get('total_spent_or_reserved_usd', 0):.4f}计及预留/${p['budget_cap_usd']:.2f}帽"
                + f" | 未知费预留 ${value.get('unknown_fee_reservation_usd', 0):.4f}"
                + f" | 在途 {value.get('in_flight', 0)}"
                + (f" | 冷却剩余 {extra['cooldown_remaining_s']:.0f}秒" if extra.get("cooldown_remaining_s", 0) > 0 else "")
                + age, flush=True)
            time.sleep(10)
    except KeyboardInterrupt:
        print("\n已退出观察；没有停止或重启模拟。", flush=True)


def run(folder, confirm=False, resume=False):
    if not confirm:
        raise ValueError("Review scope and budget, then explicitly use --confirm-scope-and-budget")
    folder = Path(folder).resolve()
    c, p = checked(folder)
    prior_rounds = sorted(folder.glob("round_*"))
    if bool(prior_rounds) != bool(resume):
        raise ValueError("Use run once; subsequent operator-approved continuation uses resume")
    slots, _ctx = _load_frozen_slots(folder, p)
    intents, replies = queue.archive(folder)
    repair_root = folder / "repair"
    repair_intents, repair_replies = queue.archive(repair_root) if repair_root.exists() else ([], [])
    balance = _account_both(intents, replies, repair_intents, repair_replies)
    if len(intents) == p["planned_calls"]:
        raise ValueError("Every new slot already attempted; evaluate offline, do not resend failures")
    if any(r.get("error") and not queue.recoverable(r, POLICY) for r in [*replies, *repair_replies]):
        raise ValueError("Prior hard failure requires explicit reconciliation")
    if balance["total_spent_or_reserved_usd"] > p["budget_cap_usd"] + 1e-9:
        raise ValueError("Prior main plus repair accounting exceeds the single frozen cap")
    from ..news_label_trial import dotenv_values
    if not (os.environ.get("OPENROUTER_API_KEY") or dotenv_values(OFFICIAL / ".env").get("OPENROUTER_API_KEY")):
        raise ValueError("OpenRouter credential unavailable; never put it in the command line")
    lock = os.open(folder / "execution.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not (folder / "authorization.json").exists():
            dump(folder / "authorization.json", dict(approved=True, config_sha256=sha(folder / "config.json"),
                user_confirmation="--confirm-scope-and-budget", at_utc=queue.now(),
                destination=p["destination"], model=p["model"], route=p["route"],
                main_max_requests=p["planned_calls"], repair_max_requests=p["planned_calls"],
                maximum_physical_attempts=2*p["planned_calls"], budget_cap_usd=p["budget_cap_usd"],
                automatic_repair_once_per_technical_failure=True,
                old_attempted_failures_repaired=False,
                scope_text=(f"Main up to {p['planned_calls']} new requests plus at most one technical repair "
                            f"per failed new slot (up to {2*p['planned_calls']} physical attempts total); "
                            f"one shared ${p['budget_cap_usd']:.2f} cap; no old failed-attempt repair.")))
        checked(folder, authorized=True)
        round_dir = folder / f"round_{len(prior_rounds) + 1:04d}"
        round_dir.mkdir(exist_ok=False)
        dump(round_dir / "launch_intent.json", dict(operator_action="resume" if resume else "run",
             previous_main_attempts=len(intents), previous_repair_attempts=len(repair_intents),
             unresolved_main_intents=balance["main"]["unresolved"],
             spent_or_reserved_usd=balance["total_spent_or_reserved_usd"],
             total_budget_cap_usd=p["budget_cap_usd"], at_utc=queue.now()))
        print(f"主批最多{p['planned_calls']:,}次；本批技术失败最多各补一次，再最多{p['planned_calls']:,}次；"
              f"物理请求上限{2*p['planned_calls']:,}。旧尝试失败不补发。"
              f"单一累计帽${p['budget_cap_usd']:.2f}（当前计及预留${balance['total_spent_or_reserved_usd']:.4f}）。", flush=True)
        with (round_dir / "worker.log").open("x") as log:
            child = subprocess.Popen([c["python"], "-u", str(ENTRY), "_worker", "--run-dir", str(folder),
                "--round-dir", str(round_dir), "--lock-fd", str(lock)], cwd=ROOT, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True, pass_fds=(lock,))
        atomic_json(folder / "latest_launch.json", dict(pid=child.pid, round_dir=str(round_dir), at_utc=queue.now()))
    finally:
        os.close(lock)
    print(f"独立后台PID {child.pid}；不会依赖当前终端逐批调度。", flush=True)
    return watch(folder)


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--package", type=Path, required=True)
    prep.add_argument("--run-dir", type=Path, required=True)
    for action in ("review", "run", "resume", "watch", "evaluate", "_worker"):
        cmd = sub.add_parser(action)
        cmd.add_argument("--run-dir", type=Path, required=True)
        if action in ("run", "resume"):
            cmd.add_argument("--confirm-scope-and-budget", action="store_true")
        if action == "evaluate":
            cmd.add_argument("--out", type=Path, required=True)
        if action == "_worker":
            cmd.add_argument("--round-dir", type=Path, required=True)
            cmd.add_argument("--lock-fd", type=int, required=True)
    args = parser.parse_args(argv)
    if args.action == "prepare":
        print(json.dumps(prepare(args.package, args.run_dir), ensure_ascii=False, indent=2))
    elif args.action == "review":
        print(json.dumps(review(args.run_dir), ensure_ascii=False, indent=2))
    elif args.action in ("run", "resume"):
        run(args.run_dir, args.confirm_scope_and_budget, args.action == "resume")
    elif args.action == "watch":
        watch(args.run_dir)
    elif args.action == "_worker":
        _worker(args.run_dir, args.round_dir, args.lock_fd)
    else:
        from ..evaluation.media_timing import evaluate
        print(json.dumps(evaluate(args.run_dir, args.out), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
