"""54-cell opt-in adapter; share prompts, Core checks and one-attempt runtime."""
from pathlib import Path
import math

from .frozen_batch import ROOT, read_json, dump, sha
from .monthly_reconstruction_pipeline import finish as assemble_base
from .monthly_reconstruction_execution import prepare as freeze_base
from ..population.monthly_fine_grid import GRID_VERSION


def assemble(inputs, families, environments, out, *, delivery, policy_supplement=None,
             confidence_supplement=None,prepared_prompts=None):
    inputs,out=Path(inputs).resolve(),Path(out).resolve()
    s=read_json(inputs/'summary.json')
    if s.get('grid_version') != GRID_VERSION or s.get('primary_weight') != 'poststratified_weight':
        raise ValueError('Declared 54-cell poststratified inputs required')
    if s.get('potential_unique_calls_before_prompt_hash')!=s['logical_positions']:
        raise ValueError('Exact request count required before generating prompts')
    result=assemble_base(inputs,families,environments,out,delivery=delivery,
                         policy_supplement=policy_supplement,confidence_supplement=confidence_supplement,
                         prepared_prompts=prepared_prompts)
    recipe=read_json(out/'evaluation_recipe.json')
    recipe.update(schema_version=2,grid_version=GRID_VERSION,
        weights='Within-cell design weight w/pi, calibrated to the full positive-weight frame mass of each of the 54 cells plus unknown; primary weighted empirical-CDF statistics. Equal-person sensitivity reported separately.',
        primary_result_path='auxiliary_survey_weighted',
        predeclared_groups=['education x numeracy x age x income plus unknown','education','age','income',
                           'numeracy','four Census regions','survey-entry status','initial-belief provenance'])
    recipe['remaining_registration']=['Explicit paid scope and cap','Strict-B release eligibility and prior updating; not part of this A run']
    dump(out/'evaluation_recipe.json',recipe)
    result.update(grid_version=GRID_VERSION,n_per_month=s['n_per_month'],minimum_floor=s['minimum_floor'],
                  primary_weight='poststratified_weight',sampling_seed=s['sampling_seed'],
                  evaluation_recipe_sha256=sha(out/'evaluation_recipe.json'))
    result['source_sha256'][str(Path(__file__).relative_to(ROOT))]=sha(Path(__file__))
    result['limits']=[v for v in result['limits'] if 'three-month bundle' not in v]
    result['limits'].append('54-cell direct-LLM sample. No Normal expansion. A historical reconstruction only.')
    dump(out/'manifest.json',result)
    return result


def freeze(assembly,out,*,cap_usd):
    """A cap is a proposed hard stop, never authority to send any request."""
    if not math.isfinite(cap_usd) or cap_usd<=0: raise ValueError('Positive proposed cap required')
    assembly,out=Path(assembly).resolve(),Path(out).resolve()
    a=read_json(assembly/'manifest.json')
    if a.get('grid_version') != GRID_VERSION: raise ValueError('54-cell assembly required')
    freeze_base(assembly,out)
    p=read_json(out/'protocol.json');m=read_json(out/'manifest.json')
    p.update(grid_version=GRID_VERSION,primary_weight='poststratified_weight',minimum_floor=a['minimum_floor'],
             budget_mode='spent_plus_inflight_reservation',budget_cap_usd=float(cap_usd),
             budget_note='Stop before dispatch if settled charges + unknown-charge reservations + in-flight worst-case reservations + next reservation exceed the cap. Completion of all calls is not guaranteed by the estimate.')
    p['randomness']['input_assignments']='54-cell P-only SRSWOR, floor8, post-stratified to cell masses; recent donors; random news and fixed role assignments'
    p['randomness']['sampling_seed']=a['sampling_seed']
    p['randomness']['dispatch_seed']=20261022
    # No current truth or evaluation cache path is included in this runner package.
    source_files=[Path(__file__),ROOT/'studies/sce_inflation_expectations/experiments/monthly_fine_inputs.py',
                  ROOT/'studies/sce_inflation_expectations/population/monthly_fine_grid.py',
                  ROOT/'studies/sce_inflation_expectations/population/grid_sampling.py',
                  ROOT/'studies/sce_inflation_expectations/experiments/monthly_main_pipeline.py',
                  ROOT/'studies/sce_inflation_expectations/evaluation/monthly_reconstruction.py',
                  ROOT/'studies/sce_inflation_expectations/evaluation/monthly_main_readout.py',
                  ROOT/'studies/sce_inflation_expectations/evaluation/monthly_release_registry.py',
                  ROOT/'studies/sce_inflation_expectations/evaluation/aggregate_blend.py',
                  ROOT/'scripts/run_sce_monthly_main_pipeline.py',ROOT/'scripts/readout_sce_monthly_main.py',
                  ROOT/'scripts/evaluate_sce_monthly_reconstruction.py']
    for f in source_files:
        m['source_sha256'][str(f.relative_to(ROOT))]=sha(f)
        target=out/'source_snapshot'/f.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(f.read_bytes())
    dump(out/'protocol.json',p);m['protocol_sha256']=sha(out/'protocol.json');dump(out/'manifest.json',m)
    return {k:p[k] for k in ['planned_calls','estimated_cost_usd','full_conservative_reservation_usd','budget_cap_usd','budget_mode','grid_version']}
