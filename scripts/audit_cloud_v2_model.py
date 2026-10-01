"""Replay the archived v2 scripted formula against local P/E and raw answers."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ARCHIVE = REPO / "data/raw/cloud_exports/2026-09-30/sce_inflation_expectations_v2"
MODEL_SHA256 = "c6029c9460583aff85f239b4f1e4ff5263b5ce83abb1e65a412575adc8e6cc23"


def stable_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def main() -> None:
    model = (ARCHIVE / "model.py").read_bytes()
    assert hashlib.sha256(model).hexdigest() == MODEL_SHA256
    assert len(model) == 9534

    with (REPO / "data/fixtures/sce_20_synthetic_personas.csv").open(newline="") as f:
        personas = {row["agent_id"]: row for row in csv.DictReader(f)}
    env = json.loads((REPO / "proposal/cloud_input/sce_2021_05_06_bls_release_e.json").read_text())
    signal_sets = {month["target_month"]: month["signals"] for month in env["target_months"]}
    answers = [json.loads(line) for line in (ARCHIVE / "raw_q8_q9.jsonl").read_text().splitlines()]

    mismatches = []
    unemployment_effect_rows = 0
    for row in answers:
        month = row["target_month"]
        agent_id = row["agent_id"]
        signals = signal_sets[month]
        inflation = next(float(s["value"]) for s in signals if "12-month" in s["measure"])
        unemployment = next(float(s["value"]) for s in signals if "unemployment rate" in s["measure"].lower())
        adjustment = (stable_int(f"42|{agent_id}|{month}") % 7 - 3) * 0.05
        income = personas[agent_id]["household_income_band"]
        income_adjustment = 0.10 if income == "125k_plus" else (-0.05 if income == "under_35k" else 0.0)
        base = inflation * 0.55 + adjustment + income_adjustment
        point = round(max(0.0, base + (unemployment - 6.0) * -0.03), 2)
        point_without_unemployment = round(max(0.0, base), 2)
        unemployment_effect_rows += point != point_without_unemployment
        shift = stable_int(f"q9|42|{agent_id}|{month}") % 5
        bins = [0.0, 0.0, 0.0, 25.0 + shift, 55.0 - shift, 20.0, 0.0, 0.0, 0.0, 0.0]
        if point != row["point_pct"] or any(
            bins[i - 1] != row[f"q9_bin{i}"] for i in range(1, 11)
        ):
            mismatches.append((month, agent_id))

    result = {
        "archived_model_sha256": MODEL_SHA256,
        "answer_rows": len(answers),
        "p_e_formula_mismatches": len(mismatches),
        "unemployment_term_changed_rounded_answer_rows": unemployment_effect_rows,
        "limit": "This is an independent formula replay with local P/E, not proof of the cloud runtime Observation contents.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert len(answers) == 40 and not mismatches


if __name__ == "__main__":
    main()
