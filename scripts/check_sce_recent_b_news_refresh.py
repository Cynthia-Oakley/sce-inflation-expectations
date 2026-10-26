#!/usr/bin/env python3
"""Read-only B input audit; writes a separate readiness receipt, never calls LLMs."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies
studies.__path__ = [str(ROOT / "studies"), *studies.__path__]

from studies.sce_inflation_expectations.experiments.frozen_batch import dump, read_json, sha
from studies.sce_inflation_expectations.experiments.media_mechanism_v3 import is_cpi_direct
from studies.sce_inflation_expectations.experiments.recent_b_news_refresh import DEFAULT_OUT, MONTHS, SEED
from studies.sce_inflation_expectations.experiments.media_mechanism_v3 import four_tier_levels
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.state_continuity_runtime import render_messages


def audit(inputs, out):
    inputs, out = Path(inputs).resolve(), Path(out).resolve()
    if not inputs.is_relative_to(ROOT / "outputs") or not out.is_relative_to(ROOT / "outputs") or out.exists():
        raise ValueError("Existing project inputs and a fresh separate readiness directory required")
    manifest = read_json(inputs / "manifest.json")
    for base, key in ((inputs, "files_sha256"), (ROOT, "source_sha256")):
        for name, digest in manifest[key].items():
            path = (base / name).resolve()
            if not path.is_relative_to(base) or not path.is_file() or sha(path) != digest:
                raise ValueError("Pinned file changed: " + name)
    summary = read_json(inputs / "summary.json")
    if summary["new_api_calls"] != 0 or summary["truth_opened"] or summary["execution_package_created"]:
        raise ValueError("Only offline candidate inputs can be audited here")
    if summary["official_core"]["official_engine_units"] != 11 or summary["official_core"]["decisions"] != 5632:
        raise ValueError("Full B11 official Core evidence required")
    parent = ROOT / summary["parent_assembly"] / "prompts"
    rows = []
    for month in MONTHS:
        folder = inputs / "prompts" / month
        states = read_json(folder / "initial_states_private.json")
        contexts = read_json(folder / "timing_context_private.json")
        previews = read_json(folder / "initial_previews_private.json")
        templates = read_json(folder / "templates_private.json")
        tiers = four_tier_levels(sorted(states), int(month), SEED)
        if Counter(tiers.values()) != {4: 128, 8: 128, 16: 128, 32: 128}:
            raise ValueError("B tiers do not preserve the registered equal allocation")
        for name in ("population", "environment", "initial_states_private", "baskets_private"):
            if sha(folder / f"{name}.json") != sha(parent / month / f"{name}.json"):
                raise ValueError("Frozen non-news bytes changed: " + name)
        exposure = {str(n): {"n": 0, "persons_with_cpi_news": 0, "personal_cpi_articles": 0,
                              "total_cpi_articles": 0} for n in (4, 8, 16, 32)}
        for aid, state in states.items():
            context = contexts[aid]; tier = tiers[aid]
            if len(context["common_news"]) != 3 or len(context["personal_news"]) != tier - 3:
                raise ValueError("Displayed article count differs from its tier")
            ids = [r["article_id"] for r in context["common_news"] + context["personal_news"]]
            if len(ids) != len(set(ids)):
                raise ValueError("Duplicate displayed articles")
            rendered = render_messages(templates[aid], state, month, context)
            if previews[aid]["messages"] != rendered or previews[aid]["prompt_sha256"] != message_hash(rendered):
                raise ValueError("Final B preview/template mismatch")
            common_n = sum(is_cpi_direct(r) for r in context["common_news"])
            personal_n = sum(is_cpi_direct(r) for r in context["personal_news"])
            counts = exposure[str(tier)]
            counts["n"] += 1
            counts["persons_with_cpi_news"] += common_n + personal_n > 0
            counts["personal_cpi_articles"] += personal_n
            counts["total_cpi_articles"] += common_n + personal_n
        rows.append({"month": month, "cpi_exposure_by_tier": exposure})
    # Supplementary dependency lock for the inherited pool/parser and official
    # scripted checker; it binds this preparation without rewriting its manifest.
    names = ["coverage_preparation.py", "news_selection_trial.py", "prior_belief_experiment.py",
             "information_update_runtime.py", "state_continuity_runtime.py",
             "experiments/state_continuity_core.py", "experiments/state_continuity_dry_run.py",
             "experiments/frozen_batch.py"]
    paths = [ROOT / "studies/sce_inflation_expectations" / name for name in names]
    paths += [ROOT / "scripts/build_sce_fullperiod_coverage.py", Path(__file__)]
    lock = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    result = {"status": "passed_offline_B11_news_refresh_readiness", "inputs": str(inputs.relative_to(ROOT)),
              "input_manifest_sha256": sha(inputs / "manifest.json"), "positions": 5632,
              "official_core_units": 11, "source_and_prepared_hashes_verified": True,
              "non_news_bytes_unchanged": True, "all_previews_reproduced": True,
              "estimated_main_cost_usd": summary["estimated_main_cost_usd"],
              "new_api_calls": 0, "truth_opened": False, "authorization_written": False,
              "execution_package_created": False, "extra_dependency_sha256": lock,
              "monthly_cpi_exposure": rows,
              "next_gate": "Evaluate full A, freeze a past-period blend weight, then separately prepare/authorize B execution."}
    out.mkdir(parents=True)
    dump(out / "acceptance.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.inputs, args.out)
    print(json.dumps({k: v for k, v in result.items() if k not in ("monthly_cpi_exposure", "extra_dependency_sha256")},
                     ensure_ascii=False, indent=2))
