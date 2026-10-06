#!/usr/bin/env python3
"""Prepare an isolated E/P routing trial; paid execution needs explicit approval.

No evaluation truth is loaded here. SocioVerse runs and audits every decision.
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
from urllib.parse import urlparse
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from socioverse.schemas import PopulationBundle, EnvironmentBundle, SimulationConfig
from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, build_sce_messages_v2
from studies.sce_inflation_expectations.information_exposure import (
    SCHEMA, PROMPT_VERSION, ARMS, route_channel, shuffled_channels,
    select_diagnostic_ids, validate_bundle, build_exposure_messages,
)

MONTHS = ("202105", "202106")
N = 48
MODEL = "deepseek-flash"
PRICE_IN, PRICE_OUT = .30, 1.20
JOB_CAP, TOTAL_CAP = .16, 1.00


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def prepare(role_root, environment_root, output):
    output.mkdir(parents=True, exist_ok=False)
    plan = {"trial_id": output.name, "status": "prepared_not_run",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "research_line": "A_historical_reconstruction", "n_per_month": N,
            "target_answers": N * 6, "max_attempts": N * 6, "seed": 42,
            "model": MODEL, "temperature_requested": .5, "normal_expansion": False,
            "total_budget_cap_usd": TOTAL_CAP, "per_job_cap_usd": JOB_CAP,
            "prices_usd_per_mtok": {"input": PRICE_IN, "output": PRICE_OUT},
            "pricing_reference_date": "2026-10-06", "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "primary_contrast": "matched minus shuffled; identical multiset of numeric information packages",
            "evaluation": "common-case paired Q9 MAE, distribution distance, IQR gap; spread alone is not success; equal-channel diagnostic sample only",
            "news_policy": "off_all_arms; retained in source ledger, not model messages",
            "CE_rule_status": "unestimated_design_assumption_not_measured_attention",
            "authorization": {"status": "pending", "destination": "https://api.deepseek.com",
                "scope": "coarse deidentified demographics, synthetic CE spending shares, historical public numeric facts; no real inflation answers, weights, IDs, Q1 or GSS"},
            "source_inputs": {}, "metadata": {}, "records": []}
    for month in MONTHS:
        paths = [role_root / month / "roles" / role / "population.json" for role in ("core", "normal")]
        basket_path = role_root / month / "experience.json"
        source_pop = json.loads(paths[0].read_text())
        other_pop = json.loads(paths[1].read_text())
        full = source_pop["personas"] + other_pop["personas"]
        if len({p["agent_id"] for p in full}) != len(full):
            raise ValueError("duplicate population IDs")
        source_pop["personas"] = full
        source_pop["materialized_count"] = len(full)
        frame = PopulationBundle.model_validate(source_pop)
        baskets = json.loads(basket_path.read_text())["experience_by_id"]
        ids, support = select_diagnostic_ids(frame.personas, baskets)
        by_id = {p.agent_id: p for p in frame.personas}
        pop = frame.model_copy(deep=True)
        pop.personas = [by_id[aid] for aid in ids]
        pop.materialized_count = N
        permitted = {"age_group", "region", "state", "education_group", "household_income_band", "numeracy", "employment_status", "housing_tenure"}
        if any(p.weight != 1 or set(p.attributes) - permitted for p in pop.personas):
            raise ValueError("population input whitelist/weight violation")
        d = output / month
        d.mkdir()
        write(d / "population.json", pop.model_dump())
        env_path, sim_path = [environment_root / month / f"{name}.json" for name in ("environment", "simulation")]
        plan["source_inputs"].update({str(p.resolve()): sha(p) for p in paths + [basket_path, env_path, sim_path]})
        env = EnvironmentBundle.model_validate(json.loads(env_path.read_text()))
        sim = SimulationConfig.model_validate(json.loads(sim_path.read_text()))
        if sim.n_steps != 1 or sim.seed != 42 or sim.warm_start is not None or len(env.provider_args["targets"]) != 1:
            raise ValueError("requires one-month cold-start seed42")
        target = env.provider_args["targets"][0]["target_month"]
        if target.replace("-", "") != month:
            raise ValueError("environment target mismatch")
        for key in ("audit_dir", "run_id", "household_state_by_id", "price_experience_mechanism", "experience_by_id", "information_exposure"):
            env.provider_args.pop(key, None)
        env.provider_args["persona_by_id"] = {p.agent_id: p.attributes for p in pop.personas}
        write(d / "environment.json", env.model_dump())
        write(d / "simulation.json", sim.model_dump())
        channels = {aid: route_channel(aid, baskets[aid]["spending_shares"]) for aid in ids}
        shuffled, donor = shuffled_channels(ids, channels)
        metadata = {"frame_n": len(full), "frame_channel_counts": support,
                    "selected_channel_counts": dict(Counter(channels.values())),
                    "shuffled_channel_counts": dict(Counter(shuffled.values())),
                    "shuffle_same_channel_count": sum(channels[aid] == shuffled[aid] for aid in ids),
                    "shuffle_donor_by_id": donor, "as_of": env.provider_args["targets"][0]["as_of"],
                    "inputs_sha256": {}}
        for arm in ARMS:
            bundle = {"schema_version": SCHEMA, "research_line": "A_historical_reconstruction",
                      "target_month": target, "arm": arm, "news_policy": "off_all_arms",
                      "routing_rule": "conditional_ce_share_draw_seed42_v1",
                      "rows": {aid: {"agent_id": aid, "profile_sha256": baskets[aid]["profile_sha256"],
                          "spending_shares": baskets[aid]["spending_shares"], "intended_channel": channels[aid],
                          "delivered_channel": shuffled[aid] if arm == "shuffled" else channels[aid]} for aid in ids}}
            validate_bundle(bundle, pop.personas, target)
            write(d / f"exposure_{arm}.json", bundle)
            effective = env.model_copy(deep=True)
            effective.provider_args["information_exposure"] = bundle
            provider = SCEEnvironmentProvider(effective)
            provider.reset(42)
            provider.advance_to(1)
            previews, bounds = [], []
            for ob in provider.observe_batch(ids, 1):
                messages = build_exposure_messages(ob, build_sce_messages_v2(ob))
                text = json.dumps(messages, ensure_ascii=False)
                if len(text) > 16000:
                    raise ValueError("prompt too long")
                bounds.append(((len(text.encode()) + 256) * PRICE_IN + 1024 * PRICE_OUT) / 1e6)
                previews.append({"agent_id": ob.agent_id, "messages": messages, "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(),
                                 "visible_signal_ids": ob.local_information["information_exposure"]["visible_signal_ids"]})
            if N * max(bounds) > JOB_CAP:
                raise ValueError("reserve exceeds job cap")
            write(d / f"prompt_preview_{arm}.json", previews)
            (d / f"sample_prompt_{arm}.txt").write_text(previews[0]["messages"][0]["content"] + "\n")
            run_id = f"{output.name}-{month}-{arm}"
            command = [sys.executable, str(ROOT / "scripts/run_sce_local.py"), "--llm", "openai", "--model", MODEL,
                       "--population", str(d / "population.json"), "--environment", str(d / "environment.json"),
                       "--simulation", str(d / "simulation.json"), "--information-exposure", str(d / f"exposure_{arm}.json"),
                       "--prompt-version", PROMPT_VERSION, "--run-id", run_id, "--temperature", "0.5",
                       "--max-tokens", "1024", "--retry-max", "0", "--max-calls", str(N),
                       "--extra-body", '{"thinking":{"type":"disabled"}}', "--price-in", str(PRICE_IN),
                       "--price-out", str(PRICE_OUT), "--cost-cap-usd", str(JOB_CAP), "--confirm-spend"]
            plan["records"].append({"month": month, "arm": arm, "run_id": run_id,
                "output_dir": str(ROOT / "outputs/local_runs" / run_id), "command": command, "status": "pending",
                "max_request_reserve_usd": max(bounds), "all_request_reserve_usd": sum(bounds),
                "max_prompt_bytes": max(len(json.dumps(p["messages"], ensure_ascii=False).encode()) for p in previews)})
        metadata["inputs_sha256"] = {str(p.resolve()): sha(p) for p in d.iterdir() if p.is_file()}
        plan["metadata"][month] = metadata
    # Reverse June order; don't reuse different-renderer historical baselines.
    plan["records"][3:] = list(reversed(plan["records"][3:]))
    codes = [Path(__file__), ROOT / "scripts/run_sce_local.py", ROOT / "scripts/analyze_sce_information_exposure_trial.py"] + sorted((ROOT / "studies/sce_inflation_expectations").rglob("*.py"))
    plan["code_sha256"] = {str(p): sha(p) for p in codes}
    for p in codes:
        dest = output / "source_snapshot" / p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(p.read_bytes())
    plan["max_call_reserve_total_usd"] = sum(r["all_request_reserve_usd"] for r in plan["records"])
    write(output / "initial_plan.json", plan)
    write(output / "trial_manifest.json", plan)
    return plan


def execute(plan, folder, approval_note):
    if plan["status"] != "prepared_not_run" or not approval_note.strip():
        raise ValueError("unused prepared plan and actual fresh user approval required")
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    endpoint = urlparse(os.environ.get("SV_LLM_BASE_URL", ""))
    if endpoint.scheme != "https" or endpoint.hostname != "api.deepseek.com":
        raise ValueError("unexpected API destination")
    if not (os.environ.get("SV_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        raise ValueError("API credential missing")
    hashes = {**plan["code_sha256"], **plan["source_inputs"]}
    for meta in plan["metadata"].values():
        hashes.update(meta["inputs_sha256"])
    plan["authorization"].update(status="user_approved", user_quote=approval_note)
    plan["status"] = "running"
    cost, identity = 0., None
    write(folder / "trial_manifest.json", plan)
    for rec in plan["records"]:
        for path, h in hashes.items():
            if sha(path) != h:
                raise ValueError("frozen code/input changed: " + path)
        if cost + JOB_CAP > TOTAL_CAP + 1e-9 or Path(rec["output_dir"]).exists():
            raise ValueError("budget/existing-run gate; no automatic repeat")
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
            raise RuntimeError("run failed; preserve outputs; no retry")
        run = json.loads((Path(rec["output_dir"]) / "run_manifest.json").read_text())
        calls = [json.loads(x) for x in (Path(rec["output_dir"]) / "llm_calls.jsonl").read_text().splitlines()]
        expected = {p["agent_id"]: p["messages"] for p in json.loads((folder / rec["month"] / f"prompt_preview_{rec['arm']}.json").read_text())}
        if len(calls) != N or {c["agent_id"] for c in calls} != set(expected):
            raise RuntimeError("call coverage mismatch")
        if any(json.loads(c["prompt_text"]) != expected[c["agent_id"]] for c in calls):
            raise RuntimeError("actual prompt differs from preview")
        tags = sorted({(c["returned_model"], c["system_fingerprint"]) for c in calls if c["error"] is None}, key=str)
        if identity is None:
            identity = tags
        rec.update(status="completed", cost=run["cost"], model_identity=tags,
                   decisions_by_validation_status=run["decisions_by_validation_status"])
        cost += run["cost"]["estimated_cost_usd"]
        plan["estimated_cost_usd"] = cost
        write(folder / "trial_manifest.json", plan)
        if len(tags) != 1 or tags != identity or run["decisions_by_validation_status"] != {"valid": N}:
            plan["status"] = "stopped_identity_or_validation_change"
            write(folder / "trial_manifest.json", plan)
            raise RuntimeError("identity/validation gate; no automatic retry")
        print("DONE", rec["month"], rec["arm"], run["cost"]["estimated_cost_usd"], flush=True)
    plan.update(status="completed", finished_at_utc=datetime.now(timezone.utc).isoformat())
    write(folder / "trial_manifest.json", plan)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--role-root", type=Path, default=ROOT / "outputs/ce_population_baskets_20261006T063749Z_a8be0d98")
    ap.add_argument("--environment-root", type=Path, default=ROOT / "outputs/price_experience_20261006_v1/n20")
    ap.add_argument("--prepared", type=Path)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--approval-note", default="")
    a = ap.parse_args()
    if a.execute and not a.approval_note.strip():
        ap.error("paid execution requires actual new approval")
    if a.prepared:
        folder = a.prepared.resolve()
        plan = json.loads((folder / "trial_manifest.json").read_text())
    else:
        folder = ROOT / "outputs" / ("sce_exposure_trial_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
        plan = prepare(a.role_root.resolve(), a.environment_root.resolve(), folder)
    print("TRIAL_DIR=" + str(folder), flush=True)
    if a.execute:
        execute(plan, folder, a.approval_note)


if __name__ == "__main__":
    main()
