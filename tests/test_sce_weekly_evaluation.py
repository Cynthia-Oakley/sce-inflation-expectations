"""Synthetic contract tests for the separate weekly evaluation process."""
from datetime import date, datetime, time, timedelta, timezone
import csv
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from studies.sce_inflation_expectations.experiments import weekly_evaluation as evaluation
from studies.sce_inflation_expectations.experiments.weekly_release_protocol import schedule
from studies.sce_inflation_expectations.experiments.frozen_batch import sha


NY = ZoneInfo("America/New_York")


def _next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _periods(start_year, start_month, n):
    rows = []
    year, month = start_year, start_month
    for _ in range(n):
        rows.append((year, month))
        year, month = _next_month(year, month)
    return rows


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _bins_for(index, week):
    group = index % 3
    first = float(12 + group * 7 + (week % 2) * 2)
    remainder = (100.0 - first) / 9
    return [first] + [remainder] * 9


def _utc_iso(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _install_synthetic_run(tmp_path, monkeypatch):
    root = Path(tmp_path)
    folder = root / "outputs" / "weekly-evaluation-fixture"
    folder.mkdir(parents=True)
    inputs = root / "outputs" / "weekly-input-fixture"
    input_rel = inputs.relative_to(root).as_posix()

    headline = []
    for index, (year, month) in enumerate(_periods(2025, 9, 13)):
        pub_year, pub_month = _next_month(year, month)
        period = f"{year:04}-{month:02}"
        source = root / "data" / "fixture_sources" / f"sce_{period}.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"synthetic headline archive {period}\n", encoding="utf-8")
        headline.append({
            "reference_period": period,
            "published_date": f"{pub_year:04}-{pub_month:02}-07",
            "value_pp": 2.4 + index * .03,  # fabricated fixture value; no target data
            "source_file": source.relative_to(root).as_posix(),
            "source_sha256": sha(source),
        })

    cpi = []
    for index, (year, month) in enumerate(_periods(2025, 4, 19)):
        pub_year, pub_month = _next_month(year, month)
        period = f"{year:04}-{month:02}"
        source = root / "data" / "fixture_sources" / f"cpi_{period}.txt"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"synthetic CPI archive {period}\n", encoding="utf-8")
        cpi.append({
            "reference_period": period,
            "published_date": f"{pub_year:04}-{pub_month:02}-07",
            "value": 2.0 + index * .02,
            "file": source.relative_to(root).as_posix(),
            "source_sha256": sha(source),
        })

    catalog_path = root / "data" / "evaluation" / "catalog" / "aggregate_inputs.json"
    _write_json(catalog_path, {"headline_releases": headline, "cpi_first_releases": cpi})
    food_archive = root / "data" / "fixture_sources" / "cpi_food_oct.txt"
    food_archive.write_text("synthetic archived CPI timestamp source\n", encoding="utf-8")
    food_catalog = root / "outputs" / "food_catalog.json"
    _write_json(food_catalog, {"202510": {"food_at_home": {
        "reference_period": "2025-10",
        "published_at": "2025-11-07T08:30:00-05:00",
        "source_file": food_archive.relative_to(root).as_posix(),
        "source_sha256": sha(food_archive),
    }}})
    cutoffs = []
    first = date(2025, 11, 7)
    for week in range(47):
        day = first + timedelta(days=7 * week)
        cutoffs.append(datetime.combine(day, time(23, 59, 59), NY).isoformat())
    points = schedule(cutoffs, headline)
    for row in points:
        day = datetime.fromisoformat(row["cutoff"]).astimezone(NY)
        row["step_key"] = "w" + day.strftime("%Y%m%d")
        row["month"] = row["target_reference_period"].replace("-", "")

    ids = [f"weekly-household-{index:03d}" for index in range(300)]
    weights = {aid: 1.0 + index / 1000 for index, aid in enumerate(ids)}
    cycles = {}
    cycle_index = {}
    for point in points:
        if point["cycle_key"] in cycles:
            continue
        cycle_index[point["cycle_key"]] = len(cycle_index)
        donor_period = int(point["anchor_reference_period"].replace("-", ""))
        states = {}
        for index, aid in enumerate(ids):
            bins = _bins_for(index, 0)
            states[aid] = {
                "fields": {
                    "q8": {"value": 3.0, "source_period": donor_period,
                           "source_kind": "synthetic_donor"},
                    "q9": {"value": bins, "source_period": donor_period,
                           "source_kind": "synthetic_donor"},
                },
                "center": 2.0 + index % 3,
            }
        cycles[point["cycle_key"]] = {"states": states, "diagnostics": {}}

    _write_json(inputs / "weekly_plan.json", points)
    _write_json(inputs / "weights_private.json", weights)
    _write_json(inputs / "priors" / "cycles_private.json", cycles)
    _write_json(inputs / "manifest.json", {"files_sha256": {}})

    macro_parameters = {
        "max_training_label_publication": "2025-11-07",
        "B_targets_used_for_fitting": False,
        "coefficient_update_within_B": False,
        "blends": {"mse": {"simulation_weight": 0.1339762571517809, "training_n": 48}},
        "fits": {
            "macro_without_sim": {
                "features": ["anchor_level", "cpi_gap", "cpi_change"],
                "coefficients": [0.0, 0.0, 0.0], "intercept": 0.0,
            },
            "macro_plus_sim": {
                "features": ["anchor_level", "cpi_gap", "cpi_change", "sim_gap"],
                "coefficients": [0.0, 0.0, 0.0, 0.0], "intercept": 0.0,
            },
        },
    }
    params_path = _write_json(root / "outputs" / "sce_recent_b_review_materials_20261026_v2"
                              / "macro_parameters.json", macro_parameters)
    _write_json(folder / "package" / "protocol.json", {
        "inputs": input_rel,
        "evaluation_catalog_only": catalog_path.relative_to(root).as_posix(),
    })
    _write_json(folder / "package" / "manifest.json", {"source_sha256": {}})

    current_states = {}
    sealed_by_step = {}
    weekly_receipts = []
    for week, point in enumerate(points):
        current = {}
        cycle = cycles[point["cycle_key"]]["states"]
        for index, aid in enumerate(ids):
            prior = cycle[aid]
            cutoff = _utc_iso(point["cutoff"])
            if aid not in current_states or point["reset_required"]:
                source_at = _utc_iso(point["anchor_known_from"])
                fields = {
                    "q8": {"value": prior["fields"]["q8"]["value"], "source_kind": "synthetic_donor",
                           "source_at": source_at},
                    "q9": {"value": list(prior["fields"]["q9"]["value"]), "source_kind": "synthetic_donor",
                           "source_at": source_at},
                }
                history = [{"source_at": source_at, "center": prior["center"],
                            "source_kind": "cycle_start_joint_prior"}]
            else:
                fields = {name: dict(value) for name, value in current_states[aid]["fields"].items()}
                history = list(current_states[aid]["history_centers"])
            q9_updated = not (week == 1 and index == 0)
            fields["q8"] = {"value": 3.1 + index / 1000, "source_kind": "simulated", "source_at": cutoff}
            if q9_updated:
                bins = _bins_for(index, week)
                center = 2.5 + index % 3 + week / 100
                fields["q9"] = {"value": bins, "source_kind": "simulated", "source_at": cutoff}
                history.append({"source_at": cutoff, "center": center, "source_kind": "simulated"})
            state = {
                "agent_id": aid, "cycle_key": point["cycle_key"], "last_cutoff": cutoff,
                "fields": fields, "history_centers": history,
                "steps": [{"cutoff": cutoff,
                           "field_updated_from_model": {"q8": True, "q9": q9_updated}}],
            }
            current[aid] = state
        current_states = current
        sealed_by_step[point["step_key"]] = (current, {
            "actual_model_results": True, "step_key": point["step_key"],
            "cycle_key": point["cycle_key"], "cutoff": point["cutoff"],
        })
        weekly_receipts.append({"actual_model_results": True, "step_key": point["step_key"],
                                "cycle_key": point["cycle_key"]})
        checkpoint = folder / "checkpoints" / point["step_key"]
        _write_json(checkpoint / "states_private.json", {"fixture": True})
        _write_json(checkpoint / "receipt.json", {"fixture": True})
        _write_json(checkpoint / "manifest.json", {"fixture": True})
        wave = folder / "waves" / point["step_key"]
        _write_json(wave / "wave_plan.json", {"fixture": True})
        _write_json(wave / "manifest.json", {"fixture": True})

    _write_json(folder / "generation_receipt.json", {
        "status": "weekly_generation_complete", "actual_model_results": True,
        "weekly_points": 47, "weekly": weekly_receipts,
    })
    protocol = {
        "inputs": input_rel,
        "evaluation_catalog_only": catalog_path.relative_to(root).as_posix(),
    }
    monkeypatch.setattr(evaluation, "ROOT", root)
    monkeypatch.setattr(evaluation, "CATALOG", catalog_path)
    monkeypatch.setattr(evaluation, "MACRO_PARAMETERS", params_path)
    monkeypatch.setattr(evaluation, "FOOD_CATALOG", food_catalog)
    matplotlib_cache = root / "matplotlib-cache"
    matplotlib_cache.mkdir()
    monkeypatch.setenv("MPLCONFIGDIR", str(matplotlib_cache))
    monkeypatch.setattr(evaluation, "checked", lambda _folder: (protocol, {"source_sha256": {}}))
    monkeypatch.setattr(evaluation, "sealed", lambda _folder, point: sealed_by_step[point["step_key"]])
    monkeypatch.setattr(evaluation, "density_center", lambda bins: float(bins[0]) / 10)
    return folder, points, cycles, weights


