#!/usr/bin/env python3
"""Split one already-built full basket population into Core/Normal, offline.

Both roles inherit the same assigned baskets. This does not generate answers
or make the existing Normal estimator basket-aware.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from socioverse.schemas import PopulationBundle
from studies.sce_inflation_expectations.price_experience import profile_hash


def split_roles(full, core, experience):
    PopulationBundle.model_validate(full)
    PopulationBundle.model_validate(core)
    people = {p['agent_id']: p for p in full['personas']}
    core_people = {p['agent_id']: p for p in core['personas']}
    if len(people) != len(full['personas']) or len(core_people) != len(core['personas']):
        raise ValueError('duplicate population IDs')
    if not core_people or not set(core_people) < set(people):
        raise ValueError('need nonempty Core and Normal in the full population')
    month = full['provider_args'].get('target_month')
    if core['provider_args'].get('target_month') != month:
        raise ValueError('Core/full target months differ')
    if experience.get('target_month') not in (month, f'{str(month)[:4]}-{str(month)[4:]}'):
        raise ValueError('basket target month differs')
    if experience.get('research_line') != 'A_historical_reconstruction':
        raise ValueError('this splitter supports the current A contract only')
    baskets = experience['experience_by_id']
    if set(baskets) != set(people):
        raise ValueError('full basket ID set differs')
    for uid, person in people.items():
        if baskets[uid].get('agent_id') != uid or baskets[uid]['profile_sha256'] != profile_hash(person['attributes']):
            raise ValueError('basket/profile mismatch')
    for uid, person in core_people.items():
        if person != people[uid]:
            raise ValueError('Core persona differs from full population')
    roles = {'core': set(core_people), 'normal': set(people) - set(core_people)}
    result = {}
    for role, ids in roles.items():
        pop = copy.deepcopy(core if role == 'core' else full)
        pop['personas'] = [copy.deepcopy(people[u]) for u in sorted(ids)]
        pop['materialized_count'] = len(ids)
        pop['provider_args']['population_role'] = role
        if role == 'normal':
            pop['provider_args']['sampling_design'] = 'complement_of_existing_core'
        PopulationBundle.model_validate(pop)
        exp = copy.deepcopy(experience)
        exp['experience_by_id'] = {u: copy.deepcopy(baskets[u]) for u in sorted(ids)}
        result[role] = (pop, exp)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--population', type=Path, required=True)
    ap.add_argument('--core-population', type=Path, required=True)
    ap.add_argument('--experience', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    inputs = {k: p.resolve() for k, p in vars(args).items() if k != 'output'}
    result = split_roles(*(json.loads(inputs[k].read_text()) for k in ['population','core_population','experience']))
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    counts = {}
    for role, (pop, exp) in result.items():
        folder = out / role
        folder.mkdir()
        pop_text = json.dumps(pop, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        exp['population_sha256'] = hashlib.sha256(pop_text.encode()).hexdigest()
        (folder/'population.json').write_text(pop_text, encoding='utf-8')
        (folder/'experience.json').write_text(json.dumps(exp,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        counts[role] = len(pop['personas'])
    snapshot = out/'source_snapshot'
    snapshot.mkdir()
    (snapshot/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    manifest = {'input_files': {k:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for k,p in inputs.items()},
                'counts':counts,'basket_generation_identical_for_roles':True,'llm_calls':0,
                'normal_estimator_updated':False,'normal_answers_generated':False,
                'files':{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'output':str(out),**counts},ensure_ascii=False))


if __name__ == '__main__':
    main()
