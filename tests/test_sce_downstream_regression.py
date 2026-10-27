import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.evaluation.downstream_regression import (
    build_analysis_frame,
    contrast_metrics,
    evaluate_a_b,
    feature_columns,
    fit_ols,
    load_merged_inputs,
    predict_ols,
    r_squared,
    training_rows,
)


def merged_fixture(periods=25):
    dates = pd.date_range("2018-01-01", periods=periods, freq="MS")
    i = np.arange(periods, dtype=float)
    frame = pd.DataFrame({
        "date": dates,
        "scope": ["A"] * periods,
        "PCEDGC96": 100 + i,
        "REVOLSL": 1000 + 2 * i,
        "wage_growth_overall": 3 + 0.05 * i,
        "MICH": 2 + 0.1 * i,
        "UNRATE": 4 + 0.01 * i,
        "JTSJOL": 7000 + i,
        "DSPIC96": 15000 + 10 * i,
        "CPIAUCSL": 100 + 2 * i,
        "CPILFESL": 100 + i,
        "UMCSENT": 80 + 0.2 * i,
        "FEDFUNDS": 1 + 0.01 * i,
        "official_sce": 3 + 0.02 * i,
        "simulated_sce": 3.1 + 0.02 * i,
        "blended_sce": 3.01 + 0.02 * i,
    })
    frame.loc[frame["date"] < pd.Timestamp("2019-01-01"), ["official_sce", "simulated_sce", "blended_sce"]] = np.nan
    return frame


def test_build_analysis_frame_uses_consumer_sim_growth_and_percent_changes():
    merged = merged_fixture()

    activity = build_analysis_frame(merged, "PCEDGC96", 2)
    wage = build_analysis_frame(merged, "wage_growth_overall", 1)

    first = activity.iloc[0]
    assert first["date"] == pd.Timestamp("2019-02-01")
    assert first["target_date"] == pd.Timestamp("2019-04-01")
    assert first["target"] == pytest.approx(np.log(115) - np.log(113))
    assert first["current_transformed"] == pytest.approx(np.log(113))
    assert first["CPI_YOY"] == pytest.approx(100 * (126 / 102 - 1))
    assert wage.iloc[0]["target"] == pytest.approx(0.05)


def test_build_analysis_frame_drops_missing_without_imputation():
    merged = merged_fixture()
    merged.loc[merged["date"] == pd.Timestamp("2019-03-01"), "UNRATE"] = np.nan

    result = build_analysis_frame(merged, "PCEDGC96", 1)

    assert pd.Timestamp("2019-03-01") not in set(result["date"])
    assert pd.Timestamp("2019-04-01") in set(result["date"])
    assert not result.isna().any().any()


def test_feature_sets_separate_domain_official_simulation_and_increment():
    domain = feature_columns("PCEDGC96", "domain_arx")
    increment = feature_columns("PCEDGC96", "official_plus_simulated")

    assert "current_transformed" in domain
    assert "UNRATE" in domain
    assert not any("sce" in name for name in domain)
    assert "official_sce" in increment
    assert "official_sce_delta" in increment
    assert "simulated_sce" in increment
    assert "simulated_sce_delta" in increment


def test_ols_recovers_known_linear_relation():
    x = np.arange(5, dtype=float).reshape(-1, 1)
    y = 1 + 2 * x[:, 0]

    fit = fit_ols(x, y)
    prediction = predict_ols(fit, x)

    assert prediction == pytest.approx(y)
    assert r_squared(y, prediction) == pytest.approx(1.0)


