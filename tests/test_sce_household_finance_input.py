"""Synthetic checks of the household Q1 input whitelist and annual wording."""
import pytest

from studies.sce_inflation_expectations import household_finance_input as h


def record():
    return {'schema_version': h.SCHEMA_VERSION, 'research_line': h.RESEARCH_LINE,
            'target_month': 202004, 'current_q1_code': 2, 'current_q1_source_month': 202004,
            'previous_q1_code': 3, 'previous_q1_source_month': 202003,
            'current_source_sha256': 'a'*64, 'previous_source_sha256': 'a'*64}


def test_prespecified_fact_and_perspective_wording_and_no_prompt_provenance():
    r = record()
    facts = h.render_household_finance_block('financial_facts', r)
    assert facts == (
        "Your household financial circumstances:\n"
        "- In the previous survey month, you described your household's finances as about the same as 12 months earlier.\n"
        "- In the current survey month, you describe your household's finances as somewhat worse than 12 months earlier.\n\n"
    )
    assert h.render_household_finance_block('baseline', r) == ''
    assert h.render_household_finance_block('financial_perspective', r) == facts + h.PERSPECTIVE_SENTENCE + '\n\n'
    for forbidden in ('sha256', '202004', 'income shock', 'lost your job', ' rent ', 'Q1', 'financial_facts'):
        assert forbidden not in facts
    assert r == record()


@pytest.mark.parametrize('code,expected', [(1, 'much worse'), (2, 'somewhat worse'),
    (3, 'about the same'), (4, 'somewhat better'), (5, 'much better')])
def test_each_official_category_and_equal_annual_assessments(code, expected):
    r = record()
    r['current_q1_code'] = r['previous_q1_code'] = code
    block = h.render_household_finance_block('financial_facts', r)
    assert block.count(expected) == 2
    assert block.count('12 months earlier') == 2


def test_missing_is_unknown_without_backfilling_and_january_rollover():
    r = record()
    r.update(target_month=202101, current_q1_source_month=202101,
             previous_q1_code=None, previous_q1_source_month=None, previous_source_sha256=None)
    assert h.previous_month(202101) == 202012
    block = h.render_household_finance_block('financial_facts', r)
    assert 'previous survey month' in block and 'are unknown' in block
    r.update(previous_q1_code=5, previous_q1_source_month=202012, previous_source_sha256='b'*64,
             current_q1_code=None, current_q1_source_month=None, current_source_sha256=None)
    assert h.validate_household_finance_record(r) == r
    block = h.render_household_finance_block('financial_facts', r)
    assert 'much better than 12 months earlier' in block and 'current survey month' in block
    assert block.count('unknown') == 1


@pytest.mark.parametrize('field,value', [
    ('userid', 1), ('agent_id', 'anon'), ('current_q9', {'bin1': 100}),
    ('schema_version', 'other'), ('research_line', 'B'),
    ('target_month', '202004'), ('target_month', 202004.), ('target_month', True),
    ('target_month', 202013), ('target_month', 202000),
    ('current_q1_code', True), ('current_q1_code', 2.), ('current_q1_code', '2'),
    ('current_q1_code', 0), ('current_q1_code', 6), ('previous_q1_code', -1),
    ('current_q1_source_month', 202003), ('current_q1_source_month', 202005),
    ('current_q1_source_month', '202004'), ('current_q1_source_month', 202004.),
    ('previous_q1_source_month', 202002), ('previous_q1_source_month', 202004),
    ('previous_q1_source_month', None), ('previous_q1_source_month', 202003.),
    ('current_source_sha256', 'A'*64), ('current_source_sha256', 'a'*63),
    ('previous_source_sha256', None), ('previous_source_sha256', 'g'*64),
    ('current_q1_code', None),
])
def test_strict_whitelist_sources_and_integer_validation_even_in_baseline(field, value):
    r = record()
    r[field] = value
    with pytest.raises(ValueError):
        h.validate_household_finance_record(r)
    for arm in h.ARMS:
        with pytest.raises(ValueError):
            h.render_household_finance_block(arm, r)


def test_missing_consistency_and_unknown_arm():
    r = record()
    del r['schema_version']
    with pytest.raises(ValueError, match='whitelist'):
        h.validate_household_finance_record(r)
    for value in (None, [], 2):
        with pytest.raises(ValueError, match='whitelist'):
            h.validate_household_finance_record(value)
    r = record()
    r.update(previous_q1_code=None, previous_q1_source_month=None)
    with pytest.raises(ValueError, match='Missing Q1'):
        h.validate_household_finance_record(r)
    with pytest.raises(ValueError, match='arm'):
        h.render_household_finance_block('invented', record())
