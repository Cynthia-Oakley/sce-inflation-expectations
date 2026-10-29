"""Offline evidence-ingestion checks for the full closed-loop message audit."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.submission_tools import portable_message_replay as replay


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _jsonl_gz(path, rows):
    with Path(path).open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as zipped:
            for row in rows:
                zipped.write((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())


def _evidence(tmp_path, *, corrupt_inner_hash=False):
    root = tmp_path / "evidence"
    data = root / "data"
    data.mkdir(parents=True)
    prompt_hash = "a" * 64
    index_row = dict(run="A", period="202001", source_agent_id="agent-1",
        household="A_000001", input_id="input:A:202001:A_000001",
        original_prompt_sha256=prompt_hash, delivered_prompt_sha256=prompt_hash,
        complete_prompt_source_path="outputs/prompts.jsonl.gz",
        complete_prompt_source_sha256="b" * 64, complete_prompt_source_line=7)
    _jsonl_gz(data / "input_index.jsonl.gz", [index_row])
    outputs = []
    receipts = []
    for stage, response_id, text in (("main", "response-main", '{"point_pct":2}'),
                                     ("repair", "response-repair", '{"point_pct":2,"q9":{}}')):
        digest = hashlib.sha256(text.encode()).hexdigest()
        outputs.append(dict(run="A", period="202001", source_agent_id="agent-1",
            household="A_000001", stage=stage, response_id=response_id,
            input_id=index_row["input_id"], prompt_sha256=prompt_hash,
            response_text=text, original_response_sha256=("0" * 64 if corrupt_inner_hash else digest),
            delivered_response_sha256=digest, response_text_redacted=False,
            finish_reason="stop", error=None, actual_model_results=True))
        receipts.append(dict(run="A", period="202001", source_agent_id="agent-1",
            stage=stage, response_id=response_id, raw_response_sha256=digest,
            source_attempt_ref=dict(path="outputs/raw_calls.jsonl", line=len(receipts) + 1)))
    _jsonl_gz(data / "model_outputs.jsonl.gz", outputs)
    _jsonl_gz(data / "call_receipts.jsonl.gz", receipts)
    source_provenance = dict(schema="sce_portable_evidence_sources/v1", sources=[
        dict(source_path="outputs/prompts.jsonl.gz", sha256="b" * 64)])
    (root / "source_provenance.json").write_text(json.dumps(source_provenance), encoding="utf-8")
    files = {str(path.relative_to(root)): _sha(path) for path in sorted(root.rglob("*")) if path.is_file()}
    manifest = dict(schema="sce_portable_call_evidence/v1", files_sha256=files,
        counts=dict(input_positions=1, attempts=2))
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_load_evidence_joins_source_id_stages_and_receipts_without_calls(tmp_path, monkeypatch):
    evidence_dir = _evidence(tmp_path)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(replay.run, "make_sender", lambda *_: (_ for _ in ()).throw(AssertionError("API sender used")))

    evidence = replay._load_evidence(evidence_dir)
    refs = replay._call_refs(evidence, "A", "202001", "agent-1")

    assert evidence["input_index"][("A", "202001", "agent-1")]["household"] == "A_000001"
    assert refs["main"]["response_id"] == "response-main"
    assert refs["repair"]["response_id"] == "response-repair"
    assert evidence["receipts_by_response"]["response-main"]["source_attempt_ref"]["line"] == 1
    assert len(evidence["raw_text_hashes"]) == 2


def test_load_evidence_rejects_raw_text_that_does_not_match_original_hash(tmp_path):
    evidence_dir = _evidence(tmp_path, corrupt_inner_hash=True)
    with pytest.raises(ValueError, match="Raw response text/hash mismatch"):
        replay._load_evidence(evidence_dir)


def test_density_cache_uses_exact_vectors_and_keeps_failed_scores(tmp_path):
    runtime = tmp_path / "runtime"
    (runtime / "evaluation").mkdir(parents=True)
    bins_ok = [10.0] + [0.0] * 9
    bins_bad = [0.0] * 9 + [100.0]
    _jsonl_gz(runtime / "evaluation/density_cache.jsonl.gz", [
        dict(bins=bins_ok, score=dict(mean=2.5, scorer_status="ok")),
        dict(bins=bins_bad, score=dict(mean=None, scorer_status="triangle_support_out_of_bounds")),
    ])

    path, cache = replay._density_lookup(runtime)

    assert path.name == "density_cache.jsonl.gz"
    assert cache[tuple(bins_ok)] == 2.5
    assert tuple(bins_bad) in cache and cache[tuple(bins_bad)] is None
