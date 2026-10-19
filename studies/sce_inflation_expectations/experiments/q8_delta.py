"""Prepare one Q8-only format contrast from pinned old inputs, not targets."""
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import json
import math

from .frozen_batch import ROOT, read_json, dump, sha

PARENT = ROOT/'outputs/sce_revision_format_trial_20261015_v1'
TRUTH = ROOT/'outputs/sce_revision_format_evaluation_20261015_v1/cases_private.json'
REFERENCE = ROOT/'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'


def prepare(out, config):
    from socioverse.schemas import PopulationBundle
    from ..prior_belief_experiment import message_hash
    from ..q8_delta_contract import ARMS, candidate_contract
    from ..revision_format_runtime import DIRECT, previous_answer
    started=perf_counter();out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    if (config['mechanism']!='q8_delta_absolute_q9' or config['arms']!=list(ARMS)
            or config['months']!=[202004,202105,202111,202203] or config['n_per_month']!=24
            or config['generation_repeats']!=[1,2]):
        raise ValueError('Fixed small developer contrast required')
    parent=read_json(PARENT/'manifest.json')
    sources={str(p.relative_to(ROOT)):sha(p) for p in [PARENT/'manifest.json',TRUTH,REFERENCE]}
    def frozen(name):
        p=PARENT/name
        if sha(p)!=parent['prepared_file_sha256'][name]:
            raise ValueError('Archived input drift: '+name)
        sources[str(p.relative_to(ROOT))]=sha(p)
        return read_json(p)
    links=frozen('evaluation_links_private.json');out.mkdir(parents=True)
    selected=[];coverage={};jobs=[];reserve=estimate=0.;maximum=0;total_missing=0
    for month in config['months']:
        dest=out/str(month);dest.mkdir()
        pop=PopulationBundle.model_validate(frozen(f'{month}/population.json'))
        pop.materialized_count=len(pop.personas)
        env=frozen(f'{month}/environment.json')
        env['provider_args']['persona_by_id']={p.agent_id:p.attributes for p in pop.personas}
        cfg=frozen(f'{month}/simulation_direct.json');cfg['decision_args']={}
        dump(dest/'population.json',pop.model_dump(mode='json'));dump(dest/'environment.json',env)
        dump(dest/'simulation.json',cfg)
        previews=frozen(f'{month}/preview_direct.json');ids={p.agent_id for p in pop.personas}
        if len(ids)!=24 or {r['agent_id'] for r in previews}!=ids:
            raise ValueError('Archived prompt/roster mismatch')
        prior_points={};common={};messages_by_arm={a:{} for a in ARMS}
        for row in previews:
            aid=row['agent_id'];messages=row['messages']
            if message_hash(messages)!=row['prompt_sha256']:
                raise ValueError('Archived message hash drift')
            text=messages[0]['content']
            if not text.endswith(DIRECT):
                raise ValueError('Exact shared answer boundary required')
            prior_points[aid]=previous_answer(messages)['point_pct']
            prefix=text[:-len(DIRECT)];common[aid]=sha_text(prefix)
            for arm in ARMS:
                changed=deepcopy(messages)
                if arm=='q8_delta':
                    changed[0]['content']=prefix+candidate_contract(prior_points[aid])
                if not changed[0]['content'].startswith(prefix):
                    raise ValueError('Non-format input changed')
                messages_by_arm[arm][aid]={'messages':changed,'prompt_sha256':message_hash(changed)}
        chosen=[deepcopy(r) for r in links if r['month']==month and r['agent_id'] in ids]
        if len(chosen)!=24:
            raise ValueError('Archived evaluation roster mismatch')
        for link in chosen:
            # Preserve the archived sensitivity weights; do not invent new pi.
            link['design_survey_weight']=link['survey_weight']
            link['prior_q8_point']=prior_points[link['agent_id']]
        selected.extend(chosen)
        missing=sum(p is None for p in prior_points.values());total_missing+=missing
        coverage[str(month)]={'n':24,'missing_prior_q8_absolute_branch':missing,
                              'common_prefix_sha256':common}
        for arm,rows in messages_by_arm.items():
            dump(dest/f'prompts_{arm}.json',{'month':month,'arm':arm,'rows':rows})
            sizes=[len(json.dumps(r['messages'],ensure_ascii=False).encode()) for r in rows.values()]
            maximum=max(maximum,max(len(json.dumps(r['messages'],ensure_ascii=False)) for r in rows.values()))
            bound=sum(((size+256)*config['price_input_per_mtok']+config['max_tokens']*config['price_output_per_mtok'])/1e6 for size in sizes)
            guess=sum((size/4*config['price_input_per_mtok']+300*config['price_output_per_mtok'])/1e6 for size in sizes)
            for repeat in config['generation_repeats']:
                cap=math.ceil(bound*1e6)/1e6
                jobs.append({'month':month,'arm':arm,'repeat':repeat,'seed':41+repeat,
                             'run_id':f'{out.name}-{month}-{arm}-r{repeat}','cap_usd':cap})
                reserve+=cap;estimate+=guess
    if total_missing!=1 or reserve>config['budget_cap_usd']:
        raise ValueError('Prior coverage or conservative budget differs')
    protocol={**config,'planned_calls':len(jobs)*24,'max_prompt_chars':maximum+100,
        'evaluation_truth':str(TRUTH.relative_to(ROOT)),
        'evaluation_truth_format':'legacy_revision_format',
        'evaluation_bin_reference':str(REFERENCE.relative_to(ROOT)),
        'research_line':'A_conditional_returner_reconstruction',
        'comparison':'Only Q8 response format differs; Q9 absolute in both; contemporary control regenerated.',
        'primary_metric':'q8_cross_section_w1_pp','primary_weight':'equal_people_months_repeats',
        'q9_guard_weight':'archived_survey_weight_sensitivity_not_new_population_design',
        'missing_previous_q8_count':total_missing,
        'candidate_gate':'Exploratory continuation only: paired-person Q8 W1 upper95<0, Q8 center point no worse, both Q9 weighted center/W1 points no worse, Q8 and Q9 validity>=99%; no automatic upgrade.',
        'truth_isolation':'Only archived roster/P/E/previous prompts parsed in prepare; current targets hashed, never read.',
        'limits':['Four previously inspected development months; no independent validation.',
            'Current national returner population is not represented by a fresh probability sample here.',
            'Archived original survey weights retained as sensitivity only; primary Q8 equal-person.',
            'Two API generations do not increase independent people; mutable alias may differ from old batches.',
            'No Q9 negative-delta repair; no clipping, normalization, forced direction or fixed update size.',
            'Historical CE/news may be retrospective; conditional A experiment, not strict B.']}
    dump(out/'protocol.json',protocol);dump(out/'coverage.json',coverage)
    dump(out/'evaluation_links_private.json',selected)
    for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        sources[str(p.relative_to(ROOT))]=sha(p)
    sources['scripts/run_sce_frozen_trial.py']=sha(ROOT/'scripts/run_sce_frozen_trial.py')
    files={str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')}
    manifest={'jobs':jobs,'planned_calls':protocol['planned_calls'],
        'protocol_sha256':sha(out/'protocol.json'),'prepared_file_sha256':files,
        'source_sha256':sources,'proposed_cap_usd':config['budget_cap_usd'],
        'conservative_reservation_usd':reserve,'estimated_cost_usd':estimate,
        'timing_seconds':{'preparation':perf_counter()-started},'new_api_calls':0}
    dump(out/'manifest.json',manifest)
    dump(out/'authorization.json',{'approved':False,'protocol_sha256':manifest['protocol_sha256'],
        'cap_usd':config['budget_cap_usd'],'planned_calls':protocol['planned_calls'],
        'destination':config['destination'],'user_confirmation':None})
    print('Prepared',len(jobs),'units;',protocol['planned_calls'],'requests; estimate',round(estimate,3),
          'reserve',round(reserve,3),'cap',config['budget_cap_usd'],flush=True)
    return manifest


def sha_text(text):
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()
