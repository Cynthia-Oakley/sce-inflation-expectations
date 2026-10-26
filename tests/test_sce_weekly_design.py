from datetime import datetime

import pytest

from studies.sce_inflation_expectations.experiments.weekly_design import weekly_cutoffs,truncation_counts
from studies.sce_inflation_expectations.experiments.full_a_personal_inputs import _food_snapshot,_policy_snapshot


def test_five_fridays_not_an_artificial_four_week_month():
    points=weekly_cutoffs('202601')
    assert [p[:10] for p in points]==['2026-01-02','2026-01-09','2026-01-16','2026-01-23','2026-01-30']
    assert all((datetime.fromisoformat(b)-datetime.fromisoformat(a)).days==7 for a,b in zip(points,points[1:]))


def test_new_york_summer_and_winter_offsets():
    assert weekly_cutoffs('202601')[0].endswith('-05:00')
    assert weekly_cutoffs('202609')[0].endswith('-04:00')


@pytest.mark.parametrize('m,w',[('202613',4),('2026-01',4),('202601',7)])
def test_bad_grid_is_rejected(m,w):
    with pytest.raises(ValueError):weekly_cutoffs(m,w)


def test_filtering_is_by_instant_not_article_month():
    contexts={'a':dict(common_news=[{'pub_date':'2026-01-03T02:00:00Z'}],
        personal_news=[{'pub_date':'2026-01-03T05:30:00Z'}])}
    result=truncation_counts(contexts,'2026-01-02T23:59:59-05:00')
    assert result['old_selected_mean_surviving']==1


def test_before_release_uses_previous_available_snapshot(monkeypatch):
    import studies.sce_inflation_expectations.experiments.full_a_personal_inputs as module
    monkeypatch.setattr(module,'validate_cutoff',lambda facts,cutoff:None)
    old={'food_at_home':{'published_at':'2025-12-18T08:30:00-05:00'}}
    new={'food_at_home':{'published_at':'2026-01-13T08:30:00-05:00'}}
    data={'old':old,'new':new}
    assert _food_snapshot(data,'2026-01-09T23:59:59-05:00')==('old',old)
    assert _food_snapshot(data,'2026-01-16T23:59:59-05:00')==('new',new)


def test_policy_snapshot_does_not_use_later_decision():
    old=dict(published_at='2025-12-10T14:00:00-05:00',facts=['a','b','c'])
    new=dict(published_at='2026-01-28T14:00:00-05:00',facts=['d','e','f'])
    assert _policy_snapshot({'old':old,'new':new},'2026-01-23T23:59:59-05:00')==old
    assert _policy_snapshot({'old':old,'new':new},'2026-01-30T23:59:59-05:00')==new
