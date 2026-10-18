"""Wave-replacement risks: attached labels, age/income boundaries and provenance."""
from copy import deepcopy
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.psychological_waves import normalize_wave
from studies.sce_inflation_expectations.experiments.psychological_wave_state import sample_wave


def fixture():
    df = pd.DataFrame({'year': [2022]*4, 'id': [1, 2, 3, 4], 'age': [39, 40, 59, 60],
        'degree': [1, 2, 3, 4], 'educ': [12, 14, 16, 18], 'income16': [18, 19, 22, 23],
        'region': [1, 2, 3, 4], 'happy': [1, 2, 3, 1], 'satfin': [3, 1, 2, 1], 'wtssps': [1.]*4})
    labels = {'happy': {1: 'very happy', 2: 'pretty happy', 3: 'not too happy'},
        'satfin': {1: 'pretty well satisfied', 2: 'more or less satisfied', 3: 'not satisfied at all'},
        'region': {1: 'northeast', 2: 'midwest', 3: 'south', 4: 'west'},
        'income16': {18: '$40,000 to $49,999', 19: '$50,000 to $59,999', 21: '$75,000 to $89,999',
                     22: '$90,000 to $109,999', 23: '$110,000 to $129,999', 26: '$170,000 or over'}}
    return df, labels


def test_age_region_income_boundaries_and_pair_preservation():
    df, labels = fixture(); g = normalize_wave(df, labels, 2022)
    assert list(g._AGE_CAT) == ['Under 40', '40 to 60', '40 to 60', 'Over 60']
    assert list(g._REGION_CAT) == ['Northeast', 'Midwest', 'South', 'West']
    assert pd.isna(g.iloc[2]._HH_INC_CAT)  # Crossing 100k is not assigned its midpoint.
    assert list(zip(g.happy, g.satfin)) == list(zip(df.happy, df.satfin))


def test_main_weight_and_joint_missing_not_filled():
    df, labels = fixture(); df.loc[0, 'wtssps'] = np.nan; df.loc[1, 'satfin'] = np.nan
    df.loc[2, 'wtssps'] = 0
    g = normalize_wave(df, labels, 2022)
    assert list(g.id) == [4] and g.iloc[0].donor_weight == 1


def test_wrong_attached_geography_or_income_codebook_rejected():
    df, labels = fixture(); bad = deepcopy(labels); bad['region'][1] = 'new england'
    with pytest.raises(ValueError, match='geography'): normalize_wave(df, bad, 2022)
    bad = deepcopy(labels); bad['income16'][22] = '$90,000 to $99,999'
    with pytest.raises(ValueError, match='boundaries'): normalize_wave(df, bad, 2022)
    with pytest.raises(ValueError, match='unique'): normalize_wave(df, labels, 2024)


def test_source_wave_not_2018_and_joint_assignment_stable():
    df, labels = fixture(); g = normalize_wave(df, labels, 2022)
    p = pd.DataFrame([{'date': 202206, 'userid': 99, **{k: g.iloc[0][k] for k in
        ['_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT', '_REGION_CAT']}}])
    a = sample_wave(p, g, 2022, 'source2022', seed=42, draw=0, min_ess=1)[0]
    b = sample_wave(p, g.iloc[::-1], 2022, 'source2022', seed=42, draw=0, min_ess=1)[0]
    assert a == b and a['source_wave'] == 2022
    assert a['source_hash'] == 'source2022' and 'observed_household_state' not in a
    assert a['psychological_attributes'] == {'HAPPY': 1, 'SATFIN': 3}
