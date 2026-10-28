"""Hand-calculated format/lineage/error boundaries for the portable micro path."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.submission_tools.micro_replay import audit_response, verify_answers, replay
from studies.sce_inflation_expectations.submission_tools.micro_export import clean_text


def response(**changes):
    # 80 raw points become 25/75 percent, independent expected numbers.
    text=json.dumps(dict(point_pct=-2,q9={f"bin{i}":20 if i==5 else 60 if i==6 else 0 for i in range(1,11)}))
    digest=hashlib.sha256(text.encode()).hexdigest()
    r=dict(response_id="r1",run="A",period="202101",household="a1",stage="main",prompt_sha256="same",
           response_text=text,original_response_sha256=digest,delivered_response_sha256=digest,
           response_text_redacted=False,error=None,actual_model_results=True)
    r.update(changes)
    return r


def answer(**changes):
    a=dict(run="A",period="202101",household="a1",analysis_weight=2,q8=-2,
           q9_bins=[0,0,0,0,25,75,0,0,0,0],field_source={"q8":"main","q9":"main"},
           selected_responses={"q8":"r1","q9":"r1"})
    a.update(changes)
    return a


def test_raw_probabilities_normalize_without_changing_text():
    r=response();old=r["response_text"]
    point,bins=audit_response(r)
    assert point==-2 and bins==[0,0,0,0,25,75,0,0,0,0]
    assert r["response_text"]==old
    assert verify_answers([answer()],{"r1":r})["proportional_normalizations"]==1


def test_no_silent_reply_change_or_scripted_promotion():
    with pytest.raises(ValueError,match="hash"):
        audit_response(response(response_text="{}"))
    with pytest.raises(ValueError,match="fixture"):
        audit_response(response(actual_model_results=False))


@pytest.mark.parametrize("change",[{"household":"other"},{"period":"202102"},{"run":"B"}])
def test_person_period_and_run_are_not_interchangeable(change):
    with pytest.raises(ValueError):verify_answers([answer()],{"r1":response(**change)})


def test_density_failure_keeps_raw_and_operational_states_distinct():
    a=answer(q9_bins=[0,0,0,0,10,90,0,0,0,0],selected_model_q9_bins=[0,0,0,0,25,75,0,0,0,0],
             density_failure_retained_input=True,fallback={"mean":3,"iqr":1})
    assert verify_answers([a],{"r1":response()})["raw_fields_verified"]==2
    assert a["q9_bins"][4]==10


def test_duplicate_and_negative_weight_rejected():
    with pytest.raises(ValueError,match="Duplicate"):verify_answers([answer(),answer()],{"r1":response()})
    with pytest.raises(ValueError,match="weight"):verify_answers([answer(analysis_weight=-1)],{"r1":response()})


def test_monthly_retention_must_use_preceding_same_household():
    a=answer(run="monthly",root_reused=True,selected_responses={"q8":None,"q9":None})
    b=deepcopy(a);b.update(period="202102",root_reused=False,previous_period="202101")
    assert verify_answers([a,b],{})["retained_fields"]==4
    b["q8"]=5
    with pytest.raises(ValueError,match="retained monthly"):verify_answers([a,b],{})


def test_paths_cannot_escape_the_micro_data_root(tmp_path):
    source=tmp_path/"data";source.mkdir();secret=tmp_path/"outside";secret.write_text("secret")
    (source/"manifest.json").write_text(json.dumps(dict(files_sha256={"../outside":hashlib.sha256(b"secret").hexdigest()})))
    with pytest.raises(ValueError,match="hash mismatch"):replay(source,tmp_path/"out")


def test_sensitive_echoes_are_explicitly_redacted():
    text,changed=clean_text('Contact a@b.edu; file /Users/any/private.csv')
    assert changed and "a@b.edu" not in text and "/Users/" not in text
    assert clean_text('{"point_pct": 3}')[1] is False
