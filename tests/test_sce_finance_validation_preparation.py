"""Check proportional allocation and outcome-free deterministic selection."""
from types import SimpleNamespace

import pytest

from studies.sce_inflation_expectations.finance_validation_preparation import (
    proportional_sample, registered_protocol,
)


def personas(high, low):
    return [SimpleNamespace(agent_id=f'{group}_{i:03}', attributes={'numeracy': group})
            for group, n in [('high', high), ('low', low)] for i in range(n)]


def test_half_sample_rounding_tie_is_predefined_not_low_oversampling():
    frame = personas(73, 23)
    ids, probabilities, audit = proportional_sample(frame, 202206)
    # 36.5/11.5: tie broken alphabetically, rather than chosen after performance.
    assert audit['selected_stratum_n'] == {'high': 37, 'low': 11}
    assert len(ids) == 48
    assert {probabilities[aid] for aid in ids if aid.startswith('high')} == {37 / 73}
    assert {probabilities[aid] for aid in ids if aid.startswith('low')} == {11 / 23}
    assert proportional_sample(list(reversed(frame)), 202206) == (ids, probabilities, audit)


def test_sequential_weights_recover_first_stage_totals_for_stratum_constants():
    frame = personas(61, 35)
    ids, pi2, audit = proportional_sample(frame, 202306)
    # Given the first stage, conditional Horvitz-Thompson expansion recovers
    # each stratum count exactly for constant-within-stratum quantities.
    for group, total in [('high', 61), ('low', 35)]:
        assert sum(1 / pi2[aid] for aid in ids if aid.startswith(group)) == pytest.approx(total)
    assert audit['selected_stratum_n'] == {'high': 31, 'low': 17}


def test_sampling_fails_when_a_stratum_would_be_excluded_or_ids_repeat():
    with pytest.raises(ValueError, match='positive inclusion'):
        proportional_sample(personas(95, 1), 202206, n=1)
    frame = personas(10, 10)
    with pytest.raises(ValueError, match='Unique'):
        proportional_sample(frame + [frame[0]], 202206, n=10)


def test_protocol_is_two_arm_conditional_replication_not_blind_forecast():
    p = registered_protocol(4.)
    assert p['months'] == [202206, 202306, 202410, 202509]
    assert p['arms'] == ['baseline', 'financial_facts']
    assert p['planned_calls'] == 768
    assert p['primary_metric'] == 'q9_center_mae_pp'
    assert p['primary_weight'] == 'design_survey_weight'
    assert 'not strict b' in p['information_boundary'].lower()
    assert 'not a pristine' in p['month_selection'].lower()
