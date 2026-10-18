from studies.sce_inflation_expectations.experiments.information_exposure import change_view
from studies.sce_inflation_expectations.news_exposure import NEWS_KEYS
from studies.sce_inflation_expectations.news_exposure_demo import render_news_input


def article(aid, common=False):
    row = {key: None for key in NEWS_KEYS}
    row.update(article_id=aid, headline='Public report '+aid, abstract='Brief '+aid,
        snippet='Brief '+aid, pub_date='2021-04-10T12:00:00Z',
        web_url='https://example.com/'+aid, text_sha256='a'*64,
        text_vintage_status='current_archive', print_section='A' if common else 'B',
        print_page='1' if common else '2', placement='a1' if common else 'other_recorded_page',
        routing_tags=[], semantic_label={'decision': 'keep'})
    return row


def test_remove_tables_and_release_metadata_preserving_prior_and_questionnaire():
    common = [article('a'+str(i), True) for i in range(3)]
    old = [article('b'+str(i)) for i in range(5)]
    timing = ('Publication timing for the same information above:\n'
        'These labels describe public availability. The rolling trends above span both earlier and later releases.\n'
        '- CPI figures, reference 2021-03, released 2021-04-13: later.\n'
        '- General news, in the order listed above: later; later; later.\n'
        '- Other news, in the order listed above: later; later; later; later; later.\n'
        '- Policy brief, released 2021-04-01: earlier.\n\n')
    tail = 'Your earlier survey response (2021-03):\nPrior untouched\nQuestionnaire untouched'
    text = ('Persona\nRecent official statistics:\nCPI 2.6\n\n'
        'Recent trends (past releases):\n1,2,3\n\n'
        'Synthetic household spending context (not your observed receipts):\nBasket unchanged\n\n'
        +render_news_input(common, old)+'\n\nPublic policy news brief (2021-04-01):\nPolicy unchanged\n\n'
        +timing+tail)
    messages = [{'role': 'user', 'content': text}]
    # The control must be exactly unchanged, including whitespace.
    assert change_view(messages, common, old, old, timing, '2021-04-01', '2021-04-30T23:59:59-04:00') == messages
    new = change_view(messages, common, old, [], timing, '2021-04-01', '2021-04-30T23:59:59-04:00', False)[0]['content']
    assert 'CPI 2.6' not in new and '- CPI figures,' not in new and 'Recent trends' not in new
    assert 'Basket unchanged' in new and 'Policy unchanged' in new
    assert new.endswith(tail)
    assert 'Brief b0' not in new and new.count('Brief a0') == 1
