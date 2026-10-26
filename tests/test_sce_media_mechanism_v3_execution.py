import json

import pytest

from studies.sce_inflation_expectations.experiments.media_mechanism_v3_execution import missing_job_indices


def manifest(folder, run_ids):
    (folder / "manifest.json").write_text(json.dumps({"jobs": [{"run_id": run_id} for run_id in run_ids]}))


def test_resume_selects_only_never_started_jobs(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    manifest(package, ["done", "pending"])
    done = tmp_path / "outputs/local_runs/done"
    done.mkdir(parents=True)
    (done / "run_manifest.json").write_text(json.dumps({"status": "completed"}))
    assert missing_job_indices(package, tmp_path) == [1]


def test_resume_blocks_partial_or_unknown_existing_runs(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    manifest(package, ["partial"])
    partial = tmp_path / "outputs/local_runs/partial"
    partial.mkdir(parents=True)
    (partial / "run_manifest.json").write_text(json.dumps({"status": "stopped_partial_no_retry"}))
    with pytest.raises(ValueError, match="partial"):
        missing_job_indices(package, tmp_path)
