"""Q1 preparation must not read targets or borrow a nonadjacent person's state."""
import pandas as pd
import pytest

from studies.sce_inflation_expectations.household_finance_preparation import q1_records


def test_q1_links_calendar_rollover_and_does_not_borrow_other_person():
    frame = pd.DataFrame([
        {'date': 201912, 'userid': 11, 'financial_change': 3},
        {'date': 202001, 'userid': 11, 'financial_change': 2},
        {'date': 201911, 'userid': 22, 'financial_change': 1},
        {'date': 202001, 'userid': 22, 'financial_change': 4},
    ])
    records = q1_records([{'month': 202001, 'userid': 11, 'agent_id': 'one'},
                          {'month': 202001, 'userid': 22, 'agent_id': 'two'}], frame, 'a'*64)
    one, two = records[202001, 'one'], records[202001, 'two']
    assert (one['previous_q1_code'], one['previous_q1_source_month']) == (3, 201912)
    assert one['current_q1_code'] == 2
    assert two['previous_q1_code'] is None
    assert two['previous_q1_source_month'] is None
    assert two['previous_source_sha256'] is None
    assert 'userid' not in one and 'agent_id' not in one


def test_q1_preparation_rejects_target_columns_and_duplicate_source():
    frame = pd.DataFrame([{'date': 202001, 'userid': 11, 'financial_change': 2}])
    links = [{'month': 202001, 'userid': 11, 'agent_id': 'one'}]
    with pytest.raises(ValueError, match='whitelist'):
        q1_records(links, frame.assign(Q9_mean=3.2), 'a'*64)
    with pytest.raises(ValueError, match='Duplicate Q1'):
        q1_records(links, pd.concat([frame, frame]), 'a'*64)


def test_q1_preparation_does_not_turn_missing_state_into_neutral():
    frame = pd.DataFrame([{'date': 202001, 'userid': 11, 'financial_change': float('nan')}])
    record = q1_records([{'month': 202001, 'userid': 11, 'agent_id': 'one'}], frame, 'a'*64)[202001, 'one']
    assert record['current_q1_code'] is None
    assert record['current_q1_source_month'] is None
    assert record['current_source_sha256'] is None
