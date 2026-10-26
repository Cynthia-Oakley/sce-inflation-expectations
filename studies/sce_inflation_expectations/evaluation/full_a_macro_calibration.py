"""Offline aggregate ARX/ridge and measurement-bridge diagnostics, no API."""
import argparse
import csv
from datetime import datetime
from pathlib import Path

import numpy as np

from ..experiments.full_a_core_normal import ROOT, checked, fresh, read, sha, write
from ..submission_tools.reproduce import no_network
from .aggregate_blend import fit_weight, metrics
from .metrics import paired_month_mae_interval

CN = ROOT/'outputs/sce_full_a_core_normal_evaluation_20261026_v3'
CORE = ROOT/'outputs/sce_full_a_t0_analysis_20261026_v1'
ENV = ROOT/'outputs/sce_fullperiod_materialized_20261022_v2'
PROTOCOL = ROOT/'docs/workstreams/20261026_core_normal_full_a/macro_calibration_protocol.json'
FEATURES = {
 'AR_public_level': ['anchor_level'],
 'macro_without_sim': ['anchor_level','cpi_gap','cpi_change'],
 'macro_plus_sim': ['anchor_level','cpi_gap','cpi_change','sim_gap'],
 'regime_without_sim': ['anchor_level','cpi_gap','cpi_change','high_cpi'],
 'regime_plus_sim': ['anchor_level','cpi_gap','cpi_change','high_cpi','sim_gap','high_cpi_sim_gap'],
}


def cpi_features(environment):
    args=environment['provider_args']
    cutoff=datetime.fromisoformat(args['targets'][0]['as_of'])
    candidates=[x for x in args['signals_by_step']['0']
                if x['signal_id'].startswith('bls_cpi_u_all_items_yoy')
                and datetime.fromisoformat(x['published_at']) <= cutoff]
    candidates=sorted(candidates, key=lambda r: (r['reference_period'],r['published_at']),reverse=True)
    if len(candidates)<2:
        raise ValueError('Two eligible first-release CPI observations required; no silent filling')
    latest,previous=candidates[:2]
    if latest['reference_period']==previous['reference_period']:
        raise ValueError('Duplicate CPI period')
    return dict(cpi_yoy_pp=float(latest['value']),cpi_change_pp=float(latest['value']-previous['value']),
      cpi_reference=latest['reference_period'],cpi_published_at=latest['published_at'],
      cpi_previous_reference=previous['reference_period'],as_of=cutoff.isoformat())


def features(row, sim):
    anchor=float(row['baseline_pp']); cpi=row['cpi_yoy_pp']; gap=float(row[sim])-anchor
    high=float(cpi>=4)
    return dict(anchor_level=anchor,cpi_gap=cpi-anchor,cpi_change=row['cpi_change_pp'],
                sim_gap=gap,high_cpi=high,high_cpi_sim_gap=high*gap)


def fit_ridge(x,y,alpha):
    x,y=np.asarray(x,float),np.asarray(y,float)
    if alpha<0 or x.ndim!=2 or y.shape!=(len(x),) or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('Finite matched training arrays and nonnegative alpha required')
    mean=x.mean(0);scale=x.std(0);scale=np.where(scale>1e-12,scale,1.)
    z=(x-mean)/scale; centre=float(y.mean())
    if alpha==0:
        beta=np.linalg.lstsq(z,y-centre,rcond=None)[0]
    else:
        beta=np.linalg.solve(z.T@z+alpha*np.eye(z.shape[1]),z.T@(y-centre))
    raw=beta/scale
    return dict(alpha=float(alpha),mean=mean.tolist(),scale=scale.tolist(),
                standardised_coefficients=beta.tolist(),coefficients=raw.tolist(),
                intercept=float(centre-mean@raw))


def predict(x,fit):
    return fit['intercept']+np.asarray(x,float)@np.asarray(fit['coefficients'])


def train_only_fit(x,y,alphas):
    if len(x)!=48 or len(y)!=48:
        raise ValueError('Exactly 48 early months required')
    candidates=[]
    for alpha in alphas:
        fit=fit_ridge(x[:36],y[:36],alpha)
        candidates.append(dict(alpha=alpha,validation_mae_pp=float(np.abs(predict(x[36:48],fit)-y[36:48]).mean())))
    minimum=min(r['validation_mae_pp'] for r in candidates)
    alpha=max(r['alpha'] for r in candidates if r['validation_mae_pp']<=minimum+1e-12)
    return dict(**fit_ridge(x,y,alpha),validation=candidates)


def csv_write(path,rows):
    with path.open('w') as stream:
        w=csv.DictWriter(stream,fieldnames=rows[0]);w.writeheader();w.writerows(rows)


