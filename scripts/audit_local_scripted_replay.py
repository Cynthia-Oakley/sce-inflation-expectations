#!/usr/bin/env python3
"""Replay audit: local scripted run vs the cloud v3 archive (2026-10-01).

Compares, per agent x runtime step (40 rows):
1. answers      — the action payloads in the local DuckDB store vs the archived
                  answers.jsonl (gz.b64), exact dict equality;
2. observations — the local audit sidecar observations.jsonl vs the archived
                  observations.jsonl, exact dict equality incl. observation_sha256.

Usage: python scripts/audit_local_scripted_replay.py <run_id>
Exit 0 only if every row matches. The archive lives in gitignored data/raw; the
script refuses to run when it is absent (a fresh clone cannot replay-audit).
"""
from __future__ import annotations

import base64
import gzip
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_ROOT = REPO_ROOT.parent / "socioverse2_repo"
V3 = REPO_ROOT / "data" / "raw" / "cloud_exports" / "2026-10-01" / "sce_inflation_expectations_v3"


def _load_archive_answers() -> dict[tuple[str, int], dict]:
    raw = (V3 / "answers.jsonl.gz.b64").read_text().strip()
    text = gzip.decompress(base64.b64decode(raw)).decode()
    return {(r["agent_id"], r["runtime_step"]): r["answer"]
            for r in (json.loads(l) for l in text.splitlines())}


def _load_local_answers(run_id: str) -> dict[tuple[str, int], dict]:
    import duckdb

    store = REPO_ROOT / "outputs" / "local_runs" / run_id / "study.duckdb"
    if not store.exists():  # runs before 2026-10-03 kept the store in the runtime copy
        store = (OFFICIAL_ROOT / "studies" / "sce_inflation_expectations"
                 / "trajectory" / f"{run_id}.duckdb")
    if not store.exists():
        sys.exit(f"store not found for run {run_id} (checked audit dir and runtime copy)")
    con = duckdb.connect(str(store), read_only=True)
    rows = con.execute(
        "SELECT agent_id, step, action_payload FROM panel WHERE step > 0 ORDER BY step, agent_id"
    ).fetchall()
    con.close()
    out = {}
    for agent_id, step, payload in rows:
        out[(agent_id, step)] = json.loads(payload) if isinstance(payload, str) else payload
    return out


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.exit(__doc__)
    run_id = argv[1]
    if not (V3 / "answers.jsonl.gz.b64").exists():
        sys.exit(f"v3 archive missing: {V3} (data/raw is gitignored; cannot replay-audit here)")

    archived = _load_archive_answers()
    local = _load_local_answers(run_id)
    report: dict = {"run_id": run_id}

    missing = sorted(set(archived) - set(local))
    extra = sorted(set(local) - set(archived))
    mismatched = sorted(k for k in set(archived) & set(local) if archived[k] != local[k])
    report["answers"] = {"archived": len(archived), "local": len(local),
                         "missing": missing, "extra": extra,
                         "mismatched": [list(k) for k in mismatched],
                         "identical": not (missing or extra or mismatched)}

    arch_obs = _load_jsonl(V3 / "observations.jsonl")
    local_obs_path = REPO_ROOT / "outputs" / "local_runs" / run_id / "observations.jsonl"
    local_obs = _load_jsonl(local_obs_path) if local_obs_path.exists() else []
    strip = ("run_id",)
    arch_map = {(r["agent_id"], r["runtime_step"]): {k: v for k, v in r.items() if k not in strip}
                for r in arch_obs}
    loc_map = {(r["agent_id"], r["runtime_step"]): {k: v for k, v in r.items() if k not in strip}
               for r in local_obs}
    obs_mismatch = sorted(k for k in set(arch_map) & set(loc_map) if arch_map[k] != loc_map[k])
    report["observations"] = {
        "archived": len(arch_obs), "local": len(local_obs),
        "key_sets_equal": set(arch_map) == set(loc_map),
        "mismatched": [list(k) for k in obs_mismatch],
        "identical_ignoring_run_id": set(arch_map) == set(loc_map) and not obs_mismatch,
    }

    ok = report["answers"]["identical"] and report["observations"]["identical_ignoring_run_id"]
    report["verdict"] = "PASS" if ok else "FAIL"
    out = REPO_ROOT / "outputs" / "local_runs" / run_id / "replay_audit_vs_v3.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"report: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
