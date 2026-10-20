#!/usr/bin/env python3
"""Procurement contrasts on cached normalized scores; no API or new density fits."""
import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
import sys
from time import perf_counter

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import verify, read_json, dump, sha
from studies.sce_inflation_expectations.evaluation import cognition as shared
from studies.sce_inflation_expectations.evaluation.temperature import dispersion_readout
from scripts.report_sce_information_exposure import cell_metrics


def summarize(cells, arms):
    return {a:shared._aggregate_cells([c['arms'][a] for c in cells],tuple(cells[0]['arms'][a]))[0] for a in arms}


def report(folder, evaluation, out):
    started = perf_counter(); folder, evaluation, out = map(lambda p: p.resolve(), (folder, evaluation, out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored report required')
    manifest, protocol = verify(folder); scored = read_json(evaluation/'summary.json')
    if scored['protocol'] != protocol or protocol.get('q9_postprocessing') != 'proportional_nonnegative_v1':
        raise ValueError('Completed matching normalized procurement evaluation required')
    cases = read_json(evaluation/'cases_private.json')
    variants = protocol['arms']; months = protocol['months']; repeats = protocol['generation_repeats']
    support = shared._common_person_months(cases, variants, repeats, 'q9')
    truth_path = ROOT/protocol['evaluation_truth']
    historical = {(r['month'],r['agent_id'],r['repeat']):r['baselines'] for r in read_json(truth_path)}
    arms = ['carry','history_anchor_half',*variants]

    def cell(rows, month, repeat):
        y = np.array([r['real']['q9_mean'] for r in rows]); prev = np.array([r['real']['previous_q9_mean'] for r in rows])
        w = np.array([r['survey_weight'] for r in rows])
        predictions = {a:np.array([r['arms'][a]['mean'] for r in rows]) for a in variants}
        predictions['carry'] = prev
        predictions['history_anchor_half'] = np.array([historical[month,r['agent_id'],repeat]['history_anchor_half'] for r in rows])
        if not np.isfinite(prev).all() or not np.isfinite(predictions['history_anchor_half']).all():
            raise ValueError('Baselines must use the same complete support')
        return {'month':month,'repeat':repeat,'n':len(rows),'effective_n':float(w.sum()**2/(w@w)),
                'maximum_weight_share':float(w.max()/w.sum()),
                'arms':{a:cell_metrics(y,prev,p,w) for a,p in predictions.items()}}

    def cells_for(selected_cases, selected_support):
        result = []
        for month in months:
            for repeat in repeats:
                rows = shared._cell_rows(selected_cases,month,repeat,selected_support)
                if rows: result.append(cell(rows,month,repeat))
        return result

    cells = cells_for(cases,support)
    if len(cells) != len(months)*len(repeats): raise ValueError('Complete common support required')
    aggregate = summarize(cells,arms); checks = 0
    for c in cells:
        for arm in variants:
            ref = next(r for r in scored['arms'][arm]['auxiliary_survey_weighted']['q9']['cells']
                       if r['month']==c['month'] and r['repeat']==c['repeat'])
            for left,right in [('center_mae_pp','q9_center_mae_pp'),('personal_mae_pp','individual_density_mean_mae_pp'),('w1_pp','cross_section_w1_pp')]:
                if abs(c['arms'][arm][left]-ref[right]) > 1e-8: raise ValueError('Shared aggregation mismatch')
                checks += 1
    monthly = [{'month':m,'n':next(c['n'] for c in cells if c['month']==m),
                'arms':summarize([c for c in cells if c['month']==m],arms)} for m in months]
    generation = {str(r):summarize([c for c in cells if c['repeat']==r],arms) for r in repeats}
    contrast = {'difference':{k:aggregate['matched_role'][k]-aggregate['shuffled_role'][k]
                             if shared.finite(aggregate['matched_role'][k]) and shared.finite(aggregate['shuffled_role'][k]) else None
                             for k in aggregate['matched_role']},
                'person_cluster_interval95_from_shared_evaluator':scored['paired_intervals'],
                'monthly_w1_nonworse':sum(m['arms']['matched_role']['w1_pp']<=m['arms']['shuffled_role']['w1_pp'] for m in monthly),
                'leave_one_month_out_w1_difference':{str(m):float(np.mean([c['arms']['matched_role']['w1_pp']-c['arms']['shuffled_role']['w1_pp'] for c in cells if c['month']!=m])) for m in months}}
    interval = (scored.get('paired_intervals') or {}).get('intervals') or {}
    w1_ci = interval.get('cross_section_w1_pp')
    passed = bool(not scored['accuracy_descriptive_only'] and w1_ci and w1_ci[1]<0
                  and aggregate['matched_role']['delta_w1_pp']<=aggregate['shuffled_role']['delta_w1_pp'])

    # Selection sensitivity: use the SAME derived scores, restricted to original
    # valid replies in every arm/repeat. Do not pretend this is a new raw fit.
    raw_support = {(m,u) for m,u in support if all(r['arms'][a]['raw_validation_status']=='valid'
        for r in cases if (r['month'],r['userid'])==(m,u) for a in variants)}
    raw_cells = cells_for(cases,raw_support)
    sensitivity = {'label':'Raw-valid-support selection sensitivity using the same normalized scores',
        'common_person_months':len(raw_support),'excluded_from_main_support':len(support-raw_support),
        'cells_used':len(raw_cells),'weighted_metrics':summarize(raw_cells,arms) if raw_cells else None,
        'note':'Different sample support; not a correction-effect estimate or unnormalized fit of invalid probabilities.'}
    groups = {}
    for feature in ['age_group','education_group','numeracy','region']:
        groups[feature] = {}
        for label in sorted({str(r['profile'].get(feature)) for r in cases}):
            subset = [r for r in cases if str(r['profile'].get(feature))==label]
            sg = {(r['month'],r['userid']) for r in subset}&support
            gc = [c for c in cells_for(subset,sg) if c['n']>=3]
            if gc: groups[feature][label]={'person_months':len(sg),'cells_used':len(gc),'min_cell_n':min(c['n'] for c in gc),
                'sparse_months_below_8':[m for m in months if sum(r['repeat']==repeats[0] and r['month']==m and (m,r['userid']) in sg for r in subset)<8],
                'descriptive_only':True,'weighted_metrics':summarize(gc,arms)}
    dispersion = dispersion_readout(cases,protocol)
    dispersion['limits']='Only two generations; equal-person noise decomposition, not measured human repeat variability or a proof of accurate identities.'
    normalization_audit = {}
    normrows = read_json(evaluation/'q9_normalization_private.json')
    coverage_by_month_arm = []
    for month in months:
        for arm in variants:
            rows = [r for r in normrows if r['month'] == month and r['arm'] == arm]
            coverage_by_month_arm.append({'month': month, 'arm': arm,
                'attempted': len(rows),
                'interface_errors': sum(r['interface_error'] for r in rows),
                'usable': sum(r['derived_bins'] is not None for r in rows),
                'normalized': sum(r['applied'] for r in rows)})
    for arm in variants:
        rows = [r for r in normrows if r['arm']==arm]
        usable = [r for r in rows if r['derived_bins'] is not None]
        totals = [r['raw_sum'] for r in usable]
        histogram = Counter(str(round(v,6)) for v in totals)
        differences = [max(abs(x-y) for x,y in zip(r['raw_bins'],r['derived_bins'])) for r in usable]
        normalization_audit[arm] = {'responses':len(rows),'usable':len(usable),
            'normalized':sum(r['applied'] for r in rows),'normalized_fraction_of_all':sum(r['applied'] for r in rows)/len(rows),
            'raw_sum_range': [min(totals),max(totals)] if totals else None,
            'raw_sum_histogram_percent':dict(histogram),
            'largest_single_bin_adjustment_probability_pp':max(differences) if differences else None}
    receipts = []; fee = 0.; counts = Counter(); spans = {}
    ledger_path=ROOT/scored['call_ledger_source'] if scored.get('call_ledger_source') else None
    for job in manifest['jobs']:
        audit = ROOT/'outputs/local_runs'/job['run_id']
        if ledger_path is not None and not (audit/'run_manifest.json').exists():continue
        r = read_json(audit/'run_manifest.json'); receipts.append(r)
        phase = 'reused_gate' if job['run_id'] in protocol['reused_completed_jobs'] else 'new_main'
        spans.setdefault(phase,[]).append((r['started_at_utc'],r['finished_at_utc']))
        counts[phase+'_requests'] += r['cost']['call_count']
        for line in (audit/'llm_calls.jsonl').read_text().splitlines():
            c=__import__('json').loads(line);counts['api_errors']+=bool(c.get('error'));counts['automatic_retries']+=c['attempt_idx']>0
            if c.get('api_reported_cost_usd') is not None: fee+=c['api_reported_cost_usd'];counts['reported_cost_calls']+=1
    extra_calls=[]
    if ledger_path is not None:
        cached_calls=read_json(ledger_path/'existing_calls_private.json')
        extra_calls=[r['call'] for r in cached_calls.values() if not r['source_file'].startswith('outputs/local_runs/')]
        extra_calls += [__import__('json').loads(line) for line in (ledger_path/'new_calls_private.jsonl').read_text().splitlines()]
        for c in extra_calls:
            counts['api_errors']+=bool(c.get('error'));counts['automatic_retries']+=c['attempt_idx']>0
            if c.get('api_reported_cost_usd') is not None:fee+=c['api_reported_cost_usd'];counts['reported_cost_calls']+=1
        counts['resumed_same_client_requests']=len(extra_calls)
        counts['new_main_requests']+=len(extra_calls)
        spans['resumed_same_client']=[(c['timestamp_utc'],c['finished_at_utc']) for c in extra_calls]
    actual_calls = sum(r['cost']['call_count'] for r in receipts)+len(extra_calls)
    if actual_calls!=3456: raise ValueError('Total must include 144 reused +3312 new requests exactly once')
    cost = (read_json(ledger_path/'run_receipt.json')['combined_spent_or_reserved_usd'] if ledger_path is not None
            else sum(r['cost']['estimated_cost_usd'] for r in receipts))
    if cost>16 or fee>16: raise ValueError('Combined budget exceeded')
    durations = {phase:(datetime.fromisoformat(max(e for b,e in rows))-datetime.fromisoformat(min(b for b,e in rows))).total_seconds() for phase,rows in spans.items()}
    result = {'status':'completed_procurement_normalized_readout','protocol_sha256':manifest['protocol_sha256'],
        'common_person_months':len(support),'unique_respondents_on_support':len({r['userid'] for r in cases if (r['month'],r['userid']) in support}),
        'weighted_metrics':aggregate,'weighted_monthly':monthly,'weighted_cells':cells,'generation_sensitivity':generation,
        'primary_matched_minus_shuffled':contrast,'development_screen_passed':passed,'automatic_upgrade':False,
        'normalization':scored['q9_postprocessing'],'normalization_audit_by_arm':normalization_audit,
        'coverage_after_postprocessing':scored['coverage'],
        'coverage_by_month_arm':coverage_by_month_arm,
        'raw_valid_support_sensitivity':sensitivity,'group_metrics':groups,
        'q8_weighted_metrics':{a:scored['arms'][a]['auxiliary_survey_weighted']['q8']['aggregate_equal_month_repeat_cells'] for a in variants},
        'individual_density_metrics':{a:scored['arms'][a]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells'] for a in variants},
        'q9_center_rmse_pp':{a:float(np.sqrt(np.mean([c['arms'][a]['center_bias_pp']**2 for c in cells]))) for a in arms},
        'actual_calls_including_reused':actual_calls,'calls':dict(counts),'api_reported_cost_usd':fee,
        'estimated_or_reserved_cost_usd':cost,'cap_usd':16,'phase_model_api_spans_seconds':durations,
        'independent_aggregation_checks':checks,'new_api_calls_by_reporting':0,'new_density_fits_by_reporting':0,
        'accuracy_descriptive_only':scored['accuracy_descriptive_only'],
        'notes':['A-line conditional returner reconstruction; all six months were previously inspected development months.',
                 'Per-person-cluster intervals hold months fixed; not a time-generalization claim.',
                 'One role-allocation seed, two generations; repeated responses are not new people.',
                 'Original raw replies retained; registered proportional normalization applied identically to all arms.',
                 'Model/price-view mechanism are fixed across the three arms; no archived DeepSeek control is substituted.'],
        'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),evaluation/'summary.json',evaluation/'cases_private.json',truth_path]},
        'report_seconds':perf_counter()-started}
    if ledger_path is not None:
        result.update(call_ledger_source=str(ledger_path.relative_to(ROOT)),
            transport_provenance={'official_core_attempts':sum(r['cost']['call_count'] for r in receipts),
                'same_sce_client_ledger_attempts':len(extra_calls),
                'note':'Remaining never-attempted slots use the same client and frozen messages outside the Core loop. Failed requests stay missing, no retries.'},
            unreceived_request_billing_unknown=counts['api_errors']>0)
    out.mkdir();dump(out/'summary.json',result);dump(out/'repeat_variance.json',dispersion)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,required=True)
    p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=report(a.folder,a.evaluation,a.out)
    print({k:r[k] for k in ['common_person_months','weighted_metrics','development_screen_passed','api_reported_cost_usd']})
