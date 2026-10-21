"""Never resend successful or unknown slots; only the explicitly listed 429s."""
from copy import deepcopy
import hashlib
import json
import pytest
from studies.sce_inflation_expectations.experiments.v32_rate_recovery import partition


def fixture():
    slots=[dict(slot_key=str(i),prompt_sha256=str(i),messages=[dict(role='user',content=str(i))]) for i in range(16)]
    text=json.dumps(dict(point_pct=3,q9={f'bin{i}':100 if i==8 else 0 for i in range(1,11)}))
    rows=[dict(slot_key=s['slot_key'],prompt_sha256=s['prompt_sha256'],prompt_text=json.dumps(s['messages'],ensure_ascii=False),
               raw_response_text=text,raw_response_sha256=hashlib.sha256(text.encode()).hexdigest(),
               error='429' if i>=4 else None,error_http_status=429 if i>=4 else None,
               returned_model='deepseek/deepseek-v3.2',returned_provider='AtlasCloud',finish_reason='stop') for i,s in enumerate(slots)]
    return slots,rows


def test_only_twelve_failed_slots_selected():
    slots,rows=fixture();good,failed=partition(slots,rows)
    assert set(good)=={'0','1','2','3'}
    assert {r['slot_key'] for r in failed}=={str(i) for i in range(4,16)}


@pytest.mark.parametrize('change',['other_error','duplicate','prompt_drift'])
def test_ambiguous_or_changed_attempt_cannot_be_manually_retried(change):
    slots,rows=fixture()
    if change=='other_error':rows[5]['error_http_status']=500
    if change=='duplicate':rows[-1]=deepcopy(rows[0])
    if change=='prompt_drift':rows[-1]['prompt_text']='changed'
    with pytest.raises(ValueError):partition(slots,rows)
