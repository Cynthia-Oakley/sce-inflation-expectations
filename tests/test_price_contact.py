"""Acceptance gates for the isolated public-price experiment."""
import json
from copy import deepcopy
from pathlib import Path
import pytest
from socioverse.schemas import PopulationBundle
from studies.sce_inflation_expectations.price_contact import validate_bundle, STATE_PADD
from studies.sce_inflation_expectations.price_contact_trial import extract_prices

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT/'outputs/sce_price_contact_trial_20261010_v1'


def fixture():
    if not FOLDER.exists():pytest.skip('Archived experiment inputs not distributed with source')
    pop=PopulationBundle.model_validate(json.loads((FOLDER/'202105/population.json').read_text()))
    b=json.loads((FOLDER/'202105/simulation_matched.json').read_text())['decision_args']['price_contact_bundle']
    return pop,b


def test_dated_official_transcription():
    if not (ROOT/'data/raw/high_frequency_prices/20261010/gas_may.pdf').exists():pytest.skip('Raw public PDFs local only')
    may=extract_prices(ROOT,'202105');june=extract_prices(ROOT,'202106')
    assert may['gasoline']['series']['national'][-1] == 2.961
    assert june['gasoline']['series']['national'][-1] == 3.035
    assert may['gasoline']['dates'][-1] == '2021-05-10'
    assert june['gasoline']['dates'][-1] == '2021-06-07'
    assert may['dairy']['items'][0]['prices'] == [2.73,2.19,1.4]
    assert june['dairy']['items'][1]['prices'] == [2.32,2.4,2.42]


def test_future_publication_and_wrong_profile_rejected():
    pop,b=fixture();validate_bundle(b,pop.personas,'2021-05')
    bad=deepcopy(b);bad['prices']['gasoline']['available_by']='2021-05-13T23:59:59-04:00'
    with pytest.raises(ValueError,match='future'):validate_bundle(bad,pop.personas,'2021-05')
    bad=deepcopy(b);bad['rows'][pop.personas[0].agent_id]['profile_sha256']='wrong'
    with pytest.raises(ValueError,match='profile'):validate_bundle(bad,pop.personas,'2021-05')
    bad=deepcopy(b);bad['rows'][pop.personas[0].agent_id]['true_inflation']=5
    with pytest.raises(ValueError,match='whitelist'):validate_bundle(bad,pop.personas,'2021-05')


def test_shuffle_preserves_price_multiset_and_basket():
    pop,b=fixture();s=json.loads((FOLDER/'202105/simulation_shuffled.json').read_text())['decision_args']['price_contact_bundle']
    validate_bundle(s,pop.personas,'2021-05')
    assert sorted(r['assigned_padd'] for r in b['rows'].values()) == sorted(r['assigned_padd'] for r in s['rows'].values())
    assert b['prices'] == s['prices']
    assert any(b['rows'][k]['assigned_padd']!=s['rows'][k]['assigned_padd'] for k in b['rows'])
    for k in b['rows']:assert b['rows'][k]['shares'] == s['rows'][k]['shares']
    assert STATE_PADD['TX']=='3' and STATE_PADD['NY']=='1' and STATE_PADD['TN']=='2'


def test_previews_contain_no_source_id_or_outcome():
    if not FOLDER.exists():pytest.skip('Inputs local only')
    links=json.loads((FOLDER/'private_evaluation_link.json').read_text())
    for month in ['202105','202106']:
        for arm in ['baseline','national','matched','shuffled']:
            previews=json.loads((FOLDER/month/f'preview_{arm}.json').read_text())
            assert len(previews)==20
            for row in previews:
                content=json.dumps(row['messages'])
                assert 'Question 1 (point estimate):' in content
                assert not any(str(l['userid']) in content for l in links)
                assert 'Q9_mean' not in content and 'donor_id' not in content
                assert 'shopping frequency' in content


def test_distribution_metrics_not_confused_with_individual_error():
    from studies.sce_inflation_expectations.price_contact_analysis import metrics
    rows=[{'real':v,'baseline':4.,'national':4.,'matched':4.,'shuffled':4.,'padd':'1'} for v in [1.,3.,5.,7.]]
    rows.append({'real':None,'baseline':50.,'national':50.,'matched':50.,'shuffled':50.,'padd':'1'})
    m=metrics(rows)
    assert m['common_valid_n']==4 and m['excluded_n']==1
    assert m['arms']['baseline']['median_absolute_error_pp']==0
    assert m['arms']['baseline']['distribution_W1_pp']==2
    assert m['real']['iqr']==3 and m['arms']['baseline']['distribution']['iqr']==0
