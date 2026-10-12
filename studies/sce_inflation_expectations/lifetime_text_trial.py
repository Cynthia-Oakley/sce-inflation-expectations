"""Prepare original/numeric/text cases; reuse audited engine and spend guards."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

from socioverse.schemas import EnvironmentBundle, PopulationBundle, SimulationConfig
from .confidence_trial import MONTHS, protected, sha, dump
from .lifetime_trial import prepare as prepare_numeric, dry_run, execute
from .lifetime_text_experiment import ARMS, SCHEMA, REF, PROMPT_VERSION, TEXT_INTRO, render_text_cards, validate_bundle, build_messages
from .lifetime_experience import json_hash, insert_block
from .model import SCEEnvironmentProvider


def prepare(root, folder):
    root, folder = Path(root).resolve(), Path(folder).resolve()
    protected(root)
    if folder.exists() or not folder.is_relative_to(root/'outputs'):
        raise ValueError('fresh ignored output directory required')
    base = folder.with_name(folder.name+'_numeric_preparation')
    plan = prepare_numeric(root,base)
    folder.mkdir()
    plan['status'] = 'offline_prepared_not_authorized'
    plan['created_at_utc'] = datetime.now(timezone.utc).isoformat()
    plan['experiment_name'] = 'Lifetime Inflation Experience: numeric versus qualitative'
    plan['arms'] = list(ARMS)
    plan['source_sha256'][str((base/'trial_manifest.json').relative_to(root))] = sha(base/'trial_manifest.json')
    plan['jobs'] = []
    plan['preregistered_evaluation']['contrasts'] = ['text_history minus numeric_history','text_history minus original','numeric_history minus original']
    plan['preregistered_evaluation']['primary_contrast'] = 'text_history minus numeric_history'
    plan['preregistered_evaluation']['representation_gate'] = 'both repeats: lower mean Q9 median error and W1 than numeric, both improve in >=3/4 periods'
    plan['preregistered_evaluation']['candidate_gate'] = 'same criterion versus original as well; no automatic production upgrade'
    plan['qualitative_duration_rule'] = 'observed complete spell >=12 months: extended; <=6: short-lived; middle: a while; left/right censoring explicitly retained'
    plan['limitations'].append('Qualitative history also shortens context and removes exact age/month/rate details; not pure isolation of CPI digits.')
    for name in ('evaluation_links_private.json',):
        shutil.copy2(base/name,folder/name)
        plan['source_sha256'][str((base/name).relative_to(root))] = sha(base/name)
    links=json.loads((folder/'evaluation_links_private.json').read_text())
    for month in MONTHS:
        dest=folder/month; dest.mkdir()
        for name in ('population.json','environment.json'):
            shutil.copy2(base/month/name,dest/name)
            plan['source_sha256'][str((base/month/name).relative_to(root))]=sha(base/month/name)
        pop=PopulationBundle.model_validate(json.loads((dest/'population.json').read_text()))
        env=EnvironmentBundle.model_validate(json.loads((dest/'environment.json').read_text()))
        numeric_cfg_path=base/month/'simulation_age_matched_episodes.json'
        plan['source_sha256'][str(numeric_cfg_path.relative_to(root))]=sha(numeric_cfg_path)
        template=SimulationConfig.model_validate(json.loads(numeric_cfg_path.read_text()))
        numeric_bundle=template.decision_args['lifetime_bundle']
        provider=SCEEnvironmentProvider(env.model_copy(deep=True));provider.audit_dir=None;provider.reset(42);provider.advance_to(1)
        observations=provider.observe_batch([p.agent_id for p in pop.personas],1)
        target=env.provider_args['targets'][0]
        previews_by_arm={}
        history_text=[]
        for arm in ARMS:
            bundle=deepcopy(numeric_bundle);bundle['schema_version']=SCHEMA;bundle['arm']=arm
            if arm=='text_history':bundle['intro']=TEXT_INTRO
            for row in bundle['rows'].values():
                if arm=='original':
                    row['cards']=[];row['messages_sha256']=row['baseline_messages_sha256']
            if arm=='text_history':
                # Compute expected messages only from the already-frozen baseline.
                old_previews=json.loads((base/month/'preview_original.json').read_text())
                originals={r['agent_id']:r['messages'] for r in old_previews}
                plan['source_sha256'][str((base/month/'preview_original.json').relative_to(root))]=sha(base/month/'preview_original.json')
                for aid,row in bundle['rows'].items():
                    text=render_text_cards(row['cards'])
                    if '%' in text or 'Price path:' in text or 'observed months' in text:
                        raise ValueError('detailed numbers in qualitative history')
                    row['messages_sha256']=json_hash(insert_block(originals[aid],text))
                    history_text.append({'agent_id':aid,'text':text})
            validate_bundle(bundle,pop.personas,target['target_month'],target['as_of'])
            cfg=template.model_copy(deep=True);cfg.decision_ref=REF
            cfg.decision_args={'lifetime_bundle':bundle,'seed':42,'llm_kind':'scripted','prompt_version':PROMPT_VERSION,'max_prompt_chars':18000}
            dump(dest/f'simulation_{arm}.json',cfg.model_dump())
            previews=[]
            for ob in observations:
                messages=build_messages(ob,bundle);serialized=json.dumps(messages,ensure_ascii=False)
                if len(serialized)>18000 or any(r['source_agent_id'] in serialized for r in links):
                    raise ValueError('prompt size or original ID leakage')
                previews.append({'agent_id':ob.agent_id,'messages':messages,'prompt_sha256':hashlib.sha256(serialized.encode()).hexdigest()})
            if arm!='text_history':
                old_arm='original' if arm=='original' else 'age_matched_episodes'
                old_previews=json.loads((base/month/f'preview_{old_arm}.json').read_text())
                if previews!=old_previews:raise ValueError('old original/numeric prompt changed')
            dump(dest/f'preview_{arm}.json',previews);previews_by_arm[arm]=previews
        dump(dest/'qualitative_history_private.json',history_text)
        for repeat in (1,2):
            offset=(MONTHS.index(month)+repeat-1)%3
            for arm in ARMS[offset:]+ARMS[:offset]:
                bounds=[(len(json.dumps(p['messages'],ensure_ascii=False).encode())+256)*.30/1e6+1024*1.20/1e6 for p in previews_by_arm[arm]]
                cap=math.ceil(sum(bounds)*100)/100;run_id=f'{folder.name}-{month}-{arm}-r{repeat}'
                command=[sys.executable,str(root/'scripts/run_sce_local.py'),'--llm','openai','--model',plan['model'],
                    '--population',str(dest/'population.json'),'--environment',str(dest/'environment.json'),
                    '--simulation',str(dest/f'simulation_{arm}.json'),'--prompt-version',PROMPT_VERSION,'--run-id',run_id,
                    '--temperature','.5','--max-tokens','1024','--retry-max','0','--max-calls','12',
                    '--extra-body','{"thinking":{"type":"disabled"}}','--price-in','.30','--price-out','1.20','--cost-cap-usd',str(cap),'--confirm-spend']
                plan['jobs'].append({'month':month,'arm':arm,'repeat':repeat,'run_id':run_id,'command':command,
                                    'conservative_cost_bound_usd':sum(bounds),'job_cap_usd':cap})
    plan['conservative_simulation_cost_bound_usd']=sum(j['conservative_cost_bound_usd'] for j in plan['jobs'])
    plan['proposed_simulation_cap_usd']=1.50
    if sum(j['job_cap_usd'] for j in plan['jobs'])>1.50:raise ValueError('inherited budget exceeded before any model call')
    plan['simulation_budget_authorization']='user_authorized_same_scope_and_new_1_50_cap; execute records exact quote'
    files=[root/'scripts/run_sce_local.py',root/'scripts/run_sce_lifetime_text_trial.py',root/'scripts/analyze_sce_lifetime_trial.py']+sorted((root/'studies/sce_inflation_expectations').rglob('*.py'))
    plan['code_sha256']={str(p.relative_to(root)):sha(p) for p in files}
    plan['prepared_file_sha256']={str(p.relative_to(folder)):sha(p) for p in folder.rglob('*.json')}
    dump(folder/'trial_manifest.json',plan)
    return plan


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','dry-run','run'])
    p.add_argument('--folder',type=Path,required=True);p.add_argument('--approval-note',default='');args=p.parse_args(argv)
    root=Path(__file__).resolve().parents[2]
    if args.mode=='prepare':
        plan=prepare(root,args.folder);print(json.dumps({k:plan[k] for k in ('planned_answers','conservative_simulation_cost_bound_usd','proposed_simulation_cap_usd')}))
    elif args.mode=='dry-run':print(json.dumps(dry_run(root,args.folder)))
    else:execute(root,args.folder,args.approval_note)
