"""Targeted, offline 2021 input/response diagnosis and aggregate blend fits.

Never changes the frozen run, its scorer, or the registered fit/evaluation split.
The all-period and later-period fits are explicitly retrospective descriptions.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np

from .aggregate_blend import estimate, evaluate
from .metrics import quantile
from ..state_continuity_runtime import render_messages
from ..procurement_price_views import fact_line

ROOT = Path(__file__).resolve().parents[3]
ANALYSIS = ROOT / 'outputs/sce_fullperiod_analysis_20261024_v1/summary.json'
RUN = ROOT / 'outputs/sce_monthly_main_six_repair_20261024_v1'
ASSEMBLY = ROOT / 'outputs/sce_monthly_fine_full_assembly_20261023_v3/prompts'
DELIVERY = ROOT / 'outputs/sce_fullperiod_materialized_20261022_v2'
RAW = ROOT / 'outputs/sce_monthly_main_resilient_20261024_v1/combined/calls_private.jsonl'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def blend_block(rows):
    result = {'months': len(rows), 'persistence': evaluate(rows, 0),
              'pure_simulation': evaluate(rows, 1), 'posthoc_fit': {}}
    for loss in ('mae', 'mse'):
        weight = estimate(rows, loss)
        result['posthoc_fit'][loss] = dict(simulation_weight=weight,
            history_weight=1-weight, metrics=evaluate(rows, weight))
    return result


def prior_diagnostic(cases):
    grouped = defaultdict(list)
    for r in cases:
        if not 202101 <= r['month'] <= 202112:
            continue
        p, y, m, w = (r['real']['previous_q9_mean'], r['real']['q9_mean'],
                     r['arms']['monthly_reconstruction']['mean'], r['survey_weight'])
        if all(isinstance(v, (int, float)) and np.isfinite(v) for v in (p, y, m, w)) and w > 0:
            grouped[r['month']].append((p, y, m, w))
    rows = []
    for month, values in sorted(grouped.items()):
        a = np.array(values); p, y, m, w = a.T; dy, dm = y-p, m-p
        row = dict(month=month, n=len(a),
            real_median_pp=quantile(y,w,.5), model_median_pp=quantile(m,w,.5),
            prior_median_pp=quantile(p,w,.5),
            real_mean_change_pp=float(np.average(dy,weights=w)),
            model_mean_change_pp=float(np.average(dm,weights=w)),
            real_median_change_pp=quantile(dy,w,.5),
            model_median_change_pp=quantile(dm,w,.5),
            model_down_share=float(np.average(dm < -1e-8,weights=w)),
            real_up_share=float(np.average(dy > 1e-8,weights=w)),
            real_up_model_down_share=float(np.average((dy > 1e-8)&(dm < -1e-8),weights=w)),
            model_center_bias_pp=quantile(m,w,.5)-quantile(y,w,.5))
        high = p > 4
        if high.any():
            row['prior_above_4'] = dict(n=int(high.sum()),
                real_mean_change_pp=float(np.average(dy[high],weights=w[high])),
                model_mean_change_pp=float(np.average(dm[high],weights=w[high])))
        rows.append(row)
    keys = [k for k,v in rows[0].items() if isinstance(v,float)]
    return dict(person_months=sum(r['n'] for r in rows), monthly=rows,
        equal_month_means={k:float(np.mean([r[k] for r in rows])) for k in keys},
        limits='Actual adjacent returners with valid current/model/previous Q9 and positive weights; descriptive, not a causal update equation.')


def run(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Use a fresh output directory under outputs')
    summary = read(ANALYSIS); cases_path = RUN/'evaluation/cases_private.json'
    cases = read(cases_path); national = summary['official_national']['monthly']
    prepared = {}; audit = []; source_files = {ANALYSIS,cases_path}
    failures = []; declared = Counter(); total_news = 0
    for month in range(202101,202113):
        folder=ASSEMBLY/str(month); materialized=DELIVERY/str(month)
        names = ['templates_private.json','initial_states_private.json','timing_context_private.json']
        templates, states, contexts = [read(folder/n) for n in names]
        source_files.update(folder/n for n in names)
        env_path, food_path = materialized/'environment.json', materialized/'food_categories.json'
        source_files.update([env_path,food_path]); env, foods=read(env_path),read(food_path)
        food = foods['food_at_home']; signals=env['provider_args']['signals_by_step']['0']
        latest=[s for s in signals if s.get('role')=='latest_release']
        def signal(part):
            return next(s for s in latest if s['signal_id'].startswith(part))
        all_cpi=signal('bls_cpi_u_all_items_yoy'); energy=signal('bls_cpi_energy_yoy')
        food_signal=signal('bls_cpi_food_at_home_yoy')
        assert food_signal['value']==food['yoy_nsa_percent']
        counts=Counter(); brief_dates=Counter(); prior_sources=Counter(); news_excluded=0
        for person, template in templates.items():
            state, context = states[person], contexts[person]
            cutoff=datetime.fromisoformat(context['as_of'])
            for fact in foods.values():
                if datetime.fromisoformat(fact['published_at'])>cutoff:
                    failures.append([month,'future_food'])
            if datetime.fromisoformat(context['policy_published_at'])>cutoff:
                failures.append([month,'future_policy'])
            news=context['common_news']+context['personal_news']; counts[len(news)]+=1
            total_news+=len(news); brief_dates[context['policy_published_at']]+=1
            for article in news:
                if datetime.fromisoformat(article['pub_date'])>cutoff:
                    failures.append([month,'future_news'])
                label=article.get('semantic_label')
                news_excluded+=int(isinstance(label,dict) and label.get('decision')=='exclude')
            for field in state['fields'].values():
                if int(field['source_period'])>=month:
                    failures.append([month,'nonpast_prior'])
                prior_sources[field['source_kind']]+=1
            text=template[0]['content']
            assert fact_line(food) in text
            for fact in foods.values():
                if '- '+fact['label']+':' in text:
                    assert fact_line(fact) in text
            declared['food_view']+=int('General grocery-price background:' in text)
            declared['full_statistics_table']+=int('Recent official statistics:' in text)
            declared['transitory_policy']+=int('transitory' in text.partition('Public policy news brief')[2].partition('Personal view')[0].lower())
            prepared[(month,person)]=render_messages(template,state,month,context)
        first=next(iter(templates.values()))[0]['content']
        policy=first.partition('Public policy news brief')[2].partition('Personal view')[0]
        signed=next(r['signed_error_components'] for r in summary['monthly'] if r['month']==month)
        audit.append(dict(month=month,n=len(templates),as_of=next(iter(contexts.values()))['as_of'],
            food_reference_period=food['reference_period'],food_published_at=food['published_at'],
            food_yoy_pp=food['yoy_nsa_percent'],food_mom_pp=food['mom_nsa_percent'],
            available_all_cpi_yoy_pp=all_cpi['value'],available_energy_yoy_pp=energy['value'],
            food_source_sha_match=sha(ROOT/food['source_file'])==food['source_sha256'],
            news_counts=dict(counts),policy_release_counts=dict(brief_dates),
            policy_mentions_transitory='transitory' in policy.lower(),
            news_semantic_exclude_occurrences=news_excluded,
            earlier_fields_by_provenance=dict(prior_sources),signed_components=signed))
    raw_n=0; mismatches=0; reason_counts=Counter(); examples=[]
    with RAW.open() as stream:
        for line in stream:
            r=json.loads(line); key=(int(r['month']),r['agent_id'])
            if key not in prepared:continue
            raw_n+=1; mismatches+=int(r['messages']!=prepared[key])
            raw=r.get('raw_response_text') or ''
            try:reason=json.loads(raw).get('reason','')
            except (ValueError,AttributeError):reason=''
            for term in ('transitory','food','fed'):
                reason_counts[term]+=int(term in reason.lower())
            if len(examples)<3 and key[0]==202106 and 'transitory' in reason.lower():
                examples.append(reason)
    assert raw_n==6144 and mismatches==0
    assert not failures and all(r['food_source_sha_match'] for r in audit)
    early=[r for r in national if r['month']<='2022-12']
    later=[r for r in national if r['month']>='2023-01']
    frozen={}
    for loss in ('mae','mse'):
        q=estimate(early,loss);frozen[loss]=dict(simulation_weight=q,history_weight=1-q,
            fit_n=len(early),evaluation_n=len(later),evaluation=evaluate(later,q))
        assert q==summary['official_national']['chronological_combinations'][loss]['simulation_weight']
    result=dict(status='completed_targeted_2021_diagnostic',created_at_utc=datetime.now(timezone.utc).isoformat(),
        new_api_calls=0,new_density_fits=0,configuration_changes=False,
        environment_audit=dict(monthly=audit,rendered_messages=raw_n,raw_message_mismatches=mismatches,
            temporal_violations=failures,news_occurrences=total_news,template_counts=dict(declared),
            note='Dates and hashes checked against archived inputs; this is not certification of historical news text vintages or of strict route B.'),
        response_text_diagnostic=dict(original_raw_responses_only=True,keyword_counts=dict(reason_counts),
            example_june_reasons=examples,limit='Self-reported reasons and keyword counts cannot identify causes; repaired responses are not counted here.'),
        adjacent_returners_2021=prior_diagnostic(cases),
        national_2021=blend_block([r for r in national if r['month'].startswith('2021')]),
        retrospective_all82=blend_block(national),frozen_48_to_34=frozen,
        retrospective_later34=blend_block(later),
        formula='forecast = (1 - lambda) * latest_eligible_public_SCE + lambda * simulated_national_median',
        constraints='0 <= lambda <= 1; weights sum to one; no intercept; months equally weighted',
        limits=['All82 and later34 fitted weights are retrospective, not independent prediction scores.',
                'The historical public anchor can be t-2 when t-1 was not yet published.',
                'Food-only numerical views were a frozen design choice, not an accidental missing file.',
                'Common front-page news may intentionally carry an exclude semantic tag for the economic-personal channel; this alone is not a routing bug.',
                'Input relevance and model response cannot be causally separated without a new controlled experiment.'],
        sources={str(p.relative_to(ROOT)):sha(p) for p in sorted(source_files)},
        raw_ledger_sha256=sha(RAW),implementation_sha256=sha(Path(__file__)))
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    draw(result,summary,out)
    print(json.dumps({k:result[k] for k in ['retrospective_all82','frozen_48_to_34','retrospective_later34']},ensure_ascii=False))
    print('AUDIT',json.dumps({k:v for k,v in result['environment_audit'].items() if k!='monthly'}))
    print('2021_RETURNERS',json.dumps(result['adjacent_returners_2021']['equal_month_means']))
    print('2021_ENV',json.dumps([{k:r[k] for k in ['month','food_yoy_pp','available_all_cpi_yoy_pp','policy_mentions_transitory']} for r in audit]))
    return result


def draw(result,summary,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'Times New Roman','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
    rows=[r for r in summary['official_national']['monthly'] if r['month'].startswith('2021')]
    x=np.arange(1,13);fig,axes=plt.subplots(2,1,figsize=(10.5,7.6),constrained_layout=True)
    for key,label,color,marker in [('truth_pp','Observed SCE median','#202020','o'),('sim_pp','Simulation median','#d55e00','s'),('anchor_pp','Latest public SCE anchor','#0072b2','^')]:
        axes[0].plot(x,[r[key] for r in rows],label=label,color=color,marker=marker,lw=2)
    axes[0].set(title='2021: the simulated SCE median lagged the rise',ylabel='12-month inflation expectation (%)',xlabel='Target month in 2021',xticks=x)
    axes[0].legend(loc='upper left',frameon=False,ncol=1);axes[0].grid(axis='y',alpha=.15)
    audit=result['environment_audit']['monthly']
    axes[1].plot(x,[r['food_yoy_pp'] for r in audit],color='#d55e00',marker='s',label='Food at home: explicit in numerical prompt')
    axes[1].plot(x,[r['available_all_cpi_yoy_pp'] for r in audit],color='#0072b2',marker='o',label='All-items CPI: available in E, absent from full numerical table')
    axes[1].set(title='Different signals: grocery inflation stayed low during the initial CPI surge',ylabel='Latest eligible CPI 12-month change (%)',xlabel='Target month in 2021 (price reference month is earlier)',xticks=x)
    axes[1].legend(loc='upper left',frameon=False);axes[1].grid(axis='y',alpha=.15)
    fig.savefig(out/'2021_diagnostic.png',dpi=170);fig.savefig(out/'2021_diagnostic.svg');plt.close(fig)
