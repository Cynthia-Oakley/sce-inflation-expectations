"""Aggregate-only inventory of public SCE characteristics and past coverage.

No model inputs/configuration are modified. Current inflation answers are not
read. Entry-only missing cells are distinguished from missing historical state.
"""
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import zipfile

from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[3]
SOURCES = [ROOT/'data/raw/sce_p_sources/micro_2017_2019.xlsx',
           ROOT/'data/raw/sce_audit_20260928/micro_2020_2024.xlsx']
LINKS = ROOT/'outputs/sce_information_update_trial_20261014_v2/evaluation_links_private.json'
FIELDS = ['Q32', 'Q33', 'Q34', 'Q36', 'Q37', 'Q38', 'Q41', 'Q42', 'Q43', 'Q43a',
          'Q44', 'Q45b', 'Q46', 'Q47', 'D1', 'D3', 'D6', 'DQ38', 'DSAME', 'Q48',
          'QRA1', 'QRA2', 'Q1', 'Q2', 'Q11', 'Q12new', '_AGE_CAT', '_NUM_CAT',
          '_REGION_CAT', '_EDU_CAT', '_HH_INC_CAT', '_STATE', '_COMMUTING_ZONE']
FIELDS += [f'Q35_{i}' for i in range(1, 7)]
FIELDS += [f'QNUM{i}' for i in (1, 2, 3, 5, 6, 8, 9)]
FIELDS += [f'Q10_{i}' for i in range(1, 11)]
FIELDS += [f'{prefix}_{i}' for prefix in ('Q45new', 'D2new') for i in range(1, 10)]
FIELDS += [f'{prefix}_{i}' for prefix in ('HH2', 'DHH2') for i in range(1, 12)]


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def code(value, low, high):
    n = number(value)
    return int(n) if n is not None and int(n) == n and low <= n <= high else None


def read_rows(path):
    wb = load_workbook(path, read_only=True, data_only=True)
    headers = list(next(wb['Data'].iter_rows(min_row=2, max_row=2, values_only=True)))
    wb.close()
    columns = {get_column_letter(i+1): k for i, k in enumerate(headers)
               if k in {'date', 'userid', *FIELDS}}
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            with archive.open('xl/sharedStrings.xml') as stream:
                for _, element in etree.iterparse(stream, events=('end',), tag='{*}si'):
                    strings.append(''.join(element.itertext()))
                    element.clear()
        with archive.open('xl/worksheets/sheet1.xml') as stream:
            for _, element in etree.iterparse(stream, events=('end',), tag='{*}row'):
                if int(element.get('r')) > 2:
                    row = {}
                    for cell in element:
                        name = columns.get(cell.get('r', '').rstrip('0123456789'))
                        if name:
                            value = cell.find('{*}v')
                            if value is not None and value.text is not None:
                                row[name] = strings[int(value.text)] if cell.get('t') == 's' else value.text
                    if 'date' in row and 'userid' in row:
                        yield row
                element.clear()
                while element.getprevious() is not None:
                    del element.getparent()[0]


def household(row, prefix):
    values = [code(row.get(f'{prefix}_{i}'), 0, 30) for i in range(1, 9)]
    alone = code(row.get(f'{prefix}_9'), 0, 1)
    if any(v is None for v in values) or alone is None:
        return None
    if (alone == 1) != (sum(values) == 0):
        return None
    return {'family_size_excluding_nonrelatives': 1+sum(values[:7]), 'children': values[3]+values[4]}


def latest_income(past):
    latest = None
    for month, row in past:
        value = code(row.get('D6'), 1, 11)
        source = 'D6'
        if value is None:
            value, source = code(row.get('Q47'), 1, 11), 'Q47'
        if value is not None:
            latest = (month, value, source)
    return latest


def family_state(past):
    """D1=change invalidates an old state unless complete D2 updates it."""
    state, source = None, None
    for month, row in past:
        entry = household(row, 'Q45new')
        if entry is not None:
            state, source = entry, 'Q45new'
        if code(row.get('D1'), 1, 2) == 2:
            state, source = household(row, 'D2new'), 'D2new'
    return state, source


def run(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    links = json.loads(LINKS.read_text()); ids = {int(r['userid']) for r in links}
    history = defaultdict(dict); stats = {k: Counter() for k in FIELDS}
    periods = Counter(); total = 0
    for path in SOURCES:
        for row in read_rows(path):
            uid, month = int(row['userid']), int(row['date'])
            if uid in ids:
                if month in history[uid]:
                    raise ValueError('Overlapping person-month sources')
                history[uid][month] = row
            # Exact 2020--2024 scope, rather than trusting the archive filename.
            if 202001 <= month <= 202412:
                total += 1; periods[month] += 1
                for field in FIELDS:
                    if row.get(field) not in (None, ''):
                        stats[field][str(row[field])] += 1
    coverage = Counter(); update_gaps = Counter()
    for link in links:
        past = [(m, r) for m, r in sorted(history[int(link['userid'])].items()) if m < int(link['month'])]
        for key, low, high in [('Q33', 1, 2), ('Q34', 1, 2), ('Q36', 1, 9), ('Q45b', 1, 5),
                                ('QRA1', 1, 7), ('QRA2', 1, 7), ('Q46', 1, 5)]:
            coverage[key] += int(any(code(r.get(key), low, high) is not None for _, r in past))
        old = [(m, code(r.get('Q47'), 1, 11)) for m, r in past if code(r.get('Q47'), 1, 11) is not None]
        new = latest_income(past)
        if new is not None:
            coverage['fine_income_Q47_or_D6'] += 1
            update_gaps['latest_income_from_'+new[2]] += 1
            if old and new[0] > old[-1][0]:
                update_gaps['income_more_recent_than_entry'] += 1
                update_gaps['income_code_differs_from_entry'] += int(new[1] != old[-1][1])
        fs, source = family_state(past)
        coverage['family_state_Q45_or_D2'] += int(fs is not None)
        update_gaps['family_final_source_'+str(source)] += 1
        update_gaps['prior_household_change_flag'] += int(any(code(r.get('D1'), 1, 2) == 2 for _, r in past))
        update_gaps['prior_job_change_flag'] += int(any(code(r.get('DSAME'), 1, 4) in (3, 4) for _, r in past))
    summary = {'status': 'completed_local_inventory_no_input_change', 'new_api_calls': 0,
        'raw_scope': '2020-01 through 2024-12, explicit date filter', 'rows': total,
        'month_count': len(periods), 'selected_person_months': len(links),
        'field_nonempty_rows': {k: sum(v.values()) for k, v in stats.items()},
        'selected_fields_observed_codes': {k: dict(stats[k]) for k in ('Q33', 'Q34', 'Q36', 'Q45b', 'QRA1', 'QRA2', 'D6', 'D1')},
        'strictly_previous_own_coverage': dict(coverage), 'existing_candidate_update_gaps': dict(update_gaps),
        'limits': ['Nonempty rows are not person-level coverage: entry-only fields require within-person history.',
            'QRA questionnaire text says 1--7 but the displayed scale lists 1--5; retain raw codes, validate before mapping.',
            'D6 is trailing-12-month income band, not exact current monthly earnings or a pure earnings shock.',
            'This inventory is retrospective A-line; it does not establish B-line publication availability.',
            'No gender/race/health/risk/fine-education fields have been added to a provider or sent externally.'],
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [*SOURCES, LINKS, ROOT/'data/raw/sce_audit_20260928/questionnaire.pdf', Path(__file__).resolve()]}}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary
