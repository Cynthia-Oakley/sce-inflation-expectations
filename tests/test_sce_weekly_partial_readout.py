"""Independent expectations for incomplete-month selection."""
import pytest
from studies.sce_inflation_expectations.experiments.weekly_partial_readout import completed_primary_points, normalized_point


def test_actual_compact_execution_schema_is_normalized_without_mutation():
    point=dict(step_key='w20251107',month='202511',cutoff='2025-11-07T23:59:59-05:00',
               cycle_key='2025-09|2025-10-07',anchor_reference_period='2025-09')
    normalized=normalized_point(point)
    assert normalized['target_reference_period']=='2025-11'
    assert normalized['anchor_published_date']=='2025-10-07'
    assert 'target_reference_period' not in point


def test_conflicting_month_is_rejected():
    with pytest.raises(ValueError,match='Execution month'):
        normalized_point(dict(month='202512',cutoff='2025-11-07T23:59:59-05:00',
                              cycle_key='2025-09|2025-10-07',anchor_reference_period='2025-09'))


def test_incomplete_month_is_not_promoted_to_primary():
    plan=[dict(step_key=k,cutoff=k,target_reference_period=m) for k,m in
          [('w20260619','2026-06'),('w20260626','2026-06'),('w20260703','2026-07'),('w20260710','2026-07')]]
    assert [p['step_key'] for p in completed_primary_points(plan,{'w20260619','w20260626','w20260703'})]==['w20260626']


def test_month_with_internal_missing_checkpoint_is_excluded():
    plan=[dict(step_key=k,cutoff=k,target_reference_period='2026-06')
          for k in ('w20260605','w20260612','w20260619','w20260626')]
    assert completed_primary_points(plan,{'w20260605','w20260619','w20260626'})==[]


def test_complete_month_uses_last_scheduled_point():
    plan=[dict(step_key=k,cutoff=k,target_reference_period='2026-06') for k in ('w20260626','w20260605')]
    assert completed_primary_points(plan,{p['step_key'] for p in plan})==[plan[0]]


def test_final_adapter_restores_reader_after_rejection(monkeypatch,tmp_path):
    import importlib.util
    from pathlib import Path
    script=Path(__file__).resolve().parents[1]/'scripts/evaluate_sce_weekly_compat.py'
    spec=importlib.util.spec_from_file_location('weekly_compat_test',script)
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    monkeypatch.setattr(adapter,'checked',lambda _:({'inputs':'outputs/fixture'},{}))
    original=adapter.ev.read_json
    def reject(_):raise ValueError('Actual complete 47-week model generation required')
    monkeypatch.setattr(adapter.ev,'evaluate',reject)
    with pytest.raises(ValueError,match='Actual complete'):
        adapter.evaluate_compatible(tmp_path)
    assert adapter.ev.read_json is original
    assert list(tmp_path.iterdir())==[]
