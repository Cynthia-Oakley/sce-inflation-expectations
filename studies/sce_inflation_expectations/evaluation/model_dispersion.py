"""Cached, common-support dispersion checks; no inference of memorization."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from .metrics import quantile


def moments(values, weights, center):
    x, w = np.asarray(values, float), np.asarray(weights, float)
    if not len(x) or x.shape != w.shape or not np.isfinite(x).all() or not np.isfinite(w).all() or (w <= 0).any():
        raise ValueError('Matched finite values and positive weights required')
    w = w / w.sum()
    mean = float(w @ x)
    var = float(w @ ((x - mean) ** 2))
    return dict(mean_pp=mean, variance_pp2=var, std_pp=float(np.sqrt(var)),
                median_pp=quantile(x, w, .5), iqr_pp=quantile(x, w, .75)-quantile(x, w, .25),
                p05_pp=quantile(x, w, .05), p95_pp=quantile(x, w, .95),
                share_within_half_pp_of_human_center=float(w @ (abs(x-center) <= .5)),
                share_within_one_pp_of_human_center=float(w @ (abs(x-center) <= 1.)))


def analyze(cases, official_centers=None):
    arms = sorted(cases[0]['arms'])
    repeats = sorted({r['repeat'] for r in cases})
    if repeats != [1, 2]:
        raise ValueError('This descriptive decomposition requires two existing repeats')
    lookup = {(r['month'], r['agent_id'], r['repeat']): r for r in cases}
    if len(lookup) != len(cases):raise ValueError('Duplicate person-month-repeat')
    monthly = []
    for month in sorted({r['month'] for r in cases}):
        pairs = []
        for r in cases:
            if r['month'] != month or r['repeat'] != 1:continue
            b = lookup.get((month, r['agent_id'], 2))
            if b is None:continue
            values = [z['real'].get('q9_mean') for z in (r, b)]
            values += [z['arms'][a].get('mean') for z in (r, b) for a in arms]
            values += [r['real'].get('previous_q9_mean')]
            if not all(v is not None and np.isfinite(v) for v in values):continue
            if r['real'] != b['real'] or r['design_survey_weight'] != b['design_survey_weight']:
                raise ValueError('Truth and design weights must be constant across repeats')
            pairs.append((r, b))
        if len(pairs) < 2:raise ValueError('Every month needs at least two common people')
        w = np.array([a['design_survey_weight'] for a,b in pairs], float)
        y = np.array([a['real']['q9_mean'] for a,b in pairs], float)
        center = quantile(y, w, .5)
        metrics = {'human': moments(y, w, center),
                   'carry': moments([a['real']['previous_q9_mean'] for a,b in pairs], w, center)}
        noise = {}
        wn = w/w.sum()
        for arm in arms:
            x = np.array([[a['arms'][arm]['mean'], b['arms'][arm]['mean']] for a,b in pairs])
            r1, r2 = (moments(x[:,i], w, center) for i in (0,1))
            metrics[arm] = {k:float((r1[k]+r2[k])/2) for k in r1}
            within = float(wn @ ((x[:,0]-x[:,1])**2) / 2)
            means = x.mean(axis=1)
            between = float(wn @ ((means-wn @ means)**2))
            adjusted = between-within/2
            noise[arm] = dict(mean_absolute_repeat_gap_pp=float(wn @ abs(x[:,0]-x[:,1])),
                within_person_generation_variance_pp2=within,
                variance_of_person_repeat_means_pp2=between,
                noise_adjusted_between_variance_pp2=adjusted,
                generation_noise_fraction=within/(adjusted+within) if adjusted+within > 0 else None)
        entry=dict(month=month, person_months=len(pairs), weight_ess=float(w.sum()**2/(w@w)),
                   human_center_pp=center, metrics=metrics, repeat_diagnostics=noise)
        if official_centers is not None:
            national=official_centers[month]
            concentration={a:float(np.mean([moments([z['arms'][a]['mean'] for z in repeat_rows],w,national)
                ['share_within_half_pp_of_human_center'] for repeat_rows in ([r for r,b in pairs],[b for r,b in pairs])])) for a in arms}
            concentration['human']=moments(y,w,national)['share_within_half_pp_of_human_center']
            concentration['carry']=moments([a['real']['previous_q9_mean'] for a,b in pairs],w,national)['share_within_half_pp_of_human_center']
            entry.update(official_national_center_pp=national,share_within_half_pp_of_official_center=concentration)
        monthly.append(entry)
    names=['human','carry',*arms]
    means={a:{k:float(np.mean([r['metrics'][a][k] for r in monthly]))
              for k in monthly[0]['metrics'][a]} for a in names}
    noise_means={a:{k:float(np.mean([r['repeat_diagnostics'][a][k] for r in monthly
                                  if r['repeat_diagnostics'][a][k] is not None]))
                   if any(r['repeat_diagnostics'][a][k] is not None for r in monthly) else None
                   for k in monthly[0]['repeat_diagnostics'][a]} for a in arms}
    return dict(months=[r['month'] for r in monthly], common_person_months=sum(r['person_months'] for r in monthly),
                monthly=monthly, equal_month_metrics=means, repeat_equal_month_means=noise_means,
                official_center_concentration_equal_month_means={a:float(np.mean([r['share_within_half_pp_of_official_center'][a] for r in monthly]))
                    for a in names} if official_centers is not None else None,
                units={'variance':'percentage points squared','std':'percentage points','shares':'fraction'},
                center='Same-person current human Q9 density-mean median, not the official national headline',
                aggregation='Design-weighted within month; average statistics over two repeats, then equal months',
                memorization_test=False, limits=[
                    'A larger variance cannot rule out memorized headlines, distributions or related macro facts.',
                    'A small variance or central clustering cannot establish memorization; shared information can also cause it.',
                    'Between-person spread, within-person generation noise and subjective Q9 uncertainty are distinct.',
                    'Only two repeats; variance subtraction is descriptive and may be negative.',
                    'Same inputs change both served model and provider; this is not a parameter-count-only experiment.'])


def run(source, out, official_chart=None):
    source, out=Path(source).resolve(),Path(out).resolve()
    if out.exists():raise ValueError('Fresh output required')
    official=None
    if official_chart:
        from openpyxl import load_workbook
        wb=load_workbook(official_chart,read_only=True,data_only=True)
        official={int(r[0]):float(r[1]) for r in wb['Inflation expectations'].iter_rows(min_row=5,values_only=True)
                  if isinstance(r[0],(int,float)) and r[1] is not None};wb.close()
    result=analyze(json.loads(source.read_text()),official)
    result.update(status='cached_common_support_model_dispersion',new_api_calls=0,scorer_calls=0,
                  completed_at_utc=datetime.now(timezone.utc).isoformat(),
                  source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    if official_chart:result['official_chart_sha256']=hashlib.sha256(Path(official_chart).read_bytes()).hexdigest()
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return result
