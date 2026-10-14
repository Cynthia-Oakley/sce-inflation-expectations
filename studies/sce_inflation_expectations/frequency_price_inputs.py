"""Read supported category prices from locally archived initial BLS CPI Table 2."""
from datetime import datetime
from pathlib import Path
import re

from pypdf import PdfReader
from .diary_experience import file_sha256

ROOT = Path(__file__).resolve().parents[2]
LABELS = {'food_at_home': 'Food at home', 'food_away_from_home': 'Food away from home',
          'household_cleaning_paper': 'Housekeeping supplies',
          'personal_care_products': 'Personal care products'}
MONTHS = ('January', 'February', 'March', 'April', 'May', 'June',
          'July', 'August', 'September', 'October', 'November', 'December')


def parse_row(line, label):
    text = re.sub(r'\s+', ' ', line).strip()
    pattern = '^' + re.escape(label) + r'(?:\s*\d+(?:,\s*\d+)*)?\s*\.(?:\s*\.){2,}\s*(.*)$'
    match = re.match(pattern, text)
    if not match: return None
    values = re.findall(r'[-+]?(?:\d+\.\d+|\d+|\.\d+)', match.group(1))
    if len(values) != 6: raise ValueError('unexpected Table 2 numeric columns: ' + text)
    return {'relative_importance': float(values[0]), 'yoy_nsa_pct': float(values[1]),
            'mom_nsa_pct': float(values[2]), 'last_adjusted_or_footnoted_month_pct': float(values[5]),
            'quote': text, 'table': 'Table 2, detailed expenditure categories',
            'column_definition': 'relative importance, 12-month NSA, 1-month NSA, three monthly SA or footnoted NSA columns'}


def extract_prices(environment):
    args = environment['provider_args']; signals = args['signals_by_step']['0']; target = args['targets'][0]
    latest = next(r for r in signals if r['signal_id'].startswith('bls_cpi_u_all_items_yoy') and r['role'] != 'history')
    reference = latest['reference_period']; paths = list((ROOT / 'data/raw/bls_initial_releases' / reference).glob('cpi*.pdf'))
    if len(paths) != 1: raise ValueError('unique cached initial release required')
    path = paths[0]; reader = PdfReader(path); release_text = re.sub(r'\s+', ' ', reader.pages[0].extract_text()).strip()
    if latest['source_version'] not in release_text: raise ValueError('release identifier not found on PDF cover')
    published = datetime.fromisoformat(latest['published_at']); cutoff = datetime.fromisoformat(target['as_of'])
    if published.tzinfo is None or published > cutoff: raise ValueError('future/naive category release')
    if published.date().isoformat().replace('-', '_') not in path.name: raise ValueError('filename publication mismatch')
    refyear, refmonth = map(int, reference.split('-')); expected_header = MONTHS[refmonth-1] + ' ' + str(refyear)
    found = {}; active = False; header_page = None
    required = {**LABELS, 'all_items_check': 'All items'}
    for number, page in enumerate(reader.pages, 1):
        layout = page.extract_text(extraction_mode='layout'); collapsed = re.sub(r'\s+', ' ', layout)
        if re.search(r'Table\s+2\.', collapsed):
            if expected_header not in collapsed or 'Unadjusted percent' not in collapsed:
                raise ValueError('Table 2 reference period/NSA header mismatch')
            active = True; header_page = header_page or number
        elif re.search(r'Table\s+3\.', collapsed): break
        if not active: continue
        for line in layout.splitlines():
            for key, label in required.items():
                row = parse_row(line, label)
                if row is not None:
                    if key in found: raise ValueError('duplicate category in Table 2')
                    found[key] = {**row, 'pdf_page': number, 'category_label': label}
    if set(found) != set(required): raise ValueError('missing detailed category: ' + str(set(required)-set(found)))
    if abs(found['all_items_check']['yoy_nsa_pct'] - float(latest['value'])) > 1e-8:
        raise ValueError('Table 2 annual column does not match old headline signal')
    food = next(r for r in signals if r['signal_id'].startswith('bls_cpi_food_at_home_yoy') and r['role'] != 'history')
    if abs(found['food_at_home']['yoy_nsa_pct'] - float(food['value'])) > 1e-8:
        raise ValueError('food annual column does not match old visible signal')
    return {'target_month': target['target_month'], 'as_of': target['as_of'],
            'reference_period': reference, 'published_at': latest['published_at'],
            'source_version': latest['source_version'], 'source_url': latest['source_url'],
            'pdf_path': str(path.relative_to(ROOT)), 'pdf_sha256': file_sha256(path),
            'header_page': header_page, 'categories': {k: found[k] for k in LABELS},
            'headline_and_food_annual_checks_passed': True,
            'interpretation': 'National category prices; match to household contact is synthetic, not store-level observed prices'}


def render_prices(bundle):
    rows = [f"Additional category prices from the same BLS CPI release ({bundle['published_at'][:10]}, reference {bundle['reference_period']}):",
            '12-month change compares prices with a year earlier. One-month change compares with the preceding month; both are unadjusted and neither is a future forecast.']
    for key, value in bundle['categories'].items():
        if key == 'food_at_home':
            rows.append(f"- Groceries for home: use the food-at-home annual change already shown above; one-month unadjusted change {value['mom_nsa_pct']:+.1f}%.")
        else:
            rows.append(f"- {value['category_label']}: 12-month change {value['yoy_nsa_pct']:+.1f}%; one-month unadjusted change {value['mom_nsa_pct']:+.1f}%.")
    return '\n'.join(rows) + '\n\n'
