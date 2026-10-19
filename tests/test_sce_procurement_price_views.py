from copy import deepcopy
import numpy as np
import pytest

from studies.sce_inflation_expectations.procurement_price_views import (
    FOOD_CATEGORIES, DETAIL_COUNT, balanced_bundle_shuffle, choose_categories,
    extract_categories, fact_line, render_view, transform_prompt, validate_cutoff)


def synthetic_pages():
    labels = ['Food at home', *FOOD_CATEGORIES.values(), 'Household cleaning products',
              'Household paper products', 'Personal care products']
    first = ['Table 1. Consumer Price Index']
    second = ['Table 2. Consumer Price Index']
    seventh = ['Table 7. Consumer Price Index']
    for i,label in enumerate(labels):
        if i==4:
            second.append('Table 2. Consumer Price Index — Continued')
        first.append(label+' . . . 1.000 100.000 101.000 102.000 -2.1 0.4 0.5 0.6 0.7')
        second.append(label+' 1, 2 . . . 1.000 -2.1 0.4 0.5 0.6 0.7')
        seventh.append(label+' . . . 1.000 -2.1 -0.03 0.10')
    return ['\n'.join(first), '\n'.join(second), 'Table 3. Consumer Price Index', '\n'.join(seventh)]


def facts():
    data=extract_categories(synthetic_pages())
    for row in data.values():
        row.update(reference_period='2022-05', published_at='2022-06-10T08:30:00-04:00')
    return data


def test_column_semantics_and_continuation():
    d=facts()
    assert len(d)==10
    assert d['dairy']['yoy_nsa_percent']==-2.1
    assert d['dairy']['mom_nsa_percent']==.4
    assert d['dairy']['mom_sa_percent']==.7


def test_cross_table_disagreement_fails_closed():
    pages=synthetic_pages(); pages[-1]=pages[-1].replace('1.000 -2.1','1.000 -9.9',1)
    with pytest.raises(ValueError,match='mismatch'):
        extract_categories(pages)


def test_missing_numeric_cell_not_silently_imputed():
    pages=synthetic_pages(); pages[1]=pages[1].replace('1.000 -2.1 0.4','1.000 -2.1 –',1)
    with pytest.raises(ValueError,match='nonnumeric'):
        extract_categories(pages)


def test_category_selection_nested_without_price_or_answer_inputs():
    selections=[choose_categories(r,'fixed-person',19) for r in range(1,6)]
    assert [len(v) for v in selections]==[0,1,3,6,6]
    assert selections[1]==selections[2][:1]
    assert choose_categories(5,'fixed-person',19)==selections[-1]
    with pytest.raises(ValueError): choose_categories(None,'fixed-person',19)


def test_period_labels_and_signed_changes():
    text=fact_line(facts()['dairy'])
    assert 'increased 0.4% from the previous month' in text
    assert 'decreased 2.1% from the same month a year earlier' in text
    assert 'not seasonally adjusted' in text


def test_future_data_blocked_and_housekeeping_not_inferred():
    with pytest.raises(ValueError,match='future'):
        validate_cutoff(facts().values(),'2022-06-09T23:59:59-04:00')
    with pytest.raises(ValueError):
        render_view(2,['cleaning'],facts(),'later')


def test_prior_and_news_preserved_while_full_table_removed():
    text=('Persona block.\nRecent official statistics:\n- arbitrary numerical data\n'
        'Recent trends (past releases):\n- more numbers\n'
        'Synthetic household spending context (not your observed receipts):\nCE unchanged.\n'
        'General news you encountered:\nOriginal news.\nPublic policy news brief (2022):\nOriginal policy.\n'
        'Publication timing for the same information above:\n- CPI figures, reference 2022-05: later.\n'
        '- General news: later.\nYour earlier survey response (2022-05):\nOriginal prior.\nOriginal questionnaire.')
    old=[{'role':'user','content':text}]; unchanged=deepcopy(old)
    new=transform_prompt(old,render_view(2,choose_categories(2,'p',1),facts(),'later'))[0]['content']
    assert old==unchanged
    assert 'Original news.' in new and 'Original policy.' in new
    assert new[new.index('Your earlier survey response ('):]==text[text.index('Your earlier survey response ('):]
    assert 'arbitrary numerical data' not in new and 'Recent trends (' not in new


def test_shuffle_preserves_complete_bundle_multiset():
    fs=facts(); bundles=[]
    for i in range(30):
        role=i%5+1; categories=choose_categories(role,str(i),17)
        bundles.append({'role':role,'categories':categories,'view':render_view(role,categories,fs,'later')})
    ix,audit=balanced_bundle_shuffle(bundles,np.ones(30),7)
    other,_=balanced_bundle_shuffle(bundles,np.ones(30),7)
    assert np.array_equal(ix,other)
    assert sorted(ix.tolist())==list(range(30))
    assert audit['weighted_detail_count_relative_gap']<1e-10
    assert audit['max_category_and_role_share_absolute_gap']<1e-10
