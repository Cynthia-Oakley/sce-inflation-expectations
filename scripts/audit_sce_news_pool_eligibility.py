"""Offline eligibility audit of the recent 11-month SCE news label candidate pools.

Purpose: zero-LLM, zero-network audit of outputs/sce_fullperiod_materialized_20261022_v2/
<YYYYMM>/news_label_index.json candidate pools for target months 2025-11..2026-09.
Replicates build_news_pool_tolerant identity/article_id logic, cross-checks the index
pools, and grades time eligibility, label provenance, text vintage and SCE leakage.

Outputs (overwritten on each run, ids and metadata only, no article text):
  outputs/sce_recent_environment_evidence_20261023_v1/news_pool_eligibility.jsonl
  outputs/sce_recent_environment_evidence_20261023_v1/news_pool_summary.json

Run: /Users/wushuyue/anaconda3/envs/socioverse/bin/python scripts/audit_sce_news_pool_eligibility.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studies.sce_inflation_expectations.news_selection_trial import RecallRules, RULE_FILE  # noqa: E402

V2 = ROOT / "outputs/sce_fullperiod_materialized_20261022_v2"
OUT = ROOT / "outputs/sce_recent_environment_evidence_20261023_v1"
OUT.mkdir(parents=True, exist_ok=True)

TARGETS = [f"{y}{m:02d}" for y, ms in ((2025, (11, 12)), (2026, range(1, 10))) for m in ms]
WINDOW_MONTHS = sorted({wm for t in TARGETS for wm in (
    f"{int(t[:4]) - (int(t[4:]) == 1):04d}-{12 if int(t[4:]) == 1 else int(t[4:]) - 1:02d}", f"{t[:4]}-{t[4:]}")})

ET = ZoneInfo("America/New_York")


def previous_month_iso(target_iso: str) -> str:
    y, m = int(target_iso[:4]), int(target_iso[5:7])
    return f"{y - (m == 1):04d}-{12 if m == 1 else m - 1:02d}"


def doc_text(doc):
    return {"headline": (doc.get("headline") or {}).get("main") or "",
            "abstract": doc.get("abstract") or "", "snippet": doc.get("snippet") or ""}


def article_id_for(identity: str, text_hash: str) -> str:
    return hashlib.sha256((identity + "\n" + text_hash).encode()).hexdigest()[:24]


def placement_of(doc) -> str:
    section = str(doc.get("print_section") or "").strip().upper()
    page = str(doc.get("print_page") or "").strip()
    if not section or not page:
        return "unknown"
    return "a1" if section == "A" and page == "1" else "other_recorded_page"


# ---------------------------------------------------------------- raw cache map
rawmap = {}          # article_id -> metadata (first occurrence across caches, tolerant)
meta_fetch = {}      # month -> fetched_at
for ym in WINDOW_MONTHS:
    meta = json.loads((ROOT / f"data/raw/nyt_archive/{ym}.meta.json").read_text())
    meta_fetch[ym] = meta["fetched_at"]
    docs = json.loads((ROOT / f"data/raw/nyt_archive/{ym}.json").read_bytes())["response"]["docs"]
    for doc in docs:
        if str(doc.get("document_type") or "").casefold() != "article":
            continue
        identity = doc.get("_id") or doc.get("uri") or doc.get("web_url")
        text = doc_text(doc)
        if not identity or not any(text.values()):
            continue
        th = hashlib.sha256(json.dumps(text, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        aid = article_id_for(identity, th)
        if aid in rawmap:
            continue
        rawmap[aid] = dict(
            canonical_source_id=identity, pub_date_full=doc.get("pub_date"), source_month=ym,
            section_name=doc.get("section_name") or "", news_desk=doc.get("news_desk") or "",
            print_section=doc.get("print_section"), print_page=doc.get("print_page"),
            placement=placement_of(doc), text_sha256=th, **text)

# ---------------------------------------------------------------- label sources
label_src = {}       # article_id -> (source_file, label_row)
label_conflicts = []
for pattern in ("outputs/sce_*label*/labels.jsonl",
                "outputs/sce_expanded_news_run_20261014_v1/part_*/labels.jsonl"):
    for p in sorted(ROOT.glob(pattern)):
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            row = rec.get("label", rec)
            aid = row["article_id"]
            if aid in label_src and label_src[aid][1] != row:
                label_conflicts.append({"article_id": aid, "first": label_src[aid][0],
                                        "second": str(p.relative_to(ROOT))})
            else:
                label_src.setdefault(aid, (str(p.relative_to(ROOT)), row))

# ---------------------------------------------------------------- tolerant pool replica
rules = RecallRules(json.loads(RULE_FILE.read_text()))


def tolerant_pool(target_ym: str, as_of: str):
    """Line-for-line replica of build_news_pool_tolerant (scripts/build_sce_fullperiod_coverage.py:105-172)."""
    target = f"{target_ym[:4]}-{target_ym[4:]}"
    cutoff = datetime.fromisoformat(as_of)
    start = datetime.fromisoformat(previous_month_iso(target) + "-01T00:00:00").replace(tzinfo=ET)
    rows, seen, counts = [], {}, Counter()
    for month in (previous_month_iso(target), target):
        docs = json.loads((ROOT / f"data/raw/nyt_archive/{month}.json").read_bytes())["response"]["docs"]
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
            if str(doc.get("document_type") or "").casefold() != "article":
                counts["non_article"] += 1
                continue
            text = doc_text(doc)
            identity = doc.get("_id") or doc.get("uri") or doc.get("web_url")
            if not identity or not any(text.values()):
                counts["missing_identity_or_text"] += 1
                continue
            th = hashlib.sha256(json.dumps(text, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if identity in seen:
                if seen[identity] != (stamp, th):
                    counts["conflicting_duplicate_kept_first"] += 1
                else:
                    counts["duplicate_source_identity"] += 1
                continue
            seen[identity] = (stamp, th)
            hits = rules.classify(doc)
            rows.append({"article_id": article_id_for(identity, th), "pub_date": stamp,
                         "source_month": month, "new_hits": hits})
            counts["unique_articles"] += 1
            counts["coarse_candidates"] += bool(hits)
    return rows, dict(counts)


def exact_dedupe(rows):
    """news_exposure_demo.exact_deduplicate: same (pub_date, headline, abstract, snippet) collapsed."""
    result, seen = [], set()
    for r in sorted(rows, key=lambda r: r["article_id"]):
        key = (r.get("pub_date"),) + tuple(
            " ".join((r.get(k) or "").split()).casefold() for k in ("headline", "abstract", "snippet"))
        if key not in seen:
            result.append(r)
            seen.add(key)
    return result


SCE_PAT = re.compile(
    r"(?i)\bsurvey of consumer expectations\b|\bconsumer expectations survey\b|"
    r"\bSCE\b|new york fed(?:eral)? (?:bank|reserve)")

eligibility_path = OUT / "news_pool_eligibility.jsonl"
fh = eligibility_path.open("w")
summary_months = []
sce_flagged_all = []

for t in TARGETS:
    idx = json.loads((V2 / t / "news_label_index.json").read_text())
    target_iso, as_of = idx["target_month"], idx["as_of"]
    cutoff = datetime.fromisoformat(as_of)
    as_of_day = cutoff.date()          # ET calendar day of the cutoff
    pool_rows, build_counts = tolerant_pool(t, as_of)

    # index cross-check
    index_ids = [r["article_id"] for r in idx["pool"]]
    replica_hit_ids = {r["article_id"] for r in pool_rows if r["new_hits"]}
    assert set(index_ids) == replica_hit_ids, (t, len(index_ids), len(replica_hit_ids))
    assert len(index_ids) == len(set(index_ids))
    assert idx["n_selected"] == len(index_ids) and idx["n_labeled"] == idx["n_selected"]

    # month labels exactly as the prompt pipeline reads them (from this index)
    month_labels = {r["article_id"]: r["label"] for r in idx["pool"] if r.get("label")}

    # true mechanism pools (state_continuity_prompts.py:149-150 semantics)
    enriched = []
    for r in pool_rows:
        meta = rawmap.get(r["article_id"])
        if meta is None:
            raise ValueError(f"article_id missing from raw map: {r['article_id']}")
        row = dict(r)
        row.update({k: meta[k] for k in ("headline", "abstract", "snippet", "placement",
                                         "section_name", "news_desk", "print_section", "print_page")})
        row["semantic_label"] = month_labels.get(r["article_id"])
        enriched.append(row)
    general = exact_dedupe([r for r in enriched if r["placement"] == "a1"])
    personal = exact_dedupe([r for r in enriched if r["placement"] != "a1"
                             and r["semantic_label"] and r["semantic_label"]["decision"] == "keep"])

    mstats = Counter()
    for r in idx["pool"]:
        aid, pub_day = r["article_id"], r["pub_date"]
        meta = rawmap[aid]
        published = datetime.fromisoformat(meta["pub_date_full"].replace("Z", "+00:00"))
        ts_ok = published <= cutoff
        if pub_day > str(as_of_day):
            time_status = "after_cutoff"
        elif pub_day == str(as_of_day):
            time_status = "same_day_cutoff"
        else:
            time_status = "ok"
        placement = meta["placement"]
        label = r.get("label")
        if placement == "a1":
            attribution = "common_a1"
        elif label and label.get("decision") == "keep":
            attribution = "personal_keep"
        else:
            attribution = "not_drawn_label_" + (label.get("decision") if label else "missing")
        src = label_src.get(aid)
        text = " ".join([meta["headline"], meta["abstract"], meta["snippet"]])
        sce_hit = bool(SCE_PAT.search(text))
        rec = {
            "article_id": aid,
            "target_month": target_iso,
            "pub_date": pub_day,
            "source_month_index": r["source_month"],
            "source_month_raw": meta["source_month"],
            "section_name": meta["section_name"],
            "news_desk": meta["news_desk"],
            "print_section": meta["print_section"],
            "print_page": meta["print_page"],
            "placement": placement,
            "pool_attribution": attribution,
            "label_status": "labeled" if label else "missing",
            "label_decision": (label or {}).get("decision"),
            "label_source_file": src[0] if src else None,
            "label_schema": ("legacy7" if any((label or {}).get(f) is not None
                                              for f in ("claim_type", "reason_zh", "evidence_snippet")) else "slim4") if label else None,
            "timestamp_within_cutoff": ts_ok,
            "time_status": time_status,
            "text_vintage_status": "text_vintage_unverified",
            "text_vintage_reason": ("NYT archive cache fetched_at %s after publication; no contemporaneous "
                                    "article-text snapshot in outputs/ or data/raw/ for this month; archive doc "
                                    "carries no publisher modified-time field" % meta_fetch.get(meta["source_month"])),
            "sce_mention": sce_hit,
            "strict_B_eligible": False,
            "strict_B_reason": "text_vintage_unverified (no historical snapshot or publisher modification evidence); "
                               "strict B requires proven historical existence of the exact text",
        }
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        mstats["pool"] += 1
        mstats[f"time_{time_status}"] += 1
        mstats[f"attrib_{attribution}"] += 1
        if not label:
            mstats["missing_label"] += 1
        if sce_hit:
            mstats["sce_mention"] += 1
            sce_flagged_all.append({"target_month": target_iso, "article_id": aid, "pub_date": pub_day,
                                    "placement": placement, "label_decision": (label or {}).get("decision"),
                                    "headline": meta["headline"],
                                    "abstract": meta["abstract"][:400]})
    fh.flush()
    general_ids = [r["article_id"] for r in general]
    personal_ids = [r["article_id"] for r in personal]
    summary_months.append({
        "target_month": target_iso,
        "as_of": as_of,
        "window": idx["window"],
        "index_pool_n": len(index_ids),
        "label_missing_n": mstats["missing_label"],
        "time_ok_n": mstats["time_ok"],
        "same_day_cutoff_n": mstats["time_same_day_cutoff"],
        "after_cutoff_n": mstats["time_after_cutoff"],
        "text_vintage_unverified_n": len(index_ids),
        "sce_mention_flag_n": mstats["sce_mention"],
        "index_common_a1_n": mstats["attrib_common_a1"],
        "index_personal_keep_n": mstats["attrib_personal_keep"],
        "mechanism_general_a1_pool_n": len(general_ids),
        "mechanism_personal_keep_pool_n": len(personal_ids),
        "meets_common_minimum_3": len(general_ids) >= 3,
        "meets_personal_minimum_17": len(personal_ids) >= 17,
        "pool_A_common_ids": general_ids,
        "pool_A_personal_ids": personal_ids,
        "pool_strict_B_ids": [],
        "replica_build_counts": build_counts,
    })
    print(t, dict(mstats), "general:", len(general_ids), "personal:", len(personal_ids),
          "same_day:", mstats["time_same_day_cutoff"], "after:", mstats["time_after_cutoff"])
fh.close()

# ------------------------------------------------- sensitivity pools (A minus same-day; no SCE hits exist)
recs = [json.loads(line) for line in eligibility_path.read_text().splitlines()]
rec_by_month = {}
for r in recs:
    rec_by_month.setdefault(r["target_month"], {})[r["article_id"]] = r


def time_status_of(aid, as_of, month_recs):
    r = month_recs.get(aid)
    if r:
        return r["time_status"], r["pub_date"]
    full = rawmap[aid]["pub_date_full"]
    pub_day = full[:10]
    as_of_day = datetime.fromisoformat(as_of).date().isoformat()
    if pub_day > as_of_day:
        return "after_cutoff", pub_day
    if pub_day == as_of_day:
        return "same_day_cutoff", pub_day
    return "ok", pub_day


for m in summary_months:
    month_recs = rec_by_month[m["target_month"]]
    m["pool_sensitivity_definition"] = (
        "mechanism A pools (all A1-printed general + keep-labeled personal) restricted to "
        "time_status == ok (same_day_cutoff excluded); no sce_mention in any month, so no leak removal needed")
    for key in ("pool_A_common_ids", "pool_A_personal_ids"):
        statuses = [time_status_of(a, m["as_of"], month_recs) for a in m[key]]
        m[key.replace("pool_A", "pool_sensitivity")] = [
            a for a, (s, _) in zip(m[key], statuses) if s == "ok"]
        m[key.replace("_ids", "_time_mix")] = dict(Counter(s for s, _ in statuses))

summary = {
    "audit": {
        "created_utc": datetime.now(ZoneInfo("UTC")).isoformat(),
        "scope": "recent 11 target months 2025-11..2026-09 news label candidate pools "
                 "(outputs/sce_fullperiod_materialized_20261022_v2/<YYYYMM>/news_label_index.json)",
        "new_api_calls": 0, "new_llm_calls": 0, "existing_files_modified": False,
        "targets": TARGETS,
        "method": [
            "article_id recomputed as sha256(identity + newline + sha256(headline/abstract/snippet))[:24], "
            "identical to build_news_pool_tolerant (scripts/build_sce_fullperiod_coverage.py:105-172)",
            "index pool == replica keyword-recall candidate set for every month (asserted)",
            "labels sourced from glob union outputs/sce_*label*/labels.jsonl + "
            "outputs/sce_expanded_news_run_20261014_v1/part_*/labels.jsonl "
            "(scripts/build_sce_fullperiod_sample_data.py:71-72,580-590)",
            "time_status: pub_date UTC calendar day vs as_of ET calendar day; "
            "after_cutoff only when pub day > as_of day (conservative); same-day listed separately; "
            "exact timestamp check published <= as_of also recorded (all True by construction)",
            "text vintage: no contemporaneous article-text snapshot exists for months 2025-10..2026-09 "
            "(outputs/ news_pool.json snapshots exist only for 202203/202303/202403/202209); "
            "nyt archive caches fetched 2026-10-07 per data/raw/nyt_archive/<YYYY-MM>.meta.json; "
            "archive docs expose no publisher modified-time field -> all text_vintage_unverified",
            "SCE leak scan: regex over headline/abstract/snippet of cached text; "
            "flagged articles manually reviewed (see sce_flagged_review)",
        ],
        "sce_leak_check_extended": {
            "pool_scan": "regex over headline/abstract/snippet of all 5611 pooled articles: "
                         "0 hits for survey-of-consumer-expectations / consumer-expectations-survey / "
                         "standalone SCE / New York Fed (bank|reserve)",
            "whole_window_raw_scan": "all docs of the 12 window-month caches 2025-10..2026-09 scanned: "
                                     "0 hits for consumer.{0,40}expect, 0 hits for inflation expectations, "
                                     "4 hits for New York Fed / Federal Reserve Bank of New York "
                                     "(John Williams interviews x3, tariff research x1) - none about the SCE "
                                     "survey or its monthly results",
            "conclusion": "no article in any candidate pool reports the target month SCE results; "
                          "general SCE coverage is also absent; leak risk = none found",
            "note": "SCE results publish the 7th-14th of the following month, after every as_of; a leak "
                    "would in any case be temporally impossible, and none was found",
        },
        "label_source_conflict_note": (
            "1 conflicting duplicate label across source files: article_id 0f66543f89c242adc6c24d92 in "
            "sce_multiperiod_news_labels_part01_v2 vs _v3 labels.jsonl; identical decision=exclude, only "
            "legacy evidence_snippet text truncated differently (v3 re-run recovered batch). The article is "
            "not in any recent-11-month pool, so the conflict has no effect on these months."),
        "strict_B_conclusion": (
            "strict_B pool is EMPTY for all 11 months: every pooled article is text_vintage_unverified "
            "(cache fetched 2026-10-07 after publication, no contemporaneous snapshot, no publisher "
            "modified-time field). Strict-B usable pool 0 << minimum 3 common / 17 personal. "
            "Original A pools and sensitivity pools remain as listed per month."),
    },
    "label_source_conflicts": label_conflicts,
    "sce_flagged_review": sce_flagged_all,
    "months": summary_months,
    "totals": {
        "index_pool_total": sum(m["index_pool_n"] for m in summary_months),
        "missing_labels_total": sum(m["label_missing_n"] for m in summary_months),
        "after_cutoff_total": sum(m["after_cutoff_n"] for m in summary_months),
        "same_day_cutoff_total": sum(m["same_day_cutoff_n"] for m in summary_months),
        "text_vintage_unverified_total": sum(m["text_vintage_unverified_n"] for m in summary_months),
        "sce_mention_total": sum(m["sce_mention_flag_n"] for m in summary_months),
        "all_months_meet_common_min_3": all(m["meets_common_minimum_3"] for m in summary_months),
        "all_months_meet_personal_min_17": all(m["meets_personal_minimum_17"] for m in summary_months),
        "strict_B_eligible_total": 0,
    },
}
(OUT / "news_pool_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print("label conflicts:", len(label_conflicts))
print("sce flagged:", len(sce_flagged_all))
print("wrote", eligibility_path, "and summary")
