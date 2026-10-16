"""Strict, identifier-free Q1 inputs for an A-line household-finance contrast.

Q1 compares household finances with twelve months earlier. Two adjacent survey
answers are two rolling annual comparisons, not an identified monthly shock.
Only the validated categories are rendered; cache provenance stays out of text.
"""
import re

ARMS = ('baseline', 'financial_facts', 'financial_perspective')
SCHEMA_VERSION = 'sce_household_finance_input_v1'
RESEARCH_LINE = 'A_conditional_returner_reconstruction'
RECORD_FIELDS = frozenset((
    'schema_version', 'research_line', 'target_month',
    'current_q1_code', 'current_q1_source_month', 'current_source_sha256',
    'previous_q1_code', 'previous_q1_source_month', 'previous_source_sha256',
))
Q1_TEXT = {
    1: 'much worse', 2: 'somewhat worse', 3: 'about the same',
    4: 'somewhat better', 5: 'much better',
}
PERSPECTIVE_SENTENCE = (
    "Consider the economic information from your household's point of view, "
    "including the financial experiences it brings to mind, alongside your earlier inflation belief."
)


def _month(value):
    if type(value) is not int or not 190001 <= value <= 219912 or not 1 <= value % 100 <= 12:
        raise ValueError('Month must be an integer YYYYMM')
    return value


def previous_month(month):
    """Return the immediately preceding calendar month."""
    month = _month(month)
    return month - 1 if month % 100 != 1 else (month // 100 - 1) * 100 + 12


def validate_household_finance_record(record):
    """Reject extra fields, noninteger codes and incorrect source months."""
    if not isinstance(record, dict) or set(record) != RECORD_FIELDS:
        raise ValueError('Household-finance record whitelist mismatch')
    if record['schema_version'] != SCHEMA_VERSION or record['research_line'] != RESEARCH_LINE:
        raise ValueError('Household-finance schema/research line mismatch')
    target = _month(record['target_month'])
    for period, expected_month in (('current', target), ('previous', previous_month(target))):
        code = record[f'{period}_q1_code']
        source_month = record[f'{period}_q1_source_month']
        source_sha256 = record[f'{period}_source_sha256']
        if code is None:
            if source_month is not None or source_sha256 is not None:
                raise ValueError('Missing Q1 must have missing source month and hash')
            continue
        if type(code) is not int or code not in Q1_TEXT:
            raise ValueError('Q1 code must be an integer from 1 to 5 or None')
        if _month(source_month) != expected_month:
            raise ValueError('Q1 source month must be the target or strictly previous calendar month')
        if not isinstance(source_sha256, str) or re.fullmatch(r'[0-9a-f]{64}', source_sha256) is None:
            raise ValueError('Q1 source sha256 required')
    return record


def render_household_finance_block(arm, record):
    """Render facts, optionally followed by the prespecified perspective cue."""
    if arm not in ARMS:
        raise ValueError('Unknown household-finance arm')
    validate_household_finance_record(record)
    if arm == 'baseline':
        return ''
    lines = ['Your household financial circumstances:']
    for period, verb in (('previous', 'described'), ('current', 'describe')):
        code = record[f'{period}_q1_code']
        if code is None:
            lines.append(f'- In the {period} survey month, your household financial circumstances compared with 12 months earlier are unknown.')
        else:
            lines.append(f"- In the {period} survey month, you {verb} your household's finances as {Q1_TEXT[code]} as 12 months earlier."
                         if code == 3 else
                         f"- In the {period} survey month, you {verb} your household's finances as {Q1_TEXT[code]} than 12 months earlier.")
    if arm == 'financial_perspective':
        lines.extend(('', PERSPECTIVE_SENTENCE))
    return '\n'.join(lines) + '\n\n'
