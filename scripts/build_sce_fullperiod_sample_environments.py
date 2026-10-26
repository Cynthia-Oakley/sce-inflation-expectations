#!/usr/bin/env python3
"""Build gap-tolerant E v2 environment bundles for the three SCE full-period
sample months (2019-06, 2023-03, 2026-06), writing into
outputs/sce_fullperiod_data_20261021_v1/<YYYYMM>/.

Why a local builder instead of running `scripts/build_sce_environment_v2.py`
directly (CLI checked: `--targets --out-prefix [--fetch]`, outputs hardcoded
under studies/ — writing there is out of scope for this delivery):

1. The stock builder requires CPI components in
   data/raw/bls_initial_releases/components_cpi.jsonl, which only covers
   refs 2019-12..2021-11 + 2026-04..2026-08. Refs 2023-02 / 2022-03..2023-01
   and everything <= 2019-11 must be extracted from the local archived
   first-release PDFs (extract_cpi_components logic, reused here; two narrow
   2019-era supplementary text patterns added, see SUPPLEMENT_PATTERNS).
2. History refs with no archived release are skipped and recorded as gaps
   instead of crashing: 2018-06..2018-11 for target 2019-06 (never archived
   locally; bls.gov returns Akamai 403 so they cannot be fetched), and
   2025-10 for target 2026-06 (permanently cancelled — the 2025-11 CPI and
   empsit PDFs state verbatim "BLS did not collect survey data for October
   2025 due to a lapse in federal appropriations"). Gasoline weekly data is
   not affected by the shutdown, so the 2025-10 gasoline history record IS
   emitted.
3. The NYT ledger (data/raw/nyt_archive/events_ledger.jsonl) only covers
   2020-10..2021-12, so the M-1 month of every sample target is recomputed
   from the raw archive cache with the identical nyt.select_events logic and
   merged with the PIT-filtered early-M selection — same selection rules as
   the stock builder, full news coverage.

Every emitted record still passes the stock hard guard published_at < as_of,
and the final bundle is validated against the official socioverse2_repo
EnvironmentBundle + SimulationConfig schemas (identical to the stock CLI).

Offline only; no existing file is modified (shadow component/ledger files
are written under the delivery output directory and the env2 module globals
COMPONENTS_JSONL / GAS_WEEKLY_CSV / NYT_LEDGER are pointed at them in-memory).
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_sce_environment as v1  # noqa: E402
import build_sce_environment_v2 as env2  # noqa: E402
import build_nyt_events as nyt  # noqa: E402
from extract_cpi_components import (  # noqa: E402
    PATTERNS, SANITY, _extract_from_table_a, _extract_from_text, _page_texts,
)

OUT_DIR = REPO_ROOT / "outputs/sce_fullperiod_data_20261021_v1"
RAW_BLS = REPO_ROOT / "data/raw/bls_initial_releases"
SUPPORT_DIR = OUT_DIR / "_build_support"
EXISTING_COMPONENTS = RAW_BLS / "components_cpi.jsonl"
GAS_CONSOLIDATED = (REPO_ROOT / "data/raw/eia_gasoline_support"
                    / "20261007T085903Z/gasoline_retail_regular_consolidated.csv")

TARGETS = ["2019-06", "2023-03", "2026-06"]

# Narrow supplements for 2019-era CPI prose not matched by the stock patterns
# (verified verbatim against the archived PDFs, with page quotes recorded):
#   2019-05: "The food index rose 2.0 percent over the past year, with the
#             food at home index increasing 1.2 percent."
#   2019-05: "The shelter index rose 3.3 percent over the year."
SUPPLEMENT_PATTERNS = {
    "cpi_food_at_home_yoy":
        [r"food at home index (?:rose|increased) (?P<num>[\d.]+) percent"
         r"(?: over the (?:past |last )?year)"],
    "cpi_shelter_yoy":
        [r"[Ss]helter index (?:rose|increased) (?P<num>[\d.]+) percent over the year"],
}


def _decoded_pages(pages: list[str]) -> list[str]:
    """+0x1D-decoded copy of every page (custom-font releases, e.g. the
    2018-10 CPI: first-page font is Caesar -3 with unrecoverable digits,
    Table A font is a fixed +0x1D shift with recoverable digits)."""
    decoded = []
    for p in pages:
        out = []
        for ch in p:
            o = ord(ch)
            if 0x11 <= o <= 0x60 and o != 0x20:  # encoded range (space 0x20 stays)
                out.append(chr(o + 0x1D))
            elif o < 0x20:
                out.append(" ")  # decoded space glyph
            else:
                out.append(ch)
        decoded.append("".join(out))
    return decoded


def _table_a_legible(page: str) -> bool:
    norm = re.sub(r"[\x00-\x1f]", " ", page)
    return "Table A" in norm and re.search(r"\d+\.\d", norm) is not None


def _best_page_texts(pdf: Path) -> list[str]:
    """Per-page best of raw vs +0x1D-decoded: some releases mix normal pages
    with custom-font pages (2018-10), so decoding is decided page by page.
    Control-char glyphs (custom-font space/digit artifacts) are normalized
    to plain spaces."""
    pages = _page_texts(pdf)
    decoded = _decoded_pages(pages)
    out = []
    for raw, dec in zip(pages, decoded):
        if _table_a_legible(raw) or not _table_a_legible(dec):
            out.append(raw)
        else:
            out.append(dec)
    return [re.sub(r"[\x00-\x1f]", " ", p) for p in out]


TABLE_A_PCT_LABELS = {
    "cpi_food_yoy": "Food",
    "cpi_food_at_home_yoy": "Food at home",
    "cpi_energy_yoy": "Energy",
    "cpi_shelter_yoy": "Shelter",
    "cpi_gasoline_yoy": "Gasoline (all types)",
}
# a numeric token in the percent-change Table A (values may lack a leading
# or trailing digit: ".2", "1."); lone leader dots must NOT match
_PCT_TOKEN = r"-?(?:\d+\.\d+|\.\d+|\d+\.)"


def _extract_from_table_a_pct(pages: list[str], sig: str) -> dict | None:
    """2018-era percent-change Table A has no >=100 index-level columns, so
    the stock table_a parser (which anchors on those) cannot read it. Here
    the LAST number of the label row is the unadjusted 12-month change."""
    label = TABLE_A_PCT_LABELS.get(sig)
    if not label:
        return None
    for page_no, p in enumerate(pages, 1):
        if "Table A" not in p:
            continue
        t = re.sub(r"\s+", " ", p)
        for m in re.finditer(re.escape(label) + r"(?=[^A-Za-z]|$)", t):
            row = t[m.start():m.start() + 220]
            # gap between label and numbers may contain only dots/spaces; if
            # another label intervenes before the numbers (text-extraction
            # interleaving, seen in cpi_2019_04), the pairing is ambiguous
            # -> handoff rather than guess.
            nums = re.search(
                r"(?P<gap>[ .=]*)(?P<nums>(?:"
                + _PCT_TOKEN + r"[ ]){5,}" + _PCT_TOKEN + r")(?![\d.])",
                row[len(label):])
            if not nums or re.search(r"[A-Za-z]", nums.group("gap")):
                continue
            toks = nums.group("nums").split()
            last = toks[-1]
            if re.fullmatch(r"-?\d+\.", last):
                # trailing-dot token: a digit glyph the font dropped
                # (e.g. 2018-10 energy row) — value unrecoverable
                return None
            return {"value": float(last),
                    "quote": row[:200].strip(), "page": page_no,
                    "pattern": f"tableA_pct:{label}", "extraction": "table_a_pct"}
    return None


def _extract_component(pdf: Path, sig: str, ref: str) -> dict | None:
    """Stock extractors, percent-change Table A, then 2019-era supplements,
    on the page-wise best raw/decoded text. Failures -> None (handoff)."""
    pages = _best_page_texts(pdf)
    hit = (_extract_from_text(pages, sig, ref)
           or _extract_from_table_a(pages, sig)
           or _extract_from_table_a_pct(pages, sig))
    if hit is None and sig in SUPPLEMENT_PATTERNS:
        for pat in SUPPLEMENT_PATTERNS[sig]:
            for page_no, text in enumerate(pages, 1):
                m = re.search(pat, text)
                if m:
                    quote = text[max(0, m.start() - 80):m.end() + 60].strip()
                    hit = {"value": float(m.group("num")), "quote": quote,
                           "page": page_no, "pattern": f"supplement:{pat[:40]}",
                           "extraction": "text_supplement_fullperiod"}
                    break
            if hit:
                break
    if hit is None:
        return None
    lo, hi = SANITY[sig]
    if not (lo <= hit["value"] <= hi):
        raise ValueError(f"{ref} {sig}: value {hit['value']} "
                         f"outside sanity [{lo},{hi}]")
    return hit


def build_shadow_components(refs: list[str]) -> Path:
    """Merge existing validated components with freshly extracted refs."""
    out_path = SUPPORT_DIR / "components_cpi_shadow.jsonl"
    existing: dict[str, dict[str, dict]] = {}
    for line in EXISTING_COMPONENTS.read_text().splitlines():
        r = json.loads(line)
        existing.setdefault(r["reference_period"], {})[r["signal_id"]] = r
    records, gaps = [], []
    for ref in sorted(set(refs)):
        if ref in existing:
            records.extend(existing[ref].values())
            continue
        pdf = next((RAW_BLS / ref).glob("cpi_*.pdf"), None)
        if pdf is None:
            for sig in PATTERNS:
                gaps.append({"reference_period": ref, "signal_id": sig,
                             "reason": "no archived CPI release (ref cancelled or never archived)"})
            continue
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        m = re.match(r"cpi_\d{4}_\d{2}_released_(\d{4})_(\d{2})_(\d{2})\.pdf",
                     pdf.name)
        published = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        for sig in PATTERNS:
            hit = _extract_component(pdf, sig, ref)
            base = {"reference_period": ref, "published_at": published,
                    "source_pdf": str(pdf.relative_to(REPO_ROOT)),
                    "source_sha256": digest, "signal_id": sig,
                    "unit": "percent_12m_nsa"}
            if hit is None:
                gaps.append({**base, "reason": "no pattern matched (incl. supplements)"})
            else:
                records.append({**base, **hit})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    (SUPPORT_DIR / "components_gaps.json").write_text(
        json.dumps(gaps, ensure_ascii=False, indent=2) + "\n")
    print(f"shadow components: {len(records)} records, {len(gaps)} signal gaps "
          f"-> {out_path.relative_to(REPO_ROOT)}")
    return out_path


def build_shadow_ledger(months: list[str]) -> Path:
    """Full-month NYT event selection for M-1 window months (identical logic
    to build_nyt_events.select_events as used for the completed-month ledger)."""
    out_path = SUPPORT_DIR / "events_ledger_shadow.jsonl"
    n_total = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for month in months:
            cache = REPO_ROOT / "data/raw/nyt_archive" / f"{month}.json"
            payload = cache.read_bytes()
            docs = json.loads(payload)["response"]["docs"]
            events = nyt.select_events(
                docs, month, hashlib.sha256(payload).hexdigest(), env2.EVENT_BUDGET)
            for e in events:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
            n_total += len(events)
            print(f"  shadow ledger {month}: {len(events)} events "
                  f"(from {len(docs)} docs)")
    return out_path


def build_environment_gap_tolerant(target: str, *, employment_reference: str | None = None) -> dict:
    """Modified copy of env2.build_window_v2 for ONE target, tolerant of
    missing history refs (recorded in data_gaps) and patched loaders.
    Record layout and guards are identical to the stock builder."""
    raw_root = RAW_BLS
    base = v1.build_window([target], raw_root, False, v1.DEFAULT_PROXY)
    components = env2.load_components()
    gasoline = env2.load_gasoline_weekly()
    events_by_month = env2.load_nyt_events()

    ref = env2.reference_period_v2(target)
    history_refs = [env2.shift_month(ref, -k) for k in range(1, 12)]
    data_gaps: list[dict] = []

    # ---- history sequences: skip refs with no archived release ----
    history: dict[str, dict] = {}
    emp_history: dict[str, dict] = {}
    for h_ref in history_refs:
        try:
            info = v1.ensure_release("cpi", h_ref, raw_root / h_ref, False,
                                     v1.DEFAULT_PROXY)
        except FileNotFoundError:
            data_gaps.append({"reference_period": h_ref, "family": "bls_cpi_yoy_history",
                              "reason": _gap_reason(h_ref)})
        else:
            try:
                cpi = _transcribe_cpi_history(
                    v1._first_pages_text(info["path"]), h_ref, info["path"])
            except ValueError as e:
                data_gaps.append({"reference_period": h_ref,
                                  "family": "bls_cpi_yoy_history",
                                  "reason": f"transcription failed: {e}"})
            else:
                history[h_ref] = {
                    "value": v1._clean_value(cpi["cpi_yoy_nsa_pct"]["value"]),
                    "published_at": env2._pub_et(info["release_date"]),
                    "source_version": f"USDL-{cpi['usdl']}",
                    "source_url": v1.ARCHIVE_URL["cpi"].format(
                        mmddyyyy=info["release_date"].strftime("%m%d%Y")),
                    "source_sha256": hashlib.sha256(info["path"].read_bytes()).hexdigest(),
                    **({"note": cpi["note"]} if "note" in cpi else {}),
                }
        try:
            einfo = v1.ensure_release("empsit", h_ref, raw_root / h_ref, False,
                                      v1.DEFAULT_PROXY)
        except FileNotFoundError:
            data_gaps.append({"reference_period": h_ref, "family": "bls_unemployment_history",
                              "reason": _gap_reason(h_ref)})
        else:
            try:
                emp = env2._unemployment_rate_only(v1._first_pages_text(einfo["path"]),
                                                   h_ref)
            except ValueError as e:
                data_gaps.append({"reference_period": h_ref,
                                  "family": "bls_unemployment_history",
                                  "reason": f"transcription failed: {e}"})
            else:
                emp_history[h_ref] = {
                    "value": v1._clean_value(emp["value"]),
                    "published_at": env2._pub_et(einfo["release_date"]),
                    "source_version": f"USDL-{emp['usdl']}",
                    "source_url": v1.ARCHIVE_URL["empsit"].format(
                        mmddyyyy=einfo["release_date"].strftime("%m%d%Y")),
                    "source_sha256": hashlib.sha256(einfo["path"].read_bytes()).hexdigest(),
                }

    # ---- latest-release headline signals (ref must exist) ----
    cpi_info = v1.ensure_release("cpi", ref, raw_root / ref, False, v1.DEFAULT_PROXY)
    emp_ref = employment_reference or ref
    emp_info = v1.ensure_release("empsit", emp_ref, raw_root / emp_ref, False,
                                 v1.DEFAULT_PROXY)
    cpi = v1.transcribe_cpi(v1._first_pages_text(cpi_info["path"]), ref)
    emp = v1.transcribe_empsit(v1._first_pages_text(emp_info["path"]), emp_ref)
    pub_cpi = v1.published_at_for(cpi_info["release_date"])
    pub_emp = v1.published_at_for(emp_info["release_date"])
    rd = cpi_info["release_date"]
    as_of = datetime(rd.year, rd.month, rd.day, 23, 59, 59, tzinfo=v1.RELEASE_TZ)
    if not datetime.fromisoformat(pub_emp) < as_of:
        raise ValueError(f"employment release for {emp_ref} not before as_of {as_of}")
    url_cpi = v1.ARCHIVE_URL["cpi"].format(mmddyyyy=rd.strftime("%m%d%Y"))
    url_emp = v1.ARCHIVE_URL["empsit"].format(
        mmddyyyy=emp_info["release_date"].strftime("%m%d%Y"))
    records = [dict(r, role="latest_release")
               for r in v1._signals_for_ref(ref, cpi, emp, url_cpi, url_emp,
                                            pub_cpi, pub_emp)]
    broadcasts = [v1._broadcast(0, target, ref, cpi, emp)]
    if emp_ref != ref:
        # Explicit caller-selected archived jobs report, still subject to the
        # publication guard above. Never relabel an older report as CPI's month.
        for record in records:
            if record['signal_id'].startswith(('bls_unemployment_', 'bls_nonfarm_')):
                record['signal_id'] = record['signal_id'].replace(ref.replace('-', '_'), emp_ref.replace('-', '_'))
                record['reference_period'] = emp_ref
        label = lambda value: f"{v1.MONTH_ABBR[int(value[5:7])-1]} {value[:4]}"
        for prefix in ('unemployment', 'nonfarm payrolls'):
            broadcasts[0]['content'] = broadcasts[0]['content'].replace(f'{prefix} {label(ref)}:', f'{prefix} {label(emp_ref)}:')
        data_gaps.append({'reference_period': ref, 'family': 'latest_employment_release_delayed',
                          'substitute_reference_period': emp_ref,
                          'reason': 'Caller-selected earlier archived jobs release available by the CPI cutoff; original period and publication retained'})

    # ---- components (latest ref; per-signal gaps recorded) ----
    ref_components = components.get(ref, {})
    usdl, cpi_url = next(
        (r["source_version"], r["source_url"]) for r in records
        if r["signal_id"].startswith("bls_cpi_u_all_items_yoy"))
    for sig, measure in env2.COMPONENT_MEASURES.items():
        c = ref_components.get(sig)
        if c is None:
            data_gaps.append({"reference_period": ref, "family": "bls_cpi_components_latest",
                              "signal_id": sig,
                              "reason": "component not extractable from archived release"})
            continue
        records.append({
            "signal_id": f"bls_{sig}_nsa_{ref.replace('-', '_')}_initial",
            "measure": measure, "value": c["value"], "unit": "percent",
            "reference_period": ref,
            "published_at": env2._pub_et(date.fromisoformat(c["published_at"])),
            "source_version": usdl, "source_url": cpi_url,
            "eligibility": "eligible", "role": "latest_release",
        })

    # ---- history records ----
    for h_ref in history_refs:
        h = history.get(h_ref)
        if h:
            records.append({
                "signal_id": f"bls_cpi_u_all_items_yoy_nsa_{h_ref.replace('-', '_')}_initial",
                "measure": ("CPI-U all items 12-month percent change, not seasonally adjusted"),
                "value": h["value"], "unit": "percent", "reference_period": h_ref,
                "published_at": h["published_at"], "source_version": h["source_version"],
                "source_url": h["source_url"], "eligibility": "eligible", "role": "history",
            })
        ue = emp_history.get(h_ref)
        if ue:
            records.append({
                "signal_id": f"bls_unemployment_rate_sa_{h_ref.replace('-', '_')}_initial",
                "measure": "Civilian unemployment rate, seasonally adjusted",
                "value": ue["value"], "unit": "percent", "reference_period": h_ref,
                "published_at": ue["published_at"], "source_version": ue["source_version"],
                "source_url": ue["source_url"], "eligibility": "eligible", "role": "history",
            })
        for sig, measure in env2.HISTORY_COMPONENTS.items():
            c = components.get(h_ref, {}).get(sig)
            if c is None:
                if h_ref in history:  # release exists but component not extractable
                    data_gaps.append({"reference_period": h_ref,
                                      "family": "bls_cpi_component_history",
                                      "signal_id": sig,
                                      "reason": "component not extractable from archived release"})
                continue
            records.append({
                "signal_id": f"bls_{sig}_nsa_{h_ref.replace('-', '_')}_initial",
                "measure": measure, "value": c["value"], "unit": "percent",
                "reference_period": h_ref,
                "published_at": history[h_ref]["published_at"],
                "source_version": history[h_ref]["source_version"],
                "source_url": history[h_ref]["source_url"],
                "eligibility": "eligible", "role": "history",
            })
        g_h = gasoline.get(h_ref)
        if g_h is None:
            data_gaps.append({"reference_period": h_ref,
                              "family": "eia_gasoline_level_history",
                              "reason": "no weekly gasoline observations for ref month"})
            continue
        gas_pub_h = (date.fromisoformat(g_h["last_obs_date"])
                     + timedelta(days=3)).isoformat() + "T17:00:00"
        rec = {
            "signal_id": f"eia_gasoline_retail_regular_mean_{h_ref.replace('-', '_')}",
            "measure": ("U.S. regular all formulations retail gasoline price, "
                        "monthly mean of weekly observations"),
            "value": g_h["price_mean"], "unit": "dollars_per_gallon",
            "reference_period": h_ref,
            "published_at": datetime.fromisoformat(gas_pub_h).replace(
                tzinfo=v1.RELEASE_TZ).isoformat(),
            "source_version": "FRED GASREGW (EIA weekly retail, Monday obs)",
            "source_url": "https://fred.stlouisfed.org/series/GASREGW",
            "eligibility": "vintage_unverified", "role": "history",
            "published_at_basis": "last_weekly_observation_plus_3_days_assumption",
            "note": ("monthly mean of weekly Monday observations; published_at = "
                     "last weekly obs + 3 days (conservative)"),
        }
        if h_ref not in emp_history and h_ref not in history:
            # shutdown-cancelled BLS month: gasoline still observed (EIA not shut down)
            rec["note"] += ("; BLS data for this reference period were cancelled "
                            "(federal shutdown) — gasoline record unaffected")
        records.append(rec)

    # ---- latest gasoline ----
    g = gasoline.get(ref)
    if not g:
        raise ValueError(f"missing gasoline data for ref {ref}")
    gas_pub = (date.fromisoformat(g["last_obs_date"])
               + timedelta(days=3)).isoformat() + "T17:00:00"
    gas_pub_dt = datetime.fromisoformat(gas_pub).replace(tzinfo=v1.RELEASE_TZ)
    gas_common = {
        "reference_period": ref, "published_at": gas_pub_dt.isoformat(),
        "source_version": "FRED GASREGW (EIA weekly retail, Monday obs)",
        "source_url": "https://fred.stlouisfed.org/series/GASREGW",
        "eligibility": "vintage_unverified", "role": "latest_release",
        "published_at_basis": "last_weekly_observation_plus_3_days_assumption",
        "note": ("monthly mean of weekly Monday observations; published_at = "
                 "last weekly obs + 3 days (conservative)"),
    }
    records.append({
        "signal_id": f"eia_gasoline_retail_regular_mean_{ref.replace('-', '_')}",
        "measure": ("U.S. regular all formulations retail gasoline price, "
                    "monthly mean of weekly observations"),
        "value": g["price_mean"], "unit": "dollars_per_gallon", **gas_common,
    })
    if "yoy_pct" in g:
        records.append({
            "signal_id": f"eia_gasoline_retail_regular_yoy_{ref.replace('-', '_')}",
            "measure": "Retail gasoline price 12-month percent change (monthly means)",
            "value": g["yoy_pct"], "unit": "percent", **gas_common,
        })
    else:
        data_gaps.append({"reference_period": ref, "family": "eia_gasoline_yoy_latest",
                          "reason": "prior-year monthly mean unavailable (weekly series starts 2018-12)"})

    # hard eligibility guard: everything strictly before as_of
    for r in records:
        if not datetime.fromisoformat(r["published_at"]) < as_of:
            raise ValueError(f"record {r['signal_id']} published {r['published_at']} "
                             f"not before as_of {as_of.isoformat()}")

    # ---- NYT events: M-1 (shadow ledger, full month) + early M (PIT cutoff) ----
    as_of_date = as_of.date()
    pool = list(events_by_month.get(env2.shift_month(target, -1), []))
    pool.extend(env2.load_nyt_events_until(target, as_of_date))
    for e in pool:
        if date.fromisoformat(e["pub_date"]) > as_of_date:
            raise ValueError(f"event {e['event_id']} after as_of")
    evs = [{k: e[k] for k in
            ("event_id", "pub_date", "tier", "headline", "abstract",
             "section_name", "web_url", "matched_keywords")}
           for e in env2._merge_event_pool(pool, env2.EVENT_BUDGET)]
    for event in evs:
        event["text_vintage_status"] = "unverified_archive_snapshot"
        event["selection_cutoff"] = as_of_date.isoformat()

    signals_by_step = {"0": records}
    events_by_step = {"0": evs}

    bundle = base["bundle"]
    bundle["provider_args"]["signals_by_step"] = signals_by_step
    bundle["provider_args"]["events_by_step"] = events_by_step
    bundle["provider_args"]["targets"] = [
        {"target_month": target, "as_of": as_of.isoformat()}]
    bundle["provider_args"]["e_version"] = "v2"
    bundle["provider_args"]["evidence_class"] = "mixed_source_vintage_status"
    bundle["provider_args"]["source_status"] = {
        "bls": "archived_initial_release_verified",
        "eia_gasoline": "current_fred_snapshot_vintage_unverified",
        "nyt": "archive_metadata_text_vintage_unverified",
    }
    bundle["provider_args"]["excluded_sources"] = ["nyfed_sce"]
    bundle["provider_args"]["e_v2_layers"] = [
        "bls_headline_4_signals", "bls_cpi_components_5",
        "eia_gasoline_retail_level_yoy",
        "bls_cpi_yoy_history_11m", "bls_unemployment_history_11m",
        "bls_cpi_component_history_3x11m", "eia_gasoline_level_history_11m",
        "nyt_salient_events_m_minus_1_through_as_of",
    ]
    bundle["provider_args"]["data_gaps"] = {
        "note": ("History refs with no archived first release are omitted (not "
                 "fabricated); gasoline records are unaffected by the 2025-10 BLS "
                 "cancellation. component/ledger shadow files live under "
                 "outputs/sce_fullperiod_data_20261021_v1/_build_support/."),
        "gaps": data_gaps,
    }
    bundle["information_program"]["broadcasts"] = broadcasts
    # extend layers exactly like the stock builder
    bundle["layers"] = bundle["layers"] + [
        {"name": "bls_cpi_component_signals",
         "modality": "physical", "scope": "macro", "dynamics": "scheduled",
         "source": "data/raw/bls_initial_releases/components_cpi.jsonl",
         "schema_ref": None,
         "description": ("Five household-perceivable CPI component 12-month "
                         "changes (food, food at home, energy, shelter, "
                         "gasoline) from the same archived first releases.")},
        {"name": "bls_cpi_yoy_history",
         "modality": "physical", "scope": "macro", "dynamics": "scheduled",
         "source": "data/raw/bls_initial_releases/",
         "schema_ref": None,
         "description": ("Trailing 11 first-release history sequences per step "
                         "(D049a/D051): CPI all-items y/y, unemployment rate, "
                         "CPI food/energy/shelter y/y, gasoline retail monthly "
                         "mean level.")},
        {"name": "eia_gasoline_retail_price",
         "modality": "physical", "scope": "macro", "dynamics": "scheduled",
         "source": "data/raw/eia_gasoline/gasoline_retail_regular_weekly.csv",
         "schema_ref": None,
         "description": ("Monthly mean + y/y of U.S. regular retail gasoline "
                         "price (EIA via FRED GASREGW).")},
        {"name": "nyt_salient_events",
         "modality": "information", "scope": "macro", "dynamics": "scheduled",
         "source": "data/raw/nyt_archive/",
         "schema_ref": None,
         "description": ("NYT front-page (A1) + inflation-keyword events, "
                         "headline + abstract, published M-1-01 through the "
                         "CPI release day inside M; current month is ranked "
                         "only after the as_of date filter (D049d/D050).")},
    ]

    external_events = base["external_events"]
    external_events["dataset_id"] = external_events["dataset_id"].replace("_v1", "_v2")
    external_events["records_by_step"] = signals_by_step
    external_events["events_by_step"] = events_by_step
    external_events["as_of"] = {"0": as_of.isoformat()}
    external_events["e_version"] = "v2"
    external_events["status"] = "mixed_source_vintage_status"
    external_events["data_gaps"] = bundle["provider_args"]["data_gaps"]

    sim = v1.simulation_config([target])
    v1.validate_with_official_schemas(bundle, sim)
    return {"bundle": bundle, "external_events": external_events,
            "data_gaps": data_gaps, "n_records": len(records), "n_events": len(evs),
            "as_of": as_of.isoformat()}


def _cpi_yoy_fallback(text: str, ref: str, pdf: Path, pages: list[str]) -> dict:
    """y/y-only transcription for releases v1.transcribe_cpi cannot parse:
    (a) shutdown-era combined releases (m/m SA not published) — prose pattern;
    (b) custom-font releases (e.g. 2018-10) — decoded Table A 'All items'
        row, last value = unadjusted 12-month percent change (2.5 for
        ref 2018-10, verified against the decoded table text)."""
    c = v1._compact(text)
    m = re.search(
        r"allitemsindex(?:rose|increased|advanced|declined|decreased|fell)"
        r"([\d.]+)percentbeforeseasonaladjustment", c)
    if m:
        value = float(m.group(1))
        quote = "fallback prose: " + m.group(0)[:120]
        note = ("y/y from shutdown-era combined release (m/m SA not published); "
                "transcribed via fullperiod fallback pattern")
    else:
        cands = [re.sub(r"\s+", " ", p) for p in _best_page_texts(pdf)]
        tbl = next((p for p in cands if "Table A" in p), None)
        if tbl is None:
            raise ValueError(f"no legible Table A for {ref}")
        row = re.search(
            rf"All items\D{{0,60}}?((?:{_PCT_TOKEN}[ ]){{6,}}{_PCT_TOKEN})", tbl)
        if not row:
            raise ValueError(f"All items row not parsed for {ref}")
        toks = row.group(1).split()
        if re.fullmatch(r"-?\d+\.", toks[-1]):
            raise ValueError(f"All items 12-month token incomplete for {ref}: "
                             f"{toks[-1]!r} (digit dropped by custom font)")
        value = float(toks[-1])
        quote = f"Table A All items row: {row.group(1).strip()}"
        note = ("y/y parsed from Table A 'All items' row (prose m/m sentence "
                "unavailable in this release)")
    if not -5.0 <= value <= 15.0:
        raise ValueError(f"{ref}: fallback y/y {value} outside sanity [-5,15]")
    usdl_m = re.search(r"usdl-(\d{2}-\d{4})", c)
    usdl = usdl_m.group(1) if usdl_m else "unverified-custom-font"
    return {"cpi_yoy_nsa_pct": {"value": value, "quote": quote},
            "usdl": usdl, "note": note}


def _transcribe_cpi_history(text: str, ref: str, pdf: Path) -> dict:
    try:
        return v1.transcribe_cpi(text, ref)
    except ValueError:
        return _cpi_yoy_fallback(text, ref, pdf, _page_texts(pdf))


def _gap_reason(ref: str) -> str:
    if ref == "2025-10":
        return ("ref 2025-10 BLS releases permanently cancelled; 2025-11 CPI and "
                "empsit PDFs state data for October 2025 were not collected "
                "(federal government shutdown)")
    return ("archived first release not available locally (pre-2018-12 ref); "
            "bls.gov archive returns 403 (Akamai) so it cannot be fetched offline")


def main() -> int:
    refs_needed = []
    window_m1 = []
    for t in TARGETS:
        ref = env2.reference_period_v2(t)
        refs_needed.append(ref)
        refs_needed += [env2.shift_month(ref, -k) for k in range(1, 12)]
        window_m1.append(env2.shift_month(t, -1))
    shadow_components = build_shadow_components(refs_needed)
    shadow_ledger = build_shadow_ledger(window_m1)

    # point the env2 module globals at the shadow files (in-memory only)
    env2.COMPONENTS_JSONL = shadow_components
    env2.GAS_WEEKLY_CSV = GAS_CONSOLIDATED
    env2.NYT_LEDGER = shadow_ledger

    for target in TARGETS:
        result = build_environment_gap_tolerant(target)
        month_dir = OUT_DIR / target.replace("-", "")
        month_dir.mkdir(parents=True, exist_ok=True)
        (month_dir / "environment.json").write_text(
            json.dumps(result["bundle"], ensure_ascii=False, indent=2) + "\n")
        (month_dir / "external_events.json").write_text(
            json.dumps(result["external_events"], ensure_ascii=False, indent=2) + "\n")
        print(f"{target}: as_of={result['as_of']} records={result['n_records']} "
              f"events={result['n_events']} gaps={len(result['data_gaps'])} "
              f"-> {month_dir.relative_to(REPO_ROOT)}/environment.json "
              "(schema-validated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
