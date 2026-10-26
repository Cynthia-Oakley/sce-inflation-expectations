#!/usr/bin/env python3
"""Missing-support sensitivity from already scored responses, with no refits."""
from copy import deepcopy
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import read_json,dump,sha
from studies.sce_inflation_expectations.evaluation import cognition as shared
from studies.sce_inflation_expectations.evaluation.price_background_readout import summarize


def analyze(cases,arm,months):
    separate={}
    for rep in (1,2):
        rows=[r for r in cases if r['repeat']==rep]
        support=shared._common_person_months(rows,[arm],[rep],'q9')
        separate[str(rep)]=summarize(rows,[arm],months,[rep],support)
    rows=deepcopy(cases);support=set();fallbacks=0
    for r in rows:
        real=r['real']
        valid=(all(shared.finite(real.get(k)) for k in ('q9_mean','q9_iqr','q9_zero_deflation'))
            and len(real.get('q9_bins',[]))==10 and all(shared.finite(v) for v in real['q9_bins']))
        if not valid:continue
        support.add((r['month'],r['userid']))
        if not shared.finite(r['arms'][arm]['mean']) or not shared.finite(r['arms'][arm]['iqr']):
            # This is a scalar engineering fallback, NOT a generated Q9 reply.
            r['arms'][arm]['mean']=real['previous_q9_mean'];fallbacks+=1
    fixed=summarize(rows,[arm],months,[1,2],support)
    return dict(status='posthoc_missing_support_diagnostic_only',new_api_calls=0,new_q9_fits=0,
        per_repeat_own_valid_support=separate,fixed_human_valid_roster_with_scalar_prior_fallback=fixed,
        fallback_slots=fallbacks,generated_replies_fabricated=0,original_targets_or_calls_changed=False,
        note='Primary complete-repeat support is unchanged. Separate-repeat supports differ. The fixed-roster option keeps every human-valid person and substitutes only a scalar prior when a model response/score is missing; it is a post-hoc deployment diagnostic, not an LLM reply or newly passed primary test.')


def run(source,evaluation,out):
    source,evaluation,out=[Path(p).resolve() for p in (source,evaluation,out)]
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output required')
    s=read_json(source/'summary.json');cases=read_json(evaluation/'cases_private.json')
    expected=s['source_sha256'][str((evaluation/'cases_private.json').relative_to(ROOT))]
    if sha(evaluation/'cases_private.json')!=expected:raise ValueError('Original scored cases changed')
    sensitivity=analyze(cases,'deepseek_v32',s['months'])
    s.update(support_sensitivity=sensitivity,readout_revision=2,
        preceding_readout_sha256=sha(source/'summary.json'),support_analysis_source_sha256=sha(__file__))
    out.mkdir();dump(out/'summary.json',s)
    return dict(primary=s['readout']['metrics'],fixed_roster=sensitivity['fixed_human_valid_roster_with_scalar_prior_fallback']['metrics'],
        fallback_slots=sensitivity['fallback_slots'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--evaluation',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(run(a.source,a.evaluation,a.out))
