"""Reusable aggregate readout of a completed two-arm frozen-prompt trial.

Only uses existing scored trajectories. Does not call an API or refit Q9.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import numpy as np
from scipy.stats import wasserstein_distance

from ..experiments.frozen_batch import ROOT, read_json, dump, sha, verify
from .cognition import _common_person_months


def median(x, w):
    x, w = np.asarray(x), np.asarray(w)
    order = np.argsort(x, kind='stable')
    return float(x[order][np.searchsorted(np.cumsum(w[order]), .5*w.sum(), side='left')])


def report(folder, evaluation, out):
    folder, evaluation, out = map(lambda p: Path(p).resolve(), (folder, evaluation, out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'): raise ValueError('New ignored report directory required')
    manifest, protocol = verify(folder); result = read_json(evaluation/'summary.json')
    if len(protocol['arms']) != 2 or result['protocol'] != protocol: raise ValueError('Complete matching two-arm trial required')
    cases = read_json(evaluation/'cases_private.json'); arms = protocol['arms']
    support = _common_person_months(cases, arms, protocol['generation_repeats'], 'q9')
    cells, verified = [], 0
    for month in protocol['months']:
        for repeat in protocol['generation_repeats']:
            rows = [r for r in cases if r['month']==month and r['repeat']==repeat and (month, r['userid']) in support]
            w = np.array([r['survey_weight'] for r in rows]); y = np.array([r['real']['q9_mean'] for r in rows])
            previous = np.array([r['real']['previous_q9_mean'] for r in rows]); truth_delta = y-previous
            cell = {'month':month, 'repeat':repeat, 'n':len(rows), 'effective_n':float(w.sum()**2/(w@w)),
                    'maximum_weight_share':float(w.max()/w.sum()), 'truth_center_pp':median(y,w), 'arms':{}}
            for arm in ['carry', *arms]:
                prediction = previous if arm=='carry' else np.array([r['arms'][arm]['mean'] for r in rows])
                delta = prediction-previous; stable = np.abs(truth_delta)<=.5; moving = ~stable
                val = {'center_mae_pp':abs(median(prediction,w)-median(y,w)), 'center_bias_pp':median(prediction,w)-median(y,w),
                       'personal_mae_pp':float(np.average(np.abs(prediction-y),weights=w)),
                       'w1_pp':float(wasserstein_distance(prediction,y,w,w)),
                       'wrong_move_given_true_stable':float(np.average(np.abs(delta[stable])>.5,weights=w[stable])) if stable.any() else None,
                       'missed_move_given_true_moving':float(np.average(np.abs(delta[moving])<=.5,weights=w[moving])) if moving.any() else None,
                       'opposite_direction_given_true_moving':float(np.average((delta[moving]*truth_delta[moving]<0)&(np.abs(delta[moving])>.5),weights=w[moving])) if moving.any() else None}
                cell['arms'][arm]=val
                if arm!='carry':
                    original=next(c for c in result['arms'][arm]['auxiliary_survey_weighted']['q9']['cells'] if c['month']==month and c['repeat']==repeat)
                    for left,right in [('center_mae_pp','q9_center_mae_pp'),('personal_mae_pp','individual_density_mean_mae_pp'),('w1_pp','cross_section_w1_pp')]:
                        if abs(val[left]-original[right])>1e-8: raise ValueError('Independent aggregate check failed')
                        verified+=1
            cells.append(cell)
    aggregate={arm:{k:float(np.mean([c['arms'][arm][k] for c in cells if c['arms'][arm][k] is not None]))
                    for k in cells[0]['arms'][arm]} for arm in ['carry',*arms]}
    monthly=[{'month':month, 'n':next(c['n'] for c in cells if c['month']==month),
              'effective_n':next(c['effective_n'] for c in cells if c['month']==month),
              'arms':{arm:{k:float(np.mean([c['arms'][arm][k] for c in cells if c['month']==month and c['arms'][arm][k] is not None]))
                           for k in cells[0]['arms'][arm]} for arm in ['carry',*arms]}} for month in protocol['months']]
    run_receipts=[]; returned=set(); temperatures=set()
    for job in manifest['jobs']:
        directory=ROOT/'outputs/local_runs'/job['run_id']; receipt=read_json(directory/'run_manifest.json')
        if receipt['status']!='completed' or receipt['cost']['call_count']!=protocol['n_per_month']: raise ValueError('Incomplete real job')
        run_receipts.append(receipt)
        for line in (directory/'llm_calls.jsonl').read_text().splitlines():
            call=json.loads(line); returned.add(str(call.get('returned_model'))); temperatures.add(call.get('temperature'))
    cost=sum(r['cost']['estimated_cost_usd'] for r in run_receipts)
    if cost>protocol['budget_cap_usd'] or sum(r['cost']['call_count'] for r in run_receipts)!=protocol['planned_calls']:
        raise ValueError('Cost or call count mismatch')
    start=min(r['started_at_utc'] for r in run_receipts); end=max(r['finished_at_utc'] for r in run_receipts)
    wins=sum(m['arms'][arms[1]]['center_mae_pp']<m['arms'][arms[0]]['center_mae_pp'] for m in monthly)
    passed=(not result['accuracy_descriptive_only'] and aggregate[arms[1]]['center_mae_pp']<aggregate[arms[0]]['center_mae_pp']
            and wins>=int(np.ceil(2*len(monthly)/3)) and aggregate[arms[1]]['w1_pp']<=aggregate[arms[0]]['w1_pp'])
    output={'status':'completed_frozen_trial_aggregate_readout','protocol_sha256':manifest['protocol_sha256'],
        'common_person_months':len(support),'planned_and_actual_calls':protocol['planned_calls'],'estimated_cost_usd_not_bill':cost,
        'cap_usd':protocol['budget_cap_usd'],'started_at_utc':start,'finished_at_utc':end,
        'parallel_job_window_seconds':(datetime.fromisoformat(end)-datetime.fromisoformat(start)).total_seconds(),
        'returned_model_ids':sorted(returned),'request_temperatures':sorted(temperatures),'automatic_retries':0,
        'weighted_metrics':aggregate,'weighted_monthly':monthly,
        'unweighted_metrics':{a:result['arms'][a]['q9']['aggregate_equal_month_repeat_cells'] for a in arms},
        'paired_intervals':result['paired_intervals'],'monthly_center_wins':wins,'pilot_screen_passed':passed,'automatic_upgrade':False,
        'independent_numeric_checks':verified,'new_api_calls_from_reporting':0,'new_q9_fits_from_reporting':0,
        'group_definition':'True and predicted movement use +/-0.5pp; opposite-direction errors require both to exceed that threshold with opposing signs. Post-hoc evaluation only. Conditional rates equally average nonempty month/repeat cells.',
        'pilot_screen_rule':'Center MAE improves, center improves in at least ceil(2/3 * months) months and W1 does not worsen; screening only, never automatic promotion.',
        'source_sha256':{str((evaluation/name).relative_to(ROOT)):sha(evaluation/name) for name in ('summary.json','cases_private.json')}}
    out.mkdir(parents=True);dump(out/'summary.json',output)
    return output
