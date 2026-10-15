from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from statsmodels.stats.sandwich_covariance import cov_cluster

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation'))
from population_associations import (ENTRY_CODES, QUIZ, attach_history,
    fit_month_model, adjacent_differences, wquantile)


def test_absorbed_wls_matches_independent_explicit_month_dummies_and_cluster_covariance():
    rng = np.random.default_rng(852)
    n, months = 160, np.repeat(np.arange(8), 20)
    persons = np.tile(np.arange(20), 8)
    x = rng.normal(size=(n, 2)); w = rng.uniform(.2, 2., size=n)
    y = 3*x[:, 0]-2*x[:, 1]+months+rng.normal(size=n)
    got = fit_month_model(y, x, w, months, persons)
    ww = w/np.bincount(months, weights=w)[months]*(n/8)
    dummy = np.eye(8)[months]
    independent = sm.WLS(y, np.column_stack([x, dummy]), weights=ww).fit()
    np.testing.assert_allclose(got['coef'], independent.params[:2], atol=1e-10)
    np.testing.assert_allclose(got['cov'], cov_cluster(independent, persons, use_correction=True)[:2, :2], atol=1e-10)


def test_entry_forward_only_and_missing_current_finance_not_carried():
    rows = []
    for date in [202001, 202002, 202003]:
        r = {'userid': 1, 'date': date, 'Q1': 2 if date < 202003 else None}
        r.update({k: None for k in [*ENTRY_CODES, *QUIZ]})
        if date == 202002:
            r.update(Q36=5, QRA1=2, Q46=3, QNUM8=3, QNUM1=150)
        rows.append(r)
    got = attach_history(pd.DataFrame(rows))
    assert np.isnan(got.iloc[0].Q36)
    assert got.iloc[2].Q36 == 5
    assert got.iloc[2].correct_QNUM1 == 1
    assert np.isnan(got.iloc[2].financial_change)
    assert np.isnan(got.iloc[2].correct_QNUM6)


def test_first_difference_does_not_turn_a_skipped_month_into_previous_month():
    f = pd.DataFrame({'userid': [1, 1, 1], 'date': [202012, 202101, 202103],
        'weight': [1., 1., 1.], 'outcome': [2., 5., 8.], 'financial_change': [3, 2, 1]})
    rows, dy, x, names = adjacent_differences(f, 'outcome', {'financial_change': [3, 1, 2, 4, 5]})
    assert rows.date.tolist() == [202101]
    assert dy.tolist() == [3.]
    assert names == ['financial_change=2']
    assert x.tolist() == [[1.]]
    assert wquantile([0., 4., 10.], [1., 2., 1.], .5) == 4.
