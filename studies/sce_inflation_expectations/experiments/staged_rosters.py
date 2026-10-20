"""Optional disjoint roster segments for one sealed, two-phase paid batch."""
from collections import Counter
import json
import math
from pathlib import Path


def job_n(protocol, job):
    if 'roster_segments' not in protocol:
        return protocol['n_per_month']
    segment = next(s for s in protocol['roster_segments'][str(job['month'])]
                   if s['name'] == job['segment'])
    return segment['n']


def job_directory(folder, protocol, job):
    path = Path(folder)/str(job['month'])
    return path/job['segment'] if 'roster_segments' in protocol else path


def expected_cells(protocol):
    if 'roster_segments' not in protocol:
        return Counter((m, a, r, None) for m in protocol['months']
                       for a in protocol['arms'] for r in protocol['generation_repeats'])
    segments = protocol['roster_segments']
    if set(segments) != {str(m) for m in protocol['months']}:
        raise ValueError('Every month needs a complete segment plan')
    for rows in segments.values():
        if (not rows or len({s['name'] for s in rows}) != len(rows)
                or any(set(s) != {'name', 'n', 'phase'} or s['name'] not in ('gate', 'remainder', 'all')
                       or s['phase'] not in ('gate', 'main') or type(s['n']) is not int or s['n'] < 1 for s in rows)
                or sum(s['n'] for s in rows) != protocol['n_per_month']):
            raise ValueError('Disjoint positive segments must sum to the full monthly roster')
    return Counter((m, a, r, s['name']) for m in protocol['months'] for a in protocol['arms']
                   for r in protocol['generation_repeats'] for s in segments[str(m)])


def verify_segments(folder, protocol, jobs):
    if 'roster_segments' not in protocol:
        return
    def read(p): return json.loads(p.read_text())
    for month in protocol['months']:
        parent = Path(folder)/str(month)
        full = read(parent/'population.json')['personas']
        original = {r['agent_id']: r for r in full}
        if len(original) != len(full) or len(full) != protocol['n_per_month']:
            raise ValueError('Full roster size mismatch')
        seen = set()
        for segment in protocol['roster_segments'][str(month)]:
            part = parent/segment['name']
            rows = read(part/'population.json')['personas']
            ids = {r['agent_id'] for r in rows}
            if (len(rows) != segment['n'] or len(ids) != len(rows) or seen & ids
                    or any(r != original.get(r['agent_id']) for r in rows)):
                raise ValueError('Segment is duplicated, altered or outside frozen roster')
            seen |= ids
            for arm in protocol['arms']:
                full_prompts = read(parent/f'prompts_{arm}.json')['rows']
                prompts = read(part/f'prompts_{arm}.json')['rows']
                if set(prompts) != ids or any(prompts[i] != full_prompts[i] for i in ids):
                    raise ValueError('Segment prompts must exactly reuse full-batch messages')
        if seen != set(original):
            raise ValueError('Incomplete segmented roster')
    for job in jobs:
        s = next(s for s in protocol['roster_segments'][str(job['month'])] if s['name'] == job['segment'])
        if job['phase'] != s['phase']:
            raise ValueError('Job phase differs from frozen segment')


def technical_gate(folder, manifest, protocol, root):
    """No targets or fitting scores: only complete original replies and format."""
    from ..model import validate_sce_bins
    valid = total = raw_valid = changed = 0
    policy = protocol.get('q9_postprocessing')
    if policy:
        from ..q9_normalization import POLICY, response_view
        if policy != POLICY: raise ValueError('Unknown Q9 postprocessing policy')
    for job in manifest['jobs']:
        if job.get('phase') != 'gate':
            continue
        audit = Path(root)/'outputs/local_runs'/job['run_id']
        receipt = json.loads((audit/'run_manifest.json').read_text())
        if (receipt['status'] != 'completed' or receipt['llm_kind'] != 'openai'
                or receipt['protocol_sha256'] != protocol.get('reused_completed_jobs', {}).get(job['run_id'], manifest['protocol_sha256'])
                or receipt['cost']['call_count'] != job_n(protocol, job)):
            raise ValueError('Complete real gate runs required')
        calls = [json.loads(s) for s in (audit/'llm_calls.jsonl').read_text().splitlines() if s]
        previews = json.loads((job_directory(folder, protocol, job)/f"prompts_{job['arm']}.json").read_text())['rows']
        if len(calls) != len(previews) or {c['agent_id'] for c in calls} != set(previews):
            raise ValueError('Gate calls must cover each frozen person once')
        for call in calls:
            total += 1
            if (call.get('error') or call.get('returned_model') != protocol['model']
                    or call.get('returned_provider') != 'DeepInfra' or call.get('attempt_idx') != 0
                    or call.get('extra_body') != protocol['request_extra_body']
                    or call.get('temperature') != protocol['temperature']
                    or call.get('max_tokens') != protocol['max_tokens']
                    or call.get('prompt_sha256') != previews[call['agent_id']]['prompt_sha256']):
                raise ValueError('Gate transport or original input mismatch')
            try:
                obj = json.loads(call['raw_response_text'])
                q9 = obj['q9']; point = obj['point_pct']
                bins = [q9[f'bin{i}'] for i in range(1, 11)]
                ok = (call['finish_reason'] == 'stop' and type(point) in (int, float)
                      and math.isfinite(point) and set(q9) == {f'bin{i}' for i in range(1, 11)}
                      and all(type(v) in (int, float) and math.isfinite(v) for v in bins)
                      and validate_sce_bins(bins)[0])
            except (ValueError, KeyError, TypeError):
                ok = False
            raw_valid += bool(ok)
            if policy:
                try:
                    view = response_view(call['raw_response_text'])
                    ok = call['finish_reason'] == 'stop'
                    changed += bool(ok and view['applied'])
                except (ValueError, TypeError):
                    ok = False
            valid += bool(ok)
    expected = protocol['technical_gate']['planned_calls']
    if total != expected:
        raise ValueError('All gate requests must finish before expansion')
    result = {'scope': 'Technical format only; no truth or fit metrics read', 'calls': total,
            'valid': valid, 'fraction': valid/total,
            'passed': valid/total >= protocol['technical_gate']['minimum_valid_fraction'],
            'protocol_sha256': manifest['protocol_sha256'], 'new_api_calls': 0}
    if policy:
        result.update(raw_valid=raw_valid, raw_valid_fraction=raw_valid/total,
                      normalized_count=changed, postprocessing=policy,
                      note='Usability after proportional normalization, not raw-answer validity.')
    return result
