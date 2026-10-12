"""Three-arm offline analysis, separate from lifetime simulation providers."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from .confidence_trial import MONTHS, check_frozen, sha, dump
from .lifetime_experiment import ARMS
from .household_state_analysis import density
from .monthly_analysis import weighted_summary
from .news_exposure_analysis import describe, finite, statistics
from .scoring.sce_q9_frozen import provenance

CONTRASTS = ((ARMS[2], ARMS[0]), (ARMS[1], ARMS[0]), (ARMS[2], ARMS[1]))
SCORE_KEYS = ('median_absolute_error_pp', 'distribution_W1_pp', 'IQR_absolute_gap_pp')


def metrics(rows, point=False, bootstrap=1000):
    common = [r for r in rows if all(finite(r.get(k)) for k in ('real',)+ARMS)]
    real = np.asarray([r['real'] for r in common])
    preds = {a: np.asarray([r[a] for r in common]) for a in ARMS}
    result = {'n_selected': len(rows), 'n_common': len(common), 'n_excluded': len(rows)-len(common),
              'estimand': 'equal-weight common age-balanced diagnostic sample, not national headline',
              'real': describe(real, point), 'arms': {}, 'contrasts': {}}
    for arm in ARMS:
        result['arms'][arm] = statistics(preds[arm], real, point)
        ages = sorted({r['profile']['age_group'] for r in common})
        result['arms'][arm]['age_groups_descriptive'] = {g: statistics(
            [r[arm] for r in common if r['profile']['age_group'] == g],
            [r['real'] for r in common if r['profile']['age_group'] == g], point) for g in ages}
        weighted = [r for r in common if finite(r.get('weight')) and r['weight'] > 0]
        if weighted:
            w = [r['weight'] for r in weighted]
            sw = weighted_summary([r[arm] for r in weighted], w, interpolate_median=point)
            rw = weighted_summary([r['real'] for r in weighted], w, interpolate_median=point)
            result['arms'][arm]['weighted_auxiliary'] = {'simulated': sw, 'real': rw,
                'median_absolute_error_pp': abs(sw['weighted_median_pp']-rw['weighted_median_pp'])}
    if not common:
        return result
    intervals = {(a,b,k): [] for a,b in CONTRASTS for k in SCORE_KEYS}
    rng = np.random.default_rng(42)
    for indices in rng.integers(0, len(common), size=(bootstrap,len(common))):
        s = {a: statistics(preds[a][indices], real[indices], point) for a in ARMS}
        for a,b,k in intervals:
            intervals[a,b,k].append(s[a][k]-s[b][k])
    for a,b in CONTRASTS:
        result['contrasts'][f'{a}_minus_{b}'] = {
            k: {'change_pp': result['arms'][a][k]-result['arms'][b][k],
                'paired_person_bootstrap_95_interval_pp': np.quantile(intervals[a,b,k],[.025,.975]).tolist() if bootstrap else None}
            for k in SCORE_KEYS}
        result['contrasts'][f'{a}_minus_{b}']['average_response_shift_pp'] = float(np.mean(preds[a]-preds[b]))
    result['bootstrap_scope'] = 'fixed assigned P/E/history, people only; no population or time generalization'
    return result


def point_value(payload):
    """Q9-only arithmetic failure does not erase a parsed, legal Q8 answer."""
    valid_q8 = payload.get('validation_status') == 'valid' or (
        payload.get('validation_status') == 'invalid' and
        str(payload.get('llm',{}).get('error','')).startswith('q9_'))
    return payload.get('point_pct') if valid_q8 and finite(payload.get('point_pct')) else None


def analyze(root, trial, truth_dir, out):
    root, trial, truth_dir, out = (Path(p).resolve() for p in (root,trial,truth_dir,out))
    if out.exists() or not out.is_relative_to(root/'outputs'):
        raise ValueError('fresh ignored analysis directory required')
    plan = json.loads((trial/'trial_manifest.json').read_text())
    if plan['status'] != 'completed_pending_analysis' or len(plan['jobs']) != 24 or any(j.get('exit_code') != 0 for j in plan['jobs']):
        raise ValueError('all 24 completed real cells required')
    check_frozen(root, trial, plan)
    scorer = provenance()
    if not scorer['live_matches_pinned']:
        raise ValueError('frozen scorer drift')
    receipt = json.loads((truth_dir/'receipt.json').read_text())
    if sha(truth_dir/'raw_reference.parquet') != receipt['parquet_sha256'] or sha(root/receipt['source']) != receipt['source_sha256']:
        raise ValueError('evaluation truth drift')
    data = pd.read_parquet(truth_dir/'raw_reference.parquet')
    truth = {(str(int(r['date'])),f"sce_u{int(r['userid'])}"):r for r in data.to_dict('records')}
    links = json.loads((trial/'evaluation_links_private.json').read_text())
    result = {'status':'completed_offline_analysis','scorer':scorer,'truth_receipt':receipt,
        'trial':str(trial.relative_to(root)), 'trial_manifest_sha256':sha(trial/'trial_manifest.json'),
        'months':{},'runs':[],'actual_calls':0,'conservative_cost_usd':0.,'not_vendor_invoice':True,
        'new_analysis_api_calls':0,'evaluation':plan['preregistered_evaluation'],'limits':plan['limitations']}
    private = []
    for month in MONTHS:
        monthly_links = [r for r in links if r['month'] == month]
        ids = {r['agent_id'] for r in monthly_links}
        if len(ids) != 12 or len(monthly_links) != 12 or any((month,r['source_agent_id']) not in truth for r in monthly_links):
            raise ValueError('exact selected sample truth coverage; no substitution')
        profiles = {p['agent_id']:p['attributes'] for p in json.loads((trial/month/'population.json').read_text())['personas']}
        result['months'][month] = {'metadata':plan['metadata'][month],'repeats':{}}
        full = data[data.date.astype(int) == int(month)]
        result['months'][month]['full_month_auxiliary_reference'] = {
            'Q9':weighted_summary(full.Q9_mean,full.weight),
            'Q8':weighted_summary(full.Q8v2part2,full.weight,interpolate_median=True),
            'note':'published derived micro values; auxiliary, not primary balanced-sample truth or rerun score'}
        for repeat in (1,2):
            answers = {}
            for arm in ARMS:
                job = next(j for j in plan['jobs'] if (j['month'],j['arm'],j['repeat']) == (month,arm,repeat))
                run = root/'outputs/local_runs'/job['run_id']
                manifest = json.loads((run/'run_manifest.json').read_text())
                if manifest['llm_kind'] != 'openai' or manifest['n_agents'] != 12 or manifest['execution_purpose'] != 'lifetime_behaviour_trial':
                    raise ValueError('wrong real run identity')
                for name,h in manifest['effective_artifact_sha256'].items() | manifest['source_snapshot_sha256'].items():
                    if sha(run/name) != h:
                        raise ValueError('execution source/effective input drift')
                    if name.startswith('source_snapshot/study/'):
                        frozen = plan['code_sha256'].get('studies/sce_inflation_expectations/'+name.removeprefix('source_snapshot/study/'))
                        if frozen and h != frozen:
                            raise ValueError('executed study differs from frozen code')
                if manifest['source_snapshot_sha256']['source_snapshot/run_sce_local.py'] != plan['code_sha256']['scripts/run_sce_local.py']:
                    raise ValueError('executed entry differs from frozen code')
                calls = [json.loads(line) for line in (run/'llm_calls.jsonl').read_text().splitlines()]
                previews = {p['agent_id']:p for p in json.loads((trial/month/f'preview_{arm}.json').read_text())}
                if len(calls) != 12 or {c['agent_id'] for c in calls} != ids:
                    raise ValueError('actual call count/roster')
                for call in calls:
                    if call['attempt_idx'] != 0 or call['requested_model'] != plan['model'] or call['temperature'] != .5 or call['prompt_text'] != json.dumps(previews[call['agent_id']]['messages'],ensure_ascii=False):
                        raise ValueError('actual prompt/model/temperature differs')
                    if call['prompt_sha256'] != previews[call['agent_id']]['prompt_sha256'] or hashlib.sha256((call['raw_response_text'] or '').encode()).hexdigest() != call['raw_response_sha256']:
                        raise ValueError('actual prompt/response hash mismatch')
                with duckdb.connect(manifest['store_path'],read_only=True) as db:
                    raw = db.execute("SELECT agent_id,action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall()
                if len(raw) != 12 or {aid for aid,_ in raw} != ids:
                    raise ValueError('trajectory roster')
                answers[arm] = {aid:json.loads(payload) if isinstance(payload,str) else payload for aid,payload in raw}
                ledger = json.loads((run/'cost_ledger.json').read_text())
                result['actual_calls'] += len(calls)
                result['conservative_cost_usd'] += ledger['estimated_cost_usd']
                result['runs'].append({'month':month,'arm':arm,'repeat':repeat,'calls':len(calls),
                    'estimated_cost_usd':ledger['estimated_cost_usd'],'input_tokens':ledger['total_prompt_tokens'],
                    'output_tokens':ledger['total_completion_tokens'],'returned_models':dict(Counter(c['returned_model'] for c in calls)),
                    'validation_counts':dict(Counter(p['validation_status'] for p in answers[arm].values())),
                    'llm_calls_sha256':sha(run/'llm_calls.jsonl'),'store_sha256':sha(Path(manifest['store_path']))})
            rows = {q:[] for q in ('Q9','Q8','personal_uncertainty','raw_deflation_probability')}
            fits_count = Counter()
            for link in monthly_links:
                aid = link['agent_id']
                actual = truth[month,link['source_agent_id']]
                bins = {'real':[actual[f'Q9_bin{i}'] for i in range(1,11)]}
                bins.update({a:[answers[a][aid][f'q9_bin{i}'] for i in range(1,11)] if answers[a][aid]['validation_status']=='valid' else [None]*10 for a in ARMS})
                fits = {a:density(v) for a,v in bins.items()}
                fits_count.update(f'{a}:{v["status"]}' for a,v in fits.items())
                base = {'agent_id':aid,'profile':profiles[aid],'weight':actual['weight']}
                for q,f in (('Q9','mean'),('personal_uncertainty','iqr')):
                    rows[q].append({**base,**{a:v[f] for a,v in fits.items()}})
                rows['Q8'].append({**base,'real':actual['Q8v2part2'],**{a:point_value(answers[a][aid]) for a in ARMS}})
                rows['raw_deflation_probability'].append({**base,**{a:sum(v[5:]) if all(finite(x) for x in v) and abs(sum(v)-100)<=.5 else None for a,v in bins.items()}})
            cell = {q:metrics(rr,point=q=='Q8') for q,rr in rows.items()}
            cell['fit_status_counts'] = dict(fits_count)
            result['months'][month]['repeats'][str(repeat)] = cell
            private.extend({'month':month,'repeat':repeat,'measure':q,**r} for q,rr in rows.items() for r in rr)
    result['across_months_by_repeat'] = {}
    for repeat in (1,2):
        entry = {}
        for q in ('Q9','Q8'):
            cells = [result['months'][m]['repeats'][str(repeat)][q] for m in MONTHS]
            entry[q] = {}
            for arm in ARMS:
                entry[q][arm] = {}
                for key in SCORE_KEYS:
                    values = [c['arms'][arm][key] for c in cells]
                    entry[q][arm][key] = float(np.mean(values)) if all(finite(x) for x in values) else None
            entry[q]['matched_months_both_improve'] = sum(all(finite(c['arms'][a][k]) for a in (ARMS[0],ARMS[2]) for k in SCORE_KEYS[:2]) and all(c['arms'][ARMS[2]][k]<c['arms'][ARMS[0]][k] for k in SCORE_KEYS[:2]) for c in cells)
        result['across_months_by_repeat'][str(repeat)] = entry
    result['candidate_continue_gate_passed'] = all(
        result['across_months_by_repeat'][str(r)]['Q9']['matched_months_both_improve']>=3 and
        all(finite(result['across_months_by_repeat'][str(r)]['Q9'][a][k]) for a in (ARMS[0],ARMS[2]) for k in SCORE_KEYS[:2]) and
        all(result['across_months_by_repeat'][str(r)]['Q9'][ARMS[2]][k]<result['across_months_by_repeat'][str(r)]['Q9'][ARMS[0]][k] for k in SCORE_KEYS[:2]) for r in (1,2))
    if result['actual_calls'] != 288 or result['conservative_cost_usd']>plan['proposed_simulation_cap_usd']:
        raise ValueError('overall call or cost limit')
    out.mkdir()
    dump(out/'summary.json',result)
    dump(out/'paired_evaluation_private.json',private)
    return result


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trial',type=Path,required=True)
    p.add_argument('--truth',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args(argv)
    result = analyze(Path(__file__).resolve().parents[2],args.trial,args.truth,args.out)
    print(json.dumps({k:result[k] for k in ('actual_calls','conservative_cost_usd','across_months_by_repeat','candidate_continue_gate_passed')}))
