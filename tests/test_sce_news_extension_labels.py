"""Cross-package identity and public-data boundary checks."""
import json

import pytest

from studies.sce_inflation_expectations.news_extension_label_preparation import freeze_requests
from studies.sce_inflation_expectations.news_pool_preparation import partition_requests
from studies.sce_inflation_expectations.news_label_trial import validate_with_evidence_shortening
from studies.sce_inflation_expectations.news_label_quote_adapter import validate_with_quote_restoration


def draft(identity='public-a'):
    article = dict(article_id=identity, headline='Public headline', abstract='Prices changed',
                   snippet='Prices changed', source='NYT', section_name='Business', news_desk='Business')
    messages = [{'role': 'system', 'content': 'Fixed classification instructions'},
                {'role': 'user', 'content': json.dumps({'articles': [article]}, ensure_ascii=False)}]
    row = {'batch_id': 1, 'article_ids': [identity], 'input_byte_reservation':
           len(json.dumps(messages, ensure_ascii=False).encode()) + 512,
           'payload': {'model': 'deepseek-flash', 'temperature': 0, 'max_tokens': 2400,
                       'response_format': {'type': 'json_object'}, 'thinking': {'type': 'disabled'},
                       'messages': messages}}
    return row, article


def test_duplicate_article_across_batches_is_rejected_before_dispatch():
    row, article = draft()
    with pytest.raises(ValueError, match='duplicate article'):
        freeze_requests([row, dict(row, batch_id=2)], [article])


def test_population_or_answer_cannot_enter_public_label_request():
    row, article = draft()
    article['actual_q9'] = 7.5
    with pytest.raises(ValueError, match='public whitelist'):
        freeze_requests([row], [article])


def test_package_cap_and_article_identity_are_preserved():
    rows, articles = [], []
    for index in range(90):
        row, article = draft(f'public-{index}')
        rows.append(dict(row, batch_id=index + 1))
        articles.append(article)
    requests, _ = freeze_requests(rows, articles)
    parts = partition_requests(requests, .25)
    assert len(parts) > 1
    assert all(sum(row['request_usd_reservation'] for row in part) <= .25 for part in parts)
    assert [row['article_ids'][0] for part in parts for row in part] == [a['article_id'] for a in articles]


def test_lowercased_headline_quote_restores_literal_case_without_changing_decision():
    source = {'article_id': 'a', 'headline': 'WeWork’s Co-Founder Is Trying to Buy the Company',
              'abstract': '', 'snippet': ''}
    label = {'article_id': 'a', 'decision': 'background', 'topics': ['other_economic'],
             'scope': 'us_unspecified', 'claim_type': 'attributed_claim', 'reason_zh': '原分类',
             'evidence_snippet': 'trying to buy the company'}
    labels, repairs = validate_with_evidence_shortening(json.dumps({'labels': [label]}), [source])
    assert labels[0]['evidence_snippet'] == 'Trying to Buy the Company'
    assert labels[0]['decision'] == 'background'
    assert repairs[0]['kind'] == 'offline_restore_source_quote_case'
    label['evidence_snippet'] = 'the price will rise substantially'
    with pytest.raises(ValueError):
        validate_with_evidence_shortening(json.dumps({'labels': [label]}), [source])


def test_nbsp_source_quote_is_restored_before_long_quote_shortening():
    quote = 'scaling back the minimum number of spots for shopping centers and apartment complexes'
    original = quote.replace('for shopping', 'for\u00a0shopping')
    source = {'article_id': 'a', 'headline': '', 'abstract': original + '.', 'snippet': ''}
    label = {'article_id': 'a', 'decision': 'keep', 'topics': ['policy'], 'scope': 'us_unspecified',
             'claim_type': 'fact', 'reason_zh': '原分类', 'evidence_snippet': quote}
    labels, repairs = validate_with_evidence_shortening(json.dumps({'labels': [label]}), [source])
    assert labels[0]['evidence_snippet'] in source['abstract']
    assert len(labels[0]['evidence_snippet'].split()) == 12
    assert labels[0]['decision'] == 'keep'
    assert [row['kind'] for row in repairs] == ['offline_restore_source_quote_whitespace', 'offline_verbatim_quote_shortening']


def test_inline_quote_recovery_preserves_all_words_and_rejects_omitted_word():
    source = {'article_id': 'a', 'headline': '',
              'abstract': 'The CEO was “cooperating in an investigation” by Chinese authorities.', 'snippet': ''}
    label = {'article_id': 'a', 'decision': 'exclude', 'topics': [], 'scope': 'non_us',
             'claim_type': 'fact', 'reason_zh': '原分类',
             'evidence_snippet': 'cooperating in an investigation by Chinese authorities'}
    labels, repairs = validate_with_quote_restoration(json.dumps({'labels': [label]}), [source])
    assert labels[0]['evidence_snippet'] in source['abstract']
    assert labels[0]['decision'] == 'exclude'
    assert repairs[0]['kind'] == 'offline_restore_source_inline_double_quotes'
    label['evidence_snippet'] = 'cooperating in investigation by Chinese authorities'
    with pytest.raises(ValueError):
        validate_with_quote_restoration(json.dumps({'labels': [label]}), [source])
