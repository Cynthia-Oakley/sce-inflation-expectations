#!/usr/bin/env python3
"""Append E source caches and prepare an isolated candidate, never run simulation.

Default is an offline inventory. --fetch downloads missing public BLS PDFs;
--fetch-nyt additionally uses the existing NYT credential (never logged).
Each invocation writes a new output directory. No existing ledger, component
file, study configuration or cached source is overwritten.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import build_sce_environment as bls
import build_sce_environment_v2 as ev
import build_nyt_events as nyt
import extract_cpi_components as components

ROOT = Path(__file__).resolve().parents[1]


def requirements(targets: list[str]) -> dict:
    if not targets:
        raise ValueError("empty target range")
    for month in targets:
        date.fromisoformat(month + "-01")
    refs = sorted({ev.shift_month(t, -k) for t in targets for k in range(1, 13)})
    news = sorted(set(targets) | {ev.shift_month(t, -1) for t in targets})
    return {"targets": targets, "bls_reference_months": refs, "nyt_months": news}


def calendar_entries(text: str, source: str) -> dict:
    """Read previously archived official annual calendar, not date guesses."""
    month_numbers = {calendar.month_name[k]: k for k in range(1, 13)}
    pattern = re.compile(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday),\s+"
        r"([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})\s+08:30 AM\s+"
        r"(Consumer Price Index|Employment Situation) for ([A-Z][a-z]+) (\d{4})")
    result = {}
    for match in pattern.finditer(text):
        rm, rd, ry, label, om, oy = match.groups()
        ref = f"{oy}-{month_numbers[om]:02d}"
        kind = "cpi" if label == "Consumer Price Index" else "empsit"
        entry = {"release_date": date(int(ry), month_numbers[rm], int(rd)).isoformat(),
                 "calendar_source": source, "calendar_quote": match.group(0)}
        if (kind, ref) in result and result[(kind, ref)] != entry:
            raise ValueError("conflicting calendar entry")
        result[kind, ref] = entry
    return result


def read_calendars() -> dict:
    result = {}
    for folder in (ROOT / "data/raw/sce_baselines_20261007",
                   ROOT / "data/raw/sce_baselines_latest_20261007"):
        for path in sorted(folder.glob("bls_schedule_*.web.txt")):
            result.update(calendar_entries(path.read_text(), str(path.relative_to(ROOT))))
    return result


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))


def cached_pdf(kind: str, ref: str) -> Path | None:
    matches = sorted((bls.DEFAULT_RAW_ROOT / ref).glob(f"{kind}_*_released_*.pdf"))
    if len(matches) > 1:
        raise ValueError(f"ambiguous cache: {kind} {ref}")
    return matches[0] if matches else None


def download_bytes(url: str, proxy: str, *, secret: bool = False) -> bytes:
    import httpx
    try:
        with httpx.Client(proxy=proxy or None, headers=bls.BROWSER_HEADERS,
                          timeout=180, follow_redirects=True) as client:
            response = client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")
        return response.content
    except Exception as exc:
        # HTTP exception messages may include NYT's credential in its query URL.
        detail = str(exc) if not secret and isinstance(exc, RuntimeError) else type(exc).__name__
        raise RuntimeError(f"download failed: {detail}") from None


def prepare_pdf(kind: str, ref: str, schedules: dict, fetch: bool,
                proxy: str) -> dict:
    path = cached_pdf(kind, ref)
    entry = schedules.get((kind, ref))
    fetched = False
    if path is None:
        if not fetch:
            raise FileNotFoundError(f"missing {kind} {ref}")
        if entry is None:
            raise ValueError(f"official calendar unavailable for {kind} {ref}")
        rd = date.fromisoformat(entry["release_date"])
        url = bls.ARCHIVE_URL[kind].format(mmddyyyy=rd.strftime("%m%d%Y"))
        dest = bls.DEFAULT_RAW_ROOT / ref
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{kind}_{ref.replace('-', '_')}_released_{rd:%Y_%m_%d}.pdf"
        tmp = path.with_suffix(".part")
        tmp.write_bytes(download_bytes(url, proxy))
        try:
            text = bls._first_pages_text(tmp)
            if not bls._verify_document(kind, ref, rd, text):
                raise ValueError(f"embargo/reference mismatch: {kind} {ref}")
            # Exclusive create: never replace an archive that appeared meanwhile.
            with path.open("xb") as handle:
                handle.write(tmp.read_bytes())
        finally:
            tmp.unlink(missing_ok=True)
        fetched = True
        time.sleep(1.5)
    rd = date.fromisoformat(path.stem.split("_released_")[1].replace("_", "-"))
    text = bls._first_pages_text(path)
    if not bls._verify_document(kind, ref, rd, text):
        raise ValueError(f"cached PDF embargo/reference mismatch: {kind} {ref}")
    if entry and entry["release_date"] != rd.isoformat():
        raise ValueError(f"calendar/PDF disagreement: {kind} {ref}")
    return {"kind": kind, "reference_period": ref, "file": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "published_at": bls.published_at_for(rd), "fetched_this_run": fetched,
            "source_url": bls.ARCHIVE_URL[kind].format(mmddyyyy=rd.strftime("%m%d%Y")),
            "verified_from": "PDF embargo/date/reference and cached official calendar when available",
            "retrieved_at_this_run": datetime.now(timezone.utc).isoformat() if fetched else None,
            "calendar": entry}


def prepare_news(month: str, fetch: bool, proxy: str, key: str | None) -> dict:
    folder = nyt.ROOT / "data/raw/nyt_archive"
    path = folder / f"{month}.json"
    if not path.exists():
        if not fetch:
            raise FileNotFoundError(f"missing NYT {month}")
        y, m = month.split("-")
        url = nyt.ARCHIVE_URL.format(y=int(y), m=int(m), key=key)
        payload = download_bytes(url, proxy, secret=True)
        data = json.loads(payload)
        if not isinstance(data.get("response", {}).get("docs"), list):
            raise ValueError("NYT missing response.docs")
        folder.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(payload)
        write_json(folder / f"{month}.meta.json", {
            "month": month, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source_url": f"https://api.nytimes.com/svc/archive/v1/{int(y)}/{int(m)}.json",
            "sha256": hashlib.sha256(payload).hexdigest(), "n_docs": len(data["response"]["docs"])})
    payload = path.read_bytes()
    meta_path = folder / f"{month}.meta.json"
    if not meta_path.exists():
        raise ValueError(f"missing NYT cache manifest: {month}")
    meta = json.loads(meta_path.read_text())
    data = json.loads(payload)
    if meta.get("month") != month or meta.get("sha256") != hashlib.sha256(payload).hexdigest():
        raise ValueError(f"NYT cache manifest/hash mismatch: {month}")
    docs = data.get("response", {}).get("docs")
    if not isinstance(docs, list) or meta.get("n_docs") != len(docs):
        raise ValueError(f"NYT cache row count mismatch: {month}")
    return data


def extract_components(records: list) -> tuple[list, list]:
    rows, failures = [], []
    for record in records:
        if record["kind"] != "cpi":
            continue
        pages = components._page_texts(ROOT / record["file"])
        for signal in components.PATTERNS:
            base = {"reference_period": record["reference_period"],
                    "published_at": record["published_at"][:10], "signal_id": signal,
                    "source_pdf": record["file"], "source_sha256": record["sha256"],
                    "unit": "percent_12m_nsa"}
            if signal == "cpi_energy_yoy":
                # Old unanchored 'energy index' can match the tail of 'all
                # items less food and energy index'. Require the named subject.
                hit = energy_annual_only(pages)
            else:
                hit = (components._extract_from_text(pages, signal, record["reference_period"])
                       or components._extract_from_table_a(pages, signal)
                       or component_wording_fallback(pages, signal))
            lo, hi = components.SANITY[signal]
            if not hit or not lo <= hit["value"] <= hi:
                failures.append({**base, "reason": "no valid deterministic extraction"})
            else:
                rows.append({**base, **hit})
    return rows, failures


def energy_annual_only(pages: list[str]) -> dict | None:
    pattern = (r"[Tt]he (?:energy index|index for energy) "
               r"(?P<verb>rose|increased|fell|declined|decreased|dropped) "
               r"(?P<num>\d+\.\d) percent "
               r"(?:over the (?:last|past) (?:12.?months|year)|for the 12 months ending)")
    for page_no, text in enumerate(pages, 1):
        match = re.search(pattern, text)
        if match:
            value = components._verb_sign(match.group("verb")) * float(match.group("num"))
            return {"value": value, "quote": match.group(0), "page": page_no,
                    "pattern": pattern, "extraction": "exact_energy_annual_subject"}
    return None


def component_wording_fallback(pages: list[str], signal: str) -> dict | None:
    """Three bounded annual-context variants found in 2022; no monthly fallback."""
    patterns = {
        "cpi_food_yoy": [
            r"[Ee]nergy index (?:rose|increased) \d+\.\d percent over the last year, "
            r"and the food index (?P<verb>increased|rose) (?P<num>\d+\.\d) percent",
        ],
        "cpi_shelter_yoy": [
            r"over the (?:past|last) 12.?months[^.]{0,150}\. "
            r"Major contributors to this increase include shelter \(\+(?P<num>\d+\.\d) percent\)",
            r"[Tt]he shelter index also (?P<verb>rose|increased) (?P<num>\d+\.\d) percent over the last year",
        ],
    }
    for page_no, text in enumerate(pages, 1):
        for pattern in patterns.get(signal, []):
            match = re.search(pattern, text)
            if match:
                return {"value": float(match.group("num")),
                        "quote": text[match.start():match.end()], "page": page_no,
                        "pattern": pattern, "extraction": "annual_context_extension"}
    return None


def check_component_html(rows: list) -> list:
    """Independent cached official HTML Table A, never the PDF text extractor.

    Table A's final column is NSA twelve-month change; earlier columns are
    monthly SA changes. Missing source/table rows remain explicitly unchecked.
    """
    labels = {"cpi_food_yoy": "Food", "cpi_food_at_home_yoy": "Food at home",
              "cpi_energy_yoy": "Energy", "cpi_shelter_yoy": "Shelter",
              "cpi_gasoline_yoy": "Gasoline (all types)"}
    result = []
    for row in rows:
        stamp = row["published_at"].replace("-", "")
        source = next((p for folder in ("sce_environment_extension_html",
                                       "sce_baselines_20261007", "sce_baselines_latest_20261007")
                       if (p := ROOT / "data/raw" / folder / f"cpi_{stamp}.web.txt").exists()), None)
        check = {"reference_period": row["reference_period"], "signal_id": row["signal_id"],
                 "pdf_value": row["value"], "status": "unchecked_no_table_row"}
        if source:
            text = source.read_text()
            start = text.find("Table A.")
            # The archived web snapshots used here include Table A before any
            # detailed tables. Match an exact row label, not prose or subgroups.
            table = text[start:] if start >= 0 else ""
            for boundary in ("Table 1.", "Table 2."):
                if boundary in table:
                    table = table.split(boundary, 1)[0]
            pattern = r"^(?:L\d+:\s*)?" + re.escape(labels[row["signal_id"]]) + r"\s*\|([^\n]+)"
            match = re.search(pattern, table, re.M)
            if match:
                cells = [v.strip() for v in match.group(1).split("|")]
                try:
                    html_value = float(cells[-1])
                except ValueError:
                    pass
                else:
                    check.update(html_value=html_value,
                                 source_file=str(source.relative_to(ROOT)),
                                 source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                                 source_quote=match.group(0),
                                 status="agree" if abs(html_value-row["value"]) < 1e-9 else "disagree")
            else:
                # Older BLS archives expose plain fixed-width Table A, with
                # dotted leaders and seven monthly columns plus annual change.
                pattern = (r"^(?:L\d+:\s*)?\s*" + re.escape(labels[row["signal_id"]])
                           + r"\.{2,}\s+([^\n]+)")
                match = re.search(pattern, table, re.M)
                if match:
                    numbers = re.findall(r"[-+]?(?:\d+\.\d+|\.\d+)", match.group(1))
                    if len(numbers) == 8:
                        html_value = float(numbers[-1])
                        check.update(html_value=html_value,
                                     source_file=str(source.relative_to(ROOT)),
                                     source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                                     source_quote=match.group(0),
                                     status="agree" if abs(html_value-row["value"]) < 1e-9 else "disagree")
        result.append(check)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--targets", required=True)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--fetch-nyt", action="store_true")
    ap.add_argument("--build-candidate", action="store_true")
    ap.add_argument("--proxy", default=bls.DEFAULT_PROXY)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    needs = requirements(bls.parse_targets(args.targets))
    out = args.out or ROOT / "outputs" / ("sce_e_extension_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    out.mkdir(parents=True, exist_ok=False)
    schedules = read_calendars()
    plan = {**needs, "missing_bls": [
        {"kind": kind, "reference_period": ref, "calendar_available": (kind, ref) in schedules}
        for ref in needs["bls_reference_months"] for kind in ("cpi", "empsit")
        if cached_pdf(kind, ref) is None], "missing_nyt": [
        m for m in needs["nyt_months"] if not (nyt.ROOT / "data/raw/nyt_archive" / f"{m}.json").exists()],
        "scope": "source preparation only; no simulation or test-window freeze",
        "as_of_policy": "existing E v2 current-month CPI release-day EOD; not B previous-month-end"}
    write_json(out / "plan.json", plan)
    print(f"Output: {out}\nMissing BLS: {len(plan['missing_bls'])}; NYT: {len(plan['missing_nyt'])}", flush=True)
    if not (args.fetch or args.fetch_nyt or args.build_candidate):
        return 0
    records, events, issues = [], [], []
    for ref in needs["bls_reference_months"]:
        for kind in ("cpi", "empsit"):
            try:
                records.append(prepare_pdf(kind, ref, schedules, args.fetch, args.proxy))
                print(f"BLS {kind} {ref}: verified", flush=True)
            except Exception as exc:
                issues.append({"source": kind, "month": ref, "reason": str(exc)})
                print(f"BLS {kind} {ref}: pending", flush=True)
    write_json(out / "bls_manifest.json", records)
    extracted, handoff = extract_components(records)
    write_jsonl(out / "components_cpi.jsonl", extracted)
    write_jsonl(out / "components_handoff.jsonl", handoff)
    html_checks = check_component_html(extracted)
    write_json(out / "component_html_checks.json", html_checks)
    issues.extend({"source": "component_html_comparison", **r}
                  for r in html_checks if r["status"] == "disagree")
    key = nyt.load_api_key(ROOT / ".env") if args.fetch_nyt and plan["missing_nyt"] else None
    last_request = None
    for month in needs["nyt_months"]:
        path = nyt.ROOT / "data/raw/nyt_archive" / f"{month}.json"
        will_fetch = args.fetch_nyt and not path.exists()
        if will_fetch:
            if last_request is not None:
                time.sleep(max(0, 15 - (time.monotonic() - last_request)))
            last_request = time.monotonic()
        try:
            data = prepare_news(month, args.fetch_nyt, args.proxy, key)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            events.extend(nyt.select_events(data["response"]["docs"], month, digest, 30))
            print(f"NYT {month}: cached", flush=True)
        except Exception as exc:
            issues.append({"source": "nyt", "month": month, "reason": str(exc)})
            print(f"NYT {month}: pending", flush=True)
            if will_fetch:
                # Stop new authenticated calls after a failure; leave remaining gaps explicit.
                args.fetch_nyt = False
    write_jsonl(out / "events_ledger.jsonl", events)
    candidate_written = False
    if args.build_candidate and not issues and not handoff:
        old = ev.COMPONENTS_JSONL, ev.NYT_LEDGER
        try:
            ev.COMPONENTS_JSONL, ev.NYT_LEDGER = out / "components_cpi.jsonl", out / "events_ledger.jsonl"
            candidate = ev.build_window_v2(needs["targets"], bls.DEFAULT_RAW_ROOT, False, args.proxy)
            write_json(out / "environment_candidate.json", candidate["bundle"])
            write_json(out / "external_events_candidate.json", candidate["external_events"])
            candidate_written = True
        except Exception as exc:
            issues.append({"source": "candidate_build", "reason": str(exc)})
        finally:
            ev.COMPONENTS_JSONL, ev.NYT_LEDGER = old
    summary = {"targets": needs["targets"], "verified_bls_pdfs": len(records),
               "components_extracted": len(extracted), "component_handoff_count": len(handoff),
               "component_html_agreement_count": sum(r["status"] == "agree" for r in html_checks),
               "component_html_unchecked_count": sum(r["status"].startswith("unchecked") for r in html_checks),
               "selected_completed_month_news": len(events), "issues": issues,
               "candidate_written": candidate_written, "real_llm_calls": 0,
               "paid_mcp_calls": 0, "nyt_text_vintage": "unverified_archive_snapshot",
               "gasoline_vintage": "current_snapshot_unverified; publication date remains assumption"}
    write_json(out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0 if not issues and not handoff and (not args.build_candidate or candidate_written) else 2


if __name__ == "__main__":
    raise SystemExit(main())
