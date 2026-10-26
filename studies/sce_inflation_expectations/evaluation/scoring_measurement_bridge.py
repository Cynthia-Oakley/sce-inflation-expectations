"""Read-only official-versus-frozen scoring bridge and aggregate sensitivity."""
import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from ..experiments.full_a_core_normal import ROOT,read,write,sha,fresh,checked
from ..prior_belief_preparation import valid_bins
from ..scoring.sce_q9_frozen import provenance
from ..submission_tools.reproduce import no_network
from .aggregate_blend import metrics
from .metrics import empirical,quantile
from .monthly_main_readout import model_distribution

CORE=ROOT/'outputs/sce_full_a_t0_analysis_20261026_v1'
NORMAL=ROOT/'outputs/sce_full_a_core_normal_prediction_20261026_v2'
FRAME=ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
CATALOG=ROOT/'data/evaluation/sce_baselines_latest_20261007/aggregate_inputs.json'
PROTOCOL=ROOT/'docs/workstreams/20261026_core_normal_full_a/measurement_and_2021_protocol.json'


def midcdf_quantile(values,weights,p):
    """Appendix-B Cox interpolation; candidate sensitivity only.

    Equal values are a single probability atom, invariant to row splitting.
    Endpoints clamp to support; nothing is fitted to official answers.
    """
    if not 0<=p<=1:raise ValueError('Probability outside [0,1]')
    x,w,_=empirical(values,weights)
    unique,inverse=np.unique(x,return_inverse=True)
    mass=np.bincount(inverse,weights=w)
    mid=(np.cumsum(mass)-.5*mass)/mass.sum()
    return float(np.interp(p,mid,unique))


def signed_decomposition(model,human,official):
    s,h,o=map(lambda x:np.asarray(x,float),(model,human,official))
    behaviour=s-h;bridge=h-o;total=s-o
    a=float(np.mean(behaviour**2));b=float(np.mean(bridge**2));c=float(2*np.mean(behaviour*bridge))
    return dict(total=metrics(s,o),common_score_target=metrics(s,h),human_measurement_bridge=metrics(h,o),
       mse_identity=dict(total=float(np.mean(total**2)),model_vs_common_human=a,measurement_square=b,cross_term=c,
                         identity_residual=float(np.mean(total**2)-a-b-c)),
       net_mae_change_when_using_official_target_pp=float(np.mean(abs(total))-np.mean(abs(behaviour))),
       interpretation='MAE difference is target-definition sensitivity, not a uniquely identified causal share of scoring error')


