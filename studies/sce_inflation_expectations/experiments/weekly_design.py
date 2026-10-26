"""Read-only weekly-design inventory; not prompts, execution or model results.

Inspect release-time snapshots and the consequences of truncating OLD monthly
selections. This does not certify full weekly news-pool or historical-vintage
coverage and does not modify any frozen monthly-run dependency.
"""
import argparse
import calendar
from datetime import date, datetime, time
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from .frozen_batch import ROOT, read_json, dump, sha
from .full_a_personal_inputs import _food_snapshot, _policy_snapshot
from ..coverage_preparation import latest_wave
from ..submission_tools.reproduce import no_network

SOURCE=ROOT/'outputs/sce_recent_b_sampled_terminal_20261026_v1'
NY=ZoneInfo('America/New_York')


def weekly_cutoffs(month, weekday=4):
    """Actual seven-day grid; some calendar months have FIVE Fridays."""
    if len(str(month))!=6 or not str(month).isdigit() or not 0<=weekday<=6:
        raise ValueError('YYYYMM and weekday 0..6 required')
    year,mon=divmod(int(month),100)
    return [datetime.combine(date(year,mon,d),time(23,59,59),NY).isoformat()
            for d in range(1,calendar.monthrange(year,mon)[1]+1)
            if date(year,mon,d).weekday()==weekday]


def truncation_counts(contexts,cutoff):
    """A source selection can be truncated, but no missing candidate is restored."""
    when=datetime.fromisoformat(cutoff)
    if when.tzinfo is None:raise ValueError('Timezone-aware cutoff required')
    result=[]
    for ctx in contexts.values():
        articles=ctx['common_news']+ctx['personal_news']
        counts=sum(datetime.fromisoformat(a['pub_date'].replace('Z','+00:00'))<=when for a in articles)
        result.append(counts)
    if not result:raise ValueError('Nonempty source roster required')
    return dict(old_selected_mean_surviving=sum(result)/len(result),old_selected_min_surviving=min(result),
                old_selected_max_surviving=max(result))


def inventory(out,months=('202601','202604','202609')):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh local outputs directory required')
    sources={}
    def load(path):
        sources[str(path.relative_to(ROOT))]=sha(path);return read_json(path)
    p=load(SOURCE/'package/protocol.json')
    if not set(months)<=set(p['months']):raise ValueError('Months must belong to the registered B span')
    foods=load(ROOT/'outputs/sce_fullperiod_materialized_20261022_v2/food_catalog.json')
    policies=load(ROOT/'data/raw/sce_fullperiod_supplement_20261022/policy_sources_full_v2.json')
    waves=load(ROOT/'docs/workstreams/20261017_reference_scaleup/confidence_sources.json')['waves']
    waves+=load(ROOT/'data/raw/sce_fullperiod_supplement_20261022/confidence_supplement.json')['waves']
    plans={r['month']:r for r in load(ROOT/p['population_preflight']/'monthly_input_plan.json')}
    rows=[]
    for month in months:
        contexts=load(ROOT/p['input_templates']/month/'timing_context_private.json')
        for cutoff in weekly_cutoffs(month):
            key,facts=_food_snapshot(foods,cutoff);policy=_policy_snapshot(policies,cutoff);wave=latest_wave(waves,cutoff)
            anchor=plans[month]['last_public_national_anchor']
            rows.append(dict(month=month,cutoff=cutoff,**truncation_counts(contexts,cutoff),
                food_catalog_snapshot=key,food_published_at=facts['food_at_home']['published_at'],
                policy_published_at=policy['published_at'],confidence_wave=wave['wave_id'],
                monthly_prior_anchor_published_date=anchor['published_date'],
                monthly_prior_anchor_already_public=anchor['published_date']<=cutoff[:10],
                after_original_global_D=datetime.fromisoformat(cutoff)>datetime.fromisoformat(plans[month]['as_of'])))
    grid=[dict(month=m,cutoff=c) for m in p['months'] for c in weekly_cutoffs(m)]
    result=dict(status='offline_weekly_design_inventory_not_execution_package',timezone='America/New_York',
        illustrative_cutoff='every Friday 23:59:59 NY',full_11month_fridays=len(grid),calls_if_300_each=len(grid)*300,
        months_screened=list(months),monthly_selected_N_for_inventory=512,
        latest_archived_policy_publication=max(x['published_at'] for x in policies.values()),weekly=rows,new_api_calls=0,
        note='These counts truncate the old monthly selected views, not the complete weekly candidate universe. The Friday schedule is an unapproved design proposal.',
        unresolved=['full candidate labels and archive coverage after monthly D not certified',
                    'population/prior must be eligible before the earliest weekly cutoff',
                    '300-core roster and design weights not prepared',
                    'full policy inventory must be reconciled with actual releases',
                    'no weekly model messages, official Core acceptance or paid authorization created'])
    for path in (Path(__file__),ROOT/'scripts/inspect_sce_weekly_readiness.py'):
        sources[str(path.relative_to(ROOT))]=sha(path)
    out.mkdir();dump(out/'summary.json',result);dump(out/'proposed_friday_grid.json',grid)
    dump(out/'manifest.json',dict(source_sha256=sources,files_sha256={f.name:sha(f) for f in out.iterdir()},new_api_calls=0))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--months',default='202601,202604,202609')
    args=parser.parse_args()
    with no_network():result=inventory(args.out,args.months.split(','))
    print(json.dumps({k:v for k,v in result.items() if k!='weekly'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
