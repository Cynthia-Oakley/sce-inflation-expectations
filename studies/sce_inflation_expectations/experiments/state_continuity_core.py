"""Use the existing frozen-prompt worker for zero-API official Core checks."""
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha, worker
from .state_continuity_dry_run import dry_run


def check(preparation, prompts, out):
    preparation, prompts, out = map(Path, (preparation, prompts, out))
    if out.exists(): raise ValueError('Fresh engineering output folder required')
    nodes = read_json(preparation / 'state_dependencies_private.json')
    source = read_json(prompts / 'summary.json')
    inputs = {}
    for month in source['coverage']:
        m = month['month']; base = prompts / m
        templates = read_json(base / 'templates_private.json')
        states = read_json(base / 'initial_states_private.json')
        context = read_json(base / 'timing_context_private.json')
        inputs.update({(m, aid): (v, states[aid], context[aid]) for aid, v in templates.items()})
    replay = dry_run(nodes, inputs, capture_all=True)
    full = replay.pop('full_rows_private'); replay.pop('preview_rows_private')
    out.mkdir(parents=True)
    sample_config = ROOT / 'outputs/sce_v32_new2025_trial_20261022_v4/202506/simulation.json'
    receipts = []
    source_hashes = {str(sample_config.relative_to(ROOT)): sha(sample_config),
                     str(Path(__file__).relative_to(ROOT)): sha(__file__)}
    for name in ['state_continuity_dry_run.py', 'state_continuity_inputs.py', 'frozen_batch.py']:
        p = Path(__file__).with_name(name); source_hashes[str(p.relative_to(ROOT))] = sha(p)
    for name in ['state_continuity_runtime.py', 'frozen_prompt_runtime.py', 'model.py', 'scoring/sce_q9_frozen.py']:
        p = ROOT / 'studies/sce_inflation_expectations' / name
        source_hashes[str(p.relative_to(ROOT))] = sha(p)
    for name in source_hashes:
        target = out / 'source_snapshot' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    for cell, rows in full.items():
        month, arm, repeat_string = cell.split('-'); repeat = int(repeat_string[1:])
        folder = out / cell; destination = folder / month; destination.mkdir(parents=True)
        for name in ['population.json', 'environment.json']:
            dump(destination / name, read_json(prompts / month / name))
        dump(destination / 'simulation.json', read_json(sample_config))
        dump(destination / f'prompts_{arm}.json', {'month': int(month), 'arm': arm, 'rows': rows})
        protocol = dict(execution_mode='engineering_only', destination=None,
                        model='NOT_CONFIGURED_ENGINEERING_ONLY', mechanism='state_continuity_engine_check',
                        months=[int(month)], arms=[arm], generation_repeats=[repeat], n_per_month=len(rows),
                        engineering_decision_count=len(rows), planned_calls=0, budget_cap_usd=0,
                        temperature=.5, max_tokens=1024, retry_max=0, thinking='disabled',
                        max_prompt_chars=source['runtime_character_cap'],
                        price_input_per_mtok=0, price_output_per_mtok=0)
        dump(folder / 'protocol.json', protocol)
        job = dict(month=int(month), arm=arm, repeat=repeat, seed=41+repeat,
                   run_id=f'{out.parent.name}-{out.name}-{cell}', cap_usd=0)
        dump(folder / 'manifest.json', dict(planned_calls=0, jobs=[job],
             protocol_sha256=sha(folder / 'protocol.json'), source_sha256=source_hashes,
             prepared_file_sha256={str(p.relative_to(folder)): sha(p) for p in folder.rglob('*.json')}))
        receipt = worker(folder, 0, True)
        receipts.append(receipt)
    summary = dict(status='completed_official_core_scripted_checks', official_engine_units=len(receipts),
                   decisions=sum(len(rows) for rows in full.values()), new_api_calls=0,
                   state_dependency_replay=replay, receipts=receipts,
                   limits='Deterministic fixture state checks only; no LLM accuracy or live runtime acceptance')
    dump(out / 'summary.json', summary)
    return {k: v for k, v in summary.items() if k not in ('receipts', 'state_dependency_replay')}
