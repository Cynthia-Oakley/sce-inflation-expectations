"""Adapt scored evaluation caches into canonical long records (zero-call, offline).

One canonical record is "experiment x month x person x repeat x arm". Batches
are discovered by scanning ``outputs/*_evaluation_*/cases_private.json``; the
REGISTRY assigns Chinese display names to known batches, unknown batches are
shown as 未登记. Batches that do not follow the current case contract (no
``real``/``arms`` keys) are discovered but excluded from analysis with an
explicit reason instead of being guessed into shape.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from studies.sce_inflation_expectations.population_stratification import cell_key

from studies.sce_inflation_expectations.panel.registry import CATALOG, entry_for

# batch dir name -> (中文显示名, 说明)；已知批次的展示元数据集中在 registry.CATALOG
REGISTRY = {k: (v['label'], v['note']) for k, v in CATALOG.items()}

PROFILE_FIELDS = ('age_group', 'region', 'state', 'education_group',
                  'household_income_band', 'numeracy', 'employment_status',
                  'housing_tenure')
REQUIRED_CASE_KEYS = ('month', 'userid', 'repeat', 'real', 'arms')

PROTOCOL_KEYS = ('id', 'research_line', 'months', 'n_per_month', 'arms',
                 'generation_repeats', 'model', 'official_advertised_version',
                 'temperature', 'status')


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _num(value):
    return float(value) if finite(value) else None


def shape_features(bins):
    """Pre-computed ten-bin shape features; None when bins are absent/invalid."""
    if not isinstance(bins, (list, tuple)) or len(bins) != 10:
        return None
    try:
        b = [float(x) for x in bins]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(x) for x in b):
        return None
    max_prob = max(b)
    return {
        'nz_bins': sum(1 for x in b if x > 0),
        'max_prob': max_prob,
        'n_modal': sum(1 for x in b if x == max_prob) if max_prob > 0 else 0,
        'all_zero': all(x <= 0 for x in b),
        'mult5_share': sum(1 for x in b if x % 5 == 0) / 10.,
        'mult10_share': sum(1 for x in b if x % 10 == 0) / 10.,
    }


def discover_case_files(outputs_dir):
    return sorted(Path(outputs_dir).glob('*_evaluation_*/cases_private.json'))


def _protocol_summary(summary):
    protocol = summary.get('protocol', {}) if isinstance(summary, dict) else {}
    out = {k: protocol.get(k) for k in PROTOCOL_KEYS if k in protocol}
    out['estimated_cost_usd'] = summary.get('estimated_run_cost_usd_not_provider_bill')
    out['batch_status'] = summary.get('status')
    return out


def load_batch(case_path):
    """Load one batch; returns (records, meta). records empty when skipped."""
    case_path = Path(case_path)
    batch = case_path.parent.name
    summary_path = case_path.parent / 'summary.json'
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    entry = entry_for(batch)
    label, description = entry['label'], entry['note']
    meta = {'batch': batch, 'label': label, 'registered': batch in CATALOG,
            'registry': {k: entry[k] for k in ('section', 'mechanism_group', 'parent',
                                               'run_status', 'evidence_stage')},
            'description': description, 'summary_path': str(summary_path),
            'protocol': _protocol_summary(summary), 'weight_field': None,
            'n_cases': 0, 'n_records': 0}
    cases = json.loads(case_path.read_text())
    meta['n_cases'] = len(cases)
    first = cases[0] if cases else {}
    missing = [k for k in REQUIRED_CASE_KEYS if k not in first]
    if missing:
        meta['status'] = 'skipped_old_contract'
        meta['skip_reason'] = ('缺少新契约字段 %s；v0 不从旧契约猜测映射，未接入分析' % ','.join(missing))
        return [], meta

    # split each person's design weight equally across that person's repeats:
    # repeats share weight, never multiply people
    repeats_per_person = defaultdict(int)
    for case in cases:
        repeats_per_person[(case['month'], case['userid'])] += 1

    def base_weight(case):
        for field in ('design_survey_weight', 'survey_weight'):
            value = _num(case.get(field))
            if value is not None and value > 0:
                if meta['weight_field'] is None:
                    meta['weight_field'] = field
                return value
        return None

    records = []
    for case in cases:
        real = case['real']
        profile = case.get('profile') or {}
        n_rep = repeats_per_person[(case['month'], case['userid'])]
        bw = base_weight(case)
        weight = bw / n_rep if bw is not None else None
        pid = '%d|%s' % (case['month'], case['userid'])
        truth_bins = real.get('q9_bins')
        for arm, entry in sorted(case['arms'].items()):
            entry = entry or {}
            record = {
                '_pid': pid,
                'experiment': batch,
                'month': int(case['month']),
                'arm': str(arm),
                'repeat': case.get('repeat'),
                'weight': weight,
                'cell': cell_key(profile),
                'prior_q9_mean': _num(real.get('previous_q9_mean')),
                'truth_q9_mean': _num(real.get('q9_mean')),
                'truth_q9_iqr': _num(real.get('q9_iqr')),
                'truth_q9_bins': truth_bins,
                'truth_q8_point': _num(real.get('q8_point')),
                'truth_zero_deflation': real.get('q9_zero_deflation'),
                'model_q9_mean': _num(entry.get('mean')),
                'model_q9_iqr': _num(entry.get('iqr')),
                'model_q9_bins': entry.get('q9_bins'),
                'model_q8_point': _num(entry.get('point')),
                'model_zero_deflation': entry.get('zero_deflation'),
                'scorer_status': entry.get('scorer_status'),
                'validation_status': entry.get('validation_status'),
                'normalization_applied': entry.get('normalization_applied'),
                'model_shape': shape_features(entry.get('q9_bins')),
                'truth_shape': shape_features(truth_bins),
            }
            for field in PROFILE_FIELDS:
                record[field] = profile.get(field)
            records.append(record)
    meta['n_records'] = len(records)
    meta['status'] = 'ok'
    meta['skip_reason'] = None
    return records, meta


def load_all(outputs_dir):
    """Discover and load every same-contract batch under outputs_dir."""
    all_records, metas = [], []
    for path in discover_case_files(outputs_dir):
        records, meta = load_batch(path)
        metas.append(meta)
        all_records.extend(records)
    return all_records, metas


def public_records(records):
    """Strip internal person linkage keys before writing the private JSON."""
    return [{k: v for k, v in r.items() if not k.startswith('_')} for r in records]
