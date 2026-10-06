#!/usr/bin/env python3
"""Prepare a Q1-only paired pilot offline; execute only after fresh approval.

No evaluation file is read by preparation or execution. All real calls use
the official SocioVerse framework and its audited decision provider.
"""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from socioverse.schemas import PopulationBundle, EnvironmentBundle, SimulationConfig
from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, build_sce_messages_v2
from studies.sce_inflation_expectations.household_state_mechanism import (
    SCHEMA, PROMPT_VERSION, validate_bundle, build_household_state_messages,
)
from studies.sce_inflation_expectations.price_experience import profile_hash

MONTHS = ("202105", "202106")
ARMS = ("baseline", "q1_state")
MODEL = "deepseek-flash"
TEMPERATURE = .5  # Preserve the main 300-Core experiment's requested setting.
PRICE_IN, PRICE_OUT = .30, 1.20
PER_JOB_CAP, TOTAL_CAP = .25, 1.0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def select_ids(rows, available_ids, month, n_per_group=10, seed=42):
    allowed = {"date", "userid", "Q1", "_AGE_CAT", "_EDU_CAT", "_HH_INC_CAT", "_REGION_CAT", "_NUM_CAT"}
    selected, states, pools = [], {}, {c: [] for c in range(1, 6)}
    seen = set()
    for row in rows:
        if set(row) - allowed:
            raise ValueError("profile whitelist excludes survey outcomes/weights")
        if str(row["date"]) != month:
            continue
        aid = f"sce_u{int(row['userid'])}"
        if aid in seen:
            raise ValueError("duplicate profile-month")
        seen.add(aid)
        if aid not in available_ids:
            raise ValueError("profile IDs missing from full population")
        code = row["Q1"]
        if isinstance(code, bool) or code not in pools:
            raise ValueError("invalid Q1 category")
        pools[int(code)].append(aid)
    if seen != set(available_ids):
        raise ValueError("profiles must cover the full monthly roster")
    for code, ids in pools.items():
        if len(ids) < n_per_group:
            raise ValueError("insufficient Q1 category; do not silently shrink or duplicate")
        # Independent of answers, weights and input file order.
        ids.sort(key=lambda aid: hashlib.sha256(f"{seed}|{month}|{code}|{aid}".encode()).hexdigest())
        for aid in ids[:n_per_group]:
            selected.append(aid)
            states[aid] = code
    return selected, states, {str(c): len(ids) for c, ids in pools.items()}


