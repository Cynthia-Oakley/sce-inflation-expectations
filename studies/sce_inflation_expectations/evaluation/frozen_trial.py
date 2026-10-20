"""Common evaluation of frozen-block trials; reuse existing scorer/cell metrics."""
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from time import perf_counter
import duckdb
import numpy as np
from . import cognition as shared
from .metrics import quantile, wasserstein1
from ..experiments.frozen_batch import ROOT, verify, read_json, dump, sha, effective_temperature
from ..model import parse_sce_response
from ..experiments.staged_rosters import job_directory, job_n

TRUTH = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'


@lru_cache(maxsize=None)
def score_bins(bins):
    return shared._score_bins(list(bins))


def paired_intervals(cases, arms, months, repeats, support, draws=1000, seed=20261017):
    """Paired person bootstrap conditional on the selected calendar months."""
    cells = [shared._cell_rows(cases, m, r, support) for m in months for r in repeats]
    if any(not cell for cell in cells): return {'reason': 'Incomplete common support', 'intervals': None}
    people = sorted({r['userid'] for cell in cells for r in cell}); index = {v: i for i, v in enumerate(people)}
    rng = np.random.default_rng(seed); samples = []
    for _ in range(draws):
        counts = np.bincount(rng.integers(len(people), size=len(people)), minlength=len(people))
        scores = {arm: np.zeros(3) for arm in arms}; valid = True
        for cell in cells:
            w = np.array([r['survey_weight']*counts[index[r['userid']]] for r in cell])
            if not w.sum(): valid = False; break
            y = np.array([r['real']['q9_mean'] for r in cell])
            for arm in arms:
                p = np.array([r['arms'][arm]['mean'] for r in cell])
                scores[arm] += [abs(quantile(p, w, .5)-quantile(y, w, .5)), np.average(abs(p-y), weights=w), wasserstein1(p, w, y, w)]
        if valid: samples.append((scores[arms[1]]-scores[arms[0]])/len(cells))
    return {'draws_used': len(samples), 'seed': seed,
        'intervals': dict(zip(('q9_center_mae_pp', 'individual_density_mean_mae_pp', 'cross_section_w1_pp'),
                             np.quantile(samples, [.025, .975], axis=0).T.tolist())),
        'scope': 'Exploratory unadjusted paired person clusters, months/repeats kept together; not time-generalization intervals.'}


def attach_reused_baseline(cases, folder, protocol):
    """Reuse already checked/scored answers only for exactly matching P/E prompts.

    Cache and original run artifacts are pinned in the new preparation manifest.
    No new API calls, invented run receipts, or replacement baseline responses.
    """
    parent = ROOT/protocol['reuse_baseline_trial']
    old = read_json(ROOT/protocol['reuse_baseline_evaluation']/'cases_private.json')
    index = {(r['month'], r['agent_id'], r['repeat']): r for r in old}
    if len(index) != len(old): raise ValueError('Duplicate reused baseline cases')
    for month in protocol['months']:
        original = read_json(parent/str(month)/'prompts_baseline.json')
        if original != read_json(folder/str(month)/'prompts_baseline.json'):
            raise ValueError('Reused baseline prompt changed')
    for row in cases:
        previous = index[row['month'], row['agent_id'], row['repeat']]
        if (previous['userid'] != row['userid'] or previous['profile'] != row['profile']
                or abs(previous['survey_weight']-row['survey_weight']) > 1e-12
                or previous['real'] != row['real']):
            raise ValueError('Reused baseline roster, weight or target mismatch')
        row['arms']['baseline'] = previous['arms']['baseline']


