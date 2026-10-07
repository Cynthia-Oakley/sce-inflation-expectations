"""Deterministic extraction of aggregate employment/income archive tables.

Fail closed on unexpected columns; no LLM transcription or current API series.
"""
import re
from html.parser import HTMLParser
from datetime import datetime
from zoneinfo import ZoneInfo

from .macro_population import month_shift

NUMBER = re.compile(r"(?<![\w])[-−]?\d[\d,]*\.\d+")


class ArchiveHTML(HTMLParser):
    """Small standard-library parser for archive anchors and table cells."""
    def __init__(self):
        super().__init__(); self.links = []; self.tables = []; self.text = []
        self.link = None; self.table = None; self.cell = None; self.caption = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a': self.link = [attrs.get('href', ''), []]
        if tag == 'table': self.table = {'title': [], 'rows': []}
        if self.table is not None:
            if tag == 'caption': self.caption = True
            if tag == 'tr': self.table['rows'].append([])
            if tag in ('td', 'th'): self.cell = []

    def handle_data(self, text):
        self.text.append(text)
        if self.link is not None: self.link[1].append(text)
        if self.caption and self.table is not None: self.table['title'].append(text)
        if self.cell is not None: self.cell.append(text)

    def handle_endtag(self, tag):
        if tag == 'a' and self.link is not None:
            self.links.append((self.link[0], ' '.join(self.link[1]))); self.link = None
        if tag == 'caption': self.caption = False
        if tag in ('th', 'td') and self.cell is not None:
            if self.table is not None and self.table['rows']:
                self.table['rows'][-1].append(' '.join(self.cell).strip())
            self.cell = None
        if tag == 'table' and self.table is not None:
            self.tables.append(self.table); self.table = None


def numbers(text):
    text = re.sub(r'(?<=\d),\s+(?=\d{3}\b)', ',', text)
    return [float(x.replace(',', '').replace('−', '-')) for x in NUMBER.findall(text)]


def table_line(text, label, width, *, allow_missing=False):
    match = re.search(r'^' + re.escape(label) + r'\b([^\n]*(?:\n[^\n]*)?)', text, re.M)
    if not match:
        raise ValueError(f'missing row {label}')
    # PDF rows normally occupy one line. Permit one numeric continuation only.
    first, *following = match.group(0).splitlines()
    vals = numbers(first)
    if allow_missing:
        vals = [None if token in ('–', '—') else float(token.replace(',', '').replace('−', '-'))
                for token in re.findall(r'[-−]?\d[\d,]*\.\d+|[–—]', first[len(label):])]
    if len(vals) < width and following and not re.search(r'[A-Za-z]', following[0]):
        vals += numbers(following[0])
    if len(vals) != width:
        raise ValueError(f'{label}: expected {width} columns, found {len(vals)}')
    return vals, first


def employment_pdf(pages, reference_period):
    """A-1 TOTAL, final SA column; B-3 total private, four SA columns."""
    a = [(i, t) for i, t in enumerate(pages, 1)
         if 'Table A-1.' in t and 'Participation rate' in t]
    b = [(i, t) for i, t in enumerate(pages, 1)
         if 'Table B-3.' in t and 'Total private' in t]
    if len(a) != 1 or len(b) != 1:
        raise ValueError('ambiguous/missing A-1 or B-3 table')
    if 'Not seasonally adjusted' not in a[0][1] or 'Seasonally adjusted' not in a[0][1]:
        raise ValueError('A-1 seasonal adjustment header missing')
    if 'seasonally adjusted' not in b[0][1].lower():
        raise ValueError('B-3 seasonal adjustment header missing')
    result = []
    for label, series in [('Participation rate', 'LNS11300000'),
                          ('Employment-population ratio', 'LNS12300000'),
                          ('Unemployment rate', 'LNS14000000')]:
        vals, quote = table_line(a[0][1], label, 9, allow_missing=True)
        if vals[-1] is None or not 0 <= vals[-1] <= 100:
            raise ValueError('invalid CPS percentage')
        result.append(dict(series=series, reference_period=reference_period,
                           value=vals[-1], unit='percent', page=a[0][0], quote=quote,
                           column='A-1 TOTAL final seasonally adjusted column'))
    vals, quote = table_line(b[0][1], 'Total private', 8)
    if not 5 < vals[3] < 100 or not 100 < vals[7] < 5000:
        raise ValueError('invalid earnings units/columns')
    ref = int(reference_period.replace('-', ''))
    # Explicit table order: year ago, two months ago, prior month, target.
    for j, offset in enumerate([-12, -2, -1, 0]):
        observed = month_shift(ref, offset)
        for series, col, unit in [('CES0500000003', j, 'USD per hour'),
                                  ('CES0500000011', j + 4, 'USD per week')]:
            result.append(dict(series=series, reference_period=f'{observed//100}-{observed%100:02d}',
                               value=vals[col], unit=unit, page=b[0][0], quote=quote,
                               column=f'B-3 Total private column {col + 1}',
                               estimate_status='initial' if offset == 0 else 'previous_period_in_release'))
    return result


