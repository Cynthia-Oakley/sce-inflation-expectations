#!/usr/bin/env python3
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent / 'socioverse2_repo'))
import studies

studies.__path__ = [str(ROOT / 'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import dump, sha
from studies.sce_inflation_expectations.experiments.information_exposure import NEWS_START, POLICY_START
from studies.sce_inflation_expectations.experiments.media_mechanism_trial import ARMS, ASSEMBLY, external_count

PATTERN = r'^- Other news, in the order listed above: .*\.$'


def read(path):
    return json.loads(Path(path).read_text())


def masked(text):
    return text[:text.index(NEWS_START)] + re.sub(PATTERN, '<NEWS_TIMING>', text[text.index(POLICY_START):], flags=re.M)


def common_block(text):
    return text[text.index(NEWS_START):text.index('Other news you encountered:')]


def audit(out):
    out = Path(out).resolve()
    summary = read(out / 'summary.json')
    receipt = {'schema': 'sce_media_mechanism_trial_acceptance/v1', 'months': {},
               'checks': {}, 'output_sha256': {}, 'code_sha256': {}}
    for relative, expected in summary['source_sha256'].items():
        assert sha(ROOT / relative) == expected, f'Upstream input changed: {relative}'
    total_prompts = 0
    distinct_hashes = set()
    for month, month_summary in summary['months'].items():
        base = ROOT / ASSEMBLY / month
        original = read(base / 'initial_previews_private.json')
        levels = read(base / 'news_quantity_frame_private.json')
        prompts = {arm: read(out / month / arm / 'prompts_private.json') for arm in ARMS}
        contexts = {arm: read(out / month / arm / 'contexts_private.json') for arm in ARMS}
        ids = set(prompts['R0'])
        assert len(ids) == summary['n_per_month'] == 96
        assert all(set(prompts[arm]) == ids and set(contexts[arm]) == ids for arm in ARMS)
        treated = 0
        for aid in ids:
            count = levels[aid] - 3
            treated += count > 0
            reference = masked(original[aid]['messages'][0]['content'])
            common = {common_block(prompts[arm][aid][0]['content']) for arm in ARMS}
            assert len(common) == 1
            for arm in ARMS:
                text = prompts[arm][aid][0]['content']
                distinct_hashes.add(hashlib.sha256(text.encode()).hexdigest())
                assert masked(text) == reference
                assert len(contexts[arm][aid]['article_ids']) == count
                sources = contexts[arm][aid]['sources']
                external = sum(source != 'NYT' for source in sources)
                assert external == (external_count(count) if arm.startswith('M') else 0)
                assert len(contexts[arm][aid]['alarming']) == count
                for excluded in month_summary['external']['excluded']:
                    assert excluded['title'] not in text
            total_prompts += len(ARMS)
        month_receipt = {'agents': len(ids), 'agents_with_personal_news': treated,
                         'agents_with_common_only': len(ids) - treated,
                         'common_news': month_summary['common_news'],
                         'arms': month_summary['arms'],
                         'prompt_characters': month_summary['prompt_characters']}
        receipt['months'][month] = month_receipt
        for arm in ARMS:
            for name in ('prompts_private.json', 'contexts_private.json'):
                path = out / month / arm / name
                receipt['output_sha256'][str(path.relative_to(ROOT))] = sha(path)
    assert total_prompts == summary['prompt_position_count'] == 768
    assert summary['physical_call_cap_two_repeats'] == 1536
    receipt['prompt_position_count'] = total_prompts
    receipt['distinct_rendered_prompt_count'] = len(distinct_hashes)
    for month in summary['months'].values():
        for pair in (('R0', 'R1'), ('M0', 'M1')):
            assert month['arms'][pair[1]]['tone_exposures'].get('alarming', 0) > month['arms'][pair[0]]['tone_exposures'].get('alarming', 0)
    receipt['checks'] = {'prompt_positions_768': True, 'two_repeat_call_cap_1536': True,
                         'month_roster_size_96': True, 'upstream_input_hashes_match': True,
                         'non_news_bytes_unchanged': True,
                         'common_news_identical_across_arms': True, 'personal_article_counts_match_3_8_20': True,
                         'external_quota_exact': True, 'sce_reports_absent': True,
                         'negative_boost_increases_alarming_exposure': True,
                         'new_api_calls': 0}
    for name in ('summary.json', 'protocol.json'):
        receipt['output_sha256'][str((out / name).relative_to(ROOT))] = sha(out / name)
    for name in ('studies/sce_inflation_expectations/experiments/media_mechanism_trial.py',
                 'scripts/prepare_sce_media_mechanism_trial.py',
                 'scripts/audit_sce_media_mechanism_trial.py',
                 'tests/test_sce_media_mechanism_trial.py'):
        receipt['code_sha256'][name] = sha(ROOT / name)
    dump(out / 'acceptance.json', receipt)
    return receipt


def budget(out):
    out = Path(out).resolve()
    estimated_unique = 0.
    max_bytes = 0
    count = 0
    distinct_hashes = set()
    for path in sorted(out.glob('*/*/prompts_private.json')):
        for messages in read(path).values():
            text = messages[0]['content']
            estimated_unique += len(text) / 4 * .259 / 1e6 + 180 * .8 / 1e6
            max_bytes = max(max_bytes, len(text.encode()))
            distinct_hashes.add(hashlib.sha256(text.encode()).hexdigest())
            count += 1
    assert count == 768
    conservative = 2 * count * ((max_bytes + 1024) * .259 + 1024 * .8) / 1e6
    result = {'schema': 'sce_media_mechanism_trial_budget/v1', 'prompt_positions': count,
              'distinct_rendered_prompts': len(distinct_hashes),
              'physical_calls_two_repeats': 2 * count, 'price_input_per_mtok': .259,
              'price_output_per_mtok': .8, 'max_output_tokens': 1024,
              'expected_output_tokens_for_estimate': 180, 'max_prompt_utf8_bytes': max_bytes,
              'estimated_two_repeat_usd': 2 * estimated_unique,
              'conservative_two_repeat_reservation_usd': conservative,
              'suggested_cap_usd': int(conservative) + 1,
              'basis': 'Registered OpenRouter -> SiliconFlow/fp8 rates; chars/4 input estimate; UTF-8 bytes + 1024 conservative input bound; not a price guarantee or authorization.',
              'new_api_calls': 0, 'authorized': False}
    dump(out / 'budget.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description='Audit the offline media-mechanism prompt package.')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.out)
    cost = budget(args.out)
    print(json.dumps({'out': str(args.out), 'checks': result['checks'], 'budget': cost,
                      'months': {m: {'agents_with_personal_news': r['agents_with_personal_news'],
                                     'agents_with_common_only': r['agents_with_common_only']}
                                 for m, r in result['months'].items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