def prepare(profiles_path, role_root, environment_root, output):
    origin = json.loads(profiles_path.with_name("summary.json").read_text())
    if origin["candidate_file_hashes"][profiles_path.name] != sha(profiles_path):
        raise ValueError("profiles disagree with audited source")
    rows = [json.loads(line) for line in profiles_path.read_text().splitlines()]
    output.mkdir(parents=True, exist_ok=False)
    plan = {"trial_id": output.name, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "prepared_not_run", "research_line": "A_historical_reconstruction",
            "model": MODEL, "n_per_month": 50, "target_answers": 200, "max_attempts": 200,
            "seed": 42, "temperature_requested": TEMPERATURE,
            "normal_expansion": False, "psychological_module": False,
            "sampling": "10 per Q1 category, hash-ranked from full monthly population; not nationally representative",
            "primary_contrast": "q1_state minus contemporaneously rerun baseline, same selected IDs",
            "evaluation": "same frozen project Q9 scorer for simulated and real raw bins; paired MAE and Q1 group-level fit; spread alone is not success",
            "total_budget_cap_usd": TOTAL_CAP, "per_job_cap_usd": PER_JOB_CAP,
            "prices_usd_per_mtok": {"input": PRICE_IN, "output": PRICE_OUT},
            "pricing_checked_on": "2026-10-06", "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "authorization": {"status": "pending", "destination": "https://api.deepseek.com",
                              "scope": "coarse deidentified demographic profiles, observed Q1 household financial change category, public macroeconomic facts/news; no real inflation answers, weights, IDs or synthetic psychology in API messages"},
            "source_inputs": {str(profiles_path.resolve()): sha(profiles_path)}, "metadata": {}, "records": []}
    for month in MONTHS:
        raw = json.loads((role_root / month / "roles/core/population.json").read_text())
        normal_path = role_root / month / "roles/normal/population.json"
        core_path = role_root / month / "roles/core/population.json"
        plan["source_inputs"].update({str(p.resolve()): sha(p) for p in (normal_path, core_path)})
        all_personas = raw["personas"] + json.loads(normal_path.read_text())["personas"]
        byid = {p["agent_id"]: p for p in all_personas}
        if len(byid) != len(all_personas):
            raise ValueError("duplicate full-population IDs")
        ids, codes, counts = select_ids(rows, byid, month)
        raw["personas"] = [deepcopy(byid[aid]) for aid in ids]
        raw["materialized_count"] = len(ids)
        pop = PopulationBundle.model_validate(raw)
        if any(p.weight != 1 for p in pop.personas):
            raise ValueError("survey weights cannot enter simulated personas")
        permitted = {"age_group", "region", "state", "education_group", "household_income_band", "numeracy", "employment_status", "housing_tenure"}
        if any(set(p.attributes) - permitted for p in pop.personas):
            raise ValueError("unexpected demographic profile fields")
        month_dir = output / month
        month_dir.mkdir()
        write(month_dir / "population.json", pop.model_dump())
        env_path, sim_path = (environment_root / month / f"{n}.json" for n in ("environment", "simulation"))
        plan["source_inputs"].update({str(p.resolve()): sha(p) for p in (env_path, sim_path)})
        env = EnvironmentBundle.model_validate(json.loads(env_path.read_text()))
        sim = SimulationConfig.model_validate(json.loads(sim_path.read_text()))
        if sim.n_steps != 1 or sim.seed != 42 or sim.warm_start is not None or len(env.provider_args["targets"]) != 1:
            raise ValueError("requires one-month, cold-start, seed42 artifacts")
        target = env.provider_args["targets"][0]["target_month"]
        if target.replace("-", "") != month:
            raise ValueError("environment month mismatch")
        for key in ("audit_dir", "run_id", "household_state_by_id", "price_experience_mechanism", "experience_by_id"):
            env.provider_args.pop(key, None)
        env.provider_args["persona_by_id"] = {p.agent_id: p.attributes for p in pop.personas}
        write(month_dir / "environment.json", env.model_dump())
        write(month_dir / "simulation.json", sim.model_dump())
        bundle = {"schema_version": SCHEMA, "research_line": "A_historical_reconstruction",
                  "source": "SCE_Q1_current_microdata", "target_month": target,
                  "state_by_id": {p.agent_id: {"agent_id": p.agent_id, "target_month": target,
                      "financial_change_12m_code": codes[p.agent_id], "profile_sha256": profile_hash(p.attributes)} for p in pop.personas}}
        validate_bundle(bundle, pop.personas, target)
        write(month_dir / "household_state.json", bundle)
        metadata = {"frame_n": len(all_personas), "Q1_frame_counts": counts,
                    "selected_Q1_counts": dict(Counter(codes.values())), "inputs_sha256": {}}
        for arm in ARMS:
            effective = env.model_copy(deep=True)
            if arm == "q1_state":
                effective.provider_args["household_state_by_id"] = bundle["state_by_id"]
            provider = SCEEnvironmentProvider(effective)
            provider.reset(42)
            provider.advance_to(1)
            previews, max_cost = [], 0.
            for ob in provider.observe_batch(ids, 1):
                messages = build_sce_messages_v2(ob, include_event_abstracts=True)
                if arm == "q1_state":
                    messages = build_household_state_messages(ob, messages)
                text = json.dumps(messages, ensure_ascii=False)
                if len(text) > 16000:
                    raise ValueError("prompt-size gate")
                max_cost = max(max_cost, ((len(text.encode()) + 256) * PRICE_IN + 1024 * PRICE_OUT) / 1e6)
                previews.append({"agent_id": ob.agent_id, "messages": messages, "prompt_sha256": hashlib.sha256(text.encode()).hexdigest()})
            if 50 * max_cost > PER_JOB_CAP:
                raise ValueError("50 answers could exceed per-job cap")
            write(month_dir / f"prompt_preview_{arm}.json", previews)
            cmd = [sys.executable, str(ROOT / "scripts/run_sce_local.py"), "--llm", "openai",
                   "--model", MODEL, "--population", str((month_dir / "population.json").resolve()),
                   "--environment", str((month_dir / "environment.json").resolve()),
                   "--simulation", str((month_dir / "simulation.json").resolve()),
                   "--run-id", f"{output.name}-{month}-{arm}", "--temperature", str(TEMPERATURE), "--max-tokens", "1024",
                   "--retry-max", "0", "--max-calls", "50", "--extra-body", '{"thinking":{"type":"disabled"}}',
                   "--price-in", str(PRICE_IN), "--price-out", str(PRICE_OUT), "--cost-cap-usd", str(PER_JOB_CAP),
                   "--confirm-spend", "--prompt-version", PROMPT_VERSION if arm == "q1_state" else "sce-q8-q9-v2-abstract"]
            if arm == "q1_state":
                cmd += ["--household-state", str((month_dir / "household_state.json").resolve())]
            plan["records"].append({"month": month, "arm": arm, "run_id": f"{output.name}-{month}-{arm}",
                                    "output_dir": str(ROOT / "outputs/local_runs" / f"{output.name}-{month}-{arm}"),
                                    "command": cmd, "status": "pending", "request_cost_upper_bound_usd": max_cost})
        metadata["inputs_sha256"] = {str(p.resolve()): sha(p) for p in month_dir.glob("*.json")}
        plan["metadata"][month] = metadata
    # Counterbalance which arm is run first, do not reuse old-model baseline.
    plan["records"][2:] = list(reversed(plan["records"][2:]))
    codes = [Path(__file__), ROOT / "scripts/run_sce_local.py"] + sorted((ROOT / "studies/sce_inflation_expectations").rglob("*.py"))
    snapshot = output / "source_snapshot"
    snapshot.mkdir()
    plan["code_sha256"] = {str(p): sha(p) for p in codes}
    for p in codes:
        dest = snapshot / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(p.read_bytes())
    write(output / "initial_plan.json", plan)
    write(output / "trial_manifest.json", plan)
    return plan


