"""Independently audit the v2 scripted pilot's pasted raw JSONL answers."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from statistics import median


EXPECTED_SHA256 = "bd94c7ae0cbb847a54172e0d923c63689dcf3da07f4459766176d7c8c6669ace"
MONTHS = {
    "2021-05": (1, "2021-04-30T23:59:59-04:00", "bls_initial_release_e_2021-05", Decimal("1.43")),
    "2021-06": (2, "2021-05-31T23:59:59-04:00", "bls_initial_release_e_2021-06", Decimal("2.31")),
}


def audit(path: Path) -> dict:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == EXPECTED_SHA256, f"File hash mismatch: {digest}"
    assert len(data) == 26520, f"Unexpected byte count: {len(data)}"
    assert data.endswith(b"\n"), "Missing final newline"

    rows = [json.loads(line) for line in data.splitlines() if line.strip()]
    assert len(rows) == 40, f"Expected 40 answers, found {len(rows)}"
    assert len({(r["target_month"], r["agent_id"]) for r in rows}) == 40
    assert set(r["target_month"] for r in rows) == set(MONTHS)

    ids_by_month = {}
    month_results = {}
    for month, (step, as_of, e_id, reported_median) in MONTHS.items():
        sample = [r for r in rows if r["target_month"] == month]
        assert len(sample) == 20, f"Wrong answer count for {month}"
        ids = {r["agent_id"] for r in sample}
        assert ids == {f"smoke_{i:03d}" for i in range(1, 21)}
        ids_by_month[month] = ids

        for row in sample:
            assert row["runtime_step"] == step
            assert row["as_of"] == as_of
            assert row["e_snapshot_id"] == e_id
            assert row["p_snapshot_id"] == "p_pilot_20260929_v1"
            assert row["model_version"] == "deterministic-scripted-v1"
            assert row["prompt_version"] == "sce-q8-q9-scripted-v1"
            assert row["seed"] == 42
            assert row["validation_status"] == "valid"
            assert row["direction"] in {"inflation", "deflation"}

            point = Decimal(str(row["point_pct"]))
            magnitude = Decimal(str(row["magnitude_pct"]))
            assert magnitude >= 0
            assert point == (magnitude if row["direction"] == "inflation" else -magnitude)
            probabilities = [Decimal(str(row[f"q9_bin{i}"])) for i in range(1, 11)]
            assert all(Decimal(0) <= p <= Decimal(100) for p in probabilities)
            assert sum(probabilities) == Decimal(100)
            assert Decimal(str(row["q9_sum"])) == Decimal(100)

        observed_median = Decimal(str(median(Decimal(str(r["point_pct"])) for r in sample)))
        assert observed_median == reported_median, f"Wrong Q8 median for {month}"
        month_results[month] = {
            "rows": len(sample),
            "unique_agent_ids": len(ids),
            "q8_equal_weight_median_pct": str(observed_median),
            "q8_range_pct": [str(min(Decimal(str(r["point_pct"])) for r in sample)),
                             str(max(Decimal(str(r["point_pct"])) for r in sample))],
            "q9_positive_bin_patterns": dict(Counter(
                ",".join(str(i) for i in range(1, 11) if r[f"q9_bin{i}"] > 0)
                for r in sample
            )),
        }

    assert ids_by_month["2021-05"] == ids_by_month["2021-06"]
    return {
        "source_path": str(path),
        "bytes": len(data),
        "sha256": digest,
        "rows": len(rows),
        "panel_ids_reused": True,
        "month_results": month_results,
        "distinct_reasons": len({r["reason"] for r in rows}),
        "caveat": "Answer rows contain E snapshot IDs, not the actual E observations or B code.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.path), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