def test_fixtures_are_rejected_before_evaluation_catalog_is_opened(tmp_path, monkeypatch):
    root = Path(tmp_path)
    folder = root / "outputs" / "fake-run"
    folder.mkdir(parents=True)
    _write_json(folder / "generation_receipt.json", {
        "status": "weekly_generation_complete", "actual_model_results": False, "weekly_points": 47,
    })
    monkeypatch.setattr(evaluation, "ROOT", root)
    monkeypatch.setattr(evaluation, "CATALOG", root / "missing-target-catalog.json")
    monkeypatch.setattr(evaluation, "checked", lambda _folder: ({"inputs": "unused"}, {}))
    with pytest.raises(ValueError, match="Actual complete 47-week"):
        evaluation.evaluate(folder)
    assert not (folder / "evaluation").exists()


def test_actual_generation_evaluation_keeps_q9_fallback_and_writes_frozen_outputs(tmp_path, monkeypatch):
    folder, points, cycles, weights = _install_synthetic_run(tmp_path, monkeypatch)
    result = evaluation.evaluate(folder)
    assert result["status"] == "completed_weekly_national_evaluation"
    assert result["actual_model_results"] is True
    assert result["weekly_points"] == 47
    assert result["fixed_households"] == 300
    assert result["public_calibration_cycles"] == 12
    assert result["target_months"] == 11
    assert result["weekly_ground_truth_available"] is False
    assert result["micro_W1"] is None
    assert result["new_api_calls"] == 0

    output = folder / "evaluation"
    with (output / "weekly_national.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 47
    assert sum(row["main_score_point"] == "True" for row in rows) == 11
    failed_week = rows[1]
    assert int(failed_week["q9_retained_n"]) == 1
    assert int(failed_week["q9_updated_n"]) == 299
    assert failed_week["sim_n_valid"] == "300"
    # First cutoff is 2025-11-07 23:59 NY; the final A training label has only
    # a date, so this CPI model cannot be used until next-day midnight.
    assert rows[0]["macro_without_sim_pp"] == ""
    assert rows[0]["macro_without_sim_status"] == "training_labels_not_public_by_cutoff"
    assert rows[1]["macro_without_sim_pp"] != ""
    assert rows[1]["macro_cpi_latest_timing_method"] == "food_catalog_archived_0830_override"

    main = result["evaluation"]["last_week_in_month"]
    assert main["n_target_months"] == 11
    assert main["raw_model"]["n_months"] == 11
    assert main["public_SCE_persistence"]["n_months"] == 11
    assert main["same_cycle_fixed_joint_prior"]["n_months"] == 11
    assert "mae_pp" in main["same_cycle_fixed_joint_prior"]
    assert main["fixed_A_early48_MSE_blend"]["n_months"] == 11
    assert main["macro_without_sim"]["n_months"] == 11
    assert main["macro_plus_sim"]["n_months"] == 11
    assert result["fixed_A_early48_MSE_blend"]["simulation_weight"] == pytest.approx(0.1339762571517809)
    assert result["fixed_A_early48_MSE_blend"]["training_months"] == 48
    assert len(result["source_sha256"]) > 47  # release archives, frozen inputs, receipts and code
    assert result["macro_fixed_model"]["cpi_publication_timing"]["override_count"] == 1
    assert (output / "weekly_national.png").is_file()
    assert (output / "index.html").is_file()
    assert "同周期合成先验MAE（pp）" in (output / "index.html").read_text(encoding="utf-8")
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["new_api_calls"] == 0
    assert manifest["actual_model_results"] is True
    assert manifest["target_catalog_sha256"] == sha(evaluation.CATALOG)
    assert len(manifest["files_sha256"]) == 4
