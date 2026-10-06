#!/usr/bin/env python3
"""Build an A-line CE basket sidecar and preview all mechanism arms, fully offline.

Only one explicit FMLI CSV wave is accepted. No SCE survey answers, targets,
API credentials or network calls are read. Outputs go into a fresh directory.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from socioverse.schemas import EnvironmentBundle, PopulationBundle
from studies.sce_inflation_expectations.price_experience import BasketAssigner, prepare_ce_donors, canonical_hash
from studies.sce_inflation_expectations.experience_mechanism import build_mechanism_messages, validate_config
from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, build_sce_messages_v2

ARMS = ROOT / "studies/sce_inflation_expectations/mechanism"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def build(args) -> dict:
    data_path, pop_path, env_path = [Path(p).resolve() for p in (args.ce_data, args.population, args.environment)]
    data = data_path.read_bytes()
    if zipfile.is_zipfile(data_path):
        if not args.member:
            raise ValueError("ZIP input requires one explicit --member FMLI CSV, never pool quarters")
        with zipfile.ZipFile(data_path) as z:
            data = z.read(args.member)
    elif args.member:
        raise ValueError("--member only applies to ZIP input")
    # Fields identify one quarter and an interview, not one person sampled four times.
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows:
        raise ValueError("empty FMLI CSV")
    donors, donor_audit = prepare_ce_donors(rows)
    wave_parts = args.wave.split("Q")
    if len(wave_parts) != 2 or not wave_parts[0].isdigit() or wave_parts[1] not in {"1", "2", "3", "4"}:
        raise ValueError("--wave must be YYYYQn")
    year, quarter = int(wave_parts[0]), int(wave_parts[1])
    if year < 2014:
        raise ValueError("this code map applies to 2014+ CE; select a supported wave")
    for raw in rows:
        normalized = {k.strip().upper(): v for k, v in raw.items()}
        # QINTRVYR is two-digit in CE. Require the actual record date, not a filename assertion.
        if "QINTRVYR" not in normalized or "QINTRVMO" not in normalized:
            raise ValueError("need QINTRVYR/QINTRVMO to verify the declared interview wave")
        observed_year = int(float(normalized["QINTRVYR"]))
        if observed_year < 100:
            observed_year += 2000
        month = int(float(normalized["QINTRVMO"]))
        if observed_year != year or not 1 <= month <= 12 or (month - 1)//3 + 1 != quarter:
            raise ValueError("CSV records do not match the declared single interview wave")
    source = {"source_url": args.source_url, "official_source_url": args.official_url or args.source_url,
              "data_sha256": sha(data_path), "member_sha256": hashlib.sha256(data).hexdigest(),
              "member": args.member, "interview_wave": args.wave,
              "public_release_date": args.release_date,
              "public_release_evidence_url": getattr(args, "release_evidence_url", None),
              "source_version_status": "downloaded_copy_not_original_release_vintage",
              "usage": "retrospective_A_proxy_only_not_PIT_certified",
              "dictionary_code_map": "CE 2013Q2+ EDUC_REF; CUTENURE 1996Q1+",
              "code_map_sha256": sha(ARMS / "ce_field_map.json"),
              "denominator": "TOTEXPPQ+TOTEXPCQ including contributions/pensions; not a CPI basket"}
    assigner = BasketAssigner(donors, source, seed=args.seed, min_pool=args.min_pool)
    pop = PopulationBundle.model_validate(json.loads(pop_path.read_text()))
    env = EnvironmentBundle.model_validate(json.loads(env_path.read_text()))
    targets = env.provider_args.get("targets", [])
    if len(targets) != 1:
        raise ValueError("prepare one target month per bundle")
    ids = [p.agent_id for p in pop.personas]
    if len(set(ids)) != len(ids) or not ids:
        raise ValueError("population requires nonempty unique IDs")
    baskets = {p.agent_id: assigner.assign(p.agent_id, p.attributes) for p in pop.personas}
    result = {"schema_version": "sce-experience-bundle-v1", "target_month": targets[0]["target_month"],
              "research_line": "A_historical_reconstruction", "population_sha256": sha(pop_path),
              "source": source, "experience_by_id": baskets}
    env.provider_args["persona_by_id"] = {p.agent_id: p.attributes for p in pop.personas}
    env.provider_args.pop("audit_dir", None)
    env.provider_args["experience_by_id"] = baskets
    # Validate every arm/agent and render exactly the messages used by the LLM provider.
    previews, facts, lengths, config_hashes = {}, {}, {}, {}
    for config_path in sorted(ARMS.glob("*.json")):
        if config_path.name == "ce_field_map.json":
            continue
        config = validate_config(json.loads(config_path.read_text()))
        config_hashes[config_path.name] = sha(config_path)
        env.provider_args["price_experience_mechanism"] = config
        provider = SCEEnvironmentProvider(env)
        provider.reset(args.seed)
        provider.advance_to(1)
        observations = provider.observe_batch(ids, 1)
        records = []
        for ob in observations:
            messages = build_mechanism_messages(ob, build_sce_messages_v2(ob, include_event_abstracts=True))
            state = ob.local_information["price_experience"]
            if len(state["source_signal_ids"]) != len(set(state["source_signal_ids"])):
                raise ValueError("signal ID duplication")
            if sorted(state["master_event_ids"]) != sorted(state["view_event_ids"]):
                raise ValueError("a news item was lost or introduced")
            facts.setdefault(ob.agent_id, state["public_fact_ledger_sha256"])
            if facts[ob.agent_id] != state["public_fact_ledger_sha256"]:
                raise ValueError("public facts differ across arms")
            # Identical serialization to the decision provider's prompt audit/length gate.
            text = json.dumps(messages, ensure_ascii=False)
            if len(text) > 16000:
                raise ValueError(f"prompt exceeds current runtime 16000-char gate: {ob.agent_id}")
            records.append({"agent_id": ob.agent_id, "arm": config["arm"],
                            "observation": ob.model_dump(), "messages": messages,
                            "prompt_sha256": hashlib.sha256(text.encode()).hexdigest(), "prompt_chars": len(text)})
        previews[config["arm"]] = records
        lengths[config["arm"]] = {"min": min(r["prompt_chars"] for r in records),
                                 "max": max(r["prompt_chars"] for r in records)}
    summary = {"status": "offline_materialized_not_behaviourally_validated", "agent_count": len(ids),
               "target_month": result["target_month"], "seed": args.seed, "minimum_pool_n": args.min_pool,
               "donor_audit": donor_audit, "source": source,
               "matched_fields_counts": dict(Counter("|".join(b["matched_fields"]) for b in baskets.values())),
               "relaxed_assignment_count": sum(bool(b["relaxed_fields"]) for b in baskets.values()),
               "min_pool_effective_n": min(b["pool_effective_n"] for b in baskets.values()),
               "unique_assigned_donors": len({b["donor_id"] for b in baskets.values()}),
               "arms": lengths, "config_file_sha256": config_hashes,
               "public_facts_identical_across_arms": True,
               "public_fact_ledger_sha256": sorted(set(facts.values())),
               "llm_calls": 0, "mcp_calls": 0,
               "inputs": {"population": {"path": str(pop_path), "sha256": sha(pop_path)},
                          "environment": {"path": str(env_path), "sha256": sha(env_path)}},
               "created_at_utc": datetime.now(timezone.utc).isoformat()}
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    snapshot = out / "source_snapshot"
    snapshot.mkdir()
    code_paths = [Path(__file__), ROOT / "studies/sce_inflation_expectations/price_experience.py",
                  ROOT / "studies/sce_inflation_expectations/experience_mechanism.py",
                  ROOT / "studies/sce_inflation_expectations/model.py"]
    summary["source_code_sha256"] = {str(p.relative_to(ROOT)): sha(p) for p in code_paths}
    for path in code_paths:
        (snapshot / path.name).write_bytes(path.read_bytes())
    for path in sorted(ARMS.glob("*.json")):
        (snapshot / path.name).write_bytes(path.read_bytes())
    summary["build_spec_sha256"] = canonical_hash({"source": source, "seed": args.seed,
        "min_pool": args.min_pool, "inputs": summary["inputs"], "code": summary["source_code_sha256"],
        "configs": config_hashes})
    write(out / "experience.json", result)
    write(out / "assignment_summary.json", summary)
    for arm, records in previews.items():
        with (out / f"prompt_preview_{arm}.jsonl").open("w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
    write(out / "manifest.json", {"files": {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}})
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ce-data", required=True)
    parser.add_argument("--member")
    parser.add_argument("--wave", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--official-url")
    parser.add_argument("--release-date", required=True)
    parser.add_argument("--release-evidence-url", help="public documentation of release date; current download still is not an original vintage")
    parser.add_argument("--population", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-pool", type=int, default=25)
    args = parser.parse_args()
    summary = build(args)
    print(json.dumps({"output": str(Path(args.output).resolve()), "agent_count": summary["agent_count"],
                      "eligible_donors": summary["donor_audit"]["eligible_n"], "arms": summary["arms"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
