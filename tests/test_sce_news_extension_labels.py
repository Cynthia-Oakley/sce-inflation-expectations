"""Cross-package identity and public-data boundary checks."""
import json

import pytest

from studies.sce_inflation_expectations.news_extension_label_preparation import freeze_requests
from studies.sce_inflation_expectations.news_pool_preparation import partition_requests


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
