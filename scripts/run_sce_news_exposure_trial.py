#!/usr/bin/env python3
"""Prepare/dry-run news exposure; real execution needs fresh complete-label approval."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.news_exposure_trial import prepare, dry_run, add_reading_preview, execute

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['prepare', 'dry-run', 'preview', 'run'])
    p.add_argument('--folder', type=Path, required=True)
    p.add_argument('--labels', type=Path, action='append')
    p.add_argument('--n', type=int, default=48)
    p.add_argument('--page', type=Path)
    p.add_argument('--prior-page', type=Path)
    p.add_argument('--approval-note', default='')
    a = p.parse_args()
    if a.mode == 'prepare':
        labels = a.labels or [ROOT / 'outputs/sce_nyt_label_trial_20261011_v3']
        r = prepare(ROOT, a.folder, [v.resolve() for v in labels], a.n)
        print(json.dumps({k: r[k] for k in ('status', 'planned_answers', 'complete_labels', 'conservative_simulation_cost_bound_usd')}, ensure_ascii=False))
    elif a.mode == 'dry-run':
        print(json.dumps(dry_run(ROOT, a.folder), ensure_ascii=False))
    elif a.mode == 'preview':
        if not a.page or not a.prior_page:
            p.error('preview requires page and prior-page directory')
        print(json.dumps(add_reading_preview(a.folder, a.page, a.prior_page)))
    else:
        if not a.approval_note.strip():
            p.error('run requires explicit new data-send and budget approval')
        execute(ROOT, a.folder, a.approval_note)

if __name__ == '__main__':
    main()
