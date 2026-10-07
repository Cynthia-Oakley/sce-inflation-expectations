#!/usr/bin/env python3
"""Build isolated B month-start input drafts from verified local release archives.

No downloading, model calls, SCE answers or simulation configuration writes.
Series retain different last-available reference periods and missing-month notes.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timedelta
import hashlib,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import extend_sce_environment_sources as src
import build_sce_environment as bls
import build_sce_environment_v2 as ev
import build_nyt_events as nyt
from sce_release_available import cpi_available
from studies.sce_inflation_expectations.environment_authoring.availability import select_available
from socioverse.schemas import EnvironmentBundle


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def json_read(path):return json.loads(path.read_text())
def lines(path):return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def release_pool(folders):
    manifests,components={},{}
    for folder in folders:
        for row in json_read(folder/'bls_manifest.json'):
            key=(row['kind'],row['reference_period'])
            if key in manifests and manifests[key]['sha256']!=row['sha256']:
                raise ValueError('conflicting release copies')
            manifests[key]=row
        for row in lines(folder/'components_cpi.jsonl'):
            key=(row['reference_period'],row['signal_id'])
            if key in components and components[key]['value']!=row['value']:
                raise ValueError('conflicting component copies')
            components[key]=row
    rows,notes,head_checks=[] ,[],[]
    for (_kind,ref),record in sorted(manifests.items()):
        path=ROOT/record['file']
        if digest(path)!=record['sha256']:raise ValueError('PDF hash changed')
        text=bls._first_pages_text(path)
        rd=datetime.fromisoformat(record['published_at']).date()
        if not bls._verify_document(record['kind'],ref,rd,text):raise ValueError('release header mismatch')
        common={k:record[k] for k in ('reference_period','published_at','source_url')}
        common.update(source_sha256=record['sha256'],source_file=record['file'],eligibility='eligible')
        def add(signal,measure,value,unit='percent',quote=None):
            rows.append(dict(common,signal_id=f'bls_{signal}_{ref.replace("-","_")}_initial',
                             measure=measure,value=value,unit=unit,source_version=f'USDL-{usdl}',source_quote=quote))
        if record['kind']=='cpi':
            values=cpi_available(text,ref);usdl=values['usdl']
            add('cpi_u_all_items_yoy_nsa','CPI-U all items 12-month percent change, not seasonally adjusted',values['cpi_yoy_nsa_pct']['value'],quote=values['cpi_yoy_nsa_pct']['quote'])
            head_checks.append({'signal_id':'cpi_all_items_yoy','reference_period':ref,'published_at':common['published_at'][:10],'value':values['cpi_yoy_nsa_pct']['value']})
            if values['cpi_mom_sa_pct'] is not None:
                add('cpi_u_all_items_mom_sa','CPI-U all items 1-month percent change, seasonally adjusted',values['cpi_mom_sa_pct']['value'],quote=values['cpi_mom_sa_pct']['quote'])
                head_checks.append({'signal_id':'cpi_all_items_mom','reference_period':ref,'published_at':common['published_at'][:10],'value':values['cpi_mom_sa_pct']['value']})
            else:
                notes.append({'reference_period':ref,'field':'cpi_mom_sa_pct','status':'structural_missing','reason':values['missing_reason']})
                # The two-month number remains in audit only, not a replacement monthly input.
                notes[-1]['two_month_sa_pct_audit_only']=values['cpi_two_month_sa_pct']['value']
            for signal,measure in ev.COMPONENT_MEASURES.items():
                item=components.get((ref,signal))
                if item is None:raise ValueError(f'missing component {ref} {signal}')
                add(signal+'_nsa',measure,item['value'],quote=item['quote'])
        else:
            values=bls.transcribe_empsit(text,ref);usdl=values['usdl']
            add('unemployment_rate_sa','Civilian unemployment rate, seasonally adjusted',values['unemployment_rate_pct']['value'],quote=values['unemployment_rate_pct']['quote'])
            add('nonfarm_payroll_change_sa','Total nonfarm payroll employment 1-month change, seasonally adjusted',values['nonfarm_payroll_change_k']['value'],'thousands',values['nonfarm_payroll_change_k']['quote'])
    comp_checks=src.check_component_html(list(components.values()))
    checks=comp_checks+src.check_component_html(head_checks)
    if any(r['status']!='agree' for r in checks):
        bad=[(r['reference_period'],r['signal_id'],r['status']) for r in checks if r['status']!='agree']
        raise ValueError(f'independent source checks incomplete: {bad}')
    notes += [{'reference_period':'2025-10','field':field,'status':'structural_missing',
               'reason':'BLS shutdown: CPI and household unemployment month unavailable; no synthetic replacement'}
              for field in ['cpi','unemployment']]
    return rows,notes,checks,list(manifests.values())


def gasoline_pool(csv_path):
    original=ev.GAS_WEEKLY_CSV
    try:
        ev.GAS_WEEKLY_CSV=csv_path
        monthly=ev.load_gasoline_weekly()
    finally:ev.GAS_WEEKLY_CSV=original
    rows=[]
    for ref,v in monthly.items():
        pub=(datetime.fromisoformat(v['last_obs_date'])+timedelta(days=3)).replace(hour=17,tzinfo=bls.RELEASE_TZ).isoformat()
        common=dict(reference_period=ref,published_at=pub,source_version='FRED GASREGW (EIA weekly retail, Monday obs)',
                    source_url='https://fred.stlouisfed.org/series/GASREGW',source_sha256=digest(csv_path),
                    eligibility='vintage_unverified',published_at_basis='last_weekly_observation_plus_3_days_assumption',
                    note='current snapshot; monthly mean of weekly observations; publication day inferred')
        rows.append(dict(common,signal_id='eia_gasoline_retail_regular_mean_'+ref.replace('-','_'),
                         measure='U.S. regular all formulations retail gasoline price, monthly mean of weekly observations',value=v['price_mean'],unit='dollars_per_gallon'))
        if 'yoy_pct' in v:
            rows.append(dict(common,signal_id='eia_gasoline_retail_regular_yoy_'+ref.replace('-','_'),
                             measure='Retail gasoline price 12-month percent change (monthly means)',value=v['yoy_pct'],unit='percent'))
    return rows


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source-dir',action='append',type=Path,required=True)
    ap.add_argument('--template',type=Path,required=True)
    ap.add_argument('--gas-weekly-csv',type=Path,required=True)
    ap.add_argument('--targets',required=True)
    ap.add_argument('--latest-observed-sce',required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();targets=bls.parse_targets(args.targets)
    args.out.mkdir(parents=True,exist_ok=False)
    pool,notes,checks,manifests=release_pool(args.source_dir)
    bundle=json_read(args.template);bundle=deepcopy(bundle)
    bundle['layers']=[l for l in bundle['layers'] if l['name']!='agent_profile_context']
    for layer in bundle['layers']:
        layer['source']=str(args.out/('selected_news.jsonl' if layer['name']=='nyt_salient_events' else 'source_observations.jsonl'))
        layer['description']='Separate last-available first-release observations; preserve actual dates and gaps.'
    if bundle['scheduled_events']:raise ValueError('unexpected scheduled events in template')
    provider=bundle['provider_args'];provider['e_version']='available_release_B_draft_20261007'
    provider['evidence_class']='mixed_source_vintage_status'
    provider['research_line']='B_previous_month_end_input_draft'
    provider['targets']=[];provider['signals_by_step']={};provider['events_by_step']={}
    provider['excluded_sources']=['nyfed_sce'];provider['e_v2_layers']=['available_bls_history','flagged_gasoline_history','previous_month_nyt']
    provider['source_status']={'bls':'archived_initial_release_verified','eia_gasoline':'current_snapshot_unverified','nyt':'archive_text_vintage_unverified'}
    bundle['information_program']={'broadcasts':[]}
    step_checks=[];full_pool=pool+gasoline_pool(args.gas_weekly_csv)
    strict=deepcopy(bundle);strict['provider_args']['e_version']='available_release_B_BLS_only_draft_20261007'
    strict['provider_args']['source_status']={'bls':'archived_initial_release_verified'}
    strict['provider_args']['excluded_sources']=['nyfed_sce','GASREGW_current_snapshot','NYT_current_archive_text']
    strict['provider_args']['e_v2_layers']=['available_bls_history']
    strict['layers']=[l for l in strict['layers'] if l['name'] not in ('eia_gasoline_retail_price','nyt_salient_events')]
    for i,target in enumerate(targets):
        cutoff=bls.as_of_for(target);key=str(i)
        selected,series_notes=select_available(full_pool,cutoff)
        source_month=ev.shift_month(target,-1)
        data=src.prepare_news(source_month,False,'',None)
        raw=(nyt.ROOT/'data/raw/nyt_archive'/f'{source_month}.json').read_bytes()
        docs=[d for d in data['response']['docs'] if d.get('pub_date','')[:10]<=cutoff[:10]]
        events=nyt.select_events(docs,source_month,hashlib.sha256(raw).hexdigest(),30)
        event_ids=set();event_rows=[]
        for e in events:
            if e['event_id'] in event_ids:continue
            event_ids.add(e['event_id']);event_rows.append({k:e[k] for k in ('event_id','pub_date','tier','headline','abstract','section_name','web_url','matched_keywords')})
            event_rows[-1].update(text_vintage_status='unverified_archive_snapshot',selection_cutoff=cutoff[:10])
        target_spec={'target_month':target,'as_of':cutoff}
        provider['targets'].append(target_spec);provider['signals_by_step'][key]=selected;provider['events_by_step'][key]=event_rows
        strict['provider_args']['targets'].append(deepcopy(target_spec))
        strict['provider_args']['signals_by_step'][key]=[r for r in selected if r['eligibility']=='eligible']
        strict['provider_args']['events_by_step'][key]=[]
        step_checks.append({'target_month':target,'as_of':cutoff,'signals':len(selected),'news':len(event_rows),
                            'series':series_notes,'evaluation_truth_status':'observed' if target<=args.latest_observed_sce else 'not_yet_verified_released'})
    EnvironmentBundle.model_validate(bundle);EnvironmentBundle.model_validate(strict)
    for name,obj in [('environment_B_full_draft.json',bundle),('environment_B_bls_only_draft.json',strict),
                     ('availability_audit.json',step_checks),('structural_missing.json',notes),('independent_value_checks.json',checks),('bls_manifest.json',manifests)]:src.write_json(args.out/name,obj)
    src.write_jsonl(args.out/'source_observations.jsonl',full_pool)
    src.write_jsonl(args.out/'selected_news.jsonl',[dict(e,target_month=targets[int(k)]) for k,rows in provider['events_by_step'].items() for e in rows])
    summary={'target_start':targets[0],'target_end':targets[-1],'target_months':len(targets),
             'latest_verified_sce':args.latest_observed_sce,'verified_bls_pdfs':len(manifests),
             'independent_value_agreements':len(checks),'schema_valid':True,'status':'B_input_draft_not_run_configuration',
             'information_cutoff':'previous month end America/New_York; per-series available first-release selection',
             'full_package_strict_pit_certified':False,'bls_only_package':'excludes current gas snapshot and current news text; source timing audited, not model-training-leakage certified',
             'unobserved_target_months':[t for t in targets if t>args.latest_observed_sce],
             'source_config_modified':False,'real_llm_calls':0,'paid_mcp_calls':0,
             'source_scope_note':'canonical report headline observations; October 2025 payroll later printed in November report not yet independently added'}
    src.write_json(args.out/'summary.json',summary)
    files=sorted(p for p in args.out.iterdir() if p.is_file())
    (args.out/'manifest.sha256').write_text(''.join(f'{digest(p)}  {p.name}\n' for p in files))
    print(json.dumps(summary))


if __name__=='__main__':main()
