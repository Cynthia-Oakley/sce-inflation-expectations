"""Prepare a local, paired real-run demo. No model calls; originals read-only."""
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import csv
import hashlib
import json
import math
import re
import sys

import numpy as np
from scipy.stats import beta as beta_distribution

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.scoring.beta_fit_kernel import fit
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import provenance
from studies.sce_inflation_expectations.scoring.sce_q9 import weighted_empirical_quantile

OUT = ROOT / 'deliverables/video/samples_v02'
BUILD = ROOT / 'tmp/video_samples_v02'
INPUT = ROOT / 'outputs/sce_full_a_personal_inputs_20261025_v1'
RUN = ROOT / 'outputs/sce_full_a_t0_terminal_20261025_v1'
EVAL = ROOT / 'outputs/sce_full_a_t0_analysis_20261026_v1'
SEED = 'sce-video-v02-20261028'
MONTH_COUNTS = {'202106': 12, '202206': 6, '202506': 6}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def write(p, x):
    Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2, allow_nan=False))


def protect():
    files = []
    for directory in ['deliverables/video/v01', 'docs/reports/final_report_draft_v10',
                      'deliverables/research_package/v05',
                      'docs/workstreams/20261027_final_delivery/overview_figure_v3']:
        for p in sorted((ROOT / directory).rglob('*')):
            if p.is_file() and p.name != '.DS_Store' and not p.name.startswith('.~'):
                files.append(dict(path=str(p.relative_to(ROOT)), sha256=sha(p)))
    dest = BUILD / 'protected_before.json'
    if dest.exists():
        assert read(dest) == files, 'Protected original changed'
    else:
        write(dest, files)
    return len(files)


def rank(aid):
    return hashlib.sha256((SEED + '|' + aid).encode()).hexdigest()


def fragment(text, start, end=None):
    a = text.index(start)
    b = text.index(end, a + len(start)) if end else len(text)
    return text[a:b].strip()


def parts(text):
    chunks = {
        'profile': [text.split('\n\n')[0],
                    fragment(text, 'Synthetic household spending context', 'General news you encountered:')],
        'belief': [fragment(text, 'Earlier belief state', 'Question 1 (point estimate):')],
        'environment': [fragment(text, 'Household grocery context', 'Synthetic household spending context'),
                        fragment(text, 'General news you encountered:', 'Earlier belief state')],
        'questions': [fragment(text, 'Question 1 (point estimate):', 'Response instructions for the same two questions above:')],
        'format': [fragment(text, 'Response instructions for the same two questions above:')],
    }
    if 'Personal view about economic policy:' in text:
        chunks['profile'].append(fragment(text, 'Personal view about economic policy:', 'Publication timing for the same information above:'))
    # Personal confidence is inside the original environment/timing block.
    for fragments in chunks.values():
        assert all(x in text for x in fragments)
    return chunks


ZH = {
    'Under 40': '40岁以下', '40–60': '40—60岁', '40-60': '40—60岁',
    '40 to 60': '40—60岁', 'Over 60': '60岁以上',
    'high_school': '高中及以下', 'some_college': '部分大学教育', 'college': '大学及以上',
    'High': '较高', 'Low': '较低', 'under_50k': '低于5万美元',
    '50k_100k': '5万—10万美元', 'over_100k': '高于10万美元',
    'employed': '在职', 'not_employed': '非在职', 'unemployed': '未就业',
    'owner': '自有住房', 'renter': '租住', 'West': '西部', 'Midwest': '中西部',
    'disabled': '因健康障碍未工作', 'homemaker': '料理家庭', 'retired': '退休',
    'Northeast': '东北部', 'South': '南部', 'Unknown': '未知',
    'under_40': '40岁以下', '40_60': '40—60岁', 'over_60': '60岁以上',
    'high': '较高', 'low': '较低', 'unknown': '未知',
}


