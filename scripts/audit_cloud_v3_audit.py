#!/usr/bin/env python3
"""Independently audit the v3 scripted audit-run artifacts retrieved from the platform.

Run: python scripts/audit_cloud_v3_audit.py

Archive: data/raw/cloud_exports/2026-10-01/sce_inflation_expectations_v3/
(retrieved via chat chunking; gzip+base64 channel verified byte-exact against
the platform's audit_manifest.sha256).

Checks:
1. All five audit files hash to the entries in audit_manifest.sha256.
2. run_manifest.json / cost_ledger.json internal consistency (run_id, counts,
   scripted zero-call ledger with billing_status=not_available).
3. observations.jsonl: 40 rows = 20 agents x 2 steps; every
   observation_sha256 recomputed as SHA-256 of the compact JSON
   (separators=(",",":"), ensure_ascii=False) of the embedded observation;
   run_id matches the manifest; E as_of values obey the month cutoff rule.
4. answers.jsonl: 40 rows; run_id matches; Q9 bins sum to 100; Q8 sign/magnitude
   consistency; and — because v3 deliberately kept P/E/B/seed identical to v2 —
   every answer field must equal the archived v2 raw answer for the same
   agent and as_of. A mismatch means the scripted behavior is not reproducible.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "data/raw/cloud_exports/2026-10-01/sce_inflation_expectations_v3"
V2_RAW = ROOT / ("data/raw/cloud_exports/2026-09-30/"
                 "sce_inflation_expectations_v2/raw_q8_q9.jsonl")

EXPECTED = {
    "run_id": "sce_inflation_expectations-v3-2c40f389c0d24e1ab1e963918b3bfec9",
    "files": {
        "answers.jsonl": (31040, 40),
        "cost_ledger.json": (317, None),
        "observations.jsonl": (101686, 40),
        "run_manifest.json": (538, None),
        "audit_manifest.sha256": (422, None),
        "validation_errors.jsonl": (0, 0),
    },
    "as_of_by_step": {1: "2021-04-30T23:59:59-04:00", 2: "2021-05-31T23:59:59-04:00"},
}
ANSWER_FIELDS = (
    ["point_pct", "magnitude_pct", "direction", "q9_sum", "seed", "model_version",
     "prompt_version", "e_snapshot_id", "p_snapshot_id", "validation_status"]
    + [f"q9_bin{i}" for i in range(1, 11)]
)


def observation_sha256(observation: dict) -> str:
    """Platform's hash: SHA-256 over compact sorted-key JSON, ensure_ascii=False.

    Matches v3 model.py `_audit_observations`: json.dumps(ob.model_dump(),
    ensure_ascii=False, sort_keys=True, separators=(",", ":")). Step-1
    observations are pure ASCII so ensure_ascii does not matter there;
    step-2 records contain non-ASCII and only ensure_ascii=False reproduces
    the platform hash (40/40).
    """
    blob = json.dumps(observation, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def main() -> dict:
    report: dict = {"archive": str(V3)}

    # 1. file hashes vs audit_manifest.sha256
    manifest_entries = {}
    for line in (V3 / "audit_manifest.sha256").read_text().splitlines():
        digest, name = line.split()
        manifest_entries[name] = digest
    # validation_errors.jsonl was empty on the platform; not retrieved (no content
    # to transcribe) — its manifest entry must be the empty-file hash.
    assert manifest_entries["validation_errors.jsonl"] == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    file_checks = {}
    for name in ("run_manifest.json", "cost_ledger.json",
                 "observations.jsonl", "answers.jsonl", "audit_manifest.sha256"):
        data = (V3 / name).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        size_ok = len(data) == EXPECTED["files"][name][0]
        file_checks[name] = {"bytes": len(data), "sha256": digest,
                             "size_matches_platform": size_ok}
        assert size_ok, f"{name}: {len(data)} bytes != platform size"
        if name in manifest_entries:
            assert digest == manifest_entries[name], f"{name}: hash mismatch"
    report["file_checks"] = file_checks

    # 2. manifests
    run = json.loads((V3 / "run_manifest.json").read_text())
    assert run["run_id"] == EXPECTED["run_id"]
    assert (run["n_agents"], run["n_steps"], run["answer_rows"]) == (20, 2, 40)
    assert run["mode"] == "scripted" and run["seed"] == 42 and run["status"] == "completed"
    ledger = json.loads((V3 / "cost_ledger.json").read_text())
    assert ledger["run_id"] == EXPECTED["run_id"]
    assert ledger["billing_status"] == "not_available" and ledger["verified_usd"] is None
    assert (ledger["real_llm_calls"], ledger["event_mcp_calls"],
            ledger["population_mcp_calls"]) == (0, 0, 0)
    report["run_manifest"] = {"run_id": run["run_id"], "started_at": run["started_at"],
                              "finished_at": run["finished_at"]}
    report["cost_ledger"] = ledger

    # 3. observations
    obs = [json.loads(l) for l in (V3 / "observations.jsonl").read_text().splitlines()]
    assert len(obs) == 40
    assert {(r["agent_id"], r["runtime_step"]) for r in obs} == {
        (f"smoke_{i:03d}", s) for i in range(1, 21) for s in (1, 2)}
    sha_ok = 0
    for r in obs:
        assert r["run_id"] == EXPECTED["run_id"]
        o = r["observation"]
        assert o["macro_information"]["as_of"] == EXPECTED["as_of_by_step"][r["runtime_step"]]
        sha_ok += observation_sha256(o) == r["observation_sha256"]
    assert sha_ok == 40, f"observation_sha256 recomputed for {sha_ok}/40"
    report["observations"] = {"rows": 40, "sha256_self_consistent": sha_ok}

    # 4. answers: internal consistency + equality with the v2 archive
    ans = [json.loads(l) for l in (V3 / "answers.jsonl").read_text().splitlines()]
    assert len(ans) == 40
    v2 = [json.loads(l) for l in V2_RAW.read_text().splitlines()]
    identical = 0
    for r in ans:
        assert r["run_id"] == EXPECTED["run_id"]
        a = r["answer"]
        probs = [Decimal(str(a[f"q9_bin{i}"])) for i in range(1, 11)]
        assert sum(probs) == Decimal(100) == Decimal(str(a["q9_sum"]))
        point = Decimal(str(a["point_pct"]))
        magnitude = Decimal(str(a["magnitude_pct"]))
        assert magnitude >= 0
        assert point == (magnitude if a["direction"] == "inflation" else -magnitude)
        v2rows = [v for v in v2 if v["agent_id"] == r["agent_id"] and v["as_of"] == a["as_of"]]
        assert len(v2rows) == 1, (r["agent_id"], a["as_of"])
        v = v2rows[0]
        mismatched = [f for f in ANSWER_FIELDS if str(v.get(f)) != str(a.get(f))]
        assert not mismatched, (r["agent_id"], a["as_of"], mismatched)
        identical += 1
    report["answers"] = {"rows": 40, "identical_to_v2_archive": identical}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return report


if __name__ == "__main__":
    main()
