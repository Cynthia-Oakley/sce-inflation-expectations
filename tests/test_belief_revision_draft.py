import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / 'studies/sce_inflation_expectations/belief_revision.py'
spec = importlib.util.spec_from_file_location('revision_draft', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def prior():
    return {'point_pct': 3., 'q9': {f'bin{i}': (90. if i == 4 else 10. if i == 5 else 0.) for i in range(1, 11)}}


def test_probability_mass_movement_and_point_change_are_different_units():
    p = prior()
    change = {'point_revision_pp': 1., 'q9_revision_pp': {f'bin{i}': (5. if i == 3 else -5. if i == 5 else 0.) for i in range(1, 11)}}
    got = module.revision_to_answer(p, change)
    assert got['point_pct'] == 4.
    assert got['q9']['bin3'] == 5.
    assert got['q9']['bin4'] == 90.
    assert got['q9']['bin5'] == 5.


def test_every_valid_answer_roundtrips_even_with_decimal_probabilities():
    current = {'point_pct': -1.7, 'q9': {f'bin{i}': 10. for i in range(1, 11)}}
    current['q9']['bin1'] = 9.9
    current['q9']['bin2'] = 10.1
    got = module.revision_to_answer(prior(), module.answer_to_revision(prior(), current))
    assert got == current


def test_invalid_revision_fails_without_repair():
    delta = module.answer_to_revision(prior(), prior())
    delta['q9_revision_pp']['bin1'] = -5.
    delta['q9_revision_pp']['bin2'] = 5.
    with pytest.raises(ValueError, match='Invalid probability'):
        module.revision_to_answer(prior(), delta)
    delta['q9_revision_pp']['bin1'] = 1.
    with pytest.raises(ValueError, match='sum to zero'):
        module.revision_to_answer(prior(), delta)


def test_prompt_does_not_discard_the_information_or_prior():
    text = 'P E Your earlier survey response Q8 Q9\nReply with ONLY a JSON object old format'
    got = module.draft_revision_messages([{'role': 'user', 'content': text}])[0]['content']
    assert got.startswith('P E Your earlier survey response Q8 Q9\n')
    assert 'old format' not in got
    assert 'point_revision_pp' in got
