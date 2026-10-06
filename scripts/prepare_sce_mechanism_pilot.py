#!/usr/bin/env python3
"""Create a small, fixed within-month comparison panel without reading answers.

This is a mechanism/debug pilot, not a representative national estimate. All
arms must reuse its same P, E and CE sidecar. Normal expansion is not applied.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from socioverse.schemas import PopulationBundle, EnvironmentBundle, SimulationConfig
from studies.sce_inflation_expectations.price_experience import profile_hash


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(pop_path, env_path, sim_path, experience_path, output, n=20, seed=42):
    paths = [Path(p).resolve() for p in (pop_path, env_path, sim_path, experience_path)]
    population, environment, simulation, experience = [json.loads(p.read_text()) for p in paths]
    pop = PopulationBundle.model_validate(population)
    env = EnvironmentBundle.model_validate(environment)
    sim = SimulationConfig.model_validate(simulation)
    ids = sorted(p.agent_id for p in pop.personas)
    targets = env.provider_args.get("targets", [])
    if len(ids) != len(set(ids)) or not 1 <= n <= len(ids):
        raise ValueError("invalid pilot size/IDs")
    if len(targets) != 1 or sim.n_steps != 1 or experience.get("target_month") != targets[0]["target_month"]:
        raise ValueError("need a matching single-month P/E/simulation/experience set")
    if experience.get("schema_version") != "sce-experience-bundle-v1" or experience.get("research_line") != "A_historical_reconstruction":
        raise ValueError("need an A-line CE sidecar")
    if set(experience["experience_by_id"]) != set(ids) or experience.get("population_sha256") != sha(paths[0]):
        raise ValueError("sidecar does not match the pilot sampling frame")
    for persona in pop.personas:
        if experience["experience_by_id"][persona.agent_id]["profile_sha256"] != profile_hash(persona.attributes):
            raise ValueError("profile/basket mismatch")
    selected = set(random.Random(seed).sample(ids, n))
    pilot = deepcopy(population)
    pilot["personas"] = [p for p in population["personas"] if p["agent_id"] in selected]
    PopulationBundle.model_validate(pilot)
    baskets = deepcopy(experience)
    baskets["experience_by_id"] = {aid: experience["experience_by_id"][aid] for aid in sorted(selected)}
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    write(out / "population.json", pilot)
    baskets["population_sha256"] = sha(out / "population.json")
    write(out / "experience.json", baskets)
    write(out / "environment.json", environment)
    write(out / "simulation.json", simulation)
    meta = {"purpose": "fixed_within_month_mechanism_pilot_not_national_estimate", "target_month": targets[0]["target_month"],
            "seed": seed, "n": n, "sampling_frame_n": len(ids), "selected_ids": sorted(selected),
            "normal_expansion": False, "outcomes_read": False, "api_calls": 0,
            "inputs": {p.name: {"path": str(p), "sha256": sha(p)} for p in paths},
            "code_sha256": sha(Path(__file__))}
    write(out / "pilot_manifest.json", meta)
    write(out / "manifest.json", {p.name: sha(p) for p in out.iterdir() if p.is_file()})
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("population", "environment", "simulation", "experience", "output"):
        ap.add_argument("--" + name, required=True)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    print(json.dumps(prepare(a.population, a.environment, a.simulation, a.experience, a.output, a.n, a.seed), ensure_ascii=False))
