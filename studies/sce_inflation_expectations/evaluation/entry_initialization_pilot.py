"""Isolated pilot truth and repeated-generation summaries using shared metrics."""
from copy import deepcopy
import json
from pathlib import Path
import shutil

from . import cognition as shared
from .metrics import headline_errors
from .monthly_reconstruction import install_score_cache
from .state_continuity import assemble_cases
from ..experiments.entry_initialization_pilot import ARM
from ..experiments.frozen_batch import ROOT, dump, read_json, sha
from ..experiments.state_continuity_execution import verify
from ..scoring.sce_q9_frozen import provenance

DEFAULT_TRUTH = ROOT/'outputs/sce_monthly_reconstruction_full_truth_20261022_v3'


def prepare_truth(package, out, source=DEFAULT_TRUTH):
    """Subset existing scored truth AFTER outcome-blind selection; never refit it."""
    package,out,source=(Path(p).resolve() for p in (package,out,source))
    p,m=verify(package)
    if p['mechanism']!='entry_initialization_pilot_v1' or out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh isolated entry-pilot truth required')
    selected=read_json(ROOT/p['preparation']/'selected_private.json')
    selection={(int(month),r['persona']['agent_id']):r for month,rows in selected.items() for r in rows}
    source_manifest=read_json(source/'manifest.json')
    if sha(source/'truth_private.json')!=source_manifest['truth_sha256']:
        raise ValueError('Source truth changed')
    rows=[]
    for original in read_json(source/'truth_private.json'):
        key=(original['month'],original['agent_id'])
        if key not in selection:continue
        item=selection[key];r=deepcopy(original)
        r.update(survey_weight=item['analysis_weight'],inclusion_probability=item['inclusion_probability'],
                 pilot_entry_cohort=item['survey_entry_status'])
        rows.append(r)
    if len(rows)!=len(selection) or len(selection)!=144:
        raise ValueError('Exact isolated fixed-roster truth required')
    cache=read_json(source/'cache_receipt.json')
    if cache['cache_sha256']!=sha(source/'scoring_cache_private.json') or cache['scorer']!=provenance():
        raise ValueError('Frozen score cache mismatch')
    out.mkdir(parents=True);dump(out/'truth_private.json',rows)
    for name in ('scoring_cache_private.json','cache_receipt.json'):shutil.copyfile(source/name,out/name)
    dump(out/'manifest.json',{'protocol_sha256':m['protocol_sha256'],'truth_sha256':sha(out/'truth_private.json'),
         'scope':'Evaluation only, never opened by selector/live executor', 'person_months':len(rows),
         'source_sha256':{str((source/name).relative_to(ROOT)):sha(source/name) for name in
                          ('manifest.json','truth_private.json','scoring_cache_private.json')},
         'evaluation_code_sha256':sha(__file__),'new_api_calls':0})
    return {'person_months':len(rows),'new_api_calls':0,'scoring_cache_reused':True}


def summarize(cases, months, repeats, arms):
    supports={k:shared._common_person_months(cases,arms,repeats,k) for k in ('q8','q9')}
    result={a:shared._summarize_arm(cases,a,months,repeats,supports['q9'],supports['q8']) for a in arms}
    for r in result.values():
        r['auxiliary_survey_weighted']['weight_definition']='raw survey weight / first-phase pi / conditional pilot pi'
        for side in (r,r['auxiliary_survey_weighted']):
            biases=[c['q9_center_bias_pp'] for c in side['q9']['cells'] if shared.finite(c['q9_center_bias_pp'])]
            side['q9']['center_headline_errors']=headline_errors(biases,[0.]*len(biases)) if biases else None
    return {'q9_person_months':len(supports['q9']),'q8_person_months':len(supports['q8']),'arms':result}


def evaluate(package,calls,truth,out):
    package,calls,truth,out=(Path(x).resolve() for x in (package,calls,truth,out));p,m=verify(package)
    if p['mechanism']!='entry_initialization_pilot_v1' or out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh entry-pilot evaluation required')
    receipt=read_json(calls/'receipt.json');cm=read_json(calls/'manifest.json');tm=read_json(truth/'manifest.json')
    if not receipt.get('actual_model_results') or receipt['status']!='completed' or receipt['attempts']!=p['planned_calls']:
        raise ValueError('Complete actual-model ledger required; never score fixtures as results')
    if any(r['protocol_sha256']!=m['protocol_sha256'] for r in (receipt,cm,tm)):
        raise ValueError('Mixed package provenance')
    for name,digest in cm['files_sha256'].items():
        if sha(calls/name)!=digest:raise ValueError('Call ledger changed')
    if sha(truth/'truth_private.json')!=tm['truth_sha256']:raise ValueError('Truth changed')
    cr=read_json(truth/'cache_receipt.json')
    if cr['cache_sha256']!=sha(truth/'scoring_cache_private.json') or cr['scorer']!=provenance():
        raise ValueError('Cache changed')
    install_score_cache({tuple(r['bins']):r['score'] for r in read_json(truth/'scoring_cache_private.json')})
    nodes=read_json(ROOT/p['preparation']/'state_dependencies_private.json')
    positions=[json.loads(line) for line in (calls/'positions_private.jsonl').read_text().splitlines()]
    originals,operational,quality=assemble_cases(nodes,positions,read_json(truth/'truth_private.json'))
    valid=lambda r:shared.finite(r['survey_weight']) and r['survey_weight']>0
    weighted=[r for r in operational if valid(r)];actual=[r for r in originals if valid(r)]
    months=[int(v) for v in p['months']];repeats=p['generation_repeats']
    arms=[ARM,'monthly_past_reference']
    def view(rows,ms=months,reps=repeats):return summarize(rows,ms,reps,arms)
    groups={label:{
        'fixed_roster':view([r for r in weighted if r['survey_entry_status']==label]),
        'usable_outputs':view([r for r in actual if r['survey_entry_status']==label]),
        'by_month':{str(month):view([r for r in weighted if r['month']==month and r['survey_entry_status']==label],[month])
                    for month in months},
        'by_repeat':{str(rep):view([r for r in weighted if r['repeat']==rep and r['survey_entry_status']==label],months,[rep])
                     for rep in repeats}}
        for label in ('entrant','returning')}
    result={'status':'completed','selected_person_months':len({(r['month'],r['agent_id']) for r in operational}),
            'quality':quality,'groups':groups,'receipt':receipt,'scorer':provenance(),
            'missing_weight_person_months':len({(r['month'],r['agent_id']) for r in operational if not valid(r)}),
            'new_api_calls':0,'limits':[
                'Entrant and returner groups differ observationally; this is not an initialization treatment effect.',
                'No nationwide 50/50 aggregate; two repeats are not twice as many respondents.',
                'Entrant baseline retains an assigned synthetic state, not that persons true previous answer.',
                'No actual entrant delta or synthetic matched-person accuracy claim; distribution metrics prioritized.',
                'Three seen months, 24 per group, one donor/news assignment; descriptive pilot only.',
                'Normal statistical expansion is not included in this trial.']}
    out.mkdir(parents=True);dump(out/'summary.json',result)
    dump(out/'cases_private.json',operational);dump(out/'raw_output_cases_private.json',originals)
    return {'status':'completed','person_months':result['selected_person_months'],'new_api_calls':0}
