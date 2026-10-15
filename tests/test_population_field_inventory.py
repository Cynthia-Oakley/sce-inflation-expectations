"""Historical update semantics; no data files/API required."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation'))
from population_field_inventory import latest_income, family_state


def members(prefix, spouse=0, child=0, nonrelative=0):
    row = {f'{prefix}_{i}': 0 for i in range(1, 10)}
    row.update({f'{prefix}_1': spouse, f'{prefix}_5': child,
                f'{prefix}_8': nonrelative, f'{prefix}_9': int(spouse+child+nonrelative == 0)})
    return row


def test_repeat_income_supersedes_entry_category_without_becoming_monthly_wages():
    assert latest_income([(202001, {'Q47': 5}), (202002, {'D6': 8})]) == (202002, 8, 'D6')


def test_household_change_without_complete_update_invalidates_entry():
    entry = members('Q45new', spouse=1)
    state, _ = family_state([(202001, entry), (202002, {'D1': 2})])
    assert state is None


def test_repeat_family_update_includes_new_child_excludes_nonrelative():
    entry = members('Q45new', spouse=1)
    update = {'D1': 2, **members('D2new', spouse=1, child=1, nonrelative=1)}
    state, source = family_state([(202001, entry), (202002, update)])
    assert state == {'family_size_excluding_nonrelatives': 3, 'children': 1}
    assert source == 'D2new'