def profile_cn(raw, stratum):
    fields = stratum.split('|')
    ed, num, age, inc = (fields + ['未知'] * 4)[:4]
    if len(fields)!=4:
        ed=raw.get('education_group','unknown');num=raw.get('numeracy','unknown')
        age=raw.get('age_group','unknown');inc=raw.get('household_income_band','unknown')
    return dict(age=ZH.get(age, age),
                education=ZH.get(ed, ed), numeracy=ZH.get(num, num), income=ZH.get(inc, inc),
                region=ZH.get(raw.get('region'), raw.get('region', '未知')),
                employment=ZH.get(raw.get('employment_status'), raw.get('employment_status', '未知')),
                housing=ZH.get(raw.get('housing_tenure'), raw.get('housing_tenure', '未知')))


def density(bins, archived):
    positive = [i for i, v in enumerate(bins) if v > 0]
    if len(positive) >= 3:
        f = fit(bins, variant='relaxed_tail_skip_zero', tail_start=20.)
        assert abs(f['mean'] - archived['mean']) < 1e-7
        assert abs(f['iqr'] - archived['iqr']) < 1e-6
        a, b, lo, hi = f['params']
        # Midpoint sampling avoids endpoint singularities. Params are retained.
        xx = np.linspace(lo + (hi-lo)*1e-5, hi-(hi-lo)*1e-5, 241)
        yy = beta_distribution.pdf((xx-lo)/(hi-lo), a, b)/(hi-lo)
        return dict(family='广义Beta', x=xx.tolist(), y=yy.tolist(), params=f['params'],
                    mean=f['mean'], q25=f['quartiles'][0], q75=f['quartiles'][2],
                    curve_reconstructed_offline=True)
    if len(positive) == 1:
        bounds=[(12,38),(8,12),(4,8),(2,4),(0,2),(-2,0),(-4,-2),(-8,-4),(-12,-8),(-38,-12)]
        lo,hi=bounds[positive[0]];xx=np.linspace(lo,hi,100)
        return dict(family='均匀',x=xx.tolist(),y=[1/(hi-lo)]*len(xx),
                    params=[lo,hi],mean=archived['mean'],q25=lo+(hi-lo)*.25,q75=lo+(hi-lo)*.75,
                    curve_reconstructed_offline=True)
    mid=archived['mean'];span=archived['iqr']/(1-1/math.sqrt(2));lo=mid-span/2;hi=mid+span/2
    xx=np.linspace(lo,hi,121);yy=np.maximum(0,2/span*(1-np.abs(xx-mid)/(span/2)))
    return dict(family='三角',x=xx.tolist(),y=yy.tolist(),params=[lo,hi],mean=mid,
                q25=mid-archived['iqr']/2,q75=mid+archived['iqr']/2,curve_reconstructed_offline=True)


def news_item(n, kind):
    return dict(kind=kind, headline=n['headline'], date=n['pub_date'][:10],
                published_at=n['pub_date'], abstract=n.get('abstract') or n.get('snippet') or '',
                url=n.get('web_url',''), tags=n.get('routing_tags') or [],
                topics=(n.get('semantic_label') or {}).get('topics') or [])


