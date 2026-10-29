#!/usr/bin/env python3
"""Freeze a paper/package comparison from existing results, with no model calls."""
import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads((ROOT / path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    with Path(path).open() as f:
        return list(csv.DictReader(f))


def run(out, package):
    import sys
    sys.path.insert(0, str(ROOT))
    from studies.sce_inflation_expectations.evaluation.metrics import headline_errors
    out.mkdir(parents=True, exist_ok=False)
    source = 'outputs/sce_full_a_t0_readout_20261026_v1/summary.json'
    summary = load(source)
    analysis = load('outputs/sce_full_a_t0_analysis_20261026_v1/summary.json')
    macro_path = ROOT / 'outputs/sce_full_a_macro_calibration_20261026_v1/monthly_predictions_public.csv'
    macro = {r['month'].replace('-', ''): r for r in rows(macro_path)}
    weights = {'descriptive_combined': 0.159249952, 'frozen_combined': 0.1339762571517809}
    data = []
    for r in summary['monthly']:
        row = dict(month=r['month'], truth_pp=r['truth_pp'], raw_pp=r['sim_pp'], anchor_pp=r['anchor_pp'],
                   macro_pp=float(macro[r['month'].replace('-', '')]['Core_macro_without_sim']))
        for label, w in weights.items():
            row[label+'_pp'] = (1-w)*row['anchor_pp']+w*row['raw_pp']
        data.append(row)
    national = {}
    for label, first, last in [('all82','2019-01','2025-10'), ('year2021','2021-01','2021-12'),
                                ('late34','2023-01','2025-10')]:
        selected = [r for r in data if first <= r['month'] <= last]
        national[label] = dict(first_month=first, last_month=last, months=len(selected),
            methods={method:headline_errors([r[method+'_pp'] for r in selected], [r['truth_pp'] for r in selected])
                     for method in ['raw','anchor','macro',*weights]})
    same = summary['same_roster']
    paired = dict(q9_person_months=same['q9_person_months'], q8_person_months=same['q8_person_months'],
                  **same['metrics']['new'])
    counts = defaultdict(lambda: {'output_records':0,'new_API_attempts':0,'reported_cost_usd':0.0})
    micro = package / 'studies/sce_inflation_expectations/reproduction_data/micro'
    with gzip.open(micro / 'model_outputs.jsonl.gz','rt') as f:
        for r in map(json.loads, f):
            c = counts[r['run']]; c['output_records'] += 1
            if r['physical_new_api_attempt']:
                c['new_API_attempts'] += 1
                c['reported_cost_usd'] += r['reported_cost_usd'] or 0
    claim = dict(schema='sce_paper_metric_crosswalk/v1', new_API_calls=0,
        combination_weights=weights, paper_national=national, paper_paired_micro=paired,
        micro_supports={key:{'q9_person_months':analysis[key]['q9_person_months'],
            'weighted_metrics':{arm:a['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells']
                               for arm,a in analysis[key]['arms'].items()}}
                       for key in ['fixed_roster','genuine_previous_only','old_new_same_roster']},
        chronological_frozen_fit=summary['official_national']['chronological_combinations']['mse'],
        final_task_cost_coverage=dict(counts), whole_project_cost_reconciled=False,
        source_files_sha256={source:sha(ROOT/source), str(macro_path.relative_to(ROOT)):sha(macro_path),
            'outputs/sce_full_a_t0_analysis_20261026_v1/summary.json':sha(ROOT/'outputs/sce_full_a_t0_analysis_20261026_v1/summary.json')},
        interpretation=['Descriptive full-period combination is fitted on all82, not held-out.',
            'Late34 checks frozen coefficients; mechanism development already inspected later months.',
            'Paper paired micro supports differ from retained-start and full-wave supports.',
            'The selected four final tasks are not the whole project cost ledger.'])
    (out/'paper_metric_crosswalk.json').write_text(json.dumps(claim,ensure_ascii=False,indent=2)+'\n')
    with (out/'paper_A82_comparison.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
    doc=ROOT/'docs/reports/final_report_draft_v10/SCE研究报告_作者审阅稿_v10.docx'
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    with zipfile.ZipFile(doc) as z:
        xml=ET.fromstring(z.read('word/document.xml'))
        text='\n'.join(''.join(t.text or '' for t in p.findall('.//w:t',ns)) for p in xml.findall('.//w:p',ns))
        comments=len(ET.fromstring(z.read('word/comments.xml')).findall('w:comment',ns))
    (out/'paper_text_for_audit.txt').write_text(text)
    findings=[]
    for id,trigger in [('grid_region_is_not_a_dimension','我选择年龄、收入、教育和地区作为网格坐标'),
                       ('mechanism_window_not_untouched','机制筛选截止于2023年12月'),
                       ('common_cutoff_is_not_month_end','信息截止：统一月末')]:
        if trigger in text:findings.append(dict(id=id,status='author_correction_required',quote=trigger))
    acceptance=load('docs/reports/final_report_draft_v10/acceptance.json')
    current_hash=sha(doc)
    report=dict(status='paper_corrections_and_clean_PDF_pending',new_API_calls=0,paper_docx_sha256=current_hash,
        author_comments=comments,tracked_insertions=len(xml.findall('.//w:ins',ns)),
        tracked_deletions=len(xml.findall('.//w:del',ns)),paper_unchanged_by_audit=True,
        numeric_claims_checked=national,paper_paired_micro=paired,findings=findings,
        fees_scope=counts,estimated_whole_project_usd=108,whole_project_invoice_reconciled=False,
        final_PDF_exists=False)
    (out/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--package-root',type=Path,required=True)
    a=p.parse_args();r=run(a.out,a.package_root)
    print(json.dumps({k:r[k] for k in ('status','new_API_calls','paper_docx_sha256','findings','fees_scope')},ensure_ascii=False,indent=2))
