from copy import deepcopy
import pytest
from studies.sce_inflation_expectations.experiments.entry_pilot_continuation import validate_attempts

def example():
    rows=[{'reuse_key':str(i),'technical_usable':i!=0,'error':'APIConnectionError' if i==0 else None} for i in range(16)]
    return rows,[{'reuse_key':r['reuse_key']} for r in rows],{str(i) for i in range(288)}

def test_only_unattempted_keys_may_continue():
    rows,intents,keys=example();before=deepcopy(rows)
    pending=validate_attempts(rows,intents,keys)
    assert len(pending)==272 and not set(pending)&{r['reuse_key'] for r in rows}
    assert rows==before

def test_uncertain_dispatch_is_not_resubmitted():
    rows,intents,keys=example();intents.append({'reuse_key':'17'})
    with pytest.raises(ValueError):validate_attempts(rows,intents,keys)

def test_bad_model_answer_does_not_qualify_as_network_exception():
    rows,intents,keys=example();rows[0]['error']=None
    with pytest.raises(ValueError):validate_attempts(rows,intents,keys)
