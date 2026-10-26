"""Same-rule SCE/CPI controls and month-end information-scope sensitivity."""
import argparse
import calendar
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import csv

import numpy as np

from ..experiments.full_a_core_normal import ROOT,read,write,sha,fresh,checked
from ..submission_tools.reproduce import no_network
from .full_a_macro_calibration import FEATURES,features,fit_ridge,predict
from .anomaly_year_calibration import choose_before_2021,eligible_training_indices
from .aggregate_blend import fit_weight,metrics
from .metrics import paired_month_mae_interval

MACRO=ROOT/'outputs/sce_full_a_macro_calibration_20261026_v1'
LEGACY=ROOT/'outputs/sce_anomaly_year_calibration_20261026_v1'
CATALOG=ROOT/'data/evaluation/sce_baselines_latest_20261007/aggregate_inputs.json'
PROTOCOL=ROOT/'docs/workstreams/20261026_measurement_anomaly/presentation_and_fair_benchmark_protocol.json'


def month_end(month):
    year,mon=int(month[:4]),int(month[4:])
    return datetime(year,mon,calendar.monthrange(year,mon)[1],23,59,59,tzinfo=ZoneInfo('America/New_York')).isoformat()


def public_anchor(releases,target,cutoff):
    eligible=[r for r in releases if r['reference_period'].replace('-','')<target and r['published_date']<=cutoff[:10]]
    if not eligible:raise ValueError('No published past SCE anchor')
    return max(eligible,key=lambda r:(r['published_date'],r['reference_period']))


def output_csv(path,rows):
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)


