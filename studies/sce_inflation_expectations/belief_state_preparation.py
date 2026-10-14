"""U1 explicit personal-state arms: offline preparation only. No API client.

Spec: docs/workstreams/20261013_behavior/kimi_u1_input_spec.md (v2, 2026-10-13).

v2 per Codex review (codex_kimi_u1_review_20261013.md): the base is the
executed own_previous arm (full raw t-1 answer kept: Q8 point + Q9 bins);
the state block is an *added*, source-labeled summary, not a replacement.
Two arms: own_state (U1s = U0 + state summary) and own_state_guided
(U1g = U1s + one update-hypothesis sentence, suppressed without an anchor).
Zero network, zero credentials, zero API calls in this module.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .prior_belief_preparation import MARKER, PRIOR_MARKER, month_offset, sha, dump, valid_bins
from .scoring.sce_q9_frozen import provenance, score_q9_frozen

STATE_MARKER = "Your survey history"
MIN_HISTORY = 2
ARMS = ("own_state", "own_state_guided")
MONTHS = ("202203", "202209", "202303", "202403")
CANDIDATE = "outputs/sce_prior_preparation_20261013_v4"
TRIAL = "outputs/sce_prior_trial_20261013_v2"

FORBIDDEN_TERMS = ("Q9_mean", '"weight"', '"userid"')


def _fmt(x: float) -> str:
    return f"{x:.1f}"


def compute_person_state(frame: pd.DataFrame, userid: int, target_month) -> dict | None:
    """S1/S2/S3 for one selected person-month from their own earlier answers.

    Returns None (explicit, countable drop) when the t-1 answer cannot be
    scored by the frozen algorithm; never falls back to another method.
    """
    target_month = int(target_month)
    rows = frame.loc[frame.userid.eq(userid)].sort_values("date", kind="stable")
    prev_date = month_offset(target_month, -1)
    prev = rows.loc[rows.date.eq(prev_date)]
    if len(prev) != 1:
        raise ValueError("selected case must have exactly one t-1 row")
    prev = prev.iloc[0]
    bins = [float(prev[f"Q9_bin{i}"]) for i in range(1, 11)]
    if not valid_bins(bins):
        raise ValueError("selected case t-1 bins must be legal")
    scored = score_q9_frozen(bins)
    if scored.status != "ok" or scored.mean is None or not np.isfinite(scored.mean):
        return None
    if any(v is None or not np.isfinite(v) for v in (scored.p25, scored.p75)):
        return None
    centers = []
    for _, r in rows.loc[rows.date.lt(target_month)].iterrows():
        b = [float(r[f"Q9_bin{i}"]) for i in range(1, 11)]
        if not valid_bins(b):
            continue
        s = score_q9_frozen(b)
        if s.status == "ok" and s.mean is not None and np.isfinite(s.mean):
            centers.append(float(s.mean))
    anchor = float(np.mean(centers)) if len(centers) >= MIN_HISTORY else None
    return {"source_month": prev_date, "center": float(scored.mean),
            "low": float(scored.p25), "high": float(scored.p75),
            "anchor": anchor, "n_earlier_valid": len(centers)}


def render_state_block(state: dict, target_month, guidance: bool = False) -> str:
    """The spec section-3 prompt block (English; US household context).

    guidance=True renders the U1g update-hypothesis sentence and requires an
    anchor (the sentence refers to "your own typical level"); callers suppress
    it for anchor-less cases, mirroring the C1 insufficient-history fallback.
    """
    target_month = int(target_month)
    if state["source_month"] != month_offset(target_month, -1):
        raise ValueError("state must describe exactly the previous calendar month")
    for key in ("center", "low", "high"):
        if not np.isfinite(state[key]) or abs(state[key]) > 100:
            raise ValueError("implausible state value")
    if state["low"] > state["high"]:
        raise ValueError("state quartiles inverted")
    if guidance and state["anchor"] is None:
        raise ValueError("the update-hypothesis sentence requires a personal anchor")
    source = f"{state['source_month'] // 100:04d}-{state['source_month'] % 100:02d}"
    lines = ["Your survey history (a summary of your own earlier answers):",
             f"- Last survey ({source}): your probability answers implied an average "
             f"expectation of about {_fmt(state['center'])}%, and about a 50% chance "
             f"of inflation between {_fmt(state['low'])}% and {_fmt(state['high'])}%."]
    if state["anchor"] is not None:
        if not np.isfinite(state["anchor"]) or abs(state["anchor"]) > 100:
            raise ValueError("implausible anchor")
        lines.append(f"- Over your past {int(state['n_earlier_valid'])} surveys, this "
                     f"probability-implied average has typically been around "
                     f"{_fmt(state['anchor'])}%.")
    if guidance:
        lines.append("")
        lines.append("One hypothesis about how people usually update, which we ask you to "
                     "consider as a possibility rather than a rule: people move only partway "
                     "from their last answer back toward their own typical level in a single "
                     "month — roughly halfway — unless recent information or their own "
                     "situation suggests a bigger or smaller change.")
    return "\n".join(lines) + "\n\n"


def add_state_block(messages, state: dict, target_month, guidance: bool = False):
    """Insert the state block between the kept raw prior answer and the questionnaire.

    The base must be an own_previous message: exactly one PRIOR_MARKER, exactly
    one questionnaire MARKER, and no pre-existing state block.
    """
    result = deepcopy(messages)
    if len(result) != 1 or set(result[0]) != {"role", "content"} or result[0]["role"] != "user":
        raise ValueError("Frozen one-user-message format required")
    text = result[0]["content"]
    if text.count(MARKER) != 1 or text.count(PRIOR_MARKER) != 1 or STATE_MARKER in text:
        raise ValueError("Base must carry the raw prior answer exactly once and no state block")
    block = render_state_block(state, target_month, guidance=guidance)
    before, after = text.split(MARKER, 1)
    result[0]["content"] = before + block + MARKER + after
    return result, block


def prepare(root: Path, out: Path) -> dict:
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("Use a fresh ignored output directory")
    protected = json.loads((root / "docs/sources/sol_handoff_protected_files_20261010.json").read_text())["files_sha256"]
    if any(sha(root / p) != h for p, h in protected.items()):
        raise ValueError("Protected pending work changed")
    scorer = provenance()
    if not scorer["live_matches_pinned"]:
        raise ValueError("Frozen scorer drift")
    candidate = root / CANDIDATE
    csum = json.loads((candidate / "summary.json").read_text())
    for name in ("labeled_reference_private.parquet", "selection_links_private.json",
                 "candidate_cases_private.jsonl"):
        if sha(candidate / name) != csum["output_file_sha256"][name]:
            raise ValueError("prior-trial candidate input changed: " + name)
    trial = root / TRIAL
    manifest = json.loads((trial / "trial_manifest.json").read_text())
    for name in ("evaluation_links_private.json",) + tuple(f"{m}/preview_own_previous.json" for m in MONTHS):
        if sha(trial / name) != manifest["prepared_file_sha256"][name]:
            raise ValueError("executed trial artifact changed: " + name)
    links = json.loads((trial / "evaluation_links_private.json").read_text())
    executed = {}  # (month, candidate agent_id) -> executed own_previous messages
    for link in links:
        previews = json.loads((trial / link["month"] / "preview_own_previous.json").read_text())
        by_id = {p["agent_id"]: p for p in previews}
        if link["agent_id"] not in by_id:
            raise ValueError("executed trial preview missing linked agent")
        sent = by_id[link["agent_id"]]
        digest = hashlib.sha256(json.dumps(sent["messages"], ensure_ascii=False).encode()).hexdigest()
        if digest != sent["prompt_sha256"]:
            raise ValueError("executed trial prompt hash mismatch")
        executed[(link["month"], link["prepared_agent_id"])] = sent["messages"]
    frame = pd.read_parquet(candidate / "labeled_reference_private.parquet")
    selection = json.loads((candidate / "selection_links_private.json").read_text())
    cases = [json.loads(s) for s in (candidate / "candidate_cases_private.jsonl").read_text().splitlines()]
    base_messages = {}
    for c in cases:
        if c["arm"] == "own_previous" and c["repeat"] == 1:
            base_messages[(c["target_month"], c["agent_id"])] = c["messages"]
    if len(selection) != 48 or len(base_messages) != 48:
        raise ValueError("expected the executed 48 person-month selection")
    out.mkdir(parents=True)
    previews = {arm: [] for arm in ARMS}
    states, dropped = [], []
    for row in sorted(selection, key=lambda r: (r["month"], r["agent_id"])):
        month, sid = row["month"], row["agent_id"]
        key = (month, sid)
        if key not in base_messages:
            raise ValueError("missing own-previous base for selected case")
        base = base_messages[key]
        if key in executed and base != executed[key]:
            raise ValueError("candidate own_previous differs from the executed trial prompt")
        state = compute_person_state(frame, int(row["source_userid"]), month)
        if state is None:
            dropped.append({"month": month, "agent_id": sid, "reason": "t-1 answer not scorable by frozen algorithm"})
            continue
        entry = {"month": month, "agent_id": sid, "source_userid": int(row["source_userid"]),
                 "base_agent_id": row["base_agent_id"], **state,
                 "guidance_active": state["anchor"] is not None, "prompt_sha256": {}}
        for arm in ARMS:
            guided = arm == "own_state_guided" and state["anchor"] is not None
            messages, block = add_state_block(base, state, month, guidance=guided)
            if messages[0]["content"].replace(block, "", 1) != base[0]["content"]:
                raise ValueError("Common P/E, raw prior answer or question changed")
            if messages[0]["content"].split(MARKER, 1)[1] != base[0]["content"].split(MARKER, 1)[1]:
                raise ValueError("Questionnaire changed")
            text = json.dumps(messages, ensure_ascii=False)
            if any(t in text for t in FORBIDDEN_TERMS) or row["base_agent_id"] in text or sid in text \
                    or f"sce_u{row['source_userid']}" in text:
                raise ValueError("Internal identity or evaluation field in message")
            digest = hashlib.sha256(json.dumps(messages, ensure_ascii=False).encode()).hexdigest()
            previews[arm].append({"month": month, "agent_id": sid, "messages": messages,
                                  "prompt_sha256": digest})
            entry["prompt_sha256"][arm] = digest
        states.append(entry)
    (out / "state_values_private.json").write_text(json.dumps(states, ensure_ascii=False, indent=2) + "\n")
    for month in MONTHS:
        part = out / month
        part.mkdir()
        for arm in ARMS:
            dump(part / f"preview_{arm}.json", [p for p in previews[arm] if p["month"] == month])
    anchored = next(s for s in states if s["anchor"] is not None)
    for arm, name in (("own_state", "preview_sample_state.txt"),
                      ("own_state_guided", "preview_sample_guided.txt")):
        sample = next(p for p in previews[arm]
                      if p["month"] == anchored["month"] and p["agent_id"] == anchored["agent_id"])
        (out / name).write_text(sample["messages"][0]["content"] + "\n")
    summary = {
        "status": "offline_preparation_completed_no_api_calls",
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "spec": "docs/workstreams/20261013_behavior/kimi_u1_input_spec.md",
        "spec_version": "v2",
        "arms": {arm: {"planned_requests": len(previews[arm]) * 2,
                       "note": "48 person-months x 2 repeats; both arms = 192 requests"} for arm in ARMS},
        "months": list(MONTHS), "selected_cases": len(selection),
        "prepared_cases_per_arm": {arm: len(previews[arm]) for arm in ARMS},
        "dropped_cases": dropped,
        "state_definition": {
            "S1_center": "frozen-scorer mean of own t-1 ten-bin answer, verbalized as probability-implied average (NOT the Q8 point answer, which stays in the kept raw prior block)",
            "S2_uncertainty": "frozen-scorer p25/p75 of own t-1 ten-bin answer, verbalized as an about-50% probability interval",
            "S3_anchor": f"expanding mean of own earlier valid frozen-scorer centers; omitted when < {MIN_HISTORY}",
            "update_hypothesis_sentence": "U1g only; verbal 'roughly halfway' = lambda 0.50 (train-selected), framed as a hypothesis; suppressed when no anchor",
        },
        "anchor_coverage": float(np.mean([s["anchor"] is not None for s in states])) if states else None,
        "guidance_active_cases": int(sum(s["guidance_active"] for s in states)),
        "leakage_guards": [
            "no current-month or future answer enters any state value (unit-tested)",
            "no SCE aggregate statistic enters the block",
            "forbidden identity/evaluation terms scanned per message",
            "base is the executed own_previous prompt, byte-checked against the trial archive",
            "questionnaire tail byte-identical to the executed own_previous base",
        ],
        "new_api_calls": 0,
        "scorer": {"live_matches_pinned": scorer["live_matches_pinned"]},
        "source_sha256": {
            **{CANDIDATE + "/" + n: sha(candidate / n) for n in
               ("summary.json", "labeled_reference_private.parquet",
                "selection_links_private.json", "candidate_cases_private.jsonl")},
            TRIAL + "/trial_manifest.json": sha(trial / "trial_manifest.json"),
            TRIAL + "/evaluation_links_private.json": sha(trial / "evaluation_links_private.json"),
            **{TRIAL + f"/{m}/preview_own_previous.json": sha(trial / m / "preview_own_previous.json")
               for m in MONTHS},
        },
        "code_sha256": {p: sha(root / p) for p in (
            "studies/sce_inflation_expectations/belief_state_preparation.py",
            "scripts/prepare_sce_u1a_state.py")},
    }
    dump(out / "summary.json", summary)
    manifest_out = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob("*")) if p.is_file()}
    dump(out / "manifest.json", {"output_file_sha256": manifest_out,
                                 "note": "written last; summary.json deliberately excludes its own hash"})
    print(json.dumps({"output": str(out), "prepared_per_arm": {a: len(p) for a, p in previews.items()},
                      "dropped": len(dropped), "new_api_calls": 0}))
    return summary
