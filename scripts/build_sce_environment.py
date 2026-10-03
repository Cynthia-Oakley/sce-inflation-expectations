#!/usr/bin/env python3
"""Materialize the BLS information environment (E) for sce_inflation_expectations.

For every target month t the environment serves the four BLS initial-release
signals that were public by as_of = end of t-1 (America/New_York, 23:59:59):

  1. CPI-U all items 12-month percent change (NSA)
  2. CPI-U all items 1-month percent change (SA)
  3. Civilian unemployment rate (SA)
  4. Total nonfarm payroll employment 1-month change (SA, thousands)

Reference period per protocol is M-2 (target 2021-01 -> reference 2020-11,
whose CPI was released 2020-12-10 and Employment Situation 2020-12-04).

Provenance rules (docs/RESEARCH_PROTOCOL.md):
- Every signal value is transcribed from an actually-retrieved BLS archived
  initial-release PDF (https://www.bls.gov/news.release/archives/{cpi|empsit}_MMDDYYYY.pdf).
- The release date is verified from the document itself: the first page carries
  "Transmission of material in this release is embargoed until 8:30 a.m. (ET)
  <Month D, YYYY>", which must equal the archive URL date. If a candidate date
  404s, nearby candidate dates are probed (CPI: days 8-20 of the release month;
  Employment Situation: weekdays of days 1-12) until the embargo line verifies.
- Retrieval channel: this machine's direct/proxied curl is blocked by Akamai
  (HTTP 403); downloads therefore use httpx with browser-like headers through
  the local proxy (default http://127.0.0.1:7890, override with --proxy or
  HTTPS_PROXY). If the archive is already present the PDF is never re-fetched.
- Each reference period is archived under data/raw/bls_initial_releases/<ref>/
  with a manifest recording URL, SHA-256, retrieval time, USDL id, the verified
  embargo date and, for each transcribed value, the exact source sentence.

Outputs (all schema-validated against socioverse2_repo socioverse.schemas):

- <study>/<out-prefix>.json                     EnvironmentBundle
- <study>/<dir(out-prefix)>/external_events_<stem>.json   external events record
- <study>/simulation/<sim_stem>.json            SimulationConfig

No persona_by_id / audit_dir / run_id is written: those are injected at runtime.
The dev-window environment.json / simulation.json are never touched.

Examples:
    python scripts/build_sce_environment.py \
        --targets 2021-01..2021-12 --fetch \
        --out-prefix environment/environment_main2021
    python scripts/build_sce_environment.py \
        --targets 2026-06..2026-10 --fetch \
        --out-prefix environment/environment_forward2026
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
STUDY_ID = "sce_inflation_expectations"
STUDY_DIR = REPO_ROOT / "studies" / STUDY_ID
SCHEMA_REPO = REPO_ROOT.parent / "socioverse2_repo"
DEFAULT_RAW_ROOT = REPO_ROOT / "data" / "raw" / "bls_initial_releases"
DEFAULT_PROXY = "http://127.0.0.1:7890"
RELEASE_TZ = ZoneInfo("America/New_York")
RELEASE_TIME = "08:30"

ARCHIVE_URL = {
    "cpi": "https://www.bls.gov/news.release/archives/cpi_{mmddyyyy}.pdf",
    "empsit": "https://www.bls.gov/news.release/archives/empsit_{mmddyyyy}.pdf",
}

MONTH_ABBR = [calendar.month_abbr[m] for m in range(1, 13)]
MONTH_NAME = [calendar.month_name[m] for m in range(1, 13)]

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}


# ---------------------------------------------------------------------------
# Targets / calendar
# ---------------------------------------------------------------------------

def parse_targets(spec: str) -> list[str]:
    """Accept '2021-01..2021-12' (inclusive) or a comma list '2021-01,2021-03'."""
    spec = spec.strip()
    if ".." in spec:
        first, last = spec.split("..", 1)
        y0, m0 = (int(x) for x in first.split("-"))
        y1, m1 = (int(x) for x in last.split("-"))
        out = []
        y, m = y0, m0
        while (y, m) <= (y1, m1):
            out.append(f"{y:04d}-{m:02d}")
            m += 1
            if m == 13:
                y, m = y + 1, 1
        return out
    months = [s.strip() for s in spec.split(",") if s.strip()]
    for m in months:
        if not re.fullmatch(r"\d{4}-\d{2}", m):
            raise ValueError(f"bad month: {m!r}")
    return months


def reference_period(target_month: str) -> str:
    """Reference period = M-2 per project protocol."""
    y, m = (int(x) for x in target_month.split("-"))
    m -= 2
    if m <= 0:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}"


def as_of_for(target_month: str) -> str:
    """as_of = last day of t-1, 23:59:59 America/New_York, with DST-correct offset."""
    y, m = (int(x) for x in target_month.split("-"))
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    last_day = calendar.monthrange(y, m)[1]
    dt = datetime(y, m, last_day, 23, 59, 59, tzinfo=RELEASE_TZ)
    return dt.isoformat()


def published_at_for(release_date: date) -> str:
    dt = datetime(release_date.year, release_date.month, release_date.day,
                  8, 30, tzinfo=RELEASE_TZ)
    return dt.isoformat()


def _candidate_dates(ref: str, kind: str) -> list[date]:
    """Probe order for the release date of reference month `ref`.

    CPI is released around the 13th of the following month; the Employment
    Situation on the first Friday of the following month. Both can shift with
    the federal-holiday calendar, so we sort a plausible window by distance
    from the canonical guess (weekdays only).
    """
    y, m = (int(x) for x in ref.split("-"))
    m += 1
    if m == 13:
        y, m = y + 1, 1
    if kind == "cpi":
        canonical, lo, hi = 13, 8, 20
    else:
        d = date(y, m, 1)
        canonical = d.day + (4 - d.weekday()) % 7  # first Friday
        lo, hi = 1, 12
    cands = [d for d in (date(y, m, day) for day in range(lo, hi + 1))
             if d.weekday() < 5]
    return sorted(cands, key=lambda d: (abs(d.day - canonical), d.day))


# ---------------------------------------------------------------------------
# Fetch + archive
# ---------------------------------------------------------------------------

def _squash(text: str) -> str:
    """Lowercased alnum-only text for layout-robust matching."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _first_pages_text(pdf_path: Path, n_pages: int = 2) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages[:n_pages])


