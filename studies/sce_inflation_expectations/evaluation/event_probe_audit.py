"""Offline admission audit of the twelve authorized Event MCP responses."""
from datetime import datetime


def audit_payload(source, payload, as_of):
    """Tool success, content coverage and historical admission are separate."""
    row = {'source': source, 'tool_status': payload.get('status'),
           'target_date': payload.get('target_date'), 'as_of': as_of,
           'from_cache': payload.get('from_cache'), 'fetched_at': payload.get('fetched_at'),
           'automatic_environment_admission': False, 'issues': []}
    if payload.get('status') != 'ok':
        return {**row, 'classification': 'source_error_no_retry', 'issues': ['Provider returned an error, not an observed zero.']}
    d = payload.get('data', {})
    if source == 'google_trends':
        row.update(keyword_count=len(d.get('keywords', [])), returned_keyword_count=len(d.get('trends', {})),
                   upstream_error_count=len(d.get('errors', [])), timeframe=d.get('timeframe'))
        if not d.get('trends'):
            return {**row, 'classification': 'empty_payload_despite_tool_ok',
                    'issues': ['No observations; cached upstream errors do not mean search interest was zero.']}
        return {**row, 'classification': 'full_month_aggregate_not_cutoff_safe',
                'issues': ['Only whole-month summary, no daily sequence to truncate.',
                           'Normalization window includes dates after the experiment cutoff; current retrieval is not a historical vintage.']}
    if source == 'household_pulse':
        row.update(survey_year=d.get('survey_year'), available_measures=d.get('available_measures'),
                   national_summary=d.get('national_summary'))
        return {**row, 'classification': 'unverified_period_and_aggregation',
                'issues': ['Survey year differs from requested monthly target; no cycle, collection dates or release version.',
                           'State-count rollup lacks universe/denominator/weighting provenance; not an identified national or individual rate.']}
    if source == 'fred':
        row['snapshot'] = d.get('snapshot', {})
        row['requested_series_only'] = set(row['snapshot']) == {'UMCSENT'}
        return {**row, 'classification': 'snapshot_missing_release_and_vintage',
                'issues': ['No original publication date or preliminary/final version in MCP response.',
                           'Requested observation month is not proof that its value was available by as_of.']}
    if source == 'ustr':
        records = []
        cutoff_date = datetime.fromisoformat(as_of).date()
        for item in d.get('ustr_examples', []):
            value = {k: item[k] for k in ('title', 'url', 'date') if k in item}
            try:
                date = datetime.fromisoformat(item['date']).date()
                value['date_screen'] = 'dated_candidate_requires_primary_page' if date <= cutoff_date else 'after_cutoff'
            except (KeyError, TypeError, ValueError):
                value['date_screen'] = 'undated_or_non_event_page'
            records.append(value)
        row.update(reported_trade_count=d.get('ustr_trade_event_count'), reported_tariff_count=d.get('ustr_tariff_event_count'),
                   examples=records)
        if not records:
            return {**row, 'classification': 'empty_count_without_archive_coverage',
                    'issues': ['Zero returned examples is not verified absence of historical trade events.']}
        return {**row, 'classification': 'mixed_events_require_item_level_screening',
                'issues': ['Examples mix dated releases, later reports and undated navigation/report pages.',
                           'No historical coverage or counting rule, so reported counts are not admitted as economic indicators.']}
    raise ValueError('Unexpected source')
