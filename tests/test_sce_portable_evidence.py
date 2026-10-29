"""Offline contract tests for the portable four-run call evidence export."""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "studies/sce_inflation_expectations/submission_tools/portable_evidence.py"
_SPEC = importlib.util.spec_from_file_location("portable_evidence_test_module", MODULE_PATH)
portable_evidence = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(portable_evidence)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_gz_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", filename="", mtime=0) as zipped:
            for row in rows:
                zipped.write((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_gz_jsonl(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def make_attempt(*, agent_id, month, key, prompt_sha256, response_text, request_id,
                 cost=0.01, reservation=0.02, error=None, usable=True):
    return {
        "key": key,
        "month": month,
        "arm": "test",
        "repeat": 1,
        "agent_id": agent_id,
        "prompt_sha256": prompt_sha256,
        "error": error,
        "fatal": False,
        "raw_response_text": response_text,
        "finish_reason": "stop" if usable else None,
        "api_reported_cost_usd": cost,
        "request_reservation_usd": reservation,
        "started_at_utc": "2026-10-25T09:00:00+00:00",
        "attempt_idx": 0,
        "actual_model_results": True,
        "returned_model": "deepseek/deepseek-v3.2",
        "returned_provider": "SiliconFlow",
        "request_id": request_id,
        "latency_ms": 1234.5,
        "system_fingerprint": None,
        "usage": {
            "completion_tokens": 11,
            "prompt_tokens": 22,
            "total_tokens": 33,
            "cost": cost,
            "cost_details": {"upstream_inference_cost": cost},
        },
        "raw_response_sha256": digest(response_text),
        "finished_at_utc": "2026-10-25T09:00:01.234500+00:00" if usable else "2026-10-25T09:00:01.234500+00:00",
        "field_usable": {"q8": usable, "q9": usable},
        "technical_usable": usable,
    }


def install_segment(root: Path, relative: str, attempt: dict) -> tuple[str, str]:
    folder = root / relative
    dispatch = [{"key": attempt["key"], "prompt_sha256": attempt["prompt_sha256"],
                 "reserved_usd": attempt["request_reservation_usd"], "at_utc": attempt["started_at_utc"]}]
    receipt = {"attempts": 1, "completed": 1, "usable": int(attempt["technical_usable"]),
               "reported_cost_usd": attempt["api_reported_cost_usd"], "actual_model_results": True,
               "status": "completed"}
    write_jsonl(folder / "calls_private.jsonl", [attempt])
    write_jsonl(folder / "dispatch_private.jsonl", dispatch)
    write_json(folder / "receipt.json", receipt)
    write_json(folder / "manifest.json", {"files_sha256": {
        "calls_private.jsonl": file_hash(folder / "calls_private.jsonl"),
        "dispatch_private.jsonl": file_hash(folder / "dispatch_private.jsonl"),
        "receipt.json": file_hash(folder / "receipt.json"),
    }})
    return (relative + "/calls_private.jsonl", relative + "/dispatch_private.jsonl")


def build_fixture(root: Path) -> None:
    """Create a minimal frozen source tree spanning each final task and edge case."""
    output_root = root / "outputs"
    ids = {
        "A_000001": "sce_opaque_a",
        "B_000001": "proxy_shared_root",
        "monthly_000001": "proxy_shared_root",
        "weekly_000001": "proxy_weekly",
    }
    id_map_path = output_root / "sce_micro_reproduction_20261029_v3/private_key_map_NOT_FOR_PACKAGE.json"
    write_json(id_map_path, ids)
    write_json(output_root / "sce_full_a_t0_analysis_20261026_v1/cases_private.json",
               [{"agent_id": "sce_opaque_a", "userid": 314159}])

    slots = [
        ("A", "202001", "A_000001", "prompt-a"),
        ("B", "202511", "B_000001", "prompt-b"),
        ("monthly", "202512", "monthly_000001", "prompt-monthly"),
        ("weekly", "w20260102", "weekly_000001", "prompt-weekly"),
    ]
    input_rows = [{"run": run, "period": period, "household": alias,
                   "original_prompt_sha256": digest(prompt), "delivered_prompt_sha256": digest(prompt),
                   "messages": []} for run, period, alias, prompt in slots]
    input_path = output_root / "sce_submission_inputs_exact_20261029_v1/complete_prompts.jsonl.gz"
    write_gz_jsonl(input_path, input_rows)
    write_json(input_path.parent / "candidate_manifest.json", {
        "complete_prompt_file": input_path.name,
        "full_prompt_rows": len(input_rows),
        "runs": {run: {"complete_prompts": 1} for run in ("A", "B", "monthly", "weekly")},
        "files": {input_path.name: {"sha256": file_hash(input_path)}},
    })

    a_prompt = digest("prompt-a")
    b_prompt = digest("prompt-b")
    monthly_prompt = digest("prompt-monthly")
    weekly_prompt = digest("prompt-weekly")
    a_text = '{"point_pct": 2.5, "q9": {"bin5": 100}}'
    a_old = make_attempt(agent_id="sce_opaque_a", month=202001, key="a|202001|sce_opaque_a|1",
                         prompt_sha256=a_prompt, response_text=a_text, request_id="gen-a-original")
    old_path = output_root / "sce_legacy_source/round_0001/segment_0001/calls_private.jsonl"
    write_jsonl(old_path, [a_old])
    old_line = old_path.read_bytes().splitlines(keepends=True)[0]
    old_file_hash = file_hash(old_path)
    write_json(old_path.parent / "manifest.json", {"files_sha256": {old_path.name: old_file_hash}})

    a_current = dict(a_old)
    a_current.update({
        "api_reported_cost_usd": 0.0,
        "request_reservation_usd": 0.0,
        "source_api_reported_cost_usd": a_old["api_reported_cost_usd"],
        "source_request_reservation_usd": a_old["request_reservation_usd"],
        "execution_kind": "historical_import",
        "external_request_sent": False,
    })
    a_repair = make_attempt(agent_id="sce_opaque_a", month=202001, key="a|repair|202001|sce_opaque_a|1",
                            prompt_sha256=digest("repair-prompt"), response_text='{"point_pct":3,"q9":{"bin5":100}}',
                            request_id="gen-a-repair")
    b_row = make_attempt(agent_id="proxy_shared_root", month="202511", key="b|202511|proxy_shared_root",
                         prompt_sha256=b_prompt, response_text='{"point_pct":2,"q9":{"bin5":100}}',
                         request_id="gen-b")
    monthly_row = make_attempt(agent_id="proxy_shared_root", month="202512", key="monthly|202512|proxy_shared_root",
                               prompt_sha256=monthly_prompt, response_text='{"point_pct":2.1,"q9":{"bin5":100}}',
                               request_id="gen-monthly")
    weekly_row = make_attempt(agent_id="proxy_weekly", month="202601", key="weekly|w20260102|proxy_weekly",
                              prompt_sha256=weekly_prompt, response_text="", request_id=None,
                              error="provider timeout", usable=False)

    paths = {
        "A_main": "outputs/sce_full_a_t0_terminal_20261025_v1/main/round_0001/segment_0001",
        "A_repair": "outputs/sce_full_a_t0_terminal_20261025_v1/repair/round_0001/segment_0001",
        "B_main": "outputs/sce_recent_b_sampled_terminal_20261026_v1/main/round_0001/segment_0001",
        "monthly_main": "outputs/sce_recent_b_recursion_terminal_20261026_v2/waves/202512/main/round_0001/segment_0001",
        "weekly_main": "outputs/sce_weekly_terminal_20261027_v1/waves/w20260102/main/round_0001/segment_0001",
    }
    for name, row in (("A_main", a_current), ("A_repair", a_repair), ("B_main", b_row),
                      ("monthly_main", monthly_row), ("weekly_main", weekly_row)):
        install_segment(root, paths[name], row)

    a_main_ref = "main/round_0001/segment_0001/calls_private.jsonl#key=" + a_current["key"]
    a_main_dispatch = "main/round_0001/segment_0001/dispatch_private.jsonl#key=" + a_current["key"]
    a_repair_ref = "repair/round_0001/segment_0001/calls_private.jsonl#key=" + a_repair["key"]
    a_repair_dispatch = "repair/round_0001/segment_0001/dispatch_private.jsonl#key=" + a_repair["key"]
    action = {
        "month": 202001,
        "agent_id": "sce_opaque_a",
        "attempt_state": "main_reply_received",
        "main": {
            "execution_kind": "historical_import",
            "external_request_sent": False,
            "dispatch_ref": a_main_dispatch,
            "raw_reply_ref": a_main_ref,
            "historical_source": {
                "stage": "main",
                "key": a_old["key"],
                "reply_path": old_path.relative_to(root).as_posix(),
                "source_file_sha256": old_file_hash,
                "source_record_sha256": hashlib.sha256(old_line).hexdigest(),
                "source_raw_response_sha256": a_old["raw_response_sha256"],
                "api_reported_cost_usd": a_old["api_reported_cost_usd"],
            },
        },
        "repair": {"dispatch_ref": a_repair_dispatch, "raw_reply_ref": a_repair_ref},
        "field_source": {"q8": "main", "q9": "repair"},
        "field_updated": {"q8": True, "q9": True},
        "needs_initial_fallback": {"q8": False, "q9": False},
        "effective_q8": 2.5,
        "effective_q9_bins": [0, 0, 0, 0, 100, 0, 0, 0, 0, 0],
        "q9_normalization": "proportional_nonnegative_v1",
    }
    actions_path = root / "outputs/sce_full_a_t0_terminal_20261025_v1/generation_views/view_0001/logical_actions_private.jsonl"
    write_jsonl(actions_path, [action])
    write_json(actions_path.parent / "receipt.json", {"status": "completed", "actual_model_results": True})
    write_json(actions_path.parent / "manifest.json", {"files_sha256": {
        actions_path.name: file_hash(actions_path),
        "receipt.json": file_hash(actions_path.parent / "receipt.json"),
    }})
    write_json(output_root / "sce_full_a_t0_terminal_20261025_v1/generation_receipt.json", {
        "status": "completed",
        "new_api_calls": 1,
        "evaluation": {"command": ["python", str(root / "scripts/analysis.py")],
                       "out": str(root / "outputs/evaluation")},
        "final_overlay": str(root / "outputs/final_overlay.json"),
    })

    raw_order = [a_current, a_repair, b_row, monthly_row, weekly_row]
    model_rows = []
    for index, (run, period, alias, _prompt) in enumerate([
        ("A", "202001", "A_000001", "prompt-a"),
        ("A", "202001", "A_000001", "repair-prompt"),
        ("B", "202511", "B_000001", "prompt-b"),
        ("monthly", "202512", "monthly_000001", "prompt-monthly"),
        ("weekly", "w20260102", "weekly_000001", "prompt-weekly"),
    ], 1):
        row = raw_order[index - 1]
        historical = index == 1
        model_rows.append({
            "response_id": f"response_{index:07d}",
            "run": run,
            "period": period,
            "household": alias,
            "stage": "repair" if index == 2 else "main",
            "prompt_sha256": row["prompt_sha256"],
            "response_text": row["raw_response_text"],
            "original_response_sha256": row["raw_response_sha256"],
            "delivered_response_sha256": row["raw_response_sha256"],
            "response_text_redacted": False,
            "finish_reason": row["finish_reason"],
            "error": row["error"],
            "model": row["returned_model"],
            "provider": row["returned_provider"],
            "reported_cost_usd": row["api_reported_cost_usd"],
            "reservation_if_cost_unknown_usd": 0,
            "tokens": {"prompt_tokens": 22, "completion_tokens": 11, "total_tokens": 33},
            "field_usable": row["field_usable"],
            "actual_model_results": True,
            "physical_new_api_attempt": not historical,
            "historical_exact_prompt_reuse": historical,
        })
    effective = [
        {"run": "A", "period": "202001", "household": "A_000001", "q8": 2.5,
         "q9_bins": [0, 0, 0, 0, 100, 0, 0, 0, 0, 0], "analysis_weight": 1,
         "field_source": {"q8": "main", "q9": "repair"},
         "selected_responses": {"q8": "response_0000001", "q9": "response_0000002"}},
        {"run": "B", "period": "202511", "household": "B_000001", "q8": 2,
         "q9_bins": [0, 0, 0, 0, 100, 0, 0, 0, 0, 0], "analysis_weight": 1,
         "field_source": {"q8": "main", "q9": "main"},
         "selected_responses": {"q8": "response_0000003", "q9": "response_0000003"}},
        {"run": "monthly", "period": "202511", "household": "monthly_000001", "q8": 2,
         "q9_bins": [0, 0, 0, 0, 100, 0, 0, 0, 0, 0], "analysis_weight": 1,
         "field_source": {"q8": "main", "q9": "main"},
         "selected_responses": {"q8": "response_0000003", "q9": "response_0000003"},
         "root_reused": True, "shared_B_root": {"period": "202511", "household": "B_000001"}},
        {"run": "monthly", "period": "202512", "household": "monthly_000001", "q8": 2.1,
         "q9_bins": [0, 0, 0, 0, 100, 0, 0, 0, 0, 0], "analysis_weight": 1,
         "field_source": {"q8": "main", "q9": "main"},
         "selected_responses": {"q8": "response_0000004", "q9": "response_0000004"}},
        {"run": "weekly", "period": "w20260102", "household": "weekly_000001", "q8": 0,
         "q9_bins": [0, 0, 0, 0, 100, 0, 0, 0, 0, 0], "analysis_weight": 1,
         "field_source": {"q8": "retained_previous", "q9": "retained_previous"},
         "selected_responses": {"q8": None, "q9": None}, "fallback": {"reason": "provider timeout"}},
    ]
    data_root = output_root / "sce_micro_reproduction_20261029_v3/data"
    write_gz_jsonl(data_root / "model_outputs.jsonl.gz", model_rows)
    write_gz_jsonl(data_root / "effective_answers.jsonl.gz", effective)
    write_json(data_root / "manifest.json", {
        "files_sha256": {
            "model_outputs.jsonl.gz": file_hash(data_root / "model_outputs.jsonl.gz"),
            "effective_answers.jsonl.gz": file_hash(data_root / "effective_answers.jsonl.gz"),
        },
        "counts": {
            "A_attempts": 2, "B_attempts": 1, "monthly_attempts": 1, "weekly_attempts": 1,
            "A_answers": 1, "B_answers": 1, "monthly_answers": 2, "weekly_answers": 1,
            "A_historical_imports": 1,
        },
        "physical_new_api_attempts": 4,
    })


def test_export_preserves_ids_receipts_and_exact_input_answer_joins(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    build_fixture(root)

    first_dir = tmp_path / "portable_a"
    manifest = portable_evidence.export(first_dir, root=root)
    data = first_dir / "data"
    calls = read_gz_jsonl(data / "call_receipts.jsonl.gz")
    outputs = read_gz_jsonl(data / "model_outputs.jsonl.gz")
    answers = read_gz_jsonl(data / "effective_answers.jsonl.gz")
    inputs = read_gz_jsonl(data / "input_index.jsonl.gz")

    assert manifest["counts"]["attempts"] == 5
    assert manifest["counts"]["request_id_rows"] == 4
    assert manifest["counts"]["missing_request_id_rows"] == 1
    assert manifest["counts"]["missing_request_id_rows_with_error"] == 1
    assert manifest["counts"]["missing_request_id_rows_without_error"] == 0
    assert manifest["counts"]["request_id_on_historical_reuse_rows"] == 1
    assert manifest["counts"]["physical_new_api_attempts"] == 4
    assert manifest["counts"]["started_at_rows"] == manifest["counts"]["finished_at_rows"] == 5
    assert manifest["counts"]["system_fingerprint_null_rows"] == 5
    assert manifest["counts"]["main_input_hash_mismatches"] == 0
    assert manifest["counts"]["input_positions"] == 4
    assert manifest["counts"]["effective_answers"] == 5
    assert manifest["counts"]["receipt_repository_path_values_normalized"] >= 2
    assert len({row["response_id"] for row in calls}) == 5
    assert {row["response_id"] for row in calls} == {row["response_id"] for row in outputs}

    imported = next(row for row in calls if row["historical_exact_prompt_reuse"])
    assert imported["request_id"] == "gen-a-original"
    assert imported["api_reported_cost_usd"] == 0.0
    assert imported["source_api_reported_cost_usd"] == 0.01
    assert imported["started_at_utc"] == "2026-10-25T09:00:00+00:00"
    assert imported["latency_ms"] == 1234.5
    assert imported["usage"]["total_tokens"] == 33
    assert imported["logical_action"]["execution_kind"] == "historical_import"
    assert imported["historical_source_ref"]["source_file_sha256"]
    assert imported["source_dispatch_ref"]["dispatch_at_utc"] == imported["started_at_utc"]

    missing_request = next(row for row in calls if row["request_id"] is None)
    assert missing_request["request_id_source_status"] == "missing_in_source"
    assert missing_request["error"] == "provider timeout"
    assert missing_request["system_fingerprint"] is None

    a_output = next(row for row in outputs if row["run"] == "A" and row["stage"] == "main")
    assert a_output["household"] == "A_000001"  # Compatibility alias remains intact.
    assert a_output["source_agent_id"] == "sce_opaque_a"
    assert a_output["public_sce_userid"] == 314159
    a_answer = next(row for row in answers if row["run"] == "A")
    assert a_answer["selected_responses"] == {"q8": "response_0000001", "q9": "response_0000002"}
    assert a_answer["input_id"] == "input:A:202001:A_000001"

    monthly_root = next(row for row in answers if row["run"] == "monthly" and row["period"] == "202511")
    assert monthly_root["input_join_kind"] == "shared_B_root"
    assert monthly_root["input_origin"]["run"] == "B"
    assert monthly_root["input_origin"]["household"] == "B_000001"
    assert len(inputs) == 4

    alias_map = json.loads((data / "source_agent_id_map.json").read_text())
    public_map = json.loads((data / "public_sce_userid_map.json").read_text())
    assert alias_map["A_000001"] == "sce_opaque_a"
    assert public_map["A_000001"] == 314159

    source_manifest = json.loads((first_dir / "source_provenance.json").read_text())
    sources = {row["source_path"]: row for row in source_manifest["sources"]}
    assert "outputs/sce_full_a_t0_terminal_20261025_v1/main/round_0001/segment_0001/calls_private.jsonl" in sources
    assert any("historical_import_attempt_ledger" in row["roles"] for row in sources.values())
    assert all(not Path(row["source_path"]).is_absolute() for row in source_manifest["sources"])
    bound_call_path = "outputs/sce_full_a_t0_terminal_20261025_v1/main/round_0001/segment_0001/calls_private.jsonl"
    assert sources[bound_call_path]["sha256"] == file_hash(root / bound_call_path)
    assert "outputs/sce_full_a_t0_terminal_20261025_v1/main/round_0001/segment_0001/manifest.json" in sources[bound_call_path]["bound_by"]
    receipt_rows = read_gz_jsonl(data / "actual_call_receipts.jsonl.gz")
    generation = next(row for row in receipt_rows if row["source_path"].endswith("/generation_receipt.json"))
    assert generation["normalized_repository_path_values"] >= 2
    assert generation["receipt"]["evaluation"]["command"] == ["python", "scripts/analysis.py"]
    assert generation["receipt"]["evaluation"]["out"] == "outputs/evaluation"
    assert generation["receipt"]["final_overlay"] == "outputs/final_overlay.json"

    text_to_scan = json.dumps(manifest) + json.dumps(source_manifest)
    assert str(root) not in text_to_scan
    assert "Authorization: Bearer" not in text_to_scan
    assert manifest["integrity"]["new_api_calls"] == 0
    exported_content = json.dumps([calls, outputs, answers, inputs, receipt_rows, manifest, source_manifest,
                                   alias_map, public_map])
    assert "/Users/" not in exported_content
    for relative, details in manifest["files"].items():
        assert file_hash(first_dir / relative) == details["sha256"]

    second_dir = tmp_path / "portable_b"
    second = portable_evidence.export(second_dir, root=root)
    assert manifest["files"] == second["files"]


def test_export_rejects_existing_output_directory(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    build_fixture(root)
    target = tmp_path / "portable"
    target.mkdir()
    with pytest.raises(ValueError, match="fresh output"):
        portable_evidence.export(target, root=root)


def test_export_rejects_call_ledger_that_disagrees_with_source_manifest(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    build_fixture(root)
    ledger = root / "outputs/sce_full_a_t0_terminal_20261025_v1/main/round_0001/segment_0001/calls_private.jsonl"
    ledger.write_text(ledger.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum differs"):
        portable_evidence.export(tmp_path / "portable", root=root)