def main():
    OUT.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    (OUT/'.gitignore').write_text('*\n')  # Local display contains paired questionnaire-derived inputs.
    (BUILD/'.gitignore').write_text('*\n')
    protected = protect()
    assert provenance()['live_matches_pinned']
    cases=defaultdict(dict)
    for c in read(EVAL/'cases_private.json'):
        if str(c['month']) in MONTH_COUNTS:
            cases[str(c['month'])][c['agent_id']]=c
    view=RUN/read(RUN/'latest_generation_view.json')['path']
    actions={}
    for line in (view/'logical_actions_private.jsonl').open():
        a=json.loads(line)
        if str(a['month']) in MONTH_COUNTS:actions[str(a['month']),a['agent_id']]=a
    sources=[EVAL/'cases_private.json',RUN/'protocol.json',view/'logical_actions_private.jsonl',
             ROOT/'studies/sce_inflation_expectations/scoring/beta_fit_kernel.py']
    normal_source=ROOT/'outputs/sce_full_a_core_normal_prediction_20261026_v2/summary.json'
    normal_months={r['month']:r for r in read(normal_source)['months']};sources.append(normal_source)
    chosen=[];contexts={};all_news={};prompts={};monthly={};private=[]
    national_path=ROOT/'deliverables/research_package/v05/package/studies/sce_inflation_expectations/reproduction_data/A82_personal_T0.csv'
    national={r['month'].replace('-',''):r for r in csv.DictReader(national_path.open())}
    for month,n in MONTH_COUNTS.items():
        pf=INPUT/month/'prompts.json';cf=INPUT/month/'contexts_private.json';rf=INPUT/month/'roster_private.json'
        sources.extend([pf,cf,rf]);prompts[month]=read(pf)['rows'];contexts[month]=read(cf);roster=read(rf)['rows']
        pool={}
        for v in contexts[month].values():
            for key in ['common_news','personal_news']:
                for article in v[key]:pool[article['article_id']]=article
        all_news[month]=pool
        eligible=[]
        for aid,c in cases[month].items():
            a=actions.get((month,aid));score=c['arms']['monthly_reconstruction']
            if not a or a['field_source']!={'q8':'main','q9':'main'} or score['scorer_status']!='ok':continue
            if not a['main']['raw_reply_ref'] or a['main']['error']:continue
            if not math.isfinite(score['mean']):continue
            eligible.append(aid)
        ranked=sorted(eligible,key=rank)
        main=ranked[0]
        if month=='202106':
            role=roster[main]['role'];tier=roster[main]['news_tier']
            second=next(a for a in ranked[1:] if roster[a]['role']==1 and roster[a]['news_tier']!=tier
                        and 'unknown' not in cases[month][a]['stratum'].lower()
                        and contexts[month][a]['as_of']<'2021-06-10')
            ranked=[main,second]+[a for a in ranked if a not in (main,second)]
        for aid in ranked[:n]:chosen.append((month,aid))
        group=[c for c in cases[month].values() if c['survey_weight'] and c['survey_weight']>0
               and c['arms']['monthly_reconstruction']['mean'] is not None]
        vals=[c['arms']['monthly_reconstruction']['mean'] for c in group];ws=[c['survey_weight'] for c in group]
        med=weighted_empirical_quantile(vals,ws,.5)
        assert abs(med-float(national[month]['sim_pp']))<1e-9
        mass=defaultdict(float)
        for v,w in zip(vals,ws):mass[v]+=w/sum(ws)
        monthly[month]=dict(n=len(group),median=med,atoms=[dict(x=x,mass=w) for x,w in sorted(mass.items())],
                            q25=weighted_empirical_quantile(vals,ws,.25),q75=weighted_empirical_quantile(vals,ws,.75),
                            frame_n=normal_months[month]['target_frame_n'],normal_n=normal_months[month]['normal_n'])
    # Read only the exact paired replies, indexed by immutable source line references.
    reply_requests=defaultdict(set)
    for month,aid in chosen:
        a=actions[month,aid];rel=a['main']['raw_reply_ref'].split('#')[0]
        reply_requests[rel].add(a['key'])
    replies={}
    for rel,keys in reply_requests.items():
        f=RUN/rel;sources.append(f)
        for i,line in enumerate(f.open(),1):
            row=json.loads(line)
            if row['key'] in keys:replies[row['key']]=(row,str(f.relative_to(ROOT)),i)
    samples=[]
    for idx,(month,aid) in enumerate(chosen,1):
        c=cases[month][aid];ctx=contexts[month][aid];a=actions[month,aid];pr=prompts[month][aid]
        raw,ref,line_no=replies[a['key']]
        actual=hashlib.sha256(json.dumps(pr['messages'],ensure_ascii=False).encode()).hexdigest()
        assert actual==pr['prompt_sha256']==a['prompt_sha256']==raw['prompt_sha256']
        rawtext=raw['raw_response_text'];obj=json.loads(rawtext)
        bins=[float(obj['q9'][f'bin{i}']) for i in range(1,11)]
        assert abs(sum(bins)-100)<1e-6,'Demo pool needs already valid raw sum'
        assert all(abs(x-y)<1e-8 for x,y in zip(bins,a['effective_q9_bins']))
        assert abs(obj['point_pct']-a['effective_q8'])<1e-8
        text=pr['messages'][0]['content'];chunks=parts(text)
        assert not re.search(r'\bsce_[0-9a-f]{16}\b',text+rawtext)
        food=chunks['environment'][0]
        roletext=food.splitlines()[1]
        rolezh=('全部采购' if 'all of' in roletext else '多数采购' if 'a lot of' in roletext else
                '少量采购' if 'a little of' in roletext else '部分采购' if 'some' in roletext else
                '不负责采购' if 'none' in roletext or 'not' in roletext else '按原文角色')
        news=[news_item(x,'共同关注') for x in ctx['common_news']]+[news_item(x,'个人匹配') for x in ctx['personal_news']]
        selectedids={x['article_id'] for x in ctx['common_news']+ctx['personal_news']}
        late=[x for key,x in all_news[month].items() if key not in selectedids and
              datetime.fromisoformat(x['pub_date'].replace('Z','+00:00'))>datetime.fromisoformat(ctx['as_of'])]
        late=sorted(late,key=lambda x:x['pub_date'])
        late_item=news_item(late[0],'晚于截止，未进入本次输入') if late else None
        score=c['arms']['monthly_reconstruction'];den=density(bins,score)
        pcn=profile_cn(c['profile'],c['stratum'])
        prior_point=re.search(r'\{"point_pct":\s*([\d.\-]+)\}',text)
        news_count=len(news)
        sample=dict(id=f'A{idx:02}',month=month,profile=pcn,cutoff=ctx['as_of'],
                    prior_q8=float(prior_point.group(1)) if prior_point else None,
                    grocery_role=rolezh,grocery_role_original=roletext,
                    food_lines=[l[2:] for l in food.splitlines() if l.startswith('- ')],
                    food_block=food,spending_block=chunks['profile'][1],
                    food_reference=ctx['food_reference_period'],food_published=ctx['food_published_at'],
                    policy_published=ctx['policy_published_at'],news_tier=ctx['news_tier'],
                    news_count=news_count,common_count=ctx['common_news_count'],personal_count=ctx['personal_news_count'],
                    news=news,late_article=late_item,sections=chunks,messages=pr['messages'],
                    response_raw=rawtext,response=obj,q8=float(obj['point_pct']),bins=bins,density=den,
                    prompt_hash=actual,response_hash=raw['raw_response_sha256'],
                    provider=raw['returned_provider'],model=raw['returned_model'],
                    raw_probability_sum=sum(bins),normalization_applied=False,
                    timestamp=raw['finished_at_utc'],latency_ms=raw.get('latency_ms'))
        assert news_count==ctx['news_tier']
        samples.append(sample)
        private.append(dict(demo_id=sample['id'],month=month,agent_id=aid,
                            prompt_file=str((INPUT/month/'prompts.json').relative_to(ROOT)),
                            reply_file=ref,reply_line=line_no,prompt_sha256=actual,raw_response_sha256=raw['raw_response_sha256']))
    data=dict(schema='sce_video_real_samples/v2',seed=SEED,default_sample='A01',comparison_sample='A02',
              samples=samples,months=monthly,bin_labels=['≤−12','−12~−8','−8~−4','−4~−2','−2~0','0~2','2~4','4~8','8~12','≥12'],
              source_note='最新A T0真实运行；展示编号不等于原受访者ID。输入节选与原始回答逐份配对。',
              curve_note='曲线仅对24个演示答卷按原冻结核重建，均值与IQR逐份核对封存计分；不更改研究结果。')
    write(BUILD/'data.json',data);write(BUILD/'private_lineage.json',private)
    write(BUILD/'source_manifest.json',dict(files={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(sources))},
                                           protected_files=protected,api_calls=0,density_curve_reconstructions=len(samples)))
    (BUILD/'node_modules').symlink_to('/Users/wushuyue/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules',target_is_directory=True) if not (BUILD/'node_modules').exists() else None
    print(json.dumps(dict(samples=len(samples),protected_files=protected,
                         main={k:samples[0][k] for k in ['id','month','profile','q8','news_count','grocery_role']},
                         comparison={k:samples[1][k] for k in ['id','month','profile','q8','news_count','grocery_role']},
                         mean=samples[0]['density']['mean'],national=monthly['202106']['median'],new_api_calls=0),ensure_ascii=False))


if __name__=='__main__':main()
