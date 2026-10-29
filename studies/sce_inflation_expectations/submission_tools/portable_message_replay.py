"""Offline re-render audit using archived raw model replies as replay inputs.

This is a hash-and-state-flow audit, not a model regeneration or score run. It
reconstructs the four final tasks' exact prompts, advances monthly and weekly
states from the raw main/repair replies, and compares every prompt to the
canonical input index. No target truth, effective-answer cache, credential, or
network access is used to initialize the replay.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path

from . import portable_run as run
from ..prior_belief_experiment import message_hash


ROOT = run.ROOT
TASKS = ("A", "B", "monthly", "weekly")
INPUT_INDEX = "data/input_index.jsonl.gz"
MODEL_OUTPUTS = "data/model_outputs.jsonl.gz"
CALL_RECEIPTS = "data/call_receipts.jsonl.gz"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _jsonl_gz(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                yield line_number, json.loads(line)


def _write_json(path: Path, value) -> None:
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                     allow_nan=False, sort_keys=True) + "\n",
                          encoding="utf-8")


def _write_jsonl_gz(path: Path, rows) -> int:
    count = 0
    with Path(path).open("xb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", filename="", mtime=0) as zipped:
            with __import__("io").TextIOWrapper(zipped, encoding="utf-8", newline="\n") as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False,
                                            separators=(",", ":"), sort_keys=True) + "\n")
                    count += 1
    return count


def _inside(base: Path, relative: str) -> Path:
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()) or path.is_symlink() or not path.is_file():
        raise ValueError("Evidence path escapes its directory or is not a regular file: " + relative)
    return path


def _verify_evidence(evidence_dir: Path):
    evidence_dir = Path(evidence_dir).resolve()
    manifest_path = _inside(evidence_dir, "manifest.json")
    manifest = _json(manifest_path)
    if manifest.get("schema") != "sce_portable_call_evidence/v1":
        raise ValueError("Portable call evidence manifest required")
    declared_files = manifest.get("files_sha256", manifest.get("files", {}))
    verified = {}
    for relative, binding in sorted(declared_files.items()):
        expected = binding.get("sha256") if isinstance(binding, dict) else binding
        if not isinstance(expected, str):
            raise ValueError("Malformed evidence file hash binding: " + relative)
        path = _inside(evidence_dir, relative)
        actual = sha(path)
        if actual != expected:
            raise ValueError("Evidence file hash mismatch: " + relative)
        verified[relative] = actual
    for required in (INPUT_INDEX, MODEL_OUTPUTS, CALL_RECEIPTS, "source_provenance.json"):
        if required not in verified:
            raise ValueError("Required evidence artifact is not bound by manifest: " + required)
    source_provenance = _json(_inside(evidence_dir, "source_provenance.json"))
    if source_provenance.get("schema") != "sce_portable_evidence_sources/v1":
        raise ValueError("Portable source-provenance index required")
    return manifest, verified, source_provenance


def _digest_text(value, label):
    if not isinstance(value, str):
        raise ValueError(label + " must be exact text")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_evidence(evidence_dir: Path):
    """Validate and index canonical inputs, archived replies, and call receipts."""
    manifest, verified, source_provenance = _verify_evidence(evidence_dir)
    input_index = {}
    source_input_bindings = set()
    for line_number, row in _jsonl_gz(_inside(evidence_dir, INPUT_INDEX)):
        key = (row.get("run"), str(row.get("period")), row.get("source_agent_id"))
        if not all(isinstance(x, str) and x for x in (key[0], key[1], key[2])):
            raise ValueError("Input index identity is incomplete")
        if key in input_index:
            raise ValueError("Duplicate canonical input identity: " + repr(key))
        digest = row.get("original_prompt_sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("Canonical prompt hash missing")
        if row.get("delivered_prompt_sha256") != digest:
            raise ValueError("Original and delivered canonical prompt hashes differ")
        if row.get("complete_prompt_source_path") and row.get("complete_prompt_source_sha256"):
            source_input_bindings.add((row["complete_prompt_source_path"],
                                       row["complete_prompt_source_sha256"]))
        input_index[key] = dict(row, _line_number=line_number)

    responses = {}
    response_by_id = {}
    raw_text_hashes = {}
    for _line_number, row in _jsonl_gz(_inside(evidence_dir, MODEL_OUTPUTS)):
        identity = (row.get("run"), str(row.get("period")), row.get("source_agent_id"), row.get("stage"))
        if identity in responses:
            raise ValueError("Duplicate raw response identity: " + repr(identity))
        text = row.get("response_text")
        digest = _digest_text(text, "Raw response")
        if row.get("response_text_redacted"):
            raise ValueError("A redacted output cannot support exact message replay")
        for field in ("original_response_sha256", "delivered_response_sha256"):
            if row.get(field) != digest:
                raise ValueError("Raw response text/hash mismatch: " + field)
        response_id = row.get("response_id")
        if not isinstance(response_id, str) or not response_id or response_id in response_by_id:
            raise ValueError("Response IDs must be present and unique")
        expected_input = input_index.get(identity[:3])
        if expected_input is None:
            raise ValueError("Raw response does not join a canonical input: " + repr(identity))
        if row.get("input_id") != expected_input.get("input_id"):
            raise ValueError("Raw response input_id disagrees with canonical identity")
        if row.get("prompt_sha256") != expected_input.get("original_prompt_sha256"):
            raise ValueError("Raw response prompt hash disagrees with canonical input")
        responses[identity] = row
        response_by_id[response_id] = row
        raw_text_hashes[response_id] = digest

    receipts_by_response = {}
    for _line_number, row in _jsonl_gz(_inside(evidence_dir, CALL_RECEIPTS)):
        response_id = row.get("response_id")
        if response_id not in response_by_id or response_id in receipts_by_response:
            raise ValueError("Call receipt has missing/duplicate response link")
        output = response_by_id[response_id]
        if any(row.get(k) != output.get(output_key) for k, output_key in (
                ("run", "run"), ("period", "period"),
                ("source_agent_id", "source_agent_id"), ("stage", "stage"))):
            raise ValueError("Call receipt identity differs from raw response")
        if row.get("raw_response_sha256") != raw_text_hashes[response_id]:
            raise ValueError("Call receipt response hash differs from raw text")
        receipts_by_response[response_id] = row
    if len(receipts_by_response) != len(responses):
        raise ValueError("Not every raw output has exactly one source call receipt")

    manifest_counts = manifest.get("counts", {})
    expected_inputs = manifest_counts.get("input_positions")
    expected_outputs = manifest_counts.get("attempts")
    if expected_inputs is not None and len(input_index) != expected_inputs:
        raise ValueError("Input index count disagrees with evidence manifest")
    if expected_outputs is not None and len(responses) != expected_outputs:
        raise ValueError("Raw output count disagrees with evidence manifest")
    # Verify that the original prompt file named in the row-level index is
    # present in the named provenance map, without opening/reconstructing it.
    source_bindings = {(r.get("source_path"), r.get("sha256"))
                       for r in source_provenance.get("sources", [])}
    missing_bindings = source_input_bindings - source_bindings
    if missing_bindings:
        raise ValueError("Canonical prompt source lacks a provenance hash binding")
    return dict(manifest=manifest, verified_files=verified, source_provenance=source_provenance,
                input_index=input_index, responses=responses,
                response_by_id=response_by_id, receipts_by_response=receipts_by_response,
                raw_text_hashes=raw_text_hashes)


def _density_lookup(runtime_data: Path):
    """Read only the exact numerical cache; no evaluation targets are opened."""
    path = _inside(Path(runtime_data).resolve(), "evaluation/density_cache.jsonl.gz")
    cache = {}
    for _line_number, row in _jsonl_gz(path):
        bins = row.get("bins")
        if not isinstance(bins, list) or len(bins) != 10:
            raise ValueError("Malformed cached Q9 vector")
        key = tuple(float(x) for x in bins)
        score = row.get("score") or {}
        mean = score.get("mean")
        if mean is not None and (type(mean) not in (int, float) or not math.isfinite(mean)):
            raise ValueError("Malformed cached density mean")
        if key in cache and cache[key] != mean:
            raise ValueError("Conflicting exact-vector density cache entries")
        cache[key] = None if mean is None else float(mean)
    return path, cache


def _cache_density_functions(cache: dict, counters: Counter):
    """Temporarily replace density fitting with exact cached-vector lookup."""
    from .. import state_continuity_runtime
    from ..experiments import weekly_state, state_continuity_inputs

    originals = {
        state_continuity_runtime: state_continuity_runtime.density_center,
        weekly_state: weekly_state.density_center,
        state_continuity_inputs: state_continuity_inputs.density_center,
    }

    def lookup(original):
        def cached(probabilities):
            key = tuple(float(x) for x in probabilities)
            if key in cache:
                counters["density_cache_hits"] += 1
                return cache[key]
            counters["density_cache_misses"] += 1
            return original(tuple(probabilities))
        return cached

    state_continuity_runtime.density_center = lookup(originals[state_continuity_runtime])
    weekly_state.density_center = lookup(originals[weekly_state])
    state_continuity_inputs.density_center = lookup(originals[state_continuity_inputs])
    return originals


def _restore_density_functions(originals):
    for module, function in originals.items():
        module.density_center = function


def _replay_row(record, key):
    return dict(key=key, raw_response_text=record["response_text"],
                finish_reason=record.get("finish_reason"), error=record.get("error"),
                actual_model_results=record.get("actual_model_results"),
                response_id=record["response_id"],
                original_response_sha256=record["original_response_sha256"])


def _call_refs(evidence, task, period, aid, *, source_task=None, source_period=None):
    source_task = source_task or task
    source_period = str(source_period if source_period is not None else period)
    key = f"{task}|{period}|{aid}"
    result = {"main": None, "repair": None}
    for stage in ("main", "repair"):
        record = evidence["responses"].get((source_task, source_period, aid, stage))
        if record is None:
            if stage == "main":
                raise ValueError("Missing main raw response for " + repr((source_task, source_period, aid)))
            continue
        result[stage] = record
    return result


def _state_hash(state):
    if state is None:
        return None
    encoded = json.dumps(state, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _verify_render(task, period, rows, messages, evidence, wave):
    checks = []
    for aid in sorted(rows):
        input_task, input_period = task, str(period)
        # The monthly November root is the exact B November input. Join by the
        # original source Agent ID, not by task-specific household alias or
        # row position.
        if task == "monthly" and input_period == "202511":
            input_task = "B"
        source_id = rows[aid].get("agent_id", aid)
        if source_id != aid:
            raise ValueError("Runtime row key differs from original source Agent ID")
        canonical = evidence["input_index"].get((input_task, input_period, source_id))
        if canonical is None:
            raise ValueError("Rendered message lacks canonical source input: " + repr((input_task, input_period, source_id)))
        if not (task == "monthly" and input_period == "202511"):
            if rows[aid].get("household") != canonical.get("household"):
                raise ValueError("Runtime alias differs from input-index household alias")
        replayed = message_hash(messages[aid])
        expected = canonical["original_prompt_sha256"]
        if replayed != expected:
            raise ValueError("Re-rendered prompt hash mismatch: " + repr((task, period, source_id)))
        checks.append((aid, canonical, replayed))
    return checks


def _response_trace(record, receipt):
    if record is None:
        return None
    receipt = receipt[record["response_id"]]
    return dict(response_id=record["response_id"],
                response_sha256=record["original_response_sha256"],
                source_attempt_ref=receipt.get("source_attempt_ref"),
                source_dispatch_ref=receipt.get("source_dispatch_ref"))


def _field_refs(answer, main_record, repair_record, before_refs):
    refs = dict(before_refs)
    sources = answer.get("field_sources", {})
    for field in ("q8", "q9"):
        source = sources.get(field)
        if source == "main" and main_record is not None:
            refs[field] = main_record["response_id"]
        elif source == "repair" and repair_record is not None:
            refs[field] = repair_record["response_id"]
        elif source in ("retained_prior", "retained_previous"):
            pass
        else:
            refs[field] = None
    return refs


def _trace_row(task, period, aid, canonical, replayed, before, after,
               source_task, source_period, refs, before_refs, answer,
               main_record, repair_record, evidence):
    return dict(task=task, period=str(period), source_agent_id=aid,
        input_id=canonical["input_id"], canonical_source_task=canonical["run"],
        canonical_source_period=str(canonical["period"]),
        canonical_household=canonical["household"], public_sce_userid=canonical.get("public_sce_userid"),
        input_source_path=canonical.get("complete_prompt_source_path"),
        input_source_line=canonical.get("complete_prompt_source_line"),
        input_source_sha256=canonical.get("complete_prompt_source_sha256"),
        original_prompt_sha256=canonical["original_prompt_sha256"],
        replayed_prompt_sha256=replayed, prompt_hash_match=(replayed == canonical["original_prompt_sha256"]),
        state_before_sha256=_state_hash(before), state_after_sha256=_state_hash(after),
        state_before_response_ids=before_refs, state_after_response_ids=refs,
        source_responses=dict(run=source_task, period=str(source_period),
            main=_response_trace(main_record, evidence["receipts_by_response"]),
            repair=_response_trace(repair_record, evidence["receipts_by_response"])),
        field_sources=answer.get("field_sources") if answer else None)


def _verify_source_directory(path: Path, expected_root: Path) -> str:
    path = Path(path).resolve()
    if not path.is_relative_to(expected_root.resolve()):
        raise ValueError("Replay inputs must live inside the portable workspace")
    return str(path.relative_to(expected_root.resolve()))


def audit(runtime_data, evidence_dir, out):
    """Replay and hash-check all A/B/monthly/weekly final prompts offline.

    Parameters are portable-workspace-relative directories. The output must be
    fresh. Returns an aggregate report; row-level prompt/state/response joins
    are written to ``replay_trace.jsonl.gz``.
    """
    runtime_data, evidence_dir = Path(runtime_data).resolve(), Path(evidence_dir).resolve()
    out = Path(out).resolve()
    for path in (runtime_data, evidence_dir):
        _verify_source_directory(path, ROOT)
    if out.exists():
        raise FileExistsError("Fresh closed-loop replay output required")
    out.mkdir(parents=True)

    from .reproduce import no_network
    density_path, density_cache = _density_lookup(runtime_data)
    evidence = _load_evidence(evidence_dir)
    index_path = runtime_data / "index.json"
    index = run.load_index(runtime_data)
    counters = Counter()
    old_density = _cache_density_functions(density_cache, counters)
    trace_path = out / "replay_trace.jsonl.gz"
    task_summary = {task: dict(rendered_messages=0, prompt_hash_matches=0,
        prompt_hash_mismatches=0, raw_main_responses=0, raw_repair_responses=0,
        recursive_steps=0, raw_response_source_runs=Counter()) for task in TASKS}
    all_input_keys = set()
    monthly_root_count = 0

    def emit_trace(row):
        counters["trace_rows"] += 1
        trace_stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False,
                                      separators=(",", ":"), sort_keys=True) + "\n")

    try:
        with no_network(), trace_path.open("xb") as binary:
            with gzip.GzipFile(fileobj=binary, mode="wb", filename="", mtime=0) as zipped:
                with __import__("io").TextIOWrapper(zipped, encoding="utf-8", newline="\n") as trace_stream:
                    # The local helper closes over the current trace stream.
                    def write_trace(row):
                        emit_trace(row)

                    for task in TASKS:
                        waves = index["waves"][task]
                        previous = None
                        predecessor = None
                        state_refs = {}
                        fixed_ids = None
                        for item in waves:
                            wave = run.checked_wave(runtime_data, item)
                            period = str(item["period"])
                            selected = sorted(wave["rows"])
                            if task in ("monthly", "weekly"):
                                if fixed_ids is None:
                                    fixed_ids = selected
                                elif selected != fixed_ids:
                                    raise ValueError("Fixed cohort changed during replay: " + task)

                            before, messages = run.render_wave(task, wave, selected,
                                                               previous, predecessor)
                            checks = _verify_render(task, period, wave["rows"], messages,
                                                    evidence, wave)
                            for aid, canonical, prompt_hash in checks:
                                all_input_keys.add((canonical["run"], str(canonical["period"]), aid))
                                task_summary[task]["rendered_messages"] += 1
                                task_summary[task]["prompt_hash_matches"] += prompt_hash == canonical["original_prompt_sha256"]

                            # A and B use independent frozen periods. Monthly's
                            # November root reuses raw B replies. Later monthly
                            # and all weekly steps advance only from raw replies
                            # in this archive, never from effective-answer rows.
                            if task == "monthly" and period == "202511":
                                source_task, source_period = "B", "202511"
                                monthly_root_count = len(selected)
                            else:
                                source_task, source_period = task, period

                            if task in ("monthly", "weekly"):
                                before_refs = {}
                                for aid in selected:
                                    inherited = {}
                                    if previous is not None and before[aid] == previous[aid]:
                                        inherited = dict(state_refs.get(aid, {}))
                                    before_refs[aid] = inherited
                                main, repairs = {}, {}
                                main_records, repair_records = {}, {}
                                for aid in selected:
                                    logical_key = f"{task}|{period}|{aid}"
                                    refs = _call_refs(evidence, task, period, aid,
                                                      source_task=source_task,
                                                      source_period=source_period)
                                    main_records[aid] = refs["main"]
                                    repair_records[aid] = refs["repair"]
                                    main[logical_key] = _replay_row(refs["main"], logical_key)
                                    if refs["repair"] is not None:
                                        repairs["repair1|" + logical_key] = _replay_row(refs["repair"],
                                                                                        "repair1|" + logical_key)
                                    task_summary[task]["raw_main_responses"] += 1
                                    task_summary[task]["raw_repair_responses"] += refs["repair"] is not None
                                    task_summary[task]["raw_response_source_runs"][source_task] += 1 + (refs["repair"] is not None)

                                after, answers = run.advance(task, before, main, repairs, wave, selected)
                                answer_by_agent = {answer["agent_id"]: answer for answer in answers}
                                next_refs = {}
                                for aid, canonical, prompt_hash in checks:
                                    answer = answer_by_agent[aid]
                                    refs = _field_refs(answer, main_records[aid], repair_records[aid],
                                                       before_refs[aid])
                                    next_refs[aid] = refs
                                    write_trace(_trace_row(task, period, aid, canonical, prompt_hash,
                                        before[aid], after[aid], source_task, source_period, refs,
                                        before_refs[aid], answer, main_records[aid],
                                        repair_records[aid], evidence))
                                previous, state_refs = after, next_refs
                                task_summary[task]["recursive_steps"] += len(selected)
                                predecessor = wave["point"]["cutoff"] if task == "weekly" else period
                            else:
                                for aid, canonical, prompt_hash in checks:
                                    refs = _call_refs(evidence, task, period, aid)
                                    task_summary[task]["raw_main_responses"] += 1
                                    task_summary[task]["raw_repair_responses"] += refs["repair"] is not None
                                    task_summary[task]["raw_response_source_runs"][task] += 1 + (refs["repair"] is not None)
                                    write_trace(_trace_row(task, period, aid, canonical, prompt_hash,
                                        before[aid], None, task, period, {}, {}, None,
                                        refs["main"], refs["repair"], evidence))

                    # Independent completeness checks catch accidental omissions
                    # from any task loop without consulting scored/effective rows.
                    if all_input_keys != set(evidence["input_index"]):
                        missing = set(evidence["input_index"]) - all_input_keys
                        extra = all_input_keys - set(evidence["input_index"])
                        raise ValueError(f"Canonical input coverage differs: missing={len(missing)}, extra={len(extra)}")
    finally:
        _restore_density_functions(old_density)

    for task in TASKS:
        task_summary[task]["prompt_hash_mismatches"] = (
            task_summary[task]["rendered_messages"] - task_summary[task]["prompt_hash_matches"])
        task_summary[task]["raw_response_source_runs"] = dict(sorted(
            task_summary[task]["raw_response_source_runs"].items()))
    if sum(v["prompt_hash_mismatches"] for v in task_summary.values()):
        raise ValueError("One or more rendered prompt hashes failed")
    files = {
        "replay_trace.jsonl.gz": dict(sha256=sha(trace_path), rows=counters["trace_rows"]),
    }
    report = dict(schema="sce_portable_message_replay/v1",
        status="passed_offline_raw_reply_closed_loop_replay",
        runtime_data_path=_verify_source_directory(runtime_data, ROOT),
        evidence_directory_path=_verify_source_directory(evidence_dir, ROOT),
        counts=dict(canonical_input_positions=len(evidence["input_index"]),
            unique_canonical_inputs_referenced=len(all_input_keys),
            task_rendered_messages=sum(x["rendered_messages"] for x in task_summary.values()),
            raw_response_records=len(evidence["responses"]),
            raw_text_sha256_checked=len(evidence["raw_text_hashes"]),
            call_receipt_joins=len(evidence["receipts_by_response"]),
            prompt_hash_mismatches=sum(x["prompt_hash_mismatches"] for x in task_summary.values()),
            density_cache_rows=len(density_cache),
            density_cache_hits=counters["density_cache_hits"],
            density_cache_misses=counters["density_cache_misses"]),
        tasks=task_summary,
        monthly_root=dict(task="monthly", period="202511", source_run="B",
            source_period="202511", join_key="source_agent_id",
            raw_main_responses=monthly_root_count,
            note="Fresh B November raw replies are replayed into the monthly root; no archived effective state initializes later months."),
        provenance=dict(runtime_index=dict(path=_verify_source_directory(index_path, ROOT),
            sha256=sha(index_path)), runtime_wave_files=[dict(task=task, period=str(item["period"]),
            path=item["file"], sha256=index["files_sha256"][item["file"]])
            for task in TASKS for item in index["waves"][task]],
            evidence_manifest=dict(path=_verify_source_directory(evidence_dir / "manifest.json", ROOT),
                sha256=sha(evidence_dir / "manifest.json")),
            evidence_artifacts=[dict(path=f"{_verify_source_directory(evidence_dir, ROOT)}/{name}", sha256=digest)
                for name, digest in sorted(evidence["verified_files"].items())],
            evidence_source_provenance=dict(path=f"{_verify_source_directory(evidence_dir, ROOT)}/source_provenance.json",
                sha256=evidence["verified_files"]["source_provenance.json"],
                source_count=len(evidence["source_provenance"].get("sources", []))),
            density_cache=dict(path=_verify_source_directory(density_path, ROOT), sha256=sha(density_path))),
        method=dict(network_allowed=False, api_calls=0, credentials_read=False,
            raw_replies_are_external_replay_inputs=True,
            score_targets_read=False, old_effective_answers_read=False,
            state_initialization="original frozen initial states/weekly public priors; later state only from replayed raw main/repair replies",
            evaluation_density_cache="exact-bin cached mean only; fallback to original scorer only for cache misses",
            authenticity="Local hash verification of supplied files; no provider-signature claim"),
        files=files)
    report_path = out / "report.json"
    _write_json(report_path, report)
    manifest = dict(schema="sce_portable_message_replay_manifest/v1",
        files_sha256={"report.json": sha(report_path), **{name: value["sha256"] for name, value in files.items()}},
        row_counts={"replay_trace.jsonl.gz": counters["trace_rows"]},
        source_runtime_index_sha256=sha(index_path),
        source_evidence_manifest_sha256=sha(evidence_dir / "manifest.json"),
        network_allowed=False, api_calls=0)
    _write_json(out / "manifest.json", manifest)
    return report


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-data", type=Path, required=True,
                        help="Frozen portable runtime data directory")
    parser.add_argument("--evidence-dir", type=Path, required=True,
                        help="Portable evidence directory with canonical prompts and raw replies")
    parser.add_argument("--out", type=Path, required=True,
                        help="Fresh directory for report.json, manifest.json and replay_trace.jsonl.gz")
    args = parser.parse_args(argv)
    report = audit(args.runtime_data, args.evidence_dir, args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


__all__ = ["audit"]


if __name__ == "__main__":  # pragma: no cover - command-line entry point
    raise SystemExit(main())
