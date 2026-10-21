from copy import deepcopy

import pytest

from studies.sce_inflation_expectations.experiments.price_background import (
    add_background, extract_broader_prices, MARKER)
from studies.sce_inflation_expectations.procurement_price_views import BASKET, validate_cutoff


def food():
    return dict(reference_period='2021-08', published_at='2021-09-14T08:30:00-04:00',
                vintage='USDL-example', source_file='example.pdf', source_sha256='example',
                source_url='https://www.bls.gov/example.pdf', historical_release_archive=True)


def pages():
    # Deliberately distinguish index levels, annual change, monthly change and weights.
    return ['Table 1. Consumer Price Index '
            'All items . . . 100.0 201.0 202.0 203.0 5.3 0.2 0.7 0.5 0.3 '
            'Energy . . . 7.0 130.0 131.0 132.0 25.0 2.0 1.0 0.5 0.6 '
            'Table 2. Consumer Price Index '
            'All items . . . 100.0 5.3 0.2 0.7 0.5 0.3 '
            'Energy . . . 7.0 25.0 2.0 1.0 0.5 0.6 '
            'Table 3. Consumer Price Index unrelated '
            'Table 7. Consumer Price Index '
            'All items . . . 100.0 5.3 Energy . . . 7.0 25.0 ']


def messages():
    return [dict(role='user', content=(
        'Population and food-role canary.\nGeneral grocery-price background:\nFood +3.0%.\n'
        'BLS release 2021-09-14T08:30:00-04:00; availability relative to your previous survey: later.\n\n'
        + BASKET + 'Basket canary.\nGeneral news you encountered:\nNews canary.\n'
        'Public policy news brief (2021):\nPolicy canary.\n'
        'Your earlier survey response (2021-08):\nPrior canary.\nQuestionnaire and format canary.'))]


def test_extracts_annual_changes_not_index_or_monthly_columns():
    facts = extract_broader_prices(pages(), food())
    assert facts['all_items']['yoy_nsa_percent'] == 5.3
    assert facts['energy']['yoy_nsa_percent'] == 25.0
    assert facts['all_items']['reference_period'] == '2021-08'
    assert facts['energy']['vintage'] == 'USDL-example'


def test_cross_table_disagreement_fails_closed():
    broken = [pages()[0].replace('100.0 5.3 0.2', '100.0 5.4 0.2')]
    with pytest.raises(ValueError, match='disagreement'):
        extract_broader_prices(broken, food())


def test_treatment_is_one_reversible_insertion():
    original = messages(); before = deepcopy(original)
    result, block = add_background(original, extract_broader_prices(pages(), food()))
    assert original == before
    assert result[0]['content'].replace(block, '', 1) == original[0]['content']
    assert result[0]['content'].count(MARKER) == 1
    assert '12-month change +5.3% (not seasonally adjusted)' in block
    assert 'later.' in block
    assert result[0]['content'].split('Your earlier survey response (', 1)[1] == original[0]['content'].split('Your earlier survey response (', 1)[1]


def test_falling_energy_is_kept_without_directional_instruction():
    facts = extract_broader_prices(pages(), food()); facts['energy']['yoy_nsa_percent'] = -9.0
    _, block = add_background(messages(), facts)
    assert '12-month change -9.0%' in block
    assert 'increase your expectation' not in block


@pytest.mark.parametrize('status', ['earlier', 'later', 'same-day uncertain'])
def test_carries_recipient_specific_release_status(status):
    old = messages(); old[0]['content'] = old[0]['content'].replace('later.', status+'.')
    _, block = add_background(old, extract_broader_prices(pages(), food()))
    assert f'previous survey: {status}.' in block


def test_cannot_add_unregistered_series_or_mixed_release():
    facts = extract_broader_prices(pages(), food()); facts['gasoline'] = facts['energy']
    with pytest.raises(ValueError, match='two series'):
        add_background(messages(), facts)
    facts = extract_broader_prices(pages(), food()); facts['energy']['reference_period'] = '2021-09'
    with pytest.raises(ValueError, match='same release'):
        add_background(messages(), facts)


def test_duplicate_treatment_or_unknown_timing_is_rejected():
    facts = extract_broader_prices(pages(), food())
    treatment, _ = add_background(messages(), facts)
    with pytest.raises(ValueError, match='insertion boundary'):
        add_background(treatment, facts)
    broken = messages(); broken[0]['content'] = broken[0]['content'].replace('later.', 'unknown.')
    with pytest.raises(ValueError, match='timing tag'):
        add_background(broken, facts)


def test_release_after_cutoff_is_rejected():
    facts = extract_broader_prices(pages(), food())
    with pytest.raises(ValueError, match='future price'):
        validate_cutoff(facts.values(), '2021-09-13T23:59:59-04:00')
    validate_cutoff(facts.values(), '2021-09-14T23:59:59-04:00')
