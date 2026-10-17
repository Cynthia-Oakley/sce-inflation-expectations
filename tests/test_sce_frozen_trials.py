"""Only new block, manifest and provider contracts; archived trials are not rerun."""
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
# Prefer the maintained study source; official Core remains an external dependency.
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.financial_outlook import render_q2, add_block
from studies.sce_inflation_expectations.experiments.frozen_batch import authorize, dump, sha
from studies.sce_inflation_expectations.frozen_prompt_runtime import FrozenPromptDecision, PROMPT
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash


def test_actual_fact_only_and_window():
    record = {'target_month': 202003, 'source_month': 202002, 'q2_code': 2}
    text = render_q2(record)
    assert 'somewhat worse' in text and '12 months after that survey' in text
    assert '%' not in text and 'inflation' not in text


def test_missing_unchanged_not_imputed():
    messages = [{'role': 'user', 'content': 'Keep P/E and questions\nReply with ONLY a JSON object'}]
    block = render_q2({'target_month': 202003, 'source_month': 202002, 'q2_code': None})
    assert add_block(messages, block) == messages


@pytest.mark.parametrize('change', [{'source_month': 202003}, {'q2_code': 8}, {'current_q2': 2}])
def test_no_concurrent_or_extra_fields(change):
    with pytest.raises(ValueError):
        render_q2({**{'target_month': 202003, 'source_month': 202002, 'q2_code': 2}, **change})


def test_only_inserted_block_changes_bytes():
    messages = [{'role': 'user', 'content': 'P/E\nQ8 and Q9\nReply with ONLY a JSON object'}]
    original = deepcopy(messages); changed = add_block(messages, 'Only this fact\n\n')
    assert messages == original and changed[0]['content'].replace('Only this fact\n\n', '', 1) == original[0]['content']


def test_unapproved_scope_stops_before_credentials(tmp_path):
    dump(tmp_path/'authorization.json', {'approved': False})
    with pytest.raises(ValueError, match='authorization'):
        authorize(tmp_path, {'protocol_sha256': 'test'}, {'budget_cap_usd': 4, 'planned_calls': 768, 'destination': 'https://api.deepseek.com'})


def test_frozen_provider_rejects_prompt_or_month_drift(tmp_path):
    path = tmp_path/'prompts.json'; messages = [{'role': 'user', 'content': 'Q8 and Q9 only'}]
    dump(path, {'month': 202003, 'arm': 'baseline', 'rows': {'anon': {'messages': messages, 'prompt_sha256': message_hash(messages)}}})
    decision = FrozenPromptDecision(llm_kind='scripted', prompt_version=PROMPT, retry_max=0,
                                   prompts_file=str(path), prompts_sha256=sha(path))
    ob = SimpleNamespace(agent_id='anon', macro_information={'target_month': '2020-03'})
    assert decision.build_llm_messages(ob) == messages
    ob.macro_information['target_month'] = '2020-04'
    with pytest.raises(ValueError, match='month'): decision.build_llm_messages(ob)
    data = json.loads(path.read_text()); data['rows']['anon']['messages'][0]['content'] = 'Changed'
    dump(path, data)
    with pytest.raises(ValueError, match='hash'): FrozenPromptDecision(llm_kind='scripted', prompt_version=PROMPT, retry_max=0,
                                   prompts_file=str(path), prompts_sha256=sha(path))
