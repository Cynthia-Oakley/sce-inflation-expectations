# Closed-loop message replay

2026-10-29. `submission_tools/portable_message_replay.py` adds a zero-network
audit of the complete portable A/B/monthly/weekly workflow. It re-renders the
messages with the original rendering and state functions, then compares their
hashes to the canonical input index. Monthly and weekly successor states come
only from archived raw main/repair response text; the monthly November root is
replayed from B's November raw responses, joined on original source Agent ID.
The audit does not open `effective_answers`, score targets, or truth data. It
uses the runtime's exact-vector density cache for the state history center and
had no cache misses in the full run.

## API and output

Python API:

```python
from studies.sce_inflation_expectations.submission_tools.portable_message_replay import audit
report = audit(runtime_data, evidence_dir, out)
```

The CLI accepts `--runtime-data`, `--evidence-dir`, and `--out`. The destination
must be new. It writes `report.json`, `manifest.json`, and deterministic
`replay_trace.jsonl.gz`. The trace has one row per rendered task message and
records the original source Agent ID, canonical prompt source path/line/hash,
replayed hash, before/after state hashes, raw response IDs/hashes, and the
original call/dispatch ledger references. It contains no copied raw response
text.

## Full frozen-data result

Local validation used:

- Runtime: `outputs/sce_portable_runtime_20261029_v2/index.json`, SHA-256
  `7a42e60b4af0ac1122ae08edfee075f2771e8c67fbc166a26243e2cc99df5036`.
- Call evidence manifest: `outputs/sce_portable_evidence_20261029_v1/manifest.json`,
  SHA-256 `369538b9cf99d6b8dfa884bd5b715c6e5fc947c24de3c8e4fd2c20cff1b13a01`.
- Source index: `outputs/sce_portable_evidence_20261029_v1/source_provenance.json`,
  SHA-256 `8107518af1ad2cd6ece7942337fbfea0de477a1bd14ee63fb918fd904e166806`,
  with 837 named source-path/hash bindings.
- Audit output: `outputs/sce_portable_message_replay_20261029_v1/`.

All 66,822 unique canonical input positions were referenced. The task-specific
render count is 67,334 because the 512 monthly root prompts are re-rendered and
checked against those same B November canonical inputs. Hash matches were A
41,970/41,970, B 5,632/5,632, monthly 5,632/5,632, and weekly 14,100/14,100;
there were zero prompt-hash mismatches.

All 67,147 raw response texts passed their original and delivered SHA-256
checks, and all 67,147 joined their call receipts by response ID and source
identity. The monthly chain consumed the 512 original B November main replies
and their repairs as its fresh root, then advanced across 5,120 monthly replies.
The 5,632 monthly recursive steps and all 14,100 weekly steps were advanced
from raw archived main/repair replies, with same-household state checks. The
exact-vector density cache had 46,675 entries, 19,729 hits, and zero misses.

The report records zero API calls, no network access, no credential reads, no
score-target reads, and no use of historical effective-answer rows as state.
Hashes establish local file consistency and joinability; they do not claim a
provider-signed authenticity guarantee.

Validation command:

```sh
/Users/wushuyue/anaconda3/envs/socioverse/bin/python -m pytest tests/test_sce_portable_message_replay.py -q
```

Result: 3 focused offline tests passed for identity/stage joins, receipt/raw
text hashes, rejected tampering, and exact cached density lookup.
