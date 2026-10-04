#!/usr/bin/env python3
"""Extract household-perceivable CPI component 12-month changes from the
archived BLS first-release PDFs (E v2 data layer, D049a/c).

Reads data/raw/bls_initial_releases/<ref-month>/cpi_*.pdf and extracts the
12-month percent change (not seasonally adjusted) for five components that
map to what households actually perceive:

  cpi_food_yoy          "the food index increased 2.4 percent [over the last 12 months]"
  cpi_food_at_home_yoy  "the food at home index increased 1.2 percent over the past 12 months"
  cpi_energy_yoy        "the energy index rose 25.1 percent over the last 12-months"
  cpi_shelter_yoy       "the shelter index increased 2.1 percent over the last 12 months"
  cpi_gasoline_yoy      text if present, else Table A row "Gasoline (all types)"

Every extracted value carries the exact source quote and PDF page. Values that
fail extraction or sanity checks go to the handoff list (per AGENTS.md rule 13,
handoff items are resolved with DeepSeek/manual transcription, never by burning
coding-agent context on full PDF reads).

    python scripts/extract_cpi_components.py \
        --archive data/raw/bls_initial_releases \
        --out data/raw/bls_initial_releases/components_cpi.jsonl \
        --handoff data/raw/bls_initial_releases/components_handoff.jsonl
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

UP = ("rose", "increased", "advanced", "grew", "climbed", "up",
      "rising", "increasing", "advancing", "growing", "climbing")
DOWN = ("fell", "declined", "decreased", "dropped", "down",
        "falling", "declining", "decreasing", "dropping")
VERBS = UP + DOWN
VERB_RE = "|".join(VERBS)

# (signal_id, list of regexes tried in order). Named groups:
#   num   (required) the percent number; may carry an explicit sign when the
#         source uses parenthetical "(+1.7 percent)" style (then verb is absent)
#   verb  (optional) direction verb; sign = verb sign * abs(num)
#   since (optional) "Month YYYY" for "rose X percent since May 2020" phrasing;
#         accepted only when it is exactly 12 months before the reference period
PATTERNS: dict[str, list[str]] = {
    "cpi_energy_yoy": [
        rf"[Tt]he energy index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12.?months",
        rf"[Ee]nergy index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12.?months",
        rf"[Tt]he energy index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent for the 12 months ending",
        rf"[Tt]he index for energy (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12.?months",
    ],
    "cpi_food_yoy": [
        rf"[Tt]he food index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent(?!\s+in\b)(?=[^.]*(?:12.?months|12-month))",
        rf"12.?months, and the food index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent(?: over that period)?(?!\s+in\b)",
        rf"[Tt]he food index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past)",
    ],
    "cpi_food_at_home_yoy": [
        rf"food at home index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12",
        rf"food at home index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the 12 months ending",
        rf"[Ii]ndex for food at home (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the 12 months ending",
        rf"[Ff]ood at home[^.]*?(?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12",
    ],
    "cpi_shelter_yoy": [
        rf"[Tt]he shelter index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12.?months",
        # parenthetical roundup style: "... 12 months. Among the indexes rising
        # ... shelter (+1.7 percent), ..." / "Indexes rising ... include
        # shelter (3.5 percent) ..." (sign comes from the number itself)
        r"12.?months\b[^%]{0,200}?rising\b[^%]{0,120}?shelter \(\+?(?P<num>-?\d+\.\d) percent\)",
        rf"[Ss]helter index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past)",
        # 2019-12..2020-08 phrasing
        rf"[Ss]helter index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the 12-month span",
        # 2020-08: value first, 12-month context trails in the same sentence
        rf"[Ss]helter index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent, and the [^%]{{0,120}}?over the (?:last|past) 12 months",
    ],
    # gasoline y/y often appears only in Table A; text pattern first.
    "cpi_gasoline_yoy": [
        rf"[Gg]asoline index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12.?months",
        rf"[Gg]asoline index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent since (?P<since>[A-Z][a-z]+ \d{{4}})",
        rf"[Gg]asoline index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the last year",
        rf"over the (?:last|past) 12.?months and the index for gasoline (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent",
        rf"index for gasoline (?P<verb>rising|falling) (?:by )?(?P<num>\d+\.\d) percent over the same period",
        # "energy index fell 9.4 percent over the past 12 months. Energy
        # commodity indexes fell sharply over the period, with ... the gasoline
        # index decreasing 19.3 percent." (2020-11/12 style)
        rf"over the (?:last|past) 12 months\.[^%]{{0,200}}?gasoline index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent(?!\s+in\b)",
        # 2019-12..2020-10 style: the 12-month window is set by the preceding
        # energy sentence ("... over the past 12 months, with its major
        # component indexes mixed. The gasoline index increased 12.8 percent,")
        rf"energy index (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12 months[^%]{{0,200}}?[Tt]he gasoline index (?P<gverb>{VERB_RE}) (?:by )?(?P<gnum>\d+\.\d) percent(?!\s+in\b)",
        rf"[Tt]he index for gasoline (?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past)",
    ],
}

# Table A fallback rows: (signal_id, row label prefix). NOTE: with pypdf the
# Table A body usually does not linearize (row labels are not found in the
# extracted text), so in practice this fallback rarely fires; when it does, the
# unadjusted 12-month change is the first number after the run of >=100 index
# level values (row layout: relative importance, index levels, 12-mo, monthly).
TABLE_A_ROWS = {
    "cpi_gasoline_yoy": "Gasoline (all types)",
    "cpi_energy_yoy": "Energy ",
    "cpi_food_at_home_yoy": "Food at home",
    "cpi_shelter_yoy": "Shelter",
}

SANITY = {  # generous physical bounds for 2020-2026 US CPI components
    "cpi_food_yoy": (-5.0, 30.0),
    "cpi_food_at_home_yoy": (-5.0, 30.0),
    "cpi_energy_yoy": (-60.0, 70.0),
    "cpi_shelter_yoy": (-2.0, 15.0),
    "cpi_gasoline_yoy": (-70.0, 90.0),
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# pypdf kerning artifacts observed in BLS releases: single letters split off
# at paragraph/section starts ("Th e food at home index", "e nergy index").
# Literal token fixes only — do NOT do generic single-letter merges.
_ARTIFACT_FIXES = [
    ("Th e ", "The "), ("T he ", "The "), ("No t ", "Not "), ("A ll ", "All "),
    ("E nergy", "Energy"), ("e nergy", "energy"),
    ("f ood", "food"), ("i ndex", "index"),
]


def _page_texts(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader
    texts = []
    for pg in PdfReader(pdf_path).pages:
        text = re.sub(r"\s+", " ", pg.extract_text() or "")
        for bad, good in _ARTIFACT_FIXES:
            text = text.replace(bad, good)
        texts.append(text)
    return texts


def _verb_sign(verb: str) -> int:
    v = verb.lower()
    if v in UP:
        return 1
    if v in DOWN:
        return -1
    raise ValueError(f"unknown verb {verb!r}")


_MONTHS = {m: i + 1 for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"))}


def _since_is_12m(since: str, ref_period: str) -> bool:
    """True when "May 2020" is exactly 12 months before ref_period "2021-05"."""
    month_name, year_s = since.split()
    ref_y, ref_m = (int(x) for x in ref_period.split("-"))
    return (ref_y * 12 + ref_m) - (int(year_s) * 12 + _MONTHS[month_name]) == 12


def _extract_from_text(pages: list[str], signal: str, ref_period: str) -> dict | None:
    for page_no, text in enumerate(pages, 1):
        for pat in PATTERNS[signal]:
            for m in re.finditer(pat, text):
                groups = m.groupdict()
                # patterns anchoring on a preceding energy sentence capture the
                # target value in gverb/gnum instead
                verb = groups.get("gverb") or groups.get("verb")
                num_s = groups.get("gnum") or groups.get("num")
                since = groups.get("since")
                if since and not _since_is_12m(since, ref_period):
                    continue
                num = float(num_s)
                value = num if verb is None else _verb_sign(verb) * abs(num)
                quote = text[max(0, m.start() - 60):m.end() + 40].strip()
                return {"value": value, "quote": quote, "page": page_no,
                        "pattern": pat[:60], "extraction": "text"}
    return None


def _extract_from_table_a(pages: list[str], signal: str) -> dict | None:
    label = TABLE_A_ROWS.get(signal)
    if not label:
        return None
    for page_no, text in enumerate(pages, 1):
        if "Table A" not in text:
            continue
        idx = text.find(label)
        while idx != -1:
            row = text[idx:idx + 220]
            nums = [float(x) for x in re.findall(r"-?\d+\.\d", row)]
            # first number after the run of >=100 index level values
            for i in range(len(nums) - 3):
                if all(v >= 100 for v in nums[i:i + 3]):
                    value = nums[i + 3]
                    return {"value": value, "quote": row.strip()[:200], "page": page_no,
                            "pattern": f"tableA:{label.strip()}", "extraction": "table_a"}
            idx = text.find(label, idx + 1)
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--archive", type=Path, default=ROOT / "data/raw/bls_initial_releases")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "data/raw/bls_initial_releases/components_cpi.jsonl")
    ap.add_argument("--handoff", type=Path,
                    default=ROOT / "data/raw/bls_initial_releases/components_handoff.jsonl")
    args = ap.parse_args(argv)

    records, handoff = [], []
    pdfs = sorted(args.archive.glob("*/cpi_*.pdf"))
    if not pdfs:
        sys.exit(f"no CPI PDFs under {args.archive}")
    for pdf in pdfs:
        ref = pdf.parent.name
        m = re.match(r"cpi_(\d{4})_(\d{2})_released_(\d{4})_(\d{2})_(\d{2})\.pdf", pdf.name)
        if not m:
            handoff.append({"pdf": str(pdf.relative_to(ROOT)),
                            "reason": "filename does not match expected pattern"})
            continue
        ref_period, published = f"{m.group(1)}-{m.group(2)}", f"{m.group(3)}-{m.group(4)}-{m.group(5)}"
        digest = _sha256(pdf)
        pages = _page_texts(pdf)
        for signal in PATTERNS:
            hit = (_extract_from_text(pages, signal, ref_period)
                   or _extract_from_table_a(pages, signal))
            base = {"reference_period": ref_period, "published_at": published,
                    "source_pdf": str(pdf.relative_to(ROOT)), "source_sha256": digest,
                    "signal_id": signal, "unit": "percent_12m_nsa"}
            if hit is None:
                handoff.append({**base, "reason": "no text/TableA pattern matched"})
                continue
            lo, hi = SANITY[signal]
            if not (lo <= hit["value"] <= hi):
                handoff.append({**base, **hit, "reason": f"sanity range [{lo},{hi}] violated"})
                continue
            records.append({**base, **hit})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    with args.handoff.open("w", encoding="utf-8") as fh:
        for r in handoff:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_expected = len(pdfs) * len(PATTERNS)
    print(f"PDFs: {len(pdfs)}; extracted {len(records)}/{n_expected} component values; "
          f"handoff: {len(handoff)}")
    by_signal: dict[str, int] = {}
    for r in handoff:
        by_signal[r["signal_id"]] = by_signal.get(r["signal_id"], 0) + 1
    if by_signal:
        print("handoff by signal:", by_signal)
    print(f"wrote {args.out} and {args.handoff}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
