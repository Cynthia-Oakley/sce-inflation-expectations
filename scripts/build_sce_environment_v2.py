#!/usr/bin/env python3
"""Build the E v2 information environment for sce_inflation_expectations.

E v2 (D049a/c/d + D050) extends the frozen v1 layer (4 BLS headline signals
per step). Timing convention (D050, user 2026-10-04): for target month M the
newest reference period is R = M-1 and as_of = the day the R CPI is released
inside month M, 23:59:59 ET. This matches the median real SCE respondent:
measured on the 2021 microdata, the median interview day is the 15th
(P25=8th, P75=21st), while the jobs report for M-1 comes out on the first
Friday of M and the CPI for M-1 on ~the 10th-13th — so the median respondent
answers after both releases. (v1 used R = M-2 with as_of = end of M-1, i.e.
the information set of someone answering on the 1st.)

For every target month M (R = M-1, as_of = CPI release day of R):

  1. CPI component latest values (first-release, from the archived PDFs via
     extract_cpi_components.py): food, food at home, energy, shelter, gasoline
     12-month changes — the prices households actually perceive.
  2. History sequences (D049a/D051), trailing 11 first-release values each
     (refs R-11..R-1): headline CPI y/y; unemployment rate; CPI component
     y/y for food, energy, shelter; retail gasoline monthly mean level.
     Nonfarm payrolls stays latest-only (abstract for households).
  3. Retail gasoline price (EIA via FRED GASREGW): monthly mean level + y/y
     change for ref R; published_at = last weekly observation + 3 days
     (documented conservative convention; EIA releases weekly prices within
     days of the Monday observation).
  4. NYT salient events (build_nyt_events.py ledger): headline + abstract for
     events published from M-1-01 through the as_of day (i.e. all of month M-1
     plus early M up to the CPI release). Tier front_page+strong uncapped,
     other tiers share a budget of 30, hit-density first then recency.

Every record carries reference_period / published_at / source and a hard
assert guarantees published_at < as_of. The v1 bundle is rebuilt in memory
(v1.build_window) as a skeleton and its signals/as_of/broadcasts are
replaced with the v2 timing — v1 output files are never touched.

    python scripts/build_sce_environment_v2.py \
        --targets 2021-01..2021-12 \
        --out-prefix environment/environment_main2021_v2 [--fetch]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_sce_environment as v1  # noqa: E402
import build_nyt_events as nyt  # noqa: E402

STUDY_ID = v1.STUDY_ID
STUDY_DIR = v1.STUDY_DIR
COMPONENTS_JSONL = REPO_ROOT / "data/raw/bls_initial_releases/components_cpi.jsonl"
GAS_WEEKLY_CSV = REPO_ROOT / "data/raw/eia_gasoline/gasoline_retail_regular_weekly.csv"
NYT_LEDGER = REPO_ROOT / "data/raw/nyt_archive/events_ledger.jsonl"

COMPONENT_MEASURES = {
    "cpi_food_yoy": "CPI-U food 12-month percent change, not seasonally adjusted",
    "cpi_food_at_home_yoy": ("CPI-U food at home 12-month percent change, "
                             "not seasonally adjusted"),
    "cpi_energy_yoy": "CPI-U energy 12-month percent change, not seasonally adjusted",
    "cpi_shelter_yoy": "CPI-U shelter 12-month percent change, not seasonally adjusted",
    "cpi_gasoline_yoy": ("CPI-U gasoline (all types) 12-month percent change, "
                         "not seasonally adjusted"),
}


def shift_month(month: str, k: int) -> str:
    y, m = (int(x) for x in month.split("-"))
    total = y * 12 + (m - 1) + k
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def reference_period_v2(target_month: str) -> str:
    """Newest available reference period = M-1 (D050 median-respondent
    timing; v1 used M-2)."""
    return shift_month(target_month, -1)


EVENT_BUDGET = 30  # lower tiers share this; front_page+strong is uncapped


def _merge_event_pool(pool: list[dict], budget: int) -> list[dict]:
    """Select from a combined event pool with the same rules as
    build_nyt_events: tier front_page+strong never capped; lower tiers fill
    the budget hit-density first, recency breaks ties."""
    by_rank: dict[int, list[dict]] = {0: [], 1: [], 2: [], 3: []}
    for e in pool:
        by_rank[nyt._TIER_RANK[e["tier"]]].append(e)
    selected = sorted(by_rank[0], key=lambda e: e["pub_date"])
    for rank in (1, 2, 3):
        remaining = budget - len(selected)
        if remaining <= 0:
            break
        p = sorted(by_rank[rank], key=lambda e: e["pub_date"], reverse=True)
        p = sorted(p, key=lambda e: -len(e["matched_keywords"]))
        selected.extend(p[:remaining])
    selected.sort(key=lambda e: e["pub_date"])
    return selected


def _pub_et(d: date) -> str:
    return datetime(d.year, d.month, d.day, 8, 30,
                    tzinfo=v1.RELEASE_TZ).isoformat()


def load_components() -> dict[str, dict[str, dict]]:
    """ref -> signal_id -> component record (from extract_cpi_components)."""
    by_ref: dict[str, dict[str, dict]] = {}
    for line in COMPONENTS_JSONL.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        by_ref.setdefault(r["reference_period"], {})[r["signal_id"]] = r
    return by_ref


def load_gasoline_weekly() -> dict[str, dict]:
    """ref month -> {price_mean, yoy_pct, n_weeks, last_obs_date}."""
    by_month: dict[str, list[tuple[str, float]]] = {}
    with GAS_WEEKLY_CSV.open(newline="", encoding="utf-8") as fh:
        for rec in csv.DictReader(fh):
            by_month.setdefault(rec["observation_date"][:7], []).append(
                (rec["observation_date"], float(rec["gasoline_retail_regular"])))
    out = {}
    for month, obs in by_month.items():
        y, m = (int(x) for x in month.split("-"))
        prev = by_month.get(f"{y - 1:04d}-{m:02d}")
        vals = [v for _, v in obs]
        mean = sum(vals) / len(vals)
        row = {"price_mean": round(mean, 3), "n_weeks": len(vals),
               "last_obs_date": max(d for d, _ in obs)}
        if prev:
            prev_mean = sum(v for _, v in prev) / len(prev)
            row["yoy_pct"] = round((mean - prev_mean) / prev_mean * 100, 1)
        out[month] = row
    return out


def load_nyt_events() -> dict[str, list[dict]]:
    by_month: dict[str, list[dict]] = {}
    for line in NYT_LEDGER.read_text(encoding="utf-8").splitlines():
        e = json.loads(line)
        by_month.setdefault(e["month"], []).append(e)
    return by_month


def cpi_history_yoy(refs: list[str], raw_root: Path, fetch: bool,
                    proxy: str) -> dict[str, dict]:
    """First-release CPI all-items y/y for each ref, from the archived PDFs."""
    out = {}
    for ref in refs:
        info = v1.ensure_release("cpi", ref, raw_root / ref, fetch, proxy)
        cpi = v1.transcribe_cpi(v1._first_pages_text(info["path"]), ref)
        out[ref] = {
            "value": v1._clean_value(cpi["cpi_yoy_nsa_pct"]["value"]),
            "published_at": _pub_et(info["release_date"]),
            "source_version": f"USDL-{cpi['usdl']}",
            "source_url": v1.ARCHIVE_URL["cpi"].format(
                mmddyyyy=info["release_date"].strftime("%m%d%Y")),
            "source_sha256": hashlib.sha256(info["path"].read_bytes()).hexdigest(),
        }
    return out


def _unemployment_rate_only(text: str, ref: str) -> dict:
    """Extract only the unemployment rate from an employment release.
    Pandemic-era reports break v1.transcribe_empsit's nonfarm patterns
    (e.g. 2020-04 "fell by 20.5 million"), but the history sequence only
    needs the unemployment rate (D051)."""
    y, m = (int(x) for x in ref.split("-"))
    c = v1._compact(text)
    month = v1.MONTH_NAME[m - 1].lower()
    both_m = re.search(
        rf"nonfarmpayrollemployment\(?([+-]?[\d,]+)\)?andtheunemploymentrate"
        rf"\(?([\d.]+)percent\)?changedlittlein{month}", c)
    if both_m:
        return {"value": float(both_m.group(2)),
                "usdl": re.search(r"usdl-(\d{2}-\d{4})", c).group(1)}
    unemp_m = re.search(
        rf"unemploymentrate(?:fell|rose|declined|edgeddown|edgedup).*?to"
        rf"([\d.]+)percent", c)
    if not unemp_m:
        unemp_m = re.search(
            r"unemploymentrate(?:wasunchanged|changedlittle|waslittlechanged)"
            r"(?:at|from)([\d.]+)percent", c)
    if not unemp_m:
        raise ValueError(f"unemployment rate sentence not found for {ref}")
    return {"value": float(unemp_m.group(1)),
            "usdl": re.search(r"usdl-(\d{2}-\d{4})", c).group(1)}


def empsit_history_unemployment(refs: list[str], raw_root: Path, fetch: bool,
                                proxy: str) -> dict[str, dict]:
    """First-release unemployment rate for each ref, from the archived PDFs
    (D051: history sequence for the macro backdrop households perceive)."""
    out = {}
    for ref in refs:
        info = v1.ensure_release("empsit", ref, raw_root / ref, fetch, proxy)
        emp = _unemployment_rate_only(v1._first_pages_text(info["path"]), ref)
        out[ref] = {
            "value": v1._clean_value(emp["value"]),
            "published_at": _pub_et(info["release_date"]),
            "source_version": f"USDL-{emp['usdl']}",
            "source_url": v1.ARCHIVE_URL["empsit"].format(
                mmddyyyy=info["release_date"].strftime("%m%d%Y")),
            "source_sha256": hashlib.sha256(info["path"].read_bytes()).hexdigest(),
        }
    return out


# component signals that also get an 11-month history sequence (D051);
# food_at_home stays latest-only (redundant with food), gasoline is covered
# by the retail-price level sequence
HISTORY_COMPONENTS = {
    "cpi_food_yoy": COMPONENT_MEASURES["cpi_food_yoy"],
    "cpi_energy_yoy": COMPONENT_MEASURES["cpi_energy_yoy"],
    "cpi_shelter_yoy": COMPONENT_MEASURES["cpi_shelter_yoy"],
}


def build_window_v2(targets: list[str], raw_root: Path, fetch: bool,
                    proxy: str) -> dict:
    base = v1.build_window(targets, raw_root, fetch, proxy)  # skeleton only
    components = load_components()
    gasoline = load_gasoline_weekly()
    events_by_month = load_nyt_events()

    # history refs needed across the whole window (R-11..R-1 for each step)
    all_history_refs = sorted({shift_month(reference_period_v2(t), -k)
                               for t in targets for k in range(1, 12)})
    history = cpi_history_yoy(all_history_refs, raw_root, fetch, proxy)
    emp_history = empsit_history_unemployment(all_history_refs, raw_root,
                                              fetch, proxy)

    signals_by_step: dict[str, list[dict]] = {}
    events_by_step: dict[str, list[dict]] = {}
    as_of_by_step: dict[str, str] = {}
    broadcasts = []

    for step, target in enumerate(targets):
        ref = reference_period_v2(target)

        # 0. four BLS headline signals for ref M-1; as_of = the day the CPI
        #    for M-1 is released inside month M, 23:59:59 ET (D050)
        cpi_info = v1.ensure_release("cpi", ref, raw_root / ref, fetch, proxy)
        emp_info = v1.ensure_release("empsit", ref, raw_root / ref, fetch,
                                     proxy)
        cpi = v1.transcribe_cpi(v1._first_pages_text(cpi_info["path"]), ref)
        emp = v1.transcribe_empsit(v1._first_pages_text(emp_info["path"]), ref)
        pub_cpi = v1.published_at_for(cpi_info["release_date"])
        pub_emp = v1.published_at_for(emp_info["release_date"])
        rd = cpi_info["release_date"]
        as_of = datetime(rd.year, rd.month, rd.day, 23, 59, 59,
                         tzinfo=v1.RELEASE_TZ)
        if not datetime.fromisoformat(pub_emp) < as_of:
            raise ValueError(
                f"employment release for {ref} not before as_of {as_of}")
        url_cpi = v1.ARCHIVE_URL["cpi"].format(
            mmddyyyy=rd.strftime("%m%d%Y"))
        url_emp = v1.ARCHIVE_URL["empsit"].format(
            mmddyyyy=emp_info["release_date"].strftime("%m%d%Y"))
        records = [dict(r, role="latest_release")
                   for r in v1._signals_for_ref(ref, cpi, emp, url_cpi, url_emp,
                                                pub_cpi, pub_emp)]
        broadcasts.append(v1._broadcast(step, target, ref, cpi, emp))

        # 1. CPI components (same release as the headline CPI record)
        ref_components = components.get(ref)
        if not ref_components:
            raise ValueError(f"missing CPI components for ref {ref}")
        usdl, cpi_url = next(
            (r["source_version"], r["source_url"]) for r in records
            if r["signal_id"].startswith("bls_cpi_u_all_items_yoy"))
        for sig, measure in COMPONENT_MEASURES.items():
            c = ref_components[sig]
            records.append({
                "signal_id": f"bls_{sig}_nsa_{ref.replace('-', '_')}_initial",
                "measure": measure,
                "value": c["value"],
                "unit": "percent",
                "reference_period": ref,
                "published_at": _pub_et(date.fromisoformat(c["published_at"])),
                "source_version": usdl,
                # components come from the same release PDF as the headline
                "source_url": cpi_url,
                "eligibility": "eligible",
                "role": "latest_release",
            })

        # 2. history sequences (R-11..R-1, D049a/D051): headline CPI y/y,
        #    unemployment rate, food/energy/shelter component y/y, gasoline
        #    retail monthly mean level
        for k in range(11, 0, -1):
            h_ref = shift_month(ref, -k)
            h = history[h_ref]
            records.append({
                "signal_id": f"bls_cpi_u_all_items_yoy_nsa_{h_ref.replace('-', '_')}_initial",
                "measure": ("CPI-U all items 12-month percent change, "
                            "not seasonally adjusted"),
                "value": h["value"],
                "unit": "percent",
                "reference_period": h_ref,
                "published_at": h["published_at"],
                "source_version": h["source_version"],
                "source_url": h["source_url"],
                "eligibility": "eligible",
                "role": "history",
            })
            ue = emp_history[h_ref]
            records.append({
                "signal_id": f"bls_unemployment_rate_sa_{h_ref.replace('-', '_')}_initial",
                "measure": "Civilian unemployment rate, seasonally adjusted",
                "value": ue["value"],
                "unit": "percent",
                "reference_period": h_ref,
                "published_at": ue["published_at"],
                "source_version": ue["source_version"],
                "source_url": ue["source_url"],
                "eligibility": "eligible",
                "role": "history",
            })
            for sig, measure in HISTORY_COMPONENTS.items():
                c = components[h_ref][sig]
                records.append({
                    "signal_id": f"bls_{sig}_nsa_{h_ref.replace('-', '_')}_initial",
                    "measure": measure,
                    "value": c["value"],
                    "unit": "percent",
                    "reference_period": h_ref,
                    "published_at": h["published_at"],  # same CPI release
                    "source_version": h["source_version"],
                    "source_url": h["source_url"],
                    "eligibility": "eligible",
                    "role": "history",
                })
            g_h = gasoline[h_ref]
            gas_pub_h = (date.fromisoformat(g_h["last_obs_date"])
                         + timedelta(days=3)).isoformat() + "T17:00:00"
            records.append({
                "signal_id": f"eia_gasoline_retail_regular_mean_{h_ref.replace('-', '_')}",
                "measure": ("U.S. regular all formulations retail gasoline price, "
                            "monthly mean of weekly observations"),
                "value": g_h["price_mean"],
                "unit": "dollars_per_gallon",
                "reference_period": h_ref,
                "published_at": datetime.fromisoformat(gas_pub_h).replace(
                    tzinfo=v1.RELEASE_TZ).isoformat(),
                "source_version": "FRED GASREGW (EIA weekly retail, Monday obs)",
                "source_url": "https://fred.stlouisfed.org/series/GASREGW",
                "eligibility": "eligible",
                "role": "history",
                "note": ("monthly mean of weekly Monday observations; "
                         "published_at = last weekly obs + 3 days (conservative)"),
            })

        # 3. retail gasoline (level + y/y) for ref R
        g = gasoline.get(ref)
        if not g:
            raise ValueError(f"missing gasoline data for ref {ref}")
        gas_pub = (date.fromisoformat(g["last_obs_date"])
                   + timedelta(days=3)).isoformat() + "T17:00:00"
        gas_pub_dt = datetime.fromisoformat(gas_pub).replace(
            tzinfo=v1.RELEASE_TZ)
        gas_common = {
            "reference_period": ref,
            "published_at": gas_pub_dt.isoformat(),
            "source_version": "FRED GASREGW (EIA weekly retail, Monday obs)",
            "source_url": "https://fred.stlouisfed.org/series/GASREGW",
            "eligibility": "eligible",
            "role": "latest_release",
            "note": ("monthly mean of weekly Monday observations; "
                     "published_at = last weekly obs + 3 days (conservative)"),
        }
        records.append({
            "signal_id": f"eia_gasoline_retail_regular_mean_{ref.replace('-', '_')}",
            "measure": ("U.S. regular all formulations retail gasoline price, "
                        "monthly mean of weekly observations"),
            "value": g["price_mean"],
            "unit": "dollars_per_gallon",
            **gas_common,
        })
        if "yoy_pct" in g:
            records.append({
                "signal_id": f"eia_gasoline_retail_regular_yoy_{ref.replace('-', '_')}",
                "measure": ("Retail gasoline price 12-month percent change "
                            "(monthly means)"),
                "value": g["yoy_pct"],
                "unit": "percent",
                **gas_common,
            })

        # hard eligibility guard: everything strictly before as_of
        for r in records:
            if not datetime.fromisoformat(r["published_at"]) < as_of:
                raise ValueError(
                    f"record {r['signal_id']} published {r['published_at']} "
                    f"not before as_of {as_of.isoformat()}")
        signals_by_step[str(step)] = records
        as_of_by_step[str(step)] = as_of.isoformat()

        # 4. NYT salient events: all of month M-1 plus early M up to as_of
        #    (the CPI release day inside M); tier front_page+strong uncapped,
        #    lower tiers share EVENT_BUDGET (hit-density first, then recency).
        as_of_date = as_of.date()
        pool = list(events_by_month.get(shift_month(target, -1), []))
        pool.extend(e for e in events_by_month.get(target, [])
                    if date.fromisoformat(e["pub_date"]) <= as_of_date)
        for e in pool:
            if date.fromisoformat(e["pub_date"]) > as_of_date:
                raise ValueError(f"event {e['event_id']} after as_of")
        evs = [{k: e[k] for k in
                ("event_id", "pub_date", "tier", "headline", "abstract",
                 "section_name", "web_url", "matched_keywords")}
               for e in _merge_event_pool(pool, EVENT_BUDGET)]
        events_by_step[str(step)] = evs

    bundle = base["bundle"]
    bundle["provider_args"]["signals_by_step"] = signals_by_step
    bundle["provider_args"]["events_by_step"] = events_by_step
    bundle["provider_args"]["targets"] = [
        {"target_month": t, "as_of": as_of_by_step[str(i)]}
        for i, t in enumerate(targets)]
    bundle["provider_args"]["e_version"] = "v2"
    bundle["provider_args"]["e_v2_layers"] = [
        "bls_headline_4_signals", "bls_cpi_components_5",
        "eia_gasoline_retail_level_yoy",
        "bls_cpi_yoy_history_11m", "bls_unemployment_history_11m",
        "bls_cpi_component_history_3x11m", "eia_gasoline_level_history_11m",
        "nyt_salient_events_m_minus_1_through_as_of",
    ]
    bundle["information_program"]["broadcasts"] = broadcasts
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
         "source": "data/raw/nyt_archive/events_ledger.jsonl",
         "schema_ref": None,
         "description": ("NYT front-page (A1) + inflation-keyword events, "
                         "headline + abstract, published M-1-01 through the "
                         "CPI release day inside M (D049d/D050).")},
    ]

    external_events = base["external_events"]
    external_events["dataset_id"] = external_events["dataset_id"].replace(
        "_v1", "_v2")
    external_events["records_by_step"] = signals_by_step
    external_events["events_by_step"] = events_by_step
    external_events["as_of"] = as_of_by_step
    external_events["e_version"] = "v2"

    return {"bundle": bundle, "external_events": external_events,
            "targets": targets}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--targets", required=True)
    ap.add_argument("--out-prefix", required=True)
    ap.add_argument("--raw-root", default=str(v1.DEFAULT_RAW_ROOT))
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--proxy", default=v1.DEFAULT_PROXY)
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args()

    targets = v1.parse_targets(args.targets)
    raw_root = Path(args.raw_root)
    if not raw_root.is_absolute():
        raw_root = REPO_ROOT / raw_root

    result = build_window_v2(targets, raw_root, args.fetch, args.proxy)

    out_env = STUDY_DIR / f"{args.out_prefix}.json"
    stem = Path(args.out_prefix).name
    ext_path = STUDY_DIR / Path(args.out_prefix).parent / f"external_events_{stem}.json"
    sim_stem = re.sub(r"^environment", "simulation", stem)
    out_sim = STUDY_DIR / "simulation" / f"{sim_stem}.json"

    ext_rel = ext_path.relative_to(STUDY_DIR).as_posix()
    for layer in result["bundle"]["layers"]:
        if layer["name"].startswith("bls_") and layer["source"].endswith(
                "PLACEHOLDER.json"):
            layer["source"] = ext_rel

    sim = v1.simulation_config(targets)
    if not args.no_validate:
        v1.validate_with_official_schemas(result["bundle"], sim)

    v1._write_json(out_env, result["bundle"])
    v1._write_json(ext_path, result["external_events"])
    v1._write_json(out_sim, sim)

    n_sig = len(result["external_events"]["records_by_step"]["0"])
    n_ev = len(result["external_events"]["events_by_step"]["0"])
    print(f"targets={len(targets)}  records/step={n_sig}  events(step0)={n_ev}")
    print(f"wrote {out_env.relative_to(REPO_ROOT)}")
    print(f"wrote {ext_path.relative_to(REPO_ROOT)}")
    print(f"wrote {out_sim.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
