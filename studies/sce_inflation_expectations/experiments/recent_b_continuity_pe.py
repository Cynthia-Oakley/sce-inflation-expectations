"""Fixed proxy-cohort P/E materials for a future recursive-belief experiment.

Preparation only: no messages, answers, scorer, API client or authorization.
The first B month supplies the cohort and the sole initial belief file. Later
months supply public environments, never another person's/month's prior.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha
from .fullperiod_materialization import news_pool_for_prompts
from .media_mechanism_v3 import draw_personal, four_tier_levels
from .recent_b_news_refresh import (
    DEFAULT_OUT as B_INPUTS, MONTHS, SEED, _latest_cpi_release_day,
    _load_labels, _news_pools,
)
from .state_continuity import month_index
from ..coverage_preparation import latest_wave, national_confidence
from ..news_exposure import interests_for_profile
from ..news_selection_trial import RecallRules, RULE_FILE
from ..procurement_price_views import choose_categories, render_view, validate_cutoff
from ..state_continuity_runtime import render_state

DEFAULT_OUT = ROOT / "outputs/sce_recent_b_continuity_pe_20261026_v2"
B_READINESS = ROOT / "outputs/sce_recent_b_news_refresh_readiness_20261025_v1/acceptance.json"
BASE_CONFIDENCE = ROOT / "docs/workstreams/20261017_reference_scaleup/confidence_sources.json"
MORE_CONFIDENCE = ROOT / "data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json"
POLICIES = ROOT / "data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json"
FOODS = ROOT / "outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json"


def checked_months(months):
    months = tuple(str(m) for m in months)
    if len(months) < 2 or len(set(months)) != len(months) or any(m not in MONTHS for m in months):
        raise ValueError("At least two unique registered B months required")
    if months[0] != MONTHS[0]:
        raise ValueError("This fixed-cohort preparation must retain the 202511 root; use a prefix of B11")
    if any(month_index(b) - month_index(a) != 1 for a, b in zip(months, months[1:])):
        raise ValueError("Recursive P/E preparation requires consecutive ordered months")
    return months


def dependency_plan(ids, months):
    months = checked_months(months)
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Unique fixed proxy identities required")
    return [{"month": month, "agent_id": aid,
             "initial_state_source": "initial_states_private.json" if i == 0 else None,
             "dependency": None if i == 0 else {"month": months[i - 1], "agent_id": aid}}
            for i, month in enumerate(months) for aid in sorted(ids)]


def validate_dependencies(nodes, ids, months):
    expected = dependency_plan(ids, months)
    if nodes != expected:
        raise ValueError("A recursive node must follow the previous month of the same fixed proxy")
    return {"positions": len(nodes), "roots": len(ids), "edges": len(nodes) - len(ids),
            "fixed_identities": len(ids), "all_months_same_roster": True,
            "later_independent_initializers": 0}


def resolve_prior(node, initial, saved_states):
    """Pure future-runtime interface; missing predecessors are never replaced.

    saved_states is keyed by (month, agent_id), with an explicit identity/month
    envelope. Recorded technical failures may carry the prior unchanged, but
    cannot silently inject a new synthetic/observed state from another source.
    """
    aid, month = node["agent_id"], node["month"]
    dep = node["dependency"]
    if dep is None:
        if node.get("initial_state_source") != "initial_states_private.json":
            raise ValueError("Only a declared chain root can initialize a belief")
        state = initial[aid]
        if any(field["source_kind"] != "synthetic_donor" for field in state["fields"].values()):
            raise ValueError("The fixed B root must use its synthetic initial seed, not real personal answers")
    else:
        if (dep["agent_id"] != aid or month_index(month) - month_index(dep["month"]) != 1
                or node.get("initial_state_source") is not None):
            raise ValueError("A chain cannot refresh or swap its prior")
        key = (dep["month"], aid)
        if key not in saved_states:
            raise ValueError("Previous simulated state is unavailable; do not use a later B initializer")
        record = saved_states[key]
        if record["agent_id"] != aid or record["month"] != dep["month"]:
            raise ValueError("Saved state identity/month differs from its dependency")
        state = record["state"]
        if any(field["source_kind"] == "own_observed" for field in state["fields"].values()):
            raise ValueError("A recursive B chain cannot refresh true personal answers")
        for key, field in state["fields"].items():
            if field["source_kind"] == "synthetic_donor" and field != initial[aid]["fields"][key]:
                raise ValueError("A retained synthetic field must equal this proxy's original seed")
    render_state(state, month)  # shared legality and strictly earlier-source checks
    return deepcopy(state)


def fixed_population(base, month, cutoff, source_wave):
    population = deepcopy(base)
    if population.get("materialized_count") != len(population["personas"]):
        raise ValueError("Invalid initial proxy population count")
    ids = [p["agent_id"] for p in population["personas"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Repeated fixed proxy identity")
    for person in population["personas"]:
        if person["weight"] != 1.0:
            raise ValueError("Analysis weights must stay outside model instructions")
    population["provider_args"].update(
        source="fixed_initial_B_proxy_cohort_for_recursive_candidate",
        source_reference_period=str(source_wave), target_month=month[:4] + "-" + month[4:],
        as_of=cutoff, profile_update_policy="frozen_initial_source_no_entry_exit_or_macro_updates",
        strict_B_eligible=False)
    return population


def validate_public_environment(environment, cutoff):
    when = datetime.fromisoformat(cutoff)
    if when.tzinfo is None:
        raise ValueError("Aware global B cutoff required")
    if (environment["provider_args"]["targets"][0]["as_of"] != cutoff
            or environment.get("scheduled_events") or environment["information_program"]["broadcasts"]
            or any(environment["provider_args"]["events_by_step"].values())):
        raise ValueError("Unexpected cutoff or unreviewed external event/broadcast")
    for rows in environment["provider_args"]["signals_by_step"].values():
        for row in rows:
            published = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
            if published.tzinfo is None or published > when:
                raise ValueError("Future/undated public environment signal")
            name = row["signal_id"].casefold()
            if "sce" in name or "nyfed" in name or "consumer_expectations" in name:
                raise ValueError("National SCE signals need a separately declared symmetric-information design")


def _verify_manifest(folder, manifest, sources):
    for root, key in ((folder, "files_sha256"), (ROOT, "source_sha256")):
        for name, digest in manifest[key].items():
            path = (root / name).resolve()
            if not path.is_relative_to(root) or not path.is_file() or sha(path) != digest:
                raise ValueError("Candidate source/prepared hash mismatch: " + name)
            if root == ROOT:
                sources[str(path.relative_to(ROOT))] = digest


def prepare(out=DEFAULT_OUT, *, months=MONTHS):
    from socioverse.schemas import PopulationBundle, EnvironmentBundle
    out = Path(out).resolve(); months = checked_months(months)
    if out.exists() or not out.is_relative_to(ROOT / "outputs"):
        raise ValueError("Fresh ignored output folder required")
    sources = {}
    def pin(path):
        path = Path(path).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError("Sources must be local project artifacts")
        sources[str(path.relative_to(ROOT))] = sha(path)
        return read_json(path)
    manifest = pin(B_INPUTS / "manifest.json")
    _verify_manifest(B_INPUTS, manifest, sources)
    ready = pin(B_READINESS)
    if (ready["input_manifest_sha256"] != sha(B_INPUTS / "manifest.json") or ready["new_api_calls"] != 0
            or ready["status"] != "passed_offline_B11_news_refresh_readiness"
            or ready["source_and_prepared_hashes_verified"] is not True):
        raise ValueError("B readiness must match the existing offline input candidate")
    for name, digest in ready["extra_dependency_sha256"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("B inherited preparation dependency changed: " + name)
        sources[name] = digest
    parent_summary = pin(B_INPUTS / "summary.json")
    first = months[0]; first_dir = B_INPUTS / "prompts" / first
    base = pin(first_dir / "population.json")
    initial = pin(first_dir / "initial_states_private.json")
    baskets = pin(first_dir / "baskets_private.json")
    people = {p["agent_id"]: p for p in base["personas"]}
    ids = sorted(people)
    if len(ids) != 512 or set(initial) != set(ids) or set(baskets) != set(ids):
        raise ValueError("Full initial 512-person B proxy cohort required")
    preflight = ROOT / parent_summary["population_preflight"]
    plans = {r["month"]: r for r in pin(preflight / "monthly_input_plan.json")}
    selected = pin(preflight / "selected_proxy_population_private.json")
    first_source = plans[first]["old_population_reference_period"]
    frame = {r["persona"]["agent_id"]: r for r in selected[first]}
    if set(frame) != set(ids):
        raise ValueError("Initial proxy weight frame differs")
    weights = {aid: {key: frame[aid][key] for key in
                    ("stratum", "analysis_weight", "raw_source_weight", "inclusion_probability")}
               for aid in ids}
    import math
    if any(not math.isfinite(r["analysis_weight"]) or r["analysis_weight"] <= 0 for r in weights.values()):
        raise ValueError("Positive finite fixed-cohort weights required")
    role_source = pin(B_INPUTS / "prompts/role_assignments_private.json")
    roles = {r["agent_id"]: {"role": r["role"], "matching_features": r["features"]}
             for r in role_source if r["month"] == first}
    if set(roles) != set(ids):
        raise ValueError("Initial grocery-role assignments incomplete")
    tiers = four_tier_levels(ids, int(first), SEED)
    # No later per-month independent prior file is opened. Source provenance of
    # the single seed remains explicit, distinct from its synthetic reference.
    prior_provenance = pin(ROOT / parent_summary["prior_source"] / f"{first}_initial_states_private.json")
    for aid in ids:
        render_state(initial[aid], first)
        if prior_provenance[aid]["actual_person_previous_answer"]:
            raise ValueError("The B seed is synthetic, not an actual personal history")
    old_assembly_summary = pin(ROOT / parent_summary["parent_assembly"] / "prompts/summary.json")
    labels = _load_labels(old_assembly_summary, sources)
    rules = RecallRules(pin(RULE_FILE))
    foods = pin(FOODS); policies = pin(POLICIES)
    waves = pin(BASE_CONFIDENCE)["waves"] + pin(MORE_CONFIDENCE)["waves"]
    for path in (Path(__file__), ROOT / "scripts/prepare_sce_recent_b_continuity_pe.py"):
        sources[str(path.relative_to(ROOT))] = sha(path)
    out.mkdir(parents=True)
    # Exactly one initializer file, outside monthly environment folders.
    for name, obj in (("fixed_population_private.json", base), ("fixed_weights_private.json", weights),
                      ("fixed_baskets_private.json", baskets), ("fixed_roles_private.json", roles),
                      ("fixed_news_tiers_private.json", tiers), ("initial_states_private.json", initial),
                      ("initial_prior_provenance_private.json", prior_provenance)):
        dump(out / name, obj)
    coverage = []
    for month in months:
        plan = plans[month]; cutoff = plan["as_of"]
        population = fixed_population(base, month, cutoff, first_source)
        PopulationBundle.model_validate(population)
        environment = pin(B_INPUTS / "prompts" / month / "environment.json")
        validate_public_environment(environment, cutoff)
        environment["provider_args"]["persona_by_id"] = {aid: people[aid]["attributes"] for aid in ids}
        EnvironmentBundle.model_validate(environment)
        food = foods[month]; validate_cutoff(list(food.values()), cutoff)
        for fact in food.values():
            if sha(ROOT / fact["source_file"]) != fact["source_sha256"]:
                raise ValueError("Archived price bytes changed")
            sources[fact["source_file"]] = fact["source_sha256"]
        eligible = [r for r in policies.values() if datetime.fromisoformat(r["published_at"]) <= datetime.fromisoformat(cutoff)]
        if not eligible:
            raise ValueError("No eligible policy before cutoff")
        policy = max(eligible, key=lambda r: r["published_at"])
        if sha(ROOT / policy["file"]) != policy["sha256"]:
            raise ValueError("Policy archive changed")
        sources[policy["file"]] = policy["sha256"]
        wave = latest_wave(waves, cutoff)
        sources[wave["local_file"]] = sha(ROOT / wave["local_file"])
        old_context = pin(B_INPUTS / "prompts" / month / "timing_context_private.json")
        representative = next(iter(old_context.values()))
        if (representative["as_of"] != cutoff or representative["policy_published_at"] != policy["published_at"]
                or representative["food_published_at"] != food["food_at_home"]["published_at"]):
            raise ValueError("Public price/policy deadline differs from the prepared independent B")
        target = month[:4] + "-" + month[4:]
        raw, _, news_sources = news_pool_for_prompts(ROOT, target, cutoff, rules)
        sources.update(news_sources)
        release_day = _latest_cpi_release_day(environment, cutoff)
        common, pool, pool_audit = _news_pools(raw, labels, cutoff, release_day)
        contexts, views = {}, {}
        for aid in ids:
            personal = draw_personal(pool, [], tiers[aid] - 3, f"{SEED}|{month}|{aid}",
                interests_for_profile(people[aid]["attributes"], baskets[aid]["spending_shares"]),
                alarming_boost=1.0, cpi_boost=1.5, fox_share=0.0)
            categories = choose_categories(roles[aid]["role"], aid, 20261019)
            grocery = render_view(roles[aid]["role"], categories, food,
                                 "compare with the earlier synthetic/simulated state at runtime")
            grocery = grocery.replace("availability relative to your previous survey:",
                                      "availability relative to the earlier belief-state reference:")
            contexts[aid] = {"as_of": cutoff, "common_news": common, "personal_news": personal,
                             "policy_published_at": policy["published_at"],
                             "food_published_at": food["food_at_home"]["published_at"]}
            views[aid] = {"news_tier": tiers[aid], "grocery_role": roles[aid]["role"],
                          "grocery_categories": categories, "grocery_text": grocery,
                          "spending_shares": baskets[aid]["spending_shares"],
                          "synthetic_fed_confidence": national_confidence(aid, 42, wave),
                          "confidence_wave": wave["wave_id"]}
        folder = out / month; folder.mkdir()
        for name, obj in (("population.json", population), ("environment.json", environment),
                          ("timing_context_private.json", contexts), ("visible_information_private.json", views),
                          ("policy.json", policy), ("confidence_wave.json", wave), ("food_facts.json", food)):
            dump(folder / name, obj)
        coverage.append({"month": month, "as_of": cutoff, "n": len(ids),
            "fixed_population_source_wave": first_source,
            "source_age_months": month_index(month) - month_index(first_source),
            "news_tiers": dict(Counter(tiers.values())), "common_routing_cpi_release_day": release_day,
            "food_published_at": food["food_at_home"]["published_at"],
            "policy_published_at": policy["published_at"], "confidence_wave": wave["wave_id"], **pool_audit})
        print(f"{month}: fixed 512 proxies + dated P/E; no later prior loaded", flush=True)
    nodes = dependency_plan(ids, months)
    lineage = validate_dependencies(nodes, ids, months)
    dump(out / "state_dependencies_private.json", nodes)
    summary = {"schema": "sce_recursive_b_PE_candidate/v1", "status": "prepared_PE_only_not_prompt_or_execution_ready",
        "months": list(months), "n_fixed_proxies": len(ids), "person_months": len(nodes), "coverage": coverage,
        "lineage_check": lineage, "initial_state_files": 1, "later_initial_state_files": 0,
        "population_source_wave": first_source, "cohort_base_month": first,
        "population_and_weights": "Fixed initial B proxy cohort and source-wave weights; not current SCE panel composition.",
        "news_attention": "Initial 4/8/16/32 tier held fixed by identity; monthly article contents re-drawn by fixed seeds.",
        "national_SCE_anchor_policy": "Only the first initial prior is calibrated; no later national anchor is inserted into P/E.",
        "provider_environment_usage": "Archived provider bundle is a host/reserve; actual visible views are separate. Prompt wiring is still pending.",
        "strict_B_eligible": False, "new_api_calls": 0, "target_truth_opened": False,
        "LLM_responses_opened": False, "official_schema_months": len(months), "official_core_units": 0,
        "authorization_written": False, "execution_package_created": False,
        "pending": ["Choose duration, controls and common public SCE information policy before a live experiment.",
                    "Wire templates to first seed / saved simulated predecessors, technical retention and checkpoint ledgers.",
                    "Complete official Core and deterministic execution checks on the final messages.",
                    "Set evaluation, fixed model, calls and budget; obtain separate live authorization."],
        "limits": ["Fixed baseline ages/education/income/employment and source weights do not track later actual composition.",
                   "Proxy source eligibility inherits the nine-month-lag assumption, not certified historical file vintages.",
                   "News/policy original text vintages and model knowledge boundaries remain unverified.",
                   "No actual recent micro targets; person-level dispersion is descriptive only."]}
    dump(out / "summary.json", summary)
    dump(out / "manifest.json", {"files_sha256": {str(p.relative_to(out)): sha(p) for p in out.rglob("*.json")},
                                "source_sha256": sources, "new_api_calls": 0, "target_truth_opened": False})
    return summary
