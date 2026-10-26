import json
import pytest
from studies.sce_inflation_expectations.news_evidence_suffix_adapter import validate


def sample(quote):
    article=dict(article_id='abc',headline='German Companies Grow Wary of Investing in the U.S.',
        abstract='German companies invest more than three times as much in the United States as American companies do in Germany, but they are starting to rethink that strategy.',snippet='')
    label=dict(article_id='abc',decision='keep',topics=['trade'],scope='international',claim_type='reported_fact',
               reason_zh='企业投资和贸易环境',evidence_snippet=quote)
    return article,label


def test_prefix_recovery_keeps_all_classifications(monkeypatch):
    # Exercise the suffix rule independently of the existing enum vocabulary.
    import studies.sce_inflation_expectations.news_evidence_suffix_adapter as module
    article,label=sample('German companies are starting to rethink that strategy')
    def guard(content, inputs):
        r=json.loads(content)['labels'][0]
        if r['evidence_snippet'] not in inputs[0]['abstract']:raise ValueError('not literal')
        return [r],[]
    monkeypatch.setattr(module,'validate_with_quote_restoration',guard)
    labels,repairs=module.validate(json.dumps({'labels':[label]}),[article])
    assert labels[0]['evidence_snippet']=='are starting to rethink that strategy'
    assert {k:v for k,v in labels[0].items() if k!='evidence_snippet'}=={k:v for k,v in label.items() if k!='evidence_snippet'}
    assert len(repairs)==1


def test_invalid_classification_is_not_repaired_by_removing_quote():
    article,label=sample('The economy is collapsing all over the world')
    with pytest.raises(ValueError):validate(json.dumps({'labels':[label]}),[article])


def test_unverifiable_quote_is_explicitly_quarantined_without_new_classification():
    from studies.sce_inflation_expectations.news_label_trial import SCOPES,CLAIMS
    article,label=sample('There is no corresponding phrase in the article')
    label.update(topics=[],scope=sorted(SCOPES)[0],claim_type=sorted(CLAIMS)[0])
    labels,repairs=validate(json.dumps({'labels':[label]}),[article])
    assert labels[0]['evidence_snippet']==''
    assert repairs[0]['evidence_verified'] is False
    assert all(labels[0][k]==label[k] for k in label if k!='evidence_snippet')


def test_only_identical_duplicate_classification_is_collapsed():
    from studies.sce_inflation_expectations.news_label_trial import SCOPES,CLAIMS
    article,label=sample('are starting to rethink that strategy')
    label.update(topics=[],scope=sorted(SCOPES)[0],claim_type=sorted(CLAIMS)[0])
    labels,repairs=validate(json.dumps({'labels':[label,label]}),[article])
    assert len(labels)==1 and repairs[0]['kind']=='offline_remove_identical_duplicate_label_object'
    other={**label,'reason_zh':'不同判断'}
    with pytest.raises(ValueError,match='Conflicting'):validate(json.dumps({'labels':[label,other]}),[article])
