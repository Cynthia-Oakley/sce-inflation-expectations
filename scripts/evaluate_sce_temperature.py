"""Evaluation-only adapter: a factual respondent-month target is repeat invariant.

The frozen legacy cache indexes two API repeats, but the temperature trial has
four. Expand target keys in memory after requiring identical cached copies.
Never alter pinned source, cache, manifest, model answers or input prompts.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.evaluation import q8_delta, frozen_trial
from studies.sce_inflation_expectations.experiments.frozen_batch import verify, dump


def main(folder,out):
    manifest,protocol=verify(folder)
    if protocol['mechanism']!='temperature_sensitivity' or protocol['generation_repeats']!=[1,2,3,4]:
        raise ValueError('Registered four-repeat temperature evaluation only')
    original=q8_delta.legacy_truth;details={}
    def repeat_invariant_truth(rows,reference):
        cached=original(rows,reference);by_person={}
        for (month,aid,repeat),target in cached.items():
            key=(month,aid)
            if key in by_person and json.dumps(by_person[key],sort_keys=True)!=json.dumps(target,sort_keys=True):
                raise ValueError('Cached factual truth changes across API repeat keys')
            by_person[key]=target
        expanded={(month,aid,repeat):target for (month,aid),target in by_person.items()
                  for repeat in protocol['generation_repeats']}
        details.update(original_cached_keys=len(cached),expanded_keys=len(expanded),
                       factual_person_months=len(by_person),cached_copies_identical=True)
        return expanded
    q8_delta.legacy_truth=repeat_invariant_truth
    try:result=frozen_trial.evaluate(folder,out)
    finally:q8_delta.legacy_truth=original
    dump(Path(out)/'evaluation_adapter_receipt.json',{
        'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'reason':'Legacy truth uses two API-repeat keys; one factual person-month target reused for four repeats.',
        'frozen_protocol_sha256':manifest['protocol_sha256'],
        'adapter_source':'scripts/evaluate_sce_temperature.py',
        'adapter_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'pinned_sources_inputs_and_answers_unchanged':True,'new_api_calls':0,**details})
    print(json.dumps({'status':result['status'],'evaluation_seconds':result['evaluation_seconds'],**details}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--folder',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();main(a.folder,a.out)