def check_employment_summary(pages, rows):
    """Check different PDF table layouts against each other, without HTML access."""
    a = [t for t in pages if 'Summary table A.' in t and re.search(r'^Participation rate', t, re.M)]
    b = [t for t in pages if 'Summary table B.' in t and re.search(r'^Average weekly earnings', t, re.M)]
    if len(a) > 1 or len(b) != 1:
        raise ValueError('summary tables unavailable/ambiguous')
    expected = {}
    for label, series in [('Participation rate', 'LNS11300000'), ('Employment-population ratio', 'LNS12300000')]:
        if a:
            values, _ = table_line(a[0], label, 5, allow_missing=True)
            expected[(series, None)] = values[-2]  # last cell is change, not level
        else:
            # April 2023 official PDF omits summary A; cover text states both levels.
            label_text = 'labor force participation rate' if series == 'LNS11300000' else 'employment-population ratio'
            matches = re.findall(re.escape(label_text) + r',\s+at\s+(\d+\.\d+)\s+percent', '\n'.join(pages[:3]), re.I)
            if len(matches) != 1:
                raise ValueError('no independent cover-text check for missing summary A')
            expected[(series, None)] = float(matches[0])
    for label, series in [('Average hourly earnings', 'CES0500000003'), ('Average weekly earnings', 'CES0500000011')]:
        values, _ = table_line(b[0], label, 4)
        prior = [r for r in rows if r['series'] == series]
        if [r['value'] for r in prior] != values:
            raise ValueError('B-3 differs from summary earnings table')
    for row in rows:
        key = (row['series'], None)
        if key in expected and abs(row['value']-expected[key]) > 1e-8:
            raise ValueError('A-1 differs from summary population table')
    return {'cps_check': 'summary table A' if a else 'cover narrative (summary A absent)',
            'earnings_check': 'summary table B'}


def employment_html(html):
    """Independent HTML cell parser (no PDF regex or column-count reuse)."""
    soup = ArchiveHTML(); soup.feed(html)
    result = {}
    for table in soup.tables:
        title = ' '.join(table['title'])
        if 'Table A-1.' in title:
            for label, series in [('Participation rate', 'LNS11300000'),
                                  ('Employment-population ratio', 'LNS12300000'),
                                  ('Unemployment rate', 'LNS14000000')]:
                for cells in table['rows']:
                    if cells and cells[0].rstrip('.') == label:
                        numeric = [c.replace(',', '').replace('$', '') for c in cells[1:]]
                        result[series] = float(numeric[-1])
                        break
        if 'Table B-3.' in title:
            for cells in table['rows']:
                if cells and cells[0].rstrip('.') == 'Total private':
                    numeric = [float(c.replace(',', '').replace('$', '')) for c in cells[1:]]
                    if len(numeric) != 8:
                        raise ValueError('HTML B-3 columns changed')
                    result['CES0500000003'] = numeric[3]
                    result['CES0500000011'] = numeric[7]
                    break
    if len(result) != 5:
        raise ValueError(f'HTML target cells missing: {result.keys()}')
    return result


def bea_pdf(pages, reference_period):
    """Table 1 monthly SAAR nominal levels, with the archive's own release date."""
    header = pages[0]
    m = re.search(r'([A-Z]+)\s+(\d{1,2}),\s+(20\d{2})', header, re.I)
    release_time = re.search(r'RELEASE\s+AT\s+(\d{1,2}):(\d{2})', header, re.I)
    if not m or not release_time:
        raise ValueError('BEA embargo timestamp not recognized')
    date = datetime.strptime(' '.join(m.groups()), '%B %d %Y').replace(
        hour=int(release_time[1]), minute=int(release_time[2]), tzinfo=ZoneInfo('America/New_York'))
    tables = [(i, t) for i, t in enumerate(pages, 1)
              if 'Table 1.' in t and 'Wages and salaries' in t and 'Personal income' in t]
    if len(tables) != 1:
        raise ValueError('BEA monthly table 1 missing/ambiguous')
    page, text = tables[0]
    ref = int(reference_period.replace('-', ''))
    result = []
    for label, series in [('Personal income', 'BEA_PERSONAL_INCOME'),
                          ('Wages and salaries', 'BEA_WAGES_SALARIES')]:
        match = re.search(r'^\s*\d+\s+' + label + r'[^\n]*', text, re.M)
        if not match:
            raise ValueError(f'BEA missing {label}')
        vals = numbers(match.group())
        if not 5 <= len(vals) <= 14 or any(v <= 0 for v in vals):
            raise ValueError(f'BEA table width/units changed: {len(vals)}')
        for j, value in enumerate(vals):
            observed = month_shift(ref, j - len(vals) + 1)
            result.append(dict(series=series, reference_period=f'{observed//100}-{observed%100:02d}',
                               value=value, unit='billion USD SAAR', page=page,
                               quote=match.group(), published_at=date.isoformat(),
                               column=f'Table 1 monthly column {j + 1}',
                               estimate_status='initial' if j == len(vals)-1 else 'previous_period_in_release'))
    return result


def bea_xlsx(path):
    """Independent Excel amounts from BEA's explicitly monthly Table 1."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True, read_only=True)
    if 'Table 1' not in wb.sheetnames:
        raise ValueError('BEA XLSX Table 1 absent')
    result = {}
    for row in wb['Table 1'].iter_rows(values_only=True):
        for label, series in [('Personal income', 'BEA_PERSONAL_INCOME'), ('Wages and salaries', 'BEA_WAGES_SALARIES')]:
            matches = [i for i, cell in enumerate(row) if isinstance(cell, str) and cell.strip() == label]
            if matches:
                vals = [float(cell) for cell in row[matches[0]+1:] if isinstance(cell, (int, float))]
                if not 5 <= len(vals) <= 14:
                    raise ValueError('unexpected XLSX monthly width')
                result[series] = vals
    wb.close()
    if len(result) != 2:
        raise ValueError('BEA XLSX income rows absent')
    return result
