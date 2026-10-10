"""Prepare frozen inputs and execute each genuine SocioVerse run once."""
import json
import os
import re
import sys
import subprocess
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import numpy as np
from pypdf import PdfReader
from socioverse.schemas import PopulationBundle, EnvironmentBundle, SimulationConfig
from .model import SCEEnvironmentProvider
from .price_experience import PROFILE_KEYS, profile_hash
from .price_contact import ARMS, REF, PROMPT_VERSION, STATE_PADD, build_messages, validate_bundle
from .spending_audit import sha
from .experience_mechanism import _check_public_time

N = 20
MODEL = 'deepseek-flash'
PRICE_IN, PRICE_OUT = .30, 1.20  # verified official peak/cache-miss upper rates
JOB_CAP, TOTAL_CAP = .12, 1.


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def extract_prices(root, month):
    tag = 'may' if month == '202105' else 'june'
    gaspath = root/f'data/raw/high_frequency_prices/20261010/gas_{tag}.pdf'
    gasurl = f'https://www.eia.gov/petroleum/supply/weekly/archive/2021/2021_{"05_12" if tag == "may" else "06_09"}/pdf/wpsrall.pdf'
    gaspage = [(i+1,p.extract_text()) for i,p in enumerate(PdfReader(gaspath).pages) if 'Table 14.' in p.extract_text()]
    if len(gaspage) != 1:
        raise ValueError('Expected one EIA table14')
    page, text = gaspage[0]
    sections = re.split(r'2021\s+((?:\d{1,2}/\d{1,2}\s+){11}\d{1,2}/\d{1,2})\s*\n', text)
    if len(sections) != 3:
        raise ValueError('Weekly date header cannot be parsed')
    dates = [f'2021-{int(s.split("/")[0]):02d}-{int(s.split("/")[1]):02d}' for s in sections[1].split()]
    weekly = sections[2].split('  Midgrade')[0]
    patterns = {'national':r'^\s*Regular\s+\.+', '1':r'^\s*East Coast \(PADD 1\)\s+\.+',
                '2':r'^\s*Midwest \(PADD 2\)\s+\.+', '3':r'^\s*Gulf Coast \(PADD 3\)\s+\.+',
                '4':r'^\s*Rocky Mountain \(PADD 4\)\s+\.+', '5':r'^\s*West Coast \(PADD 5\)\s+\.+'}
    series = {}; evidence = {}
    for key, pattern in patterns.items():
        lines = [line for line in weekly.splitlines() if re.search(pattern,line)]
        if len(lines) != 1: raise ValueError('EIA row '+key)
        vals = re.findall(r'\b\d\.\d{3}\b', lines[0])
        if len(vals) != 12: raise ValueError('EIA columns '+key)
        series[key] = list(map(float,vals)); evidence[key] = lines[0]
    dpath = (root/'data/raw/high_frequency_prices/20261009/usda_dairy_week_20210503_20210507.pdf' if tag == 'may'
             else root/'data/raw/high_frequency_prices/20261010/dairy_june.pdf')
    dpages = [(i+1,p.extract_text()) for i,p in enumerate(PdfReader(dpath).pages) if 'NATIONAL -- CONVENTIONAL DAIRY PRODUCTS' in p.extract_text()]
    if len(dpages) != 1: raise ValueError('USDA national table')
    dpage, dairytext = dpages[0]
    dairytext = dairytext.split('REGIONAL -- CONVENTIONAL')[0]
    items = []
    for label, prefix in [('Milk half gallon','Milk All fat tests half gallon'),
                          ('Natural cheese 8 oz shred','Cheese Natural Varieties 8 oz shred'),
                          ('Greek yogurt 4–6 oz','Yogurt Greek 4-6 oz')]:
        lines = [line for line in dairytext.splitlines() if line.startswith(prefix)]
        if len(lines) != 1: raise ValueError('USDA row '+prefix)
        nums = re.findall(r'(?:\d*\.\d+|\d+)', lines[0][len(prefix):])
        if len(nums) != 6: raise ValueError('USDA columns')
        items.append({'label':label,'stores':list(map(int,nums[::2])),
                      'prices':list(map(float,nums[1::2])),'source_row':lines[0]})
    gasdate = '2021-05-12' if tag == 'may' else '2021-06-09'
    ddate = '2021-05-07' if tag == 'may' else '2021-06-04'
    durl = ('https://esmis.nal.usda.gov/sites/default/release-files/z603qx43s/d217rj427/v979vz50r/DYWWEEKLYREPORT.PDF' if tag == 'may'
            else 'https://esmis.nal.usda.gov/sites/default/release-files/z603qx43s/gm80js03w/dv140p857/DYWWEEKLYREPORT.PDF')
    required = 'Friday, May 7, 2021' if tag == 'may' else 'Friday, June 4, 2021'
    if required not in dpages[0][1]: raise ValueError('USDA date evidence missing')
    return {'gasoline':{'dates':dates,'series':series,'available_by':gasdate+'T23:59:59-04:00',
              'source_url':gasurl,'sha256':sha(gaspath),'pdf_page':page,'source_rows':evidence,
              'publication_evidence':'Dated official EIA weekly archive URL; publication clock not independently recovered',
              'vintage_status':'dated_archived_report_downloaded_20261010; original bytes immutability not established'},
            'dairy':{'items':items,'available_by':ddate+'T23:59:59-04:00','source_url':durl,
              'sha256':sha(dpath),'pdf_page':dpage,'publication_evidence':'Friday issued date printed in retail report',
              'vintage_status':'dated_archived_report_downloaded; original bytes immutability not established'}}


