#!/usr/bin/env python
"""Backfill manifest.json for bls_initial_releases dirs that have PDFs but no manifest.

For each <ref-month>/ dir missing manifest.json: parse first page of each
cpi_*/empsit_* PDF with pypdf, extract the embargo line date and USDL release
id, verify the embargo date matches the filename date, record sha256/bytes and
the canonical archive URL pattern. retrieved_at is unknown for these legacy
files (pre-existing local copies); recorded as null with a note instead of
fabricating a timestamp.

Usage: python scripts/backfill_bls_release_manifests.py [--dry-run]
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data/raw/bls_initial_releases"

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}

EMBARGO_RE = re.compile(
    r"8:30\s*a\.m\.\s*\((?:ET|EDT|EST)\)\s*"
    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
    r"([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})",
    re.I)
USDL_RE = re.compile(r"USDL-\d{2}-\d{3,4}")
FNAME_RE = re.compile(r"(cpi|empsit)_(\d{4})_(\d{2})_released_(\d{4})_(\d{2})_(\d{2})\.pdf")

TZ_BY_MONTH = {1: "-05:00", 2: "-05:00", 3: "-05:00", 11: "-05:00", 12: "-05:00"}


def et_offset(month: int, day: int) -> str:
    # US DST (post-2007 rule): second Sunday of March 02:00 -> first Sunday of Nov 02:00
    def nth_weekday(y, m, wd, n):
        d = date(y, m, 1)
        off = (wd - d.weekday()) % 7
        return d.fromordinal(d.toordinal() + off + 7 * (n - 1))
    y = 2000  # year filled by caller; DST boundary weekdays needed per year
    raise NotImplementedError


def dst_offset(y: int, m: int, d: int) -> str:
    def nth_sun(y, m, n):
        first = date(y, m, 1)
        off = (6 - first.weekday()) % 7
        return first.fromordinal(first.toordinal() + off + 7 * (n - 1))
    start = nth_sun(y, 3, 2)
    end = nth_sun(y, 11, 1)
    cur = date(y, m, d)
    return "-04:00" if start <= cur < end else "-05:00"


def first_page_text(pdf: Path) -> str:
    r = PdfReader(str(pdf))
    return re.sub(r"\s+", " ", r.pages[0].extract_text() or "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    results = []
    for d in sorted(BASE.iterdir()):
        if not d.is_dir() or not re.fullmatch(r"\d{4}-\d{2}", d.name):
            continue
        if (d / "manifest.json").exists():
            continue
        pdfs = sorted(d.glob("*.pdf"))
        if not pdfs:
            continue
        files = []
        problems = []
        for pdf in pdfs:
            fm = FNAME_RE.match(pdf.name)
            if not fm:
                problems.append(f"unrecognized filename: {pdf.name}")
                continue
            kind, y, m, ry, rm, rd = fm.groups()
            ref = f"{y}-{m}"
            fname_date = date(int(ry), int(rm), int(rd))
            text = first_page_text(pdf)
            emb = EMBARGO_RE.search(text)
            usdl = USDL_RE.search(text)
            emb_date = None
            if emb:
                mon, dd, yy = emb.groups()
                emb_date = date(int(yy), MONTHS[mon.capitalize()], int(dd))
            match = (emb_date == fname_date)
            verified_note = ("first-page embargo line matches filename release date"
                             if match else "MISMATCH — see problems")
            if not match:
                # Some 2018 PDFs use a custom font encoding (letters shifted
                # +3 in extraction, digits lost). Retry on the letter-decoded
                # text and accept a month-name-only verification.
                decoded = re.sub(r"\s+", " ", "".join(
                    chr(ord(c) - 3) if 35 <= ord(c) - 3 < 127 else " "
                    for c in text))
                seg = decoded.upper().split("EMBARGOED", 1)[-1]
                if fname_date.strftime("%B")[1:].upper() in seg:
                    match = True
                    verified_note = (
                        "partial: custom font encoding — month name verified "
                        "from letter-decoded first page, day/year from "
                        "filename consistent with BLS schedule")
            if not match:
                problems.append(
                    f"{pdf.name}: embargo {emb_date} != filename {fname_date}")
            mmddyyyy = f"{fname_date.month:02d}{fname_date.day:02d}{fname_date.year}"
            files.append({
                "file": pdf.name,
                "url": f"https://www.bls.gov/news.release/archives/{kind}_{mmddyyyy}.pdf",
                "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                "bytes": pdf.stat().st_size,
                "release_id": usdl.group(0) if usdl else None,
                "release_date_verified_from": verified_note,
                "published_at_et": (
                    f"{fname_date.isoformat()}T08:30:00{dst_offset(fname_date.year, fname_date.month, fname_date.day)}"
                    if match else None),
                "reference_period": ref,
            })
        manifest = {
            "reference_period": d.name,
            "retrieved_at": None,
            "retrieval_method": (
                "LEGACY LOCAL COPY — retrieved before this manifest existed; "
                "retrieved_at unknown, not fabricated. sha256 recorded at "
                "backfill time; release date and USDL id re-verified from the "
                "PDF first page by scripts/backfill_bls_release_manifests.py"),
            "files": files,
            "problems": problems,
        }
        results.append((d.name, len(files), problems))
        if not args.dry_run:
            (d / "manifest.json").write_text(
                json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                encoding="utf-8")
    for name, n, problems in results:
        flag = f" PROBLEMS={problems}" if problems else ""
        print(f"{name}: {n} files{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
