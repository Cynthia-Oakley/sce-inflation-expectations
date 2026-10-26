"""Outcome-free shared-call roster for comparing several Core budgets.

Each budget keeps its own registered sampling weights. Extra LLM audit people
come from outside the UNION of all Core rosters, and remain evaluation-only.
No answers, provider client, prompt assembly or paid authorization are read.
"""
from collections import Counter
from pathlib import Path

from .frozen_batch import ROOT, read_json, dump, sha
from ..population.grid_sampling import plan_core, draw_core
from ..evaluation.core_normal_validation import allocation_records

SOURCE = ROOT / 'outputs/sce_core_normal_pilot_preparation_20261023_v1'
SETTINGS = ((256, 4), (384, 6), (512, 8))
MONTHS = (202109, 202206, 202506)


def shared_design(population, *, month, settings=SETTINGS, audit_n=64):
    """Use the existing per-budget design; never assume nesting is guaranteed."""
    records = allocation_records(population)
    designs = {}; union = set(); previous = set(); nested = True
    for budget, floor in sorted(settings):
        plan = plan_core(records, budget, minimum=floor)
        selected = draw_core(records, plan, seed=20261023, month=month)
        ids = {r['id'] for r in selected}
        nested = nested and previous <= ids
        designs[str(budget)] = {'month': month, 'selected': selected, 'allocation': plan}
        union.update(ids); previous = ids
    remaining = [r for r in records if r['id'] not in union]
    audit_plan = plan_core(remaining, audit_n, minimum=1)
    audit = draw_core(remaining, audit_plan, seed=20261024, month=month)
    if union & {r['id'] for r in audit}:
        raise ValueError('Audit and Core union overlap')
    entry = {r['id']: r['entry'] for r in population}
    for design in designs.values():
        if set(entry.values()) - {entry[r['id']] for r in design['selected']}:
            raise ValueError('Each Core design must support every entry pool')
    return {
        'designs': designs,
        'core_union': [{'id': uid, 'core_budgets': [int(b) for b, d in designs.items()
                        if uid in {r['id'] for r in d['selected']}]} for uid in sorted(union)],
        'audit': {'month': month, 'selected': audit, 'allocation': audit_plan,
                  'support': 'conditional on all selected Core rosters; outside their union'},
        'summary': {'month': month, 'frame_n': len(population),
                    'core_budgets': [int(b) for b in designs], 'nested': nested,
                    'core_union_n': len(union), 'audit_n': len(audit),
                    'shared_audit_population_n': len(remaining),
                    'unique_llm_positions': len(union) + len(audit),
                    'core_entry_counts': {b: dict(Counter(entry[r['id']] for r in d['selected']))
                                          for b, d in designs.items()}}}


def prepare(out, *, source=SOURCE):
    out, source = Path(out).resolve(), Path(source).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output directory required')
    prepared = []; sources = {}
    # Validate all months before creating the new output directory.
    for month in MONTHS:
        path = source / str(month) / 'population_private.json'
        p = read_json(path)
        if str(p['month']) != str(month):
            raise ValueError('Population month mismatch')
        design = shared_design(p['people'], month=month)
        old_path = source / str(month) / 'core_roster_private.json'
        old = read_json(old_path)
        if old['selected'] != design['designs']['256']['selected']:
            raise ValueError('Previously prepared 256 Core must remain unchanged')
        sources.update({str(path.relative_to(ROOT)): sha(path),
                        str(old_path.relative_to(ROOT)): sha(old_path)})
        prepared.append((month, p, design))
    out.mkdir(parents=True)
    for month, population, design in prepared:
        folder = out / str(month); folder.mkdir()
        dump(folder / 'population_private.json', population)
        for budget, data in design['designs'].items():
            dump(folder / f'core_{budget}_roster_private.json', data)
        dump(folder / 'core_union_private.json', {'month': month, 'selected': design['core_union']})
        dump(folder / 'audit_roster_private.json', design['audit'])
    result = {
        'status': 'shared_scale_rosters_ready_not_prompt_or_api_ready',
        'scope': 'Three historical A months; proposed replacement for the single-size pilot, not authorized',
        'months': [d['summary'] for _, _, d in prepared],
        'generation_repeats': 1, 'new_api_calls': 0, 'new_q9_fits': 0,
        'maximum_unique_requests_before_exact_prompt_reuse': sum(d['summary']['unique_llm_positions'] for _, _, d in prepared),
        'separate_size_pilots_without_sharing': sum(sum(b for b, _ in SETTINGS) + 64 * len(SETTINGS) for _ in MONTHS),
        'weight_rule': 'Each budget uses its own pi/calibrated weights; original weights aggregate its Core + Normal once',
        'shared_audit_rule': 'Common held-out population is outside the Core UNION. Its conditional audit weights do not estimate the entire Normal population for smaller Core budgets.',
        'no_leakage_rule': 'For a smaller-budget fit, additional larger-Core LLM answers are hidden, even though the batch acquired them.',
        'tau': {'primary': 24, 'offline_sensitivity': [0, 8], 'reselect_using_pilot': False},
        'not_ready': ['Role-independent full-frame P/E/history prompts', 'Exact prompt/route/parameter cache matches',
                      'Frozen evaluation and Core dry run', 'Token budget and explicit new paid authorization'],
        'source_sha256': {**sources, str(Path(__file__).relative_to(ROOT)): sha(Path(__file__)),
                          'studies/sce_inflation_expectations/population/grid_sampling.py': sha(ROOT / 'studies/sce_inflation_expectations/population/grid_sampling.py')}}
    dump(out / 'summary.json', result)
    return result
