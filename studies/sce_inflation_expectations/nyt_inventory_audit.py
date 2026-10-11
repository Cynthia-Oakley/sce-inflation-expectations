"""Read-only NYT cache inventory and unselected-news sampling; no API or keys."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re

MONTH_FILE = re.compile(r"\d{4}-\d{2}\.json")
# Only a sampling aid, not a new admission rule or a relevance gold standard.
HOUSEHOLD_WORDS = re.compile(
    r"\b(?:grocer\w*|supermarket\w*|retail\w*|food|diaper\w*|soap|laundry|"
    r"detergent\w*|consumer\w*|shop\w*|rent\w*|electric\w*|utilit\w*|"
    r"clothing|apparel|salary|income|price\w*|cost\w*|housing|mortgage\w*)\b", re.I)
FIELDS = ("abstract", "snippet", "lead_paragraph", "pub_date", "web_url",
          "_id", "uri", "section_name", "news_desk", "print_section", "print_page")
RUNS = {
    "202105": "outputs/local_runs/sce-local-openai-20261005T092656Z-202105-8d2e3b2c/environment_effective.json",
    "202106": "outputs/local_runs/sce-local-openai-20261005T092656Z-202106-e4f49f76/environment_effective.json",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_selector(root: Path):
    path = root / "scripts/build_nyt_events.py"
    spec = importlib.util.spec_from_file_location("nyt_selector_readonly", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def inventory(root: Path, selector):
    folder = root / "data/raw/nyt_archive"
    ledger_path = folder / "events_ledger.jsonl"
    ledger = [json.loads(line) for line in ledger_path.read_text().splitlines() if line.strip()]
    ledger_by_month = {}
    for row in ledger:
        ledger_by_month.setdefault(row["month"], []).append(row)
    rows = []
    for path in sorted(folder.iterdir()):
        if not MONTH_FILE.fullmatch(path.name):
            continue
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        response = json.loads(payload)["response"]
        docs = response["docs"]
        meta_path = path.with_name(path.stem + ".meta.json")
        meta = json.loads(meta_path.read_bytes()) if meta_path.exists() else {}
        dt_counts = Counter(str(d.get("document_type") or "unknown") for d in docs)
        date_errors = 0
        utc_month_other = 0
        for doc in docs:
            try:
                stamp = datetime.fromisoformat(doc["pub_date"].replace("Z", "+00:00"))
                utc_month_other += stamp.astimezone(timezone.utc).strftime("%Y-%m") != path.stem
            except (KeyError, TypeError, ValueError):
                date_errors += 1
        stored = ledger_by_month.get(path.stem)
        replay = selector.select_events(docs, path.stem, digest, 30) if stored is not None else None
        rows.append({
            "month": path.stem, "path": str(path.relative_to(root)), "bytes": len(payload),
            "sha256": digest, "meta_path": str(meta_path.relative_to(root)),
            "meta_exists": meta_path.exists(), "meta_sha256_matches": meta.get("sha256") == digest,
            "meta_n_docs_matches": meta.get("n_docs") == len(docs),
            "response_hits": response.get("meta", {}).get("hits"),
            "response_hits_matches": response.get("meta", {}).get("hits") == len(docs),
            "docs": len(docs), "document_types": dict(dt_counts),
            "unique_urls": len({d.get("web_url") for d in docs if d.get("web_url")}),
            "unique_article_ids": len({d.get("_id") for d in docs if d.get("_id")}),
            "headline_nonempty": sum(bool((d.get("headline") or {}).get("main")) for d in docs),
            "field_nonempty": {key: sum(bool(d.get(key)) for d in docs) for key in FIELDS},
            "invalid_pub_date": date_errors, "pub_date_utc_other_month": utc_month_other,
            "fetched_at": meta.get("fetched_at"), "local_ledger_rows": len(stored) if stored else 0,
            "replayed_monthly_selected": len(replay) if replay is not None else None,
            "ledger_replay_exact": stored == replay if stored is not None else None,
        })
    first, last = rows[0]["month"], rows[-1]["month"]
    expected = selector.parse_months(first + ".." + last)
    found = {r["month"] for r in rows}
    types = Counter()
    fields = Counter()
    for row in rows:
        types.update(row["document_types"])
        fields.update(row["field_nonempty"])
    return {
        "checked_on": "2026-10-11", "raw_cache_path": "data/raw/nyt_archive/",
        "months": len(rows), "first_month": first, "last_month": last,
        "missing_months_between_endpoints": sorted(set(expected) - found),
        "bytes": sum(r["bytes"] for r in rows), "docs": sum(r["docs"] for r in rows),
        "document_types": dict(types), "field_nonempty": dict(fields),
        "headline_nonempty": sum(r["headline_nonempty"] for r in rows),
        "all_meta_sha256_match": all(r["meta_sha256_matches"] for r in rows),
        "all_meta_counts_match": all(r["meta_n_docs_matches"] for r in rows),
        "all_response_hits_match": all(r["response_hits_matches"] for r in rows),
        "invalid_pub_dates": sum(r["invalid_pub_date"] for r in rows),
        "ledger_path": str(ledger_path.relative_to(root)), "ledger_sha256": sha(ledger_path),
        "ledger_rows": len(ledger), "ledger_months": len(ledger_by_month),
        "ledger_first": min(ledger_by_month), "ledger_last": max(ledger_by_month),
        "ledger_covered_months_exact_replay": all(r["ledger_replay_exact"] for r in rows if r["local_ledger_rows"]),
        "selector_sha256": sha(root / "scripts/build_nyt_events.py"), "monthly": rows,
        "new_api_calls": 0, "keys_read": False,
        "text_vintage_status": "unverified_archive_snapshot",
        "scope_note": "Original API metadata responses, not archived full article bodies. Header/abstract content versions at historical as_of are not established.",
    }, ledger_by_month


def merge_like_production(events, selector):
    selected = sorted([e for e in events if selector._TIER_RANK[e["tier"]] == 0], key=lambda e: e["pub_date"])
    for rank in (1, 2, 3):
        pool = [e for e in events if selector._TIER_RANK[e["tier"]] == rank]
        pool.sort(key=lambda e: e["pub_date"], reverse=True)
        pool.sort(key=lambda e: -len(e["matched_keywords"]))
        selected.extend(pool[:max(0, 30 - len(selected))])
    return sorted(selected, key=lambda e: e["pub_date"])


def sample_window(root: Path, selector, ledger, target, run_path, out: Path):
    source = root / run_path
    snapshot = json.loads(source.read_bytes())
    saved = snapshot["provider_args"]["events_by_step"]["0"]
    cutoff = saved[0]["selection_cutoff"]
    assert all(e["selection_cutoff"] == cutoff for e in saved)
    current = target[:4] + "-" + target[4:]
    y, m = map(int, current.split("-"))
    previous = f"{y if m > 1 else y - 1:04d}-{m - 1 if m > 1 else 12:02d}"
    raw = []
    stage_one_ids = set()
    raw_sources = []
    for month in (previous, current):
        path = root / "data/raw/nyt_archive" / (month + ".json")
        docs = json.loads(path.read_bytes())["response"]["docs"]
        eligible = [d for d in docs if (d.get("pub_date") or "")[:10] <= cutoff]
        stage_one = ledger[month] if month == previous else selector.select_events(eligible, month, sha(path), 30)
        stage_one_ids.update(e["event_id"] for e in stage_one)
        raw.extend((month, d) for d in eligible)
        raw_sources.append({"path": str(path.relative_to(root)), "sha256": sha(path), "date_eligible_docs": len(eligible), "stage_one_rows": len(stage_one)})
    production_pool = list(ledger[previous])
    current_docs = [d for month, d in raw if month == current]
    production_pool.extend(selector.select_events(current_docs, current, raw_sources[1]["sha256"], 30))
    replay = merge_like_production(production_pool, selector)
    replay_exact = [e["event_id"] for e in replay] == [e["event_id"] for e in saved]
    saved_by_id = {e["event_id"]: e for e in saved}
    text_exact = all(saved_by_id.get(e["event_id"], {}).get("headline") == e["headline"] and saved_by_id.get(e["event_id"], {}).get("abstract") == e["abstract"] for e in replay)
    pools = {"budget_removed": [], "rule_blocked_enriched": [], "rule_blocked_other": []}
    stages = Counter()
    dedup = set()
    final_ids = set(saved_by_id)
    for month, doc in raw:
        if str(doc.get("document_type") or "").casefold() != "article":
            stages["non_article"] += 1
            continue
        url = doc.get("web_url") or ""
        event_id = hashlib.sha256(url.encode()).hexdigest()[:16]
        if url in dedup:
            stages["duplicate_url"] += 1
            continue
        dedup.add(url)
        tier, matched = selector.classify_doc(doc)
        if event_id in final_ids:
            stages["final_selected"] += 1
            continue
        if tier is None:
            stage = "no_keyword_or_frontpage"
        elif event_id not in stage_one_ids:
            stage = "monthly_budget"
        else:
            stage = "merged_budget"
        stages[stage] += 1
        headline = (doc.get("headline") or {}).get("main", "")
        text = " ".join([headline, doc.get("abstract") or "", doc.get("snippet") or ""])
        is_enriched = (doc.get("section_name") == "Business Day" or doc.get("news_desk") == "Business" or HOUSEHOLD_WORDS.search(text))
        stratum = "budget_removed" if tier else ("rule_blocked_enriched" if is_enriched else "rule_blocked_other")
        pools[stratum].append({
            "event_id": event_id, "article_id": doc.get("_id"), "uri": doc.get("uri"),
            "target_month": target, "source_month": month, "pub_date": doc.get("pub_date"),
            "selection_cutoff": cutoff, "headline": headline, "abstract": doc.get("abstract") or "",
            "snippet": doc.get("snippet") or "", "web_url": url,
            "section_name": doc.get("section_name"), "news_desk": doc.get("news_desk"),
            "old_tier": tier, "matched_keywords": matched,
            "removed_at": stage, "sampling_stratum": stratum,
            "text_vintage_status": "unverified_archive_snapshot",
        })
    rng = random.Random(42 + int(target))
    sample = []
    for name, pool in pools.items():
        ordered = sorted(pool, key=lambda r: (r["pub_date"], r["event_id"]))
        sample.extend(rng.sample(ordered, min(20, len(ordered))))
    for index, row in enumerate(sample, 1):
        row["sample_id"] = f"{target}_{index:02d}"
    dump(out / ("unselected_pool_" + target + ".json"), pools)
    dump(out / ("sample_" + target + ".json"), sample)
    return {
        "target_month": target, "cutoff": cutoff, "saved_source_path": run_path,
        "saved_source_sha256": sha(source), "raw_sources": raw_sources,
        "eligible_raw_docs": len(raw), "stage_counts": dict(stages),
        "sampling_stratum_sizes": {name: len(pool) for name, pool in pools.items()},
        "sample_counts": dict(Counter(r["sampling_stratum"] for r in sample)),
        "sample_path": str((out / ("sample_" + target + ".json")).relative_to(root)),
        "sample_sha256": sha(out / ("sample_" + target + ".json")),
        "production_replay_event_ids_order_exact": replay_exact,
        "production_replay_titles_abstracts_exact": text_exact,
        "sampling_note": "20 random cases per stratum, seed42+targetmonth; enriched rule-blocked stratum intentionally overrepresented. Diagnostic audit, not overall recall estimation.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    out = args.out if args.out.is_absolute() else root / args.out
    out.mkdir(parents=True, exist_ok=False)
    selector = load_selector(root)
    summary, ledger = inventory(root, selector)
    dump(out / "inventory_snapshot.json", summary)
    summary["development_windows"] = [sample_window(root, selector, ledger, target, path, out) for target, path in RUNS.items()]
    protected = json.loads((root / "docs/sources/sol_handoff_protected_files_20261010.json").read_bytes())["files_sha256"]
    summary["protected_files_unchanged"] = {path: sha(root / path) == expected for path, expected in protected.items()}
    summary["audit_module_sha256"] = sha(Path(__file__))
    dump(out / "inventory_summary.json", summary)
    print(json.dumps({key: summary[key] for key in ("months", "first_month", "last_month", "docs", "document_types", "all_meta_sha256_match", "all_meta_counts_match", "all_response_hits_match", "ledger_months", "ledger_covered_months_exact_replay", "development_windows")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
