from datetime import datetime, timezone
import numpy as np
import pytest

from studies.sce_inflation_expectations.macro_profile_sources import employment_pdf, bea_pdf, numbers, bea_xlsx
from studies.sce_inflation_expectations.macro_profile_extension import select_visible, forecast_composition, income_shares


def test_bls_seasonal_columns_from_official_april_2021():
    # BLS USDL-21-0816: different NSA/SA values make wrong column detectable.
    pages = ['Table A-1. Not seasonally adjusted Seasonally adjusted\n'
             'Participation rate 60.0 61.5 61.4 60.2 61.5 61.4 61.4 61.5 61.7\n'
             'Employment-population ratio 51.3 57.7 57.9 51.3 57.4 57.5 57.6 57.8 57.9\n'
             'Unemployment rate 14.4 6.2 5.7 14.8 6.7 6.3 6.2 6.0 6.1\n',
             'Table B-3. seasonally adjusted\nTotal private $30.07 $30.00 $29.96 $30.17 $1,028.39 $1,038.00 $1,045.60 $1,055.95\n']
    rows = employment_pdf(pages, '2021-04')
    current = {r['series']: r['value'] for r in rows if r['reference_period'] == '2021-04'}
    assert current == {'LNS11300000': 61.7, 'LNS12300000': 57.9, 'LNS14000000': 6.1,
                       'CES0500000003': 30.17, 'CES0500000011': 1055.95}
    assert next(r for r in rows if r['series'] == 'CES0500000003')['reference_period'] == '2020-04'
    # Shutdown missing cells must preserve column positions, not shift to an NSA column.
    missing = pages[0].replace('61.4 61.5 61.7', '61.4 – 61.7')
    assert employment_pdf([missing, pages[1]], '2021-04')[0]['value'] == 61.7
    with pytest.raises(ValueError, match='columns'):
        employment_pdf([pages[0].replace('61.5 61.7', '61.7'), pages[1]], '2021-04')


def test_bea_embargo_and_saar_months():
    pages = ['EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Friday, May 28, 2021',
             'Table 1. Personal Income and Its Disposition (Months)\n'
             '1 Personal income 19762.2 19728.2 19544.4 19677.1 21683.1 20186.5 24400.5 21195.2 1\n'
             '3 Wages and salaries 9000.0 9001.0 9002.0 9003.0 9004.0 9005.0 9006.0 10079.2 3\n']
    rows = bea_pdf(pages, '2021-04')
    assert rows[7]['value'] == 21195.2
    assert rows[0]['reference_period'] == '2020-09'
    assert rows[0]['published_at'] == '2021-05-28T08:30:00-04:00'
    assert rows[0]['unit'] == 'billion USD SAAR'
    assert numbers('17, 434.8 17,500.7') == [17434.8, 17500.7]
    late = [pages[0].replace('8:30', '10:00'), pages[1]]
    assert bea_pdf(late, '2021-04')[0]['published_at'] == '2021-05-28T10:00:00-04:00'


def test_excel_independent_amount_columns(tmp_path):
    from openpyxl import Workbook
    w = Workbook(); sheet = w.active; sheet.title = 'Table 1'
    sheet.append(['Line', None, 2020, 2020, 2020, 2020, 2021])
    sheet.append([1, 'Personal income', 19000.1, 19001.1, 19002.1, 19003.1, 21000.1])
    sheet.append([3, 'Wages and salaries', 9000.1, 9001.1, 9002.1, 9003.1, 9500.1])
    p = tmp_path/'official.xlsx'; w.save(p)
    assert bea_xlsx(p)['BEA_PERSONAL_INCOME'] == [19000.1, 19001.1, 19002.1, 19003.1, 21000.1]


def test_vintage_cannot_see_future_revision():
    common = dict(series='X', reference_period='2021-03', release_reference_period='2021-03', eligibility='eligible')
    rows = [{**common, 'published_at': '2021-04-13T08:30:00-04:00', 'value': 2.6},
            {**common, 'published_at': '2021-05-12T08:30:00-04:00', 'value': 2.7}]
    assert select_visible(rows, datetime(2021, 4, 30, tzinfo=timezone.utc))[('X', 202103)]['value'] == 2.6
    assert select_visible(rows, datetime(2021, 5, 31, tzinfo=timezone.utc))[('X', 202103)]['value'] == 2.7


def test_training_and_scaler_do_not_use_unavailable_outcomes():
    # Changing both future outcomes and future X cannot alter an earlier forecast.
    rows = [dict(month=201801+i, base=[.4, .3, .3], truth=[.41, .3, .29], features=[i]) for i in range(6)]
    test = dict(month=202001, donor_end=201804, base=[.4, .3, .3], features=[4])
    p, a = forecast_composition(rows, test, [0], min_train=4)
    for r in rows[4:]:
        r['truth'] = [.01, .98, .01]; r['features'] = [100000]
    q, b = forecast_composition(rows, test, [0], min_train=4)
    assert p == q and a == b
    assert a['max_train_month'] == 201804
    assert np.isclose(sum(p), 1)
    with pytest.raises(ValueError):
        forecast_composition(rows, {**test, 'donor_end': 202001}, [0], min_train=4)


def test_income_unknown_is_separate():
    assert income_shares({'under_50k': .3, '50k_to_100k': .3, 'over_100k': .35, 'unknown': .05}).tolist() == [.3, .3, .35, .05]
    with pytest.raises(ValueError):
        income_shares({'under_50k': .4, 'over_100k': .7})
