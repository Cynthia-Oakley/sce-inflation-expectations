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
import shutil
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
LLM_PROMPT_VERSIONS = (
    "sce-q8-q9-llm-en-v1",
    "sce-q8-q9-v2",
    "sce-q8-q9-v2-abstract",
    "sce-q8-q9-experience-v1",
    "sce-q8-q9-household-state-v1",
    "sce-q8-q9-information-exposure-v1",
    "sce-q8-q9-native-spending-v1",
    "sce-q8-q9-price-contact-v1",
)


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


def _artifact_location(path: Path, runtime_dir: Path) -> str:
    """Label actual inputs, including independently generated monthly packages."""
    path = path.resolve()
    try:
        return str(path.relative_to(runtime_dir.resolve()))
    except ValueError:
        return str(path)


def _save_source_snapshot(runtime_dir: Path, audit_dir: Path) -> dict[str, str]:
    """Preserve the exact executed study code, including uncommitted dependencies."""
    snapshot = audit_dir / "source_snapshot"
    snapshot.mkdir(exist_ok=False)
    hashes = {}
    files = [p for p in runtime_dir.rglob("*.py") if "__pycache__" not in p.parts]
    for src in files:
        rel = src.relative_to(runtime_dir)
        dest = snapshot / "study" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        hashes[str(dest.relative_to(audit_dir))] = _sha256(dest)
    for src, name in ((Path(__file__), "run_sce_local.py"), (runtime_dir / "study.yaml", "study.yaml")):
        dest = snapshot / name
        shutil.copy2(src, dest)
        hashes[str(dest.relative_to(audit_dir))] = _sha256(dest)
    return hashes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", choices=["scripted", "openai"], default="scripted")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--force-export", action="store_true",
                    help="pass --force to export_study_runtime.py (discards derived content)")
    ap.add_argument("--model", default=None, help="requested LLM model (openai mode)")
    ap.add_argument("--prompt-version", choices=LLM_PROMPT_VERSIONS,
                    default="sce-q8-q9-v2-abstract",
                    help="LLM prompt renderer; defaults to v2 with news titles and abstracts")
    ap.add_argument("--max-calls", type=int, default=100, help="hard LLM call budget")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--retry-max", type=int, default=1, help="extra attempts per answer")
    ap.add_argument("--extra-body", default=None,
                    help="JSON object passed as extra_body, e.g. '{\"thinking\": {\"type\": \"disabled\"}}'")
    ap.add_argument("--price-in", type=float, default=None, help="USD per 1M input tokens")
    ap.add_argument("--price-out", type=float, default=None, help="USD per 1M output tokens")
    ap.add_argument("--cost-cap-usd", type=float, default=None)
    ap.add_argument("--population", default=None,
                    help="population artifact to run on, absolute path or relative to the exported study dir "
                         "(default: population/population.json, the 20-person pilot). "
                         "e.g. population/population_real100.json")
    ap.add_argument("--environment", default=None,
                    help="environment artifact, absolute path or relative to the exported study dir "
                         "(default: environment/environment.json, the 2-month dev window). "
                         "e.g. environment/environment_main2021.json")
    ap.add_argument("--simulation", default=None,
                    help="simulation config, absolute path or relative to the exported study dir "
                         "(default: simulation/simulation.json). "
                         "e.g. simulation/simulation_main2021.json")
    ap.add_argument("--mechanism", default=None, help="explicit price-experience arm JSON (repository or absolute path)")
    ap.add_argument("--experience", default=None, help="materialized CE basket JSON; required by basket/focus arms")
    ap.add_argument("--household-state", default=None, help="explicit Q1-only A reconstruction bundle")
    ap.add_argument("--information-exposure", default=None, help="explicit isolated E/P routing bundle")
    ap.add_argument("--confirm-spend", action="store_true",
                    help="required with --llm openai: confirms paid API calls are authorized")
    args = ap.parse_args(argv)

    # The native spending provider is explicitly selected in an isolated
    # simulation artifact; it uses the same audited calls and local engine.
    if args.prompt_version == "sce-q8-q9-native-spending-v1":
        if not args.simulation or args.mechanism or args.experience or args.household_state or args.information_exposure:
            sys.exit("native spending requires an explicit isolated simulation config")

    if args.llm == "openai" and not args.confirm_spend:
        sys.exit("--llm openai spends real API budget; re-run with --confirm-spend after user approval.")
    if args.experience and not args.mechanism:
        sys.exit("--experience requires --mechanism")
    if args.information_exposure and (args.mechanism or args.experience or args.household_state):
        sys.exit("E/P routing requires isolated inputs")
    if args.llm == "openai" and bool(args.information_exposure) != (args.prompt_version == "sce-q8-q9-information-exposure-v1"):
        sys.exit("--information-exposure and its prompt must be selected together")
    if args.llm == "openai" and bool(args.mechanism) != (args.prompt_version == "sce-q8-q9-experience-v1"):
        sys.exit("--mechanism and experience prompt must be selected together; refuse silent unused mechanism")
    if args.mechanism and args.llm == "scripted":
        print("ENGINEERING CHECK ONLY: scripted answers ignore the price-experience mechanism; no behaviour comparison.")
    if args.household_state and (args.mechanism or args.experience):
        sys.exit("Q1-only trial cannot combine price-experience treatments")
    if args.llm == "openai" and bool(args.household_state) != (args.prompt_version == "sce-q8-q9-household-state-v1"):
        sys.exit("--household-state and Q1-only prompt must be selected together")

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
    env_path = (runtime_dir / args.environment) if args.environment else p["environment"]
    sim_path = (runtime_dir / args.simulation) if args.simulation else p["simulation"]
    pop_path = (runtime_dir / args.population) if args.population else p["population"]
    for path, what in ((env_path, "environment"), (sim_path, "simulation"), (pop_path, "population")):
        if not path.is_file():
            sys.exit(f"{what} artifact not found in the exported copy: {path}")
    env_b = validate_handoff(env_path, EnvironmentBundle)
    pop_b = validate_handoff(pop_path, PopulationBundle)
    sim_c = validate_handoff(sim_path, SimulationConfig)
    targets = env_b.provider_args.get("targets") or []
    if sim_c.n_steps != len(targets):
        sys.exit(f"simulation has {sim_c.n_steps} steps but environment has "
                 f"{len(targets)} targets; use a matching development artifact")

    run_id = args.run_id or (f"sce-local-{args.llm}-"
                             f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}")
    audit_dir = REPO_ROOT / "outputs" / "local_runs" / run_id
    audit_dir.mkdir(parents=True, exist_ok=False)

    env_b.provider_args["audit_dir"] = str(audit_dir)
    env_b.provider_args["run_id"] = run_id
    # Bind E's persona view to the population actually being run (the bundle's baked-in
    # persona_by_id belongs to the 20-person pilot; real-P runs need their own profiles).
    env_b.provider_args["persona_by_id"] = {
        pp.agent_id: {**pp.attributes,
                      "weight": int(pp.weight) if float(pp.weight).is_integer() else pp.weight}
        for pp in pop_b.personas
    }

    mechanism_inputs = {}
    household_state_inputs = {}
    exposure_inputs = {}
    native_inputs = {}
    contact_inputs = {}
    contact_ref = "sce_inflation_expectations.price_contact_decision"
    if args.llm == "openai" and ((sim_c.decision_ref == contact_ref) != (args.prompt_version == "sce-q8-q9-price-contact-v1")):
        sys.exit("price contact provider and prompt must be selected together")
    if sim_c.decision_ref == contact_ref:
        from studies.sce_inflation_expectations.price_contact import validate_bundle
        if len(targets) != 1 or args.mechanism or args.experience or args.household_state or args.information_exposure:
            sys.exit("price contact requires an isolated one-month environment")
        if any(k in env_b.provider_args for k in ("information_exposure", "household_state_by_id", "price_experience_mechanism", "experience_by_id")):
            sys.exit("price contact requires a clean common environment")
        contact = validate_bundle(sim_c.decision_args["price_contact_bundle"], pop_b.personas, targets[0]["target_month"])
        if contact["as_of"] != targets[0]["as_of"]:
            sys.exit("price contact cutoff mismatch")
        sim_c.decision_args["price_contact_bundle"] = contact
        contact_inputs = {"arm": contact["arm"], "research_line": contact["research_line"]}
        if args.llm == "scripted":
            print("ENGINEERING CHECK ONLY: scripted answers ignore price-contact treatment.")
    native_ref = "sce_inflation_expectations.native_spending_decision"
    if args.llm == "openai" and ((sim_c.decision_ref == native_ref) != (args.prompt_version == "sce-q8-q9-native-spending-v1")):
        sys.exit("native provider and native prompt must be selected together")
    if sim_c.decision_ref == native_ref:
        from studies.sce_inflation_expectations.native_spending import validate_bundle
        if len(targets) != 1 or args.mechanism or args.experience or args.household_state or args.information_exposure:
            sys.exit("native spending requires an isolated one-month environment")
        if any(k in env_b.provider_args for k in ("information_exposure", "household_state_by_id", "price_experience_mechanism", "experience_by_id")):
            sys.exit("native spending requires a clean baseline environment")
        native = validate_bundle(sim_c.decision_args["native_spending_bundle"], pop_b.personas, targets[0]["target_month"])
        sim_c.decision_args["native_spending_bundle"] = native
        native_inputs = {"arm": native["arm"], "research_line": native["research_line"], "source_sha256": native["source_sha256"]}
        if args.llm == "scripted":
            print("ENGINEERING CHECK ONLY: scripted answers ignore native spending; no behavioural inference.")
    if args.information_exposure:
        from studies.sce_inflation_expectations.information_exposure import validate_bundle, build_exposure_messages
        from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, build_sce_messages_v2
        if len(targets) != 1:
            sys.exit("exposure v1 requires a single-month environment")
        exposure_path = (REPO_ROOT / args.information_exposure).resolve()
        bundle = validate_bundle(json.loads(exposure_path.read_text()), pop_b.personas, targets[0]["target_month"])
        if any(k in env_b.provider_args for k in ("information_exposure", "household_state_by_id", "price_experience_mechanism", "experience_by_id")):
            sys.exit("exposure inputs require a clean explicit environment")
        env_b.provider_args["information_exposure"] = bundle
        exposure_inputs = {"path": str(exposure_path), "sha256": _sha256(exposure_path), "arm": bundle["arm"]}
        check_env = SCEEnvironmentProvider(env_b.model_copy(deep=True))
        check_env.audit_dir = None
        check_env.reset(sim_c.seed)
        check_env.advance_to(1)
        for observation in check_env.observe_batch([p.agent_id for p in pop_b.personas], 1):
            messages = build_exposure_messages(observation, build_sce_messages_v2(observation))
            if len(json.dumps(messages, ensure_ascii=False)) > 16000:
                sys.exit("exposure prompt exceeds size gate")
        if args.llm == "scripted":
            print("ENGINEERING CHECK ONLY: scripted answers ignore E/P routing; no behavioural inference.")
    if args.household_state:
        from studies.sce_inflation_expectations.household_state_mechanism import validate_bundle, build_household_state_messages
        from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, build_sce_messages_v2
        if len(targets) != 1:
            sys.exit("Q1-only v1 requires a single-month environment")
        state_path = (REPO_ROOT / args.household_state).resolve()
        bundle = validate_bundle(json.loads(state_path.read_text()), pop_b.personas, targets[0]["target_month"])
        if any(k in env_b.provider_args for k in ("price_experience_mechanism", "experience_by_id", "household_state_by_id")):
            sys.exit("Q1 inputs require a clean explicit baseline environment")
        env_b.provider_args["household_state_by_id"] = bundle["state_by_id"]
        household_state_inputs = {"path": str(state_path), "sha256": _sha256(state_path),
                                  "research_line": bundle["research_line"]}
        check_env = SCEEnvironmentProvider(env_b.model_copy(deep=True))
        check_env.audit_dir = None
        check_env.reset(sim_c.seed)
        check_env.advance_to(1)
        for observation in check_env.observe_batch([p.agent_id for p in pop_b.personas], 1):
            messages = build_household_state_messages(observation, build_sce_messages_v2(observation, include_event_abstracts=True))
            if len(json.dumps(messages, ensure_ascii=False)) > int(sim_c.decision_args.get("max_prompt_chars", 16000)):
                sys.exit("Q1 prompt exceeds size gate; no calls started")
        if args.llm == "scripted":
            print("ENGINEERING CHECK ONLY: scripted answers ignore Q1; no behavioural inference.")
    if args.mechanism:
        from studies.sce_inflation_expectations.experience_mechanism import validate_config, needs_basket
        from studies.sce_inflation_expectations.price_experience import profile_hash
        mechanism_path = (REPO_ROOT / args.mechanism).resolve()
        config = validate_config(json.loads(mechanism_path.read_text()))
        env_b.provider_args["price_experience_mechanism"] = config
        mechanism_inputs["config"] = {"path": str(mechanism_path), "sha256": _sha256(mechanism_path)}
        if needs_basket(config) and not args.experience:
            sys.exit("selected mechanism arm requires --experience; no synthetic fallback")
        if args.experience:
            experience_path = (REPO_ROOT / args.experience).resolve()
            experience = json.loads(experience_path.read_text())
            if experience.get("schema_version") != "sce-experience-bundle-v1":
                sys.exit("invalid experience bundle schema")
            if experience.get("research_line") != "A_historical_reconstruction":
                sys.exit("this experience bundle must be explicitly labelled A historical reconstruction")
            if len(targets) != 1 or experience.get("target_month") != targets[0]["target_month"]:
                sys.exit("experience v1 is a single-month bundle; use the matching environment")
            baskets = experience["experience_by_id"]
            if set(baskets) != {p.agent_id for p in pop_b.personas}:
                sys.exit("experience IDs must exactly match the run population")
            for persona in pop_b.personas:
                if baskets[persona.agent_id].get("profile_sha256") != profile_hash(persona.attributes):
                    sys.exit("experience profile hash mismatch")
            env_b.provider_args["experience_by_id"] = baskets
            mechanism_inputs["experience"] = {"path": str(experience_path), "sha256": _sha256(experience_path)}
        # Fail before any real calls if an observation cannot construct its state.
        from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, build_sce_messages_v2
        from studies.sce_inflation_expectations.experience_mechanism import build_mechanism_messages
        check_env = SCEEnvironmentProvider(env_b.model_copy(deep=True))
        check_env.audit_dir = None
        check_env.reset(sim_c.seed)
        for step in range(1, sim_c.n_steps + 1):
            check_env.advance_to(step)
            check_observations = check_env.observe_batch([p.agent_id for p in pop_b.personas], step)
            if args.llm == "openai":
                for observation in check_observations:
                    messages = build_mechanism_messages(observation, build_sce_messages_v2(observation, include_event_abstracts=True))
                    if len(json.dumps(messages, ensure_ascii=False)) > int(sim_c.decision_args.get("max_prompt_chars", 16000)):
                        sys.exit("mechanism prompt exceeds configured size gate; no calls started")

    decision_args = {**sim_c.decision_args, "llm_kind": args.llm,
                     "run_id": run_id, "audit_dir": str(audit_dir)}
    if args.llm == "openai":
        extra_body = json.loads(args.extra_body) if args.extra_body else None
        model = args.model or sim_c.decision_args.get("model")
        if not model:
            sys.exit("--llm openai needs --model (pin the requested model explicitly).")
        decision_args.update({
            "prompt_version": args.prompt_version,
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
    # Save the EFFECTIVE bundles, including the P -> E binding and CLI overrides.
    # The framework materializes personas from PopulationBundle; the unrelated
    # historical roster.jsonl in the exported copy is not a run input.
    for name, bundle in (("environment_effective.json", env_b),
                         ("population_effective.json", pop_b),
                         ("simulation_effective.json", sim_c)):
        write_artifact(audit_dir / name, bundle)
    source_snapshot_hashes = _save_source_snapshot(runtime_dir, audit_dir)
    # The effective config is recorded in run_manifest.json, NOT written back into the
    # runtime copy: the copy must stay byte-identical to the export so the one-way
    # export guard (P1) never trips on run records.

    # Run outputs live entirely in the per-run audit dir (store included): the runtime
    # copy stays pristine, and even a --force re-export can never destroy run evidence
    # (P1 lesson, 2026-10-02). Engine live-view files (progress/panel_live/parquet)
    # are written next to the store, so they land here too.
    store_path = audit_dir / "study.duckdb"
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
    started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    hist = sim.run()
    elapsed = time.perf_counter() - t0
    finished_at = datetime.now(timezone.utc).isoformat()
    write_artifact(audit_dir / "metrics_history.json", hist)

    from studies.sce_inflation_expectations.model import self_reported_code_sha256

    manifest = {
        "run_id": run_id,
        "study_id": STUDY_ID,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
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
            "environment": _sha256(env_path),
            "population": _sha256(pop_path),
            "simulation": _sha256(sim_path),
        },
        "effective_artifact_sha256": {name: _sha256(audit_dir / name) for name in
                                      ("population_effective.json", "environment_effective.json", "simulation_effective.json")},
        "source_snapshot_sha256": source_snapshot_hashes,
        "roster_source": "PopulationBundle.personas and their init_state; no roster file read",
        "population_artifact": _artifact_location(pop_path, runtime_dir),
        "environment_artifact": _artifact_location(env_path, runtime_dir),
        "simulation_artifact": _artifact_location(sim_path, runtime_dir),
        "mechanism_inputs": mechanism_inputs,
        "household_state_inputs": household_state_inputs,
        "information_exposure_inputs": exposure_inputs,
        "native_spending_inputs": native_inputs,
        "price_contact_inputs": contact_inputs,
        "native_spending_behaviour_test": bool(native_inputs and args.llm == "openai"),
        "information_exposure_behaviour_test": bool(args.information_exposure and args.llm == "openai"),
        "household_state_behaviour_test": bool(args.household_state and args.llm == "openai"),
        "mechanism_behaviour_test": bool(args.mechanism and args.llm == "openai"),
        "execution_purpose": ("information_exposure_behaviour_trial" if args.llm == "openai" else "information_exposure_plumbing_only") if args.information_exposure else (("household_state_behaviour_trial" if args.llm == "openai" else "household_state_plumbing_only_scripted_answers_ignore_treatment") if args.household_state else (("mechanism_behaviour_trial" if args.llm == "openai" else "mechanism_plumbing_only_scripted_answers_ignore_treatment") if args.mechanism else "baseline_execution")),
        "git": {"research_repo": _git_state(REPO_ROOT), "official_clone": _git_state(OFFICIAL_ROOT)},
        "store_path": str(store_path),
        "cost": sim.decision.cost_summary() if hasattr(sim.decision, "cost_summary") else None,
    }
    if native_inputs:
        manifest["execution_purpose"] = "native_spending_behaviour_trial" if args.llm == "openai" else "native_spending_plumbing_only"
    if contact_inputs:
        manifest["execution_purpose"] = "price_contact_behaviour_trial" if args.llm == "openai" else "price_contact_plumbing_only"
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
