"""Concrete regressions for full-frame delivery and single-use survey weights."""
import pytest
from studies.sce_inflation_expectations.experiments.fullperiod_materialization import systematic_pps, finite_weight


def test_systematic_weight_applied_once():
    # A 1:3 weighted distribution yields exactly 25:75 equal-weight slots.
    picks=systematic_pps([1.,3.],100,20261022)
    assert picks.count(0)==25 and picks.count(1)==75
    assert picks==systematic_pps([1.,3.],100,20261022)


@pytest.mark.parametrize('value',[None,float('nan'),0,-1,float('inf')])
def test_missing_weights_remain_missing(value):
    assert finite_weight(value) is None


def test_invalid_donor_weights_cannot_be_imputed():
    with pytest.raises(ValueError): systematic_pps([1.,None],100,42)


def test_cancelled_reference_uses_actual_archived_pdf():
    from studies.sce_inflation_expectations.experiments.fullperiod_materialization import effective_reference
    cov={'diagnostics':{'ref_month':'2025-10','cpi_release_file':'cpi_2025_09_released_2025_10_24.pdf'}}
    assert effective_reference(cov)=='2025-09'


def test_missing_monthly_change_is_not_rendered_as_zero():
    from studies.sce_inflation_expectations.procurement_price_views import fact_line
    result=fact_line({'label':'Food at home','mom_nsa_percent':None,'yoy_nsa_percent':1.9,'reference_period':'2025-11'})
    assert 'not published' in result and '1.9%' in result and 'unchanged' not in result


def test_news_boundary_enrichment_keeps_complete_prompt_fields(tmp_path):
    import json
    from studies.sce_inflation_expectations.experiments.fullperiod_materialization import news_pool_for_prompts
    class Rules:
        def classify(self,doc): return ['inflation']
    folder=tmp_path/'data/raw/nyt_archive';folder.mkdir(parents=True)
    doc={'_id':'nyt://one','headline':{'main':'Prices'},'abstract':'Food prices','snippet':'Food prices',
         'document_type':'article','pub_date':'2026-07-01T14:55:07.172Z','print_section':'A','print_page':'1'}
    (folder/'2026-06.json').write_text(json.dumps({'response':{'docs':[doc]}}))
    doc={**doc,'pub_date':'2026-07-01T14:55:07Z'}
    (folder/'2026-07.json').write_text(json.dumps({'response':{'docs':[doc]}}))
    rows,counts,_=news_pool_for_prompts(tmp_path,'2026-07','2026-07-14T23:59:59-04:00',Rules())
    assert len(rows)==1 and rows[0]['placement']=='a1' and rows[0]['headline']=='Prices'
    assert counts['conflicting_duplicate_kept_first']==1
