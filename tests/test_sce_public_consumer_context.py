from copy import deepcopy
import json
from pathlib import Path
import pytest

from studies.sce_inflation_expectations.experiments.public_consumer_context import render_block

CATALOG = Path(__file__).resolve().parents[1]/'docs/workstreams/20261018_targeted_mechanisms/consumer_context_evidence.json'


def test_same_day_dated_release_requires_end_of_day_not_an_invented_clock_time():
    evidence = json.loads(CATALOG.read_text())
    assert 'gasoline' in render_block(evidence, 202206, '2022-06-10T23:59:59-04:00')
    for row in evidence['records']:
        if row['target_month'] == 202206: row['as_of'] = '2022-06-10T08:00:00-04:00'
    with pytest.raises(ValueError, match='intraday'):
        render_block(evidence, 202206, '2022-06-10T08:00:00-04:00')


def test_late_source_is_rejected_and_peer_forecast_numbers_stay_out_of_prompts():
    evidence = json.loads(CATALOG.read_text())
    for month, date in ((202009,'2020-09-11'), (202206,'2022-06-10'), (202503,'2025-03-12')):
        text = render_block(evidence, month, date+'T23:59:59-04:00')
        assert all(number not in text for number in ('3.1%', '5.4%', '4.3%'))
    changed = deepcopy(evidence)
    changed['records'][0]['published_date'] = '2020-10-02'
    with pytest.raises(ValueError, match='late'):
        render_block(changed, 202009, '2020-09-11T23:59:59-04:00')
