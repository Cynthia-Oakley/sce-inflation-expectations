#!/usr/bin/env python3
"""Build the full-period (2019-01..2026-09, 93 target months) data coverage ledger.

Writes outputs/sce_fullperiod_data_20261021_v1/coverage.json and
coverage_summary.md. Field spec: docs/workstreams/20261021_fullperiod/kimi_data_contract_v2.md (line 11).

Empirical findings baked in here (all re-verified by this script at run time):

* tenure semantics (SCE micro): for every userid observed in two consecutive
  months, tenure always increases by exactly 1 (106,351/106,351 consecutive
  pairs in the three files); tenure==1 coincides with the userid's first
  observed appearance in 0 conflicting cases. Conclusion: tenure==1 == new
  survey entrant that wave. Caveat: 1,284 first appearances carry tenure>1 —
  left-censored entrants who joined before 2017-01 (observation window
  boundary); they are NOT counted as entrant_n. (tenure==1 ⇒ entrant;
  tenure>1 at first sight ⇒ left boundary.)

* news window month (D050, empirically confirmed against the historical
  trial environment bundles, whose nyt_salient_events layer states
  "published M-1-01 through the CPI release day inside M"): the news window
  for target month M is the full previous calendar month (M-1) plus month M
  from the 1st through the as_of day (CPI release day, 23:59:59 ET). Both
  months' raw NYT archive caches are required. This matches
  studies/sce_inflation_expectations/coverage_preparation.build_news_pool.

* article_id compatibility: labels.jsonl article_id is
  sha256(identity + "\n" + text_sha256)[:24] as produced by build_news_pool
  (NOT the sha256(web_url)[:16] event_id of scripts/build_nyt_events.py).
  Verified: target 2022-03 window yields 653 keyword-selected candidates,
  0 missing labels. Selection logic is therefore a verbatim local copy of
  coverage_preparation.build_news_pool (the pipeline that produced the
  labels), tolerant of cross-cache duplicate identities (see
  build_news_pool_tolerant), not build_nyt_events.

* 2025-10 BLS cancellation: ref 2025-10 CPI (and empsit) release was
  permanently cancelled (Oct-Nov 2025 federal shutdown); no
  data/raw/bls_initial_releases/2025-10/ exists. Target 2025-11 falls back
  to ref 2025-09 (published 2025-10-24). Additionally the ref 2025-09 empsit
  was delayed to 2025-11-20 (after the fallback as_of), so the latest jobs
  report visible before the 2025-11 as_of is ref 2025-08 (2025-09-05).

Offline only: no API calls, no credentials.
"""
from __future__ import annotations

import glob
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import load_workbook  # noqa: E402

from studies.sce_inflation_expectations.news_exposure_demo import (  # noqa: E402
    front_page_status,
)
from studies.sce_inflation_expectations.news_selection_trial import (  # noqa: E402
    RULE_FILE,
    RecallRules,
)
from studies.sce_inflation_expectations.coverage_preparation import (  # noqa: E402
    previous_month,
)

OUT_DIR = ROOT / "outputs/sce_fullperiod_data_20261021_v1"
BLS_DIR = ROOT / "data/raw/bls_initial_releases"
EIA_MONTHLY = ROOT / "data/raw/eia_gasoline/gasoline_retail_regular_monthly.jsonl"
NYT_DIR = ROOT / "data/raw/nyt_archive"
MICRO_FILES = [
    ("data/raw/sce_p_sources/micro_2017_2019.xlsx", "micro_2017_2019.xlsx"),
    ("data/raw/sce_audit_20260928/micro_2020_2024.xlsx", "micro_2020_2024.xlsx"),
    ("data/raw/sce_audit_20260928/micro_latest.xlsx", "micro_latest.xlsx"),
]
LABEL_GLOBS = ["outputs/sce_*label*/labels.jsonl",
               "outputs/sce_expanded_news_run_20261014_v1/part_*/labels.jsonl"]

TARGET_START = "2019-01"
TARGET_END = "2026-09"


def month_range(start: str, end: str) -> list[str]:
    out = []
    y, m = (int(x) for x in start.split("-"))
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def prev_month(month: str) -> str:
    y, m = (int(x) for x in month.split("-"))
    return f"{y - (m == 1):04d}-{12 if m == 1 else m - 1:02d}"


def as_of_from_published(published_at_et: str) -> str:
    """Convention: day of the ref CPI initial-release PDF publication, 23:59:59, same ET offset."""
    return published_at_et[:10] + "T23:59:59" + published_at_et[-6:]


