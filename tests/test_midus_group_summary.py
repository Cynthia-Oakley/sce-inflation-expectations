"""Only invented records: never load real MIDUS data in agent-run tests."""
import json

import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.midus_group_summary import (
    TRAITS, joint_bins, summarize_frame, weighted_moments,
)


def test_weighted_population_moments_have_independent_expected_values():
    mean, cov = weighted_moments(np.array([[1.0, 2.0], [3.0, 6.0]]), np.array([1.0, 3.0]))
    np.testing.assert_allclose(mean, [2.5, 5.0])
    np.testing.assert_allclose(cov, [[0.75, 1.5], [1.5, 3.0]])


def test_small_joint_cell_suppresses_whole_histogram():
    values = np.array([[i, j] for i in [1, 2, 3] for j in [1, 2, 3] for _ in range(11)])
    result = joint_bins(values, np.ones(99), [[1.5, 2.5], [1.5, 2.5]])
    np.testing.assert_allclose(result["probabilities"], np.full((3, 3), 0.1111))
    assert joint_bins(values[:-1], np.ones(98), [[1.5, 2.5], [1.5, 2.5]]) is None


def test_official_sentinels_do_not_become_personality_or_weights():
    frame = pd.DataFrame({"RA1PRAGE": [30] * 61, "RA1PB1": [9] * 61,
                          "RA1SWGHT6": [1] * 61, "MRID": ["invented_private"] * 61})
    for field in TRAITS:
        frame[field] = 22 if field == "RA1SORIEN" else 2.0
    frame.loc[60, "RA1SNEURO"] = 8
    result = summarize_frame(frame)
    assert len(result["groups"]) == 1
    assert result["groups"][0]["mean"][0] == 2.0
    assert "invented_private" not in json.dumps(result)
    assert "MRID" not in json.dumps(result)
    frame.loc[59, "RA1SWGHT6"] = 99
    assert summarize_frame(frame)["groups"] == []


def test_uncovered_ages_and_wrong_weight_fail_without_extrapolation():
    frame = pd.DataFrame({"RA1PRAGE": [24] * 100, "RA1PB1": [5] * 100,
                          "RA1SWGHT6": [1] * 100})
    for field in TRAITS:
        frame[field] = 22 if field == "RA1SORIEN" else 2.0
    assert summarize_frame(frame)["groups"] == []
    with pytest.raises(ValueError):
        summarize_frame(frame, "RA1PWGHT6")
