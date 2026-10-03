#!/usr/bin/env python3
"""Local SCE run entry — export the study one-way, run it in the official clone, audit fully.

    python scripts/run_sce_local.py                        # scripted, offline, no key
    python scripts/run_sce_local.py --llm openai --model deepseek-flash --max-calls 100 \
        --extra-body '{"thinking": {"type": "disabled"}}' --confirm-spend

Pipeline: export_study_runtime.py refreshes the runtime copy under
socioverse2_repo/studies/ (refusing to clobber derived content unless
--force-export), then the run executes against THAT copy via
socioverse.engine.build_simulator. Every run gets a fresh run_id; outputs never
overwrite a previous run:

- trajectory store:  socioverse2_repo/studies/sce_inflation_expectations/trajectory/<run_id>.duckdb
- audit sidecar:     outputs/local_runs/<run_id>/  (observations.jsonl, llm_calls.jsonl,
                     metrics_history.json, cost_ledger.json, run_manifest.json)

--llm openai spends real money: it requires --confirm-spend and an explicit
--max-calls budget, and needs SV_LLM_API_KEY (env or the official clone's .env).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_ROOT = REPO_ROOT.parent / "socioverse2_repo"
STUDY_ID = "sce_inflation_expectations"


def _git_state(root: Path) -> dict:
    def _git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(root), *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    return {"root": str(root), "head": _git("rev-parse", "HEAD"),
            "dirty": bool(_git("status", "--porcelain"))}


def _sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", choices=["scripted", "openai"], default="scripted")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--force-export", action="store_true",
                    help="pass --force to export_study_runtime.py (discards derived content)")
    ap.add_argument("--model", default=None, help="requested LLM model (openai mode)")
    ap.add_argument("--max-calls", type=int, default=100, help="hard LLM call budget")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--retry-max", type=int, default=1, help="extra attempts per answer")
    ap.add_argument("--extra-body", default=None,
                    help="JSON object passed as extra_body, e.g. '{\"thinking\": {\"type\": \"disabled\"}}'")
    ap.add_argument("--price-in", type=float, default=None, help="USD per 1M input tokens")
    ap.add_argument("--price-out", type=float, default=None, help="USD per 1M output tokens")
    ap.add_argument("--cost-cap-usd", type=float, default=None)
    ap.add_argument("--confirm-spend", action="store_true",
                    help="required with --llm openai: confirms paid API calls are authorized")
    args = ap.parse_args(argv)

    if args.llm == "openai" and not args.confirm_spend:
        sys.exit("--llm openai spends real API budget; re-run with --confirm-spend after user approval.")

    # 1. one-way export of the maintained source into the official clone
    export_cmd = [sys.executable, str(REPO_ROOT / "scripts" / "export_study_runtime.py")]
    if args.force_export:
        export_cmd.append("--force")
    proc = subprocess.run(export_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout + proc.stderr)
        sys.exit("export failed; resolve the runtime-copy conflict (see above) or use --force-export.")

    # 2. load the runtime copy through the official framework
    if str(OFFICIAL_ROOT) not in sys.path:
        sys.path.insert(0, str(OFFICIAL_ROOT))
    import studies.sce_inflation_expectations  # noqa: F401  (registers providers from the COPY)
    from skills.sv_workspace import load_study_yaml, study_paths
    from socioverse.engine import build_simulator
    from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
    from socioverse.validation import validate_handoff, write_artifact

    runtime_dir = OFFICIAL_ROOT / "studies" / STUDY_ID
    p = study_paths(runtime_dir)
    study = load_study_yaml(p["study"])
    env_b = validate_handoff(p["environment"], EnvironmentBundle)
    pop_b = validate_handoff(p["population"], PopulationBundle)
    sim_c = validate_handoff(p["simulation"], SimulationConfig)

    run_id = args.run_id or (f"sce-local-{args.llm}-"
                             f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}")
    audit_dir = REPO_ROOT / "outputs" / "local_runs" / run_id
    audit_dir.mkdir(parents=True, exist_ok=False)

    env_b.provider_args["audit_dir"] = str(audit_dir)
    env_b.provider_args["run_id"] = run_id

    decision_args = {**sim_c.decision_args, "llm_kind": args.llm,
                     "run_id": run_id, "audit_dir": str(audit_dir)}
    if args.llm == "openai":
        extra_body = json.loads(args.extra_body) if args.extra_body else None
        model = args.model or sim_c.decision_args.get("model")
        if not model:
            sys.exit("--llm openai needs --model (pin the requested model explicitly).")
        decision_args.update({
            "prompt_version": "sce-q8-q9-llm-en-v1",
            "model": model,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "max_calls": args.max_calls,
            "retry_max": args.retry_max,
            "extra_body": extra_body,
            "price_input_per_mtok": args.price_in,
            "price_output_per_mtok": args.price_out,
            "cost_cap_usd": args.cost_cap_usd,
        })
    sim_c.decision_args = decision_args
    # The effective config is recorded in run_manifest.json, NOT written back into the
    # runtime copy: the copy must stay byte-identical to the export so the one-way
    # export guard (P1) never trips on run records.

    store_path = runtime_dir / "trajectory" / f"{run_id}.duckdb"
    store_path.parent.mkdir(parents=True, exist_ok=True)
    sim = build_simulator(env_bundle=env_b, pop_bundle=pop_b, sim_config=sim_c,
                          store_path=store_path)

    sources: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    decide = sim.decision.decide_batch

    def counted(obs, memories):
        actions = decide(obs, memories)
        sources.update(a.source for a in actions)
        statuses.update(str(a.payload.get("validation_status", "?")) for a in actions)
        return actions

    sim.decision.decide_batch = counted

    print(f"Running {STUDY_ID} locally: {len(pop_b.personas)} agents, {sim_c.n_steps} steps, "
          f"llm_kind={args.llm}, run_id={run_id}")
    t0 = time.perf_counter()
    hist = sim.run()
    elapsed = time.perf_counter() - t0
    write_artifact(audit_dir / "metrics_history.json", hist)

    from studies.sce_inflation_expectations.model import self_reported_code_sha256

    manifest = {
        "run_id": run_id,
        "study_id": STUDY_ID,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "llm_kind": args.llm,
        "decision_args": {k: v for k, v in decision_args.items()},
        "n_agents": len(pop_b.personas),
        "n_steps": sim_c.n_steps,
        "seed": sim_c.seed,
        "wall_time_s": round(elapsed, 2),
        "decisions_by_source": dict(sources),
        "decisions_by_validation_status": dict(statuses),
        "model_code_sha256_self_reported": self_reported_code_sha256(),
        "artifact_sha256": {
            "study.yaml": _sha256(p["study"]),
            "environment.json": _sha256(p["environment"]),
            "population.json": _sha256(p["population"]),
            "roster.jsonl": _sha256(p["roster"]),
            "simulation.json": _sha256(p["simulation"]),
        },
        "git": {"research_repo": _git_state(REPO_ROOT), "official_clone": _git_state(OFFICIAL_ROOT)},
        "store_path": str(store_path),
        "cost": sim.decision.cost_summary() if hasattr(sim.decision, "cost_summary") else None,
    }
    (audit_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if hasattr(sim.decision, "cost_summary"):
        ledger = {"run_id": run_id, **sim.decision.cost_summary()}
        (audit_dir / "cost_ledger.json").write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for row in hist.rows:
        print(row)
    print(f"\nDecisions by source: {dict(sources)}  status: {dict(statuses)}  ({elapsed:.1f} s)")
    if hasattr(sim.decision, "cost_summary"):
        print(f"Cost ledger: {sim.decision.cost_summary()}")
    print(f"Audit dir: {audit_dir}")
    print(f"Store: {store_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
