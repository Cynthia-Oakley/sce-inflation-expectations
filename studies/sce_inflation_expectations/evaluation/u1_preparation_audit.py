"""Independent read-only acceptance of Kimi's prepared U1 state/guided inputs.

This verifies preparation artifacts, not runtime delivery or permission to run.
No API client, credentials or simulation configuration are accessed.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .behavior_comparison import BIN_FIELDS, dump, previous_month, sha
from ..scoring.sce_q9_frozen import provenance, score_q9_frozen

QUESTION = "Question 1 (point estimate):"
STATE = "Your survey history (a summary of your own earlier answers):"
GUIDANCE = ("One hypothesis about how people usually update, which we ask you to "
            "consider as a possibility rather than a rule: people move only partway "
            "from their last answer back toward their own typical level in a single "
            "month — roughly halfway — unless recent information or their own "
            "situation suggests a bigger or smaller change.")
ARMS = ("own_state", "own_state_guided")


@lru_cache(maxsize=None)
def fit(probabilities):
    p = np.asarray(probabilities, float)
    if (len(p) != 10 or not np.isfinite(p).all() or (p < 0).any()
            or (p > 100).any() or abs(p.sum()-100) > 1e-6):
        return None
    result = score_q9_frozen(p.tolist())
    if result.status != "ok" or any(v is None or not np.isfinite(v)
                                    for v in (result.mean, result.p25, result.p75)):
        return None
    return float(result.mean), float(result.p25), float(result.p75)


def reconstruct_state(frame, uid, month):
    """No Kimi construction function is called; official derived fields unused."""
    past = frame[(frame.userid == uid) & (frame.date < month)].sort_values("date")
    previous = past[past.date == previous_month(month)]
    if len(previous) != 1:
        raise ValueError("Exact single calendar-previous answer required")
    prior = fit(tuple(previous.iloc[0][BIN_FIELDS].to_numpy(float)))
    if prior is None:
        raise ValueError("Calendar-previous probabilities not scorable")
    historical = [fit(tuple(row[BIN_FIELDS].to_numpy(float))) for _, row in past.iterrows()]
    centers = [s[0] for s in historical if s is not None]
    return {"source_month": previous_month(month), "center": prior[0],
            "low": prior[1], "high": prior[2], "n_earlier_valid": len(centers),
            "anchor": float(np.mean(centers)) if len(centers) >= 2 else None}


def independent_block(state, guided=False):
    source = f"{state['source_month']//100:04d}-{state['source_month']%100:02d}"
    lines = [STATE,
             f"- Last survey ({source}): your probability answers implied an average "
             f"expectation of about {state['center']:.1f}%, and about a 50% chance "
             f"of inflation between {state['low']:.1f}% and {state['high']:.1f}%."]
    if state["anchor"] is not None:
        lines.append(f"- Over your past {state['n_earlier_valid']} surveys, this "
                     f"probability-implied average has typically been around {state['anchor']:.1f}%.")
    if guided and state["anchor"] is not None:
        lines.extend(["", GUIDANCE])
    return "\n".join(lines) + "\n\n"


def verify_messages(base, state_messages, guided_messages, state):
    """Check whole messages, not just the presence of new keywords."""
    if len(base) != 1 or base[0]["role"] != "user":
        raise ValueError("Unexpected frozen base message shape")
    text = base[0]["content"]
    if text.count(QUESTION) != 1 or STATE in text:
        raise ValueError("Base has missing/repeated questionnaire or state")
    before, after = text.split(QUESTION, 1)
    for actual, guidance in ((state_messages, False), (guided_messages, True)):
        expected = deepcopy(base)
        block = independent_block(state, guidance)
        expected[0]["content"] = before + block + QUESTION + after
        if actual != expected:
            raise ValueError("Prepared message changed old inputs or registered state/guidance")
    return {"guidance_active": state["anchor"] is not None,
            "same_message_without_anchor": state_messages == guided_messages,
            "kept_base": True, "kept_questionnaire": True}


def run(root, bundle, out):
    root, bundle, out = map(lambda p: Path(p).resolve(), (root, bundle, out))
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("Require a fresh ignored audit directory")
    summary = json.loads((bundle / "summary.json").read_text())
    manifest = json.loads((bundle / "manifest.json").read_text())["output_file_sha256"]
    sources = summary["source_sha256"]
    for name, digest in manifest.items():
        if sha(bundle / name) != digest:
            raise ValueError("Prepared output hash changed: " + name)
    for name, digest in {**sources, **summary["code_sha256"]}.items():
        if sha(root / name) != digest:
            raise ValueError("Registered input/code hash changed: " + name)
    if not provenance()["live_matches_pinned"]:
        raise ValueError("Frozen scorer drift")
    candidate = root / "outputs/sce_prior_preparation_20261013_v4"
    trial = root / "outputs/sce_prior_trial_20261013_v2"
    links = json.loads((trial / "evaluation_links_private.json").read_text())
    registry = {(str(r["month"]), r["prepared_agent_id"]): r for r in links}
    frame = pd.read_parquet(candidate / "labeled_reference_private.parquet")
    if frame.duplicated(["userid", "date"]).any():
        raise ValueError("Duplicate reference person-month")
    saved_states = json.loads((bundle / "state_values_private.json").read_text())
    if len(saved_states) != 48 or len(registry) != 48:
        raise ValueError("Expected frozen 48-person-month cohort")
    previews, originals = {}, {}
    for month in summary["months"]:
        for arm in ARMS:
            rows = json.loads((bundle / month / f"preview_{arm}.json").read_text())
            if len(rows) != 12 or len({r["agent_id"] for r in rows}) != 12:
                raise ValueError("Expected 12 unique prepared cases per month/arm")
            previews[month, arm] = {r["agent_id"]: r for r in rows}
        originals[month] = {r["agent_id"]: r for r in
                            json.loads((trial / month / "preview_own_previous.json").read_text())}
    counts = Counter()
    max_difference = 0.
    frozen_snapshot = {str(bundle.relative_to(root)) + "/" + name: digest
                       for name, digest in manifest.items()}
    frozen_snapshot.update({str(bundle.relative_to(root)) + "/manifest.json": sha(bundle / "manifest.json"),
                            summary["spec"]: sha(root / summary["spec"])})
    private = []
    for saved in saved_states:
        month, aid = str(saved["month"]), saved["agent_id"]
        link = registry[month, aid]
        uid = int(link["source_agent_id"].removeprefix("sce_u"))
        if uid != int(saved["source_userid"]):
            raise ValueError("Saved state belongs to a different respondent")
        state = reconstruct_state(frame, uid, int(month))
        for key in state:
            if state[key] is None:
                if saved[key] is not None:
                    raise ValueError("Unexpected saved history anchor")
            else:
                difference = abs(state[key] - saved[key])
                max_difference = max(max_difference, difference)
                if difference > 1e-9:
                    raise ValueError("State values do not independently recompute")
        old = originals[month][link["agent_id"]]["messages"]
        pair = [previews[month, arm][aid] for arm in ARMS]
        checks = verify_messages(old, pair[0]["messages"], pair[1]["messages"], state)
        if saved["guidance_active"] != checks["guidance_active"]:
            raise ValueError("Saved guidance eligibility differs")
        for arm, row in zip(ARMS, pair):
            digest = hashlib.sha256(json.dumps(row["messages"], ensure_ascii=False).encode()).hexdigest()
            if digest != row["prompt_sha256"] or digest != saved["prompt_sha256"][arm]:
                raise ValueError("Prepared prompt hash differs")
            text = row["messages"][0]["content"]
            if any(term in text for term in (aid, link["agent_id"], link["source_agent_id"],
                                             '"userid"', '"weight"', "Q9_mean")):
                raise ValueError("Internal identity/evaluation field in prompt")
        # Independent current/future and derived-field perturbation; not a rerun
        # of Kimi's own assertions or a change to the reference file.
        changed = frame[frame.userid == uid].copy()
        changed.loc[changed.date >= int(month), BIN_FIELDS] = np.nan
        for field in ("Q9_mean", "Q9_iqr", "weight", "Q8v2part2"):
            if field in changed:
                changed[field] = np.nan
        if reconstruct_state(changed, uid, int(month)) != state:
            raise ValueError("Current/future/derived fields affect reconstructed state")
        counts["checked_cases"] += 1
        counts["active" if state["anchor"] is not None else "inactive"] += 1
        private.append({"month": int(month), "agent_id": link["agent_id"], "userid": uid,
                        "guidance_active": state["anchor"] is not None})
    for name, digest in {**sources, **summary["code_sha256"], **frozen_snapshot}.items():
        if sha(root / name) != digest:
            raise ValueError("Artifacts changed during read-only audit")
    verdict = {"status": "prepared_inputs_passed_not_runtime_acceptance",
               "completed_at": datetime.now(timezone.utc).isoformat(),
               "bundle": str(bundle.relative_to(root)), "counts": dict(counts),
               "prepared_prompts": counts["checked_cases"] * 2,
               "planned_requests": counts["checked_cases"] * 2 * 2,
               "state_numeric_max_difference": max_difference,
               "base_preservation_checks": counts["checked_cases"] * 2,
               "current_future_derived_perturbation_checks": counts["checked_cases"],
               "output_hashes_checked": len(manifest), "input_hashes_checked": len(sources),
               "prepared_snapshot_sha256": frozen_snapshot, "source_sha256": sources,
               "preparation_code_sha256": summary["code_sha256"],
               "audit_code_sha256": {p: sha(root / p) for p in (
                   "studies/sce_inflation_expectations/evaluation/u1_preparation_audit.py",
                   "studies/sce_inflation_expectations/evaluation/behavior_comparison.py",
                   "scripts/audit_sce_u1_preparation.py")},
               "scorer": provenance(),
               "interpretation": ["U1s versus old U0 measures a state-information package, including additional multi-survey history, not pure wording or isolated cognition.",
                                  "U1g versus U1s isolates the added hypothesis sentence conditional on matched runtime/model/information; all 48 person-months primary, 42 guidance-active secondary.",
                                  "Six unanchored cases receive identical prompts; generation differences there are not an effect of guidance.",
                                  "Matching output schemas permit common report processing; they do not imply statistically additive/orthogonal effects."],
               "remaining": ["Independent actual engine dry-run receipt/prompt hashes/config/call count", "Formal experiment/authorization alignment", "Old joint draft synchronized or retired"],
               "new_api_calls": 0, "kimi_files_modified": False}
    out.mkdir(parents=True)
    dump(out / "summary.json", verdict)
    dump(out / "guidance_membership_private.json", private)
    dump(out / "manifest.json", {"files_sha256": {p.name: sha(p) for p in out.iterdir() if p.is_file()}})
    return verdict