def run(out):
    out=fresh(out); protocol=read(PROTOCOL);write(out/'protocol.json',protocol)
    cn_manifest=read(CN/'manifest.json');checked(CN,cn_manifest['files_sha256'])
    core=read(CORE/'summary.json')
    with (CN/'monthly_public.csv').open() as stream: rows=list(csv.DictReader(stream))
    anchors={r['month'].replace('-',''):r for r in core['official_national']['monthly']}
    human={str(r['month']).replace('-',''):r['fields']['q9_mean']['observed']['median_pp'] for r in core['full_wave_monthly']}
    sources=[PROTOCOL,CN/'manifest.json',CN/'monthly_public.csv',CORE/'summary.json',Path(__file__)]
    for row in rows:
        month=row['month'];source=ENV/month/'environment.json';sources.append(source)
        row.update(cpi_features(read(source)))
        for key in ['before_model_pp','expanded_model_pp','truth_pp','baseline_pp']:
            row[key]=float(row[key])
        old=anchors[month]
        if old['anchor_published_date']>row['as_of'][:10] or old['anchor_reference'].replace('-','')>=month:
            raise ValueError('SCE anchor must already be public and from a past target month')
        if row['truth_pp']!=old['truth_pp'] or row['baseline_pp']!=old['anchor_pp']:
            raise ValueError('Frozen national target/anchor mismatch')
        row.update(anchor_reference=old['anchor_reference'],anchor_published_date=old['anchor_published_date'],
                   common_score_human_pp=float(human[month]))
    if [r['month'] for r in rows]!=[r['month'].replace('-','') for r in core['official_national']['monthly']] or len(rows)!=82:
        raise ValueError('Complete chronological 82-month join required')
    csv_write(out/'monthly_inputs_public.csv',rows)
    y=np.array([r['truth_pp'] for r in rows]);anchor=np.array([r['baseline_pp'] for r in rows])
    change=y-anchor;fits={};predictions={'persistence':anchor.copy()}
    for sim,label in [('before_model_pp','Core'),('expanded_model_pp','CoreNormal_tau8')]:
        signal=np.array([r[sim] for r in rows]);predictions[label+'_pure']=signal
        for loss in ['mae','mse']:
            weight=fit_weight(y[:48],anchor[:48],signal[:48],loss)
            name=label+'_blend_'+loss
            fits[name]=dict(simulation_weight=weight,history_weight=1-weight,training_months=48,loss=loss)
            predictions[name]=anchor+weight*(signal-anchor)
        f=[features(r,sim) for r in rows]
        for family,names in FEATURES.items():
            if sim=='expanded_model_pp' and 'sim_gap' not in names: continue
            x=np.array([[v[n] for n in names] for v in f]);name=label+'_'+family
            fit=train_only_fit(x[:48],change[:48],protocol['ridge_alphas'])
            fits[name]=dict(**fit,features=names,training_months=48)
            predictions[name]=anchor+predict(x,fit)
    write(out/'training_fits_sealed_before_later_scores.json',fits)
    results={}
    for name,pred in predictions.items():
        result={period:metrics(pred[a:b],y[a:b]) for period,a,b in [('training48',0,48),('later34',48,82),('all82_descriptive',0,82)]}
        result['later34']['r2_relative_to_persistence']=1-result['later34']['mse_pp_squared']/metrics(anchor[48:],y[48:])['mse_pp_squared']
        result['later34_interval']=paired_month_mae_interval(pred[48:]-y[48:],anchor[48:]-y[48:],block_length=6,draws=2000,seed=20261026)
        result['later_years']={year:metrics([p for p,r in zip(pred,rows) if r['month'].startswith(year)],
                                           [r['truth_pp'] for r in rows if r['month'].startswith(year)])
                               for year in ['2023','2024','2025']}
        results[name]=result
    bridge=metrics([r['common_score_human_pp'] for r in rows],y)
    bridge['max_absolute_gap_pp']=float(np.max(np.abs(np.array([r['common_score_human_pp'] for r in rows])-y)))
    # Keep reconstructed-human target scores separate from national headline.
    bridge['core_mae_against_common_score_human_pp']=metrics(predictions['Core_pure'],[r['common_score_human_pp'] for r in rows])['mae_pp']
    bridge['normal_mae_against_common_score_human_pp']=metrics(predictions['CoreNormal_tau8_pure'],[r['common_score_human_pp'] for r in rows])['mae_pp']
    output=[dict(month=r['month'],truth_pp=r['truth_pp'],**{name:float(pred[i]) for name,pred in predictions.items()}) for i,r in enumerate(rows)]
    csv_write(out/'monthly_predictions_public.csv',output)
    summary=dict(status='completed_offline_macro_calibration_diagnostic',protocol=protocol,
       new_api_calls=0,new_q9_fits=0,tau202_adopted=False,original_results_changed=False,
       measurement_bridge=bridge,results=results,fits=fits)
    write(out/'summary.json',summary)
    write(out/'manifest.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
          files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('MEASUREMENT_BRIDGE',bridge)
    for k,v in results.items():print(k,'lateMAE',round(v['later34']['mae_pp'],6),'lateRMSE',round(v['later34']['rmse_pp'],6),
                                     'fit',fits.get(k,{}).get('alpha',fits.get(k,{}).get('simulation_weight')))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args()
    with no_network():run(a.out)


if __name__=='__main__':main()