def _verify_document(kind: str, ref: str, release_date: date, page_text: str) -> bool:
    """The archive URL date must match the document's own embargo line, and the
    reference month must appear in the release heading."""
    y, m = (int(x) for x in ref.split("-"))
    embargo_key = _squash(release_date.strftime("%B %-d, %Y"))
    if embargo_key not in _squash(page_text):
        return False
    if "transmissionofmaterial" not in _squash(page_text):
        return False
    month_key = _squash(f"{MONTH_NAME[m - 1]} {y}")
    if kind == "cpi":
        return month_key in _squash(page_text)
    return month_key in _squash(page_text)


def fetch_release(kind: str, ref: str, dest: Path, proxy: str,
                  pause: float = 1.5) -> dict:
    """Download the archived initial-release PDF for `ref`, verifying the
    release date from the document's embargo line. Returns the file manifest
    entry (or reuses an existing identical file)."""
    import httpx

    dest.parent.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(proxy=proxy, headers=BROWSER_HEADERS, timeout=60,
                          follow_redirects=True)
    last_error = None
    try:
        for cand in _candidate_dates(ref, kind):
            url = ARCHIVE_URL[kind].format(mmddyyyy=cand.strftime("%m%d%Y"))
            for attempt in range(3):
                try:
                    resp = client.get(url)
                except httpx.HTTPError as exc:  # network hiccup, retry
                    last_error = f"{url}: {exc}"
                    time.sleep(2.0 * (attempt + 1))
                    continue
                if resp.status_code == 404:
                    break  # try next candidate date
                if resp.status_code != 200:
                    last_error = f"{url}: HTTP {resp.status_code}"
                    time.sleep(2.0 * (attempt + 1))
                    continue
                tmp = dest.with_suffix(".part")
                tmp.write_bytes(resp.content)
                try:
                    page_text = _first_pages_text(tmp)
                except Exception as exc:  # not a readable PDF
                    last_error = f"{url}: unreadable PDF ({exc})"
                    tmp.unlink(missing_ok=True)
                    time.sleep(1.0)
                    continue
                if not _verify_document(kind, ref, cand, page_text):
                    last_error = (f"{url}: embargo/reference verification failed "
                                  f"(retrieved document does not match {cand} "
                                  f"or reference {ref})")
                    tmp.unlink(missing_ok=True)
                    time.sleep(1.0)
                    continue
                tmp.replace(dest)
                time.sleep(pause)
                return {
                    "url": url,
                    "release_date": cand.isoformat(),
                    "page1_preview": re.sub(r"\s+", " ", page_text)[:400],
                }
    finally:
        client.close()
    raise RuntimeError(
        f"could not retrieve a verified {kind} initial release for {ref}: {last_error}"
    )


