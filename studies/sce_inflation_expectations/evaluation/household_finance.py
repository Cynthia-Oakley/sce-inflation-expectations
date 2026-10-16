"""Offline, audited evaluation of the exploratory household-finance trial.

No model calls or original survey workbooks are opened. Generic frozen scoring,
truth/roster audits and cell metrics are shared with the cognition evaluator;
this module owns its protocol, treatment checks, comparisons and decisions.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import duckdb
import numpy as np

from . import cognition as shared
from .cognition import (sha, finite, _float_or_none, _safe_relative, _read_json,
    _verify_declared_hashes, _truth_lookup, _validate_links, _load_reference,
    _validate_preview, _audit_raw_reply, _action_bins, _score_bins,
    _cell_rows, _summarize_arm, _comparison_changes)
from .metrics import quantile
from ..prior_belief_experiment import message_hash
from ..revision_format_runtime import REPLY_MARKER
from ..scoring.sce_q9_frozen import provenance

ROOT = Path(__file__).resolve().parents[3]
TRUTH = shared.TRUTH
REFERENCE = shared.REFERENCE
PARENT = ROOT / "outputs/sce_cognition_trial_20261016_v4"
ARMS = ("baseline", "financial_facts", "financial_perspective")
MONTHS = (202004, 202105, 202111, 202203)
EXPECTED_N_PER_MONTH = 24
EXPECTED_REPEATS = (1, 2)
PRIMARY_METRIC = "individual_density_mean_mae_pp"
REGISTERED_CONTRASTS = (("financial_facts", "baseline"),
    ("financial_perspective", "financial_facts"), ("financial_perspective", "baseline"))
VALIDITY_THRESHOLD = .99
BOOTSTRAP_SEED = 20261016
RESEARCH_LINE = "A_conditional_returner_reconstruction"
REF = "sce_inflation_expectations.household_finance_decision"


def _validate_protocol(protocol, manifest):
    expected = {
        "id": "sce-household-finance-pilot-v1", "research_line": RESEARCH_LINE, "arms": list(ARMS),
        "months": list(MONTHS), "n_per_month": 24, "generation_repeats": [1, 2],
        "planned_calls": 576, "primary_metric": PRIMARY_METRIC,
        "model": "deepseek-flash", "temperature": .5, "max_tokens": 1024,
        "thinking": "disabled", "retry_max": 0,
        "primary_contrast": "financial_facts minus baseline",
        "secondary_contrasts": ["financial_perspective minus financial_facts", "financial_perspective minus baseline"],
        "stratum_n": {"high": 14, "low": 10},
    }
    for key, value in expected.items():
        if protocol.get(key) != value:
            raise ValueError(f"Household-finance protocol differs at {key}")
    if (any(type(value) is not int for value in protocol["months"] + protocol["generation_repeats"])
            or type(protocol["n_per_month"]) is not int
            or type(protocol["planned_calls"]) is not int):
        raise ValueError("Protocol months, repeats and counts must be integers")
    if type(manifest.get("planned_calls")) is not int or manifest.get("planned_calls") != 576:
        raise ValueError("Prepared manifest planned-call count mismatch")
    return list(MONTHS), list(EXPECTED_REPEATS)


def _required_prepared_paths(months):
    required = {"protocol.json", "evaluation_links_private.json"}
    for month in months:
        required.update(f"{month}/{name}.json" for name in
                        ("population", "environment", "household_finance_payloads"))
        required.update(f"{month}/{prefix}_{arm}.json" for arm in ARMS
                        for prefix in ("simulation", "preview"))
    return required


def _verify_parent_baseline(folder, manifest, months):
    required = {str((PARENT / "evaluation_links_private.json").relative_to(ROOT))}
    required.update(str((PARENT / str(m) / "preview_label_only.json").relative_to(ROOT)) for m in months)
    verified = _verify_declared_hashes(ROOT, manifest.get("source_sha256"), "baseline source", required)
    if (folder / "evaluation_links_private.json").read_bytes() != (PARENT / "evaluation_links_private.json").read_bytes():
        raise ValueError("Evaluation links must be copied byte-for-byte from cognition v4")
    for month in months:
        original = _read_json(PARENT / str(month) / "preview_label_only.json")
        baseline = _read_json(folder / str(month) / "preview_baseline.json")
        if baseline != original:
            raise ValueError("Baseline differs from the latest direct label-only input")
    return verified


def _previous_month(month):
    year, number = divmod(month, 100)
    return year * 100 + number - 1 if number > 1 else (year - 1) * 100 + 12


def _load_financial_records(folder, months, manifest):
    records = {}
    fields = {"schema_version", "research_line", "target_month", "current_q1_code",
              "current_q1_source_month", "previous_q1_code", "previous_q1_source_month",
              "current_source_sha256", "previous_source_sha256"}
    source_hashes = set(manifest.get("source_sha256", {}).values())
    for month in months:
        path = folder / str(month) / "household_finance_payloads.json"
        rows = _read_json(path)
        if not isinstance(rows, dict) or not rows:
            raise ValueError("Agent-indexed financial records required")
        for agent_id, record in rows.items():
            if not isinstance(agent_id, str) or not agent_id or not isinstance(record, dict) or set(record) != fields:
                raise ValueError("Financial payload field whitelist or anonymous identifier mismatch")
            if (record["schema_version"] != "sce_household_finance_input_v1"
                    or record["research_line"] != RESEARCH_LINE
                    or type(record["target_month"]) is not int or record["target_month"] != month):
                raise ValueError("Financial payload schema/research line/target mismatch")
            for prefix, source_month in (("current", month), ("previous", _previous_month(month))):
                code, observed, digest = (record[f"{prefix}_q1_code"], record[f"{prefix}_q1_source_month"],
                                           record[f"{prefix}_source_sha256"])
                if code is None:
                    if observed is not None or digest is not None:
                        raise ValueError("Missing Q1 must have no source month/hash")
                elif (type(code) is not int or code not in range(1, 6)
                      or type(observed) is not int or observed != source_month
                      or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                      or digest not in source_hashes):
                    raise ValueError("Q1 code/time/source-hash mismatch")
        records[month] = rows
        for arm in ARMS:
            config = _read_json(folder / str(month) / f"simulation_{arm}.json")
            args = config.get("decision_args", {})
            if (config.get("decision_ref") != REF
                    or args.get("household_finance_payloads_sha256") != sha(path)
                    or args.get("household_finance_bundle", {}).get("arm") != arm):
                raise ValueError("Financial simulation provider/arm/payload hash mismatch")
    required_source_paths = {path for path, digest in manifest["source_sha256"].items()
                             if any(digest == record[f"{prefix}_source_sha256"]
                                    for rows in records.values() for record in rows.values()
                                    for prefix in ("current", "previous"))}
    _verify_declared_hashes(ROOT, manifest["source_sha256"], "financial record source", required_source_paths)
    return records


def _validate_shared_base_prompts(previews, months, agent_ids_by_month, records):
    # Compare exact registered insertion into an already-direct baseline.
    # Calling the runtime transform again would duplicate its answer contract.
    from ..household_finance_input import render_household_finance_block
    for month in months:
        if set(records[month]) != agent_ids_by_month[month]:
            raise ValueError("Financial payload roster differs from evaluation links")
        for agent_id in agent_ids_by_month[month]:
            base = previews[month, "baseline"][agent_id]["messages"]
            if (not isinstance(base, list) or len(base) != 1 or base[0].get("role") != "user"
                    or not isinstance(base[0].get("content"), str)
                    or base[0]["content"].count(REPLY_MARKER) != 1):
                raise ValueError("Baseline must contain a single direct-answer user message")
            for arm in ARMS:
                block = render_household_finance_block(arm, records[month][agent_id])
                text = base[0]["content"]
                expected = [{"role": "user", "content": text.replace(REPLY_MARKER, block + REPLY_MARKER, 1)}]
                if expected != previews[month, arm][agent_id]["messages"]:
                    raise ValueError("Exact registered financial insertion differs from preview")


def financial_group(code):
    return "worse" if code in (1, 2) else "same" if code == 3 else "better" if code in (4, 5) else "missing"


def load(folder: Path) -> dict:
    """Load, hash-check, and independently reconstruct a completed household-finance trial."""
    folder = Path(folder).resolve()
    manifest_path, protocol_path = folder / "manifest.json", folder / "protocol.json"
    manifest, protocol = _read_json(manifest_path), _read_json(protocol_path)
    protocol_hash = sha(protocol_path)
    if manifest.get("protocol_sha256") != protocol_hash:
        raise ValueError("Protocol hash differs from the prepared manifest")
    if not provenance()["live_matches_pinned"]:
        raise ValueError("Frozen Q9 scorer has changed")
    months, repeats = _validate_protocol(protocol, manifest)
    declared_prepared = manifest.get("prepared_file_sha256")
    if not isinstance(declared_prepared, dict) or not _required_prepared_paths(months).issubset(declared_prepared):
        raise ValueError("Prepared manifest omits required household-finance inputs")
    prepared_hashes = _verify_declared_hashes(folder, declared_prepared, "prepared input")
    truth_relative = str(TRUTH.resolve().relative_to(ROOT.resolve()))
    declared_sources = manifest.get("source_sha256", {})
    reference_relative = str(REFERENCE.resolve().relative_to(ROOT.resolve()))
    verified_sources = _verify_declared_hashes(
        ROOT, declared_sources, "source", {truth_relative, reference_relative})
    verified_parent = _verify_parent_baseline(folder, manifest, months)
    records = _load_financial_records(folder, months, manifest)
    truth = _truth_lookup(TRUTH)
    links = _validate_links(folder, months, truth, protocol)
    truth_for_roster = []
    for (month, agent_id), link in links.items():
        target = truth[month, agent_id]
        truth_for_roster.append({"month": month, "userid": link["userid"],
                                 "actual": target["actual"], "actual_iqr": target["actual_iqr"]})
    reference, reference_diagnostics = _load_reference(truth_for_roster, REFERENCE)
    agent_ids_by_month = {
        month: {agent_id for m, agent_id in links if m == month} for month in months
    }

    expected_jobs = {(month, arm, repeat) for month in months for arm in ARMS for repeat in repeats}
    jobs = manifest.get("jobs")
    jobs_by_key = {}
    for job in jobs or []:
        key = (int(job["month"]), str(job["arm"]), int(job["repeat"]))
        if key not in expected_jobs or key in jobs_by_key:
            raise ValueError("Manifest jobs contain an unknown or duplicate trial cell")
        run_id = job.get("run_id")
        if not isinstance(run_id, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", run_id):
            raise ValueError("Unsafe or missing run identifier")
        jobs_by_key[key] = job
    if set(jobs_by_key) != expected_jobs:
        raise ValueError("Manifest does not contain all 4×3×2 registered jobs")

    previews = {
        (month, arm): _validate_preview(folder, month, arm, agent_ids_by_month[month])
        for month in months for arm in ARMS
    }
    _validate_shared_base_prompts(previews, months, agent_ids_by_month, records)
    actions = {}
    coverage = {arm: Counter() for arm in ARMS}
    scorable = Counter()
    finance_digests = {record[f"{prefix}_source_sha256"] for rows in records.values()
                       for record in rows.values() for prefix in ("current", "previous")}
    verified_finance_sources = {name: digest for name, digest in declared_sources.items() if digest in finance_digests}
    source_hashes = {**verified_sources, **verified_parent, **verified_finance_sources, **prepared_hashes}
    estimated_cost = 0.0
    raw_replies_reconstructed = 0

    for key in sorted(expected_jobs):
        month, arm, repeat = key
        job = jobs_by_key[key]
        run_dir = _safe_relative(ROOT / "outputs" / "local_runs", job["run_id"])
        run_path = run_dir / "run_manifest.json"
        db_path = run_dir / "study.duckdb"
        calls_path = run_dir / "llm_calls.jsonl"
        for path in (run_path, db_path, calls_path):
            if not path.is_file():
                raise ValueError(f"Missing completed-run artifact for {job['run_id']}: {path.name}")
            source_hashes[str(path.relative_to(ROOT))] = sha(path)
        run = _read_json(run_path)
        if (run.get("status") != "completed" or run.get("llm_kind") != "openai"
                or int(run.get("n", -1)) != EXPECTED_N_PER_MONTH
                or run.get("run_id") != job["run_id"]
                or run.get("arm") != arm or int(run.get("month", -1)) != month
                or int(run.get("repeat", -1)) != repeat
                or run.get("protocol_sha256") != protocol_hash
                or int(run.get("cost", {}).get("call_count", -1)) != EXPECTED_N_PER_MONTH):
            raise ValueError(f"Run manifest does not match the registered cell: {job['run_id']}")
        payload_hash = sha(folder / str(month) / "household_finance_payloads.json")
        if (run.get("household_finance_payloads_sha256") != payload_hash
                or run.get("new_api_calls") != EXPECTED_N_PER_MONTH
                or run.get("actual_input_hashes_match") is not True):
            raise ValueError("Run manifest financial payload/call evidence mismatch")
        for original, saved in ((folder / str(month) / "household_finance_payloads.json", run_dir / "household_finance_payloads.json"),
                                (folder / str(month) / f"preview_{arm}.json", run_dir / "frozen_preview.json")):
            if not saved.is_file() or sha(original) != sha(saved):
                raise ValueError("Run frozen inputs differ from prepared inputs")
            source_hashes[str(saved.relative_to(ROOT))] = sha(saved)
        estimated_cost += float(run["cost"].get("estimated_cost_usd", 0.0))

        call_rows = [json.loads(line) for line in calls_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(call_rows) != EXPECTED_N_PER_MONTH:
            raise ValueError(f"Expected one original LLM call per respondent: {job['run_id']}")
        calls = {}
        for call in call_rows:
            agent_id = str(call["agent_id"])
            if agent_id in calls or agent_id not in agent_ids_by_month[month]:
                raise ValueError(f"LLM-call roster mismatch: {job['run_id']}")
            if (call.get("run_id") != job["run_id"] or int(call.get("attempt_idx", -1)) != 0
                    or call.get("target_month") != f"{month // 100:04d}-{month % 100:02d}"):
                raise ValueError(f"LLM-call metadata mismatch: {job['run_id']}")
            if (call.get("requested_model") != protocol["model"]
                    or call.get("temperature") != protocol["temperature"]
                    or call.get("max_tokens") != protocol["max_tokens"]
                    or call.get("extra_body") != {"thinking": {"type": protocol["thinking"]}}
                    or call.get("prompt_version") != "sce-q8-q9-household-finance-v1"):
                raise ValueError(f"LLM request model/settings mismatch: {job['run_id']}")
            calls[agent_id] = call
        if set(calls) != agent_ids_by_month[month]:
            raise ValueError(f"LLM-call file omits a selected respondent: {job['run_id']}")

        db = duckdb.connect(str(db_path), read_only=True)
        try:
            rows = db.execute(
                "SELECT agent_id, action_payload FROM panel "
                "WHERE step=1 AND action_kind='sce_answer'"
            ).fetchall()
        finally:
            db.close()
        if len(rows) != EXPECTED_N_PER_MONTH:
            raise ValueError(f"DuckDB action cardinality mismatch: {job['run_id']}")
        payloads = {}
        for agent_id_value, payload_value in rows:
            agent_id = str(agent_id_value)
            payload = json.loads(payload_value) if isinstance(payload_value, str) else payload_value
            if agent_id in payloads or agent_id not in agent_ids_by_month[month] or not isinstance(payload, dict):
                raise ValueError(f"DuckDB action roster mismatch: {job['run_id']}")
            payloads[agent_id] = payload
            preview = previews[month, arm][agent_id]
            call = calls[agent_id]
            expected_hash = preview["prompt_sha256"]
            expected_text = json.dumps(preview["messages"], ensure_ascii=False)
            if (payload.get("household_finance_arm") != arm
                    or payload.get("household_finance_payloads_sha256") != payload_hash
                    or payload.get("research_line") != RESEARCH_LINE
                    or payload.get("actual_messages_sha256") != expected_hash
                    or call.get("prompt_sha256") != expected_hash
                    or call.get("prompt_text") != expected_text):
                raise ValueError(f"Saved action/call does not match its exact preview: {job['run_id']}")
            raw = call.get("raw_response_text") or ""
            if hashlib.sha256(raw.encode("utf-8")).hexdigest() != call.get("raw_response_sha256"):
                raise ValueError(f"Original reply hash mismatch: {job['run_id']}")
            parsed, reply_error = _audit_raw_reply(raw, call, payload, arm)
            if parsed is not None:
                raw_replies_reconstructed += 1
            bins = _action_bins(payload)
            score = _score_bins(bins) if payload["validation_status"] == "valid" else {
                "mean": None, "iqr": None, "zero_deflation": None,
                "scorer_status": "not_scored_invalid_response", "validation_error": reply_error,
            }
            point = _float_or_none(payload.get("point_pct")) if parsed is not None else None
            result = {
                "validation_status": payload["validation_status"],
                "response_parsed": parsed is not None,
                "parse_error": reply_error,
                "point": point,
                "q9_bins": bins,
                **score,
            }
            actions[month, repeat, agent_id, arm] = result
            coverage[arm][payload["validation_status"]] += 1
            scorable[arm] += int(finite(result["mean"]) and finite(result["iqr"]))
        if set(payloads) != agent_ids_by_month[month]:
            raise ValueError("DuckDB action omits a selected respondent")

    cases = []
    for (month, agent_id), link in sorted(links.items()):
        target = truth[month, agent_id]
        reference_target = reference[month, link["userid"]]
        real = {
            "q9_mean": _float_or_none(target["actual"]),
            "q9_iqr": _float_or_none(target["actual_iqr"]),
            "q9_zero_deflation": _float_or_none(target["actual_zero_deflation"]),
            "q9_bins": reference_target["q9_bins"],
            "official_q9_mean": reference_target["official_q9_mean"],
            "official_q9_iqr": reference_target["official_q9_iqr"],
            "q8_point": _float_or_none(target["actual_point"]),
            "previous_q9_mean": _float_or_none(target["previous"]),
            "previous_q9_bins": target["previous_bins"],
        }
        finance = records[month][agent_id]
        for repeat in repeats:
            case = {
                "current_q1_code": finance["current_q1_code"],
                "previous_q1_code": finance["previous_q1_code"],
                "financial_group": financial_group(finance["current_q1_code"]),
                "month": month, "repeat": repeat, "agent_id": agent_id,
                "userid": int(link["userid"]), "numeracy": str(link["profile"]["numeracy"]).title(),
                "survey_weight": float(link["survey_weight"]),
                "raw_parent_survey_weight": float(link["raw_parent_survey_weight"]),
                "sampling_weight": float(link["sampling_weight"]), "real": real,
                "arms": {arm: actions[month, repeat, agent_id, arm] for arm in ARMS},
            }
            cases.append(case)
    return {
        "folder": folder, "protocol": protocol, "manifest": manifest,
        "protocol_sha256": protocol_hash, "cases": cases,
        "coverage": {arm: dict(coverage[arm]) for arm in ARMS},
        "scorable_n": dict(scorable), "estimated_run_cost_usd": estimated_cost,
        "raw_replies_reconstructed_and_matched": raw_replies_reconstructed,
        "source_sha256": source_hashes,
        "reference_diagnostics": reference_diagnostics,
        "prepared_file_count": len(prepared_hashes),
        "months": months, "repeats": repeats,
        "scorer": provenance(),
    }


def _common_person_months(cases, repeats, measure):
    """All arms and both repeats must be legal; preserve failures outside mask."""
    legal = [row for row in cases
             if all(row['arms'][arm].get('validation_status') == 'valid' for arm in ARMS)]
    return shared._common_person_months(legal, list(ARMS), repeats, measure)


def _paired_cluster_bootstrap(cases, months, repeats, support, draws=1000, seed=BOOTSTRAP_SEED):
    """Paired mean-MAE differences; one draw carries each person's whole panel."""
    if type(draws) is not int or draws < 1:
        raise ValueError('draws must be a positive integer')
    cells = [_cell_rows(cases, month, repeat, support) for month in months for repeat in repeats]
    empty = any(not rows for rows in cells)
    people = sorted({row['userid'] for rows in cells for row in rows})
    person_index = {person: i for i, person in enumerate(people)}
    prepared = []
    for rows in cells:
        indices = np.asarray([person_index[row['userid']] for row in rows], dtype=int)
        errors = {arm: np.asarray([abs(row['arms'][arm]['mean'] - row['real']['q9_mean'])
                                  for row in rows]) for arm in ARMS}
        prepared.append((indices, errors))
    rng = np.random.default_rng(seed)
    samples = {pair: [] for pair in REGISTERED_CONTRASTS}
    attempts = 0
    while not empty and len(next(iter(samples.values()))) < draws and attempts < draws * 20:
        attempts += 1
        counts = np.bincount(rng.integers(0, len(people), len(people)), minlength=len(people))
        arm_scores = {arm: 0.0 for arm in ARMS}
        usable = True
        for indices, errors in prepared:
            weights = counts[indices]
            if weights.sum() == 0:
                usable = False
                break
            for arm in ARMS:
                arm_scores[arm] += float(np.average(errors[arm], weights=weights)) / len(cells)
        if usable:
            for pair in REGISTERED_CONTRASTS:
                samples[pair].append(arm_scores[pair[0]] - arm_scores[pair[1]])
    return {f'{candidate}_minus_{baseline}': {
        'interval_95_unadjusted_pp': np.quantile(values, [.025, .975]).astype(float).tolist() if values else None,
        'draws_requested': draws, 'draws_used': len(values),
        'empty_cell_draws': attempts - len(values), 'seed': seed,
        'reason': 'At least one registered month-repeat cell has no common support.' if empty else None,
        'scope': 'Exploratory unadjusted respondent-cluster bootstrap; all months and both repeats remain together; equal month-repeat cells.',
    } for (candidate, baseline), values in samples.items()}


