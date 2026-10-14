"""Prepare a single-change contrast from existing frozen inputs, without truth selection."""
from collections import Counter
from copy import deepcopy
from datetime import datetime,timezone
import json
from pathlib import Path

import numpy as np
from socioverse.schemas import EnvironmentBundle,PopulationBundle,SimulationConfig

from .model import SCEEnvironmentProvider
from .expanded_state_runtime import build_messages as original_messages
from .anchor_role_runtime import REF,PROMPT,ARMS,build_messages
from .behavior_prompt_blocks import ANCHOR_BLOCK,insert_block
from .prior_belief_experiment import message_hash
from .evaluation.expanded_state import sha,dump

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'outputs/sce_expanded_state_trial_20261014_v3'
MONTHS=(202004,202105,202111,202203)
N=48
SEED=20261015
REPEATS=(1,2)
CAP=3.0


def prepare(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('fresh ignored output required')
    old=json.loads((SOURCE/'manifest.json').read_text())
    def frozen(month,name):
        path=SOURCE/str(month)/name
        if sha(path)!=old['prepared_file_sha256'][f'{month}/{name}']:raise ValueError('old input drift: '+name)
        return json.loads(path.read_text())
    sources={str((SOURCE/'manifest.json').relative_to(ROOT)):sha(SOURCE/'manifest.json')}
    for file in ['studies/sce_inflation_expectations/anchor_role_runtime.py',
                 'studies/sce_inflation_expectations/anchor_role_preparation.py',
                 'studies/sce_inflation_expectations/behavior_prompt_blocks.py',
                 'studies/sce_inflation_expectations/model.py',
                 'studies/sce_inflation_expectations/expanded_state_runtime.py',
                 'scripts/run_sce_anchor_role_trial.py']:
        sources[file]=sha(ROOT/file)
    for path in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        if '__pycache__' not in path.parts and 'evaluation' not in path.relative_to(ROOT/'studies/sce_inflation_expectations').parts:
            sources[str(path.relative_to(ROOT))]=sha(path)
    links=json.loads((SOURCE/'evaluation_links_private.json').read_text())
    if sha(SOURCE/'evaluation_links_private.json')!=old['prepared_file_sha256']['evaluation_links_private.json']:
        raise ValueError('evaluation link drift')
    sources[str((SOURCE/'evaluation_links_private.json').relative_to(ROOT))]=sha(SOURCE/'evaluation_links_private.json')
    protocol={
        'id':'sce-anchor-role-wording-v1','registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'research_line':'A_conditional_returner_reconstruction','months':list(MONTHS),'n_per_month':N,
        'sampling_seed':SEED,'generation_repeats':list(REPEATS),'arms':list(ARMS),
        'model':'deepseek-flash','official_advertised_version':'DeepSeek-V4.1-Flash','model_identity_limit':'Mutable alias, not fixed weights or verified training cutoff',
        'temperature':.5,'max_tokens':1024,'thinking':'disabled','retry_max':0,
        'price_input_per_mtok':.3,'price_output_per_mtok':1.2,'pricing_verified_date':'2026-10-14',
        'pricing_url':'https://api-docs.deepseek.com/quick_start/pricing/','budget_cap_usd':CAP,
        'comparison':'Both arms newly run in the same batch; only the exact ANCHOR_BLOCK differs. No frequency/gender/personality/model change.',
        'role_block':ANCHOR_BLOCK,'planned_calls':len(MONTHS)*N*len(ARMS)*len(REPEATS),
        'primary_contrast':'belief_start minus original on equal-month/repeat cross-section W1',
        'guardrails':['center MAE and delta W1 point values must not worsen for an overall candidate','at least 99% generated questionnaires structurally valid and scorable'],
        'candidate_gate':'W1 paired-person bootstrap upper 95% bound < 0; center MAE and delta W1 no worse; scorable coverage >=99%. This qualifies for further validation, not project success.',
        'mechanism_check':'Within-month slope on own prior mean, across-person IQR, rank correlation; do not treat a slope as an identified psychological weight.',
        'baseline_refs':['copy_previous','history_anchor_half'],'q8':'secondary, separate from Q9',
        'aggregation':'Each month/repeat separately, equal cell average; Q9 headline-style center is median of individually fitted density means, not a nationwide headline.',
        'intervals':'2000 paired-person resamples within month, both generations together; 4-month resampling sensitivity; seed 20261015',
        'truth_isolation':'Roster selected from frozen P only; current answers/weights/IDs confined to evaluation sidecar, no outcome screening or resampling.',
        'limits':['Four previously inspected development periods; no independent holdout claim.',
                  'Returners with actual private past answers and retrospective synthetic P; not real-time B.',
                  '2020Q4 CE proxy for 2020-04 is retrospective, not a PIT input.',
                  'Engine seeds do not imply a seeded or deterministic API generation.'],
        'no_tuning_after_run':True,
    }
    out.mkdir(parents=True);dump(out/'protocol.json',protocol)
    chosen_links=[];jobs=[];reserves=[];summary=[]
    for month in MONTHS:
        dest=out/str(month);dest.mkdir()
        pop=PopulationBundle.model_validate(frozen(month,'population.json'))
        ids=sorted(p.agent_id for p in pop.personas)
        selected=set(np.random.default_rng(np.random.SeedSequence([SEED,month])).choice(ids,N,replace=False).tolist())
        pop.personas=[p for p in pop.personas if p.agent_id in selected];pop.materialized_count=N
        if any(p.weight!=1 for p in pop.personas):raise ValueError('neutral population weights required')
        env=EnvironmentBundle.model_validate(frozen(month,'environment.json'))
        env.provider_args['persona_by_id']={p.agent_id:p.attributes for p in pop.personas}
        oldcfg=SimulationConfig.model_validate(frozen(month,'simulation_self_update.json'))
        base=deepcopy(oldcfg.decision_args['expanded_bundle'])
        base['rows']={aid:base['rows'][aid] for aid in selected}
        oldpreviews={p['agent_id']:p for p in frozen(month,'preview_self_update.json')}
        dump(dest/'population.json',pop.model_dump(mode='json'));dump(dest/'environment.json',env.model_dump(mode='json'))
        provider=SCEEnvironmentProvider(env.model_copy(deep=True));provider.audit_dir=None;provider.reset(42);provider.advance_to(1)
        observations=provider.observe_batch([p.agent_id for p in pop.personas],1)
        for arm in ARMS:
            bundle={'arm':arm,'base':deepcopy(base),'messages_sha256':{}}
            previews=[];reserve=0
            for ob in observations:
                original=original_messages(ob,base)
                if message_hash(original)!=oldpreviews[ob.agent_id]['prompt_sha256']:raise ValueError('base prompt not identical')
                messages=original if arm=='original' else insert_block(original,ANCHOR_BLOCK,require_prior=True)
                if arm=='belief_start' and messages[0]['content'].replace(ANCHOR_BLOCK,'')!=original[0]['content']:
                    raise ValueError('more than one block changed')
                for text in [m['content'] for m in messages]:
                    if any(term in text for term in ['"userid"','"weight"','Q9_mean','QSP5','MIDUS','sce_u']):raise ValueError('forbidden input field')
                bundle['messages_sha256'][ob.agent_id]=message_hash(messages)
                previews.append({'agent_id':ob.agent_id,'messages':messages,'prompt_sha256':message_hash(messages)})
                reserve+=(len(messages[0]['content'].encode())+256)*.3/1_000_000+1024*1.2/1_000_000
            for ob in observations:build_messages(ob,bundle)
            cfg=oldcfg.model_copy(deep=True);cfg.decision_ref=REF
            cfg.decision_args={'anchor_role_bundle':bundle,'prompt_version':PROMPT,'llm_kind':'scripted','seed':42,'max_prompt_chars':30000}
            dump(dest/f'simulation_{arm}.json',cfg.model_dump(mode='json'));dump(dest/f'preview_{arm}.json',previews)
            for repeat in REPEATS:
                cap=float(np.ceil((reserve+.000001)*1e4)/1e4)
                jobs.append({'month':month,'arm':arm,'repeat':repeat,'cap_usd':cap,
                             'run_id':f'{out.name}-{month}-{arm}-r{repeat}'})
                reserves.append(reserve)
        chosen_links += [r for r in links if r['month']==month and r['agent_id'] in selected]
        for name in ['population.json','environment.json','simulation_self_update.json','preview_self_update.json']:
            path=SOURCE/str(month)/name;sources[str(path.relative_to(ROOT))]=sha(path)
        summary.append({'month':month,'n':N,'as_of':env.provider_args['targets'][0]['as_of'],
                        'age_counts':dict(Counter(p.attributes['age_group'] for p in pop.personas))})
    # Randomize cell dispatch order before seeing any new answers.
    order=np.random.default_rng(SEED).permutation(len(jobs));jobs=[jobs[i] for i in order]
    if len(chosen_links)!=N*len(MONTHS):raise ValueError('evaluation sidecar coverage')
    dump(out/'evaluation_links_private.json',chosen_links)
    files={str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')}
    manifest={'status':'prepared_not_authorized','source_sha256':sources,'prepared_file_sha256':files,
              'jobs':jobs,'monthly_rosters':summary,'planned_calls':protocol['planned_calls'],
              'sum_job_caps_usd':sum(j['cap_usd'] for j in jobs),'conservative_reservation_usd':sum(reserves),
              'proposed_cap_usd':CAP,'new_api_calls':0,'protocol_sha256':sha(out/'protocol.json')}
    if manifest['sum_job_caps_usd']>CAP:raise ValueError('planned bound exceeds proposed cap')
    dump(out/'manifest.json',manifest)
    return manifest
