#!/usr/bin/env python3
"""Evaluation-only merge of pinned truth; never changes news or populations."""
from pathlib import Path
from copy import deepcopy
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import dump,read_json,sha
from studies.sce_inflation_expectations.evaluation.frozen_trial import score_bins
from studies.sce_inflation_expectations.experiments.news_matching import OLD,NEW,PRIOR_START


def prepare(config,out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh evaluation-only folder required')
    result=[];sources={}
    for kind,months in [('old',OLD),('new',NEW)]:
        parent=ROOT/config['source_trials'][kind];manifest=read_json(parent/'manifest.json')
        protocol=read_json(parent/'protocol.json');f=ROOT/protocol['evaluation_truth']
        expected=manifest['source_sha256'][str(f.relative_to(ROOT))]
        if sha(f)!=expected:raise ValueError('Frozen truth changed')
        sources[str(f.relative_to(ROOT))]=expected
        by_key={(r['month'],r['agent_id'],r['repeat']):r['real'] for r in read_json(f)}
        for month in months:
            p=parent/str(month)/'prompts_deepseek_v32.json'
            if sha(p)!=manifest['prepared_file_sha256'][str(p.relative_to(parent))]:raise ValueError('Frozen prior prompt changed')
            sources[str(p.relative_to(ROOT))]=sha(p)
            for aid,row in read_json(p)['rows'].items():
                # The previous answer is already explicitly present in the frozen
                # input, not inferred from current truth or from new LLM output.
                text=row['messages'][0]['content'];part=text[text.index(PRIOR_START):]
                prior,_=json.JSONDecoder().raw_decode(part[part.index('{'):])
                priorbins=[prior['q9'][f'bin{i}'] for i in range(1,11)]
                score=score_bins(tuple(priorbins))
                for repeat in (1,2):
                    real=deepcopy(by_key[month,aid,repeat])
                    if real['previous_q9_bins'] != priorbins:raise ValueError('Prior probability mismatch')
                    real.update(previous_q8_point=prior['point_pct'],previous_q9_iqr=score['iqr'],
                                previous_q9_zero_deflation=float(sum(priorbins[5:])==0))
                    result.append(dict(month=month,agent_id=aid,repeat=repeat,real=real))
    if len(result)!=2304:raise ValueError('Fixed eight-month 1152-person-month truth required')
    out.mkdir(parents=True);dump(out/'truth_private.json',result)
    dump(out/'manifest.json',dict(scope='Evaluation only; current answers cannot enter preparation or dispatch',
        source_sha256=sources,prepared_file_sha256={'truth_private.json':sha(out/'truth_private.json')},
        records=len(result),new_api_calls=0))
    return dict(records=len(result),new_api_calls=0)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(prepare(read_json(a.config),a.out))
