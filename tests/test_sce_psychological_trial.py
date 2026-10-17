"""New psychology-specific contracts; do not repeat the full old trial suite."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.psychological_state import render_psychology, profiles_from_links, permute_joint
from studies.sce_inflation_expectations.psychological_profiles import build_sidecars
from studies.sce_inflation_expectations.evaluation.frozen_trial import attach_reused_baseline


def test_neutral_state_no_inflation_direction_or_ids():
    text = render_psychology({'HAPPY': 3, 'SATFIN': 2})
    assert 'not too happy' in text and 'more or less satisfied' in text
    assert all(x not in text.lower() for x in ['inflation', 'raise', 'lower', 'gss', 'donor', '%'])
    assert render_psychology({'HAPPY': None, 'SATFIN': None}) == ''
    for record in [{'HAPPY': 1, 'SATFIN': 2, 'Q2': 1}, {'HAPPY': 4, 'SATFIN': 1}, {'HAPPY': 1, 'SATFIN': None}]:
        with pytest.raises(ValueError): render_psychology(record)


def test_profiles_whitelist_and_no_q1_needed():
    link = {'month': 202003, 'userid': 9, 'Q8': 123, 'profile': {'age_group': 'Under 40', 'education_group': 'college',
        'household_income_band': 'under_50k', 'region': 'West', 'forbidden': 99}}
    p = profiles_from_links([link])
    assert set(p.columns) == {'date', 'userid', '_AGE_CAT', '_EDU_CAT', '_HH_INC_CAT', '_REGION_CAT'}
    donor = pd.DataFrame([{'id': 100, '_AGE_CAT': 'Under 40', '_EDU_CAT': 'College', '_HH_INC_CAT': 'Under 50k',
        '_REGION_CAT': 'West', 'donor_weight': 1, 'happy': 3, 'satfin': 1}])
    r = build_sidecars(p, donor, min_ess=1, source_hash='test', include_household_state=False)[0]
    assert 'observed_household_state' not in r
    assert r['psychological_attributes'] == {'HAPPY': 3, 'SATFIN': 1}  # Retain the actual joint row, not independent marginals.
    del link['profile']['education_group']
    missing = build_sidecars(profiles_from_links([link]), donor, min_ess=1, source_hash='test', include_household_state=False)[0]
    assert missing['support_status'] == 'unsupported' and missing['psychological_attributes']['HAPPY'] is None


def test_permutation_preserves_joint_support_and_is_reproducible():
    r = {str(i): {'psychological_attributes': {'HAPPY': i%3+1, 'SATFIN': (i+1)%3+1}} for i in range(20)}
    r['missing'] = {'psychological_attributes': {'HAPPY': None, 'SATFIN': None}}
    original = deepcopy(r); changed = permute_joint(r, 202003, 42)
    assert r == original and changed == permute_joint(r, 202003, 42)
    assert changed['missing'] == r['missing']
    pairs = lambda d: sorted((v['psychological_attributes']['HAPPY'], v['psychological_attributes']['SATFIN']) for k,v in d.items() if k != 'missing')
    assert pairs(changed) == pairs(r)
    assert sum(changed[k]['psychological_attributes'] != r[k]['psychological_attributes'] for k in r) > 0


def test_reused_baseline_rejects_changed_weight(tmp_path, monkeypatch):
    import studies.sce_inflation_expectations.evaluation.frozen_trial as module
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    for prefix in ['parent/202003', 'new/202003', 'eval']: (tmp_path/prefix).mkdir(parents=True)
    prompt = {'rows': {'a': {'messages': [{'role': 'user', 'content': 'same'}]}}}
    for prefix in ['parent', 'new']: (tmp_path/prefix/'202003/prompts_baseline.json').write_text(json.dumps(prompt))
    old = {'month': 202003, 'agent_id': 'a', 'repeat': 1, 'userid': 9, 'profile': {}, 'survey_weight': 1,
        'real': {'q9_mean': 3}, 'arms': {'baseline': {'mean': 2}}}
    (tmp_path/'eval/cases_private.json').write_text(json.dumps([old]))
    current = deepcopy(old); current['arms'] = {}
    protocol = {'months': [202003], 'reuse_baseline_trial': 'parent', 'reuse_baseline_evaluation': 'eval'}
    attach_reused_baseline([current], tmp_path/'new', protocol)
    assert current['arms']['baseline']['mean'] == 2
    current['survey_weight'] = 2
    with pytest.raises(ValueError, match='mismatch'): attach_reused_baseline([current], tmp_path/'new', protocol)
