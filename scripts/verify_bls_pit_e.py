"""Verify the two-month BLS E snapshot against its archived release PDFs.

Run from any directory: python3 scripts/verify_bls_pit_e.py
Requires PyMuPDF (`fitz`) for page-one text extraction.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "proposal/cloud_input/sce_2021_05_06_bls_release_e.json"


def main() -> None:
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert data["status"] == "historical_official_release_evidence"
    assert [x["target_month"] for x in data["target_months"]] == [
        "2021-05",
        "2021-06",
    ]

    signal_ids: set[str] = set()
    for month in data["target_months"]:
        cutoff = datetime.fromisoformat(month["as_of"])
        assert len(month["signals"]) == 3
        for signal in month["signals"]:
            assert signal["signal_id"] not in signal_ids
            signal_ids.add(signal["signal_id"])
            assert datetime.fromisoformat(signal["published_at"]) <= cutoff
            assert signal["reference_period"] < month["target_month"]
            assert signal["eligibility"] == "eligible"

            source = ROOT / signal["local_source_path"]
            assert hashlib.sha256(source.read_bytes()).hexdigest() == signal[
                "local_source_sha256"
            ]
            with fitz.open(source) as pdf:
                first_page = pdf[0].get_text().replace("\n", " ")
            assert signal["source_version"] in first_page
            published = datetime.fromisoformat(signal["published_at"])
            assert published.strftime("%B %-d, %Y") in first_page

            number = f'{signal["value"]:.1f} percent'
            if "cpi" in signal["signal_id"]:
                phrase = (
                    f"increased {number}"
                    if "mom" in signal["signal_id"]
                    else f"increased {number} before seasonal adjustment"
                )
                assert phrase in first_page, signal["signal_id"]
            else:
                assert number in first_page, signal["signal_id"]

    assert len(signal_ids) == 6
    print("Verified 6 release-backed signals across 2 target months.")


if __name__ == "__main__":
    main()
