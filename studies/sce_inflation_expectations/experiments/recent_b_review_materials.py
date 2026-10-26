"""Offline B review packet: input checks and A-only aggregate calibration.

No endpoint, credentials or paid runner is opened. Target-B values are not
parsed or scored; provenance checks may hash an archive without parsing it.
The old B answer archive and every frozen input remain unchanged.
"""
import argparse
import csv
from datetime import datetime
from pathlib import Path

import numpy as np

from .full_a_core_normal import ROOT,read,write,sha,checked,fresh
from ..evaluation.full_a_macro_calibration import FEATURES,features,fit_ridge,predict
from ..evaluation.aggregate_blend import fit_weight
from ..submission_tools.reproduce import no_network

ASSEMBLY=ROOT/'outputs/sce_recent_b_news_refresh_20261025_v3'
READINESS=ROOT/'outputs/sce_recent_b_news_refresh_readiness_20261025_v1/acceptance.json'
MACRO=ROOT/'outputs/sce_full_a_macro_calibration_20261026_v1'
FAIR=ROOT/'outputs/sce_dynamic_fair_benchmark_20261026_v1'
FAMILIES=('macro_without_sim','macro_plus_sim')


def require_past_labels(rows,cutoff):
    for row in rows:
        if row['month']>='202511' or row['truth_published_date']>=cutoff[:10]:
            raise ValueError('Only A labels public before the first B cutoff may fit parameters')
        if not np.isfinite([float(row[k]) for k in ('truth_pp','baseline_pp','before_model_pp','cpi_yoy_pp','cpi_change_pp')]).all():
            raise ValueError('Finite A-only aggregate inputs required')


def freeze_macro_parameters(rows,previous_fits,cutoff):
    require_past_labels(rows,cutoff)
    rows=[{**r,**{k:float(r[k]) for k in ('truth_pp','baseline_pp','before_model_pp','cpi_yoy_pp','cpi_change_pp')}} for r in rows]
    y=np.array([float(r['truth_pp'])-float(r['baseline_pp']) for r in rows]);ff=[features(r,'before_model_pp') for r in rows]
    fits={}
    for family in FAMILIES:
        original=previous_fits['Core_'+family];names=FEATURES[family];alpha=original['alpha']
        x=np.array([[f[n] for n in names] for f in ff])
        fits[family]=dict(**fit_ridge(x,y,alpha),features=names,training_n=len(rows),
             training_first=rows[0]['month'],training_last=rows[-1]['month'],
             regularization_selection='Prior registered early36/next12 of A; unchanged for B',
             original_early48_validation=original['validation'])
    early=[r for r in rows if r['month']<='202212']
    if len(early)!=48:raise ValueError('Existing early48 blend definition required')
    blends={loss:dict(simulation_weight=fit_weight([float(r['truth_pp']) for r in early],
        [float(r['baseline_pp']) for r in early],[float(r['before_model_pp']) for r in early],loss),
        training_months=['201901','202212'],training_n=48,loss=loss) for loss in ('mse','mae')}
    return dict(aggregate_simulation_source='A actual Core aggregates, without statistical Normal extension',
       as_of_before_first_B=cutoff,coefficient_update_within_B=False,blends=blends,fits=fits,
       max_training_label_publication=max(r['truth_published_date'] for r in rows),B_targets_used_for_fitting=False)


def macro_prediction(row,fit):
    required={'baseline_pp','cpi_yoy_pp','cpi_change_pp'}
    if 'sim_gap' in fit['features']:required.add('sim_pp')
    if not all(k in row and np.isfinite(float(row[k])) for k in required):
        raise ValueError('Missing finite prediction inputs')
    # An unused placeholder must not become a simulated prediction.
    item={**row,**{k:float(row[k]) for k in required},'sim_pp':float(row.get('sim_pp',0.))};f=features(item,'sim_pp')
    return float(row['baseline_pp'])+float(predict([[f[n] for n in fit['features']]],fit)[0])


