#!/usr/bin/env python3
"""Offline, bounded CES revision example using verified local BLS PDFs."""
import argparse
from copy import deepcopy
from datetime import datetime
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import build_sce_environment as bls
from studies.sce_inflation_expectations.environment_authoring.vintages import select_vintages

MONTHS='January February March April May June July August September October November December'.split()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-pool',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    out=args.out;out.mkdir(parents=True,exist_ok=False)
    pool=[json.loads(l) for l in args.source_pool.read_text().splitlines() if l]
    first=[r for r in pool if r['measure'].startswith('Total nonfarm payroll') and '2021-03'<=r['reference_period']<='2021-06']
    if len(first)!=4:raise ValueError('four verified initial employment releases required')
    for row in first:row['vintage_kind']='initial_release'
    revisions=[]
    pattern=r'(?:The change in total nonfarm payroll employment for|the change for)\s+(\w+)\s+was revised (up|down) by ([\d,]+), from ([+−-]?[\d,]+) to ([+−-]?[\d,]+)'
    for original in first[1:]:
        path=ROOT/original['source_file']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=original['source_sha256']:raise ValueError('PDF hash mismatch')
        text=' '.join(bls._first_pages_text(path,n_pages=5).split())
        rd=datetime.fromisoformat(original['published_at']).date()
        if not bls._verify_document('empsit',original['reference_period'],rd,text):raise ValueError('header mismatch')
        matches=list(re.finditer(pattern,text,re.I))
        if len(matches)!=2:raise ValueError('expected two explicit monthly revision statements')
        y,m=map(int,original['reference_period'].split('-'))
        for match in matches:
            month,direction,amount,old,new=match.groups();ref_m=MONTHS.index(month.capitalize())+1
            ref_y=y-(ref_m>m)
            if not 1<=(y*12+m)-(ref_y*12+ref_m)<=2:raise ValueError('revision month outside two preceding months')
            parse=lambda v:int(v.replace(',','').replace('−','-'))
            delta=parse(new)-parse(old)
            if delta!=(1 if direction=='up' else -1)*parse(amount):raise ValueError('revision arithmetic inconsistent')
            row=deepcopy(original)
            row.update(reference_period=f'{ref_y}-{ref_m:02d}',value=parse(new)/1000,
                       vintage_kind='revision',
                       signal_id=f"bls_nonfarm_payroll_change_sa_{ref_y}_{ref_m:02d}_revised_{rd.isoformat()}",
                       source_quote=match.group(),prior_reported_value=parse(old)/1000,
                       source_version=original['source_version']+' monthly revision')
            revisions.append(row)
    records=first+revisions;examples=[]
    for cutoff in ['2021-04-30T23:59:59-04:00','2021-05-31T23:59:59-04:00','2021-06-30T23:59:59-04:00','2021-07-31T23:59:59-04:00']:
        examples.append({'cutoff':cutoff,'policies':{policy:[{k:r[k] for k in ['reference_period','value','unit','published_at','source_version']}
                         for r in select_vintages(records,cutoff,policy=policy)] for policy in ['first_release','as_of_latest']}})
    (out/'source_versions.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    summary={'initial_records':len(first),'monthly_revisions':len(revisions),'examples':examples,
             'scope':'bounded 2021 CES example; does not cover annual benchmarks, CPI annual SA revisions or all input series',
             'real_llm_calls':0,'source_configs_modified':False}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
