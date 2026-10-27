"""Final readout refuses incomplete and duplicated weekly score support."""
import pytest
from studies.sce_inflation_expectations.experiments.weekly_final_readout import primary_rows


def rows():
    result=[]
    for m,n in enumerate((5,4,4,5,4,4,5,4,4,4,4)):
        for i in range(n):
            result.append(dict(step_key=f'w{len(result):02}',target_reference_period=f'm{m:02}',main_score_point=i==n-1))
    return result


def test_47_unique_weeks_one_point_for_each_target_month():
    r=rows();assert len(primary_rows(r))==11


def test_partial_run_does_not_become_full_score():
    with pytest.raises(ValueError,match='47 unique'):primary_rows(rows()[:35])


def test_repeated_week_is_refused():
    r=rows();r[-1]=dict(r[0])
    with pytest.raises(ValueError,match='47 unique'):primary_rows(r)


def test_duplicate_target_month_is_refused():
    r=rows();selected=primary_rows(r);selected[1]['target_reference_period']=selected[0]['target_reference_period']
    with pytest.raises(ValueError,match='11 target'):primary_rows(r)
