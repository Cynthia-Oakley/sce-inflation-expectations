import pytest

from studies.sce_inflation_expectations.experiments.weekly_preflight import roster, news_inventory


def test_second_stage_retains_each_cells_mass_without_answers():
    weights = {'a': dict(stratum='one', analysis_weight=1.),
               'b': dict(stratum='one', analysis_weight=3.),
               'c': dict(stratum='two', analysis_weight=6.)}
    rows, audit = roster(weights, 2, seed=7, minimum=1)
    assert len(rows) == 2
    assert {r['cell']: r['poststratified_weight'] for r in rows} == {'one': 4., 'two': 6.}
    assert audit['maximum_cell_fraction_error'] < 1e-12
    assert audit['effective_sample_size'] == pytest.approx(100 / 52)
    assert len({r['id'] for r in rows}) == 2


def test_roster_is_order_invariant_and_deterministic():
    w = {str(i): dict(stratum=str(i % 2), analysis_weight=i+1.) for i in range(10)}
    assert roster(w, 6, seed=4) == roster(dict(reversed(list(w.items()))), 6, seed=4)


def test_impossible_coverage_is_not_silently_reduced():
    w = {str(i): dict(stratum=str(i), analysis_weight=1.) for i in range(3)}
    with pytest.raises(ValueError):
        roster(w, 2)


def test_missing_weight_not_filled():
    with pytest.raises(ValueError):
        roster({'a': dict(stratum='one', analysis_weight=None)}, 1)


def article(aid, stamp, text='Food prices', hits=True):
    return dict(article_id=aid, pub_date=stamp, headline=text, abstract='', snippet='', new_hits=[1] if hits else [])


def test_missing_labels_are_cutoff_eligible_and_exclude_sce_answers():
    rows = [article('past', '2026-01-03T02:00:00Z'),
            article('future', '2026-01-03T05:30:00Z'),
            article('known', '2026-01-03T02:00:00Z'),
            article('irrelevant', '2026-01-03T02:00:00Z', hits=False),
            article('sce', '2026-01-03T02:00:00Z', 'Survey of Consumer Expectations inflation results')]
    eligible, missing = news_inventory(rows, {'known': {}}, '2026-01-02T23:59:59-05:00')
    assert {r['article_id'] for r in eligible} == {'past', 'known', 'irrelevant', 'sce'}
    assert set(missing) == {'past'}
