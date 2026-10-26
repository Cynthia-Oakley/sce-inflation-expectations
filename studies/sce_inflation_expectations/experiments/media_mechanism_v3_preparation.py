"""Offline input loading and frozen-package assembly for media mechanism V3."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha, verify
from .fullperiod_materialization import news_pool_for_prompts
from .media_mechanism_trial import (
    MATERIALIZED, ASSEMBLY, change_rendered_news, latest_cpi_release_day, roster, select_salient_common)
from .media_mechanism_v3 import (
    ARM_CONFIG, ARMS, MONTHS, draw_personal, four_tier_levels, merge_supplemental_labels)
from ..news_exposure import NEWS_KEYS, interests_for_profile
from ..news_exposure_demo import exact_deduplicate, news_tags
from ..news_label_compat import normalize_label
from ..news_mechanism_labels import PERSISTENCE, TONES
from ..news_selection_trial import RecallRules, RULE_FILE
from ..prior_belief_experiment import message_hash


def load_supplemental_run(directory):
    directory = Path(directory)
    state = read_json(directory / "state.json")
    if state.get("status") != "completed":
        raise ValueError("supplemental label run must be complete")
    labels = {}
    for line in (directory / "labels.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        label = json.loads(line)["label"]
        article_id = label["article_id"]
        if article_id in labels:
            raise ValueError("duplicate supplemental label")
        if set(label) != {"article_id", "tone", "persistence"}:
            raise ValueError("unexpected supplemental fields")
        if label["tone"] not in TONES or label["persistence"] not in PERSISTENCE:
            raise ValueError("invalid supplemental enum")
        labels[article_id] = {"tone": label["tone"], "persistence": label["persistence"]}
    if len(labels) != state.get("articles_valid"):
        raise ValueError("supplemental label count differs from run receipt")
    return labels


def apply_label_overrides(labels, overrides):
    reviewed = {article_id: dict(label) for article_id, label in labels.items()}
    for article_id, changes in overrides.items():
        if article_id not in reviewed:
            raise ValueError("override references unknown article")
        if not changes or set(changes) - {"tone", "persistence"}:
            raise ValueError("unexpected override fields")
        for field, value in changes.items():
            if value not in (TONES if field == "tone" else PERSISTENCE):
                raise ValueError("invalid override enum")
            reviewed[article_id][field] = value
    return reviewed


def load_nyt_pool(root, month, supplemental):
    root = Path(root)
    target = f"{month // 100}-{month % 100:02}"
    environment = read_json(root / ASSEMBLY / str(month) / "environment.json")
    cutoff = environment["provider_args"]["targets"][0]["as_of"]
    raw, _, _ = news_pool_for_prompts(root, target, cutoff, RecallRules(read_json(RULE_FILE)))
    label_index = read_json(root / MATERIALIZED / str(month) / "news_label_index.json")
    labels = {row["article_id"]: normalize_label(row["label"]) for row in label_index["pool"] if row["label"]}
    pool = []
    for original in raw:
        label = labels.get(original["article_id"])
        if not label or label["decision"] != "keep":
            continue
        row = {key: original[key] for key in NEWS_KEYS - {"routing_tags", "semantic_label"}}
        row["routing_tags"] = news_tags(original)
        row["semantic_label"] = label
        pool.append(row)
    return exact_deduplicate(merge_supplemental_labels(pool, supplemental))


def build_month_prompts(month, agent_ids, nyt, fox, base, release_day):
    as_of = base["environment"]["provider_args"]["targets"][0]["as_of"]
    common = select_salient_common(nyt, release_day)
    common_ids = {row["article_id"] for row in common}
    nyt = [row for row in nyt if row["article_id"] not in common_ids]
    profiles = {person["agent_id"]: person["attributes"] for person in base["population"]["personas"]}
    tiers = four_tier_levels(agent_ids, month)
    prompts, contexts = {}, {}
    receipt = {
        "month": month, "as_of": as_of, "nyt_pool": len(nyt), "fox_pool": len(fox),
        "common_news": [{"article_id": row["article_id"], "headline": row["headline"], "pub_date": row["pub_date"]} for row in common],
        "tier_quotas": dict(Counter(tiers.values())), "arms": {},
    }
    for arm in ARMS:
        config = ARM_CONFIG[arm]
        arm_prompts, arm_contexts = {}, {}
        exposure = Counter()
        for agent_id in agent_ids:
            count = tiers[agent_id] if config["four_tiers"] else base["news_quantity_frame_private"][agent_id]
            interests = interests_for_profile(profiles[agent_id], base["baskets_private"][agent_id]["spending_shares"])
            personal = draw_personal(
                nyt, fox, count - 3, f"20261025|{month}|{agent_id}", interests,
                alarming_boost=config["alarming_boost"], cpi_boost=config["cpi_boost"], fox_share=config["fox_share"])
            messages = change_rendered_news(
                base["initial_previews_private"][agent_id]["messages"],
                base["timing_context_private"][agent_id]["common_news"],
                base["timing_context_private"][agent_id]["personal_news"], common, personal,
                base["initial_states_private"][agent_id]["comparison_reference_day"], as_of)
            arm_prompts[agent_id] = {"messages": messages, "prompt_sha256": message_hash(messages)}
            sources = [row["semantic_label"].get("source", "NYT") for row in personal]
            arm_contexts[agent_id] = {
                "article_ids": [row["article_id"] for row in personal], "sources": sources,
                "tone": [row["semantic_label"]["tone"] for row in personal],
                "persistence": [row["semantic_label"]["persistence"] for row in personal],
                "news_count": count, "alarming_boost": config["alarming_boost"],
                "cpi_boost": config["cpi_boost"], "fox_share": config["fox_share"],
            }
            exposure.update(sources)
        prompts[arm] = arm_prompts
        contexts[arm] = arm_contexts
        receipt["arms"][arm] = {"source_exposures": dict(exposure)}
    return prompts, contexts, receipt


def prepare(out, fox_by_month, root=ROOT, labels_dir=None, review_path=None, fox_labels_dir=None, fox_candidate_paths=None, fox_review_path=None, n=96):
    root = Path(root)
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("fresh output under outputs required")
    labels_dir = Path(labels_dir or root / "outputs/sce_news_mechanism_labels_20261025_v1")
    review_path = Path(review_path or root / "outputs/sce_news_mechanism_label_audit_20261025_v1/review.json")
    fox_labels_dir = Path(fox_labels_dir or root / "outputs/sce_fox_mechanism_labels_20261025_v1")
    review = read_json(review_path)
    supplemental = apply_label_overrides(load_supplemental_run(labels_dir), review["overrides"])
    if set(fox_by_month) != set(MONTHS):
        raise ValueError("Fox pools must cover exactly the seven registered months")
    sources = {}
    for path in (labels_dir / "state.json", labels_dir / "labels.jsonl", review_path, Path(__file__),
                 fox_labels_dir / "state.json", fox_labels_dir / "labels.jsonl",
                 root / "studies/sce_inflation_expectations/experiments/media_mechanism_v3.py"):
        sources[str(path.resolve().relative_to(root))] = sha(path)
    if fox_review_path is not None:
        sources[str(Path(fox_review_path).resolve().relative_to(root))] = sha(fox_review_path)
    for month in MONTHS:
        relative = f"existing_months/{month}.json" if month in (202106, 202206) else f"{month}/candidates.json"
        path = (Path(fox_candidate_paths[month]) if fox_candidate_paths is not None
                else root / "outputs/sce_fox_news_20261025_v1" / relative)
        sources[str(path.resolve().relative_to(root))] = sha(path)
        english = root / "outputs/sce_fox_news_20261025_v1/existing_english" / f"{month}.json"
        if month in (202106, 202206) and english.exists():
            sources[str(english.resolve().relative_to(root))] = sha(english)
    for relative in ("external_candidates.json", "external_may_2021.json", "external_may_2022.json"): 
        path = root / "outputs/sce_media_mechanism_20261024_v1" / relative
        sources[str(path.resolve().relative_to(root))] = sha(path)
    out.mkdir(parents=True)
    jobs, coverage = [], []
    reserve = estimate = 0.0
    maximum = 0
    for month in MONTHS:
        base_dir = root / ASSEMBLY / str(month)
        names = ("initial_previews_private", "timing_context_private", "initial_states_private",
                 "news_quantity_frame_private", "baskets_private", "population", "environment")
        base = {name: read_json(base_dir / f"{name}.json") for name in names}
        for name in names:
            path = base_dir / f"{name}.json"
            sources[str(path.resolve().relative_to(root))] = sha(path)
        simulation_path = (root / "outputs/sce_monthly_fine_full_assembly_20261023_v3/core_engineering" /
                           f"{month}-monthly_reconstruction-r1" / str(month) / "simulation.json")
        sources[str(simulation_path.resolve().relative_to(root))] = sha(simulation_path)
        for name in ("news_label_index.json", "environment.json"):
            path = root / MATERIALIZED / str(month) / name
            sources[str(path.resolve().relative_to(root))] = sha(path)
        previous = f"{month // 100 - (1 if month % 100 == 1 else 0)}-{12 if month % 100 == 1 else month % 100 - 1:02}"
        for window_month in (previous, f"{month // 100}-{month % 100:02}"):
            path = root / "data/raw/nyt_archive" / f"{window_month}.json"
            sources[str(path.resolve().relative_to(root))] = sha(path)
        nyt = load_nyt_pool(root, month, supplemental)
        fox = fox_by_month[month]
        ids = roster(list(base["initial_previews_private"]), n)
        prompts, contexts, receipt = build_month_prompts(month, ids, nyt, fox, base, latest_cpi_release_day(root, month))
        common_review = [row for row in review.get("common_rows", []) if row["month"] == month]
        if common_review:
            expected = {row["article_id"]: row for row in common_review}
            actual = {row["article_id"]: row for row in receipt["common_news"]}
            if set(actual) != set(expected):
                raise ValueError("common-news review does not cover the selected articles")
            by_id = {row["article_id"]: row for row in nyt}
            for article_id in actual:
                label = by_id[article_id]["semantic_label"]
                if (expected[article_id]["review_tone"] != label["tone"]
                        or expected[article_id]["review_persistence"] != label["persistence"]):
                    raise ValueError("common-news review and reviewed labels differ")
        population = dict(base["population"])
        population["personas"] = [person for person in base["population"]["personas"] if person["agent_id"] in set(ids)]
        if len(population["personas"]) != n:
            raise ValueError("roster extraction failed")
        dest = out / str(month)
        dest.mkdir()
        dump(dest / "population.json", population)
        dump(dest / "environment.json", base["environment"])
        dump(dest / "simulation.json", read_json(simulation_path))
        dump(dest / "contexts_private.json", contexts)
        for arm in ARMS:
            rows = {"month": month, "arm": arm, "rows": prompts[arm]}
            dump(dest / f"prompts_{arm}.json", rows)
            sizes = [len(json.dumps(row["messages"], ensure_ascii=False)) for row in prompts[arm].values()]
            byte_sizes = [len(json.dumps(row["messages"], ensure_ascii=False).encode()) for row in prompts[arm].values()]
            maximum = max(maximum, *sizes)
            bound = sum(((size + 1024) * 0.259 + 1024 * 0.8) / 1e6 for size in byte_sizes)
            rough = sum((size / 4 * 0.259 + 300 * 0.8) / 1e6 for size in byte_sizes)
            for repeat in (1, 2):
                cap = math.ceil(bound * 1e6) / 1e6
                reserve += cap
                estimate += rough
                jobs.append({"month": month, "arm": arm, "repeat": repeat, "seed": 41 + repeat,
                             "run_id": f"{out.name}-{month}-{arm}-r{repeat}", "cap_usd": cap})
        coverage.append(receipt)
        print(f"V3 news prompts {month}: {len(ids)} people × {len(ARMS)} arms", flush=True)
    cap = math.ceil(reserve * 1.25 * 1e6) / 1e6
    protocol = {
        "mechanism": "v32_news_mechanism_v3", "experiment_design": "media_mechanism_v3",
        "months": list(MONTHS), "arms": list(ARMS),
        "generation_repeats": [1, 2], "n_per_month": n, "planned_calls": len(MONTHS) * len(ARMS) * n * 2,
        "destination": "https://openrouter.ai/api/v1", "transport": "openrouter_locked",
        "model": "deepseek/deepseek-v3.2", "route": "siliconflow/fp8", "expected_provider": "SiliconFlow",
        "temperature": 0.5, "thinking": "disabled", "response_format": "json_object", "max_tokens": 1024,
        "retry_max": 0, "provider_fallback": False, "price_input_per_mtok": 0.259, "price_output_per_mtok": 0.8,
        "request_extra_body": {"provider": {"order": ["siliconflow/fp8"], "allow_fallbacks": False,
            "require_parameters": True, "max_price": {"prompt": 0.259, "completion": 0.8}},
            "reasoning": {"enabled": False}},
        "q9_postprocessing": "proportional_nonnegative_v1", "max_prompt_chars": maximum + 100,
        "max_workers": 4, "budget_cap_usd": cap, "registered_at_utc": datetime.now(timezone.utc).isoformat(),
        "primary_comparison": ["Q0", "Q1"], "additional_comparisons": [["R0", "Q0"], ["Q0", "Q2"], ["Q0", "Q3"]],
        "research_line": "A_conditional_exploratory_news_mechanism", "strict_B_eligible": False,
        "quantity_tiers": [4, 8, 16, 32], "common_news": 3, "personal_news": [1, 5, 13, 29],
        "alarm_boost": 2.0, "cpi_boost": 1.5, "fox_personal_share": 0.25,
        "a82_reference": "outputs/sce_monthly_main_six_repair_20261024_v1/evaluation/cases_private.json",
        "limits": ["All seven months occurred in A82; exploratory mechanism diagnosis, not independent temporal validation.",
                   "A82 has one generation; new arms have two and never invent an A82 second repeat.",
                   "Warning boost is an exposure-propagation proxy, not an estimated individual attention probability."],
    }
    dump(out / "protocol.json", protocol)
    dump(out / "coverage.json", coverage)
    for relative in (
        "studies/sce_inflation_expectations/experiments/frozen_batch.py",
        "studies/sce_inflation_expectations/experiments/staged_rosters.py",
        "studies/sce_inflation_expectations/experiments/model_comparison.py",
        "studies/sce_inflation_expectations/experiments/model_migration.py",
        "studies/sce_inflation_expectations/experiments/media_mechanism_trial.py",
        "studies/sce_inflation_expectations/experiments/media_mechanism_v3_execution.py",
        "studies/sce_inflation_expectations/experiments/fox_mechanism_preparation.py",
        "studies/sce_inflation_expectations/experiments/fullperiod_materialization.py",
        "studies/sce_inflation_expectations/news_mechanism_labels.py",
        "studies/sce_inflation_expectations/news_label_compat.py",
        "studies/sce_inflation_expectations/news_exposure.py",
        "studies/sce_inflation_expectations/news_exposure_demo.py",
        "studies/sce_inflation_expectations/information_update_runtime.py",
        "studies/sce_inflation_expectations/news_selection_trial.py",
        "studies/sce_inflation_expectations/frozen_prompt_runtime.py",
        "studies/sce_inflation_expectations/openrouter_frozen_runtime.py",
        "studies/sce_inflation_expectations/model.py",
        "scripts/export_study_runtime.py",
        "scripts/prepare_sce_media_mechanism_v3.py",
        "scripts/run_sce_media_mechanism_v3.py",
        "scripts/evaluate_sce_media_mechanism_v3.py",
        "scripts/audit_sce_media_mechanism_v3.py",
    ):
        sources[relative] = sha(root / relative)
    manifest = {
        "status": "prepared_requires_engine_checks_and_new_authorization", "jobs": jobs,
        "planned_calls": protocol["planned_calls"], "protocol_sha256": sha(out / "protocol.json"),
        "source_sha256": sources,
        "prepared_file_sha256": {str(path.relative_to(out)): sha(path) for path in out.rglob("*.json")},
        "estimated_cost_all_slots_usd": estimate, "conservative_reservation_all_slots_usd": reserve,
        "current_target_answers_read": False, "model_replies_read": False, "new_api_calls": 0,
    }
    dump(out / "manifest.json", manifest)
    dump(out / "authorization.json", {"approved": False, "protocol_sha256": manifest["protocol_sha256"],
        "cap_usd": cap, "planned_calls": protocol["planned_calls"], "destination": protocol["destination"],
        "user_confirmation": None})
    return manifest


def audit_preparation(package):
    package = Path(package).resolve()
    manifest, protocol = verify(package)
    coverage = read_json(package / "coverage.json")
    prompt_positions = 0
    for month in protocol["months"]:
        receipt = next(row for row in coverage if row["month"] == month)
        if receipt["tier_quotas"] != {"4": 24, "8": 24, "16": 24, "32": 24}:
            raise ValueError("four-tier quotas are not balanced")
        if len(receipt["common_news"]) != 3:
            raise ValueError("exactly three common stories required")
        fox = sum(count for source, count in receipt["arms"]["Q2"]["source_exposures"].items() if source.startswith("Fox"))
        if fox <= 0:
            raise ValueError("Q2 has no Fox exposure")
        for arm in protocol["arms"]:
            prompt_positions += len(read_json(package / str(month) / f"prompts_{arm}.json")["rows"])
    if prompt_positions * len(protocol["generation_repeats"]) != protocol["planned_calls"]:
        raise ValueError("prompt positions and physical call cap differ")
    wayback = {}
    for month in protocol["months"]:
        path = ROOT / "outputs/sce_fox_news_20261025_v1" / str(month) / "candidates.json"
        if path.exists():
            statuses = Counter(row.get("wayback", {}).get("status", "unverified") for row in read_json(path)["candidates"])
            wayback[str(month)] = dict(statuses)
    return {
        "status": "offline_acceptance_passed", "jobs": len(manifest["jobs"]),
        "prompt_positions": prompt_positions, "physical_call_cap": protocol["planned_calls"],
        "estimated_cost_usd": manifest["estimated_cost_all_slots_usd"],
        "conservative_reservation_usd": manifest["conservative_reservation_all_slots_usd"],
        "budget_cap_usd": protocol["budget_cap_usd"], "wayback_candidates": wayback,
        "wayback_note": "archive_verified means a 200 capture exists, not a line-by-line text diff; unverified stays disclosed.",
        "new_api_calls": 0,
    }
