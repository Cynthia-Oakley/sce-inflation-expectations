import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.submission_tools.portable_downstream import (
    MANIFEST_NAME,
    _verify_bundle_manifest,
    export,
    replay,
)


ROOT = Path(__file__).resolve().parents[1]


def test_export_is_explicit_and_hashes_all_reproduction_inputs(tmp_path):
    bundle = export(tmp_path / "bundle", root=ROOT)

    manifest = json.loads((bundle / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["status"] == "offline_downstream_reproduction_bundle"
    assert manifest["network_or_paid_calls"] == 0
    assert manifest["raw_source_file_count"] == 14
    assert manifest["raw_series_count"] == 13
    assert len(manifest["frozen_aggregate_inputs"]) == 2
    assert set(manifest["comparison"]["tables"]) == {
        "predictions.csv",
        "model_metrics.csv",
        "in_sample_metrics.csv",
        "contrasts.csv",
        "coverage.csv",
        "key_contrasts.csv",
    }
    assert len([p for p in manifest["files"] if p.startswith("data/raw/") and p.endswith((".csv", ".xlsx"))]) == 14
    assert "scripts/analyze_sce_downstream_regression.py" in manifest["files"]
    assert "studies/sce_inflation_expectations/evaluation/downstream_regression.py" in manifest["files"]
    assert "docs/workstreams/20261026_downstream/regression_protocol.json" in manifest["files"]
    assert _verify_bundle_manifest(bundle)["status"] == "offline_downstream_reproduction_bundle"


def test_bundle_hashes_detect_input_tampering(tmp_path):
    bundle = export(tmp_path / "bundle", root=ROOT)
    a_input = bundle / "data/frozen_inputs/a_monthly_predictions_public.csv"
    a_input.write_text(a_input.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Bundle hash mismatch"):
        _verify_bundle_manifest(bundle)


def test_replay_rebuilds_panel_and_matches_full_archived_outputs(tmp_path):
    bundle = export(tmp_path / "bundle", root=ROOT)
    result = replay(bundle / "data", tmp_path / "replay", source_root=bundle)

    assert result["status"] == "completed_and_verified"
    assert result["network_or_paid_calls"] == 0
    assert result["reference_comparison"]["performed"] is True
    comparisons = result["reference_comparison"]["tables"]
    assert {row["file"] for row in comparisons} == {
        "predictions.csv",
        "model_metrics.csv",
        "in_sample_metrics.csv",
        "contrasts.csv",
        "coverage.csv",
        "key_contrasts.csv",
    }
    assert all(row["status"] == "matched" for row in comparisons)
    assert (tmp_path / "replay/reconstructed_data/monthly_panel.csv").is_file()

    import pandas as pd

    predictions = pd.read_csv(tmp_path / "replay/predictions.csv")
    metrics = pd.read_csv(tmp_path / "replay/model_metrics.csv")
    contrasts = pd.read_csv(tmp_path / "replay/contrasts.csv")
    assert len(predictions) == 4896
    assert len(metrics) == 192
    assert len(contrasts) == 408
    assert (contrasts["rmse_improvement"] > 0).any()
    assert (contrasts["rmse_improvement"] < 0).any()


def test_custom_a_b_inputs_cannot_claim_frozen_reference_verification(tmp_path):
    data = tmp_path / "data"
    (data / "raw").mkdir(parents=True)

    with pytest.raises(ValueError, match="require verify_reference=False"):
        replay(
            data,
            tmp_path / "replay",
            source_root=ROOT,
            a_input=tmp_path / "new_a.csv",
            b_input=tmp_path / "new_b.csv",
        )
