"""Complete cached evaluation after a missing-prior-Q8 JSON export failure.

All API replies and original Q8/Q9 scores remain unchanged. A prior missing Q8
cannot be a carry-forward baseline, even when today's model Q8 is valid.
"""
from copy import deepcopy
import math
from pathlib import Path

from . import cognition as shared
from .news_matching_readout import operational_view
from ..experiments.frozen_batch import ROOT,read_json,dump,sha
from scripts.evaluate_sce_news_matching import fixed_roster


def finish_operational(cases,protocol):
    result=fixed_roster(cases,protocol)
    rows=operational_view(cases,protocol['arms'])
    for row in rows:
        r=row['real'];row['arms']['carry']=dict(mean=r['previous_q9_mean'],iqr=r['previous_q9_iqr'],
            zero_deflation=r['previous_q9_zero_deflation'],q9_bins=r['previous_q9_bins'],point=r['previous_q8_point'])
    support8=shared._common_person_months(rows,[*protocol['arms'],'carry'],[1,2],'q8')
    support9=shared._common_person_months(rows,protocol['arms'],[1,2],'q9')
    results={a:shared._summarize_arm(rows,a,protocol['months'],[1,2],support9,support8)['auxiliary_survey_weighted']['q8']
        for a in [*protocol['arms'],'carry']}
    result['same_support_carry']['q8']=results.pop('carry')
    result.update(q8_baseline_supported_models=results,q8_baseline_comparable_person_months=len(support8),
        q8_support_note='Current valid model Q8 is preserved independently of Q9. Carry Q8 and corresponding model comparisons additionally require a valid previous Q8; no invented prior.')
    def check(value):
        if isinstance(value,dict):
            for v in value.values():check(v)
        elif isinstance(value,list):
            for v in value:check(v)
        elif isinstance(value,float) and not math.isfinite(value):raise ValueError('Nonfinite metric must be diagnosed, not hidden')
    check(result)
    return result


def finalize(source,out):
    source,out=Path(source).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh derived evaluation folder required')
    s=read_json(source/'summary.json');cases=read_json(source/'cases_private.json')
    if s['protocol']['mechanism']!='v32_news_matching':raise ValueError('Registered cached news evaluation required')
    operational=finish_operational(cases,s['protocol'])
    result=deepcopy(s)
    result.update(fixed_roster_operational=operational,
        primary_reporting='Operational fixed-roster and paired available-output results jointly; neither alone proves a mechanism.',
        assignment_seed_limitation='One allocation seed, two model repeats; no assignment-robustness claim.',
        export_correction='Original generic Q8/Q9 scores unchanged. Missing past Q8 caused carry-baseline NaN; use matched prior-valid Q8 support, preserving all valid current Q8 separately. Zero API/refits.',
        export_source_sha256={str((source/name).relative_to(ROOT)):sha(source/name) for name in ('summary.json','cases_private.json','q9_normalization_private.json')})
    out.mkdir(parents=True)
    for name in ('cases_private.json','q9_normalization_private.json'):(out/name).write_bytes((source/name).read_bytes())
    dump(out/'fixed_roster_operational.json',operational);dump(out/'summary.json',result)
    return dict(status='completed_cached_export_repair',new_api_calls=0,new_q9_fits=0,
        q9_fixed_roster_person_months=operational['common_q9_person_months'],
        q8_current_model_person_months=operational['common_q8_person_months'],
        q8_carry_comparable_person_months=operational['q8_baseline_comparable_person_months'])
