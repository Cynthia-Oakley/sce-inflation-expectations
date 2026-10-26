"""Secondary guardrails; cannot reselect the primary frozen grid."""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

from .grid_dimension_selection import (ROOT, dump, sha, encode, fit_subsets,
    equal_month_weights, residualize, bootstrap_indices)


def within_r2(y, pred, w, months):
    yr=residualize(y,w,months).ravel(); pr=residualize(pred,w,months).ravel()
    return float(1-np.sum(w*(yr-pr)**2)/np.sum(w*yr**2))


def run(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    out.mkdir(parents=True)
    s=json.loads((source/'summary.json').read_text())
    thresholds={}
    for threshold in [.85,.9,.95]:
        valid=[m for m in s['candidates'] if m['role']=='candidate' and m['support']['development']['mean_frame_supported_mass']>=threshold]
        best=max(valid,key=lambda m:m['development_cv']['composite_gain'])
        loss=np.asarray(best['development_cv']['monthly_domain_losses']).mean(1)
        se=float(np.std([loss[i].mean() for i in bootstrap_indices(len(loss))],ddof=1))
        near=[m for m in valid if m['development_cv']['composite_gain']>=best['development_cv']['composite_gain']-se]
        win=min(near,key=lambda m:(m['cartesian_cells'],len(m['fields']),-m['development_cv']['composite_gain'],m['name']))
        thresholds[str(threshold)]={'recommended':win['name'],'best':best['name'],'screen_passed':len(valid)}
    models={m['name']:m for m in s['candidates']}
    rec=models[s['selection']['recommended']]
    baseline=models['education_x_attachment_6']
    delta=np.asarray(baseline['development_cv']['monthly_domain_losses'])-np.asarray(rec['development_cv']['monthly_domain_losses'])
    boot=np.array([delta[i].mean(0) for i in bootstrap_indices(len(delta))])
    paired={'domain_gain_vs_old_six':delta.mean(0).tolist(),
            'domain_ci95':np.quantile(boot,[.025,.975],axis=0).T.tolist(),
            'composite_gain_vs_old_six':float(delta.mean()),
            'composite_ci95':np.quantile(boot.mean(1),[.025,.975]).tolist()}
    f=pd.read_parquet(source/'analysis_frame_private.parquet')
    f=f.loc[np.isfinite(f.Q8v2part2)].copy()
    train=f.loc[f.date.le(202212)].copy()
    _,blocks=encode(train,include_attachment=True)
    shortlist=[]
    for name in ['education_x_attachment_6',s['selection']['recommended'],'education+numeracy+income+gender','all_eight_additive']:
        row=models[name]; col=[j for k in row['fields'] for j in blocks[k]]
        shortlist.append({'name':name,'columns':col})
    q8={}
    for label,bound in [('untrimmed',None),('cap_100_sensitivity',100)]:
        y=train.Q8v2part2.to_numpy(float)
        if bound: y=np.clip(y,-bound,bound)
        y=y[:,None]; x,_=encode(train,include_attachment=True)
        fold=np.array([int.from_bytes(hashlib.sha256(f'20261023:{int(u)}'.encode()).digest()[:8],'big')%4 for u in train.userid])
        pred=[np.empty_like(y) for _ in shortlist]
        for k in range(4):
            keep,test=fold!=k,fold==k
            betas=fit_subsets(x[keep],y[keep],equal_month_weights(train.loc[keep]),train.date.to_numpy()[keep],shortlist)
            for m,b,p in zip(shortlist,betas,pred):p[test]=x[test][:,m['columns']]@b
        values={m['name']:{'development_cv_within_r2':within_r2(y,p,equal_month_weights(train),train.date.to_numpy())} for m,p in zip(shortlist,pred)}
        for period,(start,end) in {'2023_2024':(202301,202412),'2025_01_10':(202501,202510)}.items():
            sub=f.loc[f.date.between(start,end)&~f.userid.isin(train.userid)].copy()
            yy=sub.Q8v2part2.to_numpy(float)
            if bound:yy=np.clip(yy,-bound,bound)
            xx,_=encode(sub,include_attachment=True)
            betas=fit_subsets(x,y,equal_month_weights(train),train.date.to_numpy(),shortlist)
            for m,b in zip(shortlist,betas):
                values[m['name']][period+'_within_r2']=within_r2(yy,xx[:,m['columns']]@b,equal_month_weights(sub),sub.date.to_numpy())
        q8[label]=values
    result={'status':'secondary_sensitivity_not_new_primary_selection','new_api_calls':0,'q9_refits':0,
            'coverage_threshold_sensitivity':thresholds,'paired_cv_vs_old_six':paired,
            'q8_guardrail':q8,'q8_development_n':len(train),
            'limits':['Same Q9-valid common support with finite Q8, not all Q8 respondents.',
                      'Raw Q8 contains extreme values up to 10000; cap is sensitivity only.',
                      'Within-month structural R2, not national median MAE.',
                      'Sensitivity cannot silently replace primary development selection.'],
            'source_sha256':{str((source/'summary.json').relative_to(ROOT)):sha(source/'summary.json'),
                             str(Path(__file__).relative_to(ROOT)):sha(__file__)}}
    dump(out/'summary.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result
