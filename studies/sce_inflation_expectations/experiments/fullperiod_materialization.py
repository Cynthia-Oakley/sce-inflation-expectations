"""Offline, versioned P/E delivery over the registered 93-month coverage.

Reuses the existing field mappers and archived-release builders. Population
delivery contains no current or prior target answers: recent belief initialization
is a separate, existing adapter. Synthetic frames are distribution extensions,
not verified historical-vintage population forecasts.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import importlib
import json
import math
from pathlib import Path
import random
import shutil
import sys

from .frozen_batch import ROOT, dump, read_json, sha

OLD = ROOT / 'outputs/sce_fullperiod_data_20261021_v1'


def effective_reference(cov):
    """A cancelled-month ledger may name the fallback PDF in a different ref."""
    import re
    match=re.match(r'cpi_(\d{4})_(\d{2})_',cov['diagnostics'].get('cpi_release_file',''))
    return '-'.join(match.groups()) if match else cov['diagnostics']['ref_month']


def news_pool_for_prompts(root,target,cutoff,rules):
    """Use the complete stock rows; enrich compact duplicate-tolerant inventory
    only for a genuinely conflicting monthly archive boundary.
    """
    from ..coverage_preparation import build_news_pool,previous_month
    try:
        return build_news_pool(root,target,cutoff,rules)
    except ValueError as exc:
        if 'conflicting duplicate source article' not in str(exc): raise
    from scripts.build_sce_fullperiod_coverage import build_news_pool_tolerant
    from ..news_exposure_demo import front_page_status
    import hashlib
    compact,counts=build_news_pool_tolerant(root,target,cutoff,rules)
    docs_by_id={};sources={}
    for month in (previous_month(target),target):
        path=root/'data/raw/nyt_archive'/f'{month}.json';sources[str(path.relative_to(root))]=sha(path)
        for doc in read_json(path)['response']['docs']:
            text={'headline':(doc.get('headline') or {}).get('main') or '',
                  'abstract':doc.get('abstract') or '', 'snippet':doc.get('snippet') or ''}
            identity=doc.get('_id') or doc.get('uri') or doc.get('web_url')
            if not identity: continue
            digest=hashlib.sha256(json.dumps(text,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            aid=hashlib.sha256((identity+'\n'+digest).encode()).hexdigest()[:24]
            docs_by_id.setdefault(aid,(doc,text,identity,digest))
    rows=[]
    for record in compact:
        doc,text,identity,digest=docs_by_id[record['article_id']]
        rows.append(dict(text,**record,canonical_source_id=identity,source='NYT Archive API',
             section_name=doc.get('section_name') or '',news_desk=doc.get('news_desk') or '',
             web_url=doc.get('web_url') or '',text_sha256=digest,text_vintage_status='unverified_archive_snapshot',
             print_section=doc.get('print_section'),print_page=doc.get('print_page'),placement=front_page_status(doc)))
    return rows,counts,sources


def helpers():
    sys.path.insert(0, str(ROOT / 'scripts'))
    return (importlib.import_module('build_sce_fullperiod_sample_data'),
            importlib.import_module('build_sce_fullperiod_sample_environments'))


def finite_weight(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def systematic_pps(weights, n, seed):
    """PPS is applied once; equal expansion weights follow a weighted draw."""
    if any(finite_weight(w) is None for w in weights) or n < 1:
        raise ValueError('Positive finite donor weights and count required')
    total = sum(weights); step = total / n
    start = random.Random(seed).random() * step
    result, index, cumulative = [], 0, weights[0]
    for j in range(n):
        threshold = start + j * step
        while threshold >= cumulative and index < len(weights)-1:
            index += 1; cumulative += weights[index]
        result.append(index)
    return result


def build_population(out, months):
    import pandas as pd
    S, _ = helpers()
    S.OUT_DIR = out
    df = S.load_micro().sort_values(['userid', 'date']).reset_index(drop=True)
    if df.duplicated(['userid', 'date']).any():
        raise ValueError('Duplicate respondent-month in raw files')
    source_hashes = {str((ROOT/rel).relative_to(ROOT)): sha(ROOT/rel) for rel, _ in S.MICRO_FILES}
    q43 = {int(u): dict(zip(g.date, g.Q43)) for u, g in df.loc[df.Q43.notna()].groupby('userid')}
    d3 = {int(u): dict(zip(g.date, g.D3)) for u, g in df.loc[df.D3.notna()].groupby('userid')}
    user_dates = {int(u): sorted(g.date.tolist()) for u, g in df.groupby('userid')}
    labels = S.load_labels()
    from ..news_selection_trial import RecallRules, RULE_FILE
    rules = RecallRules(read_json(RULE_FILE))
    source_wave = int(df.date.max())
    wave = df.loc[df.date.eq(source_wave) & df.weight.map(finite_weight).notna()].copy()
    # The fixed donor order and draw are held across recent months. No fake
    # real-world panel tenure or synthetic monthly belief chain is implied.
    picks = systematic_pps(wave.weight.tolist(), 1300, 20261022)
    summary = []
    for cov in months:
        target = cov['target_month'].replace('-', ''); date = int(target)
        folder = out / target
        if (folder/'population_receipt.json').exists():
            summary.append(read_json(folder/'population_receipt.json')); continue
        synthetic = not cov['micro_truth_available']
        frame = wave.iloc[picks].copy() if synthetic else df.loc[df.date.eq(date)].copy()
        if not len(frame):
            raise ValueError('No raw frame: '+target)
        reused = None
        if not synthetic and (OLD/target/'population.json').is_file():
            reused = read_json(OLD/target/'population.json')
            reused = {r['agent_id']: r for r in reused['personas']}
        people, entries, sampling, counts = [], [], [], Counter()
        for j, (_, row) in enumerate(frame.iterrows()):
            uid = int(row.userid)
            aid = S.syn_id_for(uid, j) if synthetic else S.agent_id_for(uid)
            row = row.copy(); row['_agent_id'] = aid
            ref = source_wave if synthetic else date
            housing, hm, age, moved = S.bp._housing_carry_forward(q43, d3, uid, ref)
            hsource = (housing, hm, age, moved) if housing is not None else None
            person = deepcopy(reused[aid]) if reused else S.build_persona(row, housing, ref, synthetic)
            # Engine multiplicity is never the raw survey expansion weight.
            person['weight'] = 1.
            people.append(person)
            prior = [d for d in user_dates[uid] if d < date]
            tenure = finite_weight(row.tenure)
            if synthetic:
                status = 'synthetic_frame'
            elif tenure is None:
                status = 'unknown'
            elif not prior:
                status = 'entrant' if tenure == 1 else 'left_boundary'
            else:
                status = 'returning' if S.prev_yyyymm_of(date) in prior else 'gap_return'
            counts[status] += 1
            entry = dict(agent_id=aid, survey_entry_status=status,
                         survey_tenure=None if synthetic or tenure is None else int(tenure),
                         core_entry_status=None, synthetic=synthetic,
                         p_field_provenance=S.p_provenance(row,hsource,ref,str(row.source_file),synthetic))
            if synthetic:
                entry.update(donor_agent_id=S.agent_id_for(uid), donor_wave=source_wave,
                             pit_risk='micro_release_date_unverified',
                             synthetic_design='systematic PPS once; equal weights; fixed whole-row pool')
            entries.append(entry)
            w = None if synthetic else finite_weight(row.weight)
            sampling.append(dict(agent_id=aid, stable_priority=S.stable_priority(aid), synthetic=synthetic,
                                 survey_weight=w, weight_valid=w is not None,
                                 synthetic_expansion_weight=1. if synthetic else None))
        from socioverse.schemas import PopulationBundle
        bundle = dict(study_id=S.STUDY_ID, personas=people,
                      interaction=dict(kind='none', edges=None, adjacency_ref=None), propagation='independent',
                      provider_ref='sce_inflation_expectations.population', materialized_count=len(people),
                      provider_args=dict(source='sce_public_micro_fullframe_or_synthetic_distribution',
                          target_month=target, as_of=cov['as_of'],p_version='fullperiod_materialized_20261022_v2',
                          household_head=True,normalized_weight=1.,
                          evidence_class='synthetic_distribution_extension' if synthetic else 'A_historical_current_micro',
                          strict_B_eligible=False,
                          micro_published_at=None,
                          sampling=dict(frame_n=len(people),actual_n=0 if synthetic else len(people),
                                        synthetic_n=len(people) if synthetic else 0,design='full_frame_no_core_selection'),
                          weight_policy='model weight one; raw weights and actual selection pi only in private evaluation sidecars'))
        PopulationBundle.model_validate(bundle)
        folder.mkdir(parents=True, exist_ok=True)
        dump(folder/'population.json', bundle)
        dump(folder/'population_state_private.json',dict(target_month=target,as_of=cov['as_of'],
             anon_salt=S.ANON_SALT,persons=entries,entry_status_counts=dict(counts)))
        dump(folder/'sampling_private.json',dict(target_month=target,frame_n=len(people),persons=sampling,
             core_selection='not performed; use registered grid SRS and actual n/N',
             weight_policy='raw missing weights remain null; synthetic PPS once then equal expansion weights'))
        dump(folder/'belief_state_private.json',dict(target_month=target,persons=[],
             status='deferred_to_recent_entry_initialization_adapter_not_model_ready',
             source_note='Legacy all-past donor beliefs are deliberately not reused; no current answers in P delivery'))
        S.build_news_index(target,labels,rules,cov['as_of'])
        news = read_json(folder/'news_label_index.json')
        receipt = dict(month=target,synthetic=synthetic,frame_n=len(people),entries=dict(counts),
                       raw_weight_missing_n=sum(p['survey_weight'] is None for p in sampling) if not synthetic else None,
                       existing_profile_reused=bool(reused),news_candidates=news['n_selected'],
                       missing_news_labels=news['n_missing_labels'],new_api_calls=0,
                       strict_B_eligible=False,source_sha256=source_hashes,
                       synthetic_source_wave=source_wave if synthetic else None,
                       synthetic_note='P extension only; recent prior and publication boundary still required' if synthetic else None)
        dump(folder/'population_receipt.json',receipt); summary.append(receipt)
        dump(out/'population_summary.json',dict(months=summary,new_api_calls=0))
        print(f'{target}: P {len(people)}, synthetic={synthetic}, missing labels={news["n_missing_labels"]}',flush=True)
    return summary


def build_environments(out, months):
    _, E = helpers()
    import hashlib
    scope=hashlib.sha256('|'.join(m['target_month'] for m in months).encode()).hexdigest()[:12]
    E.OUT_DIR=out; E.SUPPORT_DIR=out/'_build_support'/scope; E.SUPPORT_DIR.mkdir(parents=True,exist_ok=True)
    # The old wrapper uses v1 only for the schema skeleton, then replaces all
    # signals/events/cutoffs. Avoid transcribing an unrelated M-2 base release
    # (which can itself be the permanently cancelled shutdown month).
    base_bundle=read_json(OLD/'201906/environment.json')
    base_external=read_json(OLD/'201906/external_events.json')
    E.v1.build_window=lambda *a, **k: dict(bundle=deepcopy(base_bundle),external_events=deepcopy(base_external))
    original_cpi=E.v1.transcribe_cpi;original_signals=E.v1._signals_for_ref;original_broadcast=E.v1._broadcast
    def partial_cpi(text,ref):
        try: return original_cpi(text,ref)
        except ValueError as exc:
            if ref!='2025-11' or 'm/m SA' not in str(exc): raise
            pdf=next((E.RAW_BLS/ref).glob('cpi_*.pdf'))
            result=E._cpi_yoy_fallback(text,ref,pdf,E._best_page_texts(pdf))
            result['cpi_mom_sa_pct']={'value':None,'quote':'not published because October prices were not collected'}
            return result
    def partial_signals(ref,cpi,emp,cu,eu,cp,ep):
        if cpi['cpi_mom_sa_pct']['value'] is not None: return original_signals(ref,cpi,emp,cu,eu,cp,ep)
        suffix=ref.replace('-','_')
        return [dict(signal_id=f'bls_{sig}_{suffix}_initial',measure=measure,value=value,unit=unit,
                 reference_period=ref,published_at=pub,source_version=f'USDL-{version}',source_url=url,eligibility='eligible')
                for sig,measure,value,unit,pub,version,url in [
                  ('cpi_u_all_items_yoy_nsa','CPI-U all items 12-month percent change, not seasonally adjusted',cpi['cpi_yoy_nsa_pct']['value'],'percent',cp,cpi['usdl'],cu),
                  ('unemployment_rate_sa','Civilian unemployment rate, seasonally adjusted',emp['unemployment_rate_pct']['value'],'percent',ep,emp['usdl'],eu),
                  ('nonfarm_payroll_change_sa','Total nonfarm payroll employment 1-month change, seasonally adjusted',emp['nonfarm_payroll_change_k']['value'],'thousands',ep,emp['usdl'],eu)]]
    def partial_broadcast(step,target,ref,cpi,emp):
        if cpi['cpi_mom_sa_pct']['value'] is not None: return original_broadcast(step,target,ref,cpi,emp)
        return dict(message_id=f'bls-{target}',channel='official_bls_release',at_step=step,ttl=1,audience='all',
             content=f"BLS {ref}: CPI increased {cpi['cpi_yoy_nsa_pct']['value']}% over 12 months. A one-month CPI change was not published because October observations were not collected.",
             note='Unavailable one-month change omitted, not imputed.')
    E.v1.transcribe_cpi=partial_cpi;E.v1._signals_for_ref=partial_signals;E.v1._broadcast=partial_broadcast
    # PDF transcription and source loaders recur in 12-month histories. Cache
    # exact files/results for this build, instead of parsing every PDF 12 times.
    for module, names in [(E.v1,['_first_pages_text','transcribe_cpi','transcribe_empsit']),
                          (E,['_best_page_texts','_transcribe_cpi_history'])]:
        for name in names:
            setattr(module,name,lru_cache(maxsize=512)(getattr(module,name)))
    refs = sorted({effective_reference(m) for m in months} |
                  {E.env2.shift_month(effective_reference(m),-i) for m in months for i in range(1,12)})
    E.env2.COMPONENTS_JSONL=complete_components(E,refs)
    component_hash=sha(E.env2.COMPONENTS_JSONL)
    E.env2.GAS_WEEKLY_CSV=E.GAS_CONSOLIDATED
    ledger=E.SUPPORT_DIR/'events_ledger_cutoff_filtered.jsonl'
    with ledger.open('w') as handle:
        for cov in months:
            window=E.env2.shift_month(cov['target_month'],-1)
            raw=ROOT/'data/raw/nyt_archive'/f'{window}.json'
            docs=[d for d in read_json(raw)['response']['docs'] if d.get('pub_date','')[:10]<=cov['as_of'][:10]]
            for event in E.nyt.select_events(docs,window,sha(raw),E.env2.EVENT_BUDGET):
                handle.write(json.dumps(event)+'\n')
    E.env2.NYT_LEDGER=ledger
    for name in ('load_components','load_gasoline_weekly','load_nyt_events'):
        setattr(E.env2,name,lru_cache(maxsize=1)(getattr(E.env2,name)))
    from ..procurement_price_views import extract_categories
    summary=[]; food_catalog={}; errors=[]
    for cov in months:
        target=cov['target_month']; key=target.replace('-',''); folder=out/key; folder.mkdir(exist_ok=True)
        try:
            if (folder/'environment_receipt.json').exists():
                receipt=read_json(folder/'environment_receipt.json')
                if receipt.get('component_sha256')==component_hash:
                    summary.append(receipt)
                    if (folder/'food_categories.json').exists(): food_catalog[key]=read_json(folder/'food_categories.json')
                    continue
                archive=E.SUPPORT_DIR/'earlier_environment_attempt'/key; archive.mkdir(parents=True,exist_ok=True)
                for name in ('environment.json','external_events.json','environment_receipt.json','food_categories.json'):
                    path=folder/name
                    if path.exists() and not (archive/name).exists(): shutil.copyfile(path,archive/name)
            # Shutdown and late employment release are taken from the existing
            # coverage contract, never silently relabelled to another period.
            ref=effective_reference(cov)
            original_ref=E.env2.reference_period_v2
            E.env2.reference_period_v2=lambda t, ref=ref: ref
            import re
            employment=None
            jobs=[]
            for path in E.RAW_BLS.glob('*/empsit_*_released_*.pdf'):
                hit=re.fullmatch(r'empsit_(\d{4})_(\d{2})_released_(\d{4})_(\d{2})_(\d{2})\.pdf',path.name)
                if hit:
                    yr,mo,py,pm,pd=hit.groups(); jobref=f'{yr}-{mo}'; published=f'{py}-{pm}-{pd}'
                    if jobref<=ref and published<=cov['as_of'][:10]: jobs.append((jobref,published))
            if jobs:
                employment=max(jobs)[0]
            try:
                result=E.build_environment_gap_tolerant(target,employment_reference=employment)
            finally:
                E.env2.reference_period_v2=original_ref
            if result['as_of'] != cov['as_of']:
                raise ValueError('Registered cutoff mismatch')
            dump(folder/'environment.json',result['bundle']); dump(folder/'external_events.json',result['external_events'])
            cpi=E.v1.ensure_release('cpi',ref,E.RAW_BLS/ref,False,E.v1.DEFAULT_PROXY)
            try:
                facts=extract_categories(E._best_page_texts(cpi['path']))
            except ValueError:
                if ref not in {'2025-11','2025-12','2026-01'}: raise
                facts=shutdown_food_categories(E._best_page_texts(cpi['path']))
            for fact in facts.values():
                fact.update(reference_period=ref,published_at=E.v1.published_at_for(cpi['release_date']),
                    source_file=str(cpi['path'].relative_to(ROOT)),source_sha256=sha(cpi['path']),
                    vintage='archived_initial_release',strict_B_eligible=False)
            dump(folder/'food_categories.json',facts); food_catalog[key]=facts
            receipt=dict(month=key,environment_available=True,food_available=True,
                         as_of=result['as_of'],signals=result['n_records'],events=result['n_events'],
                         gaps=result['data_gaps'],component_sha256=component_hash,new_api_calls=0)
            dump(folder/'environment_receipt.json',receipt); summary.append(receipt)
            print(f'{key}: E {result["n_records"]} signals, food {len(facts)}, gaps {len(result["data_gaps"])}',flush=True)
        except Exception as exc:
            error=dict(month=key,error=repr(exc),environment_written=(folder/'environment.json').exists(),
                       status='needs_source_or_parser_repair_not_ready')
            errors.append(error); print(error,flush=True)
        dump(out/'environment_summary.json',dict(months=summary,errors=errors,new_api_calls=0))
        dump(out/'food_catalog.json',food_catalog)
    return summary,errors


def shutdown_food_categories(pages):
    """Keep unpublished shutdown table cells missing, never fill with zero."""
    import re
    from ..procurement_price_views import table_text,FOOD_CATEGORIES,RESERVE_CATEGORIES
    table=table_text(pages,2); result={}
    for key,label in {'food_at_home':'Food at home',**FOOD_CATEGORIES,**RESERVE_CATEGORIES}.items():
        expression=re.escape(label).replace(r'\ ',r'\s+')+r'\s*(?:[1-9](?:\s*,\s*[1-9])*)?\s*(?:\.\s*){2,}'
        hits=list(re.finditer(expression,table))
        if len(hits)!=1: raise ValueError('Ambiguous shutdown food row: '+label)
        tail=table[hits[0].end():]
        cells=re.match(r'\s*'.join([r'(-?\d+\.\d+|[–—])']*6)+r'(?=\s|$)',tail)
        if not cells: raise ValueError('Missing shutdown row columns: '+label)
        values=[None if v in {'–','—'} else float(v) for v in cells.groups()]
        if values[1] is None: raise ValueError('Annual change also unavailable: '+label)
        result[key]=dict(category=key,label=label,yoy_nsa_percent=values[1],mom_nsa_percent=values[2],mom_sa_percent=values[5],
                        source_table=2,exact_extracted_row=table[hits[0].start():hits[0].end()+cells.end()],
                        crosschecks={'shutdown_table2_columns_retained_missing':True},
                        scope='US city average CPI-U category, not a respondent transaction',
                        use='grocery_exposure_candidate' if key in FOOD_CATEGORIES else 'shared_aggregate' if key=='food_at_home' else 'reserve_no_role_link')
    return result


def complete_components(E,refs):
    """Do not mistake a headline-only reference entry for five components.

    A shared cache also contains all-items headline records. The legacy
    builder skipped a whole reference as soon as *any* record existed there.
    Fill each named component independently, preserving source quotes.
    """
    from ..procurement_price_views import table_text,row_values
    existing={}
    for line in E.EXISTING_COMPONENTS.read_text().splitlines():
        row=json.loads(line); existing[row['reference_period'],row['signal_id']]=row
    labels={'cpi_food_yoy':'Food','cpi_food_at_home_yoy':'Food at home',
            'cpi_energy_yoy':'Energy','cpi_shelter_yoy':'Shelter','cpi_gasoline_yoy':'Gasoline (all types)'}
    records=[];gaps=[]
    for ref in refs:
        pdf=next((E.RAW_BLS/ref).glob('cpi_*.pdf'),None)
        for sig,label in labels.items():
            old=existing.get((ref,sig))
            if old:
                records.append(old);continue
            if pdf is None:
                gaps.append(dict(reference_period=ref,signal_id=sig,reason='no archived first release'));continue
            hit=E._extract_component(pdf,sig,ref)
            if hit is None:
                try:
                    pages=E._best_page_texts(pdf)
                    a,quote=row_values(table_text(pages,1),label,9)
                    b,_=row_values(table_text(pages,7),label,2)
                    if a[4]!=b[1]: raise ValueError('Table1/Table7 mismatch')
                    hit=dict(value=a[4],quote=quote,extraction='crosschecked_table1_and_table7_yoy_nsa')
                except ValueError:
                    gaps.append(dict(reference_period=ref,signal_id=sig,reason='no unambiguous crosschecked row'));continue
            import re
            py,pm,pd=re.search(r'released_(\d{4})_(\d{2})_(\d{2})',pdf.name).groups()
            records.append(dict(reference_period=ref,signal_id=sig,published_at=f'{py}-{pm}-{pd}',
                         source_pdf=str(pdf.relative_to(ROOT)),source_sha256=sha(pdf),unit='percent_12m_nsa',**hit))
    path=E.SUPPORT_DIR/'components_cpi_complete.jsonl'
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    dump(E.SUPPORT_DIR/'components_complete_gaps.json',gaps)
    print(f'Components: {len(records)} extracted, {len(gaps)} explicit gaps',flush=True)
    return path


def materialize(out,*,stage='all',months=None):
    out=Path(out).resolve(); out.mkdir(parents=True,exist_ok=True)
    coverage=OLD/'coverage.json'
    if (out/'coverage.json').exists() and sha(out/'coverage.json')!=sha(coverage):
        raise ValueError('Registered coverage changed')
    shutil.copyfile(coverage,out/'coverage.json')
    selected=[r for r in read_json(coverage)['months'] if months is None or r['target_month'].replace('-','') in months]
    if months is not None and len(selected)!=len(set(months)):
        raise ValueError('Unknown requested month')
    if stage in ('all','population'): build_population(out,selected)
    if stage in ('all','environment'): build_environments(out,selected)
    finalize_delivery(out)
    return dict(delivery=str(out),requested_months=len(selected),new_api_calls=0,
                built_at=datetime.now(timezone.utc).isoformat())


def finalize_delivery(out):
    """Merge per-month receipts after a subset repair; never lose other months."""
    from socioverse.schemas import EnvironmentBundle
    months=read_json(out/'coverage.json')['months']
    environments=[];foods={};populations=[];gaps=[]
    for cov in months:
        month=cov['target_month'].replace('-','');folder=out/month
        if (folder/'population_receipt.json').exists(): populations.append(read_json(folder/'population_receipt.json'))
        if (folder/'food_categories.json').exists(): foods[month]=read_json(folder/'food_categories.json')
        if not (folder/'environment_receipt.json').exists():
            gaps.append(dict(month=month,status='environment_receipt_missing'));continue
        env=read_json(folder/'environment.json')
        # A reused schema skeleton must not retain the sample month dataset ID,
        # placeholder source or duplicated v2 layer names.
        layers={}
        for layer in env['layers']:
            layer=deepcopy(layer)
            if layer['source'].endswith('external_events_PLACEHOLDER.json'):
                layer['source']=str((folder/'external_events.json').relative_to(ROOT))
            layers[layer['name']]=layer
        env['layers']=list(layers.values())
        env['provider_args']['data_gaps']['note']='Unavailable archived values omitted; see explicit gaps. Shutdown cells remain missing. Gasoline/news text vintage is unverified.'
        EnvironmentBundle.model_validate(env)
        dump(folder/'environment.json',env)
        external=read_json(folder/'external_events.json')
        external['dataset_id']=f'sce_bls_initial_release_e_{cov["target_month"].replace("-","_")}_v2'
        external['data_gaps']=env['provider_args']['data_gaps']
        dump(folder/'external_events.json',external)
        environments.append(read_json(folder/'environment_receipt.json'))
    dump(out/'population_summary.json',dict(months=populations,new_api_calls=0))
    dump(out/'environment_summary.json',dict(months=environments,errors=gaps,new_api_calls=0))
    dump(out/'food_catalog.json',foods)
    status=dict(status='P_E_materialized_belief_and_prompt_readiness_separate',new_api_calls=0,
                population_months=len(populations),environment_months=len(environments),food_months=len(foods),
                historical_micro_months=sum(not r['synthetic'] for r in populations),
                synthetic_population_months=sum(r['synthetic'] for r in populations),
                missing_news_labels=sum(r['missing_news_labels'] for r in populations),
                weight_policy='Real raw weights in private sidecars only; synthetic PPS once then equal expansion weight',
                strict_B_verified_months=0,
                limits=['P/E availability does not mean initialized prompts or live authorization.',
                        '82 historical months use current micro conditions for A reconstruction.',
                        '11 synthetic frames use latest observed distribution; publication date unverified, not strict-B proof.',
                        'No evaluation target answers are delivered in population or news inputs.'])
    dump(out/'materialization_summary.json',status)
    return status