def _financial_group_descriptions(cases, months, repeats, support):
    """Median group gaps are descriptive; sparse cells never remove main rows."""
    pairs = (('worse', 'same'), ('better', 'same'), ('worse', 'better'))
    cells = []
    for month in months:
        for repeat in repeats:
            rows = _cell_rows(cases, month, repeat, support)
            groups = {label: [row for row in rows if row['financial_group'] == label]
                      for label in ('worse', 'same', 'better', 'missing')}
            cell = {'month': month, 'repeat': repeat,
                    'common_group_counts': {label: len(part) for label, part in groups.items()},
                    'contrasts': {}}
            for left, right in pairs:
                name = f'{left}_minus_{right}'
                if min(len(groups[left]), len(groups[right])) < 3:
                    cell['contrasts'][name] = {
                        'reported': False, 'reason': 'At least one financial group has fewer than 3 common respondents.',
                        'real_median_gap_pp': None, 'arms': {},
                    }
                    continue
                def median(group, arm=None):
                    values = [row['real']['q9_mean'] if arm is None else row['arms'][arm]['mean']
                              for row in groups[group]]
                    return quantile(np.asarray(values), np.ones(len(values)), .5)
                real_gap = median(left) - median(right)
                cell['contrasts'][name] = {
                    'reported': True, 'real_median_gap_pp': real_gap,
                    'arms': {arm: {
                        'model_median_gap_pp': median(left, arm) - median(right, arm),
                        'signed_deviation_from_real_gap_pp': median(left, arm) - median(right, arm) - real_gap,
                        'absolute_deviation_from_real_gap_pp': abs(median(left, arm) - median(right, arm) - real_gap),
                    } for arm in ARMS},
                }
            cells.append(cell)
    aggregate = {}
    for left, right in pairs:
        name = f'{left}_minus_{right}'
        selected = [cell['contrasts'][name] for cell in cells if cell['contrasts'][name]['reported']]
        aggregate[name] = {
            'cells_reported': len(selected), 'expected_cells': len(cells),
            'complete_all_registered_cells': len(selected) == len(cells),
            'arms': {arm: {
                'mean_absolute_deviation_from_real_gap_pp': float(np.mean([
                    item['arms'][arm]['absolute_deviation_from_real_gap_pp'] for item in selected])) if selected else None,
            } for arm in ARMS},
        }
    assigned = [row for row in cases if row['repeat'] == repeats[0]]
    return {
        'descriptive_only': True, 'current_q1_grouping': {'worse': [1, 2], 'same': [3], 'better': [4, 5]},
        'assigned_current_q1_code_counts': dict(Counter(str(row['current_q1_code']) for row in assigned)),
        'assigned_financial_group_counts': dict(Counter(row['financial_group'] for row in assigned)),
        'cells': cells, 'aggregate_over_reportable_equal_month_repeat_cells': aggregate,
        'sparse_cell_rule': 'Do not report a group contrast if either group has fewer than 3 common people; full-sample accuracy retains those people.',
        'interpretation': 'Differences between group medians compared with the matched human median gap; not causal effects or independent validation.',
    }