def test_training_rows_never_use_targets_after_forecast_origin():
    dates = pd.date_range("2020-01-01", periods=6, freq="MS")
    frame = pd.DataFrame({"date": dates, "target_date": dates + pd.offsets.MonthBegin(1)})

    result = training_rows(frame, pd.Timestamp("2020-03-01"))

    assert list(result["date"]) == [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")]


def test_b_transfer_is_frozen_on_a_labels_available_at_first_b_origin():
    frame = build_analysis_frame(merged_fixture(25), "PCEDGC96", 1)
    frame.loc[frame.index[-6:], "scope"] = "B"

    predictions, _, _ = evaluate_a_b(frame, min_train=2)
    b = predictions[predictions["scope"] == "B"]

    assert not b.empty
    assert b["n_train"].nunique() == 1
    assert set(b["evaluation"]) == {"B_frozen_A"}
    first_b = frame.loc[frame["scope"] == "B", "date"].min()
    expected_n = len(frame[(frame["scope"] == "A") & (frame["target_date"] <= first_b)])
    assert set(b["n_train"]) == {expected_n}


def test_contrast_reports_signed_improvement_and_incremental_r2():
    summary = pd.DataFrame([
        {"outcome": "PCEDGC96", "horizon": 1, "scope": "A", "model": "official_sce", "n": 20, "rmse": 2.0, "mae": 1.5},
        {"outcome": "PCEDGC96", "horizon": 1, "scope": "A", "model": "simulated_sce", "n": 20, "rmse": 1.5, "mae": 1.0},
    ])
    in_sample = pd.DataFrame([
        {"outcome": "PCEDGC96", "horizon": 1, "model": "official_sce", "r2": 0.2},
        {"outcome": "PCEDGC96", "horizon": 1, "model": "simulated_sce", "r2": 0.35},
    ])

    result = contrast_metrics(summary, in_sample)
    row = result[(result["reference"] == "official_sce") & (result["candidate"] == "simulated_sce")].iloc[0]

    assert row["rmse_improvement"] == pytest.approx(0.25)
    assert row["mae_improvement"] == pytest.approx(1 / 3)
    assert row["delta_r2"] == pytest.approx(0.15)


def write_input_fixture(root):
    merged = merged_fixture(25)
    panel = merged.drop(columns=["scope", "official_sce", "simulated_sce", "blended_sce"])
    panel_path = root / "panel.csv"
    a_path = root / "a.csv"
    b_path = root / "b.csv"
    panel.to_csv(panel_path, index=False)
    a = merged[merged["date"] < merged["date"].iloc[-6]]
    b = merged[merged["date"] >= merged["date"].iloc[-6]]
    pd.DataFrame({
        "month": a["date"].dt.strftime("%Y%m"),
        "truth_pp": a["official_sce"],
        "CoreNormal_tau8_pure": a["simulated_sce"],
        "CoreNormal_tau8_blend_mse": a["blended_sce"],
    }).to_csv(a_path, index=False)
    pd.DataFrame({
        "month": b["date"].dt.strftime("%Y%m"),
        "truth_pp": b["official_sce"],
        "expanded_pp": b["simulated_sce"],
        "expanded_blend_pp": b["blended_sce"],
    }).to_csv(b_path, index=False)
    return panel_path, a_path, b_path


def test_load_merged_inputs_uses_frozen_a_and_b_columns(tmp_path):
    paths = write_input_fixture(tmp_path)

    result = load_merged_inputs(*paths)

    assert len(result) == 25
    assert result["scope"].value_counts().to_dict() == {"A": 19, "B": 6}
    last = result.iloc[-1]
    assert last["official_sce"] == pytest.approx(last["blended_sce"] - 0.01)
    assert last["simulated_sce"] == pytest.approx(last["official_sce"] + 0.1)


def test_command_writes_all_models_outcomes_horizons_and_report(tmp_path):
    paths = write_input_fixture(tmp_path)
    script = Path(__file__).parents[1] / "scripts" / "analyze_sce_downstream_regression.py"
    spec = importlib.util.spec_from_file_location("downstream_command", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.run(*paths, tmp_path / "out", min_train=2)

    assert len(result["summary"]) == 4 * 3 * 8 * 2
    assert len(result["contrasts"]) == 4 * 3 * 17 * 2
    assert (tmp_path / "out" / "predictions.csv").is_file()
    assert (tmp_path / "out" / "index.html").is_file()
    assert (tmp_path / "out" / "manifest.json").is_file()
