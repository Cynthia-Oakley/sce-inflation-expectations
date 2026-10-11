"""Offline-only evaluation of the frozen news trial; never a simulation input."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
from .household_state_analysis import density
from .monthly_analysis import weighted_summary
from .scoring.sce_q9_frozen import provenance

ARMS = ('shared', 'random', 'matched')
GROUPS = ('housing_tenure', 'age_group', 'numeracy')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def finite(value):
    return type(value) in (float, int) and np.isfinite(value)


def describe(values, point=False):
    x = np.asarray(values, dtype=float)
    if not len(x):
        return {'n': 0, 'median_pp': None, 'mean_pp': None, 'cross_person_iqr_pp': None}
    if not np.isfinite(x).all():
        raise ValueError('nonfinite values in a common-case distribution')
    median = weighted_summary(x, np.ones(len(x)), interpolate_median=point)['weighted_median_pp']
    lo, hi = np.quantile(x, [.25, .75])
    return {'n': len(x), 'median_pp': median, 'mean_pp': float(x.mean()),
            'cross_person_iqr_pp': float(hi - lo)}


def statistics(pred, real, point=False):
    pred, real = np.asarray(pred), np.asarray(real)
    a, b = describe(pred, point), describe(real, point)
    if not len(real):
        return {'distribution': a, 'median_absolute_error_pp': None,
                'distribution_W1_pp': None, 'IQR_absolute_gap_pp': None,
                'individual_MAE_auxiliary_pp': None}
    return {'distribution': a, 'median_absolute_error_pp': abs(a['median_pp'] - b['median_pp']),
            'distribution_W1_pp': float(np.mean(abs(np.sort(pred) - np.sort(real)))),
            'IQR_absolute_gap_pp': abs(a['cross_person_iqr_pp'] - b['cross_person_iqr_pp']),
            'individual_MAE_auxiliary_pp': float(np.mean(abs(pred - real)))}


def metrics(rows, point=False, bootstrap=2000):
    common = [r for r in rows if all(finite(r[k]) for k in ('real',) + ARMS)]
    real = np.asarray([r['real'] for r in common])
    result = {'n_selected': len(rows), 'n_common': len(common), 'n_excluded': len(rows)-len(common),
              'estimand': 'equal-weight common diagnostic sample; not a nationwide headline',
              'real': describe(real, point), 'arms': {}, 'matched_minus_random': {}}
    for arm in ARMS:
        pred = np.asarray([r[arm] for r in common])
        result['arms'][arm] = statistics(pred, real, point)
        result['arms'][arm]['groups'] = {}
        for group in GROUPS:
            result['arms'][arm]['groups'][group] = {}
            group_value = lambda r: str(r['profile'].get(group) or 'unknown')
            for value in sorted({group_value(r) for r in common}):
                selected = [r for r in common if group_value(r) == value]
                rp, sp = [r['real'] for r in selected], [r[arm] for r in selected]
                result['arms'][arm]['groups'][group][value] = {
                    'real': describe(rp, point), 'simulated': describe(sp, point),
                    'median_absolute_error_pp': abs(describe(rp, point)['median_pp'] - describe(sp, point)['median_pp']) if len(selected) >= 5 else None,
                    'interpretation': 'descriptive only' if len(selected) >= 5 else 'too small for group comparison'}
        weighted_rows = [r for r in common if finite(r.get('evaluation_weight')) and r['evaluation_weight'] > 0]
        if weighted_rows:
            weights = [r['evaluation_weight'] for r in weighted_rows]
            wp = weighted_summary([r[arm] for r in weighted_rows], weights, interpolate_median=point)
            wr = weighted_summary([r['real'] for r in weighted_rows], weights, interpolate_median=point)
            result['arms'][arm]['survey_weighted_auxiliary'] = {'simulated': wp, 'real': wr,
                'median_absolute_error_pp': abs(wp['weighted_median_pp'] - wr['weighted_median_pp'])}
    if not common:
        return result
    keys = ('median_absolute_error_pp', 'distribution_W1_pp', 'individual_MAE_auxiliary_pp')
    rng = np.random.default_rng(42)
    intervals = {k: [] for k in keys}
    for idx in rng.integers(0, len(common), size=(bootstrap, len(common))):
        rr = real[idx]
        scores = {arm: statistics(np.asarray([r[arm] for r in common])[idx], rr, point) for arm in ('matched', 'random')}
        for key in keys:
            intervals[key].append(scores['matched'][key] - scores['random'][key])
    for key in keys:
        result['matched_minus_random'][key] = {
            'change_pp': result['arms']['matched'][key] - result['arms']['random'][key],
            'paired_sample_bootstrap_95_interval_pp': np.quantile(intervals[key], [.025, .975]).tolist()}
    result['bootstrap_scope'] = 'conditional selected-person uncertainty only; excludes new news draws and repeated LLM generations'
    return result


def analyze(root, folder, out):
    root, folder, out = (Path(p).resolve() for p in (root, folder, out))
    if out.exists() or not out.is_relative_to(root / 'outputs'):
        raise ValueError('new ignored analysis output required')
    manifest = folder / 'trial_manifest.json'
    plan = json.loads(manifest.read_text())
    if plan['status'] != 'completed_pending_analysis' or len(plan['jobs']) != 6 or any(j.get('exit_code') != 0 for j in plan['jobs']):
        raise ValueError('requires a completed genuine six-job trial')
    for name, expected in plan['prepared_file_sha256'].items():
        if sha(folder / name) != expected:
            raise ValueError('changed frozen prepared file')
    scorer = provenance()
    if not scorer['live_matches_pinned']:
        raise ValueError('scorer source drift')
    truth_path = root / 'data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json'
    truth_data = json.loads(truth_path.read_text())
    truth = {(str(r['date']), f"sce_u{int(r['userid'])}"): r for r in truth_data['per_person']}
    link_path = folder / 'evaluation_links_private.json'
    links = json.loads(link_path.read_text())
    sources = {str(p.relative_to(root)): sha(p) for p in (manifest, truth_path, link_path, Path(__file__))}
    result = {'status': 'completed_offline_analysis', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
              'trial_directory': str(folder.relative_to(root)), 'scorer': scorer, 'sources': sources,
              'new_analysis_api_calls': 0, 'estimated_simulation_cost_usd': 0., 'actual_simulation_calls': 0,
              'not_vendor_invoice': True, 'months': {}, 'run_audit': [], 'limits': plan['limitations']}
    private = []
    for month in plan['months']:
        h = [r for r in links if r['month'] == month]
        ids = {r['agent_id'] for r in h}
        if len(ids) != plan['n_per_month'] or len(h) != len(ids):
            raise ValueError('evaluation link coverage')
        pop = json.loads((folder / month / 'population.json').read_text())
        profiles = {p['agent_id']: p['attributes'] for p in pop['personas']}
        by_arm = {}
        for arm in ARMS:
            jobs = [j for j in plan['jobs'] if j['month'] == month and j['arm'] == arm]
            if len(jobs) != 1:
                raise ValueError('missing or duplicate cell')
            run_dir = root / 'outputs/local_runs' / jobs[0]['run_id']
            run_path = run_dir / 'run_manifest.json'
            run = json.loads(run_path.read_text())
            if run['llm_kind'] != 'openai' or run['execution_purpose'] != 'news_exposure_behaviour_trial' or run['run_id'] != jobs[0]['run_id']:
                raise ValueError('run identity or kind')
            for name, expected in run['effective_artifact_sha256'].items():
                if sha(run_dir / name) != expected:
                    raise ValueError('changed effective input')
            for name, expected in run['source_snapshot_sha256'].items():
                if sha(run_dir / name) != expected:
                    raise ValueError('changed execution source snapshot')
                if name.startswith('source_snapshot/study/'):
                    frozen = plan['code_sha256'].get('studies/sce_inflation_expectations/' + name.removeprefix('source_snapshot/study/'))
                    if frozen and expected != frozen:
                        raise ValueError('executed frozen study source mismatch')
            calls_path = run_dir / 'llm_calls.jsonl'
            calls = [json.loads(l) for l in calls_path.read_text().splitlines()]
            previews = {r['agent_id']: r for r in json.loads((folder / month / f'preview_{arm}.json').read_text())}
            if len(calls) != len(ids) or {c['agent_id'] for c in calls} != ids:
                raise ValueError('actual call coverage')
            for c in calls:
                if c['attempt_idx'] != 0 or c['requested_model'] != 'deepseek-flash' or c['temperature'] != .5:
                    raise ValueError('retry/model/temperature drift')
                text = json.dumps(previews[c['agent_id']]['messages'], ensure_ascii=False)
                if c['prompt_text'] != text or hashlib.sha256(text.encode()).hexdigest() != c['prompt_sha256']:
                    raise ValueError('actual prompt differs from frozen input')
                if c['raw_response_text'] and hashlib.sha256(c['raw_response_text'].encode()).hexdigest() != c['raw_response_sha256']:
                    raise ValueError('raw response hash mismatch')
            with duckdb.connect(run['store_path'], read_only=True) as db:
                raw = db.execute('SELECT agent_id,action_payload FROM panel WHERE step=1 ORDER BY agent_id').fetchall()
            if len(raw) != len(ids) or {aid for aid, _ in raw} != ids:
                raise ValueError('trajectory coverage')
            by_arm[arm] = {aid: json.loads(p) if isinstance(p, str) else p for aid, p in raw}
            ledger = json.loads((run_dir / 'cost_ledger.json').read_text())
            result['estimated_simulation_cost_usd'] += ledger['estimated_cost_usd']
            result['actual_simulation_calls'] += len(calls)
            audit = {'month': month, 'arm': arm, 'run_id': run['run_id'], 'calls': len(calls),
                     'request_errors': sum(bool(c['error']) for c in calls),
                     'returned_models': dict(Counter(c['returned_model'] for c in calls)),
                     'validation_statuses': dict(Counter(p['validation_status'] for p in by_arm[arm].values())),
                     'estimated_cost_usd': ledger['estimated_cost_usd'],
                     'input_tokens': sum((c['usage'] or {}).get('prompt_tokens', 0) for c in calls),
                     'output_tokens': sum((c['usage'] or {}).get('completion_tokens', 0) for c in calls)}
            result['run_audit'].append(audit)
            for p in (run_path, calls_path, run_dir/'cost_ledger.json', Path(run['store_path'])):
                sources[str(p.relative_to(root))] = sha(p)
        qs = {'Q9': [], 'Q8_secondary': [], 'personal_uncertainty': [], 'raw_deflation_probability': []}
        statuses = Counter()
        for link in sorted(h, key=lambda r: r['agent_id']):
            aid = link['agent_id']
            real = truth[(month, link['source_agent_id'])]
            bins = {'real': [real.get(f'Q9_bin{i}') for i in range(1, 11)],
                    **{arm: [by_arm[arm][aid].get(f'q9_bin{i}') for i in range(1, 11)] for arm in ARMS}}
            fit = {key: density(value) for key, value in bins.items()}
            statuses.update(f'{k}:{v["status"]}' for k, v in fit.items())
            base = {'agent_id': aid, 'month': month, 'profile': profiles[aid], 'evaluation_weight': real.get('weight')}
            for measure, field in (('Q9', 'mean'), ('personal_uncertainty', 'iqr')):
                qs[measure].append({**base, **{k: v[field] for k, v in fit.items()}})
            qs['Q8_secondary'].append({**base, 'real': real.get('Q8v2part2'),
                 **{arm: by_arm[arm][aid]['point_pct'] if by_arm[arm][aid]['validation_status']=='valid' else None for arm in ARMS}})
            qs['raw_deflation_probability'].append({**base, **{k: sum(v[5:]) if all(finite(x) for x in v) and abs(sum(v)-100)<.5 else None for k, v in bins.items()}})
        result['months'][month] = {key: metrics(rows, point=key=='Q8_secondary') for key, rows in qs.items()}
        result['months'][month]['fit_status_counts'] = dict(statuses)
        result['months'][month]['news_delivery'] = plan['metadata'][month]['delivery']
        result['months'][month]['full_month_official_derived_reference'] = truth_data['monthly_full_sample'][month]
        private.extend({'measure': key, **r} for key, rows in qs.items() for r in rows)
    if result['estimated_simulation_cost_usd'] > plan['proposed_simulation_cap_usd'] or result['actual_simulation_calls'] != plan['planned_answers']:
        raise ValueError('aggregate budget or call count')
    result['limits'] += ['Same frozen approximate density scorer on both real and simulated bins.',
                        'Shared-arm news are one random set; comparison also depends on its content.',
                        'Six sequential jobs, one news seed and one LLM draw per person; no causal or national claim.']
    out.mkdir(parents=True)
    dump = lambda p, v: p.write_text(json.dumps(v, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    dump(out/'summary.json', result)
    dump(out/'paired_evaluation_private.json', private)
    return result
