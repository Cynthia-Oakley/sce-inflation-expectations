from copy import deepcopy
import pytest

from studies.sce_inflation_expectations.experiments.media_timing_package import (
    plan_reuse, validate_labels)
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash


def row(text):
    messages=[{'role':'user','content':text}]
    return dict(messages=messages,prompt_sha256=message_hash(messages))


def protocol():
    return dict(generation_repeats=[1,2],model='deepseek/deepseek-v3.2',
        expected_provider='SiliconFlow',price_input_per_mtok=.259,
        price_output_per_mtok=.8,max_tokens=1024)


def reply(prompt,repeat=1,usable=True):
    return dict(month=202106,agent_id='a',repeat=repeat,
        prompt_sha256=prompt['prompt_sha256'],key=f'202106|Q3|{repeat}|a',
        actual_model_results=True,technical_usable=usable,error=None,
        returned_model='deepseek/deepseek-v3.2',returned_provider='SiliconFlow')


def test_reuse_same_person_repeat_and_hash_only():
    original=row('original');new=row('new')
    bundles=[(202106,'C0',{'a':original}),(202106,'T0',{'a':new}),
             (202106,'T1',{'a':new})]
    pos,slots=plan_reuse(bundles,[reply(original)],protocol())
    assert len(pos)==6 and len(slots)==3
    assert pos[0]['status']=='reuse_exact_success'
    assert pos[1]['status']=='new_request'
    assert {p['new_request_key'] for p in pos[-2:]}=={s['key'] for s in slots if s['arm']=='T0'}
    assert len({s['key'] for s in slots})==len(slots)


def test_exact_old_failure_is_held_not_resent():
    original=row('same')
    pos,slots=plan_reuse([(202106,'C0',{'a':original})],
        [reply(original,usable=False),reply(original,repeat=2,usable=False)],protocol())
    assert not slots
    assert all(r['status']=='hold_old_attempted_failure' for r in pos)


def test_wrong_supplier_and_fake_answers_rejected():
    original=row('same');r=reply(original);r['returned_provider']='Other'
    with pytest.raises(ValueError,match='receiver'):
        plan_reuse([(202106,'C0',{'a':original})],[r],protocol())
    r=reply(original);r['actual_model_results']=False
    with pytest.raises(ValueError,match='actual'):
        plan_reuse([], [r],protocol())


def test_no_invented_original_reference_or_bad_prompt_hash():
    original=row('same')
    with pytest.raises(ValueError,match='Original reference'):
        plan_reuse([(202106,'O0',{'a':original})],[],protocol())
    original['prompt_sha256']='bad'
    with pytest.raises(ValueError,match='hash'):
        plan_reuse([(202106,'C0',{'a':original})],[],protocol())


def test_original_reference_keeps_its_actual_q3_answer():
    original=row('same');other=reply(original);other['key']='202106|Q0|1|a'
    q3=reply(original,usable=False)
    q3b=reply(original,repeat=2)
    positions,_=plan_reuse([(202106,'O0',{'a':original})],[other,q3,q3b],protocol())
    assert positions[0]['source_key']=='202106|Q3|1|a'
    assert positions[0]['status']=='hold_old_attempted_failure'


def test_labels_complete_and_preserve_originals():
    pool=[dict(article_id='old',semantic_label=dict(tone='neutral',persistence='unclear')),
          dict(article_id='new',semantic_label=dict(decision='keep',tone=None,persistence=None))]
    saved=deepcopy(pool)
    labels={'new':dict(tone='alarming',persistence='persistent')}
    merged=validate_labels(pool,labels)
    assert merged[1]['semantic_label']['tone']=='alarming'
    assert pool==saved
    with pytest.raises(ValueError,match='lacks'):
        validate_labels(pool,{})
    with pytest.raises(ValueError,match='conflicts'):
        validate_labels(pool,dict(labels,old=dict(tone='reassuring')))
