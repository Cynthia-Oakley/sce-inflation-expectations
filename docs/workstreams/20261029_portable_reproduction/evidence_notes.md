# Portable call evidence

2026-10-29. Added an offline exporter for the four frozen final tasks. It reads
only the explicit source roots and manifests listed in
`submission_tools/portable_evidence.py`. It made no API calls and did not alter
the frozen run directories or the v11 submission package.

## Export

The API is `export(out, root=ROOT)` in
`studies/sce_inflation_expectations/submission_tools/portable_evidence.py`.
It rejects an existing output directory and writes stable gzip files with a
fixed timestamp and no machine-specific gzip filename. For local validation,
the current output is `outputs/sce_portable_evidence_20261029_v1/`.

The output contains:

- `data/model_outputs.jsonl.gz`: existing raw response rows, with the existing
  household alias retained and source Agent ID, public SCE userid where
  applicable, and `input_id` added.
- `data/effective_answers.jsonl.gz`: existing effective answer rows with an
  answer ID, source identifiers, selected `response_id` values, fallback data,
  and input provenance. The monthly 2025-11 root answer points to its reused B
  input via `input_join_kind=shared_B_root`.
- `data/call_receipts.jsonl.gz`: one row per raw attempt, linked to model output
  by `response_id`. It preserves original request ID, dispatch time, start/end
  times, latency, model/provider, complete usage and token metadata, recorded
  cost and reservation, errors, raw response hash, stage, source line numbers,
  and A's logical-action/repair/historical-import references.
- `data/input_index.jsonl.gz`: one record per complete prompt slot, with exact
  source path/line/hash and `input_id`. It does not copy or rewrite messages;
  the referenced full prompt file is hash-bound in the provenance index.
- `data/source_agent_id_map.json`: the original alias-to-internal-Agent-ID
  code map, preserved byte for byte. These are opaque research IDs, not names.
- `data/public_sce_userid_map.json` and `data/agent_id_crosswalk.jsonl.gz`:
  the 10,743 A aliases mapped to original public SCE userid values, plus the
  four-task alias-to-source-ID crosswalk.
- `data/actual_call_receipts.jsonl.gz`: 287 actual segment, wave, generation,
  and run receipt records, each with its original relative path and file hash.
  Receipt fields are preserved; absolute prefixes matching the repository root
  are converted to repository-relative paths.
- `source_provenance.json`: repository-relative source paths, SHA-256 values,
  adjacent manifest bindings, roles, and available row counts.
- `manifest.json`: output file hashes/counts, join contracts, evidence counts,
  and limits on the provenance claim.

## Offline checks

The live frozen sources yielded 66,822 complete input positions, 67,334
effective-answer rows, and 67,147 raw model attempts: A 42,211, B 5,648,
monthly 5,160, and weekly 14,128. All 67,147 call rows join one-to-one to the
existing response IDs by `(run, period, household alias, stage)`; the exporter
also compares response text and SHA-256. Each main request's prompt hash
matches its canonical complete input. Monthly's extra 512 effective root rows
reuse the B 2025-11 inputs and are linked explicitly.

There are 66,831 unique source request IDs and 316 rows with no request ID; the
316 are source error rows, and no ID is synthesized. Of the present IDs, 66,649
belong to physical new attempts and 182 to exact historical imports. All 67,147
records have start and finish timestamps. All 67,147 system fingerprints are
null and stay null. The source records identify 66,965 physical new API
attempts; the 182 imported rows are not counted as new attempts. The imported
rows preserve their original request IDs, cost/usage values, and pinned
historical source ledger path/hash; the current ledger's zero cost/reservation
remains distinct from its separately preserved source cost/reservation.

The local output contains no response text redactions. `source_provenance.json`
names each source file and hash; call and dispatch records also carry their
source line references. The exporter verifies adjacent source manifests,
checks imported A source-record hashes, and rewrites the local repository-root
prefix in receipt fields while keeping the original receipt SHA-256. This
keeps receipt fields intact; the recorded Python executable path outside the
project root remains verbatim as runtime provenance. The top-level manifest
and source-provenance index contain only repository-relative paths. This
supports local byte-level verification; it does not claim a provider-signed
authenticity guarantee.

Validation command:

```sh
python -m pytest tests/test_sce_portable_evidence.py -q
```

Result: 3 offline fixture tests passed, including exact response/input/answer
joins, historical import and repair linkage, null request-ID handling,
deterministic output hashes, repository-path normalization, and source-manifest
mismatch rejection.
