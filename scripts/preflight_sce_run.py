"""Render/inspect a planned SCE run without instantiating an LLM client."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, build_sce_messages_v2
from studies.sce_inflation_expectations.monthly_population import ATTRIBUTE_KEYS


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    study = ROOT / "studies/sce_inflation_expectations"
    ap.add_argument("--population", type=Path, default=study / "population/population_main2021_a73.json")
    ap.add_argument("--environment", type=Path, default=study / "environment/environment_dev2021_05_06_v2.json")
    ap.add_argument("--simulation", type=Path, default=study / "simulation/simulation_dev2021_05_06_v2.json")
    ap.add_argument("--model", default="deepseek-flash")
    ap.add_argument("--temperature", type=float, default=.5)
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--retry-max", type=int, default=1)
    args = ap.parse_args()
    pop = PopulationBundle.model_validate(json.loads(args.population.read_text()))
    bundle = EnvironmentBundle.model_validate(json.loads(args.environment.read_text()))
    config = SimulationConfig.model_validate(json.loads(args.simulation.read_text()))
    if config.n_steps != len(bundle.provider_args["targets"]):
        raise ValueError("simulation steps and environment target count differ")
    for p in pop.personas:
        if set(p.attributes) - ATTRIBUTE_KEYS or p.weight != 1:
            raise ValueError("P must contain only whitelisted profiles and neutral weights")
    # No audit side effects or request client; matching actual runner's profile binding.
    bundle.provider_args.pop("audit_dir", None)
    bundle.provider_args.pop("run_id", None)
    bundle.provider_args["persona_by_id"] = {p.agent_id: {**p.attributes, "weight": 1} for p in pop.personas}
    env = SCEEnvironmentProvider(bundle)
    env.reset(config.seed)
    per_month, samples = [], []
    for step in range(1, config.n_steps + 1):
        env.advance_to(step)
        obs = env.observe_batch([p.agent_id for p in pop.personas], step)
        lengths = []
        for i, ob in enumerate(obs):
            messages = build_sce_messages_v2(ob, include_event_abstracts=True)
            text = "\n".join(m["content"] for m in messages)
            if "Last month you gave a point estimate" in text:
                raise ValueError("own prior answer unexpectedly in v2 prompt")
            lengths.append(len(text.encode("utf-8")))
            if i < 2:
                samples.append({"agent_id": ob.agent_id, "target_month": ob.macro_information["target_month"],
                                "messages": messages})
        abstracts = [bool(str(e.get("abstract", "")).strip()) for e in obs[0].macro_information.get("events", [])]
        per_month.append({"target_month": obs[0].macro_information["target_month"],
                          "as_of": obs[0].macro_information["as_of"], "people": len(obs),
                          "signals": len(obs[0].macro_information["signals"]), "news": len(abstracts),
                          "news_with_abstract": sum(abstracts), "prompt_utf8_bytes_min": min(lengths),
                          "prompt_utf8_bytes_max": max(lengths)})
    n = len(pop.personas) * config.n_steps
    payload = {"status": "preflight_only_not_a_simulation", "real_llm_calls": 0,
               "planned_model_request": args.model, "temperature": args.temperature,
               "max_tokens": args.max_tokens, "retry_max": args.retry_max,
               "prompt_version": "sce-q8-q9-v2-abstract", "seed": config.seed,
               "planned_answer_rows": n, "maximum_requests_including_retry": n * (1 + args.retry_max),
               "months": per_month,
               "input_sha256": {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in
                                [("population", args.population), ("environment", args.environment), ("simulation", args.simulation)]},
               "notes": ["Prompt byte counts are not tokenizer counts or a billing quote",
                         "Retrospective conditional development run; not t-to-t+1 forecast",
                         "Exact historical news text and gasoline vintages remain unverified",
                         "API endpoint, current prices and spending cap must be checked before real calls"]}
    out = ROOT / "outputs" / ("preflight_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    (out / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    (out / "prompt_samples.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in samples))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(out)


if __name__ == "__main__":
    main()
