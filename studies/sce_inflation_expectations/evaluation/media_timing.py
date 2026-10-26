"""Offline evaluation for the personal-date × warning 2×2 Terminal run.

Old V3 outcomes are linked by exact archived prompt hash. Failed old attempts
and new failures stay missing. Target truth and links are opened here only.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path

from ..experiments.frozen_batch import ROOT, dump, read_json, sha
from ..experiments import frozen_message_queue as queue
from ..experiments import media_timing_terminal as terminal
from . import cognition as shared
from . import media_mechanism_terminal as old_eval


def _evaluation_truth(ctx):
    p = ctx["protocol"]
    evaluation_package = terminal._safe_root_path(p["evaluation_package"])
    manifest = read_json(evaluation_package / "manifest.json")
    ep = read_json(evaluation_package / "protocol.json")
    truth_ref = ep.get("evaluation_truth")
    if truth_ref != p["evaluation_package"].rstrip("/") + "/" + terminal.TRUTH_REL:
        raise ValueError("V3 protocol does not point to its registered private target truth")
    expected_truth = manifest.get("prepared_file_sha256", {}).get(terminal.TRUTH_REL)
    expected_links = manifest.get("prepared_file_sha256", {}).get(terminal.LINKS_REL)
    if not expected_truth or not expected_links:
        raise ValueError("V3 package manifest does not pin private evaluation inputs")
    truth_path = terminal._safe_package_path(evaluation_package, terminal.TRUTH_REL)
    links_path = terminal._safe_package_path(evaluation_package, terminal.LINKS_REL)
    if sha(truth_path) != expected_truth or sha(links_path) != expected_links:
        raise ValueError("V3 target truth/link hash mismatch")
    truth_rows = read_json(truth_path)
    links = read_json(links_path)
    if not isinstance(truth_rows, list) or not isinstance(links, list):
        raise ValueError("V3 target truth and links must be arrays")
    truth = {}
    for row in truth_rows:
        key = (int(row["month"]), str(row["agent_id"]), int(row["repeat"]))
        if key in truth:
            raise ValueError("V3 target truth contains duplicate person-month-repeat rows")
        if not isinstance(row.get("real"), dict):
            raise ValueError("V3 target truth row has no real answer")
        truth[key] = row["real"]
    link_by_key = {}
    for link in links:
        key = (int(link["month"]), str(link["agent_id"]))
        if key in link_by_key:
            raise ValueError("V3 evaluation roster contains duplicate person-month rows")
        link_by_key[key] = link
    selected = {(int(row["month"]), str(row["agent_id"])) for row in ctx["positions"].values()}
    if not selected <= set(link_by_key):
        raise ValueError("V3 target links omit one or more selected logical positions")
    selected_truth = {(month, aid, repeat) for month, aid in selected for repeat in terminal.REPEATS}
    if not selected_truth <= set(truth):
        raise ValueError("V3 target truth omits one or more selected person-month-repeat rows")
    return ({key: link_by_key[key] for key in selected},
            {key: truth[key] for key in selected_truth},
            {"evaluation_package": p["evaluation_package"],
             "evaluation_package_manifest_sha256": sha(evaluation_package / "manifest.json"),
             terminal.LINKS_REL: expected_links,
             terminal.TRUTH_REL: expected_truth})


def _validate_new_archive(run_dir, ctx, p):
    intents, replies = queue.archive(run_dir)
    expected = ctx["slot_by_key"]
    by_intent = {row["key"]: row for row in intents}
    by_reply = {row["key"]: row for row in replies}
    if len(by_intent) != len(intents) or len(by_reply) != len(replies):
        raise ValueError("New Terminal archive contains duplicate request/reply keys")
    if set(by_intent) != set(expected):
        raise ValueError("New Terminal archive has not attempted the full frozen slot scope")
    if not set(by_reply) <= set(by_intent):
        raise ValueError("New Terminal archive contains an unregistered response")
    if any(row.get("actual_model_results") is not True for row in by_reply.values()):
        raise ValueError("Engineering-only or unlabelled replies cannot enter research evaluation")
    for key, intent in by_intent.items():
        slot = expected[key]
        if (intent.get("prompt_sha256") != slot["prompt_sha256"]
                or intent.get("reserved_usd") != slot["reserved_usd"]):
            raise ValueError("New request archive differs from frozen slot")
    for row in by_reply.values():
        if row.get("prompt_sha256") != by_intent[row["key"]].get("prompt_sha256"):
            raise ValueError("New response prompt hash differs from intent")
        if row.get("error") is None and (row.get("returned_model") != p["model"]
                                          or row.get("returned_provider") != p["expected_provider"]):
            raise ValueError("New response differs from locked model/provider")
    return intents, replies, by_reply


def _validate_repair_archive(run_dir, ctx, p, main_replies):
    """Validate the independent one-time repair ledger before truth is opened."""
    repair_root = Path(run_dir) / "repair"
    intents, replies = queue.archive(repair_root) if repair_root.exists() else ([], [])
    targets, by_intent, by_reply = terminal._validate_repair_ledger_shape(
        intents, replies, ctx["slot_by_key"], main_replies, p)
    if len(intents) > len(ctx["slots"]):
        raise ValueError("Repair ledger exceeds one attempt per new request slot")
    for row in replies:
        if row.get("actual_model_results") is not True:
            raise ValueError("Engineering-only or unlabelled repair replies cannot enter research evaluation")
        target_key = terminal._repair_target_key(row["key"])
        slot = ctx["slot_by_key"].get(target_key)
        if slot is None:
            raise ValueError("Repair receiver is not one of the frozen new request slots")
        if (row.get("month"), row.get("arm"), row.get("repeat"), str(row.get("agent_id"))) != (
                slot["month"], slot["arm"], slot["repeat"], str(slot["agent_id"])):
            raise ValueError("Repair response receiver differs from the main request")
        if row.get("prompt_sha256") != slot.get("prompt_sha256"):
            raise ValueError("Repair response prompt hash differs from its frozen main slot")
        if row.get("error") is None and (row.get("returned_model") != p["model"]
                                           or row.get("returned_provider") != p["expected_provider"]):
            raise ValueError("Repair response differs from the locked model/provider")
    return intents, replies, by_reply, targets


def _validate_old_archive(ctx, p):
    intents, replies = queue.archive(ctx["old_run"])
    intent_by_key = {row["key"]: row for row in intents}
    reply_by_key = {row["key"]: row for row in replies}
    if len(intent_by_key) != len(intents) or len(reply_by_key) != len(replies):
        raise ValueError("Old V3 archive contains duplicate request/reply keys")
    if set(intent_by_key) != {row["key"] for row in ctx["old_slots"]}:
        raise ValueError("Old V3 archive does not match its complete frozen slot index")
    if not set(reply_by_key) <= set(intent_by_key):
        raise ValueError("Old V3 archive contains an unregistered response")
    for row in reply_by_key.values():
        if row.get("actual_model_results") is not True:
            raise ValueError("Old V3 archive includes an engineering-only or unlabelled reply")
        if row.get("error") is None and (row.get("returned_model") != p["model"]
                                          or row.get("returned_provider") != p["expected_provider"]):
            raise ValueError("Old V3 response differs from the locked model/provider")
    return intent_by_key, reply_by_key


def _overlay_action(main_action, main_row, repair_row, target):
    """Overlay only originally failed fields; successful main fields are immutable."""
    action = deepcopy(main_action)
    main_fields = queue.fields(main_row) if main_row is not None else {"q8": False, "q9": False}
    repair_action = old_eval.model_action(repair_row)
    sources = {"q8": "main" if main_fields["q8"] else "missing",
               "q9": "main" if main_fields["q9"] else "missing"}
    accepted = []
    attempted_fields = set((target or {}).get("fields", []))
    if (not main_fields["q8"] and "q8" in attempted_fields
            and repair_action.get("point") is not None):
        action["point"] = repair_action["point"]
        sources["q8"] = "repair"
        accepted.append("q8")
    if (not main_fields["q9"] and "q9" in attempted_fields
            and repair_action.get("validation_status") == "valid"):
        for field in ("mean", "iqr", "zero_deflation", "q9_bins", "normalization_applied"):
            action[field] = deepcopy(repair_action.get(field))
        action["validation_status"] = "valid"
        sources["q9"] = "repair"
        accepted.append("q9")
    if main_fields["q8"] and action.get("point") != main_action.get("point"):
        raise ValueError("Repair overlay attempted to replace a successful main Q8 field")
    if main_fields["q9"] and action.get("q9_bins") != main_action.get("q9_bins"):
        raise ValueError("Repair overlay attempted to replace a successful main Q9 field")
    action["field_sources"] = sources
    action["repair_accepted_fields"] = accepted
    return action


def _action_for_position(position, old_replies, new_replies, repair_by_target=None,
                         repair_targets=None):
    """Resolve one logical position to its exact archived or newly generated row."""
    status = position["status"]
    if status in ("reuse_exact_success", "hold_old_attempted_failure"):
        row = old_replies.get(position["source_key"])
        source_archive, source_key = "old_v3", position["source_key"]
    elif status in ("new_request", "reuse_same_new_prompt"):
        row = new_replies.get(position["new_request_key"])
        source_archive, source_key = "new", position["new_request_key"]
    else:
        raise ValueError(f"Unknown position status: {status}")
    action = old_eval.model_action(row)
    if source_archive == "new":
        repair_row = (repair_by_target or {}).get(source_key)
        action = _overlay_action(action, row, repair_row,
                                 (repair_targets or {}).get(source_key))
        action["repair_source_key"] = "repair1|" + source_key if repair_row is not None else None
    action["source_archive"] = source_archive
    action["source_key"] = source_key
    return action


def _build_supports(cases, repeats):
    all_five = [*terminal.REFERENCE_ARMS, *terminal.ARMS]
    return {
        "all_five_q9": _support(cases, all_five, repeats, "q9"),
        "all_five_q8": _support(cases, all_five, repeats, "q8"),
        "four_new_arms_q9": _support(cases, list(terminal.ARMS), repeats, "q9"),
        "four_new_arms_q8": _support(cases, list(terminal.ARMS), repeats, "q8"),
        "all_five_plus_copy_previous_q9": _support(cases, [*all_five, "copy_previous"], repeats, "q9"),
        "all_five_plus_copy_previous_q8": _support(cases, [*all_five, "copy_previous"], repeats, "q8"),
        "primary_c0_t0_q9": _support(cases, ["C0", "T0"], repeats, "q9"),
        "primary_c0_t0_q8": _support(cases, ["C0", "T0"], repeats, "q8"),
        "primary_c0_t0_plus_copy_previous_q9": _support(cases, ["C0", "T0", "copy_previous"], repeats, "q9"),
        "primary_c0_t0_plus_copy_previous_q8": _support(cases, ["C0", "T0", "copy_previous"], repeats, "q8"),
        "pair_t0_t1_q9": _support(cases, ["T0", "T1"], repeats, "q9"),
        "pair_t0_t1_q8": _support(cases, ["T0", "T1"], repeats, "q8"),
        "pair_c0_c1_q9": _support(cases, ["C0", "C1"], repeats, "q9"),
        "pair_c0_c1_q8": _support(cases, ["C0", "C1"], repeats, "q8"),
        "pair_o0_c0_q9": _support(cases, ["O0", "C0"], repeats, "q9"),
        "pair_o0_c0_q8": _support(cases, ["O0", "C0"], repeats, "q8"),
    }


def _metrics(cases, arms, months, repeats, q9_support, q8_support):
    result = {}
    for arm in arms:
        overall = shared._summarize_arm(cases, arm, months, repeats, q9_support, q8_support)
        by_month = {
            str(month): shared._summarize_arm(cases, arm, [month], repeats, q9_support, q8_support)
            for month in months
        }
        by_repeat = {
            str(repeat): shared._summarize_arm(cases, arm, months, [repeat], q9_support, q8_support)
            for repeat in repeats
        }
        result[arm] = {"overall": overall, "by_month": by_month, "by_repeat": by_repeat}
    return result


def _support(cases, arms, repeats, measure):
    return shared._common_person_months(cases, arms, repeats, measure)


def evaluate(folder, out):
    folder, out = Path(folder).resolve(), Path(out).resolve()
    config, protocol = terminal.checked(folder)
    ctx = terminal._package_context(Path(config["package"]), check_engineering=True)
    if out.exists() or not out.is_relative_to((ROOT / "outputs").resolve()):
        raise ValueError("Fresh evaluation output directory under outputs/ required")
    old_intents, old_replies = _validate_old_archive(ctx, protocol)
    new_intents, new_replies, new_reply_by_key = _validate_new_archive(folder, ctx, protocol)
    generation_path = folder / "generation_receipt.json"
    if not generation_path.is_file():
        raise ValueError("A completed Terminal generation receipt is required before evaluation")
    generation = read_json(generation_path)
    if (generation.get("protocol_sha256") != config["protocol_sha256"]
            or generation.get("main_complete") is not True
            or generation.get("main", {}).get("status") != "completed"
            or generation.get("main", {}).get("technical_gate", {}).get("passed") is not True
            or len(new_replies) != len(new_intents)):
        raise ValueError("Main generation is incomplete or did not pass the locked technical gate")
    if generation.get("repair", {}).get("status") == "stopped_hard_error":
        raise ValueError("Hard repair provider/account error blocks evaluation")
    repair_intents, repair_replies, repair_by_repair_key, repair_targets = _validate_repair_archive(
        folder, ctx, protocol, list(new_reply_by_key.values()))
    repair_by_target = {terminal._repair_target_key(key): row
                        for key, row in repair_by_repair_key.items()}
    accounting = terminal._account_both(new_intents, new_replies, repair_intents, repair_replies)
    if accounting["total_spent_or_reserved_usd"] > protocol["budget_cap_usd"] + 1e-9:
        raise ValueError("Main plus repair archive exceeds the single frozen budget cap")
    links, truth, truth_hashes = _evaluation_truth(ctx)

    cases = []
    counts = {arm: Counter() for arm in (*terminal.REFERENCE_ARMS, *terminal.ARMS)}
    source_counts = Counter()
    for month, aid in sorted(links):
        link = links[month, aid]
        for repeat in terminal.REPEATS:
            real = truth[month, aid, repeat]
            arms = {}
            trace = {}
            for arm in (*terminal.REFERENCE_ARMS, *terminal.ARMS):
                pos = ctx["positions"][month, arm, repeat, aid]
                trace[arm] = {k: pos[k] for k in ("status", "source_key", "new_request_key") if k in pos}
                source_counts[pos["status"]] += 1
                action = _action_for_position(pos, old_replies, new_reply_by_key,
                                              repair_by_target, repair_targets)
                arms[arm] = action
                counts[arm][action["validation_status"]] += 1
            arms["copy_previous"] = old_eval.previous_action(real)
            cases.append(dict(link, repeat=repeat,
                survey_weight=link["design_survey_weight"], real=real, arms=arms, position_trace=trace))

    months, repeats = list(protocol["months"]), list(protocol["generation_repeats"])
    all_five = [*terminal.REFERENCE_ARMS, *terminal.ARMS]
    supports = _build_supports(cases, repeats)
    groups = {
        "all_five_common_support": (all_five, supports["all_five_q9"], supports["all_five_q8"]),
        "four_new_arms_common_support": (
            list(terminal.ARMS), supports["four_new_arms_q9"], supports["four_new_arms_q8"]),
        "all_five_plus_copy_previous_same_support": (
            [*all_five, "copy_previous"], supports["all_five_plus_copy_previous_q9"],
            supports["all_five_plus_copy_previous_q8"]),
        "primary_c0_t0_paired_support": (
            ["C0", "T0"], supports["primary_c0_t0_q9"], supports["primary_c0_t0_q8"]),
        "primary_c0_t0_plus_copy_previous_same_support": (
            ["C0", "T0", "copy_previous"], supports["primary_c0_t0_plus_copy_previous_q9"],
            supports["primary_c0_t0_plus_copy_previous_q8"]),
        "pair_t0_t1_support": (["T0", "T1"], supports["pair_t0_t1_q9"], supports["pair_t0_t1_q8"]),
        "pair_c0_c1_support": (["C0", "C1"], supports["pair_c0_c1_q9"], supports["pair_c0_c1_q8"]),
        "pair_o0_c0_support": (["O0", "C0"], supports["pair_o0_c0_q9"], supports["pair_o0_c0_q8"]),
    }
    support_results = {}
    for name, (arms, q9, q8) in groups.items():
        support_results[name] = {
            "arms": arms,
            "q9_person_months": len(q9),
            "q8_person_months": len(q8),
            "q9_positions": [list(x) for x in sorted(q9)],
            "q8_positions": [list(x) for x in sorted(q8)],
            "summaries": _metrics(cases, arms, months, repeats, q9, q8),
        }

    status_counts = {arm: dict(counter) for arm, counter in counts.items()}
    new_account = queue.account(new_intents, new_replies)
    repair_account = queue.account(repair_intents, repair_replies)
    old_account = queue.account(list(old_intents.values()), list(old_replies.values()))
    result = {
        "schema": "sce_media_timing_terminal_evaluation/v1",
        "status": "completed_media_timing_terminal_evaluation",
        "new_api_calls": 0,
        "protocol": protocol,
        "mapping": {"logical_positions": len(ctx["positions"]),
                    "new_request_slots": len(ctx["slots"]),
                    "position_status_counts": dict(source_counts),
                    "reuse_exact_and_hold_are_from_old_v3_queue": True,
                    "new_prompt_aliases_share_one_archived_response": True,
                    "repair_targets": len(repair_targets),
                    "repair_attempts": len(repair_intents),
                    "maximum_attempts_per_new_slot": 2,
                    "old_failures_entered_repair": False},
        "coverage": status_counts,
        "support": {name: {"q9_person_months": len(value[1]), "q8_person_months": len(value[2]),
                            "arms": value[0]} for name, value in groups.items()},
        "support_summaries": support_results,
        "execution": {"new_requests": new_account, "repair_requests": repair_account,
                      "total_reported_cost_usd": accounting["total_reported_cost_usd"],
                      "total_spent_or_reserved_usd": accounting["total_spent_or_reserved_usd"],
                      "unknown_fee_reservation_usd": new_account["unknown_fee_reservation_usd"] + repair_account["unknown_fee_reservation_usd"],
                      "maximum_physical_attempts": 2 * protocol["planned_calls"],
                      "old_v3_archive": old_account},
        "target_inputs": truth_hashes,
        "scoring": {"q9": "Old V3 model_action and previous_action with shared cognition frozen scoring.",
                    "q8": "Independent point-estimate support and summaries.",
                    "missing": "Old attempted failures, new failures, and absent replies remain missing; no imputation."},
        "limits": ["Exploratory seven-month window previously inspected in A82; no independent time validation.",
                   "2021 subset is available by month in each support summary; no post-hoc outcome-based roster change.",
                   "O0 is the exact archived Q3 arm answer, never substituted with another old arm."],
    }
    out.mkdir(parents=True, exist_ok=False)
    dump(out / "summary.json", result)
    dump(out / "cases_private.json", cases)
    summary_lines = [
        "# 个人日期 × 警示 2×2：执行后离线摘要", "",
        "评价只复用已归档旧答和新请求；目标真值仅在本评价层读取。每个支持集合都保留失败与缺失。", "",
        f"- 主批：{new_account['attempts']:,}/{len(ctx['slots']):,}次；回包{new_account['completed']:,}；报告费用${new_account['reported_cost_usd']:.4f}，计及预留${new_account['spent_or_reserved_usd']:.4f}。",
        f"- 技术补批：{repair_account['attempts']:,}次（目标{len(repair_targets):,}，最多一次/新槽）；报告费用${repair_account['reported_cost_usd']:.4f}，计及预留${repair_account['spent_or_reserved_usd']:.4f}；主+补合计${accounting['total_reported_cost_usd']:.4f}报告、${accounting['total_spent_or_reserved_usd']:.4f}计及预留。",
        f"- 逻辑位置：{len(ctx['positions']):,}；O0＋四臂的共同Q9支持：{len(supports['all_five_q9']):,}人月；Q8：{len(supports['all_five_q8']):,}人月。",
        f"- C0/T0主要成对Q9支持：{len(supports['primary_c0_t0_q9']):,}人月；加入照抄上期后同支持：{len(supports['primary_c0_t0_plus_copy_previous_q9']):,}人月。",
        "- summary.json按支持集合、逐月、逐遍报告Q9和独立Q8摘要；copy_previous仅在相同支持中比较。", "",
        "不要把共同支持外的缺失答卷填补为旧答案或零值。O0固定为同月、同人、同遍的旧Q3归档。", "",
    ]
    for label in ("all_five_common_support", "primary_c0_t0_paired_support",
                  "four_new_arms_common_support", "pair_t0_t1_support", "pair_c0_c1_support",
                  "pair_o0_c0_support", "primary_c0_t0_plus_copy_previous_same_support"):
        block = support_results[label]
        summary_lines.append(f"## {label}（Q9 {block['q9_person_months']}人月；Q8 {block['q8_person_months']}人月）")
        for arm in block["arms"]:
            cells = block["summaries"][arm]["overall"]["auxiliary_survey_weighted"]["q9"]["aggregate_equal_month_repeat_cells"]
            mae = cells.get("q9_center_mae_pp")
            display = "缺失" if mae is None else f"{mae:.3f}"
            summary_lines.append(f"- **{arm}**：Q9中心MAE {display}pp（辅助设计权重）；逐月/逐遍与Q8见summary.json。")
        summary_lines.append("")
    (out / "RESULTS.md").write_text("\n".join(summary_lines), encoding="utf-8")
    dump(out / "manifest.json", {"new_api_calls": 0,
         "files_sha256": {name: sha(out / name) for name in ("summary.json", "cases_private.json", "RESULTS.md")},
         "target_inputs": truth_hashes,
         "run_config_sha256": sha(folder / "config.json")})
    return {"status": result["status"], "out": str(out), "new_api_calls": 0,
            "logical_positions": len(ctx["positions"]), "new_request_slots": len(ctx["slots"]),
            "all_five_q9_person_months": len(supports["all_five_q9"]),
            "primary_c0_t0_q9_person_months": len(supports["primary_c0_t0_q9"])}
