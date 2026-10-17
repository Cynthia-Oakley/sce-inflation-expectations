#!/usr/bin/env python3
"""Local-only availability audit for a proposed expanded A-line validation.

Reads projected profile/eligibility metadata, public E/news and prior cost
receipts. Does not open current inflation answers, select a favourable roster,
call a model, read credentials, or change an existing experiment.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(out):
    from studies.sce_inflation_expectations.coverage_preparation import build_news_pool, latest_wave
    from studies.sce_inflation_expectations.expanded_state_inputs import labels, confidence_waves
    from studies.sce_inflation_expectations.news_selection_trial import RecallRules, RULE_FILE
    from studies.sce_inflation_expectations.prior_belief_preparation import eligible_previous, month_offset
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh outputs directory required')
    months = [202003, 202009, 202103, 202109, 202206, 202212,
              202306, 202312, 202404, 202410, 202503, 202509]
    parent = ROOT / 'outputs/sce_expanded_state_trial_20261014_v3/manifest.json'
    frozen = json.loads(parent.read_text())
    frame_path = ROOT / 'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
    env_path = ROOT / 'outputs/sce_e_extension_2020_2025_verified_20261007/environment_candidate.json'
    source_hashes = {str(parent.relative_to(ROOT)): sha(parent)}
    for path in (frame_path, env_path):
        name = str(path.relative_to(ROOT))
        if sha(path) != frozen['source_sha256'][name]:
            raise ValueError('Archived source changed: ' + name)
        source_hashes[name] = sha(path)
    frame = pd.read_parquet(frame_path, columns=['date', 'userid', 'panel_status', 'tenure_valid',
        'timeline_consistent', 'raw_prior_valid', 'survey_date'])
    env = json.loads(env_path.read_text())
    targets = {int(t['target_month'].replace('-', '')): (i, t)
               for i, t in enumerate(env['provider_args']['targets'])}
    known_labels, label_hashes = labels()
    source_hashes.update(label_hashes)
    rules, waves = RecallRules(json.loads(RULE_FILE.read_text())), confidence_waves()
    policy_path = ROOT / 'docs/workstreams/20261013_behavior/codex_expanded_policy_sources_20261014.json'
    policies = json.loads(policy_path.read_text())
    source_hashes[str(policy_path.relative_to(ROOT))] = sha(policy_path)
    source_hashes[str(RULE_FILE.relative_to(ROOT))] = sha(RULE_FILE)
    rows, missing_ids = [], set()
    for month in months:
        index, target = targets[month]
        prior = frame[frame.date.eq(month_offset(month, -1))].set_index('userid', drop=False)
        cutoff = datetime.fromisoformat(target['as_of']).date()
        eligible = sum(eligible_previous(r, prior.loc[r['userid']], month, cutoff)
            for r in frame[frame.date.eq(month)].to_dict('records') if r['userid'] in prior.index)
        signals = env['provider_args']['signals_by_step'][str(index)]
        if any(datetime.fromisoformat(r['published_at']) > datetime.fromisoformat(target['as_of']) for r in signals):
            raise ValueError('Future public E signal')
        needed = [target['target_month'], f'{month_offset(month, -1)//100}-{month_offset(month, -1)%100:02}']
        absent = [m for m in needed if not (ROOT / 'data/raw/nyt_archive' / (m + '.json')).is_file()]
        missing = set()
        stats = {}
        if not absent:
            pool, stats, hashes = build_news_pool(ROOT, target['target_month'], target['as_of'], rules)
            source_hashes.update(hashes)
            missing = {r['article_id'] for r in pool if r['new_hits'] and r['article_id'] not in known_labels}
            missing_ids.update(missing)
        try:
            wave = latest_wave(waves, target['as_of'])
            confidence = wave['wave_id']
        except ValueError:
            confidence = 'needs_explicit_A_retrospective_2019_proxy_or_source'
        policy = policies.get(str(month))
        policy_ready = bool(policy and (ROOT / policy['file']).is_file()
                            and sha(ROOT / policy['file']) == policy['sha256'])
        rows.append({'month': month, 'as_of': target['as_of'],
            'previous_answer_eligible_upper_bound_n': int(eligible),
            'eligible_note': 'Past-only timeline/raw validity screen. Frozen-fitter eligibility, P mapping and N192 still require preparation; no current target screened.',
            'macro_environment_signal_n': len(signals), 'news_raw_missing_months': absent,
            'news_window_articles': stats.get('unique_articles'),
            'news_coarse_candidates': stats.get('coarse_candidates'),
            'missing_news_labels_in_window': len(missing),
            'archived_policy_brief_ready': policy_ready, 'confidence_source': confidence,
            'already_in_latest_four_month_trial': month in (202206, 202306, 202410, 202509)})
    receipt_path = ROOT / 'docs/workstreams/20261017_finance_validation/execution_receipt.json'
    receipt = json.loads(receipt_path.read_text())
    source_hashes[str(receipt_path.relative_to(ROOT))] = sha(receipt_path)
    planned_calls = len(months) * 192 * 2
    value = {'status': 'proposal_coverage_audited_not_prepared_or_authorized',
        'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'months': months,
        'n_per_month_proposed': 192, 'n_repeats_proposed': 2, 'llm_arms': 1,
        'planned_llm_calls': planned_calls, 'new_api_calls': 0, 'new_mcp_calls': 0,
        'current_inflation_answers_read': False, 'rows': rows,
        'news_unique_missing_labels': len(missing_ids),
        'news_raw_cache_missing_windows': sum(bool(r['news_raw_missing_months']) for r in rows),
        'policy_briefs_requiring_local_authoring': sum(not r['archived_policy_brief_ready'] for r in rows),
        'simulation_linear_cost_estimate_usd_not_cap': receipt['peak_token_cost_estimate_usd_not_bill'] / receipt['actual_calls'] * planned_calls,
        'cost_limit': 'Linear extrapolation from last768 calls only; new prompt bytes and label batches not yet materialized. No budget cap or new authorization implied.',
        'code_sha256': sha(__file__), 'source_sha256': source_hashes}
    out.mkdir(parents=True)
    (out / 'coverage.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.out)
    print(json.dumps({key: result[key] for key in ('status', 'planned_llm_calls', 'news_unique_missing_labels',
        'news_raw_cache_missing_windows', 'policy_briefs_requiring_local_authoring',
        'simulation_linear_cost_estimate_usd_not_cap', 'new_api_calls')}, ensure_ascii=False, indent=2))
