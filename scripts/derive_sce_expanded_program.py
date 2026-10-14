#!/usr/bin/env python3
"""Materialize every program prediction WITHOUT reading current real answers.

The scored common-case export is an evaluation subset. This separate complete
prediction export depends only on the locked coefficient, prior inputs and
stored new-signal actions, including respondents with unscorable current truth.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import duckdb
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.evaluation.expanded_state import combine

def main():
    p=argparse.ArgumentParser();p.add_argument('--folder',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('Fresh output file required')
    plan=json.loads((a.folder/'manifest.json').read_text());lock=json.loads((a.folder/'weight_lock.json').read_text());alpha=lock['alpha']
    rows=[]
    for job in plan['jobs']:
        if job['arm']!='new_signal':continue
        past=json.loads((a.folder/str(job['month'])/'past_private.json').read_text())
        conn=duckdb.connect(str(ROOT/'outputs/local_runs'/job['run_id']/'study.duckdb'),read_only=True)
        actions=conn.execute("SELECT agent_id, action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall();conn.close()
        if len(actions)!=96:raise ValueError('Incomplete stored source actions')
        for aid,payload in sorted(actions):
            payload=json.loads(payload) if isinstance(payload,str) else payload;prior=past[aid]['prior']
            previous=[prior['q9'][f'bin{i}'] for i in range(1,11)]
            if alpha==0:
                bins=previous;point=prior['point_pct'];status='valid_previous_only'
            elif payload.get('validation_status')=='valid':
                bins=combine(previous,[payload[f'q9_bin{i}'] for i in range(1,11)],alpha)
                point=(1-alpha)*prior['point_pct']+alpha*payload['point_pct'] if prior['point_pct'] is not None else None;status='valid_combination'
            else:bins=point=None;status='unavailable_new_signal'
            rows.append(dict(month=job['month'],phase=job['phase'],repeat=job['repeat'],agent_id=aid,
                             alpha=alpha,final_q9=bins,final_q8=point,status=status,signal_run_id=job['run_id'],
                             source_prior_sha256=hashlib.sha256((a.folder/str(job['month'])/'past_private.json').read_bytes()).hexdigest()))
    a.out.write_text(json.dumps({'weight_lock_sha256':hashlib.sha256((a.folder/'weight_lock.json').read_bytes()).hexdigest(),
                               'uses_current_real_answers':False,'new_api_calls':0,'predictions':rows},ensure_ascii=False,indent=2)+'\n')
    print('Generated',len(rows),'complete predictions; no current truth read, no API calls')

if __name__=='__main__':main()