def _support_missingness(cases, repeats, q9_support, q8_support):
    grouped = defaultdict(list)
    for row in cases:
        grouped[row['month'], row['userid']].append(row)
    truth_q9 = truth_q8 = model_q9 = model_q8 = prior_missing = 0
    for rows in grouped.values():
        truth_q9 += int(any(not all(finite(row['real'].get(key)) for key in
                                   ('q9_mean', 'q9_iqr', 'q9_zero_deflation'))
                           or len(row['real'].get('q9_bins', [])) != 10
                           or not all(finite(v) for v in row['real'].get('q9_bins', [])) for row in rows))
        truth_q8 += int(any(not finite(row['real'].get('q8_point')) for row in rows))
        prior_missing += int(any(not finite(row['real'].get('previous_q9_mean')) for row in rows))
        model_q9 += int(any(row['arms'][arm].get('validation_status') != 'valid'
                           or not all(finite(row['arms'][arm].get(key)) for key in ('mean', 'iqr', 'zero_deflation'))
                           for row in rows for arm in ARMS))
        model_q8 += int(any(row['arms'][arm].get('validation_status') != 'valid'
                           or not finite(row['arms'][arm].get('point')) for row in rows for arm in ARMS))
    return {
        'human_q9_missing_or_unscorable_person_months': truth_q9,
        'human_q8_missing_person_months': truth_q8,
        'any_model_q9_invalid_or_unscorable_person_months': model_q9,
        'any_model_q8_invalid_or_missing_person_months': model_q8,
        'human_previous_q9_missing_person_months': prior_missing,
        'q9_common_support_with_finite_real_prior_person_months': sum(
            key in q9_support and all(finite(row['real'].get('previous_q9_mean')) for row in rows)
            for key, rows in grouped.items()),
        'counts_can_overlap': True,
        'incomplete_repeat_person_months': sum(set(row['repeat'] for row in rows) != set(repeats)
                                               for rows in grouped.values()),
    }


