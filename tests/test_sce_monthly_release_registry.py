from studies.sce_inflation_expectations.evaluation.monthly_release_registry import eligible_release


def test_same_day_release_not_assumed_available_and_latest_past_is_selected():
    rows=[dict(reference_period='2025-08',published_date='2025-09-08'),
          dict(reference_period='2025-09',published_date='2025-10-07'),
          dict(reference_period='2025-10',published_date='2025-11-07')]
    assert eligible_release(rows,'2025-10-07T08:30:00-04:00')['reference_period']=='2025-08'
    assert eligible_release(rows,'2025-10-08T23:59:59-04:00')['reference_period']=='2025-09'
    assert eligible_release(rows,'2025-09-01T00:00:00-04:00') is None
