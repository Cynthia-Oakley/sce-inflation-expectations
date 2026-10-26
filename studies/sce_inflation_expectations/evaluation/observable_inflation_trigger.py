"""Observable price-pressure triggers, paired controls and true differences."""
import argparse
import csv
from pathlib import Path

import numpy as np
from scipy.optimize import lsq_linear

from ..experiments.full_a_core_normal import ROOT,read,write,sha,fresh,checked
from ..submission_tools.reproduce import no_network
from .full_a_macro_calibration import fit_ridge,predict,features
from .anomaly_year_calibration import eligible_training_indices
from .aggregate_blend import metrics
from .metrics import paired_month_mae_interval

SOURCE=ROOT/'outputs/sce_dynamic_fair_benchmark_20261026_v1'
PROTOCOL=ROOT/'docs/workstreams/20261026_dynamic_presentation/observable_trigger_protocol.json'


def training_threshold(rows):
    values=np.array([r['cpi_change_pp'] for r in rows],float)
    if not len(values) or not np.isfinite(values).all():raise ValueError('Finite training predictors required')
    return max(0.,float(np.quantile(values,.75)))


def signal_features(row,threshold):
    f=features(row,'expanded_model_pp')
    delta=float(row['cpi_change_pp']);ds=float(row['sim_change'])
    d=float(delta>threshold+1e-12);positive=max(delta,0.)
    f.update(lag_y_change=row['lag_y_change'],sim_change=ds,trigger=d,pos_cpi=positive,
             trigger_pos_cpi=d*positive,trigger_sim_change=d*ds,
             underreaction=d*max(delta-ds,0.))
    return f


def constrained_fit(x,y,alpha,nonnegative):
    if not nonnegative:return fit_ridge(x,y,alpha)
    x,y=np.asarray(x,float),np.asarray(y,float)
    if alpha<0 or not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('Invalid fitting arrays')
    mean=x.mean(0);std=x.std(0);active=std>1e-12;scale=np.where(active,std,1.)
    z=(x[:,active]-mean[active])/scale[active];centre=float(y.mean());active_ids=np.flatnonzero(active)
    beta=np.zeros(x.shape[1])
    if len(active_ids):
        lower=np.array([0. if j in nonnegative else -np.inf for j in active_ids])
        design=np.vstack([z,np.sqrt(alpha)*np.eye(len(active_ids))])
        target=np.r_[y-centre,np.zeros(len(active_ids))]
        result=lsq_linear(design,target,bounds=(lower,np.full(len(active_ids),np.inf)),tol=1e-11,max_iter=2000)
        if not result.success:raise ValueError('Bounded ridge failed')
        beta[active]=result.x
    raw=beta/scale
    return dict(alpha=float(alpha),mean=mean.tolist(),scale=scale.tolist(),
       standardised_coefficients=beta.tolist(),coefficients=raw.tolist(),
       intercept=float(centre-mean@raw),nonnegative_columns=list(nonnegative),
       constant_columns_unlearned=np.flatnonzero(~active).tolist())


def design(rows,names,threshold):
    return np.array([[signal_features(r,threshold)[n] for n in names] for r in rows])


def sign_columns(names):
    return [i for i,n in enumerate(names) if n in {'pos_cpi','underreaction'}]


def fit_initial(rows,names):
    if len(rows)!=23:raise ValueError('Exactly23 pre2021 complete-difference rows required')
    inner=rows[:17];validation=rows[17:];threshold=training_threshold(inner)
    x=design(inner,names,threshold);vx=design(validation,names,threshold)
    y=np.array([r['truth_pp']-r['baseline_pp'] for r in inner]);vy=np.array([r['truth_pp']-r['baseline_pp'] for r in validation])
    candidates=[]
    for alpha in [0,.1,1,10,100]:
        fit=constrained_fit(x,y,alpha,sign_columns(names))
        candidates.append(dict(alpha=alpha,validation_mae_pp=float(np.mean(abs(predict(vx,fit)-vy)))))
    minimum=min(v['validation_mae_pp'] for v in candidates)
    alpha=max(v['alpha'] for v in candidates if v['validation_mae_pp']<=minimum+1e-12)
    final_threshold=training_threshold(rows);xx=design(rows,names,final_threshold)
    yy=np.array([r['truth_pp']-r['baseline_pp'] for r in rows])
    return dict(**constrained_fit(xx,yy,alpha,sign_columns(names)),features=names,
       threshold=final_threshold,inner_threshold=threshold,validation=candidates,
       trigger_training_n=sum(signal_features(r,final_threshold)['trigger'] for r in rows))


def csv_write(path,rows):
    with path.open('w') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)


