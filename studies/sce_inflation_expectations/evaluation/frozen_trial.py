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
from ..experiments.frozen_batch import ROOT, verify, read_json, dump, sha
from ..model import parse_sce_response

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


def evaluate(folder, out):
    started = perf_counter(); folder, out = Path(folder).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'): raise ValueError('Fresh ignored evaluation output required')
    manifest, protocol = verify(folder)
    relative = str(TRUTH.relative_to(ROOT))
    if manifest['source_sha256'].get(relative) != sha(TRUTH): raise ValueError('Pinned evaluation truth required')
    truth = {(r['month'], r['agent_id'], r['repeat']): r['real'] for r in read_json(TRUTH)}
    links = read_json(folder/'evaluation_links_private.json')
    actions = {}; cost = 0.; coverage = {a: Counter() for a in protocol['arms']}
    for job in manifest['jobs']:
        audit = ROOT/'outputs/local_runs'/job['run_id']; receipt = read_json(audit/'run_manifest.json')
        if receipt['status'] != 'completed' or receipt['llm_kind'] != 'openai' or receipt['protocol_sha256'] != manifest['protocol_sha256']:
            raise ValueError('Complete real run required; engineering outputs are not experiments')
        previews = read_json(folder/str(job['month'])/f"prompts_{job['arm']}.json")['rows']
        calls = [json.loads(line) for line in (audit/'llm_calls.jsonl').read_text().splitlines() if line]
        if len(calls) != protocol['n_per_month'] or len({c['agent_id'] for c in calls}) != len(calls):
            raise ValueError('One audited call per person required')
        calls = {c['agent_id']: c for c in calls}
        if set(calls) != set(previews): raise ValueError('Call/preview roster mismatch')
        db = duckdb.connect(str(audit/'study.duckdb'), read_only=True)
        try: rows = db.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall()
        finally: db.close()
        if len(rows) != protocol['n_per_month'] or len({aid for aid, _ in rows}) != len(rows): raise ValueError('Incomplete action roster')
        for aid, payload in rows:
            payload = json.loads(payload) if isinstance(payload, str) else payload
            call = calls[aid]; raw = call.get('raw_response_text') or ''
            if (call['prompt_sha256'] != previews[aid]['prompt_sha256'] or call['prompt_text'] != json.dumps(previews[aid]['messages'], ensure_ascii=False)
                    or call['raw_response_sha256'] != hashlib.sha256(raw.encode()).hexdigest()
                    or call['attempt_idx'] != 0 or payload.get('actual_messages_sha256') != previews[aid]['prompt_sha256']):
                raise ValueError('Input/reply audit mismatch')
            parsed, error = parse_sce_response(raw)
            if parsed is not None and any(abs(float(payload[f'q9_bin{i+1}'])-parsed['bins'][i]) > 1e-9 for i in range(10)):
                raise ValueError('Raw reply/action probabilities differ')
            if parsed is not None and abs(float(payload['point_pct'])-parsed['point_pct']) > 5e-5:
                raise ValueError('Raw reply/action point differs')
            bins = [payload[f'q9_bin{i}'] for i in range(1, 11)]
            score = score_bins(tuple(bins)) if payload['validation_status'] == 'valid' else {'mean': None, 'iqr': None, 'zero_deflation': None}
            actions[job['month'], job['repeat'], aid, job['arm']] = {**score, 'q9_bins': bins,
                'point': payload['point_pct'] if parsed is not None else None, 'validation_status': payload['validation_status']}
            coverage[job['arm']][payload['validation_status']] += 1
        cost += receipt['cost']['estimated_cost_usd']
    cases = []
    for link in links:
        for repeat in protocol['generation_repeats']:
            m, aid = link['month'], link['agent_id']
            cases.append({**link, 'repeat': repeat, 'survey_weight': link['design_survey_weight'],
                'real': truth[m, aid, repeat], 'arms': {arm: actions[m, repeat, aid, arm] for arm in protocol['arms']}})
    arms, months, repeats = protocol['arms'], protocol['months'], protocol['generation_repeats']
    support9 = shared._common_person_months(cases, arms, repeats, 'q9')
    support8 = shared._common_person_months(cases, arms, repeats, 'q8')
    summaries = {arm: shared._summarize_arm(cases, arm, months, repeats, support9, support8) for arm in arms}
    expected = protocol['n_per_month']*len(months)*len(repeats)
    valid = all(coverage[arm]['valid']/expected >= .99 for arm in arms)
    scorable = {arm: sum(shared.finite(r['arms'][arm].get('mean')) and shared.finite(r['arms'][arm].get('iqr')) for r in cases) for arm in arms}
    valid = valid and all(n/expected >= .99 for n in scorable.values())
    result = {'status': 'completed_frozen_block_evaluation', 'protocol': protocol,
        'new_api_calls': 0, 'estimated_actual_cost_usd': cost, 'coverage': {k: dict(v) for k, v in coverage.items()},
        'common_q9_person_months': len(support9), 'common_q8_person_months': len(support8), 'scorable_counts': scorable,
        'arms': summaries, 'primary_view': 'auxiliary_survey_weighted: its survey_weight is frozen design-survey weight here.',
        'paired_intervals': paired_intervals(cases, arms, months, repeats, support9) if valid else None,
        'accuracy_descriptive_only': not valid, 'automatic_upgrade': False,
        'evaluation_seconds': perf_counter()-started, 'scorer_cache_distinct_vectors': score_bins.cache_info().currsize,
        'notes': ['No correction of invalid replies. Human scores are reused from frozen evaluation; new model vectors use the same scorer.',
                  'All-arm/both-repeat common support; macro and individual metrics are distinct; repeats are not extra people.']}
    out.mkdir(parents=True); dump(out/'summary.json', result); dump(out/'cases_private.json', cases)
    return result
