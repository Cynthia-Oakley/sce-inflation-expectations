"""Entry shares and an evaluation-only perfect-newcomer replacement diagnostic.

No new model answers, outcome-based sampling, calibration or Q9 fits occur.
The small mixed cohort is not a reconstructed national headline.
"""
from copy import deepcopy
from pathlib import Path
import json
import numpy as np

from . import cognition as shared
from .entry_initialization_pilot import summarize
from .metrics import quantile
from ..experiments.frozen_batch import ROOT,read_json,dump,sha

ARM='monthly_reconstruction'
BASE='monthly_past_reference'
IDEAL='evaluation_only_actual_newcomers'
RETAIN='retain_new_start_returner_simulation'


def analyze(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored analysis folder required')
    material=ROOT/'outputs/sce_fullperiod_materialized_20261022_v2'
    protocol=ROOT/'outputs/sce_monthly_reconstruction_full_execution_20261022_v1/protocol.json'
    sources={str(protocol.relative_to(ROOT)):sha(protocol)};shares=[]
    for month in read_json(protocol)['months']:
        state_file=material/month/'population_state_private.json';weight_file=material/month/'sampling_private.json'
        states=read_json(state_file)['persons'];raw=read_json(weight_file)['persons']
        weights={r['agent_id']:r['survey_weight'] for r in raw}
        valid=[r for r in states if shared.finite(weights[r['agent_id']]) and weights[r['agent_id']]>0]
        total=sum(weights[r['agent_id']] for r in valid)
        mass=sum(weights[r['agent_id']] for r in valid if r['survey_entry_status']=='entrant')
        shares.append({'month':month,'frame_n':len(states),
                       'entrant_n':sum(r['survey_entry_status']=='entrant' for r in states),
                       'entrant_count_share':sum(r['survey_entry_status']=='entrant' for r in states)/len(states),
                       'entrant_survey_weight_share':mass/total,'missing_weight_n':len(states)-len(valid)})
        for f in (state_file,weight_file):sources[str(f.relative_to(ROOT))]=sha(f)
    cases_file=ROOT/'outputs/sce_entry_pilot_evaluation_20261022_v1/cases_private.json'
    sources[str(cases_file.relative_to(ROOT))]=sha(cases_file)
    cases=[r for r in read_json(cases_file) if shared.finite(r['survey_weight']) and r['survey_weight']>0]
    for r in cases:
        real=r['real']
        r['arms'][IDEAL]=(deepcopy(r['arms'][ARM]) if r['survey_entry_status']!='entrant' else
            {'mean':real['q9_mean'],'iqr':real['q9_iqr'],'zero_deflation':real['q9_zero_deflation'],
             'q9_bins':real['q9_bins'],'point':real['q8_point']})
        r['arms'][RETAIN]=deepcopy(r['arms'][BASE] if r['survey_entry_status']=='entrant' else r['arms'][ARM])
    months=sorted({r['month'] for r in cases});arms=[ARM,BASE,IDEAL,RETAIN];repeats=[1,2]
    summary=summarize(cases,months,repeats,arms)
    returning=[r for r in cases if r['survey_entry_status']=='returning']
    returning_summary=summarize(returning,months,repeats,[ARM,BASE])
    support=shared._common_person_months(cases,arms,repeats,'q9')
    cells=[]
    for month in months:
        for repeat in repeats:
            rows=shared._cell_rows(cases,month,repeat,support)
            new=[r for r in rows if r['survey_entry_status']=='entrant'];old=[r for r in rows if r['survey_entry_status']=='returning']
            p=sum(r['survey_weight'] for r in new)/sum(r['survey_weight'] for r in rows)
            weights=[r['survey_weight'] for r in rows]
            actual=quantile([r['real']['q9_mean'] for r in rows],weights,.5)
            old_actual=quantile([r['real']['q9_mean'] for r in old],[r['survey_weight'] for r in old],.5)
            centers={a:quantile([r['arms'][a]['mean'] for r in rows],weights,.5) for a in arms}
            errors={a:abs(v-actual) for a,v in centers.items()}
            low=(.5-p)/(1-p);high=.5/(1-p)
            returner_bounds=[quantile([r['arms'][ARM]['mean'] for r in old],
                                     [r['survey_weight'] for r in old],q) for q in (low,high)]
            cells.append({'month':month,'repeat':repeat,'entrant_n':len(new),'returner_n':len(old),
                          'entrant_design_weight_share':p,'actual_mixed_center_pct':actual,
                          'actual_returner_center_pct':old_actual,
                          'centers_pct':centers,'errors_pp':errors,
                          'ideal_newcomer_replacement_center_change_pp':centers[IDEAL]-centers[ARM],
                          'potential_mae_reduction_pp':errors[ARM]-errors[IDEAL],
                          'arbitrary_newcomer_median_returner_quantile_bounds':[low,high],
                          'arbitrary_newcomer_median_bounds_pp':returner_bounds})
    weighted=[r['entrant_survey_weight_share'] for r in shares]
    metric=lambda view: view['arms'][ARM]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells']['q9_center_mae_pp']
    contrast={'returner_only_center_mae_pp':metric(returning_summary),'mixed_center_mae_pp':metric(summary),
              'mae_increase_pp':metric(summary)-metric(returning_summary),
              'all_six_true_centers_unchanged':all(abs(c['actual_mixed_center_pct']-c['actual_returner_center_pct'])<1e-10 for c in cells),
              'by_month':{str(month):{
                  'returner_only_center_mae_pp':metric(summarize([r for r in returning if r['month']==month],[month],repeats,[ARM,BASE])),
                  'mixed_center_mae_pp':float(np.mean([c['errors_pp'][ARM] for c in cells if c['month']==month]))}
                  for month in months}}
    sources[str(Path(__file__).relative_to(ROOT))]=sha(__file__)
    result={'status':'completed_offline_sensitivity','new_api_calls':0,'source_sha256':sources,
            'full_frame_shares':shares,'full_frame_summary':{'months':len(shares),
                'equal_month_mean_entrant_weight_share':float(np.mean(weighted)),
                'min':min(shares,key=lambda r:r['entrant_survey_weight_share']),
                'max':max(shares,key=lambda r:r['entrant_survey_weight_share'])},
            'mixed_pilot_summary':summary,'mixed_pilot_cells':cells,
            'returner_only_summary':returning_summary,'returner_vs_mixed':contrast,
            'ideal_replacement_mae_difference_pp':float(np.mean([c['potential_mae_reduction_pp'] for c in cells])),
            'limits':['Actual population share uses all positive raw survey weights, not just Q9-valid respondents.',
                      'Mixed pilot includes newcomers and eligible adjacent returners only; excludes gaps and is not national.',
                      'Existing design weights correct the 24/24 allocation; raw 50/50 count is not population composition.',
                      'Ideal replacement uses current truths ONLY in evaluation; never a feasible forecasting method.',
                      'Retaining newcomer starting states is a statistical carryover baseline, not a fitted Bayesian posterior.',
                      'Replacement error differences can change sign through cancellation; not a causal attribution.',
                      'Three seen months, one assignment seed and small cohort; cannot guarantee final MAE impact.']}
    out.mkdir(parents=True);dump(out/'summary.json',result)
    print(json.dumps({'population':result['full_frame_summary'],
        'pilot_full_frame_shares':[r for r in shares if int(r['month']) in months],
        'mixed_center_mae_pp':{a:v['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells']['q9_center_mae_pp']
                               for a,v in summary['arms'].items()},
        'ideal_replacement_potential_reduction_pp':result['ideal_replacement_mae_difference_pp'],
        'returner_vs_mixed':contrast,
        'cells':cells},ensure_ascii=False))
    return result
