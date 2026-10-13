import hashlib
import json

import numpy as np
import pandas as pd
import pytest
from scipy.stats import wasserstein_distance

from studies.sce_inflation_expectations.evaluation.behavior_comparison import (
    BIN_FIELDS, MAIN, history_baselines, import_extra, paired_intervals,
    score, screen_candidate, summarize,
)


def bins(index):
    result = [0.] * 10
    result[index] = 100.
    return result


def frame_row(person, date, index):
    return {"userid": person, "date": date, "weight": np.nan,
            **dict(zip(BIN_FIELDS, bins(index)))}


def test_history_rule_exact_calendar_and_future_isolation():
    frame = pd.DataFrame([frame_row(1, 201912, 3), frame_row(1, 202001, 4),
                          frame_row(1, 202002, 0), frame_row(1, 202003, 1),
                          frame_row(2, 201912, 2)])
    subjects = [{"userid": 1, "month": 202002, "agent_id": "a"}]
    old = history_baselines(frame, subjects)[0]
    assert old["history_n"] == 2
    assert old["copy_previous"] == pytest.approx(1)
    assert old["anchor"] == pytest.approx(2)
    assert old["history_anchor_half"] == pytest.approx(1.5)
    changed = frame.copy()
    changed.loc[(changed.date >= 202002) | (changed.userid == 2), BIN_FIELDS] = np.nan
    assert history_baselines(changed, subjects)[0] == old
    # Do not substitute the most recent available answer for calendar t-1.
    assert history_baselines(frame[frame.date != 202001], subjects)[0]["copy_previous"] is None


def test_cold_start_falls_back_and_no_current_answer_or_weight_needed():
    frame = pd.DataFrame([frame_row(1, 202001, 4)])
    result = history_baselines(frame, [{"userid": 1, "month": 202002}])[0]
    assert result["anchor"] is None
    assert result["history_anchor_half"] == result["copy_previous"] == 1
    with pytest.raises(ValueError):
        history_baselines(pd.concat([frame, frame]), [{"userid": 1, "month": 202002}])


def metric_rows():
    predicted, actual, previous = [1, 2, 2, 7], [0, 3, 4, 8], [2, 1, 5, 7]
    return [{"userid": i, "month": 202203, "repeat": 1,
             "Q8": {"real": y, "previous": p, "copy_previous": p, "llm": x}}
            for i, (x, y, p) in enumerate(zip(predicted, actual, previous))]


def test_common_metrics_against_independent_scipy_and_lower_cdf():
    result, rows = summarize(metric_rows(), ["llm", "copy_previous"], "Q8")
    measured = result["conditions"]["llm"]["aggregate"]
    assert measured["sample_center_mae_pp"] == 1
    assert measured["cross_person_iqr_pp"] == 1
    assert measured["real_cross_person_iqr_pp"] == 4
    assert measured["cross_section_w1_pp"] == pytest.approx(wasserstein_distance([1,2,2,7], [0,3,4,8]))
    assert measured["delta_w1_pp"] == pytest.approx(wasserstein_distance([-1,1,-3,0], [-2,2,-1,1]))
    assert measured["interpolated_iqr_pp"] != measured["cross_person_iqr_pp"]
    assert len(rows) == 4


def test_failed_new_answer_is_counted_before_common_exclusion():
    rows = metric_rows()
    for row in rows:
        row["Q8"]["new"] = row["Q8"]["llm"]
    rows[0]["Q8"]["new"] = None
    result, common = summarize(rows, ["llm", "new", "copy_previous"], "Q8")
    assert result["coverage"]["new"] == 3
    assert result["coverage"]["llm"] == 4
    assert result["common_rows"] == len(common) == 3
    assert result["conditions"]["llm"]["cells"][0]["n"] == 3
    assert result["conditions"]["copy_previous"]["cells"][0]["n"] == 3
    for row in rows:
        row["Q8"]["new"] = None
    assert summarize(rows, ["new", "copy_previous"], "Q8")[0]["status"] == "missing_common_cell"


def test_person_bootstrap_does_not_count_repeats_as_people():
    rows = metric_rows()
    repeated = [{**r, "repeat": 2} for r in rows]
    config = {"draws": 100, "seed": 73, "scope": "fixed months"}
    first = paired_intervals(rows, [("llm", "copy_previous")], "Q8", config)
    second = paired_intervals(rows+repeated, [("llm", "copy_previous")], "Q8", config)
    assert first == second
    assert second["persons"] == 4
    zero = paired_intervals(rows, [("llm", "llm")], "Q8", config)
    for value in zero["contrasts"]["llm_minus_llm"].values():
        assert value == {"difference_pp": 0, "interval_95": [0, 0]}


def test_screen_requires_both_repeats_distribution_update_and_coverage():
    def cond(center, cross, delta):
        return {"by_repeat": {str(r): dict(zip(MAIN, (center, cross, delta))) for r in (1,2)}}
    summary = {"status": "evaluated", "coverage": {"u1": 96, "own_previous": 96},
               "conditions": {"u1": cond(.5, 1, 2), "own_previous": cond(1,2,2)}}
    assert screen_candidate(summary, "u1")["pilot_signal"]
    summary["conditions"]["u1"]["by_repeat"]["2"]["delta_w1_pp"] = 2.1
    assert not screen_candidate(summary, "u1")["pilot_signal"]
    summary["conditions"]["u1"] = cond(.5, 1, 2)
    summary["coverage"]["u1"] = 95
    assert not screen_candidate(summary, "u1")["pilot_signal"]


def test_new_result_import_refuses_unmapped_ids_hash_drift_and_duplicates(tmp_path):
    answer = tmp_path/"answers.jsonl"
    manifest = tmp_path/"manifest.json"
    row = {"month": 202203, "agent_id": "a", "repeat": 1, "arm": "u1",
           "q9_probabilities": bins(4), "q8_point_pct": 1}
    protocol = {"research_line": "A", "months": [202203], "generation_repeats": [1,2],
                "llm_arms": ["own_previous"], "baseline_arms": ["copy_previous"]}
    def write(rows):
        answer.write_text("\n".join(json.dumps(r) for r in rows))
        manifest.write_text(json.dumps({"answers_sha256": hashlib.sha256(answer.read_bytes()).hexdigest(),
                                       "research_line": "A", "months": [202203], "repeats": [1,2],
                                       "arms": ["u1"], "model_requested": "example", "temperature": .5,
                                       "run_ids": ["test"]}))
    subjects = [{"month": 202203, "agent_id": "a"}]
    write([row])
    records, _, info = import_extra(answer, manifest, subjects, protocol)
    assert len(records) == 1 and info["missing_rows"] == 1
    write([row, row])
    with pytest.raises(ValueError, match="duplicate"):
        import_extra(answer, manifest, subjects, protocol)
    write([{**row, "agent_id": "unmatched"}])
    with pytest.raises(ValueError, match="Unknown"):
        import_extra(answer, manifest, subjects, protocol)
    write([row])
    answer.write_text(answer.read_text()+" ")
    with pytest.raises(ValueError, match="hash"):
        import_extra(answer, manifest, subjects, protocol)
    write([row])
    protocol["frozen_llm"] = {"model_requested": "different", "temperature": .5}
    with pytest.raises(ValueError, match="model/temperature"):
        import_extra(answer, manifest, subjects, protocol)


def test_invalid_probabilities_never_become_good_forecasts():
    assert score([10] * 9)["mean"] is None
    assert score([-1,101]+[0]*8)["mean"] is None
    assert score(None)["mean"] is None
    assert score([np.nan]*10)["mean"] is None
    assert score(bins(4))["mean"] == 1
