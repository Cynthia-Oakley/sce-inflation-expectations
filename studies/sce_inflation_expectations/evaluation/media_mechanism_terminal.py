"""Offline scoring of exact-message V3 ledgers, reusing frozen SCE metrics.

Targets and links are opened only here, after generation, in a separate process.
Failures remain missing, never replaced by a donor or a target response.
"""
from collections import Counter
from copy import deepcopy
from functools import lru_cache
import hashlib
from pathlib import Path

from ..experiments.frozen_batch import dump, read_json, sha
from ..experiments import frozen_message_queue as queue
from ..experiments.media_mechanism_terminal import checked, slots_for
from ..q9_normalization import response_view, response_point
from . import cognition as shared
from .media_mechanism_v3 import compare_with_a82


@lru_cache(maxsize=None)
def score(bins):
    return shared._score_bins(list(bins))


def empty():
    return dict(mean=None,iqr=None,zero_deflation=None,q9_bins=[],point=None,validation_status='invalid')


def model_action(row):
    action = empty()
    if not row or row.get('error') or row.get('finish_reason') != 'stop':
        return action
    raw = row.get('raw_response_text','')
    if row.get('raw_response_sha256') != hashlib.sha256(raw.encode()).hexdigest():
        raise ValueError('Raw answer hash changed')
    action['point'] = response_point(raw)
    try:
        view = response_view(raw)
    except (ValueError,TypeError,KeyError):
        return action
    return dict(action, **score(tuple(view['bins'])), q9_bins=view['bins'],
                validation_status='valid', normalization_applied=view['applied'])


def previous_action(real):
    action = empty()
    action['point'] = real.get('previous_q8_point')
    bins, mean = real.get('previous_q9_bins'),real.get('previous_q9_mean')
    if bins is None or len(bins) != 10 or not shared.finite(mean):
        return action
    scored = score(tuple(bins))
    return {**action, **scored, 'mean':mean, 'q9_bins':bins, 'validation_status':'valid'}


def evaluate(folder,out):
    folder,out = Path(folder).resolve(),Path(out).resolve()
    c,p = checked(folder)
    if out.exists():
        raise ValueError('Fresh evaluation directory required')
    package = Path(c['package'])
    slots = slots_for(package,read_json(package/'manifest.json'),p)
    intents,replies = queue.archive(folder)
    if len(intents) != p['planned_calls']:
        raise ValueError('Generation scope not yet fully attempted; preserve partial data')
    keys = {s['key']:s for s in slots}
    for r in intents:
        if r['key'] not in keys or r['prompt_sha256'] != keys[r['key']]['prompt_sha256']:
            raise ValueError('Input ledger differs from frozen scope')
    for row in replies:
        if row.get('actual_model_results') is not True:
            raise ValueError('Engineering replies are not research observations')
        if row.get('error') is None and (row.get('returned_model') != p['model']
                or row.get('returned_provider') != p['expected_provider']):
            raise ValueError('Locked model/provider differs')
    reply_by_key = {r['key']:r for r in replies}
    truth = {(r['month'],r['agent_id'],r['repeat']):r['real']
             for r in read_json(package/'evaluation_truth/cases_private.json')}
    cases = []
    counts = {arm:Counter() for arm in p['arms']}
    for link in read_json(package/'evaluation_links_private.json'):
        for repeat in p['generation_repeats']:
            month,aid = link['month'],link['agent_id']
            real = truth[month,aid,repeat]
            arms = {}
            for arm in p['arms']:
                key = f'{month}|{arm}|{repeat}|{aid}'
                arms[arm] = model_action(reply_by_key.get(key))
                counts[arm][arms[arm]['validation_status']] += 1
            arms['copy_previous'] = previous_action(real)
            cases.append(dict(link,repeat=repeat,survey_weight=link['design_survey_weight'],real=real,arms=arms))
    arms = list(p['arms'])
    support9 = shared._common_person_months(cases,arms,p['generation_repeats'],'q9')
    support8 = shared._common_person_months(cases,arms,p['generation_repeats'],'q8')
    def summarize(arm,s9,s8):
        value = shared._summarize_arm(cases,arm,p['months'],p['generation_repeats'],s9,s8)
        value['auxiliary_survey_weighted']['weight_definition'] = (
            'Frozen A82 design/analysis weights on the selected 96-person support; '
            'not a newly calibrated national population weight.')
        return value
    summaries = {arm:summarize(arm,support9,support8) for arm in arms}
    paired9 = shared._common_person_months(cases,[*arms,'copy_previous'],p['generation_repeats'],'q9')
    paired8 = shared._common_person_months(cases,[*arms,'copy_previous'],p['generation_repeats'],'q8')
    same_support = {arm:summarize(arm,paired9,paired8) for arm in [*arms,'copy_previous']}
    result = dict(status='completed_media_v3_terminal_evaluation',new_api_calls=0,protocol=p,
        arms=summaries,coverage={a:dict(v) for a,v in counts.items()},
        common_q9_person_months=len(support9),common_q8_person_months=len(support8),
        persistence_same_support={'q9_person_months':len(paired9),'q8_person_months':len(paired8),'arms':same_support},
        execution=queue.account(intents,replies),scorer_cache_distinct_vectors=score.cache_info().currsize,
        notes=['Both repeats are model randomness for the same people, not extra residents.',
               'Exploratory previously inspected months; no time-out-of-sample claim.',
               'No Normal, synthetic replacement of failed answers, or error-based re-query.',
               'Q9 proportional normalization is derived only; raw replies remain untouched.',
               'Persistence comparisons use identical people, weights, months and repeat support.'])
    out.mkdir(parents=True)
    dump(out/'summary.json',result)
    dump(out/'cases_private.json',cases)
    compare_with_a82(out,package,out/'comparison')
    rows = ['# 新闻机制 V3：执行后自动摘要','',
            '探索性七期对照；下列指标均为同支持设计权重，月份和遍数等权。',
            '照抄上期只使用本人真实上期记录，缺失者不填补；Q8与Q9分别评价。','']
    for arm,value in same_support.items():
        m = value['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells']
        def number(key):
            x=m[key]
            return '缺失' if x is None else f'{x:.3f}'
        rows.append(f"- **{arm}**：Q9中心MAE {number('q9_center_mae_pp')}pp，"
                    f"bias {number('q9_center_bias_pp')}pp，W1 {number('cross_section_w1_pp')}pp，"
                    f"跨人IQR {number('cross_person_iqr_pp')}pp。")
    rows += ['',f'共同Q9支持：{len(paired9)}个人月；Q8支持：{len(paired8)}个人月。',
             '逐月/逐遍与Q8结果见 summary.json；A82单遍参照和分层见 comparison/summary.json。',
             '不得把同支持中心误差直接称为完整全国调查误差。']
    (out/'RESULTS.md').write_text('\n'.join(rows)+'\n')
    dump(out/'manifest.json',dict(new_api_calls=0,files_sha256={name:sha(out/name) for name in
         ('summary.json','cases_private.json','comparison/summary.json','RESULTS.md')}))
    return dict(status=result['status'],out=str(out),new_api_calls=0,
                common_q9_person_months=len(support9),persistence_baseline_included=True)
