"""Pure fixed-household state transitions for weekly SCE simulations.

The caller owns release-cycle detection, external joint-donor calibration,
transport, retries, and independent news-memory updates. This module accepts
only timezone-aware instants and a final outcome for each completed cutoff; it
never sends or retries a request. A newly public cycle can replace the paired
Q8/Q9 starting fields while preserving the household's separate news memory.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from collections.abc import Mapping

from .state_continuity_inputs import density_center
from ..q9_normalization import normalize_bins


STATE_SCHEMA = "weekly_household_state_v1"
_SOURCE_LABELS = {
    "own_observed": "your own earlier survey answer",
    "synthetic_donor": "assigned synthetic starting belief; not your actual survey answer",
    "calibrated_synthetic_donor": "new-cycle calibrated synthetic starting belief; not your actual survey answer",
    "simulated": "your answer from an earlier step of this simulation",
}


def _instant(value: str | datetime) -> datetime:
    """Parse an aware instant and normalize it to UTC for stable comparisons."""
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("ISO-8601 timezone-aware cutoff required") from exc
    else:
        raise ValueError("ISO-8601 timezone-aware cutoff required")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Timezone-aware cutoff required")
    return result.astimezone(timezone.utc)


def _iso(value: str | datetime) -> str:
    return _instant(value).isoformat().replace("+00:00", "Z")


def _cycle_key(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Nonempty public SCE cycle key required")
    return value


def _field_value(field: str, value):
    if field == "q8":
        if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 100:
            raise ValueError("Finite signed Q8 point within [-100, 100] required")
        return float(value)
    if field == "q9":
        return normalize_bins(value)["bins"]
    raise ValueError("Only Q8 and Q9 fields are supported")


def _joint_fields(fields: Mapping, effective_at: str | datetime) -> dict:
    """Validate an externally supplied *paired* starting Q8/Q9 state."""
    if not isinstance(fields, Mapping) or set(fields) != {"q8", "q9"}:
        raise ValueError("A complete joint Q8/Q9 starting state is required")
    cutoff = _instant(effective_at)
    result = {}
    for key in ("q8", "q9"):
        field = fields[key]
        if not isinstance(field, Mapping):
            raise ValueError("Each Q8/Q9 starting field must be an object")
        kind = field.get("source_kind")
        if kind not in _SOURCE_LABELS or kind == "simulated":
            raise ValueError("Starting source must be a declared observed or synthetic source")
        # A donor manifest may provide only YYYYMM source_period. That period
        # is provenance, not the weekly transition clock; effective_at is when
        # the complete synthetic pair enters the active cycle.
        source_at = _instant(field.get("source_at", effective_at))
        if source_at > cutoff:
            raise ValueError("Starting belief cannot come from after its effective cutoff")
        result[key] = {
            "value": _field_value(key, field.get("value")),
            "source_kind": kind,
            "source_at": source_at.isoformat().replace("+00:00", "Z"),
        }
        if "source_period" in field:
            result[key]["source_period"] = deepcopy(field["source_period"])
    if (result["q8"]["source_kind"] != result["q9"]["source_kind"]
            or result["q8"]["source_at"] != result["q9"]["source_at"]):
        raise ValueError("Initial Q8/Q9 must be a joint pair from the same source and instant")
    if result["q8"].get("source_period") != result["q9"].get("source_period"):
        raise ValueError("Initial Q8/Q9 must share the same source period")
    return result


def _q9_center(value, bins):
    if value is None:
        return density_center(tuple(bins))
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("A supplied Q9 center must be finite")
    return float(value)


def initialize_state(agent_id: str, cycle_key: str, effective_at: str | datetime,
                     fields: Mapping, *, center: float | None = None, news_memory=None) -> dict:
    """Create one household's state at a calibration/origin instant.

    ``effective_at`` marks when the joint starting pair may be used. The first
    weekly forecast may use this information at that instant; subsequent
    forecasts must be strictly later than the preceding forecast cutoff.
    """
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("Stable household identity required")
    origin = _iso(effective_at)
    paired_fields = _joint_fields(fields, origin)
    initial_center = _q9_center(center, paired_fields["q9"]["value"])
    history_centers = ([] if initial_center is None else
                       [{"source_at": origin, "center": initial_center,
                         "source_kind": "cycle_start_joint_prior"}])
    return {
        "schema": STATE_SCHEMA,
        "agent_id": agent_id,
        "cycle_key": _cycle_key(cycle_key),
        "cycle_started_at": origin,
        "fields": paired_fields,
        "history_centers": history_centers,
        "steps": [],
        "last_cutoff": None,
        "cycle_archives": [],
        # News memory is deliberately opaque to this state machine.
        "news_memory": deepcopy(news_memory),
    }


def _validate_state(state: Mapping) -> None:
    if not isinstance(state, Mapping) or state.get("schema") != STATE_SCHEMA:
        raise ValueError("Weekly household state schema required")
    if not isinstance(state.get("agent_id"), str) or not state["agent_id"]:
        raise ValueError("Stable household identity required")
    _cycle_key(state.get("cycle_key"))
    _instant(state.get("cycle_started_at"))
    if not isinstance(state.get("fields"), Mapping) or set(state["fields"]) != {"q8", "q9"}:
        raise ValueError("Complete current Q8/Q9 state required")
    for key in ("q8", "q9"):
        field = state["fields"][key]
        if not isinstance(field, Mapping) or field.get("source_kind") not in _SOURCE_LABELS:
            raise ValueError("Declared Q8/Q9 state source required")
        _field_value(key, field.get("value"))
        _instant(field.get("source_at"))
    last = state.get("last_cutoff")
    if last is not None:
        _instant(last)
    if not isinstance(state.get("history_centers"), list) or not isinstance(state.get("steps"), list):
        raise ValueError("Weekly state histories must be lists")
    for row in state["history_centers"]:
        if (not isinstance(row, Mapping) or type(row.get("center")) not in (int, float)
                or not math.isfinite(row["center"])):
            raise ValueError("Finite current-cycle history centers required")
        _instant(row.get("source_at"))


def _decode_response(raw_response):
    if isinstance(raw_response, str):
        try:
            value = json.loads(raw_response)
        except (ValueError, TypeError):
            return None
    else:
        value = raw_response
    return value if isinstance(value, Mapping) else None


def advance_state(previous: Mapping, raw_response, cutoff: str | datetime, *,
                  technical_failure: bool = False, center: float | None = None) -> dict:
    """Apply one final outcome at a later weekly cutoff.

    Each answer field is validated independently. Invalid/missing fields keep
    this same household's previous value. The cutoff is consumed exactly once
    even when a final technical failure is supplied; repeating that cutoff is
    rejected, so callers must resolve unknown in-flight work outside this
    module before advancing.
    """
    _validate_state(previous)
    if type(technical_failure) is not bool:
        raise ValueError("technical_failure must be boolean")
    now = _instant(cutoff)
    prior_cutoff = _instant(previous["last_cutoff"]) if previous["last_cutoff"] else None
    if prior_cutoff is not None and now <= prior_cutoff:
        raise ValueError("Same-household weekly cutoff must be strictly later than its previous step")
    if now < _instant(previous["cycle_started_at"]):
        raise ValueError("Weekly cutoff precedes the active public SCE cycle")

    result = deepcopy(previous)
    obj = None if technical_failure else _decode_response(raw_response)
    updated = {"q8": False, "q9": False}
    normalized = False

    if obj is not None:
        point = obj.get("point_pct")
        if type(point) in (int, float) and math.isfinite(point) and abs(point) <= 100:
            result["fields"]["q8"] = {
                "value": float(point), "source_kind": "simulated", "source_at": _iso(now),
            }
            updated["q8"] = True

        raw_q9 = obj.get("q9")
        try:
            if not isinstance(raw_q9, Mapping) or set(raw_q9) != {f"bin{i}" for i in range(1, 11)}:
                raise ValueError("Exactly ten named Q9 bins required")
            view = normalize_bins([raw_q9[f"bin{i}"] for i in range(1, 11)])
        except (ValueError, TypeError, KeyError):
            view = None
        if view is not None:
            bins = view["bins"]
            result["fields"]["q9"] = {
                "value": bins, "source_kind": "simulated", "source_at": _iso(now),
            }
            updated["q9"] = True
            normalized = bool(view["applied"])
            step_center = _q9_center(center, bins)
            if step_center is not None:
                # One successful Q9 center per unique (strictly increasing) cutoff.
                result["history_centers"].append({"source_at": _iso(now), "center": step_center,
                                                   "source_kind": "simulated"})

    result["last_cutoff"] = _iso(now)
    result["steps"].append({
        "cutoff": _iso(now),
        "cycle_key": result["cycle_key"],
        "field_updated_from_model": updated,
        "field_retained_as_explicit_fallback": {key: not value for key, value in updated.items()},
        "q9_proportional_normalization": normalized,
        "technical_failure": technical_failure,
    })
    return result


def reset_state(previous: Mapping, cycle_key: str, effective_at: str | datetime,
                fields: Mapping, *, center: float | None = None) -> dict:
    """Start a new public-release cycle using externally calibrated joint fields.

    The previous cycle's fields, weekly history and step ledger are retained in
    ``cycle_archives``. Current-cycle history restarts from the new joint prior
    (and its supplied/scored center, when available). The separate
    ``news_memory`` is copied unchanged and is never reset here.
    """
    _validate_state(previous)
    new_key = _cycle_key(cycle_key)
    if new_key == previous["cycle_key"]:
        raise ValueError("A public cycle reset requires a changed cycle key")
    now = _instant(effective_at)
    if now < _instant(previous["cycle_started_at"]):
        raise ValueError("New public cycle cannot precede the active cycle")
    if previous["last_cutoff"] is not None and now < _instant(previous["last_cutoff"]):
        raise ValueError("New public calibration cannot predate the previous weekly step")
    new_fields = _joint_fields(fields, now)
    initial_center = _q9_center(center, new_fields["q9"]["value"])
    new_history_centers = ([] if initial_center is None else
                           [{"source_at": _iso(now), "center": initial_center,
                             "source_kind": "cycle_start_joint_prior"}])
    result = deepcopy(previous)
    result["cycle_archives"].append({
        "cycle_key": previous["cycle_key"],
        "cycle_started_at": previous["cycle_started_at"],
        "cycle_ended_at": _iso(now),
        "fields_at_end": deepcopy(previous["fields"]),
        "history_centers": deepcopy(previous["history_centers"]),
        "steps": deepcopy(previous["steps"]),
        "last_cutoff": previous["last_cutoff"],
    })
    result.update({
        "cycle_key": new_key,
        "cycle_started_at": _iso(now),
        "fields": new_fields,
        "history_centers": new_history_centers,
        "steps": [],
        # Preserve the prior actual response cutoff to keep household time monotone.
        "last_cutoff": previous["last_cutoff"],
    })
    return result


def render_state(state: Mapping, cutoff: str | datetime) -> str:
    """Render same-household weekly belief and current-cycle history only."""
    _validate_state(state)
    now = _instant(cutoff)
    origin = _instant(state["cycle_started_at"])
    if now < origin:
        raise ValueError("Cannot render a state before its public cycle starts")
    if state["last_cutoff"] is not None and now <= _instant(state["last_cutoff"]):
        raise ValueError("Next weekly render cutoff must follow the previous household step")

    lines = ["Earlier belief state (expectations, not measured inflation):"]
    for key in ("q8", "q9"):
        field = state["fields"][key]
        source_at = _instant(field["source_at"])
        if source_at > now or (field["source_kind"] == "simulated" and source_at >= now):
            raise ValueError("Only strictly earlier simulated belief states can be rendered")
        payload = (field["value"] if key == "q8" else
                   {f"bin{i}": value for i, value in enumerate(field["value"], 1)})
        key_name = "point_pct" if key == "q8" else "q9"
        period_label = (f', source period {field["source_period"]}'
                        if field.get("source_period") is not None else "")
        lines.append(f'- {key.upper()}, source {field["source_at"]}{period_label}: '
                     f'{_SOURCE_LABELS[field["source_kind"]]}.')
        lines.append(json.dumps({key_name: payload}, ensure_ascii=False, allow_nan=False))

    centers = state["history_centers"]
    for row in centers:
        seen_at = _instant(row["source_at"])
        same_instant_origin = (seen_at == now == origin
                               and row.get("source_kind") == "cycle_start_joint_prior")
        if (seen_at > now or (seen_at == now and not same_instant_origin) or seen_at < origin):
            raise ValueError("Cycle history must be earlier than the forecast and inside its cycle")
    if len(centers) >= 2:
        typical = math.fsum(row["center"] for row in centers) / len(centers)
        lines.append(f'- Across {len(centers)} earlier states in the current public cycle, '
                     f'the probability-implied average expectation has typically been around {typical:.2f}%.')
    lines.extend([
        "The earlier answers concerned the 12 months following their own survey dates. "
        "Today's questions concern the next 12 months from today's survey.",
        "Use the earlier state as the starting point for your current view. Consider whether "
        "new information warrants retaining or revising it. An unchanged answer is allowed; "
        "no fixed amount of adjustment is required.",
    ])
    return "\n".join(lines) + "\n\n"
