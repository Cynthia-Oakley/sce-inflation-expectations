"""Select documented versions without letting post-cutoff revisions enter B."""
from copy import deepcopy
from datetime import datetime
import math


def timestamp(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError('timestamp requires timezone')
    return stamp


def select_vintages(records, cutoff, *, policy='as_of_latest'):
    """Return one available version per measure/unit/reference period.

    Coverage is only as complete as the supplied archive. Selecting the latest
    stored version does NOT certify that every historical revision was collected.
    Retrospective latest data intentionally have no implicit B-line option.
    """
    if policy not in ('as_of_latest', 'first_release'):
        raise ValueError('unsupported B vintage policy')
    asof = timestamp(cutoff)
    groups = {}
    for row in records:
        pub = timestamp(row['published_at'])
        if not row.get('source_version') or not row.get('source_url'):
            raise ValueError('version and source evidence required')
        if not math.isfinite(float(row['value'])):
            raise ValueError('nonfinite input')
        if policy == 'first_release':
            if row.get('vintage_kind') not in ('initial_release', 'revision'):
                raise ValueError('first-release policy requires explicit version kind')
            if row['vintage_kind'] != 'initial_release':
                continue
        if pub > asof:
            continue
        key = (row['measure'], row['unit'], row['reference_period'])
        versions = groups.setdefault(key, {})
        if pub in versions and float(versions[pub]['value']) != float(row['value']):
            raise ValueError('conflicting values with indistinguishable publication time')
        versions.setdefault(pub, row)
    selected = []
    for key, versions in sorted(groups.items()):
        pub = (max if policy == 'as_of_latest' else min)(versions)
        selected.append(deepcopy(versions[pub]))
    return selected
