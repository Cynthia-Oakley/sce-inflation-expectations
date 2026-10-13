#!/usr/bin/env python3
"""Prepare factual mechanism evidence offline; never executes simulation."""
from pathlib import Path
import argparse
import json
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.factual_mechanism_audit import audit_prior, audit_diary, sha
from studies.sce_inflation_expectations.diary_experience import category_map_from_dictionary, read_official_diary_zip


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory; never overwrite a run')
    out.mkdir(parents=True)
    cache = ROOT/'outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet'
    receipt = json.loads(cache.with_name('extraction_receipt.json').read_text())
    if sha(cache) != receipt['cache_sha256']:
        raise ValueError('reference cache drift')
    for r in receipt['sources']:
        if sha(ROOT/r['path']) != r['sha256']:
            raise ValueError('official source hash drift')
    frame = pd.read_parquet(cache)
    if len(frame) != receipt['rows']:
        raise ValueError('cache row count drift')
    prior = audit_prior(frame)
    zipfile = ROOT/'data/raw/ce_experience/20261006/diary/diary20.zip'
    dictionary = ROOT/'data/raw/ce_experience/20261006/ce_pumd_dictionary_official.xlsx'
    oldpath = ROOT/'data/interim/ce_experience/20261006T071002778274Z_ce_diary2020q4_4862a21e/diary_weekly.jsonl'
    old_manifest = json.loads(oldpath.with_name('manifest.json').read_text())
    checks = [(zipfile,old_manifest['source']['archive_sha256']),
              (dictionary,old_manifest['dictionary']['sha256']),
              (oldpath,old_manifest['files']['diary_weekly.jsonl']['sha256'])]
    for p, expected in checks:
        if sha(p) != expected:
            raise ValueError('Diary input drift: '+str(p))
    old = [json.loads(x) for x in oldpath.read_text().splitlines()]
    mapping, known, map_audit = category_map_from_dictionary(dictionary)
    _, expd, members, _ = read_official_diary_zip(zipfile)
    records, frequency = audit_diary(old, expd[4], mapping, known)
    # Local external donor records only; never exported to API or runtime P.
    (out/'diary_category_days_private.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    summary = {'checked_on':'2026-10-13', 'status':'offline_evidence_and_proxy_preparation',
               'new_llm_calls':0, 'runtime_changed':False, 'prior':prior, 'diary':frequency,
               'sources': {str(p.relative_to(ROOT)):sha(p) for p in [cache,zipfile,dictionary,oldpath]},
               'official_workbook_sources':receipt['sources'], 'ucc_mapping':map_audit,
               'raw_diary_members':members,
               'code_sha256': {str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__), ROOT/'studies/sce_inflation_expectations/factual_mechanism_audit.py',ROOT/'studies/sce_inflation_expectations/diary_experience.py']}}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'output':str(out), 'sce_rows':prior['rows'], 'sce_pairs':prior['valid_q9_pairs'],
                      'diary_weeks':frequency['household_weeks'], 'union_checks':frequency['overall_day_set_reconciliation_passed']},ensure_ascii=False))


if __name__ == '__main__':
    main()
