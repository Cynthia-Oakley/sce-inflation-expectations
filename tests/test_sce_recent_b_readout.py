import hashlib
import json
import pytest
from studies.sce_inflation_expectations.evaluation import recent_b_readout as m


def test_missing_target_is_checked_before_any_scoring_or_output(tmp_path):
    catalog=tmp_path/'catalog.json'
    catalog.write_text(json.dumps({'headline_releases':[]}))
    with pytest.raises(ValueError,match='2026-09'):
        m.validate_catalog(catalog,['202609'])


def test_catalog_hash_is_checked_and_duplicate_targets_rejected(tmp_path,monkeypatch):
    monkeypatch.setattr(m,'ROOT',tmp_path)
    raw=tmp_path/'release.txt';raw.write_text('fixture')
    row=dict(reference_period='2026-09',source_file='release.txt',source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
    catalog=tmp_path/'catalog.json';catalog.write_text(json.dumps({'headline_releases':[row]}))
    m.validate_catalog(catalog,['202609'])
    raw.write_text('changed')
    with pytest.raises(ValueError,match='hash mismatch'):m.validate_catalog(catalog,['202609'])
    catalog.write_text(json.dumps({'headline_releases':[row,row]}))
    with pytest.raises(ValueError,match='Duplicate'):m.validate_catalog(catalog,['202609'])


def test_group_aggregation_equal_month_not_person_count_and_support_explicit():
    rs=[]
    for median,n,supported in [(2.,100,True),(4.,20,True),(90.,10,False)]:
        rs.append(dict(dimension='numeracy',value='high',supported=supported,n=n,
                       sim={'median_pp':median,'iqr_pp':1.},prior={'median_pp':5.,'iqr_pp':4.}))
    r=m.summarize_group_months(rs)[0]
    assert r['sim_median_pp']==3. and r['eligible_months']==2 and r['n_person_months']==120


def test_population_disagreement_and_person_uncertainty_are_distinct():
    rs=[dict(weight=1.,center=c,prior_center=2*c,uncertainty=7.) for c in (1.,2.,3.,4.)]
    d=m.describe(rs)
    assert d['sim']['iqr_pp']==2.
    assert d['prior']['iqr_pp']==4.
    assert d['median_person_uncertainty_iqr_pp']==7.


def test_readout_rejects_changed_combined_answers(tmp_path):
    folder=tmp_path/'combined';folder.mkdir()
    f=folder/'positions_private.jsonl';f.write_text('original fixture')
    (folder/'manifest.json').write_text(json.dumps({'files_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest()}}))
    m.validate_combined(tmp_path)
    f.write_text('changed fixture')
    with pytest.raises(ValueError,match='ledger hash mismatch'):m.validate_combined(tmp_path)
