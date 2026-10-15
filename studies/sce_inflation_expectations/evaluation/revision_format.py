"""Offline evaluation and raw-reply reconstruction audit for the format pilot."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
from .anchor_role import compare_cases, prior_response
from .expanded_state import sha, dump, metrics, MAIN
from .behavior_comparison import score, finite
from ..revision_format_runtime import ARMS, decode_revision
from ..model import parse_sce_response
from ..scoring.sce_q9_frozen import provenance

ROOT = Path(__file__).resolve().parents[3]
TRUTH = ROOT/'outputs/sce_information_update_evaluation_20261014_v1/cases_private.json'


def describe_failed_coverage(cases):
    """No inferential bootstrap after substantial arm-dependent invalidity.

    A multinomial draw can give zero supported mass in a generation when its
    few valid people differ from the other generation. Conditioning/resampling
    away that failure would invent a new inferential protocol. Keep descriptive
    same-row comparisons and make the validity failure the primary conclusion.
    """
    common = [r for r in cases if r['common']]
    arms = ['original', 'belief_start', 'copy_previous', 'history_anchor_half']
    results = {arm: metrics(common, arm) for arm in arms}
    contrast = {key: {'change_pp': results['belief_start']['aggregate'][key]-results['original']['aggregate'][key],
                     'paired_person_within_month_ci95_pp': None,
                     'month_bootstrap_sensitivity95_pp': None} for key in MAIN}
    for v in results.values():
        v.pop('case_predictions')
    counts = Counter((r['month'], r['userid']) for r in common)
    return {'results': results, 'belief_start_minus_original': contrast,
            'prior_position': {arm: prior_response(common, arm) for arm in ['original', 'belief_start']},
            'survey_weighted_auxiliary': {arm: metrics(common, arm, weights=[r['survey_weight'] for r in common])['aggregate'] for arm in arms},
            'common_generation_rows': len(common), 'unique_common_person_months': len(counts),
            'person_months_with_both_repeats': sum(v == 2 for v in counts.values()),
            'distinct_people': len({r['userid'] for r in common}),
            'interval_scope': 'No accuracy inference: arm-dependent invalidity exceeds the prespecified validity gate. Complete-row descriptions are selection-affected, not all-sample effects.',
            'analysis_amendment_after_validity_failure': 'Initial bootstrap stopped on zero supported mass in a resample. No prompts or answers were changed; no new API. Report primary validity failure and descriptive common-row values only, rather than inventing a conditional bootstrap.'}


def load(folder):
    manifest = json.loads((folder/'manifest.json').read_text())
    protocol = json.loads((folder/'protocol.json').read_text())
    if sha(folder/'protocol.json') != manifest['protocol_sha256'] or not provenance()['live_matches_pinned']:
        raise ValueError('Protocol/scorer changed')
    for name, digest in manifest['prepared_file_sha256'].items():
        if sha(folder/name) != digest:
            raise ValueError('Prepared input changed: '+name)
    if sha(TRUTH) != manifest['source_sha256'][str(TRUTH.relative_to(ROOT))]:
        raise ValueError('Frozen evaluation source changed')
    fields = ['actual', 'actual_iqr', 'actual_zero_deflation', 'actual_point', 'previous',
              'previous_bins', 'previous_point', 'copy_previous', 'history_anchor_half']
    truth = {}
    for row in json.loads(TRUTH.read_text()):
        key = (row['month'], row['agent_id']); values = {k: row[k] for k in fields}
        if key in truth and truth[key] != values:
            raise ValueError('Truth differs between generation rows')
        truth[key] = values
    links = json.loads((folder/'evaluation_links_private.json').read_text())
    cases = [{**truth[r['month'], r['agent_id']], **{k: r[k] for k in ['month', 'agent_id', 'userid', 'profile', 'survey_weight']},
              'repeat': repeat} for r in links for repeat in protocol['generation_repeats']]
    lookup = {(r['month'], r['repeat'], r['agent_id']): r for r in cases}
    sources = {str(TRUTH.relative_to(ROOT)): sha(TRUTH)}
    coverage = Counter(); scorable = Counter(); cost = 0.; audited = 0
    for job in manifest['jobs']:
        directory = ROOT/'outputs/local_runs'/job['run_id']
        run = json.loads((directory/'run_manifest.json').read_text())
        if run['status'] != 'completed' or run['llm_kind'] != 'openai' or run['cost']['call_count'] != protocol['n_per_month']:
            raise ValueError('Complete real cell required; incomplete evidence remains archived')
        cost += run['cost']['estimated_cost_usd']
        names = ['run_manifest.json', 'study.duckdb', 'llm_calls.jsonl']
        if job['arm'] == 'revision':
            names.append('response_mapping.jsonl')
        for name in names:
            path = directory/name; sources[str(path.relative_to(ROOT))] = sha(path)
        previews = {r['agent_id']: r for r in json.loads((folder/str(job['month'])/f"preview_{job['arm']}.json").read_text())}
        calls = [json.loads(line) for line in (directory/'llm_calls.jsonl').read_text().splitlines()]
        if len(calls) != protocol['n_per_month'] or len({r['agent_id'] for r in calls}) != len(calls):
            raise ValueError('Call cardinality/retry mismatch')
        calls = {r['agent_id']: r for r in calls}
        db = duckdb.connect(str(directory/'study.duckdb'), read_only=True)
        actions = db.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall(); db.close()
        if len(actions) != protocol['n_per_month'] or {aid for aid, _ in actions} != set(previews):
            raise ValueError('Action cardinality mismatch')
        for aid, payload in actions:
            p = json.loads(payload) if isinstance(payload, str) else payload
            call = calls[aid]; expected_hash = previews[aid]['prompt_sha256']
            if p.get('revision_format_arm') != job['arm'] or p.get('actual_messages_sha256') != expected_hash or call['prompt_sha256'] != expected_hash:
                raise ValueError('Actual prompt/arm binding mismatch')
            raw = call['raw_response_text'] or ''
            if hashlib.sha256(raw.encode()).hexdigest() != call['raw_response_sha256']:
                raise ValueError('Original response hash drift')
            row = lookup[job['month'], job['repeat'], aid]
            bins = [p[f'q9_bin{i}'] for i in range(1, 11)]
            if p['validation_status'] == 'valid':
                if job['arm'] == 'revision':
                    prior = {'point_pct': row['previous_point'], 'q9': dict(zip([f'bin{i}' for i in range(1, 11)], row['previous_bins']))}
                    restored = decode_revision(raw, prior)
                    point = restored['point_pct']; raw_bins = list(restored['q9'].values())
                else:
                    restored, error = parse_sce_response(raw)
                    if error:
                        raise ValueError('Valid direct action has invalid raw reply')
                    point, raw_bins = restored['point_pct'], restored['bins']
                if abs(round(point, 4)-p['point_pct']) > 1e-8 or not np.allclose(raw_bins, bins, rtol=0, atol=1e-8):
                    raise ValueError('Raw response and scored action disagree')
                audited += 1
            result = score(bins) if p['validation_status'] == 'valid' else score([])
            arm = job['arm']; row[arm] = result['mean']; row[arm+'_bins'] = bins
            row[arm+'_iqr'] = result['iqr']; row[arm+'_zero_deflation'] = result['zero_deflation']
            row[arm+'_point'] = p['point_pct'] if p['validation_status'] == 'valid' else None
            coverage[arm+':'+p['validation_status']] += 1
            scorable[arm+':'+('scorable' if finite(result['mean']) else 'unscorable')] += 1
    for row in cases:
        row['common'] = all(finite(row[k]) for k in ['actual', 'previous', *ARMS, 'history_anchor_half'])
    return cases, sources, dict(coverage), dict(scorable), cost, audited


def evaluate(folder, out, draws=2000):
    folder = Path(folder).resolve(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    protocol = json.loads((folder/'protocol.json').read_text())
    cases, sources, coverage, scorable, cost, audited = load(folder)
    aliases = []
    for row in cases:
        r = dict(row)
        for alias, arm in [('original', 'direct'), ('belief_start', 'revision')]:
            r[alias] = row[arm]
            for suffix in ['_bins', '_iqr', '_zero_deflation', '_point']:
                r[alias+suffix] = row[arm+suffix]
        aliases.append(r)
    rate = sum(scorable.get(a+':scorable', 0) for a in ARMS)/protocol['planned_calls']
    result = compare_cases(aliases, protocol, draws) if rate >= .99 else describe_failed_coverage(aliases)
    mapping = {'original': 'direct', 'belief_start': 'revision'}
    for key in ['results', 'prior_position', 'survey_weighted_auxiliary']:
        result[key] = {mapping.get(k, k): v for k, v in result[key].items()}
    contrast = result.pop('belief_start_minus_original'); result['revision_minus_direct'] = contrast
    gate = rate >= .99 and contrast['cross_section_w1_pp']['paired_person_within_month_ci95_pp'][1] < 0 and all(
        contrast[k]['change_pp'] <= 0 for k in ['sample_center_mae_pp', 'delta_w1_pp']) and rate >= .99
    summary = {'status': 'completed_revision_format_development_pilot',
        'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'protocol': protocol,
        'protocol_sha256': sha(folder/'protocol.json'), 'new_api_calls': protocol['planned_calls'],
        'new_peak_cost_estimate_usd': cost, 'cost_is_provider_bill': False,
        'coverage': coverage, 'scorable_coverage': scorable, 'new_valid_scorable_fraction': rate,
        'valid_raw_replies_reconstructed_and_matched': audited,
        'candidate_continue_gate_passed': gate, 'source_sha256': sources,
        'scorer': provenance(), **result}
    out.mkdir(parents=True); dump(out/'summary.json', summary); dump(out/'cases_private.json', cases)
    return summary
