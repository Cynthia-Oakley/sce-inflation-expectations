import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from studies.sce_inflation_expectations.cognition_runtime import ARMS
from studies.sce_inflation_expectations.evaluation import cognition
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.revision_format_runtime import REPLY_MARKER
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import score_q9_frozen


MONTHS = [202004, 202105, 202111, 202203]
BASE_BINS = [0.0, 0.0, 5.0, 15.0, 30.0, 25.0, 15.0, 7.0, 3.0, 0.0]


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _bins_for_person(person_index):
    bins = list(BASE_BINS)
    shift = float(person_index % 3)
    bins[4] -= shift
    bins[3] += shift
    return bins


def _model_bins(real_bins, arm):
    bins = list(real_bins)
    if arm == "label_only":
        shift = 4.0
    elif arm == "question_answer":
        shift = 2.0
    else:
        shift = 0.5
    bins[4] -= shift
    bins[5] += shift
    return bins


def _reply(point, bins):
    q9 = {f"bin{i}": value for i, value in enumerate(bins, 1)}
    return json.dumps({"point_pct": point, "q9": q9, "reason": "synthetic test answer"})


def _build_trial(root: Path, folder: Path):
    root.mkdir(parents=True)
    (root / "outputs").mkdir()
    run_root = root / "outputs" / "local_runs"
    run_root.mkdir()
    folder.mkdir(parents=True)

    truth_rows = []
    link_rows = []
    ref_rows = []
    source_records = []
    low_parent_n = [12, 11, 11, 15]
    for month_index, month in enumerate(MONTHS):
        for person_index in range(24):
            label = "high" if person_index < 14 else "low"
            agent_id = f"person{person_index:03d}"
            userid = 900000 + person_index
            actual_bins = _bins_for_person(person_index + month_index)
            previous_bins = _bins_for_person(person_index + month_index + 1)
            actual_score = score_q9_frozen(actual_bins)
            previous_score = score_q9_frozen(previous_bins)
            profile = {"numeracy": label}
            low_n = low_parent_n[month_index]
            parent_n = 48 - low_n if label == "high" else low_n
            n_selected = 14 if label == "high" else 10
            sampling_weight = parent_n / n_selected
            raw_weight = 1.0 + person_index / 100.0
            link_rows.append({
                "month": month, "agent_id": agent_id, "userid": userid,
                "profile": profile, "survey_weight": raw_weight * sampling_weight,
                "raw_parent_survey_weight": raw_weight,
                "sampling_weight": sampling_weight,
            })
            ref_rows.append((month, userid, *actual_bins, float(actual_score.mean), float(actual_score.iqr)))
            for repeat in (1, 2):
                truth_rows.append({
                    "month": month, "repeat": repeat, "agent_id": agent_id, "userid": userid,
                    "actual": float(actual_score.mean), "actual_iqr": float(actual_score.iqr),
                    "actual_zero_deflation": float(sum(actual_bins[5:]) == 0),
                    "actual_point": 2.0 + person_index / 100.0,
                    "previous": float(previous_score.mean), "previous_bins": previous_bins,
                    "profile": profile,
                })

    truth_path = root / "outputs" / "truth.json"
    truth_path.write_text(json.dumps(truth_rows), encoding="utf-8")
    reference_path = root / "outputs" / "reference.parquet"
    connection = duckdb.connect()
    column_names = ["date", "userid", *[f"Q9_bin{i}" for i in range(1, 11)], "Q9_mean", "Q9_iqr"]
    sql_columns = ", ".join(f'"{name}" DOUBLE' if name not in ("date", "userid") else f'"{name}" BIGINT'
                             for name in column_names)
    connection.execute(f"CREATE TABLE reference ({sql_columns})")
    placeholders = ",".join("?" for _ in column_names)
    connection.executemany(f"INSERT INTO reference VALUES ({placeholders})", ref_rows)
    escaped_reference = str(reference_path).replace("'", "''")
    connection.execute(f"COPY reference TO '{escaped_reference}' (FORMAT PARQUET)")
    connection.close()

    protocol = {
        "arms": list(ARMS), "months": MONTHS, "n_per_month": 24,
        "generation_repeats": [1, 2], "planned_calls": 576,
        "primary_metric": cognition.PRIMARY_METRIC,
        "primary_contrast": "faithful_paraphrase minus question_answer on individual density-IQR paired MAE",
        "secondary_contrasts": ["question_answer minus label_only", "faithful_paraphrase minus label_only"],
        "stratum_n": {"high": 14, "low": 10},
        "sampling": "Fixed-seed 14 High and 10 Low; Low oversampled for mechanism coverage; no current outcomes used.",
        "bootstrap_seed": 31415,
    }
    protocol_path = folder / "protocol.json"
    protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (folder / "evaluation_links_private.json").write_text(
        json.dumps(link_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for month in MONTHS:
        month_folder = folder / str(month)
        month_folder.mkdir()
        agents = [r for r in link_rows if r["month"] == month]
        baseline_text = (
            "Your earlier survey response was retained as the prior state. "
            "The target is today's future 12-month response.\n"
            + REPLY_MARKER + "\nReturn a JSON answer."
        )
        for arm in ARMS:
            previews = []
            for link in agents:
                content = baseline_text
                if arm != "label_only":
                    block = ("Your earlier survey responses:\nFull question and answer.\n\n"
                             if arm == "question_answer"
                             else "Your earlier survey responses:\nFaithful paraphrase and answer.\n\n")
                    content = baseline_text.replace(REPLY_MARKER, block + REPLY_MARKER, 1)
                messages = [{"role": "user", "content": content}]
                previews.append({"agent_id": link["agent_id"], "messages": messages,
                                 "prompt_sha256": message_hash(messages)})
            (month_folder / f"preview_{arm}.json").write_text(
                json.dumps(previews, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    jobs = []
    for month in MONTHS:
        for arm in ARMS:
            preview_path = folder / str(month) / f"preview_{arm}.json"
            previews = {row["agent_id"]: row for row in json.loads(preview_path.read_text())}
            for repeat in (1, 2):
                run_id = f"synthetic-{month}-{arm}-r{repeat}"
                jobs.append({"month": month, "arm": arm, "repeat": repeat, "run_id": run_id})
                run_dir = run_root / run_id
                run_dir.mkdir()
                run_manifest = {
                    "status": "completed", "llm_kind": "openai", "n": 24,
                    "run_id": run_id, "arm": arm, "month": month, "repeat": repeat,
                    "protocol_sha256": _hash(protocol_path),
                    "cost": {"call_count": 24, "estimated_cost_usd": 0.01},
                }
                (run_dir / "run_manifest.json").write_text(json.dumps(run_manifest), encoding="utf-8")
                calls = []
                connection = duckdb.connect(str(run_dir / "study.duckdb"))
                connection.execute(
                    "CREATE TABLE panel (agent_id VARCHAR, step INTEGER, action_kind VARCHAR, action_payload VARCHAR)"
                )
                for link in [row for row in link_rows if row["month"] == month]:
                    agent_id = link["agent_id"]
                    preview = previews[agent_id]
                    person_index = int(agent_id[-3:])
                    real_bins = _bins_for_person(person_index + MONTHS.index(month))
                    predicted_bins = _model_bins(real_bins, arm)
                    point = round(2.0 + person_index / 100.0 + (0.0 if arm == "question_answer" else .2), 4)
                    raw = _reply(point, predicted_bins)
                    payload = {
                        "cognition_arm": arm,
                        "actual_messages_sha256": preview["prompt_sha256"],
                        "validation_status": "valid", "point_pct": point,
                    }
                    payload.update({f"q9_bin{i}": value for i, value in enumerate(predicted_bins, 1)})
                    connection.execute("INSERT INTO panel VALUES (?, 1, 'sce_answer', ?)",
                                       [agent_id, json.dumps(payload)])
                    prompt_text = json.dumps(preview["messages"], ensure_ascii=False)
                    calls.append({
                        "run_id": run_id, "agent_id": agent_id, "attempt_idx": 0,
                        "target_month": f"{month // 100:04d}-{month % 100:02d}",
                        "prompt_sha256": preview["prompt_sha256"], "prompt_text": prompt_text,
                        "raw_response_text": raw,
                        "raw_response_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                        "error": None,
                    })
                connection.close()
                (run_dir / "llm_calls.jsonl").write_text(
                    "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in calls), encoding="utf-8")

    manifest = {
        "planned_calls": 576,
        "protocol_sha256": _hash(protocol_path),
        "source_sha256": {
            str(truth_path.relative_to(root)): _hash(truth_path),
            str(reference_path.relative_to(root)): _hash(reference_path),
        },
        "prepared_file_sha256": {
            str(path.relative_to(folder)): _hash(path)
            for path in folder.rglob("*.json") if path.name != "manifest.json"
        },
        "jobs": jobs,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8")
    return root, folder


def _patch_one_call_invalid(folder: Path, root: Path):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    job = manifest["jobs"][0]
    run_dir = root / "outputs" / "local_runs" / job["run_id"]
    calls_path = run_dir / "llm_calls.jsonl"
    calls = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines()]
    bins = [0.0] * 10
    invalid_calls = calls[:2]
    for call in invalid_calls:
        parsed = json.loads(call["raw_response_text"])
        parsed["q9"] = {f"bin{i}": 0.0 for i in range(1, 11)}
        raw = json.dumps(parsed)
        call["raw_response_text"] = raw
        call["raw_response_sha256"] = hashlib.sha256(raw.encode()).hexdigest()
    calls_path.write_text("".join(json.dumps(row) + "\n" for row in calls), encoding="utf-8")

    connection = duckdb.connect(str(run_dir / "study.duckdb"))
    for call in invalid_calls:
        parsed = json.loads(call["raw_response_text"])
        old = connection.execute("SELECT action_payload FROM panel WHERE agent_id=?", [call["agent_id"]]).fetchone()[0]
        payload = json.loads(old)
        payload.update({"validation_status": "invalid", "point_pct": parsed["point_pct"]})
        payload.update({f"q9_bin{i}": value for i, value in enumerate(bins, 1)})
        connection.execute("UPDATE panel SET action_payload=? WHERE agent_id=?",
                           [json.dumps(payload), call["agent_id"]])
    connection.close()


@pytest.fixture
def trial(tmp_path, monkeypatch):
    root, folder = _build_trial(tmp_path / "repository", tmp_path / "repository" / "outputs" / "prepared")
    monkeypatch.setattr(cognition, "ROOT", root)
    monkeypatch.setattr(cognition, "TRUTH", root / "outputs" / "truth.json")
    monkeypatch.setattr(cognition, "REFERENCE", root / "outputs" / "reference.parquet")
    return root, folder


def test_load_reconstructs_all_calls_and_checks_scored_ten_bin_truth(trial):
    loaded = cognition.load(trial[1])
    assert loaded["raw_replies_reconstructed_and_matched"] == 576
    assert len(loaded["cases"]) == 192
    assert loaded["scorable_n"] == {arm: 192 for arm in ARMS}
    assert loaded["reference_diagnostics"]["frozen_rescore_matches_pinned_truth_n"] == 96
    assert loaded["reference_diagnostics"]["comparison_tolerance"] == 1e-6
    assert len({row["userid"] for row in loaded["cases"]}) == 24


def test_evaluate_reports_paired_metrics_probabilities_and_auxiliary_weights(trial, tmp_path):
    root, folder = trial
    out = root / "outputs" / "evaluation"
    summary = cognition.evaluate(folder, out, draws=40)
    assert summary["evaluation_api_calls"] == 0
    assert summary["primary_metric"] == cognition.PRIMARY_METRIC
    assert summary["paired_contrasts"]["faithful_paraphrase_minus_question_answer"]["draws_used"] == 40
    assert summary["arms"]["question_answer"]["q9"]["aggregate_equal_month_repeat_cells"]["probability_tv_pct"] == pytest.approx(2.0)
    assert "not inflation percentage points" in summary["metric_units"]["probability_tv_pct"]
    assert "auxiliary_survey_weighted" in summary["arms"]["label_only"]
    assert len(summary["monthly_mean_bin_distributions"]["cells"]) == 8
    assert summary["sampling_design"]["low_numeracy_oversampled"] is True
    assert summary["numeracy_group_descriptions"]["Low"]["descriptive_only"] is True
    assert (out / "cases_private.json").is_file()


def test_one_invalid_action_below_99_percent_disables_effect_intervals(trial, tmp_path):
    root, folder = trial
    _patch_one_call_invalid(folder, root)
    out = root / "outputs" / "low_coverage"
    summary = cognition.evaluate(folder, out, draws=20)
    assert summary["accuracy_is_descriptive_only_due_to_validity_gate"] is True
    assert summary["coverage"][summary["protocol"]["arms"][0]]["valid_fraction"] == pytest.approx(190 / 192)
    contrast = summary["paired_contrasts"]["faithful_paraphrase_minus_question_answer"]
    assert contrast["interval_95_unadjusted_pp"] is None
    assert summary["pilot_continuation_gates_by_detailed_vs_label"]["question_answer_minus_label_only"]["pilot_continuation_gate_passed"] is False
