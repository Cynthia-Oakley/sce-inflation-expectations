"""Evaluate new B/C with frozen old A; zero API, explicit batch limitation."""
import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone

import duckdb

from .anchor_role import compare_cases, prior_response
from .expanded_state import metrics, sha, dump, MAIN
from .behavior_comparison import score, finite
from ..scoring.sce_q9_frozen import provenance

ROOT = Path(__file__).resolve().parents[3]
OLD_CASES = ROOT / 'outputs/sce_anchor_role_evaluation_20261014_v1/cases_private.json'
NEW_ARMS = ('new_wording', 'dated_information')


def alias_cases(cases, old, new):
    result = []
    for row in cases:
        r = dict(row)
        for alias, arm in [('original', old), ('belief_start', new)]:
            r[alias] = row[arm]
            for suffix in ['_bins', '_iqr', '_zero_deflation', '_point']:
                r[alias + suffix] = row.get(arm + suffix)
        result.append(r)
    return result


def compare(cases, protocol, draws=2000):
    primary = compare_cases(alias_cases(cases, 'new_wording', 'dated_information'), protocol, draws)
    exploratory = compare_cases(alias_cases(cases, 'reused_A', 'new_wording'), protocol, draws)
    common = [r for r in cases if r['common']]
    results = {name: primary['results'][alias] for name, alias in [('new_wording', 'original'), ('dated_information', 'belief_start')]}
    results['reused_A'] = metrics(common, 'reused_A'); results['reused_A'].pop('case_predictions')
    for baseline in ['copy_previous', 'history_anchor_half']: results[baseline] = primary['results'][baseline]
    return {
        'results': results,
        'primary_dated_minus_wording': primary['belief_start_minus_original'],
        'exploratory_wording_minus_reused_A': exploratory['belief_start_minus_original'],
        'exploratory_batch_limit': 'Old A is from an earlier batch. Resampling people cannot quantify or remove provider/batch drift.',
        'prior_position': {name: prior_response(common, name) for name in ['reused_A', *NEW_ARMS]},
        'survey_weighted_auxiliary': {a: metrics(common, a, weights=[r['survey_weight'] for r in common])['aggregate'] for a in results},
        **{k: primary[k] for k in ['common_generation_rows', 'unique_common_person_months', 'person_months_with_both_repeats', 'distinct_people', 'interval_scope']},
    }


def load(folder):
    m = json.loads((folder / 'manifest.json').read_text())
    if sha(folder / 'protocol.json') != m['protocol_sha256'] or not provenance()['live_matches_pinned']:
        raise ValueError('frozen protocol/scorer changed')
    if sha(OLD_CASES) != m['source_sha256'][str(OLD_CASES.relative_to(ROOT))]:
        raise ValueError('frozen parent evaluation changed')
    for j in m['reused_jobs']:
        for name in ['run_manifest.json', 'study.duckdb', 'llm_calls.jsonl']:
            p = ROOT / 'outputs/local_runs' / j['run_id'] / name
            if sha(p) != m['source_sha256'][str(p.relative_to(ROOT))]: raise ValueError('reused actual answer drift')
    cases = []
    for old in json.loads(OLD_CASES.read_text()):
        r = dict(old)
        r['reused_A'] = r['belief_start']
        for suffix in ['_bins', '_iqr', '_zero_deflation', '_point']: r['reused_A' + suffix] = r['belief_start' + suffix]
        for key in list(r):
            if key.startswith('original') or key.startswith('belief_start'): r.pop(key)
        cases.append(r)
    lookup = {(r['month'], r['repeat'], r['agent_id']): r for r in cases}
    expected = {(j['month'], j['repeat'], row['agent_id'])
                for j in m['reused_jobs'] for row in json.loads((folder / str(j['month']) / 'population.json').read_text())['personas']}
    if len(cases) != m['reused_calls'] or set(lookup) != expected:
        raise ValueError('reused A does not cover exactly the frozen roster/repeats')
    sources = {str(OLD_CASES.relative_to(ROOT)): sha(OLD_CASES)}; coverage = Counter(); scorable = Counter(); cost = 0.0
    for j in m['jobs']:
        d = ROOT / 'outputs/local_runs' / j['run_id']; run = json.loads((d / 'run_manifest.json').read_text())
        if run['llm_kind'] != 'openai' or run['cost']['call_count'] != 48: raise ValueError('complete 48-call real cell required')
        cost += run['cost']['estimated_cost_usd']
        for name in ['run_manifest.json', 'study.duckdb', 'llm_calls.jsonl']: sources[str((d / name).relative_to(ROOT))] = sha(d / name)
        previews = {r['agent_id']: r['prompt_sha256'] for r in json.loads((folder / str(j['month']) / f"preview_{j['arm']}.json").read_text())}
        conn = duckdb.connect(str(d / 'study.duckdb'), read_only=True)
        actions = conn.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall(); conn.close()
        if len(actions) != 48: raise ValueError('missing actions')
        for aid, payload in actions:
            p = json.loads(payload) if isinstance(payload, str) else payload
            if p.get('information_update_arm') != j['arm'] or p.get('actual_messages_sha256') != previews[aid]:
                raise ValueError('actual prompt/arm binding mismatch')
            arm = j['arm']; r = lookup[j['month'], j['repeat'], aid]
            bins = [p.get(f'q9_bin{i}') for i in range(1, 11)]
            s = score(bins) if p['validation_status'] == 'valid' else score([])
            r[arm] = s['mean']; r[arm + '_bins'] = bins; r[arm + '_iqr'] = s['iqr']; r[arm + '_zero_deflation'] = s['zero_deflation']
            r[arm + '_point'] = p.get('point_pct') if p['validation_status'] == 'valid' else None
            coverage[arm + ':' + p['validation_status']] += 1
            scorable[arm + ':' + ('scorable' if finite(s['mean']) else 'unscorable')] += 1
    for r in cases:
        r['common'] = all(finite(r[k]) for k in ['actual', 'previous', 'reused_A', *NEW_ARMS, 'history_anchor_half'])
    return cases, sources, dict(coverage), dict(scorable), cost


def evaluate(folder, out):
    folder = Path(folder).resolve(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'): raise ValueError('fresh ignored output required')
    p = json.loads((folder / 'protocol.json').read_text()); cases, sources, coverage, scorable, cost = load(folder)
    result = compare(cases, p)
    rate = sum(scorable.get(a + ':scorable', 0) for a in NEW_ARMS) / p['planned_calls']
    contrast = result['primary_dated_minus_wording']
    gate = contrast['cross_section_w1_pp']['paired_person_within_month_ci95_pp'][1] < 0 and all(
        contrast[k]['change_pp'] <= 0 for k in ['sample_center_mae_pp', 'delta_w1_pp']) and rate >= .99
    summary = {'status': 'completed_information_update_followup', 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'protocol': p, 'protocol_sha256': sha(folder / 'protocol.json'),
               'new_api_calls': p['planned_calls'], 'reused_A_answer_rows': len(cases), 'new_cost_estimate_usd': cost,
               'cost_is_provider_bill': False, 'coverage': coverage, 'scorable_coverage': scorable,
               'new_valid_scorable_fraction': rate, 'candidate_continue_gate_passed': gate,
               'source_sha256': sources, 'scorer': provenance(), **result}
    out.mkdir(parents=True); dump(out / 'summary.json', summary); dump(out / 'cases_private.json', cases)
    return summary
