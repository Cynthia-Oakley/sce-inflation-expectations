import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.experiments import media_mechanism_trial as trial


ROOT = Path(__file__).resolve().parents[1]


def test_external_pool_is_complete_and_excludes_sce_reports():
    for month in (202106, 202206):
        rows, receipt = trial.load_external_pool(ROOT, month)
        assert len(rows) == 29
        assert receipt['raw_candidate_count'] == 30
        assert receipt['excluded_sce_report_count'] == 1
        assert len({r['article_id'] for r in rows}) == 29
        assert all(r['semantic_label']['decision'] == 'keep' for r in rows)
        assert all(trial.is_sce_report(r) is False for r in rows)


def test_salience_common_guarantees_latest_cpi_release_day():
    for month, expected in ((202106, 'Prices Jumped 5% in May From Year Earlier, Stoking Debate in Washington'),
                            (202206, 'Inflation Sped Up Again in May, Dashing Hopes for Relief')):
        pool = trial.load_nyt_pool(ROOT, month)
        common = trial.select_salient_common(pool, trial.latest_cpi_release_day(ROOT, month))
        assert len(common) == 3
        assert expected in {r['headline'] for r in common}
        assert all(r['placement'] == 'a1' for r in common)
        assert all(trial.INFLATION_PATTERN.search(r['headline']) for r in common)
        assert all(r['semantic_label'].get('scope') == 'us_national' for r in common)


def test_negative_boost_is_defined_and_bounded():
    rows = [trial.synthetic_news(str(i), 'Inflation surges to a record high' if i == 0 else 'Local economy update')
            for i in range(2)]
    base = trial.selection_probabilities(rows, frozenset(), negative_boost=1.)
    boosted = trial.selection_probabilities(rows, frozenset(), negative_boost=2.)
    assert boosted[0] > base[0]
    assert boosted[1] < base[1]
    assert sum(boosted) == pytest.approx(1.)
    with pytest.raises(ValueError):
        trial.selection_probabilities(rows, frozenset(), negative_boost=.9)


def test_external_quota_is_fixed_before_drawing():
    assert trial.external_count(0) == 0
    assert trial.external_count(5) == 1
    assert trial.external_count(17) == 4


def test_rendered_replacement_preserves_every_non_news_byte():
    old_common = [dict(trial.synthetic_news('old-c', 'Inflation old common'), placement='a1', print_section='A', print_page='1')]
    old_personal = [trial.synthetic_news('old-p', 'Inflation old personal')]
    new_common = [dict(trial.synthetic_news('new-c', 'Inflation new common'), placement='a1', print_section='A', print_page='1')]
    new_personal = [trial.synthetic_news('new-p', 'Inflation surges to a record high')]
    as_of = '2021-06-10T23:59:59-04:00'
    previous_day = '2021-05-15'
    old_status = '- Other news, in the order listed above: ' + '; '.join(
        trial.publication_status(r['pub_date'], previous_day, as_of) for r in old_personal) + '.'
    content = ('PERSONA AND PRICES\n\n' + trial.render_news_input(old_common, old_personal) + '\n\n' +
               trial.POLICY_START + 'policy)\n\n' + trial.TIMING_START + old_status + '\n\nQUESTIONNAIRE')
    result = trial.change_rendered_news([{'role': 'user', 'content': content}], old_common, old_personal,
                                        new_common, new_personal, previous_day, as_of)
    updated = result[0]['content']
    assert 'Inflation new common' in updated and 'Inflation surges to a record high' in updated
    assert 'Inflation old common' not in updated and 'Inflation old personal' not in updated
    assert updated.startswith('PERSONA AND PRICES\n\n')
    assert updated.endswith('QUESTIONNAIRE')
    assert updated.count(trial.POLICY_START + 'policy)') == 1
