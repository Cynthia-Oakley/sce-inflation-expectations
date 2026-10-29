import csv
import json
import math
from pathlib import Path

from studies.sce_inflation_expectations.submission_tools.portable_calibration import (
    CN_DIR,
    export,
    replay,
)


ROOT = Path(__file__).resolve().parents[1]


def _read_rows(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def test_portable_calibration_replays_all_archived_canonical_outputs(tmp_path):
    bundle = tmp_path / "calibration_bundle"
    out = tmp_path / "frozen_replay"
    manifest = export(bundle, root=ROOT)

    assert manifest["status"] == "exported_portable_offline_calibration_bundle"
    assert manifest["a_month_count"] == 82
    assert manifest["public_CPI_environment_count"] == 82
    assert "frozen_A_Core_and_CoreNormal_aggregate" in {
        row["role"] for name, row in manifest["files"].items() if name.endswith("monthly_public.csv")
    }

    result = replay(bundle, out)
    assert result["status"] == "completed_frozen_calibration_replay"
    assert result["comparison"]["status"] == "matched_archived_calibration"
    assert result["new_api_calls"] == 0
    assert result["new_q9_fits"] == 0
    assert (out / "portable_calibration_receipt.json").is_file()
    assert len(_read_rows(out / "monthly_inputs_public.csv")) == 82
    assert len(_read_rows(out / "monthly_predictions_public.csv")) == 82


def test_fresh_evaluator_centers_feed_original_early48_refit_without_reference_assertions(tmp_path):
    bundle = tmp_path / "calibration_bundle"
    fresh = tmp_path / "fresh_evaluation"
    out = tmp_path / "fresh_recalibration"
    export(bundle, root=ROOT)
    fresh.mkdir()

    frozen_rows = _read_rows(bundle / CN_DIR / "monthly_public.csv")
    alpha = 0.1339762571517809
    direct_rows = []
    normal_rows = []
    downstream_rows = []
    for index, row in enumerate(frozen_rows):
        period = str(row["month"])
        direct = float(row["before_model_pp"]) + 0.2
        normal = float(row["expanded_model_pp"]) + 0.3
        direct_rows.append({
            "task": "A",
            "period": period,
            "q9_median_pp": direct,
            "truth_pp": row["truth_pp"],
            "anchor_pp": row["baseline_pp"],
        })
        normal_rows.append({
            "run": "A_Normal",
            "period": period,
            "status": "completed_fresh_joint_expansion",
            "q9": {"median_pp": normal},
        })
        downstream_rows.append({
            "month": period,
            "truth_pp": row["truth_pp"],
            "CoreNormal_tau8_pure": normal,
            "CoreNormal_tau8_blend_mse": float(row["baseline_pp"]) + alpha * (normal - float(row["baseline_pp"])),
        })

    (fresh / "summary.json").write_text(json.dumps({
        "status": "completed_fresh_model_evaluation",
        "actual_model_results": True,
        "new_model_or_network_calls": 0,
    }), encoding="utf-8")
    with (fresh / "monthly_series.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(direct_rows[0]))
        writer.writeheader()
        writer.writerows(direct_rows)
    (fresh / "normal_summary.json").write_text(json.dumps({"monthly": normal_rows}), encoding="utf-8")
    with (fresh / "monthly_predictions_public.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(downstream_rows[0]))
        writer.writeheader()
        writer.writerows(downstream_rows)

    result = replay(bundle, out, fresh_evaluation=fresh)
    receipt = json.loads((out / "portable_calibration_receipt.json").read_text(encoding="utf-8"))
    predictions = _read_rows(out / "monthly_predictions_public.csv")
    training = json.loads((out / "training_fits_sealed_before_later_scores.json").read_text(encoding="utf-8"))
    frozen_training = json.loads((ROOT / "outputs/sce_full_a_macro_calibration_20261026_v1/training_fits_sealed_before_later_scores.json").read_text(encoding="utf-8"))

    assert result["status"] == "completed_fresh_A_recalibration"
    assert result["comparison"]["status"] == "not_compared_to_archived_results"
    assert receipt["mode"]["fresh_a_core_months"] == 82
    assert receipt["mode"]["fresh_a_normal_months"] == 82
    assert receipt["mode"]["reference_value_assertions_on_fresh_results"] is False
    assert math.isclose(float(predictions[0]["Core_pure"]), float(frozen_rows[0]["before_model_pp"]) + 0.2)
    assert math.isclose(float(predictions[0]["CoreNormal_tau8_pure"]), float(frozen_rows[0]["expanded_model_pp"]) + 0.3)
    assert training["Core_blend_mse"]["simulation_weight"] != frozen_training["Core_blend_mse"]["simulation_weight"]
    assert receipt["mode"]["frozen_truth_anchor_and_public_cpi_inputs_preserved"] is True
