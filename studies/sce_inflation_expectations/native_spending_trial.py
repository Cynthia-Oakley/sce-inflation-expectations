"""Frozen native basket trial preparation and guarded execution; no truth inputs."""
import json
import os
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import numpy as np
import pandas as pd
from socioverse.schemas import PopulationBundle, EnvironmentBundle, SimulationConfig
from .model import SCEEnvironmentProvider
from .native_spending import ARMS, SCHEMA, PROMPT_VERSION, build_messages, validate_bundle
from .spending_audit import SHARES, CATEGORIES, sha
from .price_experience import PROFILE_KEYS, profile_hash

N = 32
MODEL = 'deepseek-flash'
PRICE_IN, PRICE_OUT = .30, 1.20
JOB_CAP, TOTAL_CAP = .16, 1.00


def write(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def prepare(root, output):
    root,output=Path(root).resolve(),Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    historypath=root/'outputs/sce_spending_audit_20261009_v2/historical_baskets_private.parquet'
    # Explicit projection: do not read inflation responses, probability bins,
    # weights or spending expectations into experimental preparation.
    history=pd.read_parquet(historypath,columns=['date','userid','date_basket']+SHARES)
    roles=root/'outputs/ce_population_baskets_20261006T063749Z_a8be0d98'
    eroot=root/'outputs/price_experience_20261006_v1/n20'
    plan={'trial_id':output.name,'created_at_utc':datetime.now(timezone.utc).isoformat(),
          'status':'prepared_not_run','research_line':'A_historical_reconstruction',
          'model':MODEL,'temperature':.5,'seed':42,'retry_max':0,'max_tokens':1024,
          'n_per_month':N,'months':['202105','202106'],'arms':list(ARMS),
          'max_calls':N*6,'total_cap_usd':TOTAL_CAP,'per_job_cap_usd':JOB_CAP,
          'price_usd_per_mtok':{'input':PRICE_IN,'output':PRICE_OUT},
          'pricing_source':'https://api-docs.deepseek.com/quick_start/pricing/',
          'primary_contrast':'actual versus shuffled: same spending-vector multiset; matching alone changes',
          'secondary_contrast':'actual versus withheld: additional spending context',
          'evaluation':'Paired common-case Q9 median error, W1, cross-person IQR gap; individual MAE auxiliary; no causal or nationwide claim.',
          'sample':'Four equal-frequency food-share strata, 8 people each, seed42; ties assigned deterministically by userid. No target-answer selection.',
          'limits':['Recent reported shares are not exact current-month shares or measured attention.',
                    'Only two development months and one stochastic draw per arm; effect uncertainty remains.',
                    'No Normal expansion; diagnostic sample is not representative.',
                    '2021 inputs archived retrospectively, not a real-time B test.'],
          'destination':'https://api.deepseek.com','authorization':{'status':'user_authorized_direction_and_experiments',
              'user_quote':'你可以沿着这个方向一直做调研和一些实验。预算方面，我们目前应该还能支撑一些实验，可以继续。',
              'scope':'Deidentified demographic categories, nine reported QSP5 spending percentages, prior basket month and public historical economic/news information. No source IDs, survey weights or actual inflation answers.'},
          'source_hashes':{str(historypath):sha(historypath)},'frozen_hashes':{},'metadata':{},'jobs':[]}
    mappings=[]
    for month in plan['months']:
        poppaths=[roles/month/'roles'/role/'population.json' for role in ('core','normal')]
        source=json.loads(poppaths[0].read_text());others=json.loads(poppaths[1].read_text())
        full=source['personas']+others['personas']
        byuid={int(p['agent_id'].removeprefix('sce_u')):p for p in full}
        if len(byuid)!=len(full):raise ValueError('Duplicate role IDs')
        h=history[(history.date==int(month))&history.userid.isin(byuid)].sort_values(['qsp5_3','userid']).reset_index(drop=True)
        if len(h)<N:raise ValueError('Insufficient valid linked baskets')
        rng=np.random.default_rng(42)
        bands=np.array_split(np.arange(len(h)),4)
        indexes=np.concatenate([rng.choice(band,8,replace=False) for band in bands])
        selected=h.iloc[indexes].copy().reset_index(drop=True)
        personas=[];rows={}
        target=f'{month[:4]}-{month[4:]}'
        for i,r in selected.iterrows():
            sourcep=deepcopy(byuid[int(r.userid)])
            if set(sourcep['attributes'])-PROFILE_KEYS:raise ValueError('Demographic whitelist')
            aid=f'native_{i+1:03d}'
            sourcep.update(agent_id=aid,weight=1.0,group_key=None,init_state={})
            personas.append(sourcep)
            rows[aid]={'agent_id':aid,'profile_sha256':profile_hash(sourcep['attributes']),
                       'basket_month':f'{int(r.date_basket)//100}-{int(r.date_basket)%100:02d}',
                       'shares_pct':{category:float(r[col]) for category,col in zip(CATEGORIES,SHARES)}}
            mappings.append({'date':int(month),'agent_id':aid,'userid':int(r.userid),'food_stratum':i//8})
        source.update(personas=personas,materialized_count=N)
        source['provider_args']={}  # no source IDs or donor information in provider args
        pop=PopulationBundle.model_validate(source)
        directory=output/month;directory.mkdir()
        envpath,simpath=[eroot/month/f'{name}.json' for name in ('environment','simulation')]
        env=EnvironmentBundle.model_validate(json.loads(envpath.read_text()))
        sim=SimulationConfig.model_validate(json.loads(simpath.read_text()))
        if sim.n_steps!=1 or sim.warm_start is not None or sim.seed!=42:raise ValueError('Cold-start one-month config required')
        if len(env.provider_args['targets'])!=1 or env.provider_args['targets'][0]['target_month']!=target:
            raise ValueError('Environment target mismatch')
        for key in ('audit_dir','run_id','household_state_by_id','price_experience_mechanism','experience_by_id','information_exposure'):
            env.provider_args.pop(key,None)
        env.provider_args['persona_by_id']={p.agent_id:p.attributes for p in pop.personas}
        write(directory/'population.json',pop.model_dump())
        write(directory/'environment.json',env.model_dump())
        plan['source_hashes'].update({str(p):sha(p) for p in poppaths+[envpath,simpath]})
        aids=list(rows);order=rng.permutation(N)
        # Cyclic assignment in a random ordering, guaranteeing no donor=self.
        donor={aids[int(order[i])]:aids[int(order[(i+1)%N])] for i in range(N)}
        plan['metadata'][month]={'frame_n':len(full),'eligible_n':len(h),'selected_n':N,
            'food_strata_counts':[8]*4,'as_of':env.provider_args['targets'][0]['as_of'],
            'shuffle_self_donor_n':sum(a==b for a,b in donor.items()),
            'shuffle_identical_vector_n':sum(rows[a]['shares_pct']==rows[b]['shares_pct'] for a,b in donor.items()),
            'basket_months':sorted({r['basket_month'] for r in rows.values()})}
        for arm in ARMS:
            delivered=deepcopy(rows)
            if arm=='shuffled':
                for aid in aids:
                    delivered[aid]['shares_pct']=deepcopy(rows[donor[aid]]['shares_pct'])
                    delivered[aid]['basket_month']=rows[donor[aid]]['basket_month']
            bundle={'schema_version':SCHEMA,'research_line':'A_historical_reconstruction','target_month':target,
                    'arm':arm,'rows':delivered,'source_sha256':plan['source_hashes'][str(historypath)]}
            validate_bundle(bundle,pop.personas,target)
            cfg=sim.model_copy(deep=True)
            cfg.decision_ref='sce_inflation_expectations.native_spending_decision'
            cfg.decision_args={'native_spending_bundle':bundle,'seed':42,'max_prompt_chars':16000,
                               'prompt_version':PROMPT_VERSION,'llm_kind':'scripted'}
            write(directory/f'simulation_{arm}.json',cfg.model_dump())
            envcheck=SCEEnvironmentProvider(env.model_copy(deep=True));envcheck.audit_dir=None
            envcheck.reset(42);envcheck.advance_to(1)
            preview=[]
            for ob in envcheck.observe_batch(aids,1):
                messages=build_messages(ob,bundle)
                txt=json.dumps(messages,ensure_ascii=False)
                if len(txt)>16000:raise ValueError('Prompt size gate')
                preview.append({'agent_id':ob.agent_id,'messages':messages,'sha256':__import__('hashlib').sha256(txt.encode()).hexdigest()})
            write(directory/f'preview_{arm}.json',preview)
            bounds=[(len(json.dumps(p['messages'],ensure_ascii=False).encode())+256)*PRICE_IN/1e6+1024*PRICE_OUT/1e6 for p in preview]
            if sum(bounds)>JOB_CAP:raise ValueError(f'Conservative request bounds {sum(bounds)} exceed job cap')
            runid=f'{output.name}-{month}-{arm}'
            command=[sys.executable,str(root/'scripts/run_sce_local.py'),'--llm','openai','--confirm-spend',
                '--run-id',runid,'--force-export','--population',str(directory/'population.json'),
                '--environment',str(directory/'environment.json'),'--simulation',str(directory/f'simulation_{arm}.json'),
                '--prompt-version',PROMPT_VERSION,'--model',MODEL,'--temperature','0.5','--max-calls',str(N),
                '--max-tokens','1024','--retry-max','0','--extra-body','{"thinking":{"type":"disabled"}}',
                '--price-in',str(PRICE_IN),'--price-out',str(PRICE_OUT),'--cost-cap-usd',str(JOB_CAP)]
            plan['jobs'].append({'month':month,'arm':arm,'run_id':runid,'output_dir':str(root/'outputs/local_runs'/runid),
                                 'command':command,'status':'not_run','conservative_full_output_cost_bound':sum(bounds)})
    pd.DataFrame(mappings).to_parquet(output/'private_evaluation_link.parquet',index=False)
    plan['conservative_total_cost_bound']=sum(j['conservative_full_output_cost_bound'] for j in plan['jobs'])
    if plan['conservative_total_cost_bound']>TOTAL_CAP:raise ValueError('Total bound exceeds cap')
    for p in output.rglob('*.json'):plan['frozen_hashes'][str(p)]=sha(p)
    for p in [root/'scripts/run_sce_local.py',root/'scripts/run_sce_native_spending_trial.py',*sorted((root/'studies/sce_inflation_expectations').rglob('*.py'))]:
        plan['frozen_hashes'][str(p)]=sha(p)
    plan['frozen_hashes'][str(output/'private_evaluation_link.parquet')]=sha(output/'private_evaluation_link.parquet')
    write(output/'trial_manifest.json',plan)
    print(json.dumps({'status':plan['status'],'calls':plan['max_calls'],'conservative_bound':plan['conservative_total_cost_bound'],'metadata':plan['metadata']},ensure_ascii=False),flush=True)
    return plan


def execute(root, folder, approval_note=None):
    root,folder=Path(root).resolve(),Path(folder).resolve()
    plan=json.loads((folder/'trial_manifest.json').read_text())
    if plan['status']!='prepared_not_run':raise ValueError('No automatic rerun/resume')
    if not approval_note or not approval_note.strip():
        raise ValueError('Explicit real-QSP5 external-send and $1 approval must be recorded before any API call')
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    endpoint=urlparse(os.environ.get('SV_LLM_BASE_URL','https://api.deepseek.com'))
    if endpoint.scheme!='https' or endpoint.hostname!='api.deepseek.com':raise ValueError('Unexpected destination')
    if not (os.environ.get('SV_LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')):raise ValueError('Credential missing')
    plan['authorization'].update(status='explicit_real_spending_send_and_budget_approved',
                                 approval_note=approval_note,recorded_at_utc=datetime.now(timezone.utc).isoformat())
    plan['status']='running';write(folder/'trial_manifest.json',plan)
    spent=0.;identity=None
    for job in plan['jobs']:
        for path,h in {**plan['source_hashes'],**plan['frozen_hashes']}.items():
            if sha(path)!=h:raise ValueError('Frozen input/code changed: '+path)
        if spent+JOB_CAP>TOTAL_CAP+1e-9 or Path(job['output_dir']).exists():raise ValueError('Budget/existing run gate')
        job['status']='running';write(folder/'trial_manifest.json',plan)
        print('START',job['month'],job['arm'],flush=True)
        with (folder/f'{job["month"]}_{job["arm"]}.log').open('w') as log:
            proc=subprocess.run(job['command'],cwd=root,stdout=log,stderr=subprocess.STDOUT)
        job['exit_code']=proc.returncode
        if proc.returncode:
            job['status']='failed';plan['status']='stopped_run_error';write(folder/'trial_manifest.json',plan)
            raise RuntimeError('Failed run preserved; no retry')
        run=json.loads((Path(job['output_dir'])/'run_manifest.json').read_text())
        calls=[json.loads(l) for l in (Path(job['output_dir'])/'llm_calls.jsonl').read_text().splitlines()]
        previews=json.loads((folder/job['month']/f'preview_{job["arm"]}.json').read_text())
        expected={p['agent_id']:p['messages'] for p in previews}
        if len(calls)!=N or {c['agent_id'] for c in calls}!=set(expected):raise RuntimeError('Call coverage mismatch')
        if any(json.loads(c['prompt_text'])!=expected[c['agent_id']] for c in calls):raise RuntimeError('Actual/preview prompt mismatch')
        tags=sorted({c['returned_model'] for c in calls if not c['error']})
        if identity is None:identity=tags
        spent+=run['cost']['estimated_cost_usd']
        job.update(status='completed',cost=run['cost'],returned_models=tags,
                   validation=run['decisions_by_validation_status'])
        plan['estimated_cost_usd']=spent;write(folder/'trial_manifest.json',plan)
        print('DONE',job['month'],job['arm'],'cost',job['cost']['estimated_cost_usd'],flush=True)
        if len(tags)!=1 or tags!=identity or run['decisions_by_validation_status']!={'valid':N}:
            plan['status']='stopped_identity_or_validation_change';write(folder/'trial_manifest.json',plan)
            raise RuntimeError('Stop on identity/validation change; do not alter treatment')
    plan['status']='completed';write(folder/'trial_manifest.json',plan)
    return plan
