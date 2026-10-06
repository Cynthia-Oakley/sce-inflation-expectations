#!/usr/bin/env python3
"""Freeze and run the authorized 20-person, two-month, five-arm SCE trial.

Default mode only prepares a new local trial. Execution requires --execute and
--confirm-spend. Never resumes or replaces an existing paid run automatically.
All paid requests go through the existing audited official-framework runner.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlparse
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, build_sce_messages_v2
from studies.sce_inflation_expectations.experience_mechanism import build_mechanism_messages

ARMS = ("baseline", "expression_shared", "basket_shared", "focus_only", "basket_focus")
MONTHS = ("202105", "202106")
MODEL = "deepseek-flash"
PER_JOB_CAP = 0.20
TOTAL_CAP = 2.0
PRICE_IN, PRICE_OUT = 0.30, 1.20  # peak/cache-miss conservative reference


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def prepare(pilot_root: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    prefix = output.name
    metadata, signatures = {}, {}
    for month in MONTHS:
        folder = pilot_root / month
        raw = {name: json.loads((folder / f"{name}.json").read_text())
               for name in ("population", "environment", "simulation", "experience")}
        pop = PopulationBundle.model_validate(raw["population"])
        env = EnvironmentBundle.model_validate(raw["environment"])
        sim = SimulationConfig.model_validate(raw["simulation"])
        exp = raw["experience"]
        ids = [p.agent_id for p in pop.personas]
        if len(ids) != 20 or len(set(ids)) != 20 or sim.n_steps != 1:
            raise ValueError("authorized trial requires 20 unique personas and one step per month")
        if sim.seed != 42 or sim.warm_start is not None:
            raise ValueError("trial needs seed=42 and no warm start")
        if any(p.weight != 1.0 for p in pop.personas):
            raise ValueError("survey weights must remain outside simulation personas")
        if set(exp["experience_by_id"]) != set(ids) or exp["population_sha256"] != sha(folder / "population.json"):
            raise ValueError("pilot experience/population mismatch")
        if len(env.provider_args["targets"]) != 1 or env.provider_args["targets"][0]["target_month"].replace("-", "") != month:
            raise ValueError("target month mismatch")
        file_hashes = {str((folder / f"{name}.json").resolve()): sha(folder / f"{name}.json") for name in raw}
        metadata[month] = {"n": 20, "inputs_sha256": file_hashes,
                           "profile_counts": {key: dict(Counter(str(p.attributes.get(key)) for p in pop.personas))
                                              for key in ("age_group", "region", "education_group", "household_income_band", "housing_tenure", "employment_status")}}
        for arm in ARMS:
            candidate = env.model_copy(deep=True)
            candidate.provider_args["persona_by_id"] = {p.agent_id: p.attributes for p in pop.personas}
            candidate.provider_args.pop("audit_dir", None)
            candidate.provider_args.pop("price_experience_mechanism", None)
            candidate.provider_args.pop("experience_by_id", None)
            if arm != "baseline":
                config_path = ROOT / f"studies/sce_inflation_expectations/mechanism/{arm}.json"
                candidate.provider_args["price_experience_mechanism"] = json.loads(config_path.read_text())
                candidate.provider_args["experience_by_id"] = exp["experience_by_id"]
                file_hashes[str(config_path)] = sha(config_path)
            provider = SCEEnvironmentProvider(candidate)
            provider.reset(42)
            provider.advance_to(1)
            records, maximum_cost = [], 0.0
            for ob in provider.observe_batch(ids, 1):
                messages = build_sce_messages_v2(ob, include_event_abstracts=True)
                if arm != "baseline":
                    messages = build_mechanism_messages(ob, messages)
                text = json.dumps(messages, ensure_ascii=False)
                if len(text) > 16000:
                    raise ValueError("prompt exceeds the existing size gate")
                maximum_cost = max(maximum_cost, ((len(text.encode()) + 256) * PRICE_IN + 1024 * PRICE_OUT) / 1e6)
                records.append({"agent_id": ob.agent_id, "messages": messages,
                                "prompt_sha256": hashlib.sha256(text.encode()).hexdigest()})
            if 40 * maximum_cost > PER_JOB_CAP:
                raise ValueError("maximum attempts could exceed the authorized per-job cap")
            write(output / f"prompt_preview_{month}_{arm}.json", records)
            signatures[f"{month}/{arm}"] = {"preview_sha256": sha(output / f"prompt_preview_{month}_{arm}.json"),
                                            "max_request_cost_bound_usd": maximum_cost}
    records = []
    for i, arm in enumerate(ARMS):
        for month in MONTHS if i % 2 == 0 else tuple(reversed(MONTHS)):
            run_id = f"{prefix}-{month}-{arm}"
            folder = pilot_root / month
            cmd = [sys.executable, str(ROOT / "scripts/run_sce_local.py"), "--llm", "openai",
                   "--model", MODEL, "--population", str(folder / "population.json"),
                   "--environment", str(folder / "environment.json"), "--simulation", str(folder / "simulation.json"),
                   "--run-id", run_id, "--temperature", "0", "--max-tokens", "1024",
                   "--retry-max", "1", "--max-calls", "40", "--extra-body", '{"thinking":{"type":"disabled"}}',
                   "--price-in", str(PRICE_IN), "--price-out", str(PRICE_OUT), "--cost-cap-usd", str(PER_JOB_CAP),
                   "--confirm-spend", "--prompt-version", "sce-q8-q9-v2-abstract" if arm == "baseline" else "sce-q8-q9-experience-v1"]
            if arm != "baseline":
                cmd += ["--mechanism", str(ROOT / f"studies/sce_inflation_expectations/mechanism/{arm}.json"),
                        "--experience", str(folder / "experience.json")]
            records.append({"month": month, "arm": arm, "run_id": run_id, "output_dir": str(ROOT / "outputs/local_runs" / run_id),
                            "command": cmd, "status": "pending"})
    plan = {"trial_id": prefix, "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "prepared_not_run", "research_line": "A_historical_reconstruction", "metadata": metadata,
            "n_per_month": 20, "target_answers": 200, "max_attempts": 400,
            "total_budget_cap_usd": TOTAL_CAP, "per_job_cap_usd": PER_JOB_CAP,
            "model": MODEL, "pricing_source": "https://api-docs.deepseek.com/quick_start/pricing/",
            "price_note": "Peak cache-miss/output rates used for a conservative estimate; not the vendor bill.",
            "normal_expansion": False, "actual_sce_answers_in_prompts": False,
            "prompt_previews": signatures, "records": records,
            "authorization": {"user_quote": "好的，可以开展这个实验。看一下效果。", "context": "preceding five-arm, 200-answer, $2 proposal",
                              "destination": "https://api.deepseek.com", "scope": "coarse deidentified demographic profiles, synthetic CE shares, public economic/news information; no real survey answers"},
            "runner_sha256": sha(__file__), "framework_runner_sha256": sha(ROOT / "scripts/run_sce_local.py"),
            "study_source_sha256": {str(p): sha(p) for p in sorted((ROOT / "studies/sce_inflation_expectations").rglob("*.py"))}}
    write(output / "initial_plan.json", plan)
    write(output / "trial_manifest.json", plan)
    shutil.copy2(__file__, output / "runner_snapshot.py")
    return plan


def execute(plan, output):
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    endpoint = os.environ.get("SV_LLM_BASE_URL", "")
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or parsed.hostname != "api.deepseek.com":
        raise ValueError("refusing to send this trial to a different endpoint")
    if not (os.environ.get("SV_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")):
        raise ValueError("configured key missing; do not print or copy keys into trial files")
    plan["status"] = "running"
    estimated_total, reference_identity = 0.0, None
    child_env = os.environ.copy()
    for row in plan["records"]:
        if sha(ROOT / "scripts/run_sce_local.py") != plan["framework_runner_sha256"]:
            raise ValueError("frozen framework runner changed")
        for name, h in plan["study_source_sha256"].items():
            if sha(name) != h:
                raise ValueError("frozen study source changed")
        for name, h in plan["metadata"][row["month"]]["inputs_sha256"].items():
            if sha(name) != h:
                raise ValueError("frozen trial input changed")
        if estimated_total + PER_JOB_CAP > TOTAL_CAP + 1e-9:
            raise ValueError("aggregate budget gate")
        if Path(row["output_dir"]).exists():
            raise ValueError("existing paid run found: inspect manually; never auto-repeat")
        row["status"] = "running"
        write(output / "trial_manifest.json", plan)
        print(f"START {row['month']} {row['arm']}", flush=True)
        logfile = output / f"{row['month']}_{row['arm']}.log"
        with logfile.open("w") as log:
            result = subprocess.run(row["command"], cwd=ROOT, env=child_env, stdout=log, stderr=subprocess.STDOUT)
        row["exit_code"] = result.returncode
        if result.returncode:
            row["status"] = "failed"; plan["status"] = "stopped_run_error"
            write(output / "trial_manifest.json", plan)
            raise RuntimeError(f"trial stopped: inspect local log {logfile.name}")
        run = json.loads((Path(row["output_dir"]) / "run_manifest.json").read_text())
        cost = run["cost"]
        estimated_total += float(cost["estimated_cost_usd"])
        calls = [json.loads(line) for line in (Path(row["output_dir"]) / "llm_calls.jsonl").read_text().splitlines()]
        identity = sorted({(x["returned_model"], x["system_fingerprint"]) for x in calls if x["error"] is None}, key=str)
        if reference_identity is None:
            reference_identity = identity
        row.update(status="completed", cost=cost, model_identity=identity, decisions_by_validation_status=run["decisions_by_validation_status"])
        plan["estimated_cost_usd"] = round(estimated_total, 6)
        write(output / "trial_manifest.json", plan)
        print(f"DONE {row['month']} {row['arm']} calls={cost['call_count']} estimated_usd={cost['estimated_cost_usd']} valid={run['decisions_by_validation_status'].get('valid',0)}", flush=True)
        if len(identity) != 1 or identity != reference_identity or run["decisions_by_validation_status"] != {"valid": 20}:
            plan["status"] = "stopped_identity_or_validation_change"
            write(output / "trial_manifest.json", plan)
            raise RuntimeError("model identity or validation gate: retain results; do not continue automatically")
    plan["status"] = "completed"
    plan["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    write(output / "trial_manifest.json", plan)
    print(f"COMPLETE 200 answers; conservative usage estimate ${estimated_total:.6f}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pilot-root", type=Path, default=ROOT / "outputs/price_experience_20261006_v1/n20")
    ap.add_argument("--output", type=Path)
    ap.add_argument("--prepared", type=Path, help="previously prepared trial directory; never a partially run trial")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--confirm-spend", action="store_true")
    args = ap.parse_args()
    if args.execute and not args.confirm_spend:
        ap.error("execution spends the authorized budget; --confirm-spend required")
    if args.prepared:
        output = args.prepared.resolve()
        plan = json.loads((output / "initial_plan.json").read_text())
        current = json.loads((output / "trial_manifest.json").read_text())
        if current["status"] != "prepared_not_run" or plan["runner_sha256"] != sha(__file__):
            raise ValueError("plan already run or runner changed; inspect instead of auto-repeat")
    else:
        output = (args.output or ROOT / "outputs" / ("sce-experience-trial-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])).resolve()
        plan = prepare(args.pilot_root.resolve(), output)
    print(f"TRIAL {output}", flush=True)
    if args.execute:
        execute(plan, output)


if __name__ == "__main__":
    main()
