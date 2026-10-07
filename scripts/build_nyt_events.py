#!/usr/bin/env python3
"""Build the NYT salient-event ledger (E v2 event layer, D049d).

Pulls the NYT Archive API month by month (metadata only: headline, abstract,
placement), caches each month's raw response, and selects events a household
plausibly noticed. Keywords are matched on headline + abstract + snippet in
two strengths:

  strong = price/macro-specific (inflation, gasoline, supply chain, tariff…)
  broad  = pandemic/reopening context (covid, vaccine, shutdown, reopen…)

Selection tiers, in priority order:

  front_page+strong  print A1 ∧ strong keyword
  strong_keyword     strong keyword anywhere (front page not required)
  front_page+broad   print A1 ∧ only broad keywords
  front_page         print A1, no keyword (general editorial salience,
                     the same proxy ConsumerSim used)

A broad-only hit away from the front page is NOT selected — that rule is
what keeps Covid human-interest noise out of the ledger.

The top tier (front_page+strong) is NEVER capped: every A1 article that hits
a strong keyword is kept (user 2026-10-04). Lower tiers fill the remaining
budget up to --max-per-month (default 30; the observed top-tier maximum over
2020-10..2021-12 is 19). Within a lower tier, articles with more distinct
matched keywords win the budget (hit density as a relevance proxy, user
2026-10-04), recency breaks ties; final output is chronological.

Selection is deliberately inclusive at the strong tier (user 2026-10-03:
宁宽勿漏, minor noise is acceptable); the ledger keeps headline + abstract
only, sized for short model contexts. Each event records pub_date, tier,
matched keywords, section, page, web_url and the sha256 of the raw monthly
archive it came from.

API key: reads NYT_ARCHIVE_API_KEY from the repo-root .env (never echoed).
Archive API rate limit is 5 req/min; the script sleeps between month fetches.

    python scripts/build_nyt_events.py --months 2020-10..2021-12
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ARCHIVE_URL = "https://api.nytimes.com/svc/archive/v1/{y}/{m}.json?api-key={key}"

# inflation-relevance keywords, case-insensitive word-boundary prefix match
# on headline + abstract + snippet.
# STRONG = price/macro-specific; a strong hit alone (no front page) suffices.
# BROAD = generic macro/pandemic context; only counts together with
# front-page placement (otherwise Covid human-interest and any story that
# mentions "the economy" would qualify).
STRONG_KEYWORDS = [
    # inflation headline terms — verb-attached forms keep the uncapped
    # front-page+strong tier free of metaphorical/static "price" usage;
    # downward-direction forms cover the 2020 deflation scare
    "inflation", "deflation", "consumer price", "price increase",
    "prices rose", "rising prices", "prices fell", "falling prices",
    "price drop", "price cut",
    # energy & oil
    "gasoline", "gas price", "oil price", "crude oil", "opec", "oil market",
    # supply chain & goods
    "supply chain", "supply-chain", "shortage", "shipping", "port of",
    "semiconductor", "chip shortage", "lumber", "used car",
    # commodities & food
    "commodity", "commodities", "grain", "wheat", "soybean",
    "food price", "grocery",
    # housing (2021 boom was central to the inflation narrative)
    "rent", "home price", "housing market", "mortgage",
    # wholesale / upstream pipeline
    "producer price", "wholesale price",
    # trade & tariffs
    "tariff", "trade war",
    # fiscal policy (US transfer form = checks/benefits, not vouchers)
    "stimulus", "stimulus check", "fiscal policy", "relief package",
    "spending bill", "infrastructure bill", "unemployment benefits",
    # labor market & monetary policy
    "jobs report", "jobless", "unemployment", "wage",
    "federal reserve", "interest rate",
    # macro trajectory (specific phrases only; bare "economy" is BROAD)
    "economic rebound", "economic recovery",
]
BROAD_KEYWORDS = [
    "economy",
    "pandemic", "covid", "coronavirus", "vaccine", "delta variant",
    "shutdown", "reopen", "relief check",
]
# Word-boundary prefix match: \b at the start blocks substring false
# positives ("apparently" ~ rent, "Republican" ~ rent, "waging" ~ wage)
# while still allowing natural inflections ("rents", "gas prices").
STRONG_RES = [(kw, re.compile(r"\b" + re.escape(kw), re.I)) for kw in STRONG_KEYWORDS]
BROAD_RES = [(kw, re.compile(r"\b" + re.escape(kw), re.I)) for kw in BROAD_KEYWORDS]

DEFAULT_MONTHS = "2020-10..2021-12"


def parse_months(spec: str) -> list[str]:
    start, end = spec.split("..")
    y, m = (int(x) for x in start.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def load_api_key(env_path: Path) -> str:
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("NYT_ARCHIVE_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    sys.exit(f"NYT_ARCHIVE_API_KEY not found in {env_path}")


def _download(url: str, attempts: int = 4) -> bytes:
    """Retry large downloads; the NYT archive (~10-20MB/month) occasionally
    drops the connection mid-body (http.client.IncompleteRead)."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sce-research/1.0"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError,
                http.client.HTTPException) as e:
            last = e
            if i + 1 < attempts:
                time.sleep(5 * (i + 1))
    raise SystemExit(f"download failed after {attempts} attempts: {last}")


