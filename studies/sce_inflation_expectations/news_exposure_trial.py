"""Offline population/prompt preparation and scripted engine check for news views."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import subprocess
import sys

from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from .model import SCEEnvironmentProvider
from .news_exposure import ARMS, SCHEMA, REF, PROMPT_VERSION, build_messages, interests_for_profile, validate_bundle
from .news_exposure_demo import draw_news, prepare_window, verify_sources
from .price_experience import PROFILE_KEYS, canonical_hash, profile_hash

ROOT = Path(__file__).resolve().parents[2]
MONTHS = ('202105', '202106')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def load_labels(directories):
    labels = {}
    for directory in directories:
        if json.loads((directory / 'state.json').read_text())['status'] != 'completed':
            raise ValueError('label directory incomplete')
        for line in (directory / 'labels.jsonl').read_text().splitlines():
            label = json.loads(line)['label']
            if label['article_id'] in labels and labels[label['article_id']] != label:
                raise ValueError('conflicting labels cannot be silently overwritten')
            labels[label['article_id']] = label
    return labels


def prepare(root, folder, label_dirs, n=48):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    if folder.exists() or not folder.is_relative_to(root / 'outputs') or not 1 <= n <= 300:
        raise ValueError('new ignored outputs directory and valid sample size required')
    inputs = root / 'outputs/sce_nyt_selection_trial_20261011_v1'
    old_plan = json.loads((inputs / 'summary.json').read_text())
    verify_sources(old_plan)
    labels = load_labels(label_dirs)
    folder.mkdir(parents=True)
    plan = {'status': 'offline_prepared_not_authorized', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
            'research_line': 'A_historical_reconstruction', 'months': list(MONTHS), 'n_per_month': n,
            'seed': 42, 'arms': list(ARMS), 'common_count': 3, 'personal_count': 5,
            'mixing_weight_matched': .5, 'affinity_boost': 2., 'temperature': .5,
            'model': 'deepseek-flash', 'max_tokens': 1024, 'retry_max': 0,
            'planned_answers': n * 6, 'normal_expansion': False, 'new_api_calls': 0,
            'source_sha256': {}, 'metadata': {}, 'jobs': [],
            'primary_comparison': 'matched minus random; shared is a same-count reference',
            'analysis': 'Q9 sample median error, distribution distance/IQR, demographic groups; Q8 secondary. Same cases and weights across arms; not national or individual counterfactual truth.',
            'population_sampling': 'fixed seeded simple random sample from existing monthly 300 Core; no survey answers used',
            'temporal_repetition_policy': 'retain repeated-event articles at different timestamps',
            'limitations': ['NYT/A1 are exposure proxies; paper date and text vintage unverified.',
                            '50/50 and thresholds are design assumptions; unestimated household preferences.',
                            'Four CE categories do not identify utility spending; no synthetic utility share invented.',
                            'Each month cold-start; no own prior answer or longitudinal claim.',
                            'One news seed/one generation is preliminary; independent month and seeds needed.']}
    for p in [inputs / 'summary.json', root / 'studies/sce_inflation_expectations/news_exposure.py', Path(__file__)] + [d / name for d in label_dirs for name in ('state.json', 'labels.jsonl')]:
        plan['source_sha256'][str(p.relative_to(root))] = sha(p)
    links = []
    for month in MONTHS:
        directory = folder / month
        directory.mkdir()
        role_root = root / 'outputs/ce_population_baskets_20261006T063749Z_a8be0d98' / month
        env_root = root / 'outputs/price_experience_20261006_v1/n20' / month
        source_paths = [role_root / 'roles/core/population.json', role_root / 'experience.json', env_root / 'environment.json', env_root / 'simulation.json', inputs / f'pool_{month}.json']
        for p in source_paths:
            plan['source_sha256'][str(p.relative_to(root))] = sha(p)
        population = json.loads(source_paths[0].read_text())
        baskets = json.loads(source_paths[1].read_text())['experience_by_id']
        selected = sorted(population['personas'], key=lambda p: hashlib.sha256(f"42|news-sample|{month}|{p['agent_id']}".encode()).hexdigest())[:n]
        personas, rows = [], {}
        for i, p in enumerate(selected, 1):
            if p['weight'] != 1 or set(p['attributes']) - PROFILE_KEYS:
                raise ValueError('source population whitelist/weight')
            b = baskets[p['agent_id']]
            if b['profile_sha256'] != profile_hash(p['attributes']):
                raise ValueError('CE basket profile mismatch')
            aid = f'news_{month}_{i:03d}'
            new = deepcopy(p)
            new.update(agent_id=aid, weight=1., group_key=None, init_state={})
            personas.append(new)
            rows[aid] = {'profile_sha256': profile_hash(p['attributes']), 'spending_shares': deepcopy(b['spending_shares'])}
            links.append({'month': month, 'agent_id': aid, 'source_agent_id': p['agent_id']})
        population.update(personas=personas, materialized_count=n, provider_args={})
        pop = PopulationBundle.model_validate(population)
        env = EnvironmentBundle.model_validate(json.loads(source_paths[2].read_text()))
        sim = SimulationConfig.model_validate(json.loads(source_paths[3].read_text()))
        if sim.n_steps != 1 or sim.warm_start is not None or sim.seed != 42 or len(env.provider_args['targets']) != 1:
            raise ValueError('single-month cold start required')
        target = env.provider_args['targets'][0]
        if target['target_month'].replace('-', '') != month:
            raise ValueError('target mismatch')
        for key in ('audit_dir', 'run_id', 'household_state_by_id', 'price_experience_mechanism', 'experience_by_id', 'information_exposure'):
            env.provider_args.pop(key, None)
        env.provider_args['events_by_step'] = {}
        env.information_program.broadcasts = []
        env.scheduled_events = []
        env.provider_args['persona_by_id'] = {p.agent_id: p.attributes for p in pop.personas}
        dump(directory / 'population.json', pop.model_dump())
        dump(directory / 'environment.json', env.model_dump())
        info = next(w for w in old_plan['windows'] if w['target'] == month)
        common_pool, personal_pool, stats = prepare_window(inputs, info, labels)
        candidates = [r for r in json.loads(source_paths[4].read_text()) if r['new_hits']]
        missing = sorted(r['article_id'] for r in candidates if r['article_id'] not in labels)
        pool_status = 'partial_labels_offline_only' if missing else 'complete_coarse_candidate_labels'
        stats.update(unlabelled_candidates=len(missing), pool_status=pool_status,
                     sample_status='complete coarse-candidate labels' if not missing else 'partial existing labels; new classification pending')
        dump(directory / 'library.json', {'stats': stats, 'common_a1': common_pool, 'personal_keep': personal_pool})
        common, common_audit = draw_news(common_pool, 3, f'42|{month}|common-a1')
        common.sort(key=lambda r: (r['pub_date'], r['article_id']))
        shared, _ = draw_news(personal_pool, 5, f'42|{month}|shared')
        shared.sort(key=lambda r: (r['pub_date'], r['article_id']))
        provider = SCEEnvironmentProvider(env.model_copy(deep=True))
        provider.audit_dir = None
        provider.reset(42)
        provider.advance_to(1)
        observations = provider.observe_batch([p.agent_id for p in pop.personas], 1)
        snapshots = {p.agent_id: p.attributes for p in pop.personas}
        metadata = {'source_core_n': 300, 'population_counts': {k: dict(Counter(p.attributes.get(k) for p in pop.personas)) for k in ('age_group', 'region', 'housing_tenure', 'employment_status')},
                    'as_of': target['as_of'], 'library': stats, 'common_draw_audit': common_audit, 'delivery': {}}
        for arm in ARMS:
            delivered, audit = {}, {}
            for aid, row in rows.items():
                interests = interests_for_profile(snapshots[aid], row['spending_shares'])
                articles, draw_audit = draw_news(personal_pool, 5, f'42|{month}|{aid}|personal', interests, .5 if arm == 'matched' else 0., 2.)
                if arm == 'shared':
                    articles, draw_audit = shared, []
                articles = sorted(articles, key=lambda r: (r['pub_date'], r['article_id']))
                delivered[aid] = dict(row, personal_news=articles)
                audit[aid] = {'interests': sorted(interests), 'draw_audit': draw_audit,
                              'related_news_count': sum(bool(set(r['routing_tags']) & interests) for r in articles)}
            bundle = {'schema_version': SCHEMA, 'research_line': plan['research_line'], 'target_month': target['target_month'],
                      'as_of': target['as_of'], 'arm': arm, 'mixing_weight': .5 if arm == 'matched' else 0.,
                      'affinity_boost': 2., 'common_news': common, 'rows': delivered,
                      'source_sha256': deepcopy(plan['source_sha256']), 'pool_status': pool_status}
            validate_bundle(bundle, pop.personas, target['target_month'], target['as_of'])
            cfg = sim.model_copy(deep=True)
            cfg.decision_ref = REF
            cfg.decision_args = {'news_exposure_bundle': bundle, 'seed': 42, 'llm_kind': 'scripted',
                                 'prompt_version': PROMPT_VERSION, 'max_prompt_chars': 18000}
            dump(directory / f'simulation_{arm}.json', cfg.model_dump())
            previews = []
            for ob in observations:
                messages = build_messages(ob, bundle)
                text = json.dumps(messages, ensure_ascii=False)
                if len(text) > 18000 or 'Recent news headlines' in text:
                    raise ValueError('prompt size/old news duplicate path')
                previews.append({'agent_id': ob.agent_id, 'messages': messages,
                                 'prompt_sha256': hashlib.sha256(text.encode()).hexdigest()})
            dump(directory / f'preview_{arm}.json', previews)
            dump(directory / f'draw_audit_{arm}.json', audit)
            metadata['delivery'][arm] = {'unique_personal_sets': len({tuple(r['article_id'] for r in v['personal_news']) for v in delivered.values()}),
                                        'related_news_total': sum(v['related_news_count'] for v in audit.values())}
            run_id = f'{folder.name}-{month}-{arm}'
            command = [sys.executable, str(root / 'scripts/run_sce_local.py'), '--llm', 'openai', '--model', 'deepseek-flash',
                       '--population', str(directory / 'population.json'), '--environment', str(directory / 'environment.json'),
                       '--simulation', str(directory / f'simulation_{arm}.json'), '--prompt-version', PROMPT_VERSION,
                       '--run-id', run_id, '--temperature', '0.5', '--max-tokens', '1024', '--retry-max', '0', '--max-calls', str(n),
                       '--extra-body', '{"thinking":{"type":"disabled"}}', '--price-in', '0.30', '--price-out', '1.20',
                       '--cost-cap-usd', '0.25', '--confirm-spend']
            bounds = [(len(json.dumps(p['messages'], ensure_ascii=False).encode()) + 256) * .30 / 1e6 + 1024 * 1.20 / 1e6 for p in previews]
            job_cap = math.ceil(n * max(bounds) * 100) / 100
            command[command.index('--cost-cap-usd') + 1] = str(job_cap)
            plan['jobs'].append({'month': month, 'arm': arm, 'run_id': run_id, 'command': command,
                                 'pool_status': pool_status, 'conservative_cost_bound_usd': sum(bounds),
                                 'job_cap_usd': job_cap,
                                 'max_prompt_bytes': max(len(json.dumps(p['messages'], ensure_ascii=False).encode()) for p in previews)})
        plan['metadata'][month] = metadata
    dump(folder / 'evaluation_links_private.json', links)
    plan['complete_labels'] = all(j['pool_status'] == 'complete_coarse_candidate_labels' for j in plan['jobs'])
    plan['conservative_simulation_cost_bound_usd'] = sum(j['conservative_cost_bound_usd'] for j in plan['jobs'])
    plan['simulation_budget_authorization'] = 'not_requested; full labels and freeze required first'
    plan['proposed_simulation_cap_usd'] = math.ceil(sum(j['job_cap_usd'] for j in plan['jobs']) * 2) / 2
    plan['code_sha256'] = {str(p.relative_to(root)): sha(p) for p in [root / 'scripts/run_sce_local.py', root / 'scripts/run_sce_news_exposure_trial.py'] + sorted((root / 'studies/sce_inflation_expectations').rglob('*.py'))}
    plan['prepared_file_sha256'] = {str(p.relative_to(folder)): sha(p) for p in folder.rglob('*.json')}
    dump(folder / 'trial_manifest.json', plan)
    return plan


def dry_run(root, folder):
    folder = Path(folder)
    plan = json.loads((folder / 'trial_manifest.json').read_text())
    for name, expected in plan['code_sha256'].items():
        if sha(Path(root) / name) != expected:
            raise ValueError('code changed since preparation')
    for name, expected in plan['prepared_file_sha256'].items():
        if sha(folder / name) != expected:
            raise ValueError('prepared input changed')
    records = []
    for job in plan['jobs']:
        command = list(job['command'])
        command[command.index('openai')] = 'scripted'
        command.remove('--confirm-spend')
        command[command.index('--run-id') + 1] += '-engineering'
        with (folder / f"{job['month']}_{job['arm']}_engineering.log").open('w') as handle:
            result = subprocess.run(command, cwd=root, stdout=handle, stderr=subprocess.STDOUT)
        records.append({'month': job['month'], 'arm': job['arm'], 'exit_code': result.returncode})
        dump(folder / 'engineering_check.json', records)
        if result.returncode:
            raise RuntimeError('engine check failed; inspect private log')
    return records


def add_reading_preview(folder, page, prior_directory):
    """Append actual complete prompts to the existing local reading artifact."""
    folder, page, prior_directory = map(Path, (folder, page, prior_directory))
    plan = json.loads((folder / 'trial_manifest.json').read_text())
    prior = json.loads((prior_directory / 'summary.json').read_text())
    before = page.read_text()
    if sha(page) != prior['existing_html_after_sha256'] or 'id="news-simulation-readiness"' in before:
        raise ValueError('page changed or preview already exists; preserve the earlier page')
    esc = html.escape
    items = []
    for job in plan['jobs']:
        previews = json.loads((folder / job['month'] / f"preview_{job['arm']}.json").read_text())
        message = '\n\n'.join(r['content'] for r in previews[0]['messages'])
        items.append('<details><summary>' + esc(job['month'] + ' · ' + {'shared':'所有人共享同组新闻', 'random':'个人随机新闻', 'matched':'50%随机＋50%相关加权'}[job['arm']]) +
                     '</summary><pre style="white-space:pre-wrap;overflow-wrap:anywhere">' + esc(message) + '</pre></details>')
    status = '完整候选已精筛，尚未授权真实Simulation' if plan['complete_labels'] else '当前为部分标签，禁止真实Simulation；补标完成后另留新版本'
    section = ('<section id="news-simulation-readiness"><h2>下一轮真实模拟：输入准备</h2><p class="important">' + status + '</p>'
               '<p>沿用2021年5/6月，各48个已有Core去标识画像，三组共288份提示。人口、合成CE篮子、数值经济信息、问卷和温度0.5保持相同，仅新闻接触方式不同。每组共同3条头版＋5条其他经济新闻；50/50是抽样分布混合，不是内容配额。</p>'
               '<p>不同时间对同一事件的重复报道保留。四类CE篮子不能识别水电燃气支出，因此真实样本不会凭空分配水电燃气偏好。每月独立冷启动，未发送上月自己的回答；新闻按发布时间呈现。</p>'
               '<p>下面展示每个月同一位样本在三组中收到的完整提示，不包含原始ID或真实通胀回答。规则干跑只验证工程，不证明拟合改善。</p>' + ''.join(items) + '</section>')
    if before.count('<footer>') != 1:
        raise ValueError('expected one footer')
    (folder / 'news_review_before.html').write_text(before)
    page.write_text(before.replace('<footer>', section + '<footer>', 1))
    receipt = {'status': 'reading_preview_added_no_real_simulation', 'existing_html_before_sha256': hashlib.sha256(before.encode()).hexdigest(),
               'existing_html_after_sha256': sha(page), 'new_api_calls': 0, 'previewed_complete_prompts': 6,
               'full_labels': plan['complete_labels'], 'browser_visual_verification': False}
    dump(folder / 'summary.json', receipt)
    return receipt


def execute(root, folder, approval_note):
    """Fresh, explicitly authorized complete-label trial, no automatic restart."""
    root, folder = Path(root).resolve(), Path(folder).resolve()
    plan = json.loads((folder / 'trial_manifest.json').read_text())
    if not approval_note.strip() or plan['status'] != 'offline_prepared_not_authorized' or not plan['complete_labels']:
        raise ValueError('fresh complete-label trial and explicit new send/budget approval required')
    checks = json.loads((folder / 'engineering_check.json').read_text())
    if len(checks) != 6 or any(r['exit_code'] for r in checks):
        raise ValueError('engineering gate')
    for name, expected in plan['source_sha256'].items() | plan['code_sha256'].items():
        if sha(root / name) != expected:
            raise ValueError('frozen source changed')
    for name, expected in plan['prepared_file_sha256'].items():
        if sha(folder / name) != expected:
            raise ValueError('frozen input changed')
    if sum(j['job_cap_usd'] for j in plan['jobs']) > plan['proposed_simulation_cap_usd']:
        raise ValueError('aggregate budget guard')
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    host = (os.environ.get('SV_LLM_BASE_URL') or os.environ.get('OPENAI_BASE_URL') or '').rstrip('/')
    if host not in {'https://api.deepseek.com', 'https://api.deepseek.com/v1'}:
        raise ValueError('only the registered official DeepSeek endpoint is allowed')
    if any((root / 'outputs/local_runs' / j['run_id']).exists() for j in plan['jobs']):
        raise ValueError('existing run; no automatic repeat')
    plan['status'] = 'running'
    plan['simulation_budget_authorization'] = {'user_quote': approval_note, 'recorded_at_utc': datetime.now(timezone.utc).isoformat()}
    dump(folder / 'trial_manifest.json', plan)
    for job in plan['jobs']:
        with (folder / f"{job['month']}_{job['arm']}_real.log").open('w') as handle:
            proc = subprocess.run(job['command'], cwd=root, stdout=handle, stderr=subprocess.STDOUT)
        job['exit_code'] = proc.returncode
        if proc.returncode:
            plan['status'] = 'stopped_on_error'
            dump(folder / 'trial_manifest.json', plan)
            raise RuntimeError('real run stopped; inspect audit before any continuation')
        run = root / 'outputs/local_runs' / job['run_id']
        expected = json.loads((folder / job['month'] / f"preview_{job['arm']}.json").read_text())
        prompt_hashes = {r['agent_id']: r['prompt_sha256'] for r in expected}
        calls = [json.loads(l) for l in (run / 'llm_calls.jsonl').read_text().splitlines()]
        if len(calls) != plan['n_per_month'] or any(r['prompt_sha256'] != prompt_hashes[r['agent_id']] for r in calls):
            plan['status'] = 'stopped_audit_mismatch'
            dump(folder / 'trial_manifest.json', plan)
            raise RuntimeError('actual calls differ from frozen previews')
        ledger = json.loads((run / 'cost_ledger.json').read_text())
        job['estimated_cost_usd'] = ledger['estimated_cost_usd']
        dump(folder / 'trial_manifest.json', plan)
    plan['status'] = 'completed_pending_analysis'
    dump(folder / 'trial_manifest.json', plan)
