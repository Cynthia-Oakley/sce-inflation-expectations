"""Calendar, input isolation and empirical donor invariants on invented people."""
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.prior_belief_preparation import (
    MARKER, add_prior, derangement, eligible_previous, entry_inventory, label_panel,
    matched_entry_pool, month_offset, prior_record, valid_bins,
)


def fake_rows():
    f = pd.DataFrame({"userid": [1, 1, 1, 2, 2, 3, 4],
        "date": [202012, 202101, 202103, 202101, 202102, 202101, 202101],
        "tenure": [1, 2, 3, 5, 6, 1, 13], "weight": [1.0] * 7,
        "Q8v2part2": [2.0] * 7, "_AGE_CAT": ["Under 40"] * 7,
        "_EDU_CAT": ["College"] * 7, "_NUM_CAT": ["High"] * 7})
    for i in range(1, 11):
        f[f"Q9_bin{i}"] = 100.0 if i == 4 else 0.0
    return f


def test_calendar_gap_and_entry_label_do_not_use_first_cached_row():
    f = label_panel(fake_rows())
    assert month_offset(202101, -1) == 202012
    assert month_offset(202203, -10) == 202105
    assert f.loc[f.userid.eq(1), "panel_status"].tolist() == [
        "entry_tenure_1", "adjacent_returner", "returner_after_gap"]
    assert f.loc[f.userid.eq(2), "panel_status"].tolist() == [
        "unobserved_previous_or_left_boundary", "adjacent_returner"]
    assert f.loc[f.userid.eq(4), "panel_status"].item() == "invalid_or_extended_tenure"


def test_future_tenure_reset_does_not_change_historical_entry_pool():
    f = fake_rows()
    extra = f.iloc[[0]].copy()
    extra["date"], extra["tenure"] = 202104, 1
    labeled = label_panel(pd.concat([f, extra], ignore_index=True))
    assert labeled.loc[(labeled.userid == 1) & (labeled.date == 202012), "timeline_consistent"].item()
    assert not labeled.loc[(labeled.userid == 1) & (labeled.date == 202104), "timeline_consistent"].item()
    assert 1 in set(entry_inventory(labeled, 202102).userid)


def test_probability_validation_never_normalizes_real_answers():
    assert valid_bins([0, 0, 0, 100, 0, 0, 0, 0, 0, 0])
    assert not valid_bins([0, 0, 0, 99, 0, 0, 0, 0, 0, 0])
    assert not valid_bins([float("nan")] * 10)


def test_prior_injection_preserves_body_and_rejects_current_answers():
    row = fake_rows().iloc[0].to_dict()
    row["weight"] = 99.9
    p = prior_record(row)
    assert set(p) == {"source_month", "point_pct", "q9"}
    base = [{"role": "user", "content": "Shared P/E.\n\n" + MARKER + " original question body"}]
    before = deepcopy(base)
    result, block = add_prior(base, p, 202101)
    assert base == before
    assert result[0]["content"].replace(block, "", 1) == base[0]["content"]
    assert "99.9" not in result[0]["content"]
    p["source_month"] = 202101
    with pytest.raises(ValueError, match="previous calendar"):
        add_prior(base, p, 202101)
    p["source_month"] = 202012
    p["weight"] = 1
    with pytest.raises(ValueError, match="Unexpected"):
        add_prior(base, p, 202101)


def test_permutation_keeps_inventory_and_has_no_self_match():
    ids = [f"test{i}" for i in range(12)]
    a, b = derangement(ids, 42), derangement(list(reversed(ids)), 42)
    assert a == b and sorted(a.values()) == sorted(ids)
    assert all(k != v for k, v in a.items())


def test_target_answers_and_weights_cannot_change_prior_eligibility():
    f = fake_rows()
    f["survey_date"] = pd.to_datetime(f.date.astype(str), format="%Y%m")
    f = label_panel(f)
    current, previous = f.iloc[1].to_dict(), f.iloc[0].to_dict()
    cutoff = pd.Timestamp("2021-01-15").date()
    assert eligible_previous(current, previous, 202101, cutoff)
    current.update(weight=9999, Q8v2part2=-100, Q9_bin4=0, Q9_bin10=100, Q9_mean=-90)
    assert eligible_previous(current, previous, 202101, cutoff)
    previous["date"] = 202011
    assert not eligible_previous(current, previous, 202101, cutoff)


def test_joint_donor_history_uses_supported_fields_and_never_target_month():
    f = pd.DataFrame({"userid": range(65), "date": [202012] * 30 + [202101] * 30 + [202102] * 5,
                      "tenure": [1] * 65, "weight": [1] * 65, "Q8v2part2": [2] * 65,
                      "_AGE_CAT": ["Under 40"] * 65, "_EDU_CAT": ["College"] * 65,
                      "_NUM_CAT": ["High"] * 65})
    for i in range(1, 11):
        f[f"Q9_bin{i}"] = 100 if i == 4 else 0
    pool = entry_inventory(label_panel(f), 202102)
    assert len(pool) == 60 and pool.date.max() == 202101
    donors, keys = matched_entry_pool(pool, {"_AGE_CAT": "Under 40", "_EDU_CAT": "College", "_NUM_CAT": "Low"})
    assert len(donors) == 60 and keys == ["_AGE_CAT", "_EDU_CAT"]
    donors, keys = matched_entry_pool(pool.iloc[:10], {"_AGE_CAT": "Under 40"})
    assert donors.empty and keys is None
