import json

import pytest

from studies.sce_inflation_expectations.evaluation.repeat_value import report


def run(tmp_path, pairs):
    rows = []
    for i, pair in enumerate(pairs):
        for repeat, mean in enumerate(pair, 1):
            rows.append({'month': 202001, 'agent_id': str(i), 'repeat': repeat,
                         'real': {'q9_mean': 3.}, 'design_survey_weight': 1.,
                         'arms': {'model': {'mean': mean}}})
    source = tmp_path/'cases.json'; source.write_text(json.dumps(rows))
    return report(source, tmp_path/'out')['arms']['model']['equal_month_means']


def test_identical_outputs_preserve_stable_cross_person_differences(tmp_path):
    r = run(tmp_path, [(1., 1.), (3., 3.), (5., 5.)])
    assert r['mean_absolute_repeat_gap_pp'] == 0
    assert r['generation_noise_fraction'] == 0
    assert r['noise_adjusted_between_variance_pp2'] > 0


def test_identical_across_people_has_no_defined_correlation(tmp_path):
    r = run(tmp_path, [(3., 3.), (3., 3.)])
    assert r['person_pearson_equal_weight'] is None
    assert r['generation_noise_fraction'] is None


def test_instability_not_falsely_reported_as_stable_diversity(tmp_path):
    r = run(tmp_path, [(1., 5.), (5., 1.)])
    assert r['mean_absolute_repeat_gap_pp'] == pytest.approx(4.)
    assert r['noise_adjusted_between_variance_pp2'] < 0
