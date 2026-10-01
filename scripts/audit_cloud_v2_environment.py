"""Verify the pasted v2 cloud environment against the archived local inputs."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "data/raw/cloud_exports/2026-09-30/sce_inflation_expectations_v2"
ENV_SHA256 = "765c926a5405203cebc271d827ee64bbee96bc653f8bad5e8cd6d8fc13995479"
SIGNAL_FIELDS = (
    "signal_id", "measure", "value", "unit", "reference_period",
    "published_at", "source_version", "source_url", "eligibility",
)


def main() -> None:
    raw = (ARCHIVE / "environment.json").read_bytes()
    assert len(raw) == 10718
    assert hashlib.sha256(raw).hexdigest() == ENV_SHA256
    cloud = json.loads(raw)
    source = json.loads((REPO / "proposal/cloud_input/sce_2021_05_06_bls_release_e.json").read_text())
    with (REPO / "data/fixtures/sce_20_synthetic_personas.csv").open(newline="") as file:
        personas = {row["agent_id"]: row for row in csv.DictReader(file)}

    args = cloud["provider_args"]
    assert cloud["study_id"] == "sce_inflation_expectations"
    assert cloud["provider_ref"] == "sce_inflation_expectations.environment"
    assert args["evidence_class"] == "historical_official_release_evidence"
    assert "fred" in args["excluded_sources"]
    assert len(args["persona_by_id"]) == len(personas) == 20
    for agent_id, profile in args["persona_by_id"].items():
        assert agent_id in personas
        assert {key: str(value) for key, value in profile.items()} == {
            key: value for key, value in personas[agent_id].items() if key != "agent_id"
        }

    broadcasts = cloud["information_program"]["broadcasts"]
    assert len(broadcasts) == 2
    month_results = []
    for step, month in enumerate(source["target_months"]):
        observed = args["signals_by_step"][str(step)]
        expected = month["signals"]
        assert len(observed) == len(expected) == 3
        assert [tuple(signal[field] for field in SIGNAL_FIELDS) for signal in observed] == [
            tuple(signal[field] for field in SIGNAL_FIELDS) for signal in expected
        ]
        assert all(datetime.fromisoformat(signal["published_at"]) <= datetime.fromisoformat(month["as_of"]) for signal in observed)
        broadcast = broadcasts[step]
        assert broadcast["at_step"] == step and broadcast["ttl"] == 1
        assert broadcast["message_id"] == f"bls-{month['target_month']}"
        assert all(signal["eligibility"] == "eligible" for signal in observed)
        month_results.append({"month": month["target_month"], "as_of": month["as_of"], "signal_ids": [s["signal_id"] for s in observed]})

    assert set(args["signals_by_step"]) == {"0", "1"}
    print(json.dumps({
        "environment_sha256": ENV_SHA256,
        "personas_match_fixture": 20,
        "signals_match_source": 6,
        "broadcasts_step_ttl_checked": 2,
        "months": month_results,
        "limit": "The pasted configuration is verified; the historical Observation passed to decide_batch was not persisted by the platform.",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
