"""Offline checks for accidental spending, changed scope and overwrites."""
import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations import platform_survey_pilot as pilot


def fixture_folder(tmp_path):
    request = {"platform_id": "nemotron_usa", "user_count": 10, "allow_virtual_users": False}
    pilot.write_new(tmp_path / "request.json", request)
    protocol = {"request_sha256": pilot.sha(tmp_path / "request.json"),
        "tool": pilot.TOOL, "destination_host": pilot.HOST, "user_count": 10,
        "budget_cap_usd": "0.10", "unit_price_usd_email": "0.004",
        "automatic_retries": 0, "request_count": 1,
        "code_sha256": pilot.sha(Path(pilot.__file__))}
    pilot.write_new(tmp_path / "protocol.json", protocol)
    return tmp_path


def approve(folder, cap="0.10"):
    pilot.write_new(folder / "authorization.json", {"approved": True,
        "protocol_sha256": pilot.sha(folder / "protocol.json"),
        "cap_usd": cap, "user_confirmation": "offline test fixture only"})


def test_no_approval_cannot_reach_network(tmp_path):
    with pytest.raises(FileNotFoundError):
        pilot.execute(fixture_folder(tmp_path))
    assert not (tmp_path / "execution_started.json").exists()


def test_approved_exact_scope(tmp_path):
    folder = fixture_folder(tmp_path)
    approve(folder)
    protocol, request = pilot.validate_approval(folder)
    assert request["user_count"] == 10
    assert protocol["request_count"] == 1


def test_changed_request_rejected(tmp_path):
    folder = fixture_folder(tmp_path)
    approve(folder)
    request = json.loads((folder / "request.json").read_text())
    request["user_count"] = 100
    (folder / "request.json").write_text(json.dumps(request))
    with pytest.raises(ValueError, match="mismatch"):
        pilot.validate_approval(folder)


def test_insufficient_cap_rejected(tmp_path):
    folder = fixture_folder(tmp_path)
    approve(folder, cap="0.02")
    with pytest.raises(ValueError, match="budget mismatch"):
        pilot.validate_approval(folder)


def test_long_jsonl_not_truncated_and_marker_not_overwritten(tmp_path):
    raw = {"content": [{"type": "text", "text": '{"answer":"' + "a" * 9000 + '"}'}]}
    path = tmp_path / "raw_response.json"
    pilot.write_new(path, raw)
    assert json.loads(path.read_text()) == raw
    with pytest.raises(FileExistsError):
        pilot.write_new(path, {})


def test_bin_order_reuses_reference():
    labels = pilot.bin_labels()
    assert len(labels) == 10
    assert labels[0] == "12% or more"
    assert "deflation" in labels[-1]


def test_application_error_is_not_success_when_outer_flag_false():
    raw = {"isError": False, "content": [{"type": "text", "text": json.dumps({
        "status": "error", "message": "questionnaire options invalid"})}]}
    assert pilot.classify_response(raw) == "application_error_no_retry"


def test_native_reserves_prior_attempt_against_same_cap(tmp_path):
    folder = fixture_folder(tmp_path)
    request = json.loads((folder / "request.json").read_text())
    request["user_count"] = 1
    (folder / "request.json").write_text(json.dumps(request))
    p = json.loads((folder / "protocol.json").read_text())
    p.update(probe_variant="native_q9_options", user_count=1,
             request_sha256=pilot.sha(folder / "request.json"), prior_reserved_usd_email="0.099")
    (folder / "protocol.json").write_text(json.dumps(p))
    approve(folder)
    with pytest.raises(ValueError, match="budget mismatch"):
        pilot.validate_approval(folder)