def ensure_release(kind: str, ref: str, raw_dir: Path, fetch: bool,
                   proxy: str) -> dict:
    """Return (file_path, release_date_iso); archive to raw_dir if needed."""
    ref_y, ref_m = ref.split("-")
    prefix = f"{kind}_{ref_y}_{ref_m}_released_"
    existing = sorted(raw_dir.glob(prefix + "*.pdf"))
    if existing:
        path = existing[0]
        m = re.fullmatch(re.escape(prefix) + r"(\d{4})_(\d{2})_(\d{2})\.pdf",
                         path.name)
        if not m:
            raise ValueError(f"unexpected archive file name: {path.name}")
        release_date = date.fromisoformat("-".join(m.groups()))
        return {"path": path, "release_date": release_date, "fetched": False}
    if not fetch:
        raise FileNotFoundError(
            f"missing archived {kind} release for {ref} under {raw_dir} "
            f"(re-run with --fetch to download)")
    info = fetch_release(kind, ref, raw_dir / f"{prefix}pending.pdf", proxy)
    release_date = date.fromisoformat(info["release_date"])
    path = raw_dir / f"{prefix}{release_date.strftime('%Y_%m_%d')}.pdf"
    (raw_dir / f"{prefix}pending.pdf").replace(path)
    return {"path": path, "release_date": release_date, "fetched": True,
            "url": info["url"]}


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

def _compact(text: str) -> str:
    """Layout-robust text: lowercase, whitespace and PDF line-break artifacts
    removed (pypdf splits words mid-syllable at line ends, e.g. 'Novembe\\nr').
    Keeps digits, '.', '%', ',' and '-' so numbers stay readable."""
    return re.sub(r"[^a-z0-9.,%-]", "", text.lower())