def prepare(root, folder):
    root, folder = Path(root).resolve(), Path(folder).resolve(); folder.mkdir(parents=True,exist_ok=False)
    plan = {'trial_id':folder.name,'status':'prepared_not_run','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'research_line':'A_historical_reconstruction','months':['202105','202106'],'arms':list(ARMS),
            'n_per_month':N,'max_calls':N*8,'model':MODEL,'temperature':.5,'seed':42,'retry_max':0,'max_tokens':1024,
            'total_cap_usd':TOTAL_CAP,'per_job_cap_usd':JOB_CAP,'source_hashes':{},'frozen_hashes':{},'jobs':[],
            'price_usd_per_mtok':{'input':PRICE_IN,'output':PRICE_OUT},
            'price_policy':'Conservative official peak/cache-miss rates, verified 2026-10-10; no discounts claimed.',
            'pricing_source':'https://api-docs.deepseek.com/quick_start/pricing/',
            'contrasts':{'national-baseline':'recent food+gasoline context added together',
                         'matched-national':'regional gasoline granularity; both arms retain recent food',
                         'matched-shuffled':'geographic assignment only; same regional series multiset'},
            'limitations':['Existing diagnostic 20-person sample, no national representation.',
                           'CE shares are synthetic, unavailable at 2021 origins: retrospective A only.',
                           'Dairy promotional national averages cover three products only, not the household actual prices.',
                           'Gasoline geography does not establish driving frequency or actual purchases.',
                           'Original full statistics/news retained; no test of deleting them.',
                           'Single generation per arm; cannot disentangle stochastic generation variation.'],
            'destination':'https://api.deepseek.com',
            'authorization':{'user_quote':'好的，我基本觉得这个思路可以继续进行下去，你可以开始你的实验了。实验过程与分析都需要最后记录一下。',
                             'scope':'Deidentified demographic categories, synthetic CE shares, public historical economic/news and retail-price reports; no source person IDs, weights, actual QSP5 shares or inflation answers.',
                             'budget_basis':'Small experiment within $1 cap announced before execution.'},'metadata':{}}
    links=[]
    for month in plan['months']:
        source = root/'outputs/price_experience_20261006_v1/n20'/month
        files = {k:source/f'{k}.json' for k in ('population','environment','simulation','experience')}
        plan['source_hashes'].update({str(p):sha(p) for p in files.values()})
        pop = json.loads(files['population'].read_text()); oldbasket=json.loads(files['experience'].read_text())['experience_by_id']
        personas=[]; rows={}
        for i,p in enumerate(pop['personas']):
            if set(p['attributes'])-PROFILE_KEYS: raise ValueError('Demographic whitelist')
            aid=f'contact_{i+1:03d}'; basket=oldbasket[p['agent_id']]
            if basket['profile_sha256'] != profile_hash(p['attributes']): raise ValueError('Source basket/profile mismatch')
            links.append({'date':int(month),'agent_id':aid,'userid':int(p['agent_id'].removeprefix('sce_u')),
                          'padd':STATE_PADD[p['attributes']['state']],'food_share':basket['spending_shares']['food']})
            new=deepcopy(p);new.update(agent_id=aid,weight=1.,group_key=None,init_state={});personas.append(new)
            rows[aid]={'profile_sha256':profile_hash(p['attributes']),'shares':deepcopy(basket['spending_shares']),
                       'assigned_padd':STATE_PADD[p['attributes']['state']]}
        if len(personas)!=N: raise ValueError('Sample size changed')
        pop.update(personas=personas,materialized_count=N,provider_args={})
        pop=PopulationBundle.model_validate(pop)
        env=EnvironmentBundle.model_validate(json.loads(files['environment'].read_text()))
        sim=SimulationConfig.model_validate(json.loads(files['simulation'].read_text()))
        target=env.provider_args['targets'][0]
        if len(env.provider_args['targets'])!=1 or sim.n_steps!=1 or sim.warm_start is not None or sim.seed!=42:
            raise ValueError('Isolated cold-start trial required')
        for key in ('audit_dir','run_id','household_state_by_id','price_experience_mechanism','experience_by_id','information_exposure'):
            env.provider_args.pop(key,None)
        env.provider_args['persona_by_id']={p.agent_id:p.attributes for p in pop.personas}
        prices=extract_prices(root,month)
        for tag in ['gasoline','dairy']:
            fpath=(root/f'data/raw/high_frequency_prices/20261010/gas_{"may" if month=="202105" else "june"}.pdf' if tag=='gasoline' else
                   (root/'data/raw/high_frequency_prices/20261009/usda_dairy_week_20210503_20210507.pdf' if month=='202105' else root/'data/raw/high_frequency_prices/20261010/dairy_june.pdf'))
            plan['source_hashes'][str(fpath)]=sha(fpath)
        directory=folder/month;directory.mkdir()
        write(directory/'population.json',pop.model_dump());write(directory/'environment.json',env.model_dump())
        write(directory/'price_evidence.json',prices)
        aids=list(rows);rng=np.random.default_rng(42);order=rng.permutation(N)
        donors={aids[int(order[i])]:aids[int(order[(i+1)%N])] for i in range(N)}
        plan['metadata'][month]={'as_of':target['as_of'],'source_frame':'existing n20 sample; no answer-based reselection',
            'regional_counts':{k:sum(r['assigned_padd']==k for r in rows.values()) for k in sorted(set(STATE_PADD.values()))},
            'shuffle_self_donor_n':sum(a==b for a,b in donors.items()),
            'shuffle_same_padd_n':sum(rows[a]['assigned_padd']==rows[b]['assigned_padd'] for a,b in donors.items())}
        for arm in ARMS:
            delivered=deepcopy(rows)
            if arm=='shuffled':
                for aid in aids:delivered[aid]['assigned_padd']=rows[donors[aid]]['assigned_padd']
            bundle={'schema':'sce-price-contact-v1','research_line':plan['research_line'],'target_month':target['target_month'],
                    'as_of':target['as_of'],'arm':arm,'rows':delivered,'prices':prices}
            validate_bundle(bundle,pop.personas,target['target_month'])
            cfg=sim.model_copy(deep=True);cfg.decision_ref=REF
            cfg.decision_args={'price_contact_bundle':bundle,'seed':42,'max_prompt_chars':18000,
                               'prompt_version':PROMPT_VERSION,'llm_kind':'scripted'}
            write(directory/f'simulation_{arm}.json',cfg.model_dump())
            provider=SCEEnvironmentProvider(env.model_copy(deep=True));provider.audit_dir=None;provider.reset(42);provider.advance_to(1)
            observations=provider.observe_batch(aids,1)
            for ob in observations:_check_public_time(ob.macro_information)
            previews=[{'agent_id':o.agent_id,'messages':build_messages(o,bundle)} for o in observations]
            if any(len(json.dumps(x['messages'],ensure_ascii=False))>18000 for x in previews):raise ValueError('Prompt size')
            write(directory/f'preview_{arm}.json',previews)
            bound=sum((len(json.dumps(x['messages'],ensure_ascii=False).encode())+256)*PRICE_IN/1e6+1024*PRICE_OUT/1e6 for x in previews)
            if bound>JOB_CAP:raise ValueError('Job cost bound')
            runid=f'{folder.name}-{month}-{arm}'
            cmd=[sys.executable,str(root/'scripts/run_sce_local.py'),'--llm','openai','--confirm-spend','--run-id',runid,'--force-export',
                 '--population',str(directory/'population.json'),'--environment',str(directory/'environment.json'),
                 '--simulation',str(directory/f'simulation_{arm}.json'),'--prompt-version',PROMPT_VERSION,'--model',MODEL,
                 '--temperature','0.5','--max-calls',str(N),'--max-tokens','1024','--retry-max','0',
                 '--extra-body','{"thinking":{"type":"disabled"}}','--price-in',str(PRICE_IN),'--price-out',str(PRICE_OUT),'--cost-cap-usd',str(JOB_CAP)]
            plan['jobs'].append({'month':month,'arm':arm,'run_id':runid,'output_dir':str(root/'outputs/local_runs'/runid),
                                 'command':cmd,'status':'not_run','conservative_full_output_cost_bound':bound})
    write(folder/'private_evaluation_link.json',links)
    plan['conservative_total_cost_bound']=sum(j['conservative_full_output_cost_bound'] for j in plan['jobs'])
    if plan['conservative_total_cost_bound']>TOTAL_CAP:raise ValueError('Total cost bound')
    for p in folder.rglob('*.json'):plan['frozen_hashes'][str(p)]=sha(p)
    for p in [root/'scripts/run_sce_local.py',root/'scripts/run_sce_price_contact_trial.py',*sorted((root/'studies/sce_inflation_expectations').rglob('*.py'))]:
        plan['frozen_hashes'][str(p)]=sha(p)
    write(folder/'trial_manifest.json',plan)
    return plan


