"""Select each series' available observations separately, retaining real dates."""
from copy import deepcopy
from datetime import datetime
import math

HISTORY_MEASURES = {
    'CPI-U all items 12-month percent change, not seasonally adjusted',
    'Civilian unemployment rate, seasonally adjusted',
    'CPI-U food 12-month percent change, not seasonally adjusted',
    'CPI-U energy 12-month percent change, not seasonally adjusted',
    'CPI-U shelter 12-month percent change, not seasonally adjusted',
    'U.S. regular all formulations retail gasoline price, monthly mean of weekly observations',
}


def select_available(records, cutoff, history_measures=HISTORY_MEASURES):
    stamp = datetime.fromisoformat(cutoff)
    if stamp.tzinfo is None:
        raise ValueError('cutoff requires timezone')
    groups, seen = {}, set()
    for row in records:
        when = datetime.fromisoformat(row['published_at'])
        if when.tzinfo is None:
            raise ValueError('publication timestamp requires timezone')
        if not math.isfinite(float(row['value'])):
            raise ValueError('nonfinite input')
        if when > stamp:
            continue
        if row['eligibility'] not in ('eligible', 'vintage_unverified'):
            raise ValueError('unknown input eligibility')
        key = (row['measure'], row['unit'], row['reference_period'])
        if key in seen:
            raise ValueError('duplicate observation')
        seen.add(key)
        groups.setdefault((row['measure'],row['unit']),[]).append(row)
    chosen, notes = [], []
    for (measure, _unit), rows in sorted(groups.items()):
        rows.sort(key=lambda r:r['reference_period'])
        selected = rows[-12:] if measure in history_measures else rows[-1:]
        for i,row in enumerate(selected):
            result=deepcopy(row)
            result['role']='latest_release' if i==len(selected)-1 else 'history'
            chosen.append(result)
        notes.append({'measure':measure,'latest_reference_period':selected[-1]['reference_period'],
                      'latest_published_at':selected[-1]['published_at'],
                      'history_reference_periods':[r['reference_period'] for r in selected[:-1]],
                      'observations':len(selected)})
    if not chosen:
        raise ValueError('no available observations')
    return chosen, notes
