"""Same-person frequency-instruction evaluation; offline, frozen scorer."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb
from .anchor_role import compare_cases, prior_response
from .expanded_state import metrics, sha, dump
from .behavior_comparison import score, finite
from ..scoring.sce_q9_frozen import provenance

ROOT = Path(__file__).resolve().parents[3]
OLD_CASES = ROOT / 'outputs/sce_information_update_evaluation_20261014_v1/cases_private.json'
ARMS = ('frequency_data', 'frequency_rule')


def load(folder):
    m = json.loads((folder / 'manifest.json').read_text())
    p = json.loads((folder / 'protocol.json').read_text())
    if sha(folder / 'protocol.json') != m['protocol_sha256'] or not provenance()['live_matches_pinned']:
        raise ValueError('frozen protocol/scorer changed')
    if sha(OLD_CASES) != m['source_sha256'][str(OLD_CASES.relative_to(ROOT))]:
        raise ValueError('frozen truth/prior changed')
    fields = ['actual', 'actual_iqr', 'actual_zero_deflation', 'actual_point', 'previous',
              'previous_bins', 'previous_point', 'copy_previous', 'history_anchor_half',
              'month', 'repeat', 'userid', 'agent_id', 'profile', 'survey_weight']
    cases = []
    for old in json.loads(OLD_CASES.read_text()):
        row = {k: old[k] for k in fields}
        row['reused_C'] = old['dated_information']
        for suffix in ['_bins', '_iqr', '_zero_deflation', '_point']:
            row['reused_C' + suffix] = old.get('dated_information' + suffix)
        cases.append(row)
    lookup = {(r['month'], r['repeat'], r['agent_id']): r for r in cases}
    links = json.loads((folder / 'evaluation_links_private.json').read_text())
    expected = {(r['month'], repeat, r['agent_id']) for r in links for repeat in p['generation_repeats']}
    if len(cases) != len(expected) or set(lookup) != expected:
        raise ValueError('same frozen roster/repeats required')
    for name, digest in m['prepared_file_sha256'].items():
        if sha(folder / name) != digest:
            raise ValueError('prepared input changed: ' + name)
    for j in m['reused_jobs']:
        for name in ['run_manifest.json', 'study.duckdb', 'llm_calls.jsonl']:
            path = ROOT / 'outputs/local_runs' / j['run_id'] / name
            if sha(path) != m['source_sha256'][str(path.relative_to(ROOT))]:
                raise ValueError('old context changed')
    sources = {str(OLD_CASES.relative_to(ROOT)): sha(OLD_CASES)}
    coverage = Counter(); scorable = Counter(); cost = 0.0
    for j in m['jobs']:
        directory = ROOT / 'outputs/local_runs' / j['run_id']
        run = json.loads((directory / 'run_manifest.json').read_text())
        if run.get('status') != 'completed' or run['llm_kind'] != 'openai' or run['cost']['call_count'] != p['n_per_month']:
            raise ValueError('complete real cell required; partial runs remain separately archived')
        cost += run['cost']['estimated_cost_usd']
        for name in ['run_manifest.json', 'study.duckdb', 'llm_calls.jsonl']:
            path = directory / name; sources[str(path.relative_to(ROOT))] = sha(path)
        previews = {r['agent_id']: r['prompt_sha256'] for r in json.loads((folder / str(j['month']) / f"preview_{j['arm']}.json").read_text())}
        conn = duckdb.connect(str(directory / 'study.duckdb'), read_only=True)
        actions = conn.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall(); conn.close()
        if len(actions) != p['n_per_month'] or {a for a, _ in actions} != set(previews):
            raise ValueError('missing or duplicate actions')
        for aid, payload in actions:
            payload = json.loads(payload) if isinstance(payload, str) else payload
            if payload.get('purchase_frequency_arm') != j['arm'] or payload.get('actual_messages_sha256') != previews[aid]:
                raise ValueError('actual message/arm binding mismatch')
            arm = j['arm']; row = lookup[j['month'], j['repeat'], aid]
            bins = [payload.get(f'q9_bin{i}') for i in range(1, 11)]
            result = score(bins) if payload['validation_status'] == 'valid' else score([])
            row[arm] = result['mean']; row[arm + '_bins'] = bins
            row[arm + '_iqr'] = result['iqr']; row[arm + '_zero_deflation'] = result['zero_deflation']
            row[arm + '_point'] = payload.get('point_pct') if payload['validation_status'] == 'valid' else None
            coverage[arm + ':' + payload['validation_status']] += 1
            scorable[arm + ':' + ('scorable' if finite(result['mean']) else 'unscorable')] += 1
    for row in cases:
        row['common'] = all(finite(row[k]) for k in ['actual', 'previous', *ARMS, 'history_anchor_half'])
    return cases, sources, dict(coverage), dict(scorable), cost


def compare(cases, protocol, draws=2000):
    aliases = []
    for row in cases:
        r = dict(row)
        for alias, arm in [('original', 'frequency_data'), ('belief_start', 'frequency_rule')]:
            r[alias] = row[arm]
            for suffix in ['_bins', '_iqr', '_zero_deflation', '_point']:
                r[alias + suffix] = row.get(arm + suffix)
        aliases.append(r)
    result = compare_cases(aliases, protocol, draws)
    result['results'] = {**{arm: result['results'][alias] for arm, alias in [('frequency_data', 'original'), ('frequency_rule', 'belief_start')]},
                         **{k: result['results'][k] for k in ['copy_previous', 'history_anchor_half']}}
    result['frequency_rule_minus_data'] = result.pop('belief_start_minus_original')
    result['prior_position'] = {arm: result['prior_position'][alias] for arm, alias in [('frequency_data', 'original'), ('frequency_rule', 'belief_start')]}
    result['survey_weighted_auxiliary'] = {**{arm: result['survey_weighted_auxiliary'][alias] for arm, alias in [('frequency_data', 'original'), ('frequency_rule', 'belief_start')]},
                                         **{k: result['survey_weighted_auxiliary'][k] for k in ['copy_previous', 'history_anchor_half']}}
    context = [r for r in cases if r['common'] and finite(r['reused_C'])]
    if len(context) != result['common_generation_rows']:
        raise ValueError('historical context support differs; do not silently compare')
    past = metrics(context, 'reused_C'); past.pop('case_predictions')
    result['results']['reused_C_context'] = past
    result['context_limit'] = 'Earlier C batch without the added price/frequency block; only descriptive context, not a clean incremental data effect.'
    return result


def evaluate(folder, out):
    folder = Path(folder).resolve(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('fresh ignored output required')
    protocol = json.loads((folder / 'protocol.json').read_text())
    cases, sources, coverage, scorable, cost = load(folder)
    result = compare(cases, protocol)
    rate = sum(scorable.get(a + ':scorable', 0) for a in ARMS) / protocol['planned_calls']
    contrast = result['frequency_rule_minus_data']
    gate = contrast['cross_section_w1_pp']['paired_person_within_month_ci95_pp'][1] < 0 and all(
        contrast[k]['change_pp'] <= 0 for k in ['sample_center_mae_pp', 'delta_w1_pp']) and rate >= .99
    summary = {'status': 'completed_purchase_frequency_instruction_trial',
               'completed_at_utc': datetime.now(timezone.utc).isoformat(),
               'protocol': protocol, 'protocol_sha256': sha(folder / 'protocol.json'),
               'new_api_calls': protocol['planned_calls'], 'new_cost_estimate_usd': cost,
               'cost_is_provider_bill': False, 'coverage': coverage, 'scorable_coverage': scorable,
               'new_valid_scorable_fraction': rate, 'candidate_continue_gate_passed': gate,
               'source_sha256': sources, 'scorer': provenance(), **result}
    out.mkdir(parents=True); dump(out / 'summary.json', summary); dump(out / 'cases_private.json', cases)
    return summary
