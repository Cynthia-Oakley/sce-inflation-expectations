"""Prepare outcome-free Core/audit roles for a later, separately approved pilot."""
from collections import Counter
import json
from pathlib import Path

import numpy as np

from .frozen_batch import ROOT, dump, read_json, sha
from ..population.grid_sampling import plan_core, draw_core
from ..evaluation.core_normal_validation import PROTOCOL, population_frame, profiles, allocation_records


def prepare(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored preparation required')
    p=json.loads(PROTOCOL.read_text());settings=p['pilot_preparation']
    frame=population_frame();frame=frame.loc[np.isfinite(frame.weight)&frame.weight.gt(0)]
    out.mkdir(parents=True);summary=[]
    for month in settings['months']:
        rows=frame.loc[frame.date.eq(month)];population=profiles(rows)
        records=allocation_records(population)
        plan=plan_core(records,settings['core_n'],minimum=settings['core_floor'])
        core=draw_core(records,plan,seed=20261023,month=month);core_ids={r['id'] for r in core}
        remaining=[r for r in records if r['id'] not in core_ids]
        audit_plan=plan_core(remaining,settings['audit_llm_n'],minimum=settings['audit_floor'])
        audit=draw_core(remaining,audit_plan,seed=20261024,month=month)
        if core_ids & {r['id'] for r in audit}:raise ValueError('Core/audit overlap')
        entry={r['id']:r['entry'] for r in population}
        if set(entry.values())-set(entry[u] for u in core_ids):raise ValueError('Core does not represent every entry pool')
        folder=out/str(month);folder.mkdir()
        dump(folder/'population_private.json',{'month':month,'scope':'historical_A_positive_original_weight_frame',
             'people':population,'note':'Local frame includes weights/sex for analysis; not an outbound LLM prompt.'})
        dump(folder/'core_roster_private.json',{'month':month,'selected':core,'allocation':plan})
        dump(folder/'audit_roster_private.json',{'month':month,'selected':audit,'allocation':audit_plan,
             'rule':'Audit LLM answers are evaluation-only; never pass into the Core expansion fit.'})
        summary.append({'month':month,'frame_n':len(population),'core_n':len(core),'audit_n':len(audit),
                        'normal_n':len(population)-len(core),
                        'core_entry_counts':dict(Counter(entry[u] for u in core_ids)),
                        'audit_entry_counts':dict(Counter(entry[r['id']] for r in audit)),
                        'core_unknown_n':sum(r['cell']=='unknown' for r in core)})
    result={'status':'roles_ready_not_prompt_or_api_ready','new_api_calls':0,
            'protocol':p,'months':summary,'maximum_calls_before_exact_prompt_reuse':sum(r['core_n']+r['audit_n'] for r in summary),
            'generation_repeats':1,'model':'deepseek/deepseek-v3.2','provider':'OpenRouter -> SiliconFlow FP8',
            'pending':['Kimi/Codex monthly input adapter: recent own/donor beliefs for new selected IDs',
                       'Existing E/news/policy/price prompt assembly and official Core dry run',
                       'Exact prompt-hash reuse check and token/cost estimate',
                       'Explicit destination/data-scope/budget authorization'],
            'not_authorized':['No model request','No 82-month run','No audit-answer fitting','No new/current human inflation answers sent'],
            'source_sha256':{str(path.relative_to(ROOT)):sha(path) for path in [PROTOCOL,Path(__file__),
                ROOT/'outputs/sce_population_associations_20261015_v1/analysis_frame_private.parquet',
                ROOT/'studies/sce_inflation_expectations/population/grid_sampling.py']}}
    dump(out/'summary.json',result)
    return result
