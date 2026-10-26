"""Separate-process national B evaluation; fixed A-trained parameters, no refit."""
from collections import defaultdict
import csv
import json
from pathlib import Path

from .frozen_batch import ROOT, read_json, dump, sha
from .state_continuity_execution import verify
from . import recent_b_evaluation as frozen
from .recent_b_review_materials import macro_prediction
from ..evaluation.recent_b_readout import validate_catalog, validate_combined
from ..evaluation.metrics import distribution_summary, headline_errors


def evaluate(folder):
    folder=Path(folder).resolve();p,_=verify(folder/'package')
    receipt=read_json(folder/'generation_receipt.json')
    if receipt['status']!='generation_and_one_repair_complete' or not receipt['actual_model_results']:
        raise ValueError('Actual complete main/repair generation required before evaluation')
    validate_combined(folder)
    catalog=ROOT/p['target_catalog_evaluation_only'];validate_catalog(catalog,p['months'])
    cachepath=ROOT/'outputs/sce_recent_b_readout_20261025_v2/scoring_cache_private.json'
    cache={}
    if cachepath.exists():
        expected=read_json(cachepath.parent/'manifest.json')['files_sha256'][cachepath.name]
        if sha(cachepath)!=expected:raise ValueError('Exact-vector scorer cache changed')
        cache={tuple(row['bins']):row['score'] for row in read_json(cachepath)}
    original=frozen._score_bins;oldcatalog=frozen.CATALOG
    def score(bins):
        key=tuple(bins)
        if key not in cache:cache[key]=original(list(key))
        return cache[key]
    frozen._score_bins=score;frozen.CATALOG=catalog
    try:
        result=frozen.evaluate(folder)
    finally:
        frozen._score_bins=original;frozen.CATALOG=oldcatalog
    out=folder/'evaluation';params=read_json(ROOT/p['parameter_source'])
    with (ROOT/p['public_macro_review']).open() as stream:
        public={r['month']:r for r in csv.DictReader(stream)}
    for row in result['monthly']:
        month=str(row['month']);r=public[month]
        predictors=dict(baseline_pp=row['anchor_pp'],sim_pp=row['sim_pp'],
                        cpi_yoy_pp=float(r['cpi_yoy_pp']),cpi_change_pp=float(r['cpi_change_pp']))
        row['macro_without_sim_pp']=macro_prediction(predictors,params['fits']['macro_without_sim'])
        row['macro_with_sim_pp']=macro_prediction(predictors,params['fits']['macro_plus_sim'])
        row['mae_trained_blend_pp']=row['anchor_pp']+params['blends']['mae']['simulation_weight']*(row['sim_pp']-row['anchor_pp'])
    truth=[r['truth_pp'] for r in result['monthly']]
    comparison={key:headline_errors([r[key] for r in result['monthly']],truth) for key in
        ('sim_pp','anchor_pp','frozen_combination_pp','mae_trained_blend_pp','macro_without_sim_pp','macro_with_sim_pp')}
    # Descriptive simulation heterogeneity only: recent micro truth is unavailable.
    pop=read_json(ROOT/p['population_preflight']/'selected_proxy_population_private.json')
    rosters={m:{r['persona']['agent_id']:r for r in rs} for m,rs in pop.items()}
    grouped=defaultdict(list)
    for line in (folder/'combined/positions_private.jsonl').read_text().splitlines():
        row=json.loads(line);m=row['month'];person=rosters[m][row['agent_id']]
        center=score(row['state_after']['fields']['q9']['value'])['mean']
        if center is None:
            initial=read_json(ROOT/p['input_templates']/m/'initial_states_private.json')
            center=score(initial[row['agent_id']]['fields']['q9']['value'])['mean']
        for dim in ('age_group','education_group','household_income_band','numeracy','employment_status','region','housing_tenure'):
            value=str(person['persona']['attributes'].get(dim) or 'missing')
            grouped[m,dim,value].append((center,person['analysis_weight']))
    groups=[]
    for (m,dim,value),rows in sorted(grouped.items()):
        desc=distribution_summary([r[0] for r in rows],[r[1] for r in rows])
        groups.append(dict(month=m,dimension=dim,value=value,n=len(rows),
                           supported=len(rows)>=20 and desc['ess']>=10,simulation_only=desc))
    dump(out/'fixed_model_comparison.json',dict(fits=params,metrics=comparison,monthly=result['monthly'],
        coefficient_refit=False,B_targets_used_for_parameter_fit=False))
    dump(out/'simulated_groups_descriptive_only.json',groups)
    dump(out/'scoring_cache_private.json',[dict(bins=list(k),score=v) for k,v in cache.items()])
    with (out/'monthly_comparison.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(result['monthly'][0]));writer.writeheader();writer.writerows(result['monthly'])
    html=out/'index.html'
    html.write_text(html.read_text().replace('</h1>','</h1><p>新版：前一年同月抽取作答日期，个人环境截止受原预测时点封顶；四档新闻＋CPI相关度。原始模拟、历史基线、简单组合和公平宏观模型均保留。</p>',1)+
        '<p><a href="fixed_model_comparison.json">固定参数组合及宏观模型对照</a> · <a href="monthly_comparison.csv">逐月完整比较</a> · '+
        '<a href="simulated_groups_descriptive_only.json">模拟人群差异（非真人拟合）</a></p>')
    dump(out/'manifest.json',dict(files_sha256={f.name:sha(f) for f in out.iterdir() if f.is_file()},new_api_calls=0,
        target_catalog_sha256=sha(catalog),parameter_source_sha256=sha(ROOT/p['parameter_source'])))
    print(json.dumps(dict(status='national_and_fixed_macro_evaluation_complete',metrics=comparison),ensure_ascii=False,indent=2),flush=True)
    return result
