"""Draft recent-B synthetic starting beliefs from the qualified old snapshot.

Reuses A's donor matching, bounded probability tilt and joint Q8/Q9 draw. The
old observation dates remain explicit. Only a PREVIOUS published national Q9
headline constrains the expected prior median; Q8 has no headline constraint.
This is an offline candidate, not a dispatch authorization or a measured panel.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import hashlib

import numpy as np
import pandas as pd

from .frozen_batch import ROOT, read_json, dump, sha
from .monthly_reconstruction_inputs import PastScoreCache
from ..population.entry_initialization import donor_candidates, calibrate, draw
from ..evaluation.metrics import distribution_summary

CACHE = ROOT/'outputs/sce_monthly_fine_full_truth_20261023_v3/scoring_cache_private.json'


def month_age(target, source):
    target,source = int(target),int(source)
    return (target//100-source//100)*12+target%100-source%100


def next_month(source):
    source = int(source); y,m = divmod(source,100)
    return (y+1)*100+1 if m==12 else y*100+m+1


def options_from_old_pool(past, selected, *, source_max_month):
    """The 1/3-month window is within the OLD SOURCE pool, not target lag one."""
    options=[]
    for recipient in selected:
        person=recipient['persona']
        subset,p0,meta=donor_candidates(past,next_month(source_max_month),person['attributes'],donor_type='unknown')
        meta.update(source_pool_reference_max=str(source_max_month),
                    window_semantics='1 or 3 months behind the archived source maximum; not recent months before the target')
        options.append({'agent_id':person['agent_id'],'weight':recipient['analysis_weight'],
            'q8':subset._point.to_numpy(float),'q9':subset._center.to_numpy(float),
            'bins':subset[[f'Q9_bin{i}' for i in range(1,11)]].to_numpy(float),
            'donor_ids':subset.userid.to_numpy(int),'donor_periods':subset.date.to_numpy(int),
            'p0':p0,'p':p0.copy(),'fixed':{},'older_own_memory':{},
            'synthetic_fields':['q8','q9'],'matching':meta,'donor_type':'unknown'})
    return options


def prior_bands(options, published_anchor):
    # Q8 is deliberately unconstrained: a Q9 national headline is NOT Q8 truth.
    point=np.concatenate([o['q8'] for o in options])
    return {'q8':[float(point.min()-1),float(point.max()+1)],
            'q9':[float(published_anchor)-.05,float(published_anchor)+.05]}


def expected_summary(options, *, calibrated):
    out={}
    weights=np.concatenate([o['weight']*(o['p'] if calibrated else o['p0']) for o in options])
    for key in ('q8','q9'):
        out[key]=distribution_summary(np.concatenate([o[key] for o in options]),weights)
    return out


def balance_joint_draw(options, draws, band, *, month, seed):
    """Condition a finite old-donor assignment on a PUBLIC past median band.

    Keep all P IDs/weights fixed. If needed, replace only enough out-of-band
    synthetic assignments by an admissible intact joint donor from that
    recipient's SAME matching pool. No fabricated bins, clipping, new seed
    search, current outcomes or survey-weight changes are allowed. This
    creates dependent assignments; marginal donor probabilities are no longer
    exactly p, so probability-tilt ratio bounds must not be claimed for this
    additional constrained assignment.
    """
    result=deepcopy(draws);total=sum(r['weight'] for r in result)
    lower,upper=band
    if total<=0 or lower>upper:raise ValueError('Positive mass and ordered band required')
    indexed={o['agent_id']:o for o in options}
    def masses():
        return (sum(r['weight'] for r in result if r['q9']<lower)/total,
                sum(r['weight'] for r in result if r['q9']<=upper)/total)
    before=masses();changed=[]
    for direction in ('low','high'):
        low,high=masses()
        if (direction=='low' and low<.5-1e-12) or (direction=='high' and high>=.5+1e-12):continue
        candidates=[]
        for i,r in enumerate(result):
            relevant=r['q9']<lower if direction=='low' else r['q9']>upper
            o=indexed[r['agent_id']];mask=(o['q9']>=lower)&(o['q9']<=upper)
            mass=float(o['p'][mask].sum())
            if relevant and mass>0:
                tie=hashlib.sha256(f'{seed}|{month}|{r["agent_id"]}|balance'.encode()).digest()
                candidates.append((-r['weight'],-mass,tie,i,mask))
        for _,_,_,i,mask in sorted(candidates,key=lambda c:c[:3]):
            r=result[i];o=indexed[r['agent_id']]
            candidates_idx=np.flatnonzero(mask);p=o['p'][mask];p=p/p.sum()
            h=hashlib.sha256(f'{seed}|{month}|{r["agent_id"]}|conditional-donor'.encode()).digest()
            rng=np.random.default_rng(int.from_bytes(h[:8],'little'))
            j=int(rng.choice(candidates_idx,p=p))
            r.update(q8=float(o['q8'][j]),q9=float(o['q9'][j]),q9_bins=o['bins'][j].tolist(),
                     donor_userid_private=int(o['donor_ids'][j]),donor_period=int(o['donor_periods'][j]))
            changed.append(r['agent_id'])
            low,high=masses()
            if (direction=='low' and low<.5-1e-12) or (direction=='high' and high>=.5+1e-12):break
    after=masses()
    median=distribution_summary([r['q9'] for r in result],[r['weight'] for r in result])['median_pp']
    return result,{'status':'finite_assignment_band_met' if lower<=median<=upper else 'finite_assignment_infeasible',
        'median_band_pp':band,'realized_median_pp':median,'cdf_before':list(before),'cdf_after':list(after),
        'changed_assignments':len(set(changed)),'changed_weight_fraction':sum(r['weight'] for r in result if r['agent_id'] in set(changed))/total,
        'same_recipient_matching_pools':True,'joint_donor_answers_unchanged':True,
        'recipient_weights_unchanged':True,'new_marginal_probability_ratio_bound_claimed':False}


def prepare(source, out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    status=read_json(source/'summary.json')
    if status['status'] not in {'offline_public_P_and_past_anchor_ready_not_dispatchable',
                               'offline_rolling_proxy_P_under_declared_release_lag_assumption'}:
        raise ValueError('Declared and validated population preflight required')
    for path,digest in status['source_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('Preflight source changed')
    pop=read_json(source/'selected_proxy_population_private.json')
    plans=read_json(source/'monthly_input_plan.json')
    past=pd.read_parquet(source/'old_joint_donor_pool_private.parquet')
    maximum=int(status['source_snapshot_reference_max'])
    if past.date.max()>maximum:raise ValueError('Newer microdata cannot enter the old donor pool')
    cache=PastScoreCache()
    wanted={tuple(r) for r in past[[f'Q9_bin{i}' for i in range(1,11)]].itertuples(index=False,name=None)}
    cache.values={tuple(r['bins']):r['score']['mean'] for r in read_json(CACHE) if tuple(r['bins']) in wanted}
    scored=cache.score(past,next_month(maximum))
    out.mkdir(parents=True); rows=[];preview=[]
    for plan in plans:
        month=plan['month'];anchor=plan['last_public_national_anchor']
        if int(anchor['reference_period'].replace('-',''))>=int(month):
            raise ValueError('Current/future target entered initial beliefs')
        wave=int(plan.get('old_population_reference_period',maximum))
        if wave>maximum or wave>=int(month):raise ValueError('Source wave exceeds source or target boundary')
        eligible=scored.loc[scored.date.le(wave)].copy()
        eligible['_age_months']=[month_age(next_month(wave),v) for v in eligible.date]
        options=options_from_old_pool(eligible,pop[month],source_max_month=wave)
        before=expected_summary(options,calibrated=False)
        bands=prior_bands(options,anchor['value_pp'])
        fit=calibrate(options,bands,max_ratio=4.)
        after=expected_summary(options,calibrated=True)
        original_draw=draw(options,month,20261024)
        drawn,assignment=balance_joint_draw(options,original_draw,bands['q9'],month=month,seed=20261024)
        states={}
        for r in drawn:
            states[r['agent_id']]={
                'source_kind':('synthetic_release_rule_joint_donor' if status.get('availability_basis') else 'synthetic_old_public_joint_donor'),
                'synthetic_reference_period':anchor['reference_period'],
                'observed_donor_reference_period':str(r['donor_period']),
                'observed_donor_age_months':month_age(month,r['donor_period']),
                'donor_public_known_by_utc':status['source_public_known_by_utc'],
                'availability_basis':plan.get('availability_basis','archived_public_snapshot'),
                'historical_byte_vintage_verified':plan.get('historical_byte_vintage_verified',True),
                'q8_point_pct':r['q8'],'q9_bins':r['q9_bins'],'q9_density_mean_pct':r['q9'],
                'actual_person_previous_answer':False,'actual_recent_person_history_available':False}
        dump(out/f'{month}_independent_draws_private.json',original_draw)
        dump(out/f'{month}_draws_private.json',drawn)
        dump(out/f'{month}_initial_states_private.json',states)
        actual={key:distribution_summary([r[key] for r in drawn],[r['weight'] for r in drawn]) for key in ('q8','q9')}
        rows.append({'month':month,'n':len(drawn),'source_wave':str(wave),'past_public_anchor':anchor,
            'q9_expected_median_band_pp':bands['q9'],'q8_national_constraint':None,
            'calibration':fit,'finite_assignment':assignment,
            'expected_quantile_inside_band':bands['q9'][0]<=after['q9']['median_pp']<=bands['q9'][1],
            'expected_before':before,'expected_after':after,'realized_draw':actual,
            'source_pool_windows':dict(Counter(str(r['matching']['window_months']) for r in drawn)),
            'source_age_months_min':min(v['observed_donor_age_months'] for v in states.values()),
            'source_age_months_max':max(v['observed_donor_age_months'] for v in states.values()),
            'no_reseeding_or_numeric_repair':True})
        r=next(iter(states.values()))
        preview.append(f"{month}\nSynthetic earlier belief state, assigned from an old publicly available survey pool; not your actual previous-month answer.\nThe observed source is {r['observed_donor_reference_period']}, with a pool-level probability calibration toward the already published national {anchor['reference_period']} Q9 headline.\nAssigned Q8 point: {r['q8_point_pct']:.6g}%. Assigned Q9 probabilities (bin1 to bin10): {r['q9_bins']}.\nConsider keeping or revising this synthetic starting view using today's available information.\n")
        print(f"{month}: {assignment['status']}; realized {actual['q9']['median_pp']:.4f}; anchor {anchor['value_pp']:.1f}; {assignment['changed_assignments']} joint assignments changed",flush=True)
    dump(out/'monthly_prior_diagnostics.json',rows)
    (out/'synthetic_prior_wording_preview.txt').write_text('\n'.join(preview))
    result={'status':'draft_synthetic_priors_not_dispatchable','months':len(rows),'person_months':sum(r['n'] for r in rows),
        'new_api_calls':0,'new_q9_input_fits':cache.new_fits,'source_micro_max':str(maximum),
        'population_preflight':str(source.relative_to(ROOT)),
        'availability_basis':status.get('availability_basis','archived_public_snapshot'),
        'method':'existing A donor matching and probability tilt, then a finite public-past-median-constrained joint donor assignment',
        'q9_band_rule':'last publicly released one-decimal Q9 national headline +/-0.05pp; realized finite assignment checked explicitly',
        'q8_rule':'no national Q8 target; retain joint sampled answers without direct Q8 calibration',
        'draw_seed':20261024,'old_observations_relabelled_as_actual_last_month':False,
        'calibration_statuses':dict(Counter(r['calibration']['status'] for r in rows)),
        'finite_assignment_statuses':dict(Counter(r['finite_assignment']['status'] for r in rows)),
        'max_changed_assignment_weight_fraction':max(r['finite_assignment']['changed_weight_fraction'] for r in rows),
        'built_at_utc':datetime.now(timezone.utc).isoformat(),
        'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in (source/'summary.json',source/'monthly_input_plan.json',source/'selected_proxy_population_private.json',source/'old_joint_donor_pool_private.parquet',CACHE,Path(__file__))},
        'pending':['User review of old-source/synthetic-prior assumptions and residuals.',
                   'Freeze historical text-version treatment and complete qualified environment prompts.',
                   'Official Core dry-run and a separate exact batch/data/budget approval.'],
        'limits':['Only median/CDF mass constrained; no claim that recent microstructure is identified.',
                  ('Source observations follow the declared per-month release-lag assumption; exact historical byte vintages remain unverified.' if status.get('availability_basis') else 'Source observations remain 15-27 months old for these targets; probability reweighting does not refresh personal experience.'),
                  'Finite assignment conditions on the known past median and couples donor choices; it changes the unconstrained donor-draw law and can affect conditional priors.',
                  'Infeasible finite assignments remain explicit and are not dispatched or repaired numerically; no prior seed search.',
                  'No recent target outcomes, real recent individual histories or current population weights enter this adapter.']}
    dump(out/'summary.json',result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    result=prepare(args.source,args.out)
    print(json.dumps({k:v for k,v in result.items() if k!='source_sha256'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
