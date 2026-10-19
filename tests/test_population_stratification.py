from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations'))
from population_stratification import cell_key, allocate_core


def test_cells_use_only_declared_profile_fields_and_unknown_stays_unknown():
    p={'education_group':'college','employment_status':'employed'}
    assert cell_key(p)==cell_key({**p,'current_q9':1000,'age_group':'Over 60'})=='college|attached'
    assert cell_key({'_EDU_CAT':'High School','employment':'retired'})=='high_school|not_attached'
    assert cell_key({'education_group':'college','employment_status':'unknown'})=='unknown'
    assert cell_key({'education_group':None,'employment_status':'retired'})=='unknown'


def test_minimum_proportional_allocation_and_frame_capacity():
    counts={'a':100,'b':30,'unknown':3};masses={'a':100.,'b':50.,'unknown':3.}
    r=allocate_core(counts,masses,60,12)
    assert sum(r.values())==60 and r['a']>=12 and r['b']>=12 and r['unknown']==3
    assert all(r[k]<=counts[k] for k in r)
    assert allocate_core(counts,masses,133,12)==counts


def test_impossible_minimum_does_not_silently_drop_cells():
    with pytest.raises(ValueError,match='minimums'):
        allocate_core({'a':30,'b':30},{'a':1.,'b':1.},10,12)
