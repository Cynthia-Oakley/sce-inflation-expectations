"""Prepare A-line monthly P/E/simulation packages without model calls.

Writes only fresh ignored outputs; never overwrites study's approved artifacts.
The input reader requests profiles and survey metadata, never Q8/Q9 outcomes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.monthly_population import (
    PROFILE_COLUMNS, build_analysis_weights, build_monthly_population,
)
from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig


def slice_environment(bundle, month):
    out = deepcopy(bundle)
    args = out["provider_args"]
    target = f"{month // 100:04}-{month % 100:02}"
    matches = [i for i, row in enumerate(args["targets"]) if row["target_month"] == target]
    if len(matches) != 1:
        raise ValueError("expected exactly one matching environment target")
    step = matches[0]
    args["targets"] = [args["targets"][step]]
    for key in ["signals_by_step", "events_by_step"]:
        args[key] = {"0": args.get(key, {}).get(str(step), [])}
    args.pop("persona_by_id", None)
    args["research_line"] = "A_historical_reconstruction"
    args["e_version"] = args.get("e_version", "") + f"_monthly_{month}"
    broadcasts = []
    for b in out["information_program"]["broadcasts"]:
        if b["at_step"] == step:
            b["at_step"] = 0
            broadcasts.append(b)
    out["information_program"]["broadcasts"] = broadcasts
    # Existing dev E has no scheduled physical events; fail on unsupported ones.
    if out.get("scheduled_events"):
        raise ValueError("monthly slicer does not support scheduled physical events")
    as_of = datetime.fromisoformat(args["targets"][0]["as_of"])
    for signal in args["signals_by_step"]["0"]:
        if datetime.fromisoformat(signal["published_at"]) > as_of:
            raise ValueError("future signal in sliced environment")
    for event in args["events_by_step"]["0"]:
        stamp = event.get("published_at") or event.get("pub_date")
        if not stamp:
            raise ValueError("undated/future news in sliced environment")
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when.tzinfo is None:
            if len(stamp) != 10 or when.date() > as_of.date():
                raise ValueError("unknown-time/future news in sliced environment")
            if when.date() == as_of.date() and (as_of.hour, as_of.minute, as_of.second) != (23, 59, 59):
                raise ValueError("date-only news cannot establish within-day availability")
            args["news_time_resolution"] = "calendar_date_only_as_in_source; exact_timestamp_unverified"
        elif when > as_of:
            raise ValueError("future news in sliced environment")
    EnvironmentBundle.model_validate(out)
    return out


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--months", default="202105,202106")
    ap.add_argument("--sizes", default="all,300,500")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--design", choices=["independent_srs", "stable_priority_srs"], default="independent_srs")
    ap.add_argument("--data", type=Path, default=ROOT / "data/raw/sce_audit_20260928/micro_2020_2024.xlsx")
    ap.add_argument("--environment", type=Path, default=ROOT / "studies/sce_inflation_expectations/environment/environment_dev2021_05_06_v2.json")
    ap.add_argument("--simulation", type=Path, default=ROOT / "studies/sce_inflation_expectations/simulation/simulation_dev2021_05_06_v2.json")
    args = ap.parse_args()
    months = sorted(set(map(int, args.months.split(","))))
    sizes = [None if s == "all" else int(s) for s in args.sizes.split(",")]
    digest = hashlib.sha256(args.data.read_bytes()).hexdigest()
    # Cache is generated locally from the same source/hash/reader-column contract.
    columns = PROFILE_COLUMNS + ["weight", "survey_date"]
    cache_key = hashlib.sha256((digest + json.dumps(columns)).encode()).hexdigest()[:20]
    cache = ROOT / "data/cache" / f"monthly_profiles_{cache_key}.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
    else:
        print("Reading whitelisted profile fields; no questionnaire outcomes", flush=True)
        df = pd.read_excel(args.data, skiprows=1, usecols=columns)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
    profiles = df[PROFILE_COLUMNS]
    weights = df[["date", "userid", "weight"]]
    environment = json.loads(args.environment.read_text())
    simulation = json.loads(args.simulation.read_text())
    out = ROOT / "outputs" / ("monthly_inputs_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"build_id": out.name, "created_utc": datetime.now(timezone.utc).isoformat(),
                "research_line": "A_historical_reconstruction", "seed": args.seed, "sampling_design": args.design,
                "source_sha256": digest, "read_columns": columns,
                "local_derived_cache_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
                "environment_source_sha256": hashlib.sha256(args.environment.read_bytes()).hexdigest(),
                "source_code_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                       [Path(__file__), ROOT / "studies/sce_inflation_expectations/monthly_population.py"]},
                "paid_calls": 0, "packages": []}
    snapshot = out / "source_snapshot"
    snapshot.mkdir()
    for src in [Path(__file__), ROOT / "studies/sce_inflation_expectations/monthly_population.py"]:
        (snapshot / src.name).write_bytes(src.read_bytes())
    for month in months:
        env = slice_environment(environment, month)
        sim = deepcopy(simulation)
        sim.update(n_steps=1, warm_start=None)
        sim["engine_args"]["memory_window"] = 1
        SimulationConfig.model_validate(sim)
        for size in sizes:
            pop, meta = build_monthly_population(profiles, month, n=size, seed=args.seed, design=args.design)
            PopulationBundle.model_validate(pop)
            analysis = build_analysis_weights(pop, meta, weights)
            folder = out / ("all" if size is None else f"n{size}") / str(month)
            folder.mkdir(parents=True)
            write_json(folder / "population.json", pop)
            write_json(folder / "sampling_meta.json", meta)
            write_json(folder / "environment.json", env)
            write_json(folder / "simulation.json", sim)
            with (folder / "analysis_weights.jsonl").open("w") as f:
                for row in analysis:
                    f.write(json.dumps(row) + "\n")
            with (folder / "survey_dates.jsonl").open("w") as f:
                dates = df[df.date == month].set_index("userid").survey_date
                for p in pop["personas"]:
                    value = dates.loc[int(p["agent_id"].removeprefix("sce_u"))]
                    f.write(json.dumps({"agent_id": p["agent_id"], "target_month": month,
                                        "survey_date": None if pd.isna(value) else str(value)}) + "\n")
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.is_file()}
            manifest["packages"].append({"path": str(folder.relative_to(out)), "target_month": month,
                                         "frame_n": meta["frame_n"], "selected_n": meta["selected_n"], "sha256": hashes})
            print(f"Prepared {month}: {meta['selected_n']} / {meta['frame_n']} people", flush=True)
    write_json(out / "manifest.json", manifest)
    print(out, flush=True)


if __name__ == "__main__":
    main()
