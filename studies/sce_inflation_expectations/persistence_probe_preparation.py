"""Offline paired input prototypes. No provider registration or paid execution."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ARMS = ('unassigned', 'easing_prior', 'persistent_prior')
INTRO = 'Your prior impression before reading the current information is that unusually rapid increases in everyday prices '
END = (' This is your starting impression, not a known future outcome, and the information below may change your view.'
       ' A slowing rate of price increases does not by itself mean prices return to their earlier level.')
PRIORS = {
    'easing_prior': INTRO + 'tend to ease within the coming year.' + END,
    'persistent_prior': INTRO + 'tend to persist through the coming year.' + END,
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def message_sha(messages):
    return hashlib.sha256(json.dumps(messages,ensure_ascii=False).encode()).hexdigest()


def common_correction(messages):
    corrected = deepcopy(messages)
    if len(corrected) != 1 or corrected[0]['role'] != 'user':
        raise ValueError('unreviewed message layout')
    text = corrected[0]['content']
    # This is the BLS shelter index, including owners' equivalent rent. No numbers change.
    text = text.replace('rent and shelter', 'shelter (a national housing-cost index, not your own rent)')
    text = text.replace('Rent/shelter prices (12-month %)', 'Shelter price index (12-month %)')
    corrected[0]['content'] = text
    return corrected


def with_prior(corrected, arm):
    if arm not in ARMS:
        raise ValueError('unknown condition')
    result = deepcopy(corrected)
    if arm == 'unassigned':
        return result
    marker = 'Recent official statistics:'
    if result[0]['content'].count(marker) != 1:
        raise ValueError('missing insertion point')
    result[0]['content'] = result[0]['content'].replace(marker, PRIORS[arm]+'\n\n'+marker, 1)
    return result


def prepare(root, source, diagnostic, out):
    root, source, diagnostic, out = [Path(p).resolve() for p in (root,source,diagnostic,out)]
    if out.exists() or not out.is_relative_to(root/'outputs'):
        raise ValueError('new ignored local output required')
    plan = json.loads((source/'trial_manifest.json').read_text())
    audit = json.loads((diagnostic/'summary.json').read_text())
    if audit['run_coverage']['counts'].get('202203',0) or audit['run_coverage']['counts'].get('202303',0):
        raise ValueError('proposed transfer month found in prior local run inventory')
    rows, inputs = [], {}
    for month in plan['months']:
        path = source/month/'preview_matched.json'
        key = f'{month}/preview_matched.json'
        if sha(path) != plan['prepared_file_sha256'][key]:
            raise ValueError('source preview differs from frozen inputs')
        inputs[str(path.relative_to(root))] = sha(path)
        for old in json.loads(path.read_text()):
            baseline = common_correction(old['messages'])
            for arm in ARMS:
                messages = with_prior(baseline,arm)
                recovered = deepcopy(messages)
                if arm in PRIORS:
                    recovered[0]['content'] = recovered[0]['content'].replace(PRIORS[arm]+'\n\n','',1)
                if recovered != baseline:
                    raise ValueError('treatment changed another input')
                rows.append({'month':month,'local_alias':old['agent_id'],'arm':arm,'messages':messages,
                             'messages_sha256':message_sha(messages),
                             'common_baseline_sha256':message_sha(baseline)})
    reg = {'status':'offline_prototype_and_provisional_transfer_registration_not_runnable',
           'created_at_utc':datetime.now(timezone.utc).isoformat(), 'new_api_calls':0, 'new_cost_usd':0,
           'mechanism':'prior belief about persistence of price increases; synthetic scenarios, no population prevalence assigned',
           'primary_contrast':'persistent_prior minus easing_prior within the same person, month, news draw and generation replicate',
           'additional_reference':'unassigned (no extra prior); do not attribute its length/extra-instruction difference solely to belief',
           'preview_months_only':plan['months'],'preview_people_per_month':48,'preview_message_count':len(rows),
           'preview_usage':'local structural inspection only; no new runs on May/June and no fit-based wording tuning',
           'prospective_transfer_months':['202203','202303'],
           'month_selection_rule':'March in two successive years, fixed calendar comparison outside previously recorded 2021 simulations; not selected by candidate fit',
           'holdout_limits':'Historical real outcomes, scorer, baselines and population statistics have already been studied. These are new to this mechanism, not never-seen data or proof of model-training exclusion.',
           'research_line':'A conditional mechanism probe; no B forecasting claim',
           'candidate_sample_size_per_month':24,
           'sampling_rule':'one fixed answer-blind draw from a rebuilt monthly Core, reused in all arms/seeds; diagnostics only',
           'population_seed':104729,'news_draw_seeds':[104729,130363],
           'generation_replicates':[0,1], 'api_seed_guarantee':False,
           'news_rule':{'uniform_fraction':.5,'weighted_fraction':.5,'affinity_boost':2,'common':3,'personal':5,'different_time_repeated_events':'retain'},
           'planned_answer_count_if_all_gates_pass':24*2*3*2*2,
           'model_candidate':'deepseek-flash official API; alias and returned model recorded, availability recheck before authorization',
           'temperature':.5,'retry_max':0,'same_questionnaire_in_all_arms':True,
           'common_future_correction':'BLS shelter label; no change to old runs',
           'paid_authorization':'not requested or granted for this future scope',
           'budget_usd':None,'as_of_by_month':'pending existing date-contract/E-release audit; not silently chosen here',
           'population_prevalence':'unknown; do not pool counterfactual arms as a synthetic national population',
           'success_gate':'paired direction repeats in both months and both news draws, magnitude exceeds same-condition generation variation; this is a sensitivity gate, not realism or improved SCE fit',
           'metrics':['paired Q8 and Q9 mean change','within-condition generation variation','raw zero/negative mass and positive-bin count','point-minus-density mean','failure rate'],
           'stop_rule':'if prior response is unstable or only wording compliance, stop assigning this attribute; do not tune prevalence to SCE targets',
           'prerequisites':['fresh months P/E and as_of audit','complete candidate news labels/new labelling cost if needed','48 people/months input isolation and paired invariants','offline engine/collector/cost checks','provider quote and explicit data/budget authorization'],
           'source_sha256':{**inputs,str(diagnostic.relative_to(root)/'summary.json'):sha(diagnostic/'summary.json'),
                            str(Path(__file__).relative_to(root)):sha(__file__)}}
    out.mkdir(parents=True)
    (out/'previews_private.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
    reg['preview_sha256']=sha(out/'previews_private.json')
    (out/'registration.json').write_text(json.dumps(reg,ensure_ascii=False,indent=2)+'\n')
    (out/'prior_texts.json').write_text(json.dumps(PRIORS,indent=2)+'\n')
    return reg
