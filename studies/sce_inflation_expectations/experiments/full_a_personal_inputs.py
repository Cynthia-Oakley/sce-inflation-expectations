"""Prepare outcome-free full-period A prompts with person-specific cutoffs.

The package is a local, no-API input artifact.  It projects only respondent
identity, target month and survey completion date for timing; prior states,
personas, baskets, roles and the 54-cell design are copied from the frozen
full-period package.  The date exclusion is never replaced.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from .frozen_batch import ROOT, dump, read_json, sha
from .media_mechanism_trial import (
    INFLATION_PATTERN,
    is_alarming,
    is_sce_report,
    parse_time,
    select_salient_common,
    text_of,
)
from .media_mechanism_v3 import draw_personal, four_tier_levels
from .fullperiod_materialization import news_pool_for_prompts
from .media_timing_inputs import (
    FRAME,
    cutoff_for_response,
    food_text,
    load_date_map,
    parsed,
    transform,
)
from ..belief_trial_preparation import confidence_block
from ..coverage_preparation import latest_wave, national_confidence
from ..news_exposure import NEWS_KEYS, interests_for_profile
from ..news_exposure_demo import exact_deduplicate, news_tags
from ..news_label_compat import normalize_label
from ..news_selection_trial import RecallRules, RULE_FILE
from ..prior_belief_experiment import message_hash
from ..procurement_price_views import validate_cutoff


ASSEMBLY = ROOT / "outputs/sce_monthly_fine_full_assembly_20261023_v3"
OLD_INPUTS = ROOT / "outputs/sce_monthly_fine_full_inputs_20261023_v2"
DELIVERY = ROOT / "outputs/sce_fullperiod_materialized_20261022_v2"
POLICY_BASE = ROOT / "docs/workstreams/20261021_fullperiod/new2025_policy_sources.json"
POLICY_SUPPLEMENT = ROOT / "data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json"
CONFIDENCE_BASE = ROOT / "docs/workstreams/20261017_reference_scaleup/confidence_sources.json"
CONFIDENCE_SUPPLEMENT = ROOT / "data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json"
LABEL_OVERLAY = ROOT / "outputs/sce_late2025_label_reuse_20261025_v1/base_label_overlay.jsonl"
EARLY_FOOD = ROOT / "outputs/sce_early_food_evidence_20261025_v1/candidate_food_catalog.json"
DEFAULT_OUT = ROOT / "outputs/sce_full_a_personal_inputs_20261025_v1"
NY = ZoneInfo("America/New_York")
EXPECTED_ORIGINAL = 41_984
EXPECTED_EXCLUDED = 14
EXPECTED_RETAINED = 41_970
NEWS_SEED = 20261025
COMMON_NEWS_N = 3
TIER_LEVELS = (4, 8, 16, 32)
GRID_CELLS = {
    f"{education}|{numeracy}|{age}|{income}"
    for education in ("high_school", "some_college", "college")
    for numeracy in ("High", "Low")
    for age in ("under_40", "40_60", "over_60")
    for income in ("under_50k", "50k_100k", "over_100k")
}
INPUT_PRICE_PER_MTOK = 0.259
OUTPUT_PRICE_PER_MTOK = 0.8
ESTIMATED_OUTPUT_TOKENS = 300


def _without_tone(label: dict) -> dict:
    """Project topic-label fields only; warning/persistence labels are not used."""
    return {key: deepcopy(label[key]) for key in ("article_id", "decision", "topics", "scope")}


def _load_overlay(path: Path, sources: dict[str, str]) -> dict[str, dict]:
    sources[str(path.relative_to(ROOT))] = sha(path)
    result = {}
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        label = normalize_label(row["base_label"])
        target_months = set(row.get("target_month") or [])
        if not target_months:
            raise ValueError(f"Base-label overlay row {line_no} has no target month")
        aid = row["article_id"]
        if label["article_id"] != aid:
            raise ValueError(f"Base-label overlay article ID mismatch at line {line_no}")
        normalized = _without_tone(label)
        prior = result.get(aid)
        value = {"label": normalized, "target_months": sorted(target_months)}
        if prior and prior != value:
            raise ValueError(f"Conflicting base-label overlay for {aid}")
        result[aid] = value
    return result


def _label_inventory(month: str, next_month: str, overlay: dict[str, dict], sources: dict[str, str]) -> dict[str, dict]:
    labels = {}
    for label_month in (month, next_month):
        path = DELIVERY / label_month / "news_label_index.json"
        sources[str(path.relative_to(ROOT))] = sha(path)
        for row in read_json(path)["pool"]:
            if row.get("label"):
                label = normalize_label(row["label"])
                labels.setdefault(row["article_id"], _without_tone(label))
    target_iso = f"{month[:4]}-{month[4:]}"
    for aid, entry in overlay.items():
        if target_iso not in entry["target_months"]:
            continue
        labels[aid] = deepcopy(entry["label"])
    return labels


def _build_keep_pool(raw_rows: list[dict], labels: dict[str, dict], month: str, cutoff: str) -> tuple[list[dict], dict]:
    pool = []
    missing = []
    counts = Counter()
    cutoff_dt = parsed(cutoff)
    target = f"{month[:4]}-{month[4:]}"
    start = datetime.fromisoformat(f"{_previous_month(target)}-01T00:00:00").replace(tzinfo=NY)
    for original in raw_rows:
        published = parsed(original["pub_date"])
        if published > cutoff_dt:
            continue
        if published < start:
            raise ValueError("News pool included material before the previous-month first day")
        if is_sce_report(original):
            counts["excluded_sce_report"] += 1
            continue
        label = labels.get(original["article_id"])
        if label is None:
            if original.get("new_hits"):
                missing.append(original["article_id"])
            else:
                counts["unlabeled_noncandidate"] += 1
            continue
        if label["decision"] != "keep":
            counts["topic_labeled_not_keep"] += 1
            continue
        record = {key: original[key] for key in NEWS_KEYS - {"routing_tags", "semantic_label"}}
        record.update(routing_tags=news_tags(original), semantic_label=deepcopy(label))
        pool.append(record)
        counts["topic_labeled_keep"] += 1
    if missing:
        raise ValueError(
            f"Missing base topic labels for {month} cutoff {cutoff}: "
            + ",".join(sorted(set(missing))[:40])
        )
    pool = exact_deduplicate(pool)
    counts["deduplicated_keep_pool"] = len(pool)
    if any(parsed(row["pub_date"]) > cutoff_dt for row in pool):
        raise ValueError("Future news survived personal-cutoff filter")
    return pool, dict(counts)


def _previous_month(target: str) -> str:
    year, month = map(int, target.split("-"))
    return f"{year - (month == 1):04d}-{12 if month == 1 else month - 1:02d}"


def _food_snapshot(foods: dict, cutoff: str) -> tuple[str, dict]:
    eligible = [(key, row) for key, row in foods.items()
                if parsed(row["food_at_home"]["published_at"]) <= parsed(cutoff)]
    if not eligible:
        raise ValueError(f"No archived food-price release available by {cutoff}")
    key, facts = max(eligible, key=lambda pair: parsed(pair[1]["food_at_home"]["published_at"]))
    validate_cutoff(facts.values(), cutoff)
    return key, facts


def _policy_snapshot(policies: dict, cutoff: str) -> dict:
    eligible = [row for row in policies.values() if parsed(row["published_at"]) <= parsed(cutoff)]
    if not eligible:
        raise ValueError(f"No archived policy statement available by {cutoff}")
    record = max(eligible, key=lambda row: parsed(row["published_at"]))
    if len(record.get("facts") or []) != 3:
        raise ValueError("Selected policy statement must have three dated facts")
    return record


def _common_score_key(row: dict, release_day: str):
    inflation = bool(INFLATION_PATTERN.search(text_of(row)))
    release = inflation and parse_time(row["pub_date"]).date().isoformat() == release_day
    living = bool(set(row["routing_tags"]) & {
        "food", "road_fuel", "rental_housing", "owned_housing", "labor_income"
    })
    score = 4 * inflation + 8 * release + 2 * living + 1 * is_alarming(row)
    return (-score, -parse_time(row["pub_date"]).timestamp(), row["article_id"])


def _select_common(pool: list[dict], release_day: str) -> tuple[list[dict], dict]:
    """Prefer three A1 rows; fill any shortage from the same eligible pool."""
    a1 = [row for row in pool if row.get("placement") == "a1"]
    if len(a1) >= COMMON_NEWS_N:
        common = select_salient_common(pool, release_day)
        return common, {"rule": "existing_a1_salience", "a1_available": len(a1), "fallback_n": 0}
    if len(pool) < COMMON_NEWS_N:
        raise ValueError(
            f"Eligible news pool has {len(pool)} total rows; three common stories are required"
        )
    selected = sorted(a1, key=lambda row: _common_score_key(row, release_day))[:COMMON_NEWS_N]
    selected_ids = {row["article_id"] for row in selected}
    remaining = [row for row in pool if row["article_id"] not in selected_ids]
    selected.extend(sorted(remaining, key=lambda row: _common_score_key(row, release_day))[
        :COMMON_NEWS_N - len(selected)
    ])
    selected.sort(key=lambda row: (parse_time(row["pub_date"]), row["article_id"]))
    if len(selected) != COMMON_NEWS_N:
        raise ValueError("Could not fill three common stories from the eligible news pool")
    return selected, {
        "rule": "a1_first_then_eligible_pool_salience",
        "a1_available": len(a1),
        "fallback_n": COMMON_NEWS_N - len(a1),
    }


def _pin_source_file(path_value: str, expected_sha: str, sources: dict[str, str]) -> None:
    path = (ROOT / path_value).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError("Source path must be an existing repository file: " + path_value)
    observed = sha(path)
    if observed != expected_sha:
        raise ValueError("Archived source checksum changed: " + path_value)
    sources[str(path.relative_to(ROOT))] = observed


def _calibrate_remaining_weights(original: dict[str, dict], keep_ids: set[str], month: str):
    if len(original) != 512 or not keep_ids <= set(original):
        raise ValueError(f"{month}: complete 512-row original weights required")
    original_cells = defaultdict(list)
    retained_cells = defaultdict(list)
    for aid, row in original.items():
        cell = row.get("profile_cell") or row.get("stratum")
        if not isinstance(cell, str) or not cell:
            raise ValueError(f"{month}: missing 54-cell profile for {aid}")
        if cell not in GRID_CELLS and cell != "unknown":
            raise ValueError(f"{month}: weight cell is outside the 54-cell grid: {cell}")
        if row.get("grid_version") != "education_numeracy_age_income_54_v1" or row.get("weight_valid") is not True:
            raise ValueError(f"{month}: invalid original fine-grid weight for {aid}")
        base = row.get("poststratified_weight")
        if type(base) not in (int, float) or not math.isfinite(base) or base <= 0:
            raise ValueError(f"{month}: invalid original post-stratified weight for {aid}")
        original_cells[cell].append((aid, float(base)))
        if aid in keep_ids:
            retained_cells[cell].append((aid, float(base)))
    empty = sorted(set(original_cells) - set(retained_cells))
    if empty:
        raise ValueError(f"{month}: empty 54-cell mass after date exclusions: {empty}")
    original_zero_mass_grid_cells = sorted(GRID_CELLS - set(original_cells))
    result = {}
    cell_receipt = {}
    for cell in sorted(original_cells):
        target_mass = sum(weight for _, weight in original_cells[cell])
        retained_mass = sum(weight for _, weight in retained_cells[cell])
        if not math.isfinite(target_mass) or target_mass <= 0 or retained_mass <= 0:
            raise ValueError(f"{month}: nonpositive mass in 54-cell {cell}")
        factor = target_mass / retained_mass
        cell_receipt[cell] = {
            "original_n": len(original_cells[cell]),
            "retained_n": len(retained_cells[cell]),
            "original_poststratified_mass": target_mass,
            "retained_precalibration_mass": retained_mass,
            "exclusion_calibration_factor": factor,
            "retained_calibrated_mass": 0.0,
        }
        for aid, base_weight in retained_cells[cell]:
            row = deepcopy(original[aid])
            adjusted = base_weight * factor
            row.update(
                original_poststratified_weight=base_weight,
                analysis_weight=adjusted,
                poststratified_weight=adjusted,
                exclusion_calibration_factor=factor,
                cell_original_mass=target_mass,
                cell_retained_n=len(retained_cells[cell]),
            )
            result[aid] = row
            cell_receipt[cell]["retained_calibrated_mass"] += adjusted
        if not math.isclose(cell_receipt[cell]["retained_calibrated_mass"], target_mass,
                            rel_tol=1e-12, abs_tol=1e-10):
            raise ValueError(f"{month}: calibrated mass does not restore original 54-cell {cell}")
    return result, cell_receipt, original_zero_mass_grid_cells


def _date_for_person(date_map: dict, month: str, aid: str):
    value = date_map.get((int(month), aid))
    if value is None:
        return None, None, "missing_completion_date"
    try:
        cutoff = cutoff_for_response(value, month)
    except ValueError:
        return str(value), None, "cross_month_completion_date"
    return str(value), cutoff, None


def _load_sources(sources: dict[str, str]):
    assembly_manifest_path = ASSEMBLY / "manifest.json"
    assembly_manifest = read_json(assembly_manifest_path)
    if assembly_manifest.get("status") != "offline_monthly_A_bundle_complete_not_paid_authorized":
        raise ValueError("Frozen full82 assembly is not complete")
    if assembly_manifest.get("new_api_calls") != 0 or assembly_manifest.get("new_model_answers") != 0:
        raise ValueError("Frozen full82 source package records live calls or new answers")
    months = [str(m) for m in assembly_manifest["months"]]
    if len(months) != 82 or len(set(months)) != 82:
        raise ValueError("Expected 82 unique frozen full-period months")
    source_files = [
        assembly_manifest_path,
        ASSEMBLY / "evaluation_recipe.json",
        ASSEMBLY / "prompts" / "role_assignments_private.json",
        OLD_INPUTS / "summary.json",
        FRAME,
        DELIVERY / "food_catalog.json",
        POLICY_BASE,
        POLICY_SUPPLEMENT,
        CONFIDENCE_BASE,
        CONFIDENCE_SUPPLEMENT,
        LABEL_OVERLAY,
        EARLY_FOOD,
        RULE_FILE,
        Path(__file__),
        Path(__file__).with_name("media_timing_inputs.py"),
        Path(__file__).with_name("media_mechanism_v3.py"),
        Path(__file__).with_name("media_mechanism_trial.py"),
        Path(__file__).with_name("fullperiod_materialization.py"),
        Path(__file__).parents[1] / "news_label_compat.py",
        Path(__file__).parents[1] / "news_exposure_demo.py",
        Path(__file__).parents[1] / "procurement_price_views.py",
        Path(__file__).parents[1] / "coverage_preparation.py",
        Path(__file__).parents[1] / "news_mechanism_label_preparation.py",
    ]
    for path in source_files:
        sources[str(path.relative_to(ROOT))] = sha(path)
    policies = read_json(POLICY_BASE)
    policies.update(read_json(POLICY_SUPPLEMENT))
    base_confidence = read_json(CONFIDENCE_BASE)["waves"]
    supplement_confidence = read_json(CONFIDENCE_SUPPLEMENT)["waves"]
    waves = base_confidence + supplement_confidence
    if not waves:
        raise ValueError("No confidence-source snapshots registered")
    foods = read_json(DELIVERY / "food_catalog.json")
    candidate_foods = read_json(EARLY_FOOD)
    # Candidate catalog contributes its additional pre-2019 release only.
    for key, candidate in candidate_foods.items():
        if key in foods:
            raise ValueError("Early food candidate unexpectedly overlaps frozen catalog: " + key)
        foods[key] = candidate
    if "201812" not in candidate_foods:
        raise ValueError("Expected the early 2018-12 food release candidate")
    overlay = _load_overlay(LABEL_OVERLAY, sources)
    rules = RecallRules(read_json(RULE_FILE))
    return months, policies, waves, foods, overlay, rules


def _tier_counts(tiers: dict[str, int], ids: set[str]) -> dict[str, int]:
    return {str(level): sum(tiers[aid] == level for aid in ids) for level in TIER_LEVELS}


def _serialize_prompt(messages: list[dict], month: str, aid: str) -> dict:
    if len(messages) != 1 or messages[0].get("role") != "user":
        raise ValueError(f"{month}/{aid}: exactly one user message required")
    if not messages[0].get("content") or "[[SCE_CONTINUITY_" in messages[0]["content"]:
        raise ValueError(f"{month}/{aid}: unresolved state/timing token")
    return {"messages": messages, "prompt_sha256": message_hash(messages)}


def _sample_context(
    *, month: str, aid: str, tier: int, cutoff: str, common: list[dict], personal: list[dict],
    food_key: str, facts: dict, policy: dict, wave: dict, pool_receipt: dict,
    common_selection: dict,
) -> dict:
    return {
        "agent_id": aid,
        "target_month": f"{month[:4]}-{month[4:]}",
        "as_of": cutoff,
        "information_cutoff": cutoff,
        "cutoff_rule": "survey completion date minus one calendar day at 23:59:59 America/New_York",
        "news_window_start": datetime.fromisoformat(
            f"{_previous_month(f'{month[:4]}-{month[4:]}')}-01T00:00:00"
        ).replace(tzinfo=NY).isoformat(),
        "news_tier": tier,
        "common_news_count": len(common),
        "personal_news_count": len(personal),
        "common_news": common,
        "personal_news": personal,
        "common_selection": common_selection,
        "food_catalog_period": food_key,
        "food_reference_period": facts["food_at_home"]["reference_period"],
        "food_published_at": facts["food_at_home"]["published_at"],
        "policy_published_at": policy["published_at"],
        "confidence_wave_id": wave["wave_id"],
        "pool_receipt": pool_receipt,
        "selection": {"common_n": COMMON_NEWS_N, "alarming_boost": 1.0, "cpi_boost": 1.5,
                      "fox_share": 0.0, "tone_or_persistence_used": False,
                      "seed": f"{NEWS_SEED}|{month}|{aid}"},
    }


def prepare(out: Path = DEFAULT_OUT) -> dict:
    """Build all 41,970 personal-cutoff A prompts locally; never uses API/truth."""
    out = Path(out).resolve()
    outputs = (ROOT / "outputs").resolve()
    if out.exists() or not out.is_relative_to(outputs):
        raise ValueError("Fresh output path under repository outputs required")

    source_hashes: dict[str, str] = {}
    months, policies, waves, foods, overlay, rules = _load_sources(source_hashes)
    date_map = load_date_map()  # Exactly userid/date/survey_date are projected by this helper.
    sources = {str(FRAME.relative_to(ROOT)): sha(FRAME)}
    source_hashes.update(sources)
    salt_state_path = DELIVERY / "201905" / "population_state_private.json"
    source_hashes[str(salt_state_path.relative_to(ROOT))] = sha(salt_state_path)

    staged = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=outputs))
    exclusions = []
    rows_by_month = {}
    month_summaries = []
    total_prompt_chars = total_prompt_bytes = total_estimated_input_tokens = 0
    max_prompt_chars = max_prompt_bytes = 0
    all_prompt_hashes = Counter()
    current_month = None
    builder_sha256 = sha(Path(__file__))
    try:
        for month in months:
            current_month = month
            base = ASSEMBLY / "prompts" / month
            preview_path = base / "initial_previews_private.json"
            state_path = base / "initial_states_private.json"
            context_path = base / "timing_context_private.json"
            basket_path = base / "baskets_private.json"
            population_path = base / "population.json"
            weights_path = OLD_INPUTS / f"{month}_weights_private.json"
            role_path = ASSEMBLY / "prompts" / "role_assignments_private.json"
            for path in (preview_path, state_path, context_path, basket_path, population_path, weights_path,
                         role_path):
                source_hashes[str(path.relative_to(ROOT))] = sha(path)
            previews = read_json(preview_path)
            states = read_json(state_path)
            old_contexts = read_json(context_path)
            baskets = read_json(basket_path)
            population = read_json(population_path)
            old_weights = read_json(weights_path)
            people = {row["agent_id"]: row for row in population["personas"]}
            if not all(len(obj) == 512 for obj in (previews, states, old_contexts, baskets, old_weights)):
                raise ValueError(f"{month}: expected complete 512-person frozen inputs")
            ids = sorted(previews)
            if any(set(obj) != set(ids) for obj in (states, old_contexts, baskets, old_weights, people)):
                raise ValueError(f"{month}: identity mismatch across frozen inputs")
            tiers = four_tier_levels(ids, int(month))  # Assign all four tiers before cutoff exclusions.
            if _tier_counts(tiers, set(ids)) != {"4": 128, "8": 128, "16": 128, "32": 128}:
                raise ValueError(f"{month}: four-tier assignment is not balanced over all 512 IDs")
            roles = {
                row["agent_id"]: row["role"]
                for row in read_json(role_path)
                if row["month"] == month
            }
            if set(roles) != set(ids):
                raise ValueError(f"{month}: complete 512-row role mapping required")

            completion_dates = {}
            cutoffs = {}
            eligible_ids = set()
            excluded_this_month = []
            for aid in ids:
                survey_date, cutoff, reason = _date_for_person(date_map, month, aid)
                if reason is None and datetime.fromisoformat(states[aid]["comparison_reference_day"]).date() > parsed(cutoff).date():
                    reason = "prior_reference_after_personal_cutoff"
                completion_dates[aid] = survey_date
                if reason:
                    row = {"month": month, "agent_id": aid, "survey_date": survey_date,
                           "news_tier": tiers[aid], "reason": reason}
                    exclusions.append(row)
                    excluded_this_month.append(row)
                    continue
                eligible_ids.add(aid)
                cutoffs[aid] = cutoff
            if not eligible_ids:
                raise ValueError(f"{month}: no respondents eligible at their personal cutoffs")
            cutoff_counts = Counter(cutoffs.values())
            max_cutoff = max(cutoffs.values(), key=parsed)
            year, month_num = int(month[:4]), int(month[4:])
            target = f"{year}-{month_num:02d}"
            raw_superset, _, news_hashes = news_pool_for_prompts(ROOT, target, max_cutoff, rules)
            source_hashes.update(news_hashes)
            next_month = f"{year + (month_num == 12):04d}{1 if month_num == 12 else month_num + 1:02d}"
            labels = _label_inventory(month, next_month, overlay, source_hashes)

            # Cache each month x exact personal cutoff view, sharing the expensive
            # raw monthly archive parse across all completion dates in that month.
            cutoff_cache = {}
            for cutoff in sorted(cutoff_counts, key=parsed):
                pool, pool_receipt = _build_keep_pool(raw_superset, labels, month, cutoff)
                food_key, facts = _food_snapshot(foods, cutoff)
                policy = _policy_snapshot(policies, cutoff)
                wave = latest_wave(waves, cutoff)
                for record in facts.values():
                    _pin_source_file(record["source_file"], record["source_sha256"], source_hashes)
                _pin_source_file(policy["file"], policy["sha256"], source_hashes)
                _pin_source_file(wave["local_file"], wave["sha256"], source_hashes)
                common, common_receipt = _select_common(
                    pool, facts["food_at_home"]["published_at"][:10])
                if len(common) != COMMON_NEWS_N:
                    raise ValueError(f"{month} cutoff {cutoff}: exactly three eligible common stories required")
                available_ids = {row["article_id"] for row in pool}
                if not {row["article_id"] for row in common} <= available_ids:
                    raise ValueError("Common news is outside the cutoff-eligible pool")
                cutoff_cache[cutoff] = {"pool": pool, "common": common,
                                        "common_receipt": common_receipt, "food_key": food_key,
                                        "facts": facts, "policy": policy, "wave": wave,
                                        "receipt": pool_receipt}

            # Preflight every cutoff's remaining pool before rendering any prompt
            # for this month. This prevents a partial month if the largest tier
            # cannot be drawn without replacement.
            by_cutoff_aids = defaultdict(list)
            for aid in eligible_ids:
                by_cutoff_aids[cutoffs[aid]].append(aid)
            for cutoff, aids in by_cutoff_aids.items():
                cached = cutoff_cache[cutoff]
                available_n = len(cached["pool"]) - len(cached["common"])
                required_n = max(tiers[aid] - COMMON_NEWS_N for aid in aids)
                cached["personal_pool_n"] = available_n
                cached["required_personal_pool_n"] = required_n
                if available_n < required_n:
                    raise ValueError(
                        f"{month} cutoff {cutoff}: eligible personal pool has {available_n} rows, "
                        f"but tier requires {required_n}"
                    )

            calibrated_weights, cell_masses, original_zero_mass_cells = _calibrate_remaining_weights(
                old_weights, eligible_ids, month)

            prompts = {}
            contexts = {}
            roster_rows = {}
            for aid in ids:
                reason = next((x["reason"] for x in excluded_this_month if x["agent_id"] == aid), None)
                roster_rows[aid] = {
                    "agent_id": aid,
                    "eligible": aid in eligible_ids,
                    "news_tier": tiers[aid],
                    "personal_news_count": tiers[aid] - COMMON_NEWS_N,
                    "role": roles[aid],
                    "profile_cell": old_weights[aid]["profile_cell"],
                    "survey_date": completion_dates[aid],
                    "information_cutoff": cutoffs.get(aid),
                    "exclusion_reason": reason,
                }

            for cutoff, aids in by_cutoff_aids.items():
                cached = cutoff_cache[cutoff]
                pool, common = cached["pool"], cached["common"]
                common_ids = {row["article_id"] for row in common}
                for aid in aids:
                    basket = baskets[aid]
                    profile = people[aid]["attributes"]
                    interest = interests_for_profile(profile, basket["spending_shares"])
                    personal = draw_personal(
                        [row for row in pool if row["article_id"] not in common_ids], [],
                        tiers[aid] - COMMON_NEWS_N,
                        f"{NEWS_SEED}|{month}|{aid}", interest,
                        alarming_boost=1.0, cpi_boost=1.5, fox_share=0.0,
                    )
                    if len(personal) != tiers[aid] - COMMON_NEWS_N:
                        raise ValueError(f"{month}/{aid}: personal news tier count mismatch")
                    if {row["article_id"] for row in personal} & common_ids:
                        raise ValueError("Common and personal news overlap")
                    context = _sample_context(
                        month=month, aid=aid, tier=tiers[aid], cutoff=cutoff,
                        common=common, personal=personal, food_key=cached["food_key"],
                        facts=cached["facts"], policy=cached["policy"], wave=cached["wave"],
                        pool_receipt=cached["receipt"], common_selection=cached["common_receipt"],
                    )
                    old_context = old_contexts[aid]
                    old_cutoff = old_context["as_of"]
                    old_policy = _policy_snapshot(policies, old_cutoff)
                    old_wave = latest_wave(waves, old_cutoff)
                    old_food = foods[month]
                    role = roles[aid]
                    old_food_text = food_text(role, aid, old_food)
                    old_conf = confidence_block(national_confidence(aid, 42, old_wave))
                    new_conf = confidence_block(national_confidence(aid, 42, cached["wave"]))
                    messages = transform(
                        previews[aid]["messages"], old_context, context, states[aid],
                        old_food_text, food_text(role, aid, cached["facts"]),
                        old_policy, cached["policy"], old_conf, new_conf,
                    )
                    prompts[aid] = _serialize_prompt(messages, month, aid)
                    contexts[aid] = context
                    text = messages[0]["content"]
                    prompt_chars = len(text)
                    prompt_bytes = len(text.encode("utf-8"))
                    total_prompt_chars += prompt_chars
                    total_prompt_bytes += prompt_bytes
                    max_prompt_chars = max(max_prompt_chars, prompt_chars)
                    max_prompt_bytes = max(max_prompt_bytes, prompt_bytes)
                    total_estimated_input_tokens += math.ceil(len(json.dumps(messages, ensure_ascii=False)) / 4)
                    all_prompt_hashes[prompts[aid]["prompt_sha256"]] += 1

            if set(prompts) != eligible_ids or set(contexts) != eligible_ids or set(calibrated_weights) != eligible_ids:
                raise ValueError(f"{month}: prompts/contexts/weights do not match eligible roster")
            tone_audit = _check_alarm_one_invariance_sample(
                month, cutoff_cache, by_cutoff_aids, tiers, baskets, people)
            month_folder = staged / month
            month_folder.mkdir()
            dump(month_folder / "prompts.json", {"month": month, "rows": prompts})
            dump(month_folder / "contexts_private.json", contexts)
            dump(month_folder / "weights_private.json", calibrated_weights)
            dump(month_folder / "roster_private.json", {
                "month": month, "frame_n": len(ids), "eligible_n": len(eligible_ids),
                "excluded_n": len(excluded_this_month), "rows": roster_rows,
            })
            rows_by_month[month] = len(prompts)
            month_summaries.append({
                "month": month,
                "original_n": len(ids),
                "eligible_n": len(eligible_ids),
                "excluded_n": len(excluded_this_month),
                "tier_counts_before_exclusion": _tier_counts(tiers, set(ids)),
                "tier_counts_after_exclusion": _tier_counts(tiers, eligible_ids),
                "cutoff_count": len(cutoff_cache),
                "common_pool_fallback_cutoffs": {
                    cutoff: cached["common_receipt"] for cutoff, cached in cutoff_cache.items()
                    if cached["common_receipt"]["fallback_n"] > 0
                },
                "cutoffs": {cutoff: n for cutoff, n in sorted(cutoff_counts.items(), key=lambda x: parsed(x[0]))},
                "personal_pool_capacity_by_cutoff": {
                    cutoff: {"available_n": cached["personal_pool_n"],
                             "required_max_n": cached["required_personal_pool_n"]}
                    for cutoff, cached in cutoff_cache.items()
                },
                "cell_count": len(cell_masses),
                "positive_cells": sorted(cell_masses),
                "positive_grid_cells": sorted(set(cell_masses) & GRID_CELLS),
                "structural_zero_grid_cells": original_zero_mass_cells,
                "positive_grid_cell_count": len(set(cell_masses) & GRID_CELLS),
                "cell_mass_receipt": cell_masses,
                "unknown_cell_n": cell_masses.get("unknown", {}).get("original_n", 0),
                "prompt_characters_total": sum(len(v["messages"][0]["content"]) for v in prompts.values()),
                "prompt_characters_max": max(len(v["messages"][0]["content"]) for v in prompts.values()),
                "prompt_utf8_bytes_max": max(len(v["messages"][0]["content"].encode()) for v in prompts.values()),
                "tone_persistence_dependency": False,
                "alarm_one_with_vs_without_tone_same_selection": tone_audit,
            })
            dump(staged / "checkpoint.json", {
                "schema": "sce_full_a_personal_inputs_checkpoint_v1",
                "status": "building",
                "completed_months": [row["month"] for row in month_summaries],
                "rows_by_month": rows_by_month,
                "excluded_total_so_far": len(exclusions),
                "builder_source_sha256_by_month": {row["month"]: builder_sha256 for row in month_summaries},
                "input_files_sha256_so_far": source_hashes,
                "new_api_calls": 0,
            })
            print(f"{month}: {len(prompts)}/512 prompts; {len(excluded_this_month)} date exclusions; "
                  f"{len(cutoff_cache)} cutoff caches", flush=True)

        if sum(rows_by_month.values()) != EXPECTED_RETAINED or sum(r["original_n"] for r in month_summaries) != EXPECTED_ORIGINAL:
            raise ValueError(
                f"Full-A roster total mismatch: original={sum(r['original_n'] for r in month_summaries)}, "
                f"eligible={sum(rows_by_month.values())}, excluded={len(exclusions)}; "
                "expected 41984/41970/14"
            )
        if len(exclusions) != EXPECTED_EXCLUDED:
            by_reason = dict(Counter(row["reason"] for row in exclusions))
            raise ValueError(f"Expected exactly 14 exclusions; observed {len(exclusions)} ({by_reason})")
        if any(row["reason"] != "cross_month_completion_date" for row in exclusions):
            raise ValueError("Only cross-month completion dates are authorized exclusions")

        # Measure the serialized messages as the existing assembly did; this is
        # a rough offline estimate, not an API quote or spend authorization.
        estimated_input_cost = total_estimated_input_tokens * INPUT_PRICE_PER_MTOK / 1_000_000
        estimated_output_cost = sum(rows_by_month.values()) * ESTIMATED_OUTPUT_TOKENS * OUTPUT_PRICE_PER_MTOK / 1_000_000
        summary = {
            "status": "ready",
            "artifact": "sce_full_a_personal_inputs_20261025_v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "months": months,
            "original_total": EXPECTED_ORIGINAL,
            "eligible_total": EXPECTED_RETAINED,
            "excluded_total": len(exclusions),
            "rows_by_month": rows_by_month,
            "new_api_calls": 0,
            "new_model_answers": 0,
            "current_target_answers_read": False,
            "source_answer_columns_projected": ["userid", "date", "survey_date"],
            "tier_levels": list(TIER_LEVELS),
            "tier_assignment_frame": "all 512 IDs per month before date exclusions",
            "common_news_n": COMMON_NEWS_N,
            "common_pool_rule": "select three A1 stories when available; if fewer than three, retain all available A1 stories and fill from the same cutoff-eligible keep pool by the existing salience score",
            "selection": {"alarming_boost": 1.0, "cpi_boost": 1.5, "fox_share": 0.0,
                          "tone_or_persistence_used": False,
                          "alarm_one_invariance_audit": "one person per news tier at earliest and latest cutoff for each month; exact selected-ID comparison",
                          "alarm_one_invariance_checked_person_months": sum(
                              row["alarm_one_with_vs_without_tone_same_selection"]["checked_person_months"]
                              for row in month_summaries)},
            "builder_source_sha256_by_month": {month: builder_sha256 for month in months},
            "cutoff_rule": "day before survey completion date at 23:59:59 America/New_York",
            "news_window_rule": "previous calendar month day 1 00:00 America/New_York through personal cutoff",
            "food_policy_confidence_rule": "latest pinned publication available by personal cutoff",
            "personal_cutoff_cache": "month x distinct personal cutoff; raw monthly archive parsed once per month",
            "cell_mass_basis": "preserve each originally positive 54-grid cell and unknown-cell poststratified mass from the frozen 512-row roster; record structural zero grid cells separately",
            "first_preflight_audit": {
                "result": "failed_closed_no_ready_output",
                "finding": "201901 frozen 512-row weights contain 52 positive grid cells plus one positive unknown cell; two of the 54 theoretical grid cells are structural zeros",
                "corrective_assertion": "calibrate all originally positive cells, report original structural zero grid cells, and fail if date exclusions empty any originally positive cell",
            },
            "preflight_failures_before_ready": [
                {
                    "status": "failed_closed_no_ready_output",
                    "finding": "Initial weight assertion treated structural-zero theoretical grid cells as occupied; 201901 had 52 positive grid cells plus unknown and 2 structural-zero grid cells.",
                    "corrective_rule": "calibrate only originally positive cells and report structural zeros separately",
                    "api_calls": 0,
                },
                {
                    "status": "failed_closed_no_ready_output",
                    "finding": "202403 cutoffs 2024-02-29 through 2024-03-03 had 108-120 eligible keep-news rows but only 2 A1 rows; 110 person-months were blocked by the old A1-only common selection helper.",
                    "corrective_rule": "retain all available A1 stories and fill common-news slots from the same cutoff-eligible pool by the existing salience score; no synthetic rows",
                    "api_calls": 0,
                },
            ],
            "prompt_characters_total": total_prompt_chars,
            "prompt_characters_max": max_prompt_chars,
            "prompt_utf8_bytes_total": total_prompt_bytes,
            "prompt_utf8_bytes_max": max_prompt_bytes,
            "estimated_input_tokens_char_div_4": total_estimated_input_tokens,
            "estimated_output_tokens_assumed_per_prompt": ESTIMATED_OUTPUT_TOKENS,
            "price_input_per_million_tokens_usd": INPUT_PRICE_PER_MTOK,
            "price_output_per_million_tokens_usd": OUTPUT_PRICE_PER_MTOK,
            "estimated_input_cost_usd": estimated_input_cost,
            "estimated_output_cost_usd": estimated_output_cost,
            "estimated_total_cost_usd": estimated_input_cost + estimated_output_cost,
            "cost_note": "rough text-length estimate from the existing full-A assembly price basis; not authorization or quote",
            "months_summary": month_summaries,
            "prompt_sha256_unique": len(all_prompt_hashes),
            "prompt_duplicate_positions": sum(n - 1 for n in all_prompt_hashes.values() if n > 1),
            "limits": [
                "A historical person-specific information-cutoff package, not strict B.",
                "No LLM/API calls, no current target answers and no Q9 fitting.",
                "T0 uses no tone or persistence labels; at alarm boost 1 adding tone does not alter selection.",
                "14 cross-month completion dates are excluded with no replacement; remaining weights restore each original 54-cell mass.",
                "News archive text vintage remains unverified; publication-date filtering is enforced.",
            ],
            "input_files_sha256": source_hashes,
        }
        dump(staged / "exclusions.json", {"rows": exclusions, "count": len(exclusions)})
        dump(staged / "summary.json", summary)
        dump(staged / "checkpoint.json", {
            "schema": "sce_full_a_personal_inputs_checkpoint_v1",
            "status": "ready_to_publish",
            "completed_months": months,
            "rows_by_month": rows_by_month,
            "excluded_total": len(exclusions),
            "builder_source_sha256_by_month": {month: builder_sha256 for month in months},
            "input_files_sha256": source_hashes,
            "new_api_calls": 0,
        })
        file_hashes = {}
        for path in sorted(staged.rglob("*.json")):
            if path.name == "manifest.json":
                continue
            file_hashes[str(path.relative_to(staged))] = sha(path)
        manifest = {
            "schema": "sce_full_a_personal_inputs_v1",
            "status": "offline_inputs_ready_no_api",
            "months": months,
            "files_sha256": file_hashes,
            "input_files_sha256": source_hashes,
            "current_target_answers_read": False,
            "new_api_calls": 0,
            "artifact_contract": {
                "monthly_prompts": "<YYYYMM>/prompts.json:{month,rows:{aid:{messages,prompt_sha256}}}",
                "monthly_contexts": "<YYYYMM>/contexts_private.json:{aid:context}",
                "monthly_weights": "<YYYYMM>/weights_private.json:{aid:all original fields plus calibrated fields}",
                "monthly_roster": "<YYYYMM>/roster_private.json:{month,frame_n,eligible_n,excluded_n,rows:{aid:...eligible}}",
            },
        }
        dump(staged / "manifest.json", manifest)
        os.rename(staged, out)
        return summary
    except BaseException as exc:
        dump(staged / "failure.json", {
            "status": "failed_with_month_checkpoints_preserved",
            "current_month": current_month,
            "completed_months": [row["month"] for row in month_summaries],
            "completed_rows_by_month": rows_by_month,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "new_api_calls": 0,
        })
        dump(staged / "checkpoint.json", {
            "schema": "sce_full_a_personal_inputs_checkpoint_v1",
            "status": "failed_month_checkpoints_preserved",
            "current_month": current_month,
            "completed_months": [row["month"] for row in month_summaries],
            "rows_by_month": rows_by_month,
            "excluded_total_so_far": len(exclusions),
            "builder_source_sha256_by_month": {row["month"]: builder_sha256 for row in month_summaries},
            "input_files_sha256_so_far": source_hashes,
            "failure_type": type(exc).__name__,
            "failure": str(exc),
            "new_api_calls": 0,
        })
        print(f"Preserved completed months in {staged}", flush=True)
        raise


def _check_alarm_one_invariance_sample(month, cutoff_cache, by_cutoff_aids, tiers, baskets, people):
    ordered_cutoffs = sorted(by_cutoff_aids, key=parsed)
    sampled_cutoffs = ordered_cutoffs[:1] if len(ordered_cutoffs) == 1 else [ordered_cutoffs[0], ordered_cutoffs[-1]]
    checked = 0
    sampled_ids = []
    for cutoff in sampled_cutoffs:
        base_pool = cutoff_cache[cutoff]["pool"]
        common_ids = {row["article_id"] for row in cutoff_cache[cutoff]["common"]}
        tone_pool = deepcopy(base_pool)
        for row in tone_pool:
            row["semantic_label"]["tone"] = "alarming"
        aids = by_cutoff_aids[cutoff]
        for tier in TIER_LEVELS:
            aid = next((candidate for candidate in sorted(aids) if tiers[candidate] == tier), None)
            if aid is None:
                continue
            interest = interests_for_profile(people[aid]["attributes"], baskets[aid]["spending_shares"])
            without_tone = draw_personal(
                [row for row in base_pool if row["article_id"] not in common_ids], [],
                tiers[aid] - COMMON_NEWS_N, f"{NEWS_SEED}|{month}|{aid}", interest,
                alarming_boost=1.0, cpi_boost=1.5, fox_share=0.0)
            with_tone = draw_personal(
                [row for row in tone_pool if row["article_id"] not in common_ids], [],
                tiers[aid] - COMMON_NEWS_N, f"{NEWS_SEED}|{month}|{aid}", interest,
                alarming_boost=1.0, cpi_boost=1.5, fox_share=0.0)
            before = [row["article_id"] for row in without_tone]
            after = [row["article_id"] for row in with_tone]
            if before != after:
                raise ValueError(f"{month}/{aid}: alarm=1 selection changed when tone was added")
            sampled_ids.append(aid)
            checked += 1
    return {
        "status": "passed",
        "sampled_cutoffs": sampled_cutoffs,
        "sampled_agent_ids": sampled_ids,
        "tiers": sorted({tiers[aid] for aid in sampled_ids}),
        "checked_person_months": checked,
        "method": "one representative per tier at earliest/latest cutoff; add-alarming-tone counterfactual, alarm_boost=1",
    }
