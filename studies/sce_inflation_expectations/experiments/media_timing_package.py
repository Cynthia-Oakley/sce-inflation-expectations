"""Freeze the personal-date x alarming-news comparison without paid sending.

The dated input draft is immutable. Old replies are reused only for the same
person, month, repeat, message bytes, model and supplier. Nothing reads targets.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha, worker
from . import frozen_message_queue as queue
from .media_timing_inputs import (BASE, PARENT, NEWS, POLICY, TIMING, STATE,
                                  parsed, replace_region, timing_block)
from .media_mechanism_v3 import draw_personal
from .media_mechanism_v3_preparation import load_supplemental_run
from .state_continuity_execution import reserve
from ..news_exposure import interests_for_profile
from ..news_exposure_demo import render_news_input
from ..prior_belief_experiment import message_hash

ARMS = ('C0', 'C1', 'T0', 'T1')
OLD_RUN = ROOT/'outputs/sce_media_mechanism_terminal_20261025_v2'
METADATA = ROOT/'data/raw/mcp_checks/2026-10-21_v32_fullperiod_free_v1/deepseek_v32_endpoints.json'


def replace_personal_news(row, context, state, personal):
    """Change exactly the news region and its release-order tags."""
    result = deepcopy(row['messages'])
    text = result[0]['content']
    old_news = text[text.index(NEWS):text.index(POLICY)]
    rendered = render_news_input(context['common_news'], context['personal_news'])
    if not old_news.startswith(rendered) or old_news[len(rendered):].strip():
        raise ValueError('Original dated news does not reproduce')
    new = dict(context, personal_news=personal)
    text = replace_region(text, NEWS, POLICY,
        render_news_input(new['common_news'], personal)+old_news[len(rendered):])
    old_timing = text[text.index(TIMING):text.index(STATE)]
    trailing = old_timing[len(old_timing.rstrip('\n')):]
    text = replace_region(text, TIMING, STATE, timing_block(new, state).rstrip('\n')+trailing)
    if text[text.index(STATE):] != result[0]['content'][result[0]['content'].index(STATE):]:
        raise ValueError('Prior, questions or output contract changed')
    result[0]['content'] = text
    return {'messages': result, 'prompt_sha256': message_hash(result)}, new


def validate_labels(pool, labels):
    """Do not silently call a missing tone neutral, or replace an old label."""
    result = deepcopy(pool)
    for row in result:
        semantic = row['semantic_label']
        aid = row['article_id']
        if aid in labels:
            for field, value in labels[aid].items():
                if semantic.get(field) is not None and semantic[field] != value:
                    raise ValueError('Supplemental run conflicts with frozen old label')
                semantic[field] = value
        if not all(semantic.get(field) is not None for field in ('tone', 'persistence')):
            raise ValueError('Date-eligible keep article still lacks supplemental labels')
    return result


def request_identity(month, aid, repeat, digest):
    return month, aid, repeat, digest


def plan_reuse(bundles, replies, protocol):
    """Plan all logical views; never send an already attempted exact failure."""
    old, by_source_key = {}, {}
    for row in replies:
        if row.get('actual_model_results') is not True:
            raise ValueError('Only actual archived model replies may be reused')
        if not row.get('error') and (row.get('returned_model') != protocol['model'] or
                                   row.get('returned_provider') != protocol['expected_provider']):
            raise ValueError('Archived receiver differs from new frozen receiver')
        key = request_identity(row['month'], row['agent_id'], row['repeat'], row['prompt_sha256'])
        by_source_key[row['key']] = row
        def priority(answer):
            return bool(answer.get('technical_usable')), answer['key'].split('|')[1] == 'Q3'
        if key not in old or priority(row) > priority(old[key]):
            old[key] = row
    positions, slots, unique = [], [], {}
    for month, arm, rows in bundles:
        for aid, row in sorted(rows.items()):
            if message_hash(row['messages']) != row['prompt_sha256']:
                raise ValueError('Prompt hash differs')
            for repeat in protocol['generation_repeats']:
                identity = request_identity(month, aid, repeat, row['prompt_sha256'])
                pos = dict(month=month, arm=arm, repeat=repeat, agent_id=aid,
                           prompt_sha256=row['prompt_sha256'])
                prior = old.get(identity)
                if arm == 'O0':
                    prior = by_source_key.get(f'{month}|Q3|{repeat}|{aid}')
                    if prior is None or request_identity(prior['month'], prior['agent_id'],
                            prior['repeat'], prior['prompt_sha256']) != identity:
                        raise ValueError('Original reference has no exact archived Q3 attempt')
                if prior is not None:
                    pos.update(status='reuse_exact_success' if prior.get('technical_usable') else
                               'hold_old_attempted_failure', source_key=prior['key'])
                else:
                    first = identity not in unique
                    if first:
                        key = f'{month}|{arm}|{repeat}|{aid}'
                        size = len(json.dumps(row['messages'], ensure_ascii=False).encode())
                        slot = dict(key=key, month=month, arm=arm, repeat=repeat, agent_id=aid,
                            prompt_sha256=row['prompt_sha256'], messages=row['messages'],
                            reserved_usd=reserve(protocol, size))
                        unique[identity] = slot
                        slots.append(slot)
                    pos.update(status='new_request' if first else 'reuse_same_new_prompt',
                               new_request_key=unique[identity]['key'])
                positions.append(pos)
    slots.sort(key=lambda s: hashlib.sha256(('media_timing_dispatch|'+s['key']).encode()).digest())
    return positions, slots


def core_check(package, protocol, out):
    """Each month/arm/repeat uses the existing official one-step Core worker."""
    out.mkdir(exist_ok=False)
    checks = []
    for month in protocol['months']:
        base = BASE/str(month)
        for arm in ARMS:
            bundle = read_json(package/str(month)/f'prompts_{arm}.json')
            ids = set(bundle['rows'])
            for repeat in protocol['generation_repeats']:
                cell = out/f'{month}-{arm}-r{repeat}'
                dest = cell/str(month)
                dest.mkdir(parents=True)
                population = read_json(base/'population.json')
                population['personas'] = [v for v in population['personas'] if v['agent_id'] in ids]
                if len(population['personas']) != len(ids):
                    raise ValueError('Official roster differs')
                for person in population['personas']:
                    person['weight'] = 1.
                dump(dest/'population.json', population)
                dump(dest/'environment.json', read_json(base/'environment.json'))
                dump(dest/'simulation.json', read_json(PARENT/str(month)/'simulation.json'))
                dump(dest/f'prompts_{arm}.json', bundle)
                engineering = dict(execution_mode='engineering_only', destination=None,
                    model='NOT_CONFIGURED_ENGINEERING_ONLY', mechanism='media_timing_engine_check',
                    months=[month], arms=[arm], generation_repeats=[repeat], n_per_month=len(ids),
                    engineering_decision_count=len(ids), planned_calls=0, budget_cap_usd=0,
                    temperature=.5, max_tokens=1024, retry_max=0, thinking='disabled',
                    max_prompt_chars=protocol['max_prompt_chars'], price_input_per_mtok=0,
                    price_output_per_mtok=0)
                dump(cell/'protocol.json', engineering)
                run_id = f'{package.name}-{month}-{arm}-r{repeat}'
                job = dict(month=month, arm=arm, repeat=repeat, seed=41+repeat, run_id=run_id, cap_usd=0)
                dump(cell/'manifest.json', dict(planned_calls=0, jobs=[job],
                    protocol_sha256=sha(cell/'protocol.json'), source_sha256={},
                    prepared_file_sha256={str(p.relative_to(cell)): sha(p) for p in cell.rglob('*.json')}))
                worker(cell, 0, True)
                receipt = ROOT/'outputs/local_runs'/(run_id+'-engineering')/'run_manifest.json'
                actual = read_json(receipt)
                if actual['status'] != 'completed' or actual['cost']['call_count'] != 0 or not actual['actual_input_hashes_match']:
                    raise ValueError('Official Core check failed')
                checks.append(dict(month=month, arm=arm, repeat=repeat, n=len(ids), run_id=run_id,
                    receipt_file=str(receipt.relative_to(ROOT)), receipt_sha256=sha(receipt),
                    protocol_sha256=sha(cell/'protocol.json'), exit_code=0))
    return checks


def build(draft, labels_dir, out):
    draft, labels_dir, out = map(lambda p: Path(p).resolve(), (draft, labels_dir, out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh output under outputs required')
    original_manifest = read_json(draft/'manifest.json')
    for name, digest in original_manifest['files_sha256'].items():
        if sha(draft/name) != digest:
            raise ValueError('Immutable input draft changed')
    source_summary = read_json(draft/'summary.json')
    for name, digest in source_summary['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Original material source changed')
    labels = load_supplemental_run(labels_dir)
    pending = read_json(draft/'supplemental_label_inputs/pending_public_articles.json')
    # The prepared public article file is a list, not a target dataset.
    if set(labels) != {r['article_id'] for r in pending}:
        raise ValueError('Supplemental scope differs from pending unique articles')
    protocol = deepcopy(read_json(PARENT/'protocol.json'))
    protocol.update(mechanism='v32_media_timing', experiment_design='personal_time_x_alarming_2x2',
        arms=list(ARMS), reference_arms=['O0'], old_run=str(OLD_RUN.relative_to(ROOT)),
        evaluation_package=str(PARENT.relative_to(ROOT)),
        n_by_month={str(r['month']): r['n_timing_eligible'] for r in source_summary['months']},
        n_per_month=None, max_workers=64, timeout_s=120,
        provider_metadata=str(METADATA.relative_to(ROOT)),
        budget_mode='spent_plus_inflight_reservation', primary_comparison=['C0','T0'],
        additional_comparisons=[['O0','C0'],['C0','C1'],['T0','T1']],
        timing_convention='Previous calendar day end 23:59:59 America/New_York, based on completed survey date; A reconstruction only.',
        baseline_definition='Copy own observed adjacent previous Q8/Q9 only, identical comparison support.',
        primary_metrics=['q9_center_mae_pp_all_seven','q9_center_mae_pp_2021_selected_three'],
        old_failures='Held as archived; no silent resend of an exact old attempt.',
        strict_B_eligible=False)
    protocol['limits'] = [
        'Date-only completion metadata uses previous-day-end NY convention, not certified response-hour matching.',
        'Previously inspected seven months; exploratory, no independent time validation.',
        'Month-label out-of-month completion excluded before outcomes (one June 2022 response).',
        'O0 archived reference vs C0 isolates General-news timing-label correction.',
        'C0 vs T0 changes news and dated grocery/policy/confidence jointly; it is an information-date bundle.',
        'Labels are content descriptors, not measured personal fear or causal exposure weights.',
        'Personal completion day-derived cutoff is sent as public information date; no raw respondent identifiers.']
    bundles, context_summary = [], []
    out.mkdir(parents=True, mode=0o700)
    for row in source_summary['months']:
        month = row['month']
        folder = out/str(month)
        folder.mkdir()
        for arm in ('C0','C1','T0'):
            bundle = read_json(draft/str(month)/f'prompts_{arm}.json')
            dump(folder/f'prompts_{arm}.json', bundle)
            bundles.append((month, arm, bundle['rows']))
        contexts = read_json(draft/str(month)/'contexts_T0_private.json')
        states = read_json(BASE/str(month)/'initial_states_private.json')
        pool = validate_labels(read_json(draft/str(month)/'full_news_pool_private.json'), labels)
        pool_by_id = {r['article_id']: r for r in pool}
        baskets = read_json(BASE/str(month)/'baskets_private.json')
        profiles = {v['agent_id']: v['attributes'] for v in read_json(BASE/str(month)/'population.json')['personas']}
        t0 = read_json(folder/'prompts_T0.json')['rows']
        t1, c1 = {}, {}
        for aid, ctx in contexts.items():
            cutoff = parsed(ctx['as_of'])
            common_ids = {r['article_id'] for r in ctx['common_news']}
            available = [r for r in pool if parsed(r['pub_date']) <= cutoff and r['article_id'] not in common_ids]
            count = len(ctx['personal_news'])
            interests = interests_for_profile(profiles[aid], baskets[aid]['spending_shares'])
            personal = draw_personal(available, [], count, f'20261025|{month}|{aid}', interests,
                                    alarming_boost=2., cpi_boost=1.5, fox_share=0.)
            t1[aid], c1[aid] = replace_personal_news(t0[aid], ctx, states[aid], personal)
        dump(folder/'prompts_T1.json', {'month': month, 'arm': 'T1', 'rows': t1})
        dump(folder/'contexts_T1_private.json', c1)
        bundles.append((month, 'T1', t1))
        original = read_json(PARENT/str(month)/'prompts_Q3.json')['rows']
        bundles.append((month, 'O0', {aid: original[aid] for aid in t0}))
        context_summary.append(dict(month=month, n=len(t0), new_vs_old_date=dict(Counter(
            'earlier' if parsed(v['as_of']) < parsed(row['shared_cutoff']) else
            'later' if parsed(v['as_of']) > parsed(row['shared_cutoff']) else 'same'
            for v in contexts.values())),
            alarming_t0=sum(pool_by_id[r['article_id']]['semantic_label']['tone'] == 'alarming'
                for ctx in contexts.values() for r in ctx['personal_news']),
            alarming_t1=sum(r['semantic_label']['tone'] == 'alarming' for ctx in c1.values() for r in ctx['personal_news'])))
    _, old_replies = queue.archive(OLD_RUN)
    old_protocol = read_json(PARENT/'protocol.json')
    for field in ('destination','transport','model','route','expected_provider','temperature','thinking','response_format','max_tokens','request_extra_body'):
        if protocol[field] != old_protocol[field]:
            raise ValueError('Archived model/configuration is not identical')
    positions, slots = plan_reuse(bundles, old_replies, protocol)
    planned = len(slots)
    expected = sum((len(json.dumps(s['messages'], ensure_ascii=False).encode())/4*.259+300*.8)/1e6 for s in slots)
    bound = sum(s['reserved_usd'] for s in slots)
    protocol.update(planned_calls=planned, logical_positions=len(positions),
        estimated_cost_usd=expected, conservative_reservation_usd=bound,
        budget_cap_usd=math.ceil(bound),
        max_prompt_chars=max(len(m['content']) for s in slots for m in s['messages']))
    dump(out/'protocol.json', protocol)
    dump(out/'positions_private.json', positions)
    dump(out/'new_requests_private.json', slots)
    checks = core_check(out, protocol, out/'core_engineering')
    dump(out/'engineering_checks.json', checks)
    pins = dict(source_summary['source_sha256'])
    for path in (draft/'manifest.json', draft/'summary.json', labels_dir/'state.json', labels_dir/'labels.jsonl',
                 OLD_RUN/'config.json', PARENT/'manifest.json', PARENT/'protocol.json', METADATA, Path(__file__)):
        pins[str(path.relative_to(ROOT))] = sha(path)
    for check in checks:
        pins[check['receipt_file']] = check['receipt_sha256']
    for path in OLD_RUN.glob('round_*/segment_*/manifest.json'):
        pins[str(path.relative_to(ROOT))] = sha(path)
    stats = Counter(r['status'] for r in positions)
    summary = dict(status='prepared_official_core_complete_awaiting_simulation_authorization',
        new_api_calls=0, target_answers_read=False, months=protocol['months'], arms=list(ARMS),
        reference_arms=['O0'], n_by_month=protocol['n_by_month'], repeats=protocol['generation_repeats'],
        logical_positions=len(positions), unique_new_requests=planned, reuse=dict(stats),
        estimated_cost_usd=expected, conservative_reservation_usd=bound,
        suggested_budget_cap_usd=protocol['budget_cap_usd'], official_engine_units=len(checks),
        scripted_decisions=sum(r['n'] for r in checks), source_draft=str(draft.relative_to(ROOT)),
        supplemental_labels=str(labels_dir.relative_to(ROOT)), context_summary=context_summary,
        timing_label_correction_person_months=sum(r['general_timing_label_repairs'] for r in source_summary['months']),
        source_sha256=pins)
    dump(out/'summary.json', summary)
    dump(out/'manifest.json', dict(protocol_sha256=sha(out/'protocol.json'), planned_calls=planned,
        source_sha256=pins,
        prepared_file_sha256={str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')}))
    return {k:v for k,v in summary.items() if k not in ('source_sha256','context_summary')}