def complete_differences(raw):
    rows=[]
    for previous,current in zip(raw,raw[1:]):
        prev,current=dict(previous),dict(current)
        for row in [prev,current]:
            for k in ['truth_pp','baseline_pp','expanded_model_pp','cpi_yoy_pp','cpi_change_pp']:row[k]=float(row[k])
        def index(month):return int(month[:4])*12+int(month[4:])
        if index(current['month'])-index(prev['month'])!=1:raise ValueError('Contiguous months required')
        if not np.isclose(current['baseline_pp'],prev['truth_pp'],atol=1e-12):
            raise ValueError('Public anchor is not adjacent SCE; cannot claim first difference')
        if previous['truth_published_date']>current['as_of'][:10]:raise ValueError('Unavailable lagged SCE')
        current['lag_y_change']=prev['truth_pp']-prev['baseline_pp']
        current['sim_change']=current['expanded_model_pp']-prev['expanded_model_pp']
        rows.append(current)
    return rows


def run(out):
    out=fresh(out);protocol=read(PROTOCOL);write(out/'protocol.json',protocol)
    checked(SOURCE,read(SOURCE/'manifest.json')['files_sha256'])
    with (SOURCE/'monthly_inputs_public.csv').open() as f:rows=complete_differences(list(csv.DictReader(f)))
    early=[r for r in rows if r['month']<'202101'];test=[r for r in rows if r['month']>='202101']
    if len(early)!=23 or len(test)!=58:raise ValueError('Expected23/58 split')
    if any(r['truth_published_date']>test[0]['as_of'][:10] for r in early):raise ValueError('Initial label unavailable')
    anchor=np.array([r['baseline_pp'] for r in test]);truth=np.array([r['truth_pp'] for r in test])
    prediction={'persistence':anchor,'raw_simulation':np.array([r['expanded_model_pp'] for r in test])};fits={}
    for family,names in protocol['families'].items():
        fit=fit_initial(early,names);fits[family]=fit;threshold=fit['threshold']
        prediction[family+'_fixed']=anchor+predict(design(test,names,threshold),fit)
        values=[];audit=[]
        for row in test:
            known=eligible_training_indices(rows,row);training=[rows[int(i)] for i in known]
            x=design(training,names,threshold);y=np.array([r['truth_pp']-r['baseline_pp'] for r in training])
            now=constrained_fit(x,y,fit['alpha'],sign_columns(names))
            values.append(row['baseline_pp']+predict(design([row],names,threshold),now)[0])
            audit.append(dict(month=row['month'],n_training=len(training),last_training_month=training[-1]['month'],
              last_training_publication=training[-1]['truth_published_date'],
              trigger_training_n=sum(signal_features(r,threshold)['trigger'] for r in training),**now))
        prediction[family+'_expanding']=np.array(values);fits[family]['expanding_fits']=audit
    write(out/'fits_sealed_before_scores.json',fits)
    threshold=training_threshold(early);triggers=np.array([signal_features(r,threshold)['trigger']>0 for r in test])
    periods={'year2021':np.arange(12),'year2021_H1':np.arange(6),'year2021_H2':np.arange(6,12),
        'year2022':np.arange(12,24),'later34':np.arange(24,58),'all58':np.arange(58),
        'trigger_months':np.flatnonzero(triggers),'nontrigger_months':np.flatnonzero(~triggers)}
    result={k:{p:dict(n=len(ix),**metrics(values[ix],truth[ix])) for p,ix in periods.items() if len(ix)} for k,values in prediction.items()}
    pairs={}
    for control,model in [('level_macro','level_sim'),('difference_macro','difference_sim'),
                          ('trigger_macro','trigger_sim'),('bounded_macro','bounded_sim')]:
        for mode in ['fixed','expanding']:
            no,yes=control+'_'+mode,model+'_'+mode
            pairs[yes+'_versus_'+no]={p:paired_month_mae_interval(prediction[yes][ix]-truth[ix],prediction[no][ix]-truth[ix],
                  block_length=min(3,len(ix)),draws=2000,seed=20261026) for p,ix in periods.items() if len(ix)}
    public=[dict(month=r['month'],truth_pp=r['truth_pp'],cpi_change_pp=r['cpi_change_pp'],
        sim_change_pp=r['sim_change'],trigger=bool(triggers[j]),
        **{k:float(v[j]) for k,v in prediction.items()}) for j,r in enumerate(test)]
    csv_write(out/'monthly_public.csv',public)
    summary=dict(status='completed_observable_trigger_diagnostic',protocol=protocol,results=result,fits=fits,
        paired_comparisons=pairs,threshold_pp=threshold,pre2021_trigger_count=int(sum(signal_features(r,threshold)['trigger'] for r in early)),
        pre2021_month_count=23,trigger_months=[r['month'] for r,flag in zip(test,triggers) if flag],
        new_api_calls=0,new_density_fits=0,production_changed=False)
    write(out/'summary.json',summary)
    sources=[PROTOCOL,SOURCE/'manifest.json',SOURCE/'monthly_inputs_public.csv',Path(__file__)]
    write(out/'manifest.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
         files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('TRIGGER',threshold,summary['pre2021_trigger_count'],'/',23)
    for k,v in result.items():print(k,{p:round(v[p]['mae_pp'],6) for p in ['year2021','year2021_H1','year2021_H2','year2022','later34','all58']})


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    with no_network():run(a.out)


if __name__=='__main__':main()
