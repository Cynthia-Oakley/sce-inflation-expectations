from studies.sce_inflation_expectations.submission_tools.portable_evaluate import (
    _a_full_wave,
    _build_normal,
    _national_metrics,
    _prepare_answers,
)


POSITIVE_BINS = [0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0]
NEGATIVE_BINS = [0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0]
ARCHIVED_SCORE_FIXTURE = {
    tuple(POSITIVE_BINS): {
        "mean": 1.0,
        "iqr": 1.0,
        "zero_deflation": 1.0,
        "scorer_status": "ok",
        "validation_error": None,
    },
}


def answer(bins, *, q8=2.5, period="201901", original_id="person-a", alias="A_000001"):
    return {
        "task": "A",
        "period": period,
        "agent_id": original_id,
        "household": alias,
        "weight": 1.0,
        "q8": q8,
        "q9_bins": list(bins),
        "field_sources": {"q8": "main", "q9": "main"},
        "actual_model_results": True,
    }


def one_person_a_normal(old_answer=None):
    return {
        "run": "A_Normal",
        "period": "201901",
        "inputs": {
            "people": [{
                "id": "A_Normal_000001",
                "weight": 1.0,
                "entry": "returner",
                "education": "college",
                "numeracy": "High",
                "age": "40_60",
                "income": "50k_100k",
            }],
            "selected": [{"id": "A_Normal_000001", "poststratified_weight": 1.0}],
            # This old answer is deliberately conflicting; the adapter must
            # construct a new bank exclusively from fresh A rows.
            "answers": [old_answer or {
                "id": "A_Normal_000001",
                "q9_bins": NEGATIVE_BINS,
                "q9_mean": -25.0,
                "q9_iqr": 13.0,
                "q8": -20.0,
            }],
        },
        "expected_atoms": {"old_result_that_must_not_be_used": True},
    }


def test_fresh_a_full_wave_statistics_move_when_the_answer_changes():
    code_map = {"A_000001": "person-a"}
    rows_one, _, counts_one = _prepare_answers([answer(POSITIVE_BINS)], code_map, dict(ARCHIVED_SCORE_FIXTURE))
    rows_two, _, counts_two = _prepare_answers([answer(NEGATIVE_BINS)], code_map, dict(ARCHIVED_SCORE_FIXTURE))
    full_wave = [{"month": "201901", "q9_mean": 3.0, "q8": 3.0, "weight": 1.0}]

    stats_one = _a_full_wave(rows_one, full_wave)[0]["fields"]["q9_mean"]
    stats_two = _a_full_wave(rows_two, full_wave)[0]["fields"]["q9_mean"]

    assert stats_one["simulated"]["median_pp"] != stats_two["simulated"]["median_pp"]
    assert stats_one["w1_pp"] != stats_two["w1_pp"]
    assert counts_one["exact_cache_lookups"] == 1
    assert counts_two["new_frozen_scores"] == 1


def test_a_density_failure_uses_explicit_prior_bins_for_operational_scoring():
    model_bins = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0]
    model_cache = {
        tuple(model_bins): {
            "mean": None,
            "iqr": None,
            "zero_deflation": 0.0,
            "scorer_status": "candidate_exception",
            "validation_error": None,
        },
    }
    row = answer(model_bins)
    row.update(before_q8=4.0, before_q9_bins=POSITIVE_BINS)
    scored, _, counts = _prepare_answers([row], {"A_000001": "person-a"}, model_cache)

    assert scored[0]["model_q9_mean"] is None
    assert scored[0]["q9_mean"] == ARCHIVED_SCORE_FIXTURE[tuple(POSITIVE_BINS)]["mean"]
    assert scored[0]["q9_bins"] == POSITIVE_BINS
    assert scored[0]["q9_prior_fallback"] is True
    assert scored[0]["q8"] == row["q8"]
    assert counts["q9_prior_fallbacks"] == 1


def test_normal_bank_uses_fresh_answers_and_marks_partial_roster_unavailable():
    code_map = {
        "A_000001": "person-a",
        "A_000002": "person-b",
        "A_Normal_000001": "person-a",
        "A_Normal_000002": "person-b",
    }
    cache = dict(ARCHIVED_SCORE_FIXTURE)
    cache[tuple(NEGATIVE_BINS)] = {
        "mean": -1.0,
        "iqr": 1.0,
        "zero_deflation": 0.0,
        "scorer_status": "ok",
        "validation_error": None,
    }
    original = one_person_a_normal()
    original["inputs"]["selected"].append({"id": "A_Normal_000002", "poststratified_weight": 1.0})
    original["inputs"]["people"].append({
        "id": "A_Normal_000002", "weight": 1.0, "entry": "returner",
        "education": "college", "numeracy": "Low", "age": "40_60", "income": "50k_100k",
    })
    # Even though an old answer exists for both records, one fresh Core ID is
    # absent, so no partial or historical Normal bank may be substituted.
    original["inputs"]["answers"].append({
        "id": "A_Normal_000002", "q9_bins": NEGATIVE_BINS,
        "q9_mean": -1.0, "q9_iqr": 1.0, "q8": -1.0,
    })
    _, fresh_by_key, _ = _prepare_answers(
        [answer(POSITIVE_BINS)], {"A_000001": "person-a"}, cache
    )
    incomplete, normal_rows = _build_normal(
        original,
        "201901",
        "A",
        fresh_by_key,
        code_map,
        {"201901": [{"q9_mean": 1.0, "q8": 2.0, "weight": 1.0}]},
    )
    assert incomplete["status"] == "unavailable_incomplete_fresh_core_answers"
    assert incomplete["core_ids_missing"] == 1
    assert normal_rows == []

    _, complete_by_key, _ = _prepare_answers(
        [answer(POSITIVE_BINS), answer(NEGATIVE_BINS, original_id="person-b", alias="A_000002")],
        {"A_000001": "person-a", "A_000002": "person-b"},
        cache,
    )
    result, rows = _build_normal(
        original,
        "201901",
        "A",
        complete_by_key,
        code_map,
        {"201901": [{"q9_mean": 1.0, "q8": 2.0, "weight": 1.0}]},
    )
    assert result["status"] == "completed_fresh_joint_expansion"
    assert result["q9"]["median_pp"] != 99.0
    assert result["q9_population_mass"] == 2.0
    assert len(rows) == 2
    assert {row["q9_joint"]["source"] for row in rows} == {"fresh_core_model_output"}

    _, all_positive_by_key, _ = _prepare_answers(
        [answer(POSITIVE_BINS), answer(POSITIVE_BINS, original_id="person-b", alias="A_000002")],
        {"A_000001": "person-a", "A_000002": "person-b"},
        cache,
    )
    changed, _ = _build_normal(
        original,
        "201901",
        "A",
        all_positive_by_key,
        code_map,
        {"201901": [{"q9_mean": 1.0, "q8": 2.0, "weight": 1.0}]},
    )
    assert result["q9"]["median_pp"] != changed["q9"]["median_pp"]


