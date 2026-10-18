from studies.sce_inflation_expectations.evaluation.event_probe_audit import audit_payload


def test_tool_ok_with_empty_trends_is_not_observed_zero():
    result = audit_payload('google_trends', {'status':'ok','data':{'trends':{},'errors':['429']}}, '2025-03-12T23:59:59-04:00')
    assert result['classification'] == 'empty_payload_despite_tool_ok'
    assert result['automatic_environment_admission'] is False


def test_monthly_tariff_result_does_not_admit_future_or_undated_pages():
    result = audit_payload('ustr', {'status':'ok','data':{'ustr_examples':[
        {'date':'2025-03-31','title':'report'}, {'date':'2025-03-03','title':'agenda'}, {'title':'leadership'}]}}, '2025-03-12T23:59:59-04:00')
    assert [r['date_screen'] for r in result['examples']] == ['after_cutoff','dated_candidate_requires_primary_page','undated_or_non_event_page']


def test_fred_snapshot_has_no_implicit_vintage():
    result = audit_payload('fred', {'status':'ok','data':{'snapshot':{'UMCSENT':57.}}}, '2025-03-12T23:59:59-04:00')
    assert result['classification'] == 'snapshot_missing_release_and_vintage'
    assert result['requested_series_only'] is True