def dry_run(root, folder):
    plan=json.loads((Path(folder)/'trial_manifest.json').read_text());record=[]
    for job in plan['jobs']:
        cmd=list(job['command']);cmd[cmd.index('openai')]='scripted';cmd.remove('--confirm-spend')
        cmd[cmd.index('--run-id')+1]=job['run_id']+'-engineering'
        with (Path(folder)/f'{job["month"]}_{job["arm"]}_engineering.log').open('w') as log:
            proc=subprocess.run(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT)
        record.append({'run_id':cmd[cmd.index('--run-id')+1],'exit_code':proc.returncode})
        write(Path(folder)/'engineering_check.json',record)
        if proc.returncode:raise RuntimeError('Engineering run failed; inspect log')
    return record


def execute(root,folder,approval_note):
    root,folder=Path(root).resolve(),Path(folder).resolve();plan=json.loads((folder/'trial_manifest.json').read_text())
    if plan['status']!='prepared_not_run' or not approval_note.strip():raise ValueError('Approved fresh trial only')
    check=json.loads((folder/'engineering_check.json').read_text())
    if len(check)!=8 or any(r['exit_code'] for r in check):raise ValueError('Engineering gate')
    from socioverse.external_events import _load_dotenv
    _load_dotenv()
    endpoint=urlparse(os.environ.get('SV_LLM_BASE_URL','https://api.deepseek.com'))
    if endpoint.scheme!='https' or endpoint.hostname!='api.deepseek.com':raise ValueError('Destination gate')
    if not (os.environ.get('SV_LLM_API_KEY') or os.environ.get('OPENAI_API_KEY')):raise ValueError('Credential missing')
    plan['authorization']['approval_note']=approval_note;plan['status']='running';write(folder/'trial_manifest.json',plan)
    spent=0.;identity=None
    for job in plan['jobs']:
        for path,h in {**plan['source_hashes'],**plan['frozen_hashes']}.items():
            if sha(path)!=h:raise ValueError('Frozen input/code changed: '+path)
        if spent+JOB_CAP>TOTAL_CAP+1e-9 or Path(job['output_dir']).exists():raise ValueError('Budget/existing run gate')
        job['status']='running';write(folder/'trial_manifest.json',plan);print('START',job['month'],job['arm'],flush=True)
        with (folder/f'{job["month"]}_{job["arm"]}.log').open('w') as log:
            proc=subprocess.run(job['command'],cwd=root,stdout=log,stderr=subprocess.STDOUT)
        job['exit_code']=proc.returncode
        if proc.returncode:
            job['status']='failed';plan['status']='stopped_run_error';write(folder/'trial_manifest.json',plan)
            raise RuntimeError('Run failed, no automatic retry')
        runpath=Path(job['output_dir']);run=json.loads((runpath/'run_manifest.json').read_text())
        calls=[json.loads(l) for l in (runpath/'llm_calls.jsonl').read_text().splitlines()]
        preview={x['agent_id']:x['messages'] for x in json.loads((folder/job['month']/f'preview_{job["arm"]}.json').read_text())}
        if len(calls)!=N or {c['agent_id'] for c in calls}!=set(preview):raise RuntimeError('Actual call coverage')
        if any(json.loads(c['prompt_text'])!=preview[c['agent_id']] for c in calls):raise RuntimeError('Actual preview mismatch')
        tags=sorted({c['returned_model'] for c in calls if not c['error']})
        if identity is None:identity=tags
        spent+=run['cost']['estimated_cost_usd'];plan['estimated_cost_usd']=spent
        job.update(status='completed',cost=run['cost'],returned_models=tags,validation=run['decisions_by_validation_status'])
        write(folder/'trial_manifest.json',plan);print('DONE',job['month'],job['arm'],spent,flush=True)
        if len(tags)!=1 or tags!=identity or job['validation']!={'valid':N}:
            plan['status']='stopped_identity_or_validation';write(folder/'trial_manifest.json',plan);raise RuntimeError('Identity/validation stop')
    plan['status']='completed';write(folder/'trial_manifest.json',plan)
    return plan
