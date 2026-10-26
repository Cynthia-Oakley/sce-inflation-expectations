"""Public-news-only handoff/inventory for immutable B archive repair overlays."""
import argparse
import json
from pathlib import Path

from .recent_b_sampled_dates import ROOT,BASE,load_repair,merge_labels,archive_view,archive_screen
from .full_a_core_normal import read,write,sha,fresh
from .recent_b_news_refresh import _load_labels,is_sce_report,B_SCE_PATTERN,text_of
from .fullperiod_materialization import news_pool_for_prompts
from ..coverage_preparation import previous_month
from ..news_selection_trial import RecallRules,RULE_FILE
from ..evaluation.response_date_distribution import days
from ..submission_tools.reproduce import no_network


def inventory(out,repair_manifest=None):
    out=fresh(out);sources={str(p.relative_to(ROOT)):sha(p) for p in (BASE/'summary.json',RULE_FILE,Path(__file__))}
    overrides,extra=load_repair(repair_manifest,sources)
    labels=merge_labels(_load_labels(read(BASE/'summary.json'),sources),extra)
    targets=['2026-01','2026-02','2026-09'];months={m for target in targets for m in (previous_month(target),target)}
    view,aliases=archive_view(out,months,overrides)
    screens=[archive_screen(m,days(m.replace('-','')),overrides,sources) for m in sorted(months)]
    rules=RecallRules(read(RULE_FILE));pending={};by_window={}
    for target in targets:
        cutoff=f'{target}-{days(target.replace("-","")):02}T23:59:59'+('-05:00' if target[-2:] in ('01','02') else '-04:00')
        pool,_,hashes=news_pool_for_prompts(view,target,cutoff,rules)
        for name,digest in hashes.items():
            m=Path(name).stem;actual=ROOT/aliases[m]
            if sha(actual)!=digest:raise ValueError('Archive alias hash mismatch')
            sources[aliases[m]]=digest
        rows=[r for r in pool if r['new_hits'] and r['article_id'] not in labels
              and not is_sce_report(r) and not B_SCE_PATTERN.search(text_of(r))]
        by_window[target]=len(rows)
        for row in rows:
            aid=row['article_id']
            if aid not in pending:
                pending[aid]={k:row.get(k,'') for k in ('article_id','headline','abstract','snippet','source',
                    'section_name','news_desk','pub_date','web_url','canonical_source_id','text_sha256')}
                pending[aid]['target_windows']=[]
            pending[aid]['target_windows'].append(target)
    ordered=sorted(pending.values(),key=lambda r:(r['pub_date'],r['article_id']))
    for name,rows in [('pending_public_news.jsonl',ordered),('pending_public_news_202609.jsonl',[r for r in ordered if '2026-09' in r['target_windows']])]:
        with (out/name).open('w') as f:
            for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    write(out/'archive_coverage.json',screens)
    summary=dict(status='public_news_repair_inventory_only',target_windows=targets,missing_labels_by_window=by_window,
       unique_pending_articles=len(pending),archive_coverage_blockers=[r for r in screens if not r['screen_passed']],
       January_raw_gap_also_affects_February=True,
       September_note='Canonical September has observed dates1..30;297 previously unclassified candidates are labels,not297 missing original articles. Endpoint/source completeness still needs reconciliation.',
       repaired_sources_requested=repair_manifest is not None,new_api_calls=0,raw_files_overwritten=False,
       expected_overlay_schema='sce_B_news_repair_overlay/v1')
    write(out/'summary.json',summary)
    for name in ('experiments/recent_b_sampled_dates.py','experiments/recent_b_news_refresh.py','experiments/fullperiod_materialization.py'):
        p=ROOT/'studies/sce_inflation_expectations'/name;sources[str(p.relative_to(ROOT))]=sha(p)
    write(out/'manifest.json',dict(source_sha256=sources,
       files_sha256={str(p.relative_to(out)):sha(p) for p in out.iterdir() if p.is_file()}))
    print('Public-news pending',len(pending),'by window',by_window,';0 API')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--repair-manifest',type=Path);a=p.parse_args()
    with no_network():inventory(a.out,a.repair_manifest)


if __name__=='__main__':main()
