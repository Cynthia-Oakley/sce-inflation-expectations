"""Freeze the independent monthly main run for the existing one-attempt queue.

No live API client is instantiated by preparation. Authorization and execution
reuse state_continuity_execution; independent nodes have no state dependencies.
"""
from datetime import datetime,timezone
from pathlib import Path
import math

from .frozen_batch import ROOT,dump,read_json,sha
from .state_continuity_execution import reserve


def prepare(assembly,out):
    assembly,out=map(lambda p:Path(p).resolve(),(assembly,out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored execution package required')
    a=read_json(assembly/'manifest.json')
    if a['status']!='offline_monthly_A_bundle_complete_not_paid_authorized':
        raise ValueError('Complete official-engine assembly required')
    inputs=ROOT/a['inputs'];prompts=assembly/'prompts';core=assembly/'core_engineering'
    s=read_json(prompts/'summary.json');c=read_json(core/'summary.json')
    nodes=read_json(inputs/'state_dependencies_private.json')
    if any(n['dependency'] is not None for n in nodes) or c['official_engine_units']!=len(a['months']) or c['decisions']!=len(nodes):
        raise ValueError('Exact independent-month official Core coverage required')
    if len({n['logical_reuse_key'] for n in nodes})!=len(nodes):
        raise ValueError('One distinct main generation per person-month required')
    provider=ROOT/'data/raw/mcp_checks/2026-10-21_v32_fullperiod_free_v1/deepseek_v32_endpoints.json'
    p=dict(mechanism='monthly_reconstruction_v1',months=a['months'],arms=['monthly_reconstruction'],
        generation_repeats=[1],n_per_month=512,planned_calls=len(nodes),logical_positions=len(nodes),
        randomness={'dispatch_seed':20261022,'input_assignments':'frozen six-cell SRS, recent donors, random news and role records',
                    'generation_seed':None,'note':'One stochastic main generation; no claim of bitwise model reproducibility.'},
        destination='https://openrouter.ai/api/v1',model='deepseek/deepseek-v3.2',route='siliconflow/fp8',expected_provider='SiliconFlow',
        temperature=.5,thinking='disabled',response_format='json_object',max_tokens=1024,timeout_s=120,
        retry_max=0,provider_fallback=False,price_input_per_mtok=.259,price_output_per_mtok=.8,
        max_prompt_chars=s['runtime_character_cap'],max_prompt_bytes=s['runtime_utf8_byte_cap'],
        technical_gate={'calls':32,'minimum_usable':31},
        concurrency_stages=[{'after_completed':0,'workers':8},{'after_completed':32,'workers':64}],
        error_policy='One attempt per slot. Stop on HTTP errors/provider mismatch/budget violation or three consecutive connection failures; drain in-flight calls. Manual continuation only for never-attempted slots.',
        q9_postprocessing='proportional_nonnegative_v1',
        field_fallback='Failed/non-stop/unusable fields retain the declared initial state. Never replace a respondent.',
        input_templates=str(prompts.relative_to(ROOT)),preparation=str(inputs.relative_to(ROOT)),core_check=str(core.relative_to(ROOT)),
        delivery=a['delivery'],
        provider_metadata=str(provider.relative_to(ROOT)),
        evaluation_recipe=str((assembly/'evaluation_recipe.json').relative_to(ROOT)),
        macro_combination={'form':'(1-alpha)*last eligible published national SCE + alpha*current simulated median; 0<=alpha<=1',
             'fit_months':['2019-01','2022-12'],'evaluation_months':['2023-01','2025-10'],
             'primary_loss':'MAE','secondary_loss':'MSE','fit_intercept':False,
             'seen_months_note':'Previously inspected sample months disclosed separately; later evaluation is not wholly blind.',
             'raw_simulation_and_persistence_always_reported':True},
        research_line='A_historical_reconstruction_with_observed_past_personal_answers',
        strict_B_eligible=False,created_at_utc=datetime.now(timezone.utc).isoformat())
    p['request_extra_body']={'provider':{'order':[p['route']],'allow_fallbacks':False,'require_parameters':True,
                                          'max_price':{'prompt':.259,'completion':.8}},'reasoning':{'enabled':False}}
    p['full_conservative_reservation_usd']=p['planned_calls']*reserve(p,p['max_prompt_bytes'])
    p['budget_cap_usd']=math.ceil(p['full_conservative_reservation_usd']/5)*5
    p['estimated_cost_usd']=s['estimated_cost_usd']
    sources={str(path.relative_to(ROOT)):sha(path) for path in [assembly/'manifest.json',assembly/'evaluation_recipe.json',
        inputs/'summary.json',inputs/'state_dependencies_private.json',core/'summary.json',provider]}
    sources.update(s['source_sha256'])
    for path in prompts.rglob('*.json'): sources[str(path.relative_to(ROOT))]=sha(path)
    code=[Path(__file__),Path(__file__).with_name('state_continuity_execution.py'),
          Path(__file__).with_name('state_continuity_dry_run.py'),Path(__file__).with_name('state_continuity_inputs.py'),
          Path(__file__).with_name('monthly_reconstruction_inputs.py'),Path(__file__).with_name('state_continuity_prompts.py')]
    for name in ['state_continuity_runtime.py','model.py','model_counterfactual.py','q9_normalization.py','scoring/sce_q9_frozen.py']:
        code.append(ROOT/'studies/sce_inflation_expectations'/name)
    for path in (core/'source_snapshot').rglob('*.py'):
        relative=path.relative_to(core/'source_snapshot')
        if sha(ROOT/relative)!=sha(path): raise ValueError('Core checked source changed: '+str(relative))
    sources.update({str(path.relative_to(ROOT)):sha(path) for path in code})
    out.mkdir(parents=True)
    dump(out/'protocol.json',p)
    dump(out/'manifest.json',dict(protocol_sha256=sha(out/'protocol.json'),source_sha256=sources,
         new_api_calls=0,truth_in_execution_inputs=False,authorization_status='not_authorized'))
    for path in code:
        dest=out/'source_snapshot'/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(path.read_bytes())
    return {k:p[k] for k in ('planned_calls','estimated_cost_usd','full_conservative_reservation_usd','budget_cap_usd')}
