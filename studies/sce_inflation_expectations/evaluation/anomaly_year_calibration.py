"""2021 diagnostics with pre-2021 coefficients or publication-gated updates."""
import argparse
import csv
from pathlib import Path

import numpy as np

from ..experiments.full_a_core_normal import ROOT,read,write,sha,fresh,checked
from ..submission_tools.reproduce import no_network
from .aggregate_blend import fit_weight,metrics
from .metrics import paired_month_mae_interval
from .full_a_macro_calibration import FEATURES,features,fit_ridge,predict

MACRO=ROOT/'outputs/sce_full_a_macro_calibration_20261026_v1'
CORE=ROOT/'outputs/sce_full_a_t0_analysis_20261026_v1'
PROTOCOL=ROOT/'docs/workstreams/20261026_core_normal_full_a/measurement_and_2021_protocol.json'


def eligible_training_indices(rows,target):
    return np.array([i for i,r in enumerate(rows) if r['month']<target['month']
        and r['truth_published_date']<=target['as_of'][:10]],dtype=int)


def choose_before_2021(x,y,alphas):
    if len(x)!=24 or len(y)!=24:raise ValueError('24 pre-2021 months required')
    validations=[]
    for alpha in alphas:
        fit=fit_ridge(x[:18],y[:18],alpha)
        validations.append(dict(alpha=alpha,mae_pp=float(np.mean(abs(predict(x[18:],fit)-y[18:])))))
    best=min(r['mae_pp'] for r in validations)
    alpha=max(r['alpha'] for r in validations if r['mae_pp']<=best+1e-12)
    return dict(**fit_ridge(x,y,alpha),validation=validations)


def run(out):
    out=fresh(out);protocol=read(PROTOCOL);write(out/'protocol.json',protocol)
    checked(MACRO,read(MACRO/'manifest.json')['files_sha256'])
    with (MACRO/'monthly_inputs_public.csv').open() as f: rows=list(csv.DictReader(f))
    official={r['month'].replace('-',''):r for r in read(CORE/'summary.json')['official_national']['monthly']}
    for row in rows:
        row['truth_published_date']=official[row['month']]['truth_published_date']
        for k in ['before_model_pp','expanded_model_pp','baseline_pp','truth_pp','cpi_yoy_pp','cpi_change_pp']:
            row[k]=float(row[k])
    early=[i for i,r in enumerate(rows) if r['month']<'202101']
    test=[i for i,r in enumerate(rows) if r['month'].startswith('2021')]
    if len(early)!=24 or len(test)!=12:raise ValueError('Expected24/12 chronological split')
    first=rows[test[0]]
    if not set(early)<=set(eligible_training_indices(rows,first)):
        raise ValueError('All fixed-training outcomes must be public before first test cutoff')
    y=np.array([r['truth_pp'] for r in rows]);anchor=np.array([r['baseline_pp'] for r in rows]);change=y-anchor
    fits={};prediction={'persistence':anchor[test].copy()};rolling_audit=[]
    for i in test:
        known=eligible_training_indices(rows,rows[i])
        rolling_audit.append(dict(month=rows[i]['month'],as_of=rows[i]['as_of'],n_training=len(known),
            last_training_month=rows[int(known[-1])]['month'],
            last_training_label_published_at=rows[int(known[-1])]['truth_published_date'],
            high_CPI_training_n=sum(rows[int(j)]['cpi_yoy_pp']>=4 for j in known)))
    alphas=[0,.1,1,10,100]
    for sim,label in [('before_model_pp','Core'),('expanded_model_pp','CoreNormal_tau8')]:
        signal=np.array([r[sim] for r in rows]);prediction[label+'_pure']=signal[test]
        for loss in ['mae','mse']:
            weight=fit_weight(y[early],anchor[early],signal[early],loss)
            name=label+'_blend_'+loss
            fits[name]=dict(weight=weight,training_months=[rows[i]['month'] for i in early])
            prediction[name+'_fixed']=anchor[test]+weight*(signal[test]-anchor[test])
            rolling=[];wa=[]
            for i in test:
                known=eligible_training_indices(rows,rows[i]);w=fit_weight(y[known],anchor[known],signal[known],loss)
                rolling.append(anchor[i]+w*(signal[i]-anchor[i]));wa.append(dict(month=rows[i]['month'],weight=w))
            prediction[name+'_rolling']=np.array(rolling);fits[name]['rolling_weights']=wa
        ff=[features(r,sim) for r in rows]
        for family,names in FEATURES.items():
            if sim=='expanded_model_pp' and 'sim_gap' not in names:continue
            x=np.array([[f[n] for n in names] for f in ff]);name=label+'_'+family
            fit=choose_before_2021(x[early],change[early],alphas)
            unidentified=[n for n,std in zip(names,x[early].std(axis=0)) if std<=1e-12]
            fits[name]=dict(**fit,features=names,unidentified_constant_pre2021_columns=unidentified,
                            n_high_CPI_training=int(sum(rows[i]['cpi_yoy_pp']>=4 for i in early)))
            prediction[name+'_fixed']=anchor[test]+predict(x[test],fit)
            values=[];yearfits=[]
            for i in test:
                known=eligible_training_indices(rows,rows[i]);current=fit_ridge(x[known],change[known],fit['alpha'])
                values.append(anchor[i]+predict(x[[i]],current)[0])
                yearfits.append(dict(month=rows[i]['month'],n_training=len(known),**current))
            prediction[name+'_rolling']=np.array(values);fits[name]['rolling_fits']=yearfits
    write(out/'fits_sealed_before_2021_scores.json',fits)
    actual=y[test];base=anchor[test];result={}
    for name,p in prediction.items():
        result[name]=dict(year2021=metrics(p,actual),first_half=metrics(p[:6],actual[:6]),
            second_half=metrics(p[6:],actual[6:]),
            paired_mae_interval=paired_month_mae_interval(p-actual,base-actual,block_length=3,draws=2000,seed=20261026))
    public=[dict(month=rows[i]['month'],truth_pp=rows[i]['truth_pp'],
            **{name:float(pred[j]) for name,pred in prediction.items()}) for j,i in enumerate(test)]
    with (out/'monthly_public.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=public[0]);w.writeheader();w.writerows(public)
    summary=dict(status='completed_pre2021_and_rolling_diagnostic',protocol=protocol,
        new_api_calls=0,new_density_fits=0,results=result,fits=fits,rolling_publication_audit=rolling_audit,
        fixed_training_months=[rows[i]['month'] for i in early],
        warning='Statistical coefficients exclude future labels; A simulation/configuration and historical periods are not untouched and not certified common-cutoff forecasts')
    write(out/'summary.json',summary)
    source=[PROTOCOL,MACRO/'manifest.json',MACRO/'monthly_inputs_public.csv',CORE/'summary.json',Path(__file__)]
    write(out/'manifest.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in source},
         files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    for name,r in result.items(): print(name,round(r['year2021']['mae_pp'],6),round(r['year2021']['rmse_pp'],6))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    with no_network():run(a.out)


if __name__=='__main__':main()
