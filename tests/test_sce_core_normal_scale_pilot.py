from studies.sce_inflation_expectations.experiments.core_normal_scale_pilot import shared_design


def population():
    return [{'id': str(i), 'weight': 1. + (i % 4) / 2,
             'entry': 'newcomer' if i % 3 == 0 else 'returner',
             'education': 'college' if i < 12 else 'high_school',
             'numeracy': 'High', 'age': 'under_40', 'income': 'under_50k'} for i in range(30)]


def test_shared_calls_equal_union_not_sum_and_old_selection_unchanged():
    p = population()
    result = shared_design(p, month=202206, settings=((8, 1), (16, 2)), audit_n=4)
    small = {r['id'] for r in result['designs']['8']['selected']}
    large = {r['id'] for r in result['designs']['16']['selected']}
    union = {r['id'] for r in result['core_union']}
    audit = {r['id'] for r in result['audit']['selected']}
    assert union == small | large
    assert not union & audit
    assert result['summary']['unique_llm_positions'] == len(union) + 4
    assert result['summary']['unique_llm_positions'] < 8 + 16 + 8
    same_small = shared_design(p, month=202206, settings=((8, 1),), audit_n=4)
    assert same_small['designs']['8'] == result['designs']['8']


def test_audit_weights_reference_remaining_union_frame():
    result = shared_design(population(), month=202206, settings=((8, 1), (16, 2)), audit_n=4)
    for row in result['audit']['selected']:
        c = result['audit']['allocation']['cells'][row['cell']]
        assert row['inclusion_probability'] == c['selected_n'] / c['frame_n']
    assert result['audit']['allocation']['frame_n'] == result['summary']['shared_audit_population_n']
    assert result['summary']['shared_audit_population_n'] == 30 - result['summary']['core_union_n']


def test_weights_are_budget_specific_and_input_order_invariant():
    p = population()
    first = shared_design(p, month=202206, settings=((8, 1), (16, 2)), audit_n=4)
    second = shared_design(list(reversed(p)), month=202206, settings=((8, 1), (16, 2)), audit_n=4)
    assert first == second
    by_id = {b: {r['id']: r for r in d['selected']} for b, d in first['designs'].items()}
    assert any(by_id['8'][i]['inclusion_probability'] != by_id['16'][i]['inclusion_probability']
               for i in by_id['8'])