def run(out):
    out=fresh(out);protocol=read(PROTOCOL);write(out/'protocol.json',protocol)
    for path in [MACRO,LEGACY]:checked(path,read(path/'manifest.json')['files_sha256'])
    with (MACRO/'monthly_inputs_public.csv').open() as f: rows=list(csv.DictReader(f))
    releases=read(CATALOG)['headline_releases'];truth={r['reference_period'].replace('-',''):r for r in releases}
    for row in rows:
        old_asof=row['as_of'];row['original_shared_as_of']=old_asof
        row['as_of']=month_end(row['month']);anchor=public_anchor(releases,row['month'],row['as_of'])
        row['original_shared_anchor_pp']=float(row['baseline_pp'])
        row['baseline_pp']=float(anchor['value_pp']);row['anchor_reference']=anchor['reference_period']
        row['anchor_published_date']=anchor['published_date'];row['truth_published_date']=truth[row['month']]['published_date']
        for k in ['truth_pp','before_model_pp','expanded_model_pp','cpi_yoy_pp','cpi_change_pp']:row[k]=float(row[k])
        if datetime.fromisoformat(row['cpi_published_at'])>datetime.fromisoformat(row['as_of']):
            raise ValueError('Future CPI')
        if row['cpi_reference'].replace('-','')>=row['month']:raise ValueError('Target-month CPI not allowed')
    early=np.array([i for i,r in enumerate(rows) if r['month']<'202101'])
    test=np.array([i for i,r in enumerate(rows) if r['month']>='202101'])
    if len(early)!=24 or len(test)!=58:raise ValueError('Expected24 training and58 chronological check months')
    if not set(early)<=set(eligible_training_indices(rows,rows[int(test[0])])):
        raise ValueError('Fixed training labels unavailable')
    y=np.array([r['truth_pp'] for r in rows]);anchor=np.array([r['baseline_pp'] for r in rows]);change=y-anchor
    signal=np.array([r['expanded_model_pp'] for r in rows]);ff=[features(r,'expanded_model_pp') for r in rows]
    fitted={};predictions={'persistence':anchor[test],'simulation':signal[test]}
    for loss in ['mae','mse']:
        weight=fit_weight(y[early],anchor[early],signal[early],loss)
        fitted['blend_'+loss]=dict(weight=weight)
        predictions['blend_'+loss+'_fixed']=anchor[test]+weight*(signal[test]-anchor[test])
        values=[];weights=[]
        for i in test:
            known=eligible_training_indices(rows,rows[int(i)])
            w=fit_weight(y[known],anchor[known],signal[known],loss)
            values.append(anchor[i]+w*(signal[i]-anchor[i]));weights.append(dict(month=rows[i]['month'],weight=w))
        predictions['blend_'+loss+'_expanding']=np.array(values);fitted['blend_'+loss]['expanding_weights']=weights
    for family in protocol['model_families']:
        names=FEATURES[family];x=np.array([[v[n] for n in names] for v in ff])
        fit=choose_before_2021(x[early],change[early],[0,.1,1,10,100]);fitted[family]=dict(**fit,features=names)
        predictions[family+'_fixed']=anchor[test]+predict(x[test],fit)
        values=[];trace=[]
        for i in test:
            known=eligible_training_indices(rows,rows[int(i)])
            current=fit_ridge(x[known],change[known],fit['alpha'])
            values.append(anchor[i]+predict(x[[i]],current)[0])
            trace.append(dict(month=rows[i]['month'],n_training=len(known),last_training_month=rows[int(known[-1])]['month'],
                              last_training_label_publication=rows[int(known[-1])]['truth_published_date'],**current))
        predictions[family+'_expanding']=np.array(values);fitted[family]['expanding_fits']=trace
    write(out/'fits_sealed_before_scores.json',fitted)
    testrows=[rows[int(i)] for i in test];actual=y[test];periods={
       'all58':np.arange(58),'year2021':np.arange(12),'year2021_H1':np.arange(6),'year2021_H2':np.arange(6,12),
       'year2022':np.arange(12,24),'later34':np.arange(24,58)}
    result={k:{p:metrics(pred[ix],actual[ix]) for p,ix in periods.items()} for k,pred in predictions.items()}
    comparisons={}
    for no,yes in [('macro_without_sim_expanding','macro_plus_sim_expanding'),('regime_without_sim_expanding','regime_plus_sim_expanding')]:
        comparison={}
        for p,ix in periods.items():
            errors=predictions[yes][ix]-actual[ix];base=predictions[no][ix]-actual[ix]
            comparison[p]=dict(mae_reduction_pp=float(np.mean(abs(base))-np.mean(abs(errors))),
              mse_reduction_fraction=float(1-np.mean(errors**2)/np.mean(base**2)),
              paired_interval=paired_month_mae_interval(errors,base,block_length=min(3,len(ix)),draws=2000,seed=20261026))
        comparisons[yes+'_versus_'+no]=comparison
    output=[dict(month=r['month'],truth_pp=r['truth_pp'],**{k:float(v[j]) for k,v in predictions.items()}) for j,r in enumerate(testrows)]
    output_csv(out/'monthly_inputs_public.csv',rows);output_csv(out/'monthly_predictions_public.csv',output)
    legacy=read(LEGACY/'summary.json')
    summary=dict(status='completed_dynamic_fair_benchmark',protocol=protocol,results=result,fits=fitted,
       matched_comparisons=comparisons,new_api_calls=0,new_density_fits=0,original_outputs_changed=False,
       old_shared_midmonth_2021={k:v for k,v in legacy['results'].items() if k in ['persistence','Core_macro_without_sim_rolling',
          'CoreNormal_tau8_macro_plus_sim_rolling','Core_regime_without_sim_rolling','CoreNormal_tau8_regime_plus_sim_rolling']},
       changed_anchor_months=[r['month'] for r in rows if r['baseline_pp']!=r['original_shared_anchor_pp']],
       warning=protocol['limits'])
    write(out/'summary.json',summary)
    sources=[PROTOCOL,CATALOG,MACRO/'manifest.json',MACRO/'monthly_inputs_public.csv',LEGACY/'manifest.json',LEGACY/'summary.json',Path(__file__)]
    write(out/'manifest.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
         files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    for name,v in result.items():print(name,{p:round(v[p]['mae_pp'],6) for p in ['year2021','year2021_H2','year2022','later34','all58']})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    with no_network():run(a.out)


if __name__=='__main__':main()