def _comparison_results(metrics, intervals):
    results = {}
    for candidate, baseline in REGISTERED_CONTRASTS:
        name = f'{candidate}_minus_{baseline}'
        changes = _comparison_changes(metrics, candidate, baseline)
        results[name] = {
            'primary_metric': PRIMARY_METRIC,
            'primary_metric_difference_pp': changes[PRIMARY_METRIC],
            **intervals[name], 'other_metric_point_changes': changes,
            'confirmatory_claim': False,
        }
    return results


def _pilot_gates(comparisons, coverage_ok, expected_cells):
    gates = {}
    for name, comparison in comparisons.items():
        interval = comparison.get('interval_95_unadjusted_pp')
        changes = comparison['other_metric_point_changes']
        bootstrap_complete = comparison.get('draws_requested') == 1000 and comparison.get('draws_used') == 1000
        primary_ok = bool(interval is not None and interval[1] < 0)
        center_ok = finite(changes.get('q9_center_mae_pp')) and changes['q9_center_mae_pp'] <= 0
        w1_ok = finite(changes.get('cross_section_w1_pp')) and changes['cross_section_w1_pp'] <= 0
        gates[name] = {
            'pilot_continuation_gate_passed': bool(coverage_ok and expected_cells and bootstrap_complete and primary_ok and center_ok and w1_ok),
            'coverage_gate_passed': coverage_ok, 'all_registered_accuracy_cells_present': expected_cells,
            'registered_1000_bootstrap_draws_complete': bootstrap_complete,
            'primary_mean_mae_upper_interval_below_zero': primary_ok,
            'center_error_point_change_nonworse': bool(center_ok),
            'cross_section_w1_point_change_nonworse': bool(w1_ok),
            'interpretation': 'Exploratory continuation screen only; no automatic default upgrade or confirmed mechanism claim.',
        }
    return gates


