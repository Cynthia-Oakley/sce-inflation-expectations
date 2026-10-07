"""Independent information-time and shutdown-period checks."""
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from sce_release_available import cpi_available
import build_sce_environment as bls
from studies.sce_inflation_expectations.environment_authoring.availability import select_available


def record(measure,ref,published,value):
    return {'signal_id':f'{measure}_{ref}','measure':measure,'reference_period':ref,
            'published_at':published,'value':value,'unit':'percent','eligibility':'eligible'}


def test_each_series_uses_own_last_published_month():
    rows=[record('CPI','2025-08','2025-09-11T08:30:00-04:00',2.9),
          record('CPI','2025-09','2025-10-24T08:30:00-04:00',3.0),
          record('Unemployment','2025-08','2025-09-05T08:30:00-04:00',4.3),
          record('Unemployment','2025-09','2025-11-20T08:30:00-05:00',4.4)]
    selected,_=select_available(rows,'2025-10-31T23:59:59-04:00',set())
    assert {(r['measure'],r['reference_period']) for r in selected}=={('CPI','2025-09'),('Unemployment','2025-08')}
    assert len(rows)==4 and all('role' not in r for r in rows)


def test_history_keeps_missing_calendar_month_and_does_not_impute():
    rows=[record('CPI','2025-09','2025-10-24T08:30:00-04:00',3.0),
          record('CPI','2025-11','2025-12-18T08:30:00-05:00',2.7)]
    selected,notes=select_available(rows,'2025-12-31T23:59:59-05:00',{'CPI'})
    assert [r['reference_period'] for r in selected]==['2025-09','2025-11']
    assert [r['role'] for r in selected]==['history','latest_release']
    assert notes[0]['history_reference_periods']==['2025-09']


def test_duplicate_or_naive_publication_is_rejected():
    r=record('CPI','2025-09','2025-10-24T08:30:00-04:00',3.0)
    with pytest.raises(ValueError,match='duplicate'):select_available([r,r],'2025-10-31T23:59:59-04:00')
    r['published_at']='2025-10-24T08:30:00'
    with pytest.raises(ValueError,match='timezone'):select_available([r],'2025-10-31T23:59:59-04:00')


def test_november_shutdown_two_month_change_not_single_month():
    text=('CONSUMER PRICE INDEX - NOVEMBER 2025 USDL-25-1584 '
          'The Consumer Price Index for All Urban Consumers (CPI-U) increased 0.2 percent '
          'on a seasonally adjusted basis over the 2 months from September 2025 to November 2025. '
          'Over the last 12 months, the all items index increased 2.7 percent before seasonal adjustment.')
    result=cpi_available(text,'2025-11')
    assert result['cpi_mom_sa_pct'] is None
    assert result['cpi_yoy_nsa_pct']['value']==2.7
    assert result['cpi_two_month_sa_pct']['value']==0.2
    with pytest.raises(ValueError,match='CPI m/m'):bls.transcribe_cpi(text,'2025-11')
    with pytest.raises(ValueError,match='context'):cpi_available(text.replace('2 months','1 month'),'2025-11')


def test_shutdown_employment_rate_is_dated_to_november():
    text=('USDL-25-1576 In November, the unemployment rate, at 4.6 percent, '
          'was little changed from September. Total nonfarm payroll employment '
          'changed little in November (+64,000).')
    result=bls.transcribe_empsit(text,'2025-11')
    assert result['unemployment_rate_pct']['value']==4.6
    assert result['nonfarm_payroll_change_k']['value']==64
