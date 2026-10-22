#!/usr/bin/env python3
"""Extract headline CPI-U all-items 12-month change from archived BLS
first-release PDFs (regime-label support, Codex task priority 3B).

Reuses extract_cpi_components' page extraction, pattern matching and sanity
machinery verbatim (its PATTERNS/SANITY module globals are swapped in for the
headline signal, so the matching logic is identical to the audited component
extraction). Output rows carry reference_period/published_at/source sha256,
the exact quote and page, like components_cpi.jsonl. Failures go to the
handoff list for DeepSeek/manual transcription (AGENTS.md rule 13) — never
silently dropped.

    python scripts/extract_cpi_headline.py \
        --archive data/raw/bls_initial_releases \
        --out data/raw/bls_initial_releases/headline_cpi.jsonl \
        --handoff data/raw/bls_initial_releases/headline_handoff.jsonl
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_cpi_components as ec  # noqa: E402

VERB_RE = ec.VERB_RE

# Headline 12-month phrasings observed in BLS first releases 2013-2026.
# "all items index" must NOT be followed by "less food and energy".
HEADLINE_PATTERNS = {
    "cpi_all_items_yoy": [
        rf"[Tt]he all items index (?!less)(?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12.?months",
        rf"[Tt]he all items index (?!less)(?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent for the 12 months end(?:ed|ing)",
        rf"[Tt]he all items index (?!less)(?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the 12-month span",
        rf"[Aa]ll items index (?!less)(?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent over the (?:last|past) 12.?months",
        # "12 months ended June 2021, the all items index increased 5.4 percent"
        rf"12 months end(?:ed|ing) [A-Z][a-z]+ \d{{4}}[^.]{{0,120}}?[Tt]he all items index (?!less)(?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent",
        # "Over the last 12 months, the all items index increased 0.3 percent
        # before seasonal adjustment" (2018-11, 2020-04 style)
        rf"[Oo]ver the (?:last|past) 12 months, the all items index (?!less)(?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent before seasonal adjustment",
        # "... increased X percent for the period ending April" (2020-04 style)
        rf"[Tt]he all items index (?!less)(?P<verb>{VERB_RE}) (?:by )?(?P<num>\d+\.\d) percent for the period ending",
    ],
}

HEADLINE_SANITY = {"cpi_all_items_yoy": (-10.0, 25.0)}


def main(argv: list[str] | None = None) -> int:
    ec.PATTERNS = HEADLINE_PATTERNS
    ec.SANITY = HEADLINE_SANITY
    return ec.main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