def run(out):
    out=fresh(out);write(out/'protocol.json',read(PROTOCOL))
    assert provenance()['live_matches_pinned']
    manifest=read(CORE/'manifest.json');checked(CORE,manifest['files_sha256'])
    core=read(CORE/'summary.json'); cache={tuple(r['bins']):r['score'] for r in read(CORE/'scoring_cache_private.json')}
    source=[PROTOCOL,FRAME,CATALOG,CORE/'manifest.json',CORE/'summary.json',CORE/'scoring_cache_private.json',
            CORE/'cases_private.json',Path(__file__)]
    columns=['date','weight','Q9_mean',*[f'Q9_bin{i}' for i in range(1,11)]]
    raw=pd.read_parquet(FRAME,columns=columns)
    raw=raw.loc[raw.date.between(201901,202510)]
    cases=defaultdict(list)
    for row in read(CORE/'cases_private.json'):cases[str(row['month'])].append(row)
    official={r['reference_period'].replace('-',''):r for r in read(CATALOG)['headline_releases']}
    summaries={str(r['month']):r for r in core['full_wave_monthly']}
    records=[];pair_errors=[];pair_weights=[];branch=defaultdict(lambda:[[],[]])
    for month,group in raw.groupby('date',sort=True):
        month=str(int(month));own=[];ref=[];weights=[];branches=[]
        for row in group.to_dict('records'):
            w=row['weight']
            if not np.isfinite(w) or w<=0:continue
            bins=[float(row[f'Q9_bin{i}']) for i in range(1,11)]
            x=None
            if valid_bins(bins):
                if tuple(bins) not in cache:raise ValueError('Frozen score missing; no refitting allowed')
                x=cache[tuple(bins)]['mean']
            own.append(float(x) if x is not None and np.isfinite(x) else np.nan)
            ref.append(float(row['Q9_mean']) if np.isfinite(row['Q9_mean']) else np.nan)
            weights.append(float(w))
            positive=[i for i,v in enumerate(bins) if np.isfinite(v) and v>0]
            branches.append('uniform' if len(positive)==1 else 'two_bin' if len(positive)==2 else
                            'beta_open' if positive and (positive[0]==0 or positive[-1]==9) else 'beta_closed')
        own,ref,weights=map(np.asarray,(own,ref,weights));ours=np.isfinite(own);refs=np.isfinite(ref);common=ours&refs
        if not common.any():raise ValueError('No common human support')
        for i in np.flatnonzero(common):
            e=own[i]-ref[i];pair_errors.append(e);pair_weights.append(weights[i]);branch[branches[i]][0].append(e);branch[branches[i]][1].append(weights[i])
        h=quantile(own[ours],weights[ours],.5);hc=quantile(own[common],weights[common],.5)
        rc=quantile(ref[common],weights[common],.5);ra=quantile(ref[refs],weights[refs],.5)
        target=official[month];chart=float(target['chart_snapshot_value_pp']);published=float(target['value_pp'])
        if not np.isclose(h,summaries[month]['fields']['q9_mean']['observed']['median_pp'],atol=1e-10):
            raise ValueError('Existing frozen human aggregate differs: '+month)
        atom_path=NORMAL/month/'atoms_private.json';source.append(atom_path);atoms=read(atom_path)
        vx=[a['q9_mean'] for a in atoms['q9_atoms']];vw=atoms['by_tau']['8']['q9_mass']
        sx,sw=model_distribution(cases[month],'q9_mean')
        item=dict(month=month,n_positive_weight=len(weights),n_ours=int(ours.sum()),n_official=int(refs.sum()),
             n_common=int(common.sum()),our_human_full_pp=h,our_human_common_pp=hc,official_human_common_pp=rc,
             official_human_full_pp=ra,official_chart_pp=chart,official_initial_pp=published,
             our_only_support_effect_pp=h-hc,density_common_effect_pp=hc-rc,
             official_only_support_effect_pp=rc-ra,aggregation_vintage_effect_pp=ra-chart,
             chart_initial_precision_vintage_effect_pp=chart-published,
             our_human_cox_pp=midcdf_quantile(own[ours],weights[ours],.5),
             official_human_cox_pp=midcdf_quantile(ref[refs],weights[refs],.5),
             core_empirical_pp=quantile(sx,sw,.5),core_cox_pp=midcdf_quantile(sx,sw,.5),
             normal_empirical_pp=quantile(vx,vw,.5),normal_cox_pp=midcdf_quantile(vx,vw,.5))
        if not np.isclose(sum(item[k] for k in ['our_only_support_effect_pp','density_common_effect_pp',
            'official_only_support_effect_pp','aggregation_vintage_effect_pp','chart_initial_precision_vintage_effect_pp']),h-published,atol=1e-12):
            raise ValueError('Measurement identity failed')
        records.append(item)
    if len(records)!=82:raise ValueError('Expected82 monthly records')
    summary=dict(status='completed_measurement_bridge',new_api_calls=0,new_density_fits=0,original_scorer_changed=False,
        common_person_weighted_mae_pp=float(np.average(np.abs(pair_errors),weights=pair_weights)),
        common_person_n=len(pair_errors),branches={k:dict(n=len(e),weighted_mae_pp=float(np.average(np.abs(e),weights=w))) for k,(e,w) in branch.items()},periods={})
    for period,rr in [('all82',records),('year2021',[r for r in records if r['month'].startswith('2021')])]:
        p=[r['official_initial_pp'] for r in rr];h=[r['our_human_full_pp'] for r in rr]
        block=dict(n_months=len(rr),components_mean_absolute_pp={k:float(np.mean([abs(r[k]) for r in rr])) for k in
          ['our_only_support_effect_pp','density_common_effect_pp','official_only_support_effect_pp',
           'aggregation_vintage_effect_pp','chart_initial_precision_vintage_effect_pp']})
        for model in ['core','normal']:
            s=[r[model+'_empirical_pp'] for r in rr]
            block[model]=signed_decomposition(s,h,p)
            block[model]['cox_sensitivity_against_initial']=metrics([r[model+'_cox_pp'] for r in rr],p)
            # Exact, ordered target-replacement accounting; signed effects may
            # offset, and a different ordering need not attribute the same MAE.
            names=['our_human_full_pp','our_human_common_pp','official_human_common_pp','official_human_full_pp','official_chart_pp','official_initial_pp']
            losses=[metrics(s,[r[k] for r in rr])['mae_pp'] for k in names]
            block[model]['ordered_target_replacement_mae_effects_pp']={f'{a}_to_{b}':losses[i+1]-losses[i] for i,(a,b) in enumerate(zip(names,names[1:]))}
        block['official_fields_empirical_vs_chart']=metrics([r['official_human_full_pp'] for r in rr],[r['official_chart_pp'] for r in rr])
        block['official_fields_cox_vs_chart']=metrics([r['official_human_cox_pp'] for r in rr],[r['official_chart_pp'] for r in rr])
        summary['periods'][period]=block
    import csv
    with (out/'monthly_public.csv').open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=records[0]);w.writeheader();w.writerows(records)
    write(out/'summary.json',summary)
    write(out/'manifest.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in source},
          files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    for k,v in summary['periods'].items():print(k,v)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    with no_network():run(a.out)


if __name__=='__main__':main()
