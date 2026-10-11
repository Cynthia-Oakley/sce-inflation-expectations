"""Audit new-month P/E and prepare public-news labeling inputs, entirely offline.

This creates candidate sources and synthetic national confidence assignments.
It has no API client, credential reader, simulation runner or outcome reader.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from math import isfinite
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .belief_trial_preparation import CATEGORIES, confidence_block, stable_rank
from .evaluation.shared_environment import extract_shared_rows
from .monthly_population import ATTRIBUTE_KEYS
from .news_exposure_demo import front_page_status
from .news_exposure_trial import load_labels
from .news_selection_trial import RecallRules, RULE_FILE, normalize
from .price_experience import BasketAssigner, prepare_ce_donors

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def latest_wave(waves, as_of):
    """Date-only publication evidence is admitted at the end of its local day."""
    cutoff = datetime.fromisoformat(as_of)
    if cutoff.tzinfo is None:
        raise ValueError("cutoff requires a timezone")
    eligible = []
    for wave in waves:
        published = datetime.fromisoformat(wave["published_date"] + "T23:59:59").replace(
            tzinfo=ZoneInfo("America/New_York"))
        if published <= cutoff:
            eligible.append(wave)
    if not eligible:
        raise ValueError("no previously published confidence wave")
    return max(eligible, key=lambda wave: wave["published_date"])


def national_confidence(identity, seed, wave):
    raw = wave["national_source_percent"]
    if len(raw) != len(CATEGORIES) or any(type(x) not in (int, float) or not isfinite(x) or not 0 <= x <= 100 for x in raw) or sum(raw) <= 0:
        raise ValueError("invalid national distribution")
    uniform = int.from_bytes(stable_rank(seed, "national_fed_confidence", identity)[:8], "big") / 2**64
    cumulative = 0.
    for category, value in zip(CATEGORIES, raw):
        cumulative += value / sum(raw)
        if uniform < cumulative:
            return category
    return CATEGORIES[-1]


def previous_month(target):
    year, month = map(int, target.split("-"))
    return f"{year - (month == 1):04d}-{12 if month == 1 else month - 1:02d}"


def build_news_pool(root, target, as_of, rules):
    """Previous calendar month + current month through exact NY cutoff.

    Later reports about the same event remain. Only duplicate source identity
    is collapsed here; same-time/text deduplication occurs in exposure assembly.
    """
    cutoff = datetime.fromisoformat(as_of)
    if cutoff.tzinfo is None:
        raise ValueError("cutoff requires timezone")
    start = datetime.fromisoformat(previous_month(target) + "-01T00:00:00").replace(
        tzinfo=ZoneInfo("America/New_York"))
    rows, seen, counts, sources = [], {}, Counter(), {}
    for month in (previous_month(target), target):
        path = root / "data/raw/nyt_archive" / (month + ".json")
        sources[str(path.relative_to(root))] = sha(path)
        docs = json.loads(path.read_bytes())["response"]["docs"]
        for doc in docs:
            counts["raw_docs"] += 1
            stamp = doc.get("pub_date")
            try:
                published = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                if published.tzinfo is None:
                    raise ValueError("no timezone")
            except (ValueError, TypeError, AttributeError):
                counts["unknown_publication_time_quarantined"] += 1
                continue
            if published < start or published > cutoff:
                counts["outside_window"] += 1
                continue
            counts["docs_in_window"] += 1
            if str(doc.get("document_type") or "").casefold() != "article":
                counts["non_article"] += 1
                continue
            text = {"headline": (doc.get("headline") or {}).get("main") or "",
                    "abstract": doc.get("abstract") or "", "snippet": doc.get("snippet") or ""}
            identity = doc.get("_id") or doc.get("uri") or doc.get("web_url")
            if not identity or not any(text.values()):
                counts["missing_identity_or_text"] += 1
                continue
            text_hash = hashlib.sha256(json.dumps(text, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if identity in seen:
                if seen[identity] != (stamp, text_hash):
                    raise ValueError("conflicting duplicate source article")
                counts["duplicate_source_identity"] += 1
                continue
            seen[identity] = (stamp, text_hash)
            article_id = hashlib.sha256((identity + "\n" + text_hash).encode()).hexdigest()[:24]
            hits = rules.classify(doc)
            placement = front_page_status(doc)
            rows.append(dict(text, article_id=article_id, canonical_source_id=identity,
                             source="NYT Archive API", source_month=month, pub_date=stamp,
                             section_name=doc.get("section_name") or "", news_desk=doc.get("news_desk") or "",
                             web_url=doc.get("web_url") or "", text_sha256=text_hash,
                             text_vintage_status="unverified_archive_snapshot", new_hits=hits,
                             print_section=doc.get("print_section"), print_page=doc.get("print_page"),
                             placement=placement))
            counts["unique_articles"] += 1
            counts["coarse_candidates"] += bool(hits)
            counts["recorded_a1"] += placement == "a1"
            counts["abstract_equals_snippet"] += bool(text["abstract"]) and normalize(text["abstract"]) == normalize(text["snippet"])
    return rows, dict(counts), sources


def prepare(root, monthly, out, label_dirs, *, seed=42, sample_size=48):
    if out.exists() or not out.resolve().is_relative_to(root / "outputs"):
        raise ValueError("use a fresh ignored outputs directory")
    source_manifest = json.loads((monthly / "manifest.json").read_text())
    for package in source_manifest["packages"]:
        for name, expected in package["sha256"].items():
            if sha(monthly / package["path"] / name) != expected:
                raise ValueError("monthly package changed")
    wave_path = root / "docs/literature/sce/belief_proxies/gallup_waves_20261011.json"
    wave_config = json.loads(wave_path.read_text())
    labels = load_labels(label_dirs)
    rules = RecallRules(json.loads(RULE_FILE.read_text()))
    # Reuse the declared CE proxy to isolate the new mechanism. This is not a
    # claim that 2020 consumption shares describe each 2024 household exactly.
    basket_source_path = root / "outputs/ce_population_baskets_20261006T063749Z_a8be0d98/202105/experience.json"
    source = json.loads(basket_source_path.read_text())["source"]
    ce = root / "data/raw/ce_experience/20261006/intrvw20.zip"
    from zipfile import ZipFile
    import csv
    import io
    with ZipFile(ce) as archive:
        ce_bytes = archive.read(source["member"])
    if sha(ce) != source["data_sha256"] or hashlib.sha256(ce_bytes).hexdigest() != source["member_sha256"]:
        raise ValueError("CE source changed")
    donors, donor_stats = prepare_ce_donors(csv.DictReader(io.StringIO(ce_bytes.decode("utf-8-sig"))))
    assigner = BasketAssigner(donors, source, seed=seed, min_pool=25)
    out.mkdir(parents=True)
    pending, stats, hashes = {}, [], {}
    dependencies = [Path(__file__).with_name(name) for name in (
        "belief_trial_preparation.py", "monthly_population.py", "news_exposure_demo.py",
        "news_exposure_trial.py", "news_selection_trial.py", "price_experience.py")]
    dependencies.append(Path(__file__).parent / "evaluation/shared_environment.py")
    for path in [monthly / "manifest.json", wave_path, RULE_FILE, Path(__file__), basket_source_path, ce] + dependencies:
        hashes[str(path.relative_to(root))] = sha(path)
    for directory in label_dirs:
        for name in ("state.json", "labels.jsonl"):
            path = directory / name
            hashes[str(path.relative_to(root))] = sha(path)
    for wave in wave_config["waves"]:
        path = root / wave["local_file"]
        if sha(path) != wave["sha256"]:
            raise ValueError("confidence source changed")
        hashes[wave["local_file"]] = wave["sha256"]
    policy_path = root / "docs/literature/sce/belief_proxies/fomc_candidate_facts_20261011.json"
    policy = json.loads(policy_path.read_text())
    hashes[str(policy_path.relative_to(root))] = sha(policy_path)
    for fact in policy["files"]:
        if sha(root / fact["file"]) != fact["sha256"]:
            raise ValueError("policy source changed")
        hashes[fact["file"]] = fact["sha256"]
    for package in source_manifest["packages"]:
        if not package["path"].startswith(f"n{sample_size}/"):
            continue
        src = monthly / package["path"]
        for name, expected in package["sha256"].items():
            if sha(src / name) != expected:
                raise ValueError("monthly package changed")
        pop = json.loads((src / "population.json").read_text())
        env = json.loads((src / "environment.json").read_text())
        shared = extract_shared_rows(env, allow_unverified_vintage=True)[0]
        target, cutoff = shared["target_month"], shared["as_of"]
        wave = latest_wave(wave_config["waves"], cutoff)
        eligible_policy = [f for f in policy["files"] if datetime.fromisoformat(f["published_at"]) <= datetime.fromisoformat(cutoff)]
        latest_policy = max(eligible_policy, key=lambda f: f["published_at"])
        rows, news_stats, news_sources = build_news_pool(root, target, cutoff, rules)
        hashes.update(news_sources)
        candidates = [r for r in rows if r["new_hits"]]
        for row in candidates:
            if row["article_id"] not in labels:
                pending[row["article_id"]] = {k: row[k] for k in (
                    "article_id", "headline", "abstract", "snippet", "source", "section_name", "news_desk")}
        month_out = out / target.replace("-", "")
        month_out.mkdir()
        dump(month_out / "news_pool.json", rows)
        assignments, baskets = [], {}
        for person in pop["personas"]:
            if set(person["attributes"]) - ATTRIBUTE_KEYS or person["weight"] != 1:
                raise ValueError("profile whitelist/weight violation")
            label = national_confidence(person["agent_id"], seed, wave)
            assignments.append({"agent_id": person["agent_id"], "label": label, "wave_id": wave["wave_id"],
                                "basis": "synthetic draw from national adult distribution; no demographic conditioning",
                                "candidate_prompt_addition": confidence_block(label)})
            baskets[person["agent_id"]] = assigner.assign(person["agent_id"], person["attributes"])
        dump(month_out / "confidence_assignments_private.json", assignments)
        dump(month_out / "synthetic_ce_baskets_private.json", baskets)
        dump(month_out / "public_policy_candidate.json", latest_policy)
        census_meta = json.loads((monthly / "all" / str(package["target_month"]) / "sampling_meta.json").read_text())
        row = {"target_month": target, "as_of": cutoff, "frame_n": package["frame_n"], "sample_n": package["selected_n"],
               "full_frame_missing_attributes": {k: package["frame_n"] - sum(v.values()) for k, v in census_meta["attribute_counts"].items()},
               "numeric_signals": len(shared["signals"]), "numeric_evidence_uncertainties": shared["evidence_uncertainties"],
               "old_selected_news": len(shared["news"]), "news": news_stats,
               "new_labels_needed": sum(r["article_id"] not in labels for r in candidates),
               "previously_labelled_candidates": sum(r["article_id"] in labels for r in candidates),
               "latest_confidence_wave": wave["wave_id"], "wave_published_date": wave["published_date"],
               "confidence_source_age_days": (datetime.fromisoformat(cutoff).date() - datetime.fromisoformat(wave["field_dates"][1]).date()).days,
               "confidence_counts": dict(Counter(a["label"] for a in assignments)),
               "latest_archived_policy_date": latest_policy["release_date"],
               "policy_status": "candidate_only_not_injected; same_policy_exposure_required_across_confidence_arms",
               "ce_proxy_wave": source["interview_wave"], "ce_proxy_match_depth_counts": dict(Counter(len(x["matched_fields"]) for x in baskets.values())),
               "simulation_status": "not_configured_not_called; monthly simulation.json is the old scripted preparation template"}
        dump(month_out / "summary.json", row)
        stats.append(row)
    if not stats:
        raise ValueError("monthly inputs contain no requested sample-size packages")
    prompt_path = root / "docs/literature/sce/news_selection/llm_label_prompt_v1_2.md"
    hashes[str(prompt_path.relative_to(root))] = sha(prompt_path)
    system = re.search(r"```text\n(.*?)\n```", prompt_path.read_text(), re.S).group(1)
    articles = [pending[key] for key in sorted(pending)]
    requests = []
    for i in range(0, len(articles), 8):
        batch = articles[i:i + 8]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"articles": batch}, ensure_ascii=False)}]
        requests.append({"batch_id": len(requests) + 1, "article_ids": [r["article_id"] for r in batch],
                         "payload": {"model": "deepseek-flash", "temperature": 0, "max_tokens": 2400,
                                     "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"}, "messages": messages},
                         "input_byte_reservation": len(json.dumps(messages, ensure_ascii=False).encode()) + 512})
    (out / "news_requests_draft.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests))
    dump(out / "pending_public_articles.json", articles)
    protected = json.loads((root / "docs/sources/sol_handoff_protected_files_20261010.json").read_text())["files_sha256"]
    if any(sha(root / path) != digest for path, digest in protected.items()):
        raise ValueError("protected work changed")
    result = {"status": "offline_sources_and_inputs_prepared; paid_classification_and_simulation_not_authorized",
              "created_at_utc": datetime.now(timezone.utc).isoformat(), "research_line": "A_historical_reconstruction",
              "monthly_inputs_path": str(monthly.relative_to(root)), "months": stats,
              "unique_news_labels_needed": len(articles), "draft_label_batches": len(requests), "batch_size": 8,
              "new_paid_api_calls": 0, "simulation_calls": 0, "source_sha256": hashes, "protected_files_unchanged": len(protected),
              "ce_donors": donor_stats, "confidence_assignment_seed": seed,
              "requested_sample_size": sample_size,
              "news_timestamp_rule": "previous month start 00:00 NY through as_of, using aware online pub_date; original text/print-date vintage unverified",
              "confidence_primary_candidate": "national distribution only; education conditioning remains separate optional research",
              "configuration_status": "month and sample candidates prepared, not a frozen paid experiment",
              "remaining_gates": ["classify new public news with a new budget and guarded runner", "freeze actual confidence experiment and generation/news seeds",
                                  "register decision provider and prepare final prompts with no truth/weights/IDs", "dry-run then confirm concrete model/data-send/budget scope"],
              "not_claimed": ["confidence matches actual people", "forecast B input validity", "national representativeness of 48 cases", "fully unseen holdout months", "historical version certification"]}
    dump(out / "summary.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--monthly-inputs", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--labels", type=Path, action="append", required=True)
    parser.add_argument("--sample-size", type=int, default=48)
    args = parser.parse_args(argv)
    result = prepare(ROOT, args.monthly_inputs.resolve(), args.out.resolve(), [p.resolve() for p in args.labels], sample_size=args.sample_size)
    print(json.dumps({"months": [{k: m[k] for k in ("target_month", "frame_n", "sample_n", "numeric_signals", "new_labels_needed", "latest_confidence_wave")} for m in result["months"]],
                      "unique_news_labels_needed": result["unique_news_labels_needed"], "draft_label_batches": result["draft_label_batches"], "new_paid_api_calls": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
