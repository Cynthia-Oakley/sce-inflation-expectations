from copy import deepcopy
import hashlib

import pandas as pd
import pytest

from studies.sce_inflation_expectations.experiments.recent_b_preflight import (
    qualify_micro, select_public_anchor, select_population, timestamp, validate_frame,
)


def test_timezone_comparison_and_naive_timestamp_rejected():
    assert timestamp('2025-11-13T23:59:59-05:00') == timestamp('2025-11-14T04:59:59Z')
    with pytest.raises(ValueError,match='Timezone'):
        timestamp('2025-11-13T23:59:59')


def test_snapshot_requires_actual_archived_bytes_and_publication_before_cutoff(tmp_path):
    p = tmp_path/'micro.xlsx';p.write_bytes(b'archived-byte-evidence')
    evidence = dict(local_file='micro.xlsx',bytes=p.stat().st_size,
                    sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                    snapshot_time_utc='2025-07-02T15:07:33Z')
    assert qualify_micro(evidence,'2025-11-13T23:59:59-05:00',root=tmp_path)==p
    with pytest.raises(ValueError,match='verified before'):
        qualify_micro(evidence,'2025-01-01T00:00:00Z',root=tmp_path)
    p.write_bytes(b'unverified-replacement')
    with pytest.raises(ValueError,match='verified before'):
        qualify_micro(evidence,'2025-11-13T23:59:59-05:00',root=tmp_path)


def releases():
    return [dict(reference_period='2025-09',published_date='2025-10-07',value_pp=3.4),
            dict(reference_period='2025-10',published_date='2025-11-07',value_pp=3.2),
            dict(reference_period='2025-11',published_date='2025-12-08',value_pp=3.2)]


def test_new_november_cutoff_uses_past_october_anchor_not_target():
    rows = releases()
    assert select_public_anchor(rows,'202511','2025-10-24T23:59:59-04:00')['reference_period']=='2025-09'
    assert select_public_anchor(rows,'202511','2025-11-13T23:59:59-05:00')['reference_period']=='2025-10'


def test_same_day_date_only_release_excluded_and_target_truth_rejected():
    assert select_public_anchor(releases(),'202511','2025-11-07T23:59:59-05:00')['reference_period']=='2025-09'
    bad = releases()+[dict(reference_period='2025-11',published_date='2025-11-01',value_pp=99)]
    with pytest.raises(ValueError,match='Current/future'):
        select_public_anchor(bad,'202511','2025-11-13T23:59:59-05:00')


def test_missing_national_history_does_not_use_future_release():
    with pytest.raises(ValueError,match='No proven public'):
        select_public_anchor(releases(),'202501','2024-12-31T23:59:59-05:00')


def test_snapshot_coverage_and_duplicate_people_guard():
    e = {'coverage':dict(min_survey_month='202407',max_survey_month='202408',n_rows=2)}
    f = pd.DataFrame({'date':[202407,202408],'userid':[1,1]})
    assert len(validate_frame(f,e))==2
    with pytest.raises(ValueError,match='coverage'):
        validate_frame(f.assign(date=[202407,202510]),e)
    with pytest.raises(ValueError,match='coverage'):
        validate_frame(pd.DataFrame({'date':[202408,202408],'userid':[1,1]}),e)


def people():
    a = dict(education_group='college',numeracy='high',age_group='Under 40',household_income_band='under_50k')
    p = [dict(agent_id=f'proxy_{i}',attributes=dict(a),synthetic_proxy=True) for i in range(10)]
    p += [dict(agent_id='unknown',attributes={},synthetic_proxy=True),
          dict(agent_id='no_weight',attributes=dict(a),synthetic_proxy=True)]
    weights={x['agent_id']:i+1. for i,x in enumerate(p)};weights['no_weight']=None
    return p, weights


def test_old_frame_calibration_and_unknown_weight_policy():
    p,w=people();selected,plan,excluded=select_population(p,w,'202511',budget=6,minimum=1)
    assert excluded==['no_weight'] and len(selected)==6
    assert any(r['persona']['agent_id']=='unknown' for r in selected)
    for c,v in plan['cells'].items():
        assert sum(r['analysis_weight'] for r in selected if r['stratum']==c)==pytest.approx(v['population_mass'])


def test_different_outcomes_cannot_change_proxy_population_selection_or_be_sent():
    p,w=people();expected,_,_=select_population(p,w,'202511',budget=6,minimum=1)
    changed=deepcopy(p)
    for r in changed:r['attributes'].update(current_q8=999,current_q9_mean=-999)
    actual,_,_=select_population(changed,w,'202511',budget=6,minimum=1)
    assert actual==expected
    assert all('current_q8' not in r['persona']['attributes'] for r in actual)


def test_duplicate_proxy_id_cannot_silently_increase_population():
    p,w=people()
    with pytest.raises(ValueError,match='Duplicate'):
        select_population(p+[p[0]],w,'202511',budget=6,minimum=1)
