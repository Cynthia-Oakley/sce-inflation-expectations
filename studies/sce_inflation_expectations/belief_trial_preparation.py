"""Offline preparation only: no API client, credentials, model calls or scoring.

Reuse saved v2-abstract messages. Add only a synthetic Gallup-compatible Fed
confidence statement; leave the original questionnaire and information intact.
Outputs containing personas or message text remain local and Git-ignored.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
import re
from uuid import uuid4

PROFILE_KEYS = {
    "age_group", "region", "state", "education_group", "household_income_band",
    "numeracy", "employment_status", "housing_tenure",
}
EDUCATION_MAP = {
    "college": "college_graduate", "some_college": "some_college",
    "high_school": "high_school_or_less",
}
CATEGORIES = (
    "great_deal", "fair_amount", "only_a_little", "almost_none",
    "dont_know_or_refused",
)
ARMS = ("no_added_confidence", "education_conditioned", "shuffled")
MARKER = "Question 1 (point estimate):"
INSERT_PREFIX = "Personal view about economic policy:\n"
CONFIDENCE_TEXT = {
    "great_deal": "You have a great deal of confidence in the Federal Reserve chair to do or recommend the right thing for the economy.",
    "fair_amount": "You have a fair amount of confidence in the Federal Reserve chair to do or recommend the right thing for the economy.",
    "only_a_little": "You have only a little confidence in the Federal Reserve chair to do or recommend the right thing for the economy.",
    "almost_none": "You have almost no confidence in the Federal Reserve chair to do or recommend the right thing for the economy.",
}
SOURCE_RUNS = {
    "202105": "sce-local-openai-20261005T092656Z-202105-8d2e3b2c",
    "202106": "sce-local-openai-20261005T092656Z-202106-e4f49f76",
}
PATTERNS = {
    "Fed_or_monetary_policy_mention": r"\b(?:fed|federal reserve|central bank|interest rates?)\b",
    "possible_temporary_or_easing_language": r"\b(?:temporary|transitory|patient|patience|eases|easing|restart|restarting|unchanged)\b",
    "possible_price_or_supply_pressure_language": r"\b(?:inflation|shortages?|soaring|jump|jumped|rising|rise|raises|stoking)\b",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def stable_rank(seed, namespace, identity):
    return hashlib.sha256(f"{seed}|{namespace}|{identity}".encode()).digest()


def validate_distribution(distribution):
    if tuple(distribution["categories"]) != CATEGORIES:
        raise ValueError("Unexpected confidence categories/order")
    if set(distribution["education_tables"]) != set(EDUCATION_MAP.values()):
        raise ValueError("Unexpected education source groups")
    for table in distribution["education_tables"].values():
        raw, probs = table["source_percent"], table["candidate_probabilities"]
        if len(raw) != 5 or len(probs) != 5 or sum(raw) <= 0:
            raise ValueError("Malformed source distribution")
        if any(not isinstance(x, (int, float)) or not isfinite(x) or not 0 <= x <= 100 for x in raw):
            raise ValueError("Invalid source percentage")
        if any(not isinstance(x, (int, float)) or not isfinite(x) or not 0 <= x <= 1 for x in probs):
            raise ValueError("Invalid candidate probability")
        if any(not isclose(p, x / sum(raw), abs_tol=1e-12) for x, p in zip(raw, probs)):
            raise ValueError("Candidate probabilities must reproduce the rounded source table")


def assign_confidence(profile, identity, seed, distribution):
    if set(profile) - PROFILE_KEYS:
        raise ValueError("Persona whitelist: unexpected attribute")
    education = EDUCATION_MAP.get(profile.get("education_group"))
    if education is None:
        return None
    probabilities = distribution["education_tables"][education]["candidate_probabilities"]
    # The same household gets the same uniform draw across months. Changed
    # education would change its conditional transform and is separately audited.
    u = int.from_bytes(stable_rank(seed, "confidence", identity)[:8], "big") / 2**64
    cumulative = 0.0
    for label, p in zip(CATEGORIES, probabilities):
        cumulative += p
        if u < cumulative:
            return label
    return CATEGORIES[-1]


def confidence_block(label):
    if label is None or label == "dont_know_or_refused":
        # DK and refusal are pooled in the source. Do not invent an ignorance,
        # distrust or refusal persona for this non-substantive response.
        return ""
    if label not in CONFIDENCE_TEXT:
        raise ValueError("Invalid confidence label")
    return INSERT_PREFIX + CONFIDENCE_TEXT[label] + "\n\n"


def augment_messages(messages, label):
    if len(messages) != 1 or messages[0].get("role") != "user" or set(messages[0]) != {"role", "content"}:
        raise ValueError("Expected the saved single-message v2-abstract contract")
    text = messages[0]["content"]
    if text.count(MARKER) != 1 or INSERT_PREFIX in text:
        raise ValueError("Questionnaire marker or existing treatment mismatch")
    if any(term in text for term in ("Q9_mean", "Q9c_mean", "previous_answer", "prior_answer")):
        raise ValueError("Unexpected derived-answer or prior-answer field in prompt")
    before, after = text.split(MARKER, 1)
    result = deepcopy(messages)
    result[0]["content"] = before + confidence_block(label) + MARKER + after
    return result


def shuffled_labels(labels, seed, namespace):
    order = sorted(labels, key=lambda identity: stable_rank(seed, namespace, identity))
    return dict(zip(labels, (labels[identity] for identity in order)))


def audit_news(events, cutoff):
    rows = []
    for event in events:
        if event["pub_date"][:10] > cutoff[:10]:
            raise ValueError("Future news relative to unchanged cutoff")
        text = event["headline"] + " " + event.get("abstract", "")
        flags = []
        if "wage" in event.get("matched_keywords", []) and re.search(r"\bwaged\b", text, re.I) and not re.search(r"\bwages?\b", text, re.I):
            flags.append("lexical_false_positive_wage_matches_waged")
        if "shipping" in event.get("matched_keywords", []) and "Roth Book" in event["headline"]:
            flags.append("shipping_book_not_economic_supply_chain")
        if any(s in event["headline"] for s in ("Food Allergy Law", "Mayor’s Race", "Keep Their Son Alive")):
            flags.append("manual_context_review_needed_not_automatic_exclusion")
        rows.append({
            "event_id": event["event_id"], "headline": event["headline"],
            "pub_date": event["pub_date"], "web_url": event["web_url"],
            "source_matched_keywords": event.get("matched_keywords", []),
            "text_sha256": canonical_hash({"headline": event["headline"], "abstract": event.get("abstract", "")}),
            "flags": flags,
            "lexical_indicators": {k: bool(re.search(v, text, re.I)) for k, v in PATTERNS.items()},
        })
    pairs = []
    stop = {"a", "an", "the", "as", "to", "in", "on", "of", "and", "over", "s", "its"}
    inflections = {"jobs": "job", "disappoints": "disappoint"}
    def title_tokens(title):
        return {inflections.get(t, t) for t in re.findall(r"\w+", title.lower())} - stop
    for i, left in enumerate(events):
        a = title_tokens(left["headline"])
        for right in events[i + 1:]:
            b = title_tokens(right["headline"])
            similarity = len(a & b) / len(a | b) if a | b else 0
            if similarity >= 0.65:
                pairs.append({"left": left["event_id"], "right": right["event_id"],
                              "title_token_jaccard": similarity,
                              "status": "candidate_duplicate_not_deduplicated"})
    return {"events": rows, "event_count": len(rows),
            "lexical_counts": {k: sum(r["lexical_indicators"][k] for r in rows) for k in PATTERNS},
            "flagged_events": sum(bool(r["flags"]) for r in rows),
            "candidate_duplicate_pairs": pairs,
            "interpretation": "Lexical flags, not semantic stance classification, exposure measurement or causal evidence. Frozen E is unchanged."}


def load_run(root, run_name):
    folder = root / "outputs/local_runs" / run_name
    population_path, environment_path = folder / "population_effective.json", folder / "environment_effective.json"
    calls_path = folder / "llm_calls.jsonl"
    population = json.loads(population_path.read_text())["personas"]
    environment = json.loads(environment_path.read_text())["provider_args"]
    calls = {}
    for line in calls_path.read_text().splitlines():
        row = json.loads(line)
        if hashlib.sha256(row["prompt_text"].encode()).hexdigest() != row["prompt_sha256"]:
            raise ValueError("Saved prompt hash mismatch")
        if row.get("error"):
            continue
        if row["agent_id"] in calls:
            raise ValueError("Ambiguous multiple successful source calls")
        calls[row["agent_id"]] = {k: row[k] for k in ("prompt_text", "prompt_sha256", "prompt_version", "target_month")}
    ids = [p["agent_id"] for p in population]
    if len(set(ids)) != len(ids) or set(ids) != set(calls):
        raise ValueError("Source persona/call coverage mismatch")
    source_hashes = {str(p.relative_to(root)): digest(p) for p in (population_path, environment_path, calls_path)}
    return population, environment, calls, source_hashes


def prepare(root, output, per_education=20, seed=42):
    root, output = Path(root).resolve(), Path(output).resolve()
    if per_education < 1:
        raise ValueError("per_education must be positive")
    if not output.is_relative_to(root / "outputs"):
        raise ValueError("Private preparation must stay under Git-ignored outputs/")
    if output.exists():
        raise FileExistsError("Do not overwrite a preparation")
    candidate_path = root / "docs/literature/sce/belief_proxies/fed_confidence_candidate_2021.json"
    distribution = json.loads(candidate_path.read_text())
    validate_distribution(distribution)
    pdf = root / "data/raw/belief_proxies/20261010/gallup_fed_confidence_20210426.pdf"
    if digest(pdf) != distribution["source_sha256"]:
        raise ValueError("Gallup source PDF hash mismatch")
    output.mkdir(parents=True)
    summary = {"status": "offline_prepared_not_executable_simulation", "research_line": "A_development",
               "created_at_utc": datetime.now(timezone.utc).isoformat(), "seed": seed,
               "per_education": per_education, "arms": list(ARMS), "months": {},
               "source_hashes": {str(p.relative_to(root)): digest(p) for p in
                                 (candidate_path, pdf, Path(__file__), root / "scripts/prepare_sce_belief_trial.py",
                                  root / "scripts/build_nyt_events.py")},
               "new_llm_calls": 0, "new_mcp_calls": 0, "new_api_cost_usd": 0,
               "B_eligible": False, "provider_registered": False,
               "government_confidence_added": False, "TIPS_added": False,
               "inflation_persistence_population_added": False}
    preview, linkage, draws, news, news_candidates = [], [], {}, {}, {}
    previous = {}
    cross_month = {"same_source_household": 0, "changed_education": 0, "same_education_changed_label": 0}
    for month, name in SOURCE_RUNS.items():
        population, env, calls, hashes = load_run(root, name)
        summary["source_hashes"].update(hashes)
        target = env["targets"][0]
        if target["target_month"].replace("-", "") != month:
            raise ValueError("Source month mismatch")
        all_labels = {p["agent_id"]: assign_confidence(p["attributes"], p["agent_id"], seed, distribution) for p in population}
        selected = []
        groups = {}
        for education in EDUCATION_MAP:
            pool = [p for p in population if p["attributes"].get("education_group") == education]
            if len(pool) < per_education:
                raise ValueError("Not enough eligible source households; no replacement or silent fallback")
            selected.extend(sorted(pool, key=lambda p: stable_rank(seed, "sampling:" + education, p["agent_id"]))[:per_education])
            groups[education] = {"source_n": len(pool), "selected_n": per_education}
        labels = {p["agent_id"]: all_labels[p["agent_id"]] for p in selected}
        permuted = shuffled_labels(labels, seed + 100000, "shuffle:" + month)
        if Counter(labels.values()) != Counter(permuted.values()):
            raise ValueError("Permutation must preserve exact category counts")
        draw_rows = []
        for i, persona in enumerate(selected, 1):
            identity = persona["agent_id"]
            alias = f"belief_{month}_{i:03d}"
            education = persona["attributes"]["education_group"]
            source = calls[identity]
            base = json.loads(source["prompt_text"])
            # Validates answer-field isolation even in the no-treatment arm.
            augment_messages(base, None)
            if identity in source["prompt_text"]:
                raise ValueError("Source ID must not be sent in message text")
            if source["target_month"] != target["target_month"]:
                raise ValueError("Saved call month mismatch")
            linkage.append({"target_month": month, "case_id": alias, "source_agent_id": identity})
            for arm in ARMS:
                label = None if arm == ARMS[0] else labels[identity] if arm == ARMS[1] else permuted[identity]
                messages = augment_messages(base, label)
                if messages[0]["content"].replace(confidence_block(label), "", 1) != base[0]["content"]:
                    raise ValueError("Treatment changed the baseline information or questionnaire")
                preview.append({"case_id": alias, "target_month": month, "arm": arm,
                                "confidence_category": label, "source_prompt_sha256": source["prompt_sha256"],
                                "messages_sha256": canonical_hash(messages), "messages": messages})
            draw_rows.append({"case_id": alias, "education_group": education,
                              "conditioned": labels[identity], "shuffled": permuted[identity]})
        for persona in population:
            identity, education = persona["agent_id"], persona["attributes"].get("education_group")
            if identity in previous:
                cross_month["same_source_household"] += 1
                old_education, old_label = previous[identity]
                cross_month["changed_education"] += int(old_education != education)
                cross_month["same_education_changed_label"] += int(old_education == education and old_label != all_labels[identity])
            previous[identity] = (education, all_labels[identity])
        draws[month] = {"selected": draw_rows,
                        "alternative_draw_counts": {str(s): dict(Counter(assign_confidence(p["attributes"], p["agent_id"], s, distribution) for p in selected)) for s in (seed, seed + 1000, seed + 2000)}}
        news[month] = audit_news(env["events_by_step"]["0"], target["as_of"])
        clear_flags = {"lexical_false_positive_wage_matches_waged", "shipping_book_not_economic_supply_chain"}
        removal = {r["event_id"] for r in news[month]["events"] if set(r["flags"]) & clear_flags}
        news_candidates[month] = {
            "status": "review_candidate_only_not_installed",
            "as_of": target["as_of"], "excluded_event_ids": sorted(removal),
            "events": [e for e in env["events_by_step"]["0"] if e["event_id"] not in removal],
            "rule": "Only the two documented clear false positives; ambiguous contexts and duplicate candidates retained.",
        }
        summary["months"][month] = {"target": target, "source_n": len(population), "education": groups,
                                    "unmapped_education_n": sum(v is None for v in all_labels.values()),
                                    "selected_n": len(selected), "conditioned_category_counts": dict(Counter(labels.values())),
                                    "shuffle_same_category_n": sum(labels[k] == permuted[k] for k in labels),
                                    "full_source_category_counts": dict(Counter(all_labels.values())),
                                    "news_screen": {k: v for k, v in news[month].items() if k not in ("events", "interpretation")}}
    summary["cross_month_assignment_check"] = cross_month
    summary["prompt_count"] = len(preview)
    summary["preview_inputs_sha256"] = canonical_hash(preview)
    for name, value in (("summary.json", summary), ("candidate_assignments_private.json", draws),
                        ("private_evaluation_link.json", linkage), ("news_inventory.json", news),
                        ("news_screen_candidate.json", news_candidates)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    with (output / "prompt_previews_private.jsonl").open("w") as handle:
        for row in preview:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--per-education", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out or root / "outputs" / f"sce_belief_preparation_20261011_{uuid4().hex[:8]}"
    result = prepare(root, out, args.per_education, args.seed)
    print(json.dumps({"output": str(out), "status": result["status"], "prompt_count": result["prompt_count"],
                      "months": result["months"], "new_llm_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