def fetch_month(month: str, api_key: str, cache_dir: Path, refresh: bool) -> dict:
    """Return the raw archive JSON for YYYY-MM, using the cache when present."""
    y, m = month.split("-")
    cache = cache_dir / f"{month}.json"
    meta_path = cache_dir / f"{month}.meta.json"
    if cache.exists() and not refresh:
        return json.loads(cache.read_text(encoding="utf-8"))

    url = ARCHIVE_URL.format(y=int(y), m=int(m), key=api_key)
    payload = _download(url)
    data = json.loads(payload)
    docs = data.get("response", {}).get("docs", [])
    cache.write_bytes(payload)
    meta = {
        "month": month,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_url": f"https://api.nytimes.com/svc/archive/v1/{int(y)}/{int(m)}.json",
        "n_docs": len(docs),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    return data


def classify_doc(doc: dict) -> tuple[str | None, list[str]]:
    """(tier, matched keywords); tier None = not selected.

    Two keyword strengths (matched on headline + abstract + snippet):
    strong hits qualify anywhere in the paper; broad (pandemic/reopening
    context) hits only qualify together with front-page placement —
    otherwise every Covid human-interest story would flood the ledger.
    """
    fp = (str(doc.get("print_section") or "") == "A"
          and str(doc.get("print_page") or "") == "1")
    text = " ".join(filter(None, [
        (doc.get("headline") or {}).get("main", ""),
        doc.get("abstract", ""),
        doc.get("snippet", ""),
    ]))
    strong = [kw for kw, rx in STRONG_RES if rx.search(text)]
    broad = [kw for kw, rx in BROAD_RES if rx.search(text)]
    if fp and strong:
        return "front_page+strong", strong
    if strong:
        return "strong_keyword", strong
    if fp and broad:
        return "front_page+broad", broad
    if fp:
        return "front_page", []
    return None, []


# selection priority: A1 + strong first, then strong anywhere, then
# A1 + broad, then remaining front page (general salience)
_TIER_RANK = {
    "front_page+strong": 0,
    "strong_keyword": 1,
    "front_page+broad": 2,
    "front_page": 3,
}


def select_events(docs: list[dict], month: str, archive_sha: str,
                  max_per_month: int) -> list[dict]:
    events, seen = [], set()
    for doc in docs:
        if str(doc.get("document_type") or "").casefold() != "article":
            continue
        tier, matched = classify_doc(doc)
        if tier is None:
            continue
        url = doc.get("web_url", "")
        if url in seen:
            continue
        seen.add(url)
        events.append({
            "event_id": hashlib.sha256(url.encode()).hexdigest()[:16],
            "pub_date": (doc.get("pub_date") or "")[:10],
            "month": month,
            "tier": tier,
            "matched_keywords": matched,
            "headline": (doc.get("headline") or {}).get("main", ""),
            "abstract": doc.get("abstract", ""),
            "section_name": doc.get("section_name", ""),
            "news_desk": doc.get("news_desk", ""),
            "print_section": str(doc.get("print_section") or ""),
            "print_page": str(doc.get("print_page") or ""),
            "web_url": url,
            "source": "NYT Archive API",
            "archive_sha256": archive_sha,
        })
    # Rank 0 (front_page+strong) is never capped. Lower ranks fill the
    # remaining budget up to max_per_month; within a rank, keyword-dense
    # articles win (more distinct matched keywords = more likely genuinely
    # inflation-relevant, less likely a passing mention), recency breaks
    # ties. Final output is chronological.
    by_rank: dict[int, list[dict]] = {0: [], 1: [], 2: [], 3: []}
    for e in events:
        by_rank[_TIER_RANK[e["tier"]]].append(e)
    selected: list[dict] = sorted(by_rank[0], key=lambda e: e["pub_date"])
    for rank in (1, 2, 3):
        remaining = max_per_month - len(selected)
        if remaining <= 0:
            break
        # within a tier prefer keyword-dense articles (more distinct matched
        # keywords = more likely genuinely inflation-relevant); recency
        # breaks ties (stable sort keeps newest-first within equal hits)
        pool = sorted(by_rank[rank], key=lambda e: e["pub_date"],
                      reverse=True)
        pool = sorted(pool, key=lambda e: -len(e["matched_keywords"]))
        selected.extend(pool[:remaining])
    selected.sort(key=lambda e: e["pub_date"])
    return selected


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--months", default=DEFAULT_MONTHS,
                    help=f"month range YYYY-MM..YYYY-MM (default {DEFAULT_MONTHS})")
    ap.add_argument("--max-per-month", type=int, default=30,
                    help="budget for ranks 1-3; rank 0 (front_page+strong) "
                         "is always kept in full (default 30)")
    ap.add_argument("--sleep", type=float, default=13.0,
                    help="seconds between API calls (archive limit is 5/min)")
    ap.add_argument("--refresh", action="store_true", help="re-fetch cached months")
    ap.add_argument("--cache-dir", type=Path, default=ROOT / "data/raw/nyt_archive")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data/raw/nyt_archive/events_ledger.jsonl")
    args = ap.parse_args(argv)

    api_key = load_api_key(ROOT / ".env")
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    months = parse_months(args.months)

    all_events = []
    for i, month in enumerate(months):
        cache = args.cache_dir / f"{month}.json"
        if i and (not cache.exists() or args.refresh):
            time.sleep(args.sleep)  # stay under 5 req/min
        try:
            data = fetch_month(month, api_key, args.cache_dir, args.refresh)
        except urllib.error.HTTPError as e:
            sys.exit(f"fetch failed for {month}: HTTP {e.code} {e.reason}")
        docs = data.get("response", {}).get("docs", [])
        sha = hashlib.sha256((args.cache_dir / f"{month}.json")
                             .read_bytes()).hexdigest()
        events = select_events(docs, month, sha, args.max_per_month)
        from collections import Counter
        tiers = Counter(e["tier"] for e in events)
        print(f"{month}: {len(docs)} docs -> {len(events)} events "
              f"({dict(tiers)})")
        all_events.extend(events)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for e in all_events:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(f"wrote {len(all_events)} events to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