def evaluate(folder, out):
    started = perf_counter(); folder, out = Path(folder).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'): raise ValueError('Fresh ignored evaluation output required')
    manifest, protocol = verify(folder)
    if protocol.get('execution_mode') == 'engineering_only':
        raise ValueError('Engineering-only answers are not research results; no truth read or accuracy scoring')
    truth_file=(ROOT/protocol.get('evaluation_truth',str(TRUTH.relative_to(ROOT)))).resolve()
    if not truth_file.is_relative_to(ROOT/'outputs') or truth_file.name!='cases_private.json':
        raise ValueError('Safe cached evaluation truth required')
    relative = str(truth_file.relative_to(ROOT))
    if manifest['source_sha256'].get(relative) != sha(truth_file): raise ValueError('Pinned evaluation truth required')
    q8_only=protocol['mechanism']=='q8_delta_absolute_q9'
    if protocol.get('evaluation_truth_format') == 'legacy_revision_format':
        from .q8_delta import legacy_truth
        reference=(ROOT/protocol['evaluation_bin_reference']).resolve()
        if not reference.is_relative_to(ROOT/'outputs') or manifest['source_sha256'].get(str(reference.relative_to(ROOT)))!=sha(reference):
            raise ValueError('Pinned legacy bin reference required')
        truth=legacy_truth(read_json(truth_file),reference)
    else:
        truth = {(r['month'], r['agent_id'], r['repeat']): r['real'] for r in read_json(truth_file)}
    links = read_json(folder/'evaluation_links_private.json')
    actions = {}; cost = 0.; coverage = {a: Counter() for a in protocol['arms']}
    for job in manifest['jobs']:
        audit = ROOT/'outputs/local_runs'/job['run_id']; receipt = read_json(audit/'run_manifest.json')
        expected_protocol = protocol.get('reused_completed_jobs', {}).get(job['run_id'], manifest['protocol_sha256'])
        if receipt['status'] != 'completed' or receipt['llm_kind'] != 'openai' or receipt['protocol_sha256'] != expected_protocol:
            raise ValueError('Complete real run required; engineering outputs are not experiments')
        previews = read_json(job_directory(folder, protocol, job)/f"prompts_{job['arm']}.json")['rows']
        calls = [json.loads(line) for line in (audit/'llm_calls.jsonl').read_text().splitlines() if line]
        if len(calls) != job_n(protocol, job) or len({c['agent_id'] for c in calls}) != len(calls):
            raise ValueError('One audited call per person required')
        calls = {c['agent_id']: c for c in calls}
        if set(calls) != set(previews): raise ValueError('Call/preview roster mismatch')
        mappings={}
        if q8_only:
            mapping_rows=[json.loads(s) for s in (audit/'response_mapping.jsonl').read_text().splitlines() if s]
            mappings={r['agent_id']:r for r in mapping_rows}
            if len(mappings)!=len(mapping_rows) or set(mappings)!=set(calls):
                raise ValueError('Complete Q8 raw-to-parser evidence required')
        db = duckdb.connect(str(audit/'study.duckdb'), read_only=True)
        try: rows = db.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall()
        finally: db.close()
        if len(rows) != job_n(protocol, job) or len({aid for aid, _ in rows}) != len(rows): raise ValueError('Incomplete action roster')
        for aid, payload in rows:
            payload = json.loads(payload) if isinstance(payload, str) else payload
            call = calls[aid]; raw = call.get('raw_response_text') or ''
            if protocol.get('transport') == 'openrouter_locked' and (
                    call.get('returned_model') != protocol['model'] or call.get('returned_provider') != 'DeepInfra'
                    or call['extra_body'] != protocol['request_extra_body'] or call['temperature'] != protocol['temperature']):
                raise ValueError('Locked model/provider/request evidence mismatch')
            if protocol['mechanism'] == 'temperature_sensitivity' and (
                    call['temperature'] != effective_temperature(protocol, job)
                    or call['max_tokens'] != protocol['max_tokens']
                    or call['extra_body'] != {'thinking': {'type': 'disabled'}}):
                raise ValueError('Temperature-only request settings differ from protocol')
            if (call['prompt_sha256'] != previews[aid]['prompt_sha256'] or call['prompt_text'] != json.dumps(previews[aid]['messages'], ensure_ascii=False)
                    or call['raw_response_sha256'] != hashlib.sha256(raw.encode()).hexdigest()
                    or call['attempt_idx'] != 0 or payload.get('actual_messages_sha256') != previews[aid]['prompt_sha256']):
                raise ValueError('Input/reply audit mismatch')
            parser_text=raw;independent_q8=None
            if q8_only:
                from ..q8_delta_contract import mapping_result
                from ..revision_format_runtime import previous_answer
                parser_text,independent_q8,mapping_error=mapping_result(raw,job['arm'],
                    previous_answer(previews[aid]['messages'])['point_pct'])
                record=mappings[aid]
                if (record['raw_response_sha256']!=call['raw_response_sha256']
                    or record['parser_input_sha256']!=hashlib.sha256(parser_text.encode()).hexdigest()
                    or record['mapping_error']!=mapping_error or record['arm']!=job['arm']
                    or record['reconstructed_q8_point']!=independent_q8):
                    raise ValueError('Q8 conversion evidence mismatch')
            parsed, error = parse_sce_response(parser_text)
            if parsed is not None and any(abs(float(payload[f'q9_bin{i+1}'])-parsed['bins'][i]) > 1e-9 for i in range(10)):
                raise ValueError('Raw reply/action probabilities differ')
            if parsed is not None and abs(float(payload['point_pct'])-parsed['point_pct']) > 5e-5:
                raise ValueError('Raw reply/action point differs')
            bins = [payload[f'q9_bin{i}'] for i in range(1, 11)]
            score = score_bins(tuple(bins)) if payload['validation_status'] == 'valid' else {'mean': None, 'iqr': None, 'zero_deflation': None}
            action_key = job['month'], job['repeat'], aid, job['arm']
            if action_key in actions:
                raise ValueError('Duplicate person across roster segments')
            actions[action_key] = {**score, 'q9_bins': bins,
                'point': (round(independent_q8,4) if independent_q8 is not None else None) if q8_only
                    else payload['point_pct'] if parsed is not None else None,
                'validation_status': payload['validation_status']}
            coverage[job['arm']][payload['validation_status']] += 1
        cost += receipt['cost']['estimated_cost_usd']
    cases = []
    for link in links:
        for repeat in protocol['generation_repeats']:
            m, aid = link['month'], link['agent_id']
            cases.append({**link, 'repeat': repeat, 'survey_weight': link['design_survey_weight'],
                'real': truth[m, aid, repeat], 'arms': {arm: actions[m, repeat, aid, arm] for arm in protocol['arms']}})
    arms, months, repeats = list(protocol['arms']), protocol['months'], protocol['generation_repeats']
    if protocol.get('reuse_baseline_evaluation'):
        attach_reused_baseline(cases, folder, protocol)
        arms = ['baseline', *arms]
        coverage['baseline'] = Counter(r['arms']['baseline']['validation_status'] for r in cases)
    support9 = shared._common_person_months(cases, arms, repeats, 'q9')
    support8 = shared._common_person_months(cases, arms, repeats, 'q8')
    summaries = {arm: shared._summarize_arm(cases, arm, months, repeats, support9, support8) for arm in arms}
    if q8_only:
        for summary in summaries.values():
            summary['auxiliary_survey_weighted']['weight_definition']=protocol['q9_guard_weight']
    expected = protocol['n_per_month']*len(months)*len(repeats)
    valid = all(coverage[arm]['valid']/expected >= .99 for arm in arms)
    scorable = {arm: sum(shared.finite(r['arms'][arm].get('mean')) and shared.finite(r['arms'][arm].get('iqr')) for r in cases) for arm in arms}
    valid = valid and all(n/expected >= .99 for n in scorable.values())
    primary_arms = protocol.get('primary_comparison', arms[:2])
    extra_pairs = protocol.get('additional_comparisons',
        ([['baseline', arms[2]], [arms[2], arms[1]]] if len(arms) == 3 else []))
    result = {'status': 'completed_frozen_block_evaluation', 'protocol': protocol,
        'new_api_calls': 0, 'estimated_actual_cost_usd': cost, 'coverage': {k: dict(v) for k, v in coverage.items()},
        'common_q9_person_months': len(support9), 'common_q8_person_months': len(support8), 'scorable_counts': scorable,
        'arms': summaries, 'primary_view': 'auxiliary_survey_weighted: its survey_weight is frozen design-survey weight here.',
        'primary_comparison': primary_arms,
        'paired_intervals': paired_intervals(cases, primary_arms, months, repeats, support9) if valid else None,
        'additional_paired_intervals': {f'{other}_minus_{base}': paired_intervals(cases, [base, other], months, repeats, support9)
            for base, other in extra_pairs} if valid else None,
        'accuracy_descriptive_only': not valid, 'automatic_upgrade': False,
        'evaluation_seconds': perf_counter()-started, 'scorer_cache_distinct_vectors': score_bins.cache_info().currsize,
        'notes': ['No correction of invalid replies. Human scores are reused from frozen evaluation; new model vectors use the same scorer.',
                  'All-arm/both-repeat common support; macro and individual metrics are distinct; repeats are not extra people.',
                  'Reused baseline cost is historical, excluded from this batch estimated_actual_cost_usd.']}
    if q8_only:
        from .q8_delta import point_readout
        point=point_readout(cases,protocol)
        q8_valid={a:sum(shared.finite(r['arms'][a]['point']) for r in cases)/len(cases) for a in arms}
        result['primary_view']='Q8 equal people/months/repeats; Q9 guard uses archived survey-weight sensitivity.'
        result['q8_independent']=point;result['q8_valid_fraction']=q8_valid
        base,candidate=arms
        def guard(a,key):return summaries[a]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells'][key]
        complete=point.get('paired_person_intervals95') is not None
        result['candidate_continuation_passed']=bool(complete and valid and min(q8_valid.values())>=.99
            and point['paired_person_intervals95']['w1_pp'][1]<0
            and point['equal_people'][candidate]['center_mae_pp']<=point['equal_people'][base]['center_mae_pp']
            and guard(candidate,'q9_center_mae_pp')<=guard(base,'q9_center_mae_pp')
            and guard(candidate,'cross_section_w1_pp')<=guard(base,'cross_section_w1_pp'))
    if protocol['mechanism'] == 'temperature_sensitivity':
        from .temperature import dispersion_readout
        result['temperature_dispersion'] = dispersion_readout(cases, protocol)
    out.mkdir(parents=True); dump(out/'summary.json', result); dump(out/'cases_private.json', cases)
    return result
