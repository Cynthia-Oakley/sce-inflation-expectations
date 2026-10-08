#!/usr/bin/env python3
"""Prepare fixed 2021 model comparisons offline; never read keys or call APIs."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from socioverse.schemas import EnvironmentBundle, PopulationBundle
from studies.sce_inflation_expectations.model import SCEEnvironmentProvider, build_sce_messages_v2
from studies.sce_inflation_expectations.monthly_population import ATTRIBUTE_KEYS
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import provenance

MODELS = {
    'deepseek-flash': {'destination': 'https://api.deepseek.com/v1', 'provider': 'DeepSeek',
        'input_price': .30, 'output_price': 1.20, 'extra_body': {'thinking': {'type': 'disabled'}},
        'price_basis': 'previous configured estimate; refresh before execution'},
    'qwen/qwen-2.5-72b-instruct': {'destination': 'https://openrouter.ai/api/v1', 'provider': 'DeepInfra',
        'route': 'deepinfra/fp8', 'input_price': .36, 'output_price': .40},
    'meta-llama/llama-3.1-70b-instruct': {'destination': 'https://openrouter.ai/api/v1', 'provider': 'DeepInfra',
        'route': 'deepinfra/turbo', 'input_price': .40, 'output_price': .40},
    'meta-llama/llama-3.3-70b-instruct': {'destination': 'https://openrouter.ai/api/v1', 'provider': 'DeepInfra',
        'route': 'deepinfra/turbo', 'input_price': .10, 'output_price': .32,
        'execution_gate': 'same format protocol must pass before annual batch'},
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    manifest_path = args.packages / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    if manifest['sampling_design'] != 'stable_priority_srs' or manifest['seed'] != 42:
        raise ValueError('sampling design changed')
    if manifest['source_sha256'] != '1b57ffb75c2170d767f46a001002db8c40c228fe5691f6dd19e39777ffe469c6':
        raise ValueError('population workbook differs from audited source')
    receipt_path = ROOT / 'docs/sources/sce_environment_2020_2025_20261007.json'
    receipt = json.loads(receipt_path.read_text())
    env_artifact = next(r for r in receipt['artifacts'] if r['path'].endswith('/environment_candidate.json'))
    if manifest['environment_source_sha256'] != env_artifact['sha256'] or sha(ROOT / env_artifact['path']) != env_artifact['sha256']:
        raise ValueError('annual environment differs from accepted source')
    scorer = provenance()
    if not scorer['live_matches_pinned']:
        raise ValueError('scorer differs from frozen source')
    sources = {str(manifest_path.resolve().relative_to(ROOT)): sha(manifest_path),
        str(receipt_path.relative_to(ROOT)): sha(receipt_path)}
    for entry in manifest['packages']:
        for name, expected in entry['sha256'].items():
            path = args.packages / entry['path'] / name
            if sha(path) != expected:
                raise ValueError('monthly package changed')
            sources[str(path.resolve().relative_to(ROOT))] = expected
    args.out.mkdir(parents=True, exist_ok=False)
    month_reports = []
    char_counts = []
    with (args.out / 'requests_prepared.jsonl').open('w') as requests, (args.out / 'case_identity_private.jsonl').open('w') as identities:
        for month in range(202101, 202113):
            core_dir = args.packages / 'n300' / str(month)
            full_dir = args.packages / 'all' / str(month)
            population = json.loads((core_dir / 'population.json').read_text())
            full = json.loads((full_dir / 'population.json').read_text())
            if len(population['personas']) != 300:
                raise ValueError('need 300 fixed Core per month')
            core = {p['agent_id']: p for p in population['personas']}
            if len(core) != 300 or not set(core).issubset({p['agent_id'] for p in full['personas']}):
                raise ValueError('invalid Core identity set')
            if any(set(p['attributes']) - ATTRIBUTE_KEYS for p in population['personas']):
                raise ValueError('nonwhitelisted profile fields')
            PopulationBundle.model_validate(population)
            raw_env = json.loads((core_dir / 'environment.json').read_text())
            if raw_env != json.loads((full_dir / 'environment.json').read_text()):
                raise ValueError('Core and full environment differ')
            env_config = copy.deepcopy(raw_env)
            env_config['provider_args']['persona_by_id'] = {u: p['attributes'] for u, p in core.items()}
            env = SCEEnvironmentProvider(EnvironmentBundle.model_validate(env_config))
            env.reset(42)
            env.advance_to(1)
            observations = {o.agent_id: o for o in env.observe_batch(sorted(core), 1)}
            message_hashes = {}
            for i, uid in enumerate(sorted(core), 1):
                case = f'{month // 100}-{month % 100:02}_case_{i:03}'
                messages = build_sce_messages_v2(observations[uid], include_event_abstracts=True)
                text = json.dumps(messages, ensure_ascii=False)
                if uid in text:
                    raise ValueError('original ID leaked into model message')
                digest = hashlib.sha256(text.encode()).hexdigest()
                message_hashes[case] = digest
                char_counts.append(len(text))
                identities.write(json.dumps({'case_id': case, 'source_agent_id': uid, 'month': month, 'messages_sha256': digest}) + '\n')
                for model, option in MODELS.items():
                    payload = {'model': model, 'messages': messages, 'temperature': .5, 'max_tokens': 1024,
                        'response_format': {'type': 'json_object'}}
                    if option.get('route'):
                        payload['provider'] = {'order': [option['route']], 'allow_fallbacks': False, 'require_parameters': True}
                    else:
                        payload.update(option['extra_body'])
                    # Only payload crosses the API boundary; case and cost metadata stay local.
                    requests.write(json.dumps({'case_id': case, 'month': month,
                        'destination': option['destination'], 'payload': payload,
                        'input_price_per_million': option['input_price'],
                        'output_price_per_million': option['output_price'],
                        'route_candidate': option.get('route')}, ensure_ascii=False) + '\n')
            target = raw_env['provider_args']['targets'][0]
            month_reports.append({'month': month, 'frame_n': len(full['personas']), 'core_n': 300,
                'normal_n': len(full['personas']) - 300, 'as_of': target['as_of'],
                'signal_count': len(raw_env['provider_args']['signals_by_step']['0']),
                'news_count': len(raw_env['provider_args']['events_by_step']['0']),
                'message_hashes_sha256': hashlib.sha256(json.dumps(message_hashes, sort_keys=True).encode()).hexdigest()})
    per_model = {m: {**v, 'target_answers': 3600,
        'reference_token_estimate_usd': 3600 * (2500 * v['input_price'] + 150 * v['output_price']) / 1e6}
        for m, v in MODELS.items()}
    report = {'status': 'prepared offline; new annual budget and live execution not authorized',
        'research_line': 'A retrospective reconstruction/model comparison; not blind B forecast',
        'months': month_reports, 'population_package': str(args.packages.resolve().relative_to(ROOT)),
        'core_n_per_month': 300, 'normal_population': 'complete current-month retrospective frame',
        'base_unique_case_inputs': 3600, 'potential_answers': 14400, 'models': per_model,
        'reference_total_usd': sum(v['reference_token_estimate_usd'] for v in per_model.values()),
        'proposed_new_budget_cap_usd': 20., 'new_llm_calls': 0, 'new_paid_mcp_calls': 0,
        'temperature': .5, 'prompt_version': 'sce-q8-q9-v2-abstract', 'max_tokens': 1024,
        'seed': 42, 'normal_prior_strength': 5., 'minimum_group_count': 20,
        'population_sampling': 'stable-priority SRS per current wave; no answer-based selection',
        'prompt_character_count': {'mean': sum(char_counts) / len(char_counts), 'min': min(char_counts), 'max': max(char_counts)},
        'requests_sha256': sha(args.out / 'requests_prepared.jsonl'),
        'private_mapping_sha256': sha(args.out / 'case_identity_private.jsonl'),
        'source_sha256': sources, 'scorer': scorer,
        'code_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__).resolve(),
            ROOT / 'studies/sce_inflation_expectations/model.py', ROOT / 'studies/sce_inflation_expectations/monthly_population.py',
            ROOT / 'studies/sce_inflation_expectations/core_normal.py']},
        'limitations': ['One planned valid generation per model/case, no estimate of regeneration variance',
            '2021 development year already inspected; no untouched test or no-memory claim',
            'A monthly CPI release-day input, not each respondent answer-date information or previous-month B input',
            'Gasoline/news versions have existing uncertainty; no strict-PIT claim',
            'Prepared monthly simulation.json files are scripted placeholders, not real-model execution configs',
            'Annual execution/format-repair/evaluation adapter still require implementation and validation',
            'Earlier answers may only be reused after exact-message/config/protocol checks; not counted as reused yet']}
    dump(args.out / 'summary.json', report)
    (args.out / 'source_snapshot').mkdir()
    for rel in report['code_sha256']:
        (args.out / 'source_snapshot' / Path(rel).name).write_bytes((ROOT / rel).read_bytes())
    print(json.dumps({k: report[k] for k in ['base_unique_case_inputs', 'potential_answers', 'reference_total_usd', 'prompt_character_count', 'requests_sha256', 'new_llm_calls']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
