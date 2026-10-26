#!/usr/bin/env python3
"""Audit a fixed-cohort recursive P/E candidate without scoring or LLM calls."""
import argparse
from collections import Counter
from datetime import datetime
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / "socioverse2_repo"))
import studies
studies.__path__ = [str(ROOT / "studies"), *studies.__path__]

from studies.sce_inflation_expectations.experiments.frozen_batch import dump, read_json, sha
from studies.sce_inflation_expectations.experiments.recent_b_continuity_pe import (
    B_INPUTS, DEFAULT_OUT, validate_dependencies, validate_public_environment,
)
from studies.sce_inflation_expectations.coverage_preparation import latest_wave, previous_month
from studies.sce_inflation_expectations.procurement_price_views import validate_cutoff
from studies.sce_inflation_expectations.state_continuity_runtime import render_state


def audit(inputs, out):
    inputs, out = Path(inputs).resolve(), Path(out).resolve()
    if (not inputs.is_relative_to(ROOT / "outputs") or not out.is_relative_to(ROOT / "outputs")
            or out.exists()):
        raise ValueError("Existing project input and fresh independent readiness directory required")
    manifest = read_json(inputs / "manifest.json")
    for base, key in ((inputs, "files_sha256"), (ROOT, "source_sha256")):
        for name, digest in manifest[key].items():
            path = (base / name).resolve()
            if not path.is_relative_to(base) or not path.is_file() or sha(path) != digest:
                raise ValueError("Source or prepared file changed: " + name)
    summary = read_json(inputs / "summary.json")
    months = summary["months"]; first = months[0]
    fixed = read_json(inputs / "fixed_population_private.json")
    people = {p["agent_id"]: p for p in fixed["personas"]}; ids = set(people)
    weights = read_json(inputs / "fixed_weights_private.json")
    baskets = read_json(inputs / "fixed_baskets_private.json")
    roles = read_json(inputs / "fixed_roles_private.json")
    tiers = read_json(inputs / "fixed_news_tiers_private.json")
    initial = read_json(inputs / "initial_states_private.json")
    if any(set(obj) != ids for obj in (weights, baskets, roles, tiers, initial)) or len(ids) != 512:
        raise ValueError("Fixed-cohort sidecars differ in identity support")
    if Counter(tiers.values()) != {4: 128, 8: 128, 16: 128, 32: 128}:
        raise ValueError("Fixed attention strata do not match the registered allocation")
    if any(not math.isfinite(r["analysis_weight"]) or r["analysis_weight"] <= 0 for r in weights.values()):
        raise ValueError("Invalid fixed-cohort analysis weight")
    if initial != read_json(B_INPUTS / "prompts" / first / "initial_states_private.json"):
        raise ValueError("The sole root belief differs from its frozen initial B source")
    if len(list(inputs.rglob("initial_states_private.json"))) != 1:
        raise ValueError("Later monthly initializers must not exist in recursive P/E")
    for state in initial.values():
        render_state(state, first)
    allowed_view_keys = {"news_tier", "grocery_role", "grocery_categories", "grocery_text",
                         "spending_shares", "synthetic_fed_confidence", "confidence_wave"}
    month_checks = []
    for month in months:
        folder = inputs / month
        population = read_json(folder / "population.json")
        if population["personas"] != fixed["personas"]:
            raise ValueError("Population identity/attributes/engine weights changed across months")
        environment = read_json(folder / "environment.json")
        cutoff = environment["provider_args"]["targets"][0]["as_of"]
        validate_public_environment(environment, cutoff)
        if environment["provider_args"]["persona_by_id"] != {aid: people[aid]["attributes"] for aid in ids}:
            raise ValueError("Provider profile map still uses independent monthly B population")
        original = read_json(B_INPUTS / "prompts" / month / "environment.json")
        if original["provider_args"]["targets"] != environment["provider_args"]["targets"]:
            raise ValueError("Global cutoff changed from the prepared B environment")
        contexts = read_json(folder / "timing_context_private.json")
        views = read_json(folder / "visible_information_private.json")
        facts = read_json(folder / "food_facts.json")
        policy = read_json(folder / "policy.json")
        wave = read_json(folder / "confidence_wave.json")
        if set(contexts) != ids or set(views) != ids:
            raise ValueError("A monthly environment does not cover the fixed cohort")
        validate_cutoff(list(facts.values()), cutoff)
        latest_wave([wave], cutoff)
        when = datetime.fromisoformat(cutoff)
        if datetime.fromisoformat(policy["published_at"]) > when:
            raise ValueError("Policy was not public at the global cutoff")
        start = previous_month(month[:4] + "-" + month[4:]) + "-01"
        article_count = 0
        for aid in ids:
            context, view = contexts[aid], views[aid]
            if set(view) != allowed_view_keys or context["as_of"] != cutoff:
                raise ValueError("Unexpected prior/answer field or cutoff in the visible-information view")
            if (view["news_tier"] != tiers[aid] or view["grocery_role"] != roles[aid]["role"]
                    or view["spending_shares"] != baskets[aid]["spending_shares"]):
                raise ValueError("Fixed attention, grocery role or CE spending changed")
            articles = context["common_news"] + context["personal_news"]
            if (len(context["common_news"]) != 3 or len(articles) != tiers[aid]
                    or len({r["article_id"] for r in articles}) != len(articles)):
                raise ValueError("Duplicated or wrong-sized personal news view")
            for row in articles:
                published = datetime.fromisoformat(row["pub_date"].replace("Z", "+00:00"))
                if published > when or published.astimezone(when.tzinfo).date().isoformat() < start:
                    raise ValueError("Selected news falls outside the registered B window")
            if (context["policy_published_at"] != policy["published_at"]
                    or context["food_published_at"] != facts["food_at_home"]["published_at"]):
                raise ValueError("Timing context differs from the actual price/policy data")
            article_count += len(articles)
        month_checks.append({"month": month, "fixed_n": len(ids), "as_of": cutoff,
                             "displayed_article_positions": article_count,
                             "separate_monthly_initializer": False})
    lineage = validate_dependencies(read_json(inputs / "state_dependencies_private.json"), sorted(ids), months)
    result = {"status": "passed_fixed_cohort_recursive_PE_readiness", "inputs": str(inputs.relative_to(ROOT)),
              "input_manifest_sha256": sha(inputs / "manifest.json"), "fixed_proxies": len(ids),
              "months": len(months), "person_months": len(ids) * len(months), "lineage": lineage,
              "all_source_and_output_hashes_verified": True, "fixed_profiles_roles_attention_weights": True,
              "single_initial_seed_file": True, "public_E_cutoffs_and_profile_maps_checked": True,
              "monthly": month_checks, "audit_script_sha256": sha(Path(__file__)),
              "new_api_calls": 0, "target_truth_opened": False, "LLM_responses_opened": False,
              "prompts_ready": False, "execution_ready": False, "authorization_written": False}
    out.mkdir(parents=True)
    dump(out / "acceptance.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.inputs, args.out)
    import json
    print(json.dumps({k: v for k, v in result.items() if k != "monthly"}, ensure_ascii=False, indent=2))