def test_national_metrics_use_frozen_period_eligibility_and_report_coverage():
    expected = {
        "A": {"official_national": {"monthly": [
            {"month": "2019-01", "truth_pp": 4.0, "anchor_pp": 2.0},
            {"month": "2019-02", "truth_pp": 4.0, "anchor_pp": 3.0},
        ]}},
        "B": [{"month": 202511, "truth_pp": 3.0, "anchor_pp": 2.5}],
        "monthly": [
            {"month": "202511", "truth_pp": 3.0, "anchor_pp": 2.5, "shared_reused_root": True},
            {"month": "202512", "truth_pp": 4.0, "anchor_pp": 3.0, "shared_reused_root": False},
        ],
        "weekly": [
            {"step_key": "w20251121", "main_score_point": "False", "target_release_value_pp": "3.0", "anchor_pp": "2.5"},
            {"step_key": "w20251128", "main_score_point": "True", "target_release_value_pp": "4.0", "anchor_pp": "3.0"},
        ],
    }
    direct = [
        {"task": "A", "period": "201901", "q9": {"median_pp": 3.0}},
        {"task": "A", "period": "201902", "q9": None},
        {"task": "B", "period": "202511", "q9": {"median_pp": 4.0}},
        {"task": "monthly", "period": "202512", "q9": {"median_pp": 5.0}},
        {"task": "weekly", "period": "w20251128", "q9": {"median_pp": 6.0}},
    ]
    normal = [
        {"run": "A_Normal", "period": "201901", "status": "completed_fresh_joint_expansion",
         "q9": {"median_pp": 3.5}, "q8": {"median_pp": 2.0},
         "core_ids_expected": 512, "core_ids_present": 512, "core_ids_missing": 0,
         "valid_fresh_Q9_donors": 510, "valid_fresh_Q8_donors": 512,
         "q9_population_mass": 100.0, "q8_population_mass": 100.0},
        {"run": "A_Normal", "period": "201902", "status": "unavailable_incomplete_fresh_core_answers",
         "core_ids_expected": 512, "core_ids_present": 500, "core_ids_missing": 12},
        {"run": "B_Normal", "period": "202511", "status": "completed_fresh_joint_expansion",
         "q9": {"median_pp": 4.5}, "q8": {"median_pp": 3.0},
         "core_ids_expected": 512, "core_ids_present": 512, "core_ids_missing": 0,
         "valid_fresh_Q9_donors": 512, "valid_fresh_Q8_donors": 511,
         "q9_population_mass": 1300.0, "q8_population_mass": 1300.0},
    ]
    answer_rows = [{
        "task": "A", "period": "201901", "weight": 1.0,
        "actual_model_results": True, "q8": 2.0, "q9_mean": 3.0,
        "q8_retained_fallback": True, "q9_prior_fallback": False,
        "field_sources": {"q8": "retained_input", "q9": "repair"},
    }]

    result = _national_metrics(expected, direct, normal, answer_rows, alpha=0.1)
    assert result["series"]["A"]["metrics"]["fresh_raw"] is None
    assert result["series"]["A"]["missing_forecast_periods"] == ["201902"]
    assert result["series"]["A"]["metrics"]["baseline_anchor"]["n_months"] == 2
    assert result["series"]["A"]["monthly"][0]["coverage"]["q8_field_sources"] == {"retained_input": 1}
    assert result["series"]["A"]["monthly"][0]["coverage"]["q9_field_sources"] == {"repair": 1}
    assert result["series"]["A_Normal"]["metrics"]["fresh_raw"] is None
    assert result["series"]["A_Normal"]["missing_forecast_periods"] == ["201902"]

    monthly = result["series"]["monthly"]
    assert monthly["period_count"] == 1
    assert monthly["excluded_periods"] == ["202511"]
    assert monthly["metrics"]["fresh_raw"]["mae_pp"] == 1.0
    assert monthly["monthly"][0]["fixed_A_early48_MSE_blend_pp"] == 3.2

    weekly = result["series"]["weekly"]
    assert weekly["period_count"] == 1
    assert weekly["excluded_periods"] == ["w20251121"]
    assert weekly["metrics"]["fresh_raw"]["mae_pp"] == 2.0
    assert result["series"]["B_Normal"]["metrics"]["fresh_raw"]["n_months"] == 1
