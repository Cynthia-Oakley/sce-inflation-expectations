import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.news_label_id_repair import correct_single_id_substitution


def text(ids):
    return json.dumps({'labels': [dict(article_id=i, tone='alarming', persistence='temporary') for i in ids]})


def test_unique_one_character_identifier_repair_changes_no_semantics():
    original = text(['abc1', 'defb', 'ghi3'])
    fixed, audit = correct_single_id_substitution(original, ['abc1', 'def2', 'ghi3'])
    assert fixed['labels'][1] == dict(article_id='def2', tone='alarming', persistence='temporary')
    assert audit['tone_and_persistence_changed'] is False
    assert json.loads(original)['labels'][1]['article_id'] == 'defb'


@pytest.mark.parametrize('ids', [['abc1', 'abc1', 'ghi3'], ['abc1', 'debb', 'ghi3'],
                               ['ghi3', 'defb', 'abc1'], ['abc1', 'defb']])
def test_ambiguous_missing_duplicate_reordered_or_multichar_cases_stay_unrepaired(ids):
    with pytest.raises(ValueError):
        correct_single_id_substitution(text(ids), ['abc1', 'def2', 'ghi3'])