def _quote(compact: str, match: re.Match, window: int = 160) -> str:
    lo = max(0, match.start() - window // 3)
    hi = min(len(compact), match.end() + window)
    return compact[lo:hi]


def transcribe_cpi(text: str, ref: str) -> dict:
    """Transcribe y/y NSA and m/m SA for CPI-U all items from the release text.

    Patterns run against the compacted first-page text; the first 12-month
    match is the CPI-U all-items sentence (component indexes appear later)."""
    y, m = (int(x) for x in ref.split("-"))
    c = _compact(text)
    month = MONTH_NAME[m - 1].lower()

    # m/m SA. Phrasing varies: "...increased 0.2 percent in november on a
    # seasonally adjusted basis" (pre-2026) vs "...increased 0.6 percent on a
    # seasonally adjusted basis in april" (2026+).
    orderings = (rf"in{month}onaseasonallyadjustedbasis",
                 rf"onaseasonallyadjustedbasisin{month}")
    mom_m = None
    for ordering in orderings:
        mom_m = re.search(
            rf"(increased|rose|advanced|declined|decreased|fell)([\d.]+)percent"
            rf"{ordering}", c)
        if mom_m:
            break
    if mom_m:
        verb, num = mom_m.group(1), float(mom_m.group(2))
        mom = -num if verb in ("declined", "decreased", "fell") else num
        mom_quote = _quote(c, mom_m)
    else:
        for ordering in orderings:
            mom_m = re.search(rf"unchanged{ordering}", c)
            if mom_m:
                break
        if not mom_m:
            raise ValueError(f"CPI m/m SA sentence not found for {ref}")
        mom, mom_quote = 0.0, _quote(c, mom_m)

    # y/y NSA, all items only. Candidate shapes:
    #   "...the all items index increased 1.2 percent before seasonal adjustment"
    #   "The Consumer Price Index for All Urban Consumers (CPI-U) increased 1.2
    #    percent over the last 12 months to an index level of ..."
    # Core/component indexes also carry "over the last 12 months" sentences, so
    # the match must sit next to an all-items anchor.
    yoy_m = None
    for mm in re.finditer(
            r"(increased|rose|declined|decreased|fell)([\d.]+)percent"
            r"(?:overthelast12months|beforeseasonaladjustment)", c):
        ctx = c[max(0, mm.start() - 80):mm.start()]
        if ("allitemsindex" in ctx or
                "consumerpriceindexforallurbanconsumers" in ctx or
                "all-itemsindex" in ctx):
            yoy_m = mm
            break
    if not yoy_m:
        raise ValueError(f"CPI y/y NSA all-items sentence not found for {ref}")
    verb, num = yoy_m.group(1), float(yoy_m.group(2))
    yoy = -num if verb in ("declined", "decreased", "fell") else num
    yoy_quote = _quote(c, yoy_m)

    usdl = re.search(r"usdl-(\d{2}-\d{4})", c).group(1)
    return {
        "cpi_yoy_nsa_pct": {"value": yoy, "quote": yoy_quote},
        "cpi_mom_sa_pct": {"value": mom, "quote": mom_quote},
        "usdl": usdl,
    }


def transcribe_empsit(text: str, ref: str) -> dict:
    """Transcribe the unemployment rate (SA) and nonfarm payroll change (SA)."""
    y, m = (int(x) for x in ref.split("-"))
    c = _compact(text)
    month = MONTH_NAME[m - 1].lower()

    # Unemployment rate. Variants:
    #   "...unemployment rate fell ... to 6.0 percent in march"
    #   "...unemployment rate was unchanged at 4.3 percent ..."
    #   "Both total nonfarm payroll employment (...) and the unemployment rate
    #    (4.2 percent) changed little in june" (2026-06 shape)
    both_m = re.search(
        rf"nonfarmpayrollemployment\(?([+-]?[\d,]+)\)?andtheunemploymentrate"
        rf"\(?([\d.]+)percent\)?changedlittlein{month}", c)
    if both_m:
        unemp = float(both_m.group(2))
        nfr = round(int(both_m.group(1).replace(",", "")) / 1000.0)
        return {
            "unemployment_rate_pct": {"value": unemp, "quote": _quote(c, both_m)},
            "nonfarm_payroll_change_k": {"value": nfr,
                                         "quote": _quote(c, both_m)},
            "usdl": re.search(r"usdl-(\d{2}-\d{4})", c).group(1),
        }
    unemp_m = re.search(
        rf"unemploymentrate(?:fell|rose|declined|edgeddown|edgedup).*?to"
        rf"([\d.]+)percent", c)
    if unemp_m:
        unemp = float(unemp_m.group(1))
        unemp_quote = _quote(c, unemp_m)
    else:
        unemp_m = re.search(
            r"unemploymentrate(?:wasunchanged|changedlittle|waslittlechanged)"
            r"(?:at|from)([\d.]+)percent", c)
        if not unemp_m:
            raise ValueError(f"unemployment rate sentence not found for {ref}")
        unemp = float(unemp_m.group(1))
        unemp_quote = _quote(c, unemp_m)

    # Nonfarm payrolls: "Total nonfarm payroll employment rose by 916,000 in
    # march"; pandemic-era variants include "nonfarm payroll employment changed
    # little (+49,000)".
    nf_m = re.search(
        rf"totalnonfarmpayrollemployment(rose|increased|grew|fell|declined|"
        rf"decreased|edgedup|edgeddown)by([\d,]+)in{month}", c)
    if nf_m:
        verb = nf_m.group(1)
        n_k = int(nf_m.group(2).replace(",", "")) / 1000.0
        nfr = -n_k if verb in ("fell", "declined", "decreased", "edgeddown") \
            else n_k
        nf_quote = _quote(c, nf_m)
    else:
        nf_m = re.search(
            r"nonfarmpayrollemploymentchangedlittle\(?(\+?-?[\d,]+)\)?", c)
        if nf_m:
            nfr = round(int(nf_m.group(1).replace(",", "")) / 1000.0)
            nf_quote = _quote(c, nf_m)
        else:
            nf_m = re.search(
                rf"totalnonfarmpayrollemployment(?:changedlittle|waslittlechanged)"
                rf"in{month}", c)
            if not nf_m:
                raise ValueError(f"nonfarm payroll sentence not found for {ref}")
            nfr, nf_quote = 0.0, _quote(c, nf_m)
    nfr = round(nfr)

    usdl = re.search(r"usdl-(\d{2}-\d{4})", c).group(1)
    return {
        "unemployment_rate_pct": {"value": unemp, "quote": unemp_quote},
        "nonfarm_payroll_change_k": {"value": nfr, "quote": nf_quote},
        "usdl": usdl,
    }


def _clean_value(v: float) -> float | int:
    return int(v) if float(v).is_integer() else v


# ---------------------------------------------------------------------------
# Signal / bundle assembly
# ---------------------------------------------------------------------------

def _signals_for_ref(ref: str, cpi: dict, emp: dict, url_cpi: str, url_emp: str,
                     pub_cpi: str, pub_emp: str) -> list[dict]:
    ref_y, ref_m = ref.split("-")
    sfx = f"{ref_y}_{ref_m}"
    rid = ref_m.lstrip("0")
    return [
        {
            "signal_id": f"bls_cpi_u_all_items_yoy_nsa_{sfx}_initial",
            "measure": "CPI-U all items 12-month percent change, not seasonally adjusted",
            "value": _clean_value(cpi["cpi_yoy_nsa_pct"]["value"]),
            "unit": "percent",
            "reference_period": ref,
            "published_at": pub_cpi,
            "source_version": f"USDL-{cpi['usdl']}",
            "source_url": url_cpi,
            "eligibility": "eligible",
        },
        {
            "signal_id": f"bls_cpi_u_all_items_mom_sa_{sfx}_initial",
            "measure": "CPI-U all items 1-month percent change, seasonally adjusted",
            "value": _clean_value(cpi["cpi_mom_sa_pct"]["value"]),
            "unit": "percent",
            "reference_period": ref,
            "published_at": pub_cpi,
            "source_version": f"USDL-{cpi['usdl']}",
            "source_url": url_cpi,
            "eligibility": "eligible",
        },
        {
            "signal_id": f"bls_unemployment_rate_sa_{sfx}_initial",
            "measure": "Civilian unemployment rate, seasonally adjusted",
            "value": _clean_value(emp["unemployment_rate_pct"]["value"]),
            "unit": "percent",
            "reference_period": ref,
            "published_at": pub_emp,
            "source_version": f"USDL-{emp['usdl']}",
            "source_url": url_emp,
            "eligibility": "eligible",
        },
        {
            "signal_id": f"bls_nonfarm_payroll_change_sa_{sfx}_initial",
            "measure": ("Total nonfarm payroll employment 1-month change, "
                        "seasonally adjusted"),
            "value": _clean_value(emp["nonfarm_payroll_change_k"]["value"]),
            "unit": "thousands",
            "reference_period": ref,
            "published_at": pub_emp,
            "source_version": f"USDL-{emp['usdl']}",
            "source_url": url_emp,
            "eligibility": "eligible",
        },
    ]


def _broadcast(step: int, target: str, ref: str, cpi: dict, emp: dict) -> dict:
    y, m = ref.split("-")
    ref_label = f"{MONTH_ABBR[int(m) - 1]} {y}"
    nfr = _clean_value(emp["nonfarm_payroll_change_k"]["value"])
    nfr_txt = f"{nfr:+d}k" if isinstance(nfr, int) else f"{nfr:+.1f}k"
    return {
        "message_id": f"bls-{target}",
        "content": (
            f"BLS initial releases available by {target} as_of: "
            f"CPI-U {ref_label}: {cpi['cpi_yoy_nsa_pct']['value']:+.1f}% y/y NSA; "
            f"CPI-U {ref_label}: {cpi['cpi_mom_sa_pct']['value']:+.1f}% m/m SA; "
            f"unemployment {ref_label}: "
            f"{emp['unemployment_rate_pct']['value']:.1f}% SA; "
            f"nonfarm payrolls {ref_label}: {nfr_txt} SA."
        ),
        "channel": "official_bls_release",
        "at_step": step,
        "ttl": 1,
        "audience": "all",
        "note": "Historical official release evidence; not FRED and not SCE result.",
    }


def _dataset_id(targets: list[str]) -> str:
    first, last = targets[0].replace("-", "_"), targets[-1].replace("-", "_")
    return f"sce_bls_initial_release_e_{first}_{last}_v1" if len(targets) > 1 else \
        f"sce_bls_initial_release_e_{first}_v1"


def build_window(targets: list[str], raw_root: Path, fetch: bool, proxy: str) -> dict:
    """Fetch/verify archives, transcribe values and assemble one window."""
    refs = [reference_period(t) for t in targets]
    signals_by_step: dict[str, list[dict]] = {}
    broadcasts = []
    external_records: dict[str, list[dict]] = {}
    as_of_by_step: dict[str, str] = {}
    manifests: dict[str, dict] = {}

    for step, (target, ref) in enumerate(zip(targets, refs)):
        raw_dir = raw_root / ref
        cpi_info = ensure_release("cpi", ref, raw_dir, fetch, proxy)
        emp_info = ensure_release("empsit", ref, raw_dir, fetch, proxy)

        cpi_text = _first_pages_text(cpi_info["path"])
        emp_text = _first_pages_text(emp_info["path"])
        cpi = transcribe_cpi(cpi_text, ref)
        emp = transcribe_empsit(emp_text, ref)

        pub_cpi = published_at_for(cpi_info["release_date"])
        pub_emp = published_at_for(emp_info["release_date"])
        as_of = as_of_for(target)
        # published must be strictly before the as_of cutoff
        if not (datetime.fromisoformat(pub_cpi) < datetime.fromisoformat(as_of)
                and datetime.fromisoformat(pub_emp) < datetime.fromisoformat(as_of)):
            raise ValueError(f"release for {ref} not published before as_of {as_of}")

        url_cpi = ARCHIVE_URL["cpi"].format(
            mmddyyyy=cpi_info["release_date"].strftime("%m%d%Y"))
        url_emp = ARCHIVE_URL["empsit"].format(
            mmddyyyy=emp_info["release_date"].strftime("%m%d%Y"))

        signals = _signals_for_ref(ref, cpi, emp, url_cpi, url_emp, pub_cpi, pub_emp)
        signals_by_step[str(step)] = signals
        external_records[str(step)] = signals
        as_of_by_step[str(step)] = as_of
        broadcasts.append(_broadcast(step, target, ref, cpi, emp))

        def _entry(path: Path, rel_date: date, url: str, usdl: str,
                   extractions: dict) -> dict:
            return {
                "file": path.name,
                "url": url,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
                "release_id": f"USDL-{usdl}",
                "release_date_verified_from": (
                    "first-page line 'Transmission of material in this release is "
                    "embargoed until 8:30 a.m. (ET) <Month D, YYYY>' matching the "
                    "archive URL date"),
                "published_at_et": published_at_for(rel_date),
                "reference_period": ref,
                "for_target_month": target,
                "extractions": [
                    {"field": k, "value": _clean_value(v["value"]),
                     "source_quote": v["quote"][:400]}
                    for k, v in extractions.items()
                ],
            }

        manifests[ref] = {
            "reference_period": ref,
            "for_target_month": target,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "retrieval_method": (
                "httpx GET with browser headers via local proxy "
                f"{proxy} (direct/proxied curl blocked by Akamai 403 on bls.gov); "
                "release date verified from the document embargo line; values "
                "transcribed from the archived initial-release PDF text. source_quote "
                "snippets are lowercased with whitespace removed (pypdf splits words "
                "at line ends); numbers and punctuation are unaltered"),
            "files": [
                _entry(cpi_info["path"], cpi_info["release_date"], url_cpi,
                       cpi["usdl"], {"cpi_u_yoy_nsa_pct": cpi["cpi_yoy_nsa_pct"],
                                     "cpi_u_mom_sa_pct": cpi["cpi_mom_sa_pct"]}),
                _entry(emp_info["path"], emp_info["release_date"], url_emp,
                       emp["usdl"], {"unemployment_rate_pct": emp["unemployment_rate_pct"],
                                     "nonfarm_payroll_change_k": emp["nonfarm_payroll_change_k"]}),
            ],
        }

    layer_source = "studies/sce_inflation_expectations/environment/external_events_PLACEHOLDER.json"
    bundle = {
        "study_id": STUDY_ID,
        "layers": [
            {
                "name": "bls_macro_release_signals",
                "modality": "physical",
                "scope": "macro",
                "dynamics": "scheduled",
                "source": layer_source,
                "schema_ref": None,
                "description": ("Four eligible BLS initial-release macro signals "
                                "(CPI y/y NSA, CPI m/m SA, unemployment rate SA, "
                                "nonfarm payrolls SA) for the current target month."),
            },
            {
                "name": "bls_release_information",
                "modality": "information",
                "scope": "macro",
                "dynamics": "scheduled",
                "source": layer_source,
                "schema_ref": None,
                "description": ("Macro broadcast carrying the same four BLS signals; "
                                "ttl=1."),
            },
            {
                "name": "agent_profile_context",
                "modality": "physical",
                "scope": "local",
                "dynamics": "static",
                "source": "uploads/_new/sce_20_synthetic_personas.csv",
                "schema_ref": None,
                "description": "Fixed synthetic profile fields used only for B mapping.",
            },
        ],
        "scheduled_events": [],
        "information_program": {"broadcasts": broadcasts},
        "provider_ref": f"{STUDY_ID}.environment",
        "provider_args": {
            "targets": [{"target_month": t, "as_of": as_of_for(t)} for t in targets],
            "signals_by_step": signals_by_step,
            "evidence_class": "historical_official_release_evidence",
            "excluded_sources": ["fred", "nyfed_sce", "nyt_archive"],
        },
    }

    external_events = {
        "study_id": STUDY_ID,
        "provider": "user_uploaded_bls_initial_release_json",
        "dataset_id": _dataset_id(targets),
        "status": "historical_official_release_evidence",
        "requested_months": targets,
        "records_by_step": external_records,
        "as_of": as_of_by_step,
        "fred_isolation": {
            "status": "unknown_as_of",
            "used_in_b": False,
            "reason": ("Event payload lacked published_at/release_date/vintage/"
                       "source_version."),
        },
    }
    return {"bundle": bundle, "external_events": external_events,
            "manifests": manifests, "targets": targets}


def simulation_config(targets: list[str]) -> dict:
    return {
        "study_id": STUDY_ID,
        "n_steps": len(targets),
        "seed": 42,
        "warm_start": None,
        "decision_ref": f"{STUDY_ID}.decision",
        "decision_args": {
            "llm_kind": "scripted",
            "prompt_version": "sce-q8-q9-scripted-v1",
            "model_version": "deterministic-scripted-v1",
            "seed": 42,
        },
        "collector_ref": f"{STUDY_ID}.collector",
        "collector_args": {},
        "interaction_rounds": 1,
        "engine_args": {"memory_window": 12},
        "store_ref": "duckdb",
        "store_args": {},
    }


def validate_with_official_schemas(bundle: dict, sim: dict) -> None:
    """model_validate against the socioverse2_repo official schemas."""
    if str(SCHEMA_REPO) not in sys.path:
        sys.path.insert(0, str(SCHEMA_REPO))
    from socioverse.schemas import EnvironmentBundle as _EB
    from socioverse.schemas import SimulationConfig as _SC

    _EB.model_validate(bundle)
    _SC.model_validate(sim)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--targets", required=True,
                    help="e.g. 2021-01..2021-12 or 2026-06,2026-07,2026-08")
    ap.add_argument("--out-prefix", required=True,
                    help="study-relative path stem, e.g. environment/environment_main2021")
    ap.add_argument("--raw-root", default=str(DEFAULT_RAW_ROOT),
                    help="archive root for BLS initial releases")
    ap.add_argument("--fetch", action="store_true",
                    help="download missing archived releases (default: fail if missing)")
    ap.add_argument("--proxy", default=DEFAULT_PROXY,
                    help="HTTP proxy for httpx downloads")
    ap.add_argument("--no-validate", action="store_true", help="skip schema validation")
    args = ap.parse_args()

    targets = parse_targets(args.targets)
    raw_root = Path(args.raw_root)
    if not raw_root.is_absolute():
        raw_root = REPO_ROOT / raw_root

    result = build_window(targets, raw_root, args.fetch, args.proxy)

    out_env = STUDY_DIR / f"{args.out_prefix}.json"
    stem = Path(args.out_prefix).name
    ext_path = STUDY_DIR / Path(args.out_prefix).parent / f"external_events_{stem}.json"
    sim_stem = re.sub(r"^environment", "simulation", stem)
    out_sim = STUDY_DIR / "simulation" / f"{sim_stem}.json"

    # point layer sources at the emitted external events file (study-relative)
    ext_rel = ext_path.relative_to(STUDY_DIR).as_posix()
    for layer in result["bundle"]["layers"]:
        if layer["name"].startswith("bls_"):
            layer["source"] = ext_rel

    sim = simulation_config(targets)
    if not args.no_validate:
        validate_with_official_schemas(result["bundle"], sim)

    _write_json(out_env, result["bundle"])
    _write_json(ext_path, result["external_events"])
    _write_json(out_sim, sim)

    # per-reference manifests into the raw archive
    for ref, manifest in result["manifests"].items():
        _write_json(raw_root / ref / "manifest.json", manifest)

    print(f"targets={len(targets)} refs={result['targets'][0]}..{result['targets'][-1]}")
    for step, b in enumerate(result["bundle"]["information_program"]["broadcasts"]):
        print(f"  step {step}: {b['content']}")
    print(f"wrote {out_env.relative_to(REPO_ROOT)}")
    print(f"wrote {ext_path.relative_to(REPO_ROOT)}")
    print(f"wrote {out_sim.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
