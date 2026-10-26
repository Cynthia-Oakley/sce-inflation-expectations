"""Outcome-free B news update; the completed B population/prior stay frozen.

This is input preparation only. It never loads responses, national target values,
credentials or a sender. A separate execution package is intentionally deferred
until the running full-A candidate has been evaluated.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha
from .fullperiod_materialization import news_pool_for_prompts
from .media_mechanism_trial import is_sce_report, parse_time, select_salient_common, text_of
from .media_mechanism_v3 import draw_personal, four_tier_levels
from .recent_b_prompts import LEAK as B_SCE_PATTERN
from .state_continuity_core import check as check_core
from ..news_exposure import NEWS_KEYS, interests_for_profile
from ..news_exposure_demo import exact_deduplicate, news_tags, render_news_input
from ..news_label_compat import normalize_label
from ..news_selection_trial import RecallRules, RULE_FILE
from ..prior_belief_experiment import message_hash
from ..state_continuity_runtime import STATE_TOKEN, TIMING_TOKEN, render_messages

PARENT_RUN = ROOT / "outputs/sce_recent_b_overnight_20261025_v3"
DEFAULT_OUT = ROOT / "outputs/sce_recent_b_news_refresh_20261025_v3"
MONTHS = ("202511", "202512", *(f"2026{m:02}" for m in range(1, 10)))
NEWS = "General news you encountered:\n"
POLICY = "Public policy news brief ("
SEED = 20261025


def _safe_source(name, expected, sources):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or sha(path) != expected:
        raise ValueError("Frozen B source changed or outside project: " + name)
    sources[str(path.relative_to(ROOT))] = expected
    return path


def _topic_label(raw):
    label = normalize_label(raw)
    return {key: deepcopy(label[key]) for key in ("article_id", "decision", "topics", "scope")}


def _load_labels(summary, sources):
    # Use exactly the old assembly's declared ordered union, not a live glob
    # that could silently introduce later classification versions.
    labels = {}
    for name, digest in summary["source_sha256"].items():
        if not name.endswith("labels.jsonl"):
            continue
        path = _safe_source(name, digest, sources)
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                label = _topic_label(row.get("label", row))
                labels[label["article_id"]] = label
    if not labels:
        raise ValueError("The frozen B base-label union is empty")
    return labels


def _latest_cpi_release_day(environment, cutoff):
    releases = [parse_time(row["published_at"])
                for row in environment["provider_args"]["signals_by_step"]["0"]
                if row["signal_id"].startswith("bls_cpi_u_all_items_yoy_nsa_")
                and parse_time(row["published_at"]) <= parse_time(cutoff)]
    if not releases:
        raise ValueError("No eligible actual CPI release before the B cutoff")
    return max(releases).date().isoformat()


def _news_pools(raw, labels, cutoff, release_day):
    pool, excluded = [], 0
    for row in raw:
        if parse_time(row["pub_date"]) > parse_time(cutoff):
            raise ValueError("Future news entered the cutoff-specific source pool")
        if is_sce_report(row) or B_SCE_PATTERN.search(text_of(row)):
            excluded += 1
            continue
        aid = row["article_id"]
        if row["new_hits"] and aid not in labels:
            raise ValueError("Missing base classification: " + aid)
        item = {key: row[key] for key in NEWS_KEYS - {"routing_tags", "semantic_label"}}
        item.update(routing_tags=news_tags(row), semantic_label=labels.get(aid))
        # A1 candidates without recalled economic keywords were already valid
        # general news in old B; neutral local metadata is used for routing only.
        if item["semantic_label"] is None:
            item["semantic_label"] = {"article_id": aid, "decision": "background_only",
                                      "topics": [], "scope": "unclear"}
        pool.append(item)
    pool = exact_deduplicate(pool)
    common = select_salient_common(pool, release_day)
    common_ids = {row["article_id"] for row in common}
    personal = [row for row in pool if row["placement"] != "a1"
                and row["semantic_label"]["decision"] == "keep"
                and row["article_id"] not in common_ids]
    if len(personal) < 29:
        raise ValueError("The 32-article tier needs 29 distinct eligible personal articles")
    return common, personal, {"raw_n": len(raw), "common_a1_n": sum(r["placement"] == "a1" for r in pool),
                              "personal_pool_n": len(personal), "sce_articles_excluded": excluded}


def _validate_plan(plan, month):
    if plan["month"] != month or month not in MONTHS:
        raise ValueError("Unregistered B target month")
    cutoff = parse_time(plan["as_of"])
    if cutoff.strftime("%Y%m") != month:
        raise ValueError("B cutoff must stay in its registered target month")
    anchor = plan["last_public_national_anchor"]
    if datetime.fromisoformat(anchor["published_date"]).date() > cutoff.date():
        raise ValueError("National prior anchor was not public by the cutoff")
    if anchor["reference_period"].replace("-", "") >= month:
        raise ValueError("Target/future national value cannot initialize B")


def replace_news_template(template, old_context, new_context, state, old_preview, month):
    """Alter news only; re-render *both* publication lists from the new context."""
    if render_messages(template, state, month, old_context) != old_preview:
        raise ValueError("Frozen B preview does not reproduce from its state/template")
    if old_context["as_of"] != new_context["as_of"]:
        raise ValueError("A news refresh cannot move the B forecast cutoff")
    for key in ("policy_published_at", "food_published_at"):
        if old_context[key] != new_context[key]:
            raise ValueError("Non-news environment changed: " + key)
    text = template[0]["content"]
    if any(text.count(marker) != 1 for marker in (NEWS, POLICY, STATE_TOKEN, TIMING_TOKEN)):
        raise ValueError("Unique frozen template boundaries required")
    start, end = text.index(NEWS), text.index(POLICY)
    old_news = render_news_input(old_context["common_news"], old_context["personal_news"])
    region = text[start:end]
    if not region.startswith(old_news) or region[len(old_news):].strip():
        raise ValueError("Frozen B news region does not reproduce")
    replacement = render_news_input(new_context["common_news"], new_context["personal_news"])
    updated = deepcopy(template)
    updated[0]["content"] = text[:start] + replacement + region[len(old_news):] + text[end:]
    rendered = render_messages(updated, state, month, new_context)
    return updated, rendered


def prepare(out=DEFAULT_OUT):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / "outputs"):
        raise ValueError("Fresh output under outputs/ required")
    sources = {}
    # The original B manifest cannot pin selectors that did not yet belong to
    # that experiment. Bind the new treatment's actual implementation as well.
    for path in (Path(__file__), ROOT / "scripts/prepare_sce_recent_b_news_refresh.py",
                 Path(__file__).with_name("media_mechanism_trial.py"),
                 Path(__file__).with_name("media_mechanism_v3.py"),
                 Path(__file__).with_name("fullperiod_materialization.py"),
                 ROOT / "studies/sce_inflation_expectations/news_exposure_demo.py",
                 ROOT / "studies/sce_inflation_expectations/news_exposure.py",
                 ROOT / "studies/sce_inflation_expectations/news_label_compat.py"):
        sources[str(path.relative_to(ROOT))] = sha(path)
    parent = PARENT_RUN / "package"
    manifest = read_json(parent / "manifest.json")
    protocol = read_json(parent / "protocol.json")
    if sha(parent / "protocol.json") != manifest["protocol_sha256"]:
        raise ValueError("Old B protocol changed")
    if tuple(protocol["months"]) != MONTHS or protocol["planned_calls"] != 5632:
        raise ValueError("The completed independent B11 scope is required")
    # Verify only declared input sources; no generated answers/evaluation files.
    for name, digest in manifest["source_sha256"].items():
        _safe_source(name, digest, sources)
    sources[str((parent / "manifest.json").relative_to(ROOT))] = sha(parent / "manifest.json")
    sources[str((parent / "protocol.json").relative_to(ROOT))] = sha(parent / "protocol.json")
    base = ROOT / protocol["input_templates"]
    old_summary = read_json(base / "summary.json")
    _safe_source(str((base / "summary.json").relative_to(ROOT)),
                 manifest["source_sha256"][str((base / "summary.json").relative_to(ROOT))], sources)
    plans_file = ROOT / protocol["population_preflight"] / "monthly_input_plan.json"
    plans = {row["month"]: row for row in read_json(plans_file)}
    selected_file = ROOT / protocol["population_preflight"] / "selected_proxy_population_private.json"
    selected = read_json(selected_file)
    labels = _load_labels(old_summary, sources)
    sources[str(RULE_FILE.relative_to(ROOT))] = sha(RULE_FILE)
    rules = RecallRules(read_json(RULE_FILE))
    out.mkdir(parents=True)
    prompts = out / "prompts"; prompts.mkdir()
    inputs = out / "inputs"; inputs.mkdir()
    coverage, nodes, sizes = [], [], []
    for month in MONTHS:
        plan = plans[month]; _validate_plan(plan, month)
        previous = {name: read_json(base / month / f"{name}.json") for name in (
            "population", "environment", "templates_private", "initial_states_private",
            "timing_context_private", "initial_previews_private", "baskets_private")}
        ids = sorted(previous["initial_states_private"])
        profiles = {row["agent_id"]: row["attributes"] for row in previous["population"]["personas"]}
        if len(ids) != 512 or set(ids) != set(profiles) or set(ids) != {r["persona"]["agent_id"] for r in selected[month]}:
            raise ValueError("Frozen 512-person B roster differs")
        target = month[:4] + "-" + month[4:]
        raw, _, news_sources = news_pool_for_prompts(ROOT, target, plan["as_of"], rules)
        for name, digest in news_sources.items():
            _safe_source(name, digest, sources)
        release_day = _latest_cpi_release_day(previous["environment"], plan["as_of"])
        common, pool, pool_audit = _news_pools(raw, labels, plan["as_of"], release_day)
        tiers = four_tier_levels(ids, int(month), SEED)
        templates, contexts, previews = {}, {}, {}
        unchanged_count = 0
        for aid in ids:
            state = previous["initial_states_private"][aid]
            context = previous["timing_context_private"][aid]
            if context["as_of"] != plan["as_of"] or state["comparison_day_source"] != "synthetic_prior_reference_month_end":
                raise ValueError("B must retain the common cutoff and synthetic reference day")
            personal = draw_personal(pool, [], tiers[aid] - 3, f"{SEED}|{month}|{aid}",
                interests_for_profile(profiles[aid], previous["baskets_private"][aid]["spending_shares"]),
                alarming_boost=1.0, cpi_boost=1.5, fox_share=0.0)
            new_context = {**context, "common_news": common, "personal_news": personal}
            old_preview = previous["initial_previews_private"][aid]
            if message_hash(old_preview["messages"]) != old_preview["prompt_sha256"]:
                raise ValueError("Old B prompt hash mismatch")
            template, messages = replace_news_template(previous["templates_private"][aid], context,
                new_context, state, old_preview["messages"], month)
            templates[aid], contexts[aid] = template, new_context
            previews[aid] = {"messages": messages, "prompt_sha256": message_hash(messages)}
            unchanged_count += previews[aid]["prompt_sha256"] == old_preview["prompt_sha256"]
            sizes.append((len(json.dumps(messages, ensure_ascii=False)),
                          len(json.dumps(messages, ensure_ascii=False).encode())))
            nodes.append({"month": month, "agent_id": aid, "repeat": 1, "arm": "recent_b",
                          "dependency": None, "source_kind": "synthetic_public_prior",
                          "logical_reuse_key": f"{month}|{aid}|1|recent_b"})
        dest = prompts / month; dest.mkdir()
        for name in ("population", "environment", "initial_states_private", "baskets_private"):
            (dest / f"{name}.json").write_bytes((base / month / f"{name}.json").read_bytes())
        for name, value in (("templates_private", templates), ("timing_context_private", contexts),
                            ("initial_previews_private", previews)):
            dump(dest / f"{name}.json", value)
        unchanged = {name: sha(dest / f"{name}.json") == sha(base / month / f"{name}.json")
                     for name in ("population", "environment", "initial_states_private", "baskets_private")}
        coverage.append({"month": month, "n": len(ids), "as_of": plan["as_of"],
            "population_source_wave": plan["old_population_reference_period"],
            "news_quantity": dict(Counter(tiers.values())), "common_routing_cpi_release_day": release_day,
            "unchanged_input_bytes": unchanged,
            "identical_old_prompt_n": unchanged_count, **pool_audit})
        print(f"{month}: 512 B news views prepared; P/prior/price/policy unchanged", flush=True)
    dump(inputs / "state_dependencies_private.json", nodes)
    # Preserve role assignments as a pinned provenance artifact, never resample.
    (prompts / "role_assignments_private.json").write_bytes((base / "role_assignments_private.json").read_bytes())
    summary = {"schema": "sce_recent_b_news_refresh/v1", "status": "offline_candidate_not_authorized",
        "coverage": coverage, "planned_unique_requests": len(nodes), "logical_positions": len(nodes),
        "runtime_character_cap": max(x[0] for x in sizes) + 512,
        "runtime_utf8_byte_cap": max(x[1] for x in sizes) + 1024,
        "estimated_main_cost_usd": (sum(x[0] for x in sizes) / 4 * .259 + len(nodes) * 300 * .8) / 1e6,
        "estimated_output_tokens_per_request": 300,
        "source_sha256": sources, "research_line": protocol["research_line"], "strict_B_eligible": False,
        "population_preflight": protocol["population_preflight"], "prior_source": protocol["prior_source"],
        "micro_availability_basis": protocol["micro_availability_basis"],
        "parent_assembly": str(base.parent.relative_to(ROOT)), "new_api_calls": 0,
        "truth_opened": False, "authorization_written": False, "execution_package_created": False,
        "news_selection": {"tier_levels": [4, 8, 16, 32], "tier_assignment_frame": "same 512 selected proxies per month",
            "allocation_seed": SEED, "common_news": "three salient A1 stories", "alarming_boost": 1.0,
            "cpi_boost": 1.5, "fox_share": 0.0, "matching": "half uniform, half interest/relevance weighted"},
        "combination_weight_status": "pending_full_A_early_period_fit; never refit on B targets",
        "limits": ["Same historical source-wave availability assumption as completed B; exact file vintages unverified.",
            "No actual recent interview dates: retain each month's global as_of; no A personal cutoff is reused.",
            "No recent micro targets: national accuracy only; micro dispersion is descriptive.",
            "T0-style news candidate only; do not label the B design as A personal-date T0."]}
    dump(prompts / "summary.json", summary)
    core = check_core(inputs, prompts, out / "core_engineering")
    summary["official_core"] = core
    dump(out / "summary.json", summary)
    generated = {str(p.relative_to(out)): sha(p) for p in out.rglob("*.json")}
    dump(out / "manifest.json", {"schema": "sce_recent_b_news_refresh_manifest/v1", "files_sha256": generated,
        "source_sha256": sources, "builder_sha256": sha(Path(__file__)),
        "new_api_calls": 0, "truth_opened": False, "authorization_written": False})
    return summary