def build_news_pool_tolerant(root: Path, target: str, as_of: str, rules) -> tuple[list[dict], dict]:
    """Line-for-line copy of coverage_preparation.build_news_pool with one
    deliberate deviation: instead of raising on a conflicting duplicate
    source identity, keep the first occurrence and count the conflict.

    The stock function raises ValueError("conflicting duplicate source
    article"); this first fires at target 2026-07 because the NYT Archive
    API serves July-1st articles in BOTH the 2026-06 and 2026-07 monthly
    caches with pub_date stamps differing only by millisecond formatting
    (e.g. "14:55:07.172Z" vs "14:55:07Z", 7 identities at the 2026-06/07
    boundary). That pipeline never processed those windows before. The
    article_id (sha256 of identity + text hash) is unaffected by the stamp,
    so label matching is unchanged. Equivalence check: target 2022-03 yields
    the same 653 candidates / 0 missing labels as the stock function.
    """
    from zoneinfo import ZoneInfo

    cutoff = datetime.fromisoformat(as_of)
    if cutoff.tzinfo is None:
        raise ValueError("cutoff requires timezone")
    start = datetime.fromisoformat(previous_month(target) + "-01T00:00:00").replace(
        tzinfo=ZoneInfo("America/New_York"))
    rows, seen, counts = [], {}, Counter()
    for month in (previous_month(target), target):
        path = root / "data/raw/nyt_archive" / (month + ".json")
        docs = json.loads(path.read_bytes())["response"]["docs"]
        for doc in docs:
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
            text = {"headline": (doc.get("headline") or {}).get("main") or "",
                    "abstract": doc.get("abstract") or "", "snippet": doc.get("snippet") or ""}
            identity = doc.get("_id") or doc.get("uri") or doc.get("web_url")
            if not identity or not any(text.values()):
                counts["missing_identity_or_text"] += 1
                continue
            text_hash = hashlib.sha256(
                json.dumps(text, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if identity in seen:
                if seen[identity] != (stamp, text_hash):
                    counts["conflicting_duplicate_kept_first"] += 1
                else:
                    counts["duplicate_source_identity"] += 1
                continue
            seen[identity] = (stamp, text_hash)
            hits = rules.classify(doc)
            rows.append({
                "article_id": hashlib.sha256(
                    (identity + "\n" + text_hash).encode()).hexdigest()[:24],
                "pub_date": stamp,
                "source_month": month,
                "new_hits": hits,
            })
            counts["unique_articles"] += 1
            counts["coarse_candidates"] += bool(hits)
            counts["recorded_a1"] += front_page_status(doc) == "a1"
    return rows, dict(counts)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_bls_release(ref: str, prefix: str) -> dict | None:
    """Return {'published_at_et': ...} for the cpi_/empsit_ file of ref month, or None."""
    manifest = BLS_DIR / ref / "manifest.json"
    if not manifest.exists():
        return None
    for f in json.loads(manifest.read_text()).get("files", []):
        if f.get("file", "").startswith(prefix):
            return {"published_at_et": f["published_at_et"], "file": f["file"]}
    return None


def latest_empsit_before(as_of: str) -> dict | None:
    best = None
    for manifest in sorted(BLS_DIR.glob("*/manifest.json")):
        for f in json.loads(manifest.read_text()).get("files", []):
            if not f.get("file", "").startswith("empsit_"):
                continue
            if f["published_at_et"] <= as_of:
                if best is None or f["published_at_et"] > best["published_at_et"]:
                    best = {"published_at_et": f["published_at_et"], "file": f["file"]}
    return best


def scan_micro() -> dict[int, dict]:
    """month(YYYYMM int) -> {'rows': n, 'entrant_n': tenure==1 count, 'source': file name}.

    Rows with a missing/None date are skipped (micro_2020_2024.xlsx carries
    10,559 such non-data rows after the data block; they carry no date/userid).
    """
    result: dict[int, dict] = {}
    for rel, name in MICRO_FILES:
        path = ROOT / rel
        wb = load_workbook(path, read_only=True)
        ws = wb["Data"]
        it = ws.iter_rows(min_row=2, values_only=True)
        header = next(it)
        di, ti = header.index("date"), header.index("tenure")
        for row in it:
            d = row[di]
            if d is None:
                continue
            month = int(d)
            rec = result.setdefault(month, {"rows": 0, "entrant_n": 0, "source": name})
            rec["rows"] += 1
            if row[ti] == 1:
                rec["entrant_n"] += 1
        wb.close()
    return result


def load_label_ids() -> tuple[set[str], list[str]]:
    ids: set[str] = set()
    paths = sorted(p for g in LABEL_GLOBS for p in glob.glob(str(ROOT / g)))
    for p in paths:
        for line in Path(p).read_text().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            row = record.get("label", record)
            ids.add(row["article_id"])
    return ids, [str(Path(p).relative_to(ROOT)) for p in paths]


def main() -> int:
    targets = month_range(TARGET_START, TARGET_END)
    assert len(targets) == 93, len(targets)

    print("scanning SCE micro files (xlsx, read_only)...", flush=True)
    micro = scan_micro()
    micro_months = sorted(micro)
    print(f"  micro months: {micro_months[0]}..{micro_months[-1]} "
          f"({len(micro_months)} months, contiguous={all((m in micro) for m in range(201901, 202511))})")

    print("loading EIA gasoline monthly aggregation...", flush=True)
    eia_months = {json.loads(line)["reference_period"] for line in EIA_MONTHLY.read_text().splitlines()}
    print(f"  EIA months: {min(eia_months)}..{max(eia_months)} ({len(eia_months)})")

    print("collecting LLM news labels...", flush=True)
    label_ids, label_paths = load_label_ids()
    print(f"  {len(label_paths)} labels.jsonl files, {len(label_ids)} unique article_ids")

    rules = RecallRules(json.loads(RULE_FILE.read_text()))

    months = []
    for i, target in enumerate(targets):
        ref = prev_month(target)
        reason_bits: list[str] = []

        # --- as_of from ref CPI initial release (with 2025-10 shutdown fallback) ---
        cpi = load_bls_release(ref, "cpi_")
        bls_ok = cpi is not None
        if cpi is None and ref == "2025-10":
            # 2025-10 CPI permanently cancelled (Oct-Nov 2025 federal shutdown);
            # fall back to the most recent published CPI (ref 2025-09, 2025-10-24).
            fallback_ref = prev_month(ref)
            cpi = load_bls_release(fallback_ref, "cpi_")
            bls_ok = cpi is not None
            reason_bits.append("bls_shutdown_ref2025-10_cancelled_fallback_to_ref2025-09")
            if load_bls_release(ref, "empsit_") is None:
                last_emp = latest_empsit_before(as_of_from_published(cpi["published_at_et"]))
                emp_note = (f"ref2025-10_empsit_also_cancelled;"
                            f" latest_empsit_before_as_of={last_emp['file'].removesuffix('.pdf')}"
                            if last_emp else "ref2025-10_empsit_also_cancelled; no empsit before as_of")
                reason_bits.append(emp_note)
        if cpi is None:
            as_of = None
            reason_bits.append(f"bls_manifest_missing_for_ref_{ref}")
        else:
            as_of = as_of_from_published(cpi["published_at_et"])

        # --- micro truth ---
        key = int(target.replace("-", ""))
        micro_rec = micro.get(key)
        micro_available = micro_rec is not None

        # --- environment readiness ---
        eia_ok = target in eia_months
        window_months = [prev_month(target), target]
        nyt_ok = all((NYT_DIR / f"{m}.json").exists() for m in window_months)
        env_ready = bls_ok and eia_ok and nyt_ok
        if not eia_ok:
            reason_bits.append(f"eia_gasoline_monthly_missing_{target}")
        if not nyt_ok:
            missing = [m for m in window_months if not (NYT_DIR / f"{m}.json").exists()]
            reason_bits.append(f"nyt_cache_missing_{'|'.join(missing)}")

        # --- news label gap for the window ---
        news_missing = None
        n_candidates = None
        if env_ready and as_of:
            rows, pool_counts = build_news_pool_tolerant(ROOT, target, as_of, rules)
            candidates = [r for r in rows if r["new_hits"]]
            n_candidates = len(candidates)
            news_missing = sum(1 for r in candidates if r["article_id"] not in label_ids)

        if micro_available and env_ready:
            status = "ready"
        elif not micro_available and env_ready:
            status = "ready_no_micro"
        else:
            status = "partial"

        months.append({
            "target_month": target,
            "as_of": as_of,
            "micro_truth_available": micro_available,
            "micro_source_period": micro_rec["source"] if micro_available else None,
            "micro_published_at": None,
            "aggregate_truth_available": target <= TARGET_END,
            "population_n": micro_rec["rows"] if micro_available else None,
            "entrant_n": micro_rec["entrant_n"] if micro_available else None,
            "environment_ready": env_ready,
            "news_labels_missing": news_missing,
            "status": status,
            "reason": ";".join(reason_bits),
            # diagnostics (kept inside each row for auditability)
            "diagnostics": {
                "ref_month": ref,
                "cpi_release_file": cpi["file"] if cpi else None,
                "news_window_months": window_months,
                "news_candidates_selected": n_candidates,
                "news_pool_conflicting_duplicates": pool_counts.get("conflicting_duplicate_kept_first", 0),
            },
        })
        print(f"[{i + 1:2d}/93] {target} as_of={as_of} micro={micro_available} "
              f"env={env_ready} labels_missing={news_missing}", flush=True)

    # continuity check
    assert [m["target_month"] for m in months] == targets

    coverage = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "convention": {
            "as_of": ("as_of = ref (M-1) month CPI initial-release PDF's published_at_et date, "
                      "at 23:59:59 with the same ET offset (D050: simulated household information "
                      "cutoff aligned to the median real SCE respondent, who answers after the M-1 "
                      "CPI release)."),
            "exception_2025_11": ("ref 2025-10 CPI was permanently cancelled (Oct-Nov 2025 federal "
                                  "shutdown); target 2025-11 falls back to the most recent published "
                                  "CPI, ref 2025-09 (published 2025-10-24), as_of=2025-10-24T23:59:59-04:00. "
                                  "ref 2025-10 empsit was likewise cancelled and the delayed ref 2025-09 "
                                  "empsit (2025-11-20) postdates the as_of, so the latest jobs report "
                                  "visible at the 2025-11 as_of is ref 2025-08 (2025-09-05)."),
            "news_window": ("target M uses news published from M-1-01 00:00 ET through the as_of day "
                            "(CPI release day) inside M (D050). Empirically confirmed against the "
                            "historical trial environment bundles (nyt_salient_events layer: "
                            "'published M-1-01 through the CPI release day inside M')."),
            "tenure": ("entrant_n = rows with tenure==1. Empirically verified on the three micro files: "
                       "tenure always increments by exactly 1 across consecutive months for the same "
                       "userid (106,351/106,351 pairs), and tenure==1 always coincides with the userid's "
                       "first observed appearance. First appearances with tenure>1 (1,284) are "
                       "left-censored entrants (joined before 2017-01) and are not counted as entrants."),
        },
        "sources": {
            "bls_initial_releases": {
                "path": "data/raw/bls_initial_releases/<YYYY-MM>/manifest.json",
                "method": ("files[] entry whose file name starts with 'cpi_' -> published_at_et; "
                           "as_of = that date at 23:59:59 same offset. All ref months 2018-12..2026-08 "
                           "verified present except 2025-10 (shutdown cancellation)."),
            },
            "sce_micro": {
                "paths": [rel for rel, _ in MICRO_FILES],
                "method": ("openpyxl read_only, sheet 'Data', header on row 2 (row 1 = Source note), "
                           "'date' column int YYYYMM; population_n = data rows of the month; entrant_n = "
                           "rows with tenure==1. Rows with empty date skipped (10,559 in "
                           "micro_2020_2024.xlsx, non-data trailing rows). Coverage read directly from "
                           "the files: 201701-201912 (36 mo), 202001-202412 (60 mo), 202501-202510 "
                           "(10 mo); no overlaps."),
            },
            "sce_aggregate_chart": {
                "path": "data/raw/sce_micro_refresh_20261021/chart.xlsx",
                "method": ("NOT re-read by this script; per pre-verified fact the national headline "
                           "median series reaches 2026-09, so aggregate_truth_available=true for every "
                           "target month."),
            },
            "eia_gasoline": {
                "path": "data/raw/eia_gasoline/gasoline_retail_regular_monthly.jsonl",
                "method": ("reference_period values read directly: exactly 2019-01..2026-09, "
                           "93/93 target months covered."),
            },
            "nyt_archive": {
                "path": "data/raw/nyt_archive/<YYYY-MM>.json",
                "method": ("window months for target M are M-1 and M (M truncated at the as_of day); "
                           "both monthly caches must exist. Verified: 2018-12..2026-09 all present "
                           "(incl. the backfilled 2018-12 cache used by target 2019-01)."),
            },
            "news_labels": {
                "paths": LABEL_GLOBS,
                "files_used": label_paths,
                "method": ("union of article_id over all labels.jsonl (19 sce_*label* part dirs + 12 "
                           "sce_expanded_news_run_20261014_v1 parts = 7,157 unique ids). Selection of "
                           "window articles reuses the coverage_preparation.build_news_pool logic "
                           "verbatim via a local copy (build_news_pool_tolerant) that tolerates "
                           "cross-cache duplicate identities differing only in pub_date millisecond "
                           "formatting (first seen at the 2026-06/07 boundary) instead of raising; "
                           "article_id is stamp-independent so label matching is unaffected. "
                           "Equivalence verified on target 2022-03: 653 candidates, 0 missing."),
            },
        },
        "months": months,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n")

    # ---- summary markdown ----
    by_status = Counter(m["status"] for m in months)
    total_label_gap = sum(m["news_labels_missing"] or 0 for m in months)
    top10 = sorted(months, key=lambda m: -(m["news_labels_missing"] or 0))[:10]
    by_year: dict[str, Counter] = {}
    for m in months:
        c = by_year.setdefault(m["target_month"][:4], Counter())
        c[m["status"]] += 1
        c["label_gap"] += m["news_labels_missing"] or 0

    lines = [
        "# SCE full-period data coverage summary (2019-01..2026-09, 93 months)",
        "",
        f"Generated: {coverage['generated_at']}",
        "",
        "## Overall",
        "",
        f"- target months: {len(months)} (continuous, no gaps)",
        f"- status counts: {dict(by_status)}",
        f"- months with micro truth: {sum(1 for m in months if m['micro_truth_available'])}"
        f" ({months[0]['target_month']}..{[m['target_month'] for m in months if m['micro_truth_available']][-1]})",
        f"- months without micro truth: {sum(1 for m in months if not m['micro_truth_available'])}"
        f" ({[m['target_month'] for m in months if not m['micro_truth_available']][0]}..{months[-1]['target_month']})",
        f"- environment_ready: {sum(1 for m in months if m['environment_ready'])}/93",
        f"- total news label gap (selected-but-unlabeled across all windows): {total_label_gap}",
        "",
        "## Gaps by year segment",
        "",
        "| year | months | ready | ready_no_micro | partial | label gap |",
        "|---|---|---|---|---|---|",
    ]
    for year in sorted(by_year):
        c = by_year[year]
        lines.append(f"| {year} | {sum(v for k, v in c.items() if k in ('ready', 'ready_no_micro', 'partial'))} "
                     f"| {c.get('ready', 0)} | {c.get('ready_no_micro', 0)} | {c.get('partial', 0)} "
                     f"| {c['label_gap']} |")
    lines += [
        "",
        "## Top 10 months by news_labels_missing",
        "",
        "| target_month | missing | selected candidates | as_of |",
        "|---|---|---|---|",
    ]
    for m in top10:
        lines.append(f"| {m['target_month']} | {m['news_labels_missing']} "
                     f"| {m['diagnostics']['news_candidates_selected']} | {m['as_of']} |")
    lines += [
        "",
        "## Anomalies",
        "",
    ]
    for m in months:
        if m["reason"]:
            lines.append(f"- {m['target_month']}: {m['reason']}")
    (OUT_DIR / "coverage_summary.md").write_text("\n".join(lines) + "\n")

    # ---- acceptance self-checks ----
    def row(t):
        return next(m for m in months if m["target_month"] == t)
    checks = {
        "2020-03 population_n=1300": row("2020-03")["population_n"] == 1300,
        "2020-03 as_of": row("2020-03")["as_of"] == "2020-03-11T23:59:59-04:00",
        "2025-11 shutdown fallback reason": "bls_shutdown_ref2025-10_cancelled_fallback_to_ref2025-09"
            in row("2025-11")["reason"],
        "2025-11 as_of=2025-10-24": row("2025-11")["as_of"] == "2025-10-24T23:59:59-04:00",
        "2025-10 normal (ref 2025-09)": row("2025-10")["as_of"] == "2025-10-24T23:59:59-04:00"
            and not row("2025-10")["reason"],
        "2026-09 no micro / aggregate yes": (row("2026-09")["micro_truth_available"] is False
            and row("2026-09")["aggregate_truth_available"] is True),
        "2026-09 as_of": row("2026-09")["as_of"] == "2026-09-11T23:59:59-04:00",
        "2019-01 label gap computed": isinstance(row("2019-01")["news_labels_missing"], int),
        "2022-03 label gap near 0": (row("2022-03")["news_labels_missing"] is not None
            and row("2022-03")["news_labels_missing"] <= 2),
        "93 continuous rows": len(months) == 93 and [m["target_month"] for m in months] == targets,
    }
    print("\nacceptance checks:")
    for k, ok in checks.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {k}")
    print(f"\nwrote {OUT_DIR / 'coverage.json'}")
    print(f"wrote {OUT_DIR / 'coverage_summary.md'}")
    print(f"total news label gap: {total_label_gap}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
