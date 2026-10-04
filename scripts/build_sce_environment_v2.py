#!/usr/bin/env python3
"""Build the E v2 information environment for sce_inflation_expectations.

E v2 (D049a/c/d) extends the frozen v1 layer (4 BLS headline signals per step)
with, for every target month M (release reference period R = M-2, as_of = end
of M-1 23:59:59 ET):

  1. CPI component latest values (first-release, from the archived PDFs via
     extract_cpi_components.py): food, food at home, energy, shelter, gasoline
     12-month changes — the prices households actually perceive.
  2. Headline CPI y/y history: the trailing first-release values for refs
     R-11..R-1 (sequence, not just the latest point).
  3. Retail gasoline price (EIA via FRED GASREGW): monthly mean level + y/y
     change for ref R; published_at = last weekly observation + 3 days
     (documented conservative convention; EIA releases weekly prices within
     days of the Monday observation).
  4. NYT salient events (build_nyt_events.py ledger): headline + abstract for
     events published in month M-1, i.e. strictly before as_of.

Every record carries reference_period / published_at / source and a hard
assert guarantees published_at < as_of. The v1 bundle is rebuilt in memory
(v1.build_window) and extended — v1 output files are never touched.

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


def build_window_v2(targets: list[str], raw_root: Path, fetch: bool,
                    proxy: str) -> dict:
    base = v1.build_window(targets, raw_root, fetch, proxy)
    components = load_components()
    gasoline = load_gasoline_weekly()
    events_by_month = load_nyt_events()

    # history refs needed across the whole window (R-11..R-1 for each step)
    all_history_refs = sorted({shift_month(v1.reference_period(t), -k)
                               for t in targets for k in range(1, 12)})
    history = cpi_history_yoy(all_history_refs, raw_root, fetch, proxy)

    signals_by_step: dict[str, list[dict]] = {}
    events_by_step: dict[str, list[dict]] = {}
    as_of_by_step: dict[str, str] = {}

    for step, target in enumerate(targets):
        ref = v1.reference_period(target)
        as_of = datetime.fromisoformat(v1.as_of_for(target))
        records = [dict(r, role="latest_release")
                   for r in base["bundle"]["provider_args"]
                              ["signals_by_step"][str(step)]]

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

        # 2. headline CPI y/y history (R-11..R-1)
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

        # 4. NYT salient events from month M-1 (all strictly before as_of)
        ev_month = shift_month(target, -1)
        evs = []
        for e in events_by_month.get(ev_month, []):
            if date.fromisoformat(e["pub_date"]) > as_of.date():
                raise ValueError(f"event {e['event_id']} after as_of")
            evs.append({k: e[k] for k in
                        ("event_id", "pub_date", "tier", "headline", "abstract",
                         "section_name", "web_url", "matched_keywords")})
        events_by_step[str(step)] = evs

    bundle = base["bundle"]
    bundle["provider_args"]["signals_by_step"] = signals_by_step
    bundle["provider_args"]["events_by_step"] = events_by_step
    bundle["provider_args"]["e_version"] = "v2"
    bundle["provider_args"]["e_v2_layers"] = [
        "bls_headline_4_signals", "bls_cpi_components_5",
        "bls_cpi_yoy_history_11m", "eia_gasoline_retail_level_yoy",
        "nyt_salient_events_m_minus_1",
    ]
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
         "description": ("Trailing 11 first-release CPI all-items y/y values "
                         "per step (sequence, D049a).")},
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
                         "headline + abstract, pub month M-1 (D049d).")},
    ]

    external_events = base["external_events"]
    external_events["dataset_id"] = external_events["dataset_id"].replace(
        "_v1", "_v2")
    external_events["records_by_step"] = signals_by_step
    external_events["events_by_step"] = events_by_step
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