def evaluate(folder: Path, out: Path, draws: int = 1000) -> dict:
    """Audit every completed real run, then write fresh local evaluation outputs."""
    folder, out = Path(folder).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to((ROOT / 'outputs').resolve()):
        raise ValueError('Require a fresh output directory under the ignored outputs folder')
    if type(draws) is not int or draws < 1:
        raise ValueError('draws must be a positive integer')
    loaded = load(folder)
    cases, protocol = loaded['cases'], loaded['protocol']
    months, repeats = loaded['months'], loaded['repeats']
    planned_per_arm = len(months) * EXPECTED_N_PER_MONTH * len(repeats)
    fractions = {}
    for arm in ARMS:
        valid = loaded['coverage'][arm].get('valid', 0)
        scorable = loaded['scorable_n'].get(arm, 0)
        fractions[arm] = {'planned': planned_per_arm, 'valid_n': valid,
                          'valid_fraction': valid / planned_per_arm, 'scorable_n': scorable,
                          'scorable_fraction': scorable / planned_per_arm,
                          'validation_status_counts': loaded['coverage'][arm]}
    coverage_ok = all(item['valid_fraction'] >= VALIDITY_THRESHOLD and item['scorable_fraction'] >= VALIDITY_THRESHOLD
                      for item in fractions.values())
    q9_support = _common_person_months(cases, repeats, 'q9')
    q8_support = _common_person_months(cases, repeats, 'q8')
    metrics = {arm: _summarize_arm(cases, arm, months, repeats, q9_support, q8_support) for arm in ARMS}
    seed = int(protocol.get('bootstrap_seed', BOOTSTRAP_SEED))
    if coverage_ok:
        intervals = _paired_cluster_bootstrap(cases, months, repeats, q9_support, draws, seed)
    else:
        intervals = {f'{candidate}_minus_{baseline}': {
            'interval_95_unadjusted_pp': None, 'draws_requested': draws, 'draws_used': 0,
            'reason': 'At least one arm is below 99% valid/scorable; accuracy is descriptive.',
        } for candidate, baseline in REGISTERED_CONTRASTS}
    comparisons = _comparison_results(metrics, intervals)
    expected_cells = all(metrics[arm]['q9']['cells_used_by_metric'][PRIMARY_METRIC] == len(months) * len(repeats)
                         for arm in ARMS)
    gates = _pilot_gates(comparisons, coverage_ok, expected_cells)
    expected_people = len(months) * EXPECTED_N_PER_MONTH
    summary = {
        'status': 'completed_sce_household_finance_development_pilot_evaluation',
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'protocol': protocol, 'protocol_sha256': loaded['protocol_sha256'],
        'research_line': RESEARCH_LINE, 'primary_metric': PRIMARY_METRIC,
        'primary_contrast': 'financial_facts minus baseline',
        'secondary_contrasts': ['financial_perspective minus financial_facts', 'financial_perspective minus baseline'],
        'intervals_are_exploratory_only': True, 'confirmatory_claim': False,
        'individual_update_mae_identity': {
            'formula': '|(model_current - real_previous) - (real_current - real_previous)| = |model_current - real_current|',
            'metric': PRIMARY_METRIC, 'independent_evidence': False,
            'scope': 'On the same finite matched real previous belief, individual-update MAE equals current density-mean MAE exactly. It is one piece of evidence; distributional delta-W1 is a different descriptive quantity.',
        },
        'evaluation_api_calls': 0, 'evaluated_llm_calls': protocol['planned_calls'],
        'estimated_run_cost_usd_not_provider_bill': loaded['estimated_run_cost_usd'],
        'raw_replies_reconstructed_and_matched': loaded['raw_replies_reconstructed_and_matched'],
        'scorer_provenance': loaded['scorer'], 'reference_truth_verification': loaded['reference_diagnostics'],
        'human_truth_scoring': 'Human and model ten-bin Q9 vectors use the same frozen approximate scorer; official summary fields are sensitivity diagnostics only.',
        'coverage': fractions, 'accuracy_is_descriptive_only_due_to_validity_gate': not coverage_ok,
        'common_support': {
            'registered_person_months': expected_people,
            'q9_common_scorable_person_months': len(q9_support),
            'q9_excluded_person_months': expected_people - len(q9_support),
            'q9_common_generation_rows': len(q9_support) * len(repeats),
            'q9_assigned_generation_rows': expected_people * len(repeats),
            'q8_common_person_months': len(q8_support),
            'q8_excluded_person_months': expected_people - len(q8_support),
            'support_definition': 'Each retained person-month has valid answers in all three arms and both repeats, finite matched frozen Q9 mean/IQR/zero and raw bins; Q8 has its own legal all-arm/all-repeat finite-point mask. Missing and invalid cases remain in assigned coverage counts.',
        },
        'aggregation': 'Equal month × repeat cells; paired globally clustered respondent bootstrap retains every sampled person’s months and repeats. Repeated generations are not new humans.',
        'sampling_design': {'selected_per_month': {'High': 14, 'Low': 10},
                            'primary_analysis': 'Unweighted within selected roster; equal month and repeat cells; not nationally representative.',
                            'auxiliary_weighting': 'Parent survey weight × inverse selection probability, descriptive sensitivity only.'},
        'support_missingness': _support_missingness(cases, repeats, q9_support, q8_support),
        'arms': metrics, 'financial_group_descriptions': _financial_group_descriptions(cases, months, repeats, q9_support),
        'paired_contrasts': comparisons, 'pilot_continuation_gates': gates,
        'primary_continuation_gate': gates['financial_facts_minus_baseline'],
        'source_sha256': loaded['source_sha256'], 'prepared_file_count_verified': loaded['prepared_file_count'],
        'evaluator_sha256': {str(Path(__file__).relative_to(Path(__file__).resolve().parents[3])): sha(Path(__file__)),
                             'studies/sce_inflation_expectations/evaluation/cognition.py': sha(Path(shared.__file__))},
        'bootstrap': {'draws_requested': draws, 'seed': seed, 'person_clustered_across_months': True,
                      'all_intervals_unadjusted_and_exploratory': True},
        'metric_units': {'density_mean_iqr_center_w1_q8': 'inflation percentage points',
                         'probability_tv_pct': 'probability percentage points', 'rates': 'fractions'},
        'limitations': [
            'Current Q1 and inflation answers were collected in the same survey. This is A historical conditional reconstruction, not B ex ante forecasting or a causal financial-shock estimate.',
            'Four previously inspected development months, numeracy-stratified roster and few extreme financial states; no independent validation or national inference.',
            'Public information, earlier beliefs and price news are held fixed across arms. Financial facts and household-perspective wording remain exploratory interventions.',
            'Group comparisons are descriptive; groups with fewer than 3 common respondents in a cell are suppressed without deleting full-sample rows.',
            'Accuracy conditions on common legal/scorable support; assigned counts retain invalid and missing cases.',
        ],
    }
    out.mkdir(parents=True, exist_ok=False)
    for name, value in (('summary.json', summary), ('cases_private.json', cases)):
        (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return summary


load_completed_cases = load