def cpi_review(environment):
    args=environment['provider_args'];cutoff=args['targets'][0]['as_of']
    signals=sorted([s for s in args['signals_by_step']['0']
        if s['signal_id'].startswith('bls_cpi_u_all_items_yoy')
        and datetime.fromisoformat(s['published_at'])<=datetime.fromisoformat(cutoff)],
        key=lambda s:(s['reference_period'],s['published_at']),reverse=True)
    if len(signals)<2 or signals[0]['reference_period']==signals[1]['reference_period']:
        raise ValueError('Two distinct eligible CPI releases required')
    a,b=signals[:2]
    def index(m):return int(m[:4])*12+int(m[5:7])
    return dict(cpi_yoy_pp=float(a['value']),cpi_change_pp=float(a['value']-b['value']),
        cpi_reference=a['reference_period'],cpi_published_at=a['published_at'],
        previous_cpi_reference=b['reference_period'],cpi_reference_gap_months=index(a['reference_period'])-index(b['reference_period']))


def prepare(out):
    out=fresh(out)
    manifest=read(ASSEMBLY/'manifest.json');checked(ASSEMBLY,manifest['files_sha256']);checked(ROOT,manifest['source_sha256'])
    ready=read(READINESS);checked(ROOT,ready['extra_dependency_sha256'])
    if ready['input_manifest_sha256']!=sha(ASSEMBLY/'manifest.json') or ready['positions']!=5632:raise ValueError('B input readiness changed')
    s=read(ASSEMBLY/'summary.json');pre=ROOT/s['population_preflight'];prior=ROOT/s['prior_source']
    plans=read(pre/'monthly_input_plan.json');diagnostics={r['month']:r for r in read(prior/'monthly_prior_diagnostics.json')}
    expected=[f'{y:04}{m:02}' for y,m in [(2025,11),(2025,12),*[(2026,m) for m in range(1,10)]]]
    if [r['month'] for r in plans]!=expected:raise ValueError('Registered B11 scope required')
    for folder in (MACRO,FAIR):checked(folder,read(folder/'manifest.json')['files_sha256'])
    with (FAIR/'monthly_inputs_public.csv').open() as f:publications={r['month']:r['truth_published_date'] for r in csv.DictReader(f)}
    with (MACRO/'monthly_inputs_public.csv').open() as f:training=[dict(r,truth_published_date=publications[r['month']]) for r in csv.DictReader(f)]
    if len(training)!=82 or training[-1]['month']!='202510':raise ValueError('Full A82 training source required')
    params=freeze_macro_parameters(training,read(MACRO/'summary.json')['fits'],plans[0]['as_of'])
    old_weight=read(MACRO/'summary.json')['fits']['Core_blend_mse']['simulation_weight']
    if not np.isclose(params['blends']['mse']['simulation_weight'],old_weight,rtol=0,atol=1e-12):raise ValueError('Old main blend did not reproduce')
    write(out/'macro_parameters.json',params)
    monthly=[]
    for plan in plans:
        month=plan['month'];anchor=plan['last_public_national_anchor'];d=diagnostics[month]
        cp=cpi_review(read(ASSEMBLY/'prompts'/month/'environment.json'))
        if anchor['reference_period'].replace('-','')>=month or anchor['published_date']>=plan['as_of'][:10]:raise ValueError('Unavailable public prior')
        if abs(d['realized_draw']['q9']['median_pp']-anchor['value_pp'])>.05+1e-12:raise ValueError('Prior national median outside declared band')
        item=dict(month=month,as_of=plan['as_of'],source_wave=plan['old_population_reference_period'],
             source_age_months=plan['source_age_months'],sample_n=512,old_frame_n=plan['frame_n'],
             public_anchor_reference=anchor['reference_period'],public_anchor_pp=anchor['value_pp'],
             public_anchor_published_date=anchor['published_date'],
             realized_prior_q9_median_pp=d['realized_draw']['q9']['median_pp'],
             **cp)
        item['macro_without_sim_prediction_pp']=macro_prediction(dict(baseline_pp=anchor['value_pp'],**cp),params['fits']['macro_without_sim'])
        monthly.append(item)
    with (out/'monthly_inputs_review.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=monthly[0]);w.writeheader();w.writerows(monthly)
    protocol=dict(status='review_packet_prepared_no_dispatch_authorization',months=expected,n_per_month=512,
      planned_calls=5632,repeat_count=1,model='deepseek/deepseek-v3.2',route='OpenRouter -> SiliconFlow FP8',
      temperature=.5,json_mode=True,reasoning=False,max_output_tokens=1024,provider_fallback=False,
      news=s['news_selection'],as_of_rule='Keep registered common per-month cutoffs; November13 confirmed; no actual-person or future random cutoff',
      population='Existing release-lag-assumed source waves and 54-cell weighted 512 proxies; no current recent-person truth',
      prior='Existing joint donor Q8/Q9; public historical Q9 median +/-0.05pp; intact answers; no target calibration',
      current_B_Normal_expansion=False,normal_explanation='512 weighted LLM proxies represent the declared old source frame; current B actual N/margins unavailable; no claim of current survey-sized statistical expansion',
      continuous_person_belief_recursion=False,entry_exit_mechanism=False,
      primary_outputs=['raw_simulation','public_persistence','frozen_early48_MSE_convex_blend'],
      required_auxiliary_pair=['frozen_A82_SCE_CPI_without_sim','frozen_A82_SCE_CPI_plus_sim'],
      sensitivity_outputs=['early48_MAE_blend_weight_zero'],
      previous_observable_trigger_not_automatically_ported='Previous trigger/difference fits used EOM and CoreNormal; B uses common cutoff and unexpanded Core. Do not transfer coefficients or select the2021 winner.',
      coefficient_rule='No B outcome fitting or within-B coefficient updates; A82 macro refit uses fixed early48 alpha. Blend retains registered early48 weight.',
      compare_old_B='Recompute old and new raw/convex/dynamic summaries with identical frozen parameters, truth versions, rosters, weights and cutoffs',
      metrics=['national Q9 MAE primary','RMSE','signed bias','monthly absolute/signed error','win months'],
      descriptive_only=['Q8 simulated median','simulated cross-person IQR','profile group comparisons'],
      no_recent_micro_accuracy=['No observed W1 or personal accuracy without recent micro truth'],
      estimated_main_cost_usd=s['estimated_main_cost_usd'],proposed_main_plus_one_technical_repair_cap_usd=10.,
      scheduler='Reuse independent Terminal controller,32-call8-worker format gate,32 then64 main workers,16 then32 repair; bounded cooling and at most one technical repair; scope+budget approval required',
      new_api_calls=0,B_target_values_parsed_or_scored=False,paid_execution_package_frozen=False,
      pending_before_live=['Bind refreshed builder/readiness and these parameters into a NEW execution package; do not run the old completed B directory',
                           'Offline queue/evaluator replay with the new bindings, then exact-scope budget authorization and local Terminal launch'],
      limitations=['Already viewed old B outcomes; this is a retrospective mechanism comparison, not a new blind test',
                   'Nine-month micro availability is a rule assumption, not certified historical bytes',
                   'Text historical versions and LLM knowledge boundary remain uncertified',
                   'A personal-date simulation and B common-cutoff simulation differ; A-derived calibration may transfer imperfectly',
                   'CPI changes are differences between successive available releases; missing reference months are flagged, not silently treated as adjacent'])
    write(out/'protocol.json',protocol)
    write(out/'summary.json',dict(status=protocol['status'],positions=5632,official_core_units=11,
        input_manifest_sha256=sha(ASSEMBLY/'manifest.json'),months=monthly,macro_parameters=params,
        new_api_calls=0,B_target_values_parsed_or_scored=False,authorization_written=False,
        source_checked=True,normal_expansion=False))
    sources=[ASSEMBLY/'manifest.json',ASSEMBLY/'summary.json',READINESS,pre/'monthly_input_plan.json',
        prior/'monthly_prior_diagnostics.json',MACRO/'manifest.json',MACRO/'summary.json',MACRO/'monthly_inputs_public.csv',
        FAIR/'manifest.json',FAIR/'monthly_inputs_public.csv',Path(__file__),Path(__file__).parents[1]/'evaluation/full_a_macro_calibration.py']
    write(out/'manifest.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
       files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()}))
    print('Prepared B11 review;0 API; main blend',params['blends']['mse']['simulation_weight'])
    print('CPI gaps',[(r['month'],r['cpi_reference_gap_months']) for r in monthly if r['cpi_reference_gap_months']!=1])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    with no_network():prepare(a.out)


if __name__=='__main__':main()