def execute(plan, folder, approval_note):
    if plan["status"] != "prepared_not_run" or not approval_note.strip():
        raise ValueError("requires unused prepared plan and explicit fresh approval note")
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    endpoint = urlparse(os.environ.get("SV_LLM_BASE_URL", ""))
    if endpoint.scheme != "https" or endpoint.hostname != "api.deepseek.com":
        raise ValueError("unexpected API destination")
    if not (os.environ.get("SV_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        raise ValueError("configured API key missing")
    all_hashes = {**plan["code_sha256"], **plan["source_inputs"]}
    for meta in plan["metadata"].values():
        all_hashes.update(meta["inputs_sha256"])
    for path, h in all_hashes.items():
        if sha(path) != h:
            raise ValueError("frozen code/input changed: " + path)
    plan["authorization"].update(status="user_approved", user_quote=approval_note)
    plan["status"] = "running"
    cost, identity = 0., None
    write(folder / "trial_manifest.json", plan)
    for rec in plan["records"]:
        for path, h in all_hashes.items():
            if sha(path) != h:
                raise ValueError("frozen input/code changed between jobs: " + path)
        if cost + PER_JOB_CAP > TOTAL_CAP + 1e-9 or Path(rec["output_dir"]).exists():
            raise ValueError("budget/existing-run gate; never auto-repeat paid attempts")
        rec["status"] = "running"
        write(folder / "trial_manifest.json", plan)
        print("START", rec["month"], rec["arm"], flush=True)
        with (folder / f"{rec['month']}_{rec['arm']}.log").open("w") as log:
            done = subprocess.run(rec["command"], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        rec["exit_code"] = done.returncode
        if done.returncode:
            rec["status"] = "failed"
            plan["status"] = "stopped_run_error"
            write(folder / "trial_manifest.json", plan)
            raise RuntimeError("run failed; inspect saved log; no automatic rerun")
        run = json.loads((Path(rec["output_dir"]) / "run_manifest.json").read_text())
        calls = [json.loads(x) for x in (Path(rec["output_dir"]) / "llm_calls.jsonl").read_text().splitlines()]
        previews = json.loads((folder / rec["month"] / f"prompt_preview_{rec['arm']}.json").read_text())
        expected = {p["agent_id"]: p["messages"] for p in previews}
        if len(calls) != 50 or {c["agent_id"] for c in calls} != set(expected):
            raise RuntimeError("actual call coverage mismatch; stop without rerun")
        for c in calls:
            actual = c.get("messages")
            # The existing provider stores serialized prompt_text, not messages.
            if actual is None:
                actual = json.loads(c["prompt_text"])
            if actual != expected[c["agent_id"]]:
                raise RuntimeError("actual prompt differs from frozen preview; stop")
        tags = sorted({(c["returned_model"], c["system_fingerprint"]) for c in calls if c["error"] is None}, key=str)
        if identity is None:
            identity = tags
        rec.update(status="completed", cost=run["cost"], model_identity=tags,
                   decisions_by_validation_status=run["decisions_by_validation_status"])
        cost += run["cost"]["estimated_cost_usd"]
        plan["estimated_cost_usd"] = cost
        write(folder / "trial_manifest.json", plan)
        if len(tags) != 1 or tags != identity or run["decisions_by_validation_status"] != {"valid": 50}:
            plan["status"] = "stopped_identity_or_validation_change"
            write(folder / "trial_manifest.json", plan)
            raise RuntimeError("model identity/answer gate; preserve outputs and stop")
        print("DONE", rec["month"], rec["arm"], "estimatedUSD", run["cost"]["estimated_cost_usd"], flush=True)
    plan.update(status="completed", finished_at_utc=datetime.now(timezone.utc).isoformat())
    write(folder / "trial_manifest.json", plan)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profiles", type=Path, default=ROOT / "outputs/household_psychology_20261006T133213Z_6de9a161/profile_candidates.jsonl")
    ap.add_argument("--role-root", type=Path, default=ROOT / "outputs/ce_population_baskets_20261006T063749Z_a8be0d98")
    ap.add_argument("--environment-root", type=Path, default=ROOT / "outputs/price_experience_20261006_v1/n20")
    ap.add_argument("--prepared", type=Path)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--approval-note", default="", help="actual new user authorization, never inferred or fabricated")
    a = ap.parse_args()
    if a.execute and not a.approval_note.strip():
        ap.error("paid execution requires a new explicit approval note")
    if a.prepared:
        folder = a.prepared.resolve()
        plan = json.loads((folder / "trial_manifest.json").read_text())
    else:
        folder = ROOT / "outputs" / ("sce_q1_trial_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
        plan = prepare(a.profiles.resolve(), a.role_root.resolve(), a.environment_root.resolve(), folder)
    print("TRIAL_DIR=" + str(folder), flush=True)
    if a.execute:
        execute(plan, folder, a.approval_note)


if __name__ == "__main__":
    main()
