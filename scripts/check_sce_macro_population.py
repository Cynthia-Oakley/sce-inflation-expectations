#!/usr/bin/env python3
"""No API: compare macro profile forecasts against lagged SCE distributions."""
import argparse,hashlib,json,sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import calendar
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.macro_population import month_shift,employment_shares,forecast
from studies.sce_inflation_expectations.environment_authoring.vintages import timestamp
UE='Civilian unemployment rate, seasonally adjusted'
PAY='Total nonfarm payroll employment 1-month change, seasonally adjusted'


def read_macro(path):
    selected=[];seen=set()
    for line in path.read_text().splitlines():
        r=json.loads(line)
        if r['measure'] not in (UE,PAY):continue
        if r['eligibility']!='eligible' or not r['signal_id'].endswith('_initial'):raise ValueError('only verified initial releases allowed in this diagnostic')
        key=(r['measure'],r['reference_period'])
        if key in seen:raise ValueError('duplicate macro observation')
        seen.add(key);r['month']=int(r['reference_period'].replace('-',''));selected.append(r)
    return selected


def build_rows(population, macro):
    waves={r['month']:r for r in population};rows=[]
    for month,wave in sorted(waves.items()):
        if month<202001:continue
        donor=month_shift(month,-10)
        if donor not in waves:continue
        previous=month_shift(month,-1);y,m=divmod(previous,100)
        asof=datetime.fromisoformat(f'{y}-{m:02d}-{calendar.monthrange(y,m)[1]}T23:59:59').replace(tzinfo=ZoneInfo('America/New_York'))
        known=[r for r in macro if timestamp(r['published_at'])<=asof]
        by_measure={measure:{r['month']:r for r in known if r['measure']==measure} for measure in [UE,PAY]}
        if not all(by_measure.values()):continue
        ue,pay=by_measure[UE],by_measure[PAY];latest_ue=max(ue);latest_pay=max(pay)
        refs=[donor,month_shift(latest_ue,-3)]
        pay_refs=[month_shift(end,-i) for end in [latest_pay,donor] for i in range(3)]
        if any(r not in ue for r in refs) or any(r not in pay for r in pay_refs):continue
        features=[ue[latest_ue]['value']-ue[donor]['value'],
                  (sum(pay[month_shift(latest_pay,-i)]['value'] for i in range(3))-sum(pay[month_shift(donor,-i)]['value'] for i in range(3)))/1000.,
                  ue[latest_ue]['value']-ue[month_shift(latest_ue,-3)]['value']]
        base=employment_shares(waves[donor]['margins']['employment_status']['weighted'])
        donor_months=[month_shift(donor,-i) for i in range(12)]
        if any(r not in waves for r in donor_months):continue
        mixture=np.mean([employment_shares(waves[r]['margins']['employment_status']['weighted']) for r in donor_months],axis=0)
        truth=employment_shares(wave['margins']['employment_status']['weighted'])
        rows.append({'month':month,'as_of':asof.isoformat(),'donor_end':donor,'base':base.tolist(),'mixture':mixture.tolist(),
                     'truth':truth.tolist(),'features':features,'latest_unrate_month':latest_ue,'latest_payroll_month':latest_pay,
                     'macro_version_policy':'first_release_only','label_availability':'assumed_t_minus_10_not_historical_posting_proof'})
    return rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--population-stats',type=Path,required=True);ap.add_argument('--macro-pool',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    rows=build_rows(json.loads(args.population_stats.read_text()),read_macro(args.macro_pool));predictions=[]
    for test in rows:
        if sum(r['month']<=test['donor_end'] for r in rows)<24:continue
        methods={'latest_public_wave':test['base'],'past_12_public_waves':test['mixture']};audits={}
        for method in ['historical_drift','unrate_ols','macro_ridge']:
            p,audit=forecast(rows,test,label_cutoff=test['donor_end'],method=method)
            if audit['max_train_month']>test['donor_end']:raise ValueError('training label leak')
            methods[method]=p.tolist();audits[method]=audit
        predictions.append({**test,'predictions':methods,'fit_audit':audits})
    if not predictions:raise ValueError('no common forecast months')
    metrics={}
    for method in predictions[0]['predictions']:
        err=np.array([np.array(r['predictions'][method])-r['truth'] for r in predictions])*100
        metrics[method]={'employed_mae_pp':float(np.abs(err[:,0]).mean()),'sce_unemployed_label_mae_pp':float(np.abs(err[:,1]).mean()),
                         'distribution_mean_tvd':float(np.abs(err).sum(axis=1).mean()/200),
                         'employed_bias_pp':float(err[:,0].mean()),'employed_rmse_pp':float(np.sqrt((err[:,0]**2).mean()))}
    correlations={}
    for name,i in [('unrate_gap_pp',0),('three_month_payroll_sum_gap_millions',1),('unrate_three_month_change_pp',2)]:
        correlations[name]=float(np.corrcoef([r['features'][i] for r in rows],[r['truth'][0]-r['base'][0] for r in rows])[0,1])
    summary={'feature_months':len(rows),'evaluated_months':len(predictions),'evaluation_start':predictions[0]['month'],'evaluation_end':predictions[-1]['month'],
             'metrics':metrics,'descriptive_employment_change_correlations':correlations,
             'features':['unrate_gap_since_donor_month','three_month_payroll_sum_gap_millions','unrate_three_month_change'],
             'min_train_labels':24,'source_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.population_stats,args.macro_pool]},
             'created_at_utc':datetime.now(timezone.utc).isoformat(),
             'code_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__).resolve(),ROOT/'studies/sce_inflation_expectations/macro_population.py']},
             'status':'exploratory aggregate distribution backtest; not blind evaluation or validated B simulation',
             'limitations':['historical SCE posting dates assumed via t-minus-10; current micro snapshots',
                            'macro first-release variant; later annual revisions not used','no CPI/SCE answers or LLM predictions involved',
                            'COVID months enter descriptive relations/training, but not forecast evaluation due insufficient available earlier labels',
                            'income model and population reweighting not implemented'],'real_llm_calls':0}
    for filename,data in [('feature_rows.json',rows),('predictions.json',predictions),('summary.json',summary)]:
        (args.out/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
