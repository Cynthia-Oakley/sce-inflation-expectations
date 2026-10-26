"""Pure weekly news allocation with persistent article memory and monthly caps.

The four attention tiers are monthly ceilings for newly encountered, unique
articles, including shared salient news. A cutoff only unlocks the fraction of
that ceiling accrued by its New York calendar day. There is no opening
backfill: unused end-of-month capacity is not issued early or carried forward.
"""
from __future__ import annotations

import calendar
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo

from .media_mechanism_trial import parse_time
from .media_mechanism_v3 import draw_personal

ATTENTION_TIERS = (4, 8, 16, 32)
COMMON_MONTHLY_CAP = 3
ALARMING_BOOST = 1.0
CPI_BOOST = 1.5
NEWS_SEED = "sce_weekly_news_v1"
NEW_YORK = ZoneInfo("America/New_York")
_STATE_KEYS = {
    "schema_version", "attention_tier", "seen_article_ids", "month",
    "month_article_ids", "month_common_article_ids", "last_cutoff",
}


def empty_news_state(attention_tier: int) -> dict:
    """Create a no-backfill initial memory for one fixed attention tier."""
    _check_tier(attention_tier)
    return {
        "schema_version": 1,
        "attention_tier": attention_tier,
        "seen_article_ids": [],
        "month": None,
        "month_article_ids": [],
        "month_common_article_ids": [],
        "last_cutoff": None,
    }


def monthly_quota_at_cutoff(attention_tier: int, cutoff: str) -> dict:
    """Return the cumulative monthly cap accrued by an aware cutoff instant."""
    _check_tier(attention_tier)
    local = _cutoff(cutoff).astimezone(NEW_YORK)
    days_in_month = calendar.monthrange(local.year, local.month)[1]
    target = attention_tier * local.day // days_in_month
    last_friday = days_in_month - ((datetime(local.year, local.month, days_in_month).weekday() - 4) % 7)
    return {
        "month": local.strftime("%Y-%m"),
        "day_of_month": local.day,
        "days_in_month": days_in_month,
        "monthly_target": target,
        "not_yet_accrued_quota": attention_tier - target,
        "is_last_friday_of_month": local.day == last_friday,
        "after_last_friday_unissued_quota": (
            attention_tier - target if local.day == last_friday else None
        ),
    }


def advance_weekly_news(
    *,
    candidate_pool,
    common_candidates,
    cutoff: str,
    household_id: str,
    attention_tier: int,
    interests,
    state: dict | None = None,
    seed: str = NEWS_SEED,
) -> dict:
    """Select this cutoff's new shared/personal articles and return memory.

    ``candidate_pool`` is the complete article catalog for the target window;
    it may contain future articles, which are filtered before any selector sees
    them. ``common_candidates`` is the existing salient-common selector's
    ordered result for this cutoff (normally three A1 articles). Its IDs must
    belong to the complete catalog. Keep articles, including A1 keep articles,
    can enter the personal pool once they are not delivered as common.

    Reusing the same inputs and prior state is deterministic. Applying the
    returned state again at the same cutoff is a no-op, which makes stateful
    reruns idempotent as well.
    """
    _check_tier(attention_tier)
    if not isinstance(household_id, str) or not household_id:
        raise ValueError("household_id must be a nonempty stable ID")
    cutoff_dt = _cutoff(cutoff)
    local = cutoff_dt.astimezone(NEW_YORK)
    month_key = local.strftime("%Y-%m")
    current = _validated_state(state, attention_tier)

    prior_cutoff = parse_time(current["last_cutoff"]) if current["last_cutoff"] else None
    if prior_cutoff is not None:
        if cutoff_dt < prior_cutoff:
            raise ValueError("weekly news cutoffs must be nondecreasing")
        if cutoff_dt == prior_cutoff:
            return _result_noop(current, cutoff, attention_tier)

    if current["month"] is not None and month_key < current["month"]:
        raise ValueError("weekly news state cannot move backward across months")

    # Filter by the information cutoff before common selection, relevance
    # weighting, or personal sampling. Future rows do not affect any choice.
    candidate_rows = list(candidate_pool)
    common_rows = list(common_candidates)
    _validate_pool_ids(candidate_rows, "candidate_pool")
    _validate_pool_ids(common_rows, "common_candidates")
    eligible, future_excluded = _filter_by_cutoff(candidate_rows, cutoff_dt)
    eligible_common, common_future_excluded = _filter_by_cutoff(common_rows, cutoff_dt)
    catalog = {row["article_id"]: row for row in eligible}
    for row in eligible_common:
        if row["article_id"] not in catalog or row != catalog[row["article_id"]]:
            raise ValueError("common candidates must be exact rows from candidate_pool")
        if row.get("placement") != "a1":
            raise ValueError("shared salient candidates must have A1 placement")
    if len(eligible_common) > COMMON_MONTHLY_CAP:
        raise ValueError("at most three ordered shared candidates may be supplied")

    quota = monthly_quota_at_cutoff(attention_tier, cutoff)
    if current["month"] == month_key:
        month_ids = set(current["month_article_ids"])
        common_ids = set(current["month_common_article_ids"])
    else:
        # Lifetime seen IDs persist. Only monthly counters reset at the
        # calendar boundary; publication calibration never enters this module.
        month_ids, common_ids = set(), set()

    seen = set(current["seen_article_ids"])
    target = quota["monthly_target"]
    slots = max(0, target - len(month_ids))
    common_slots = min(slots, max(0, COMMON_MONTHLY_CAP - len(common_ids)))
    new_common = []
    for row in eligible_common:
        if row["article_id"] in seen:
            continue
        if len(new_common) >= common_slots:
            break
        new_common.append(row)

    new_common_ids = {row["article_id"] for row in new_common}
    remaining_slots = slots - len(new_common)
    personal_pool = [
        row for row in eligible
        if row["article_id"] not in seen
        and row["article_id"] not in new_common_ids
        and (row.get("semantic_label") or {}).get("decision") == "keep"
    ]
    personal_count = min(remaining_slots, len(personal_pool))
    personal = draw_personal(
        personal_pool,
        [],
        personal_count,
        f"{seed}|{month_key}|{household_id}|slot{len(month_ids) + len(new_common)}",
        set(interests),
        alarming_boost=ALARMING_BOOST,
        cpi_boost=CPI_BOOST,
    ) if personal_count else []

    new_articles = sorted(
        [*new_common, *personal],
        key=lambda row: (parse_time(row["pub_date"]), row["article_id"]),
    )
    new_ids = [row["article_id"] for row in new_articles]
    if len(new_ids) != len(set(new_ids)):
        raise AssertionError("a weekly article cannot be delivered twice")

    all_seen = seen | set(new_ids)
    updated_month_ids = month_ids | set(new_ids)
    updated_common_ids = common_ids | new_common_ids
    next_state = {
        "schema_version": 1,
        "attention_tier": attention_tier,
        "seen_article_ids": sorted(all_seen),
        "month": month_key,
        "month_article_ids": sorted(updated_month_ids),
        "month_common_article_ids": sorted(updated_common_ids),
        "last_cutoff": cutoff_dt.isoformat(),
    }
    cumulative_count = {
        **quota,
        "monthly_contact_count": len(updated_month_ids),
        "monthly_common_count": len(updated_common_ids),
        "lifetime_contact_count": len(all_seen),
        "unfilled_count": max(0, target - len(updated_month_ids)),
    }
    return {
        "common_news": deepcopy(new_common),
        "personal_news": deepcopy(personal),
        "new_articles": deepcopy(new_articles),
        "new_article_ids": new_ids,
        "unfilled_count": cumulative_count["unfilled_count"],
        "cumulative_count": cumulative_count,
        "memory_after": next_state,
        "state": deepcopy(next_state),
        "audit": {
            "cutoff": cutoff_dt.isoformat(),
            "candidate_count": len(candidate_rows),
            "eligible_candidate_count": len(eligible),
            "future_candidate_count_excluded": future_excluded,
            "future_common_count_excluded": common_future_excluded,
            "eligible_common_candidate_count": len(eligible_common),
            "common_monthly_cap": COMMON_MONTHLY_CAP,
            "alarming_boost": ALARMING_BOOST,
            "cpi_relevance_boost": CPI_BOOST,
            "quota_rule": "floor(attention_tier * New_York_day_of_month / calendar_days_in_month)",
            "bootstrap_background_count": 0,
            "is_last_friday_of_month": quota["is_last_friday_of_month"],
            "after_last_friday_unissued_quota": quota["after_last_friday_unissued_quota"],
            "quota_note": (
                "No opening backfill; quota accrued after the last Friday is unissued, "
                "and any unused quota is not carried to the next month."
            ),
        },
    }


def _result_noop(state: dict, cutoff: str, attention_tier: int) -> dict:
    quota = monthly_quota_at_cutoff(attention_tier, cutoff)
    if state["month"] != quota["month"]:
        raise ValueError("same cutoff does not match the saved news-state month")
    monthly_count = len(state["month_article_ids"])
    common_count = len(state["month_common_article_ids"])
    cumulative = {
        **quota,
        "monthly_contact_count": monthly_count,
        "monthly_common_count": common_count,
        "lifetime_contact_count": len(state["seen_article_ids"]),
        "unfilled_count": max(0, quota["monthly_target"] - monthly_count),
    }
    return {
        "common_news": [], "personal_news": [], "new_articles": [],
        "new_article_ids": [], "unfilled_count": cumulative["unfilled_count"],
        "cumulative_count": cumulative,
        "memory_after": deepcopy(state), "state": deepcopy(state),
        "audit": {
            "cutoff": _cutoff(cutoff).isoformat(),
            "candidate_count": 0, "eligible_candidate_count": 0,
            "future_candidate_count_excluded": 0, "future_common_count_excluded": 0,
            "eligible_common_candidate_count": 0,
            "common_monthly_cap": COMMON_MONTHLY_CAP,
            "alarming_boost": ALARMING_BOOST, "cpi_relevance_boost": CPI_BOOST,
            "quota_rule": "floor(attention_tier * New_York_day_of_month / calendar_days_in_month)",
            "bootstrap_background_count": 0,
            "is_last_friday_of_month": quota["is_last_friday_of_month"],
            "after_last_friday_unissued_quota": quota["after_last_friday_unissued_quota"],
            "quota_note": "Already applied cutoff; replay returned no new exposure.",
        },
    }


def _validated_state(state: dict | None, attention_tier: int) -> dict:
    if state is None:
        return empty_news_state(attention_tier)
    if not isinstance(state, dict) or set(state) != _STATE_KEYS:
        raise ValueError("news state has an unsupported schema")
    if state["schema_version"] != 1 or state["attention_tier"] != attention_tier:
        raise ValueError("news state version or fixed attention tier changed")
    normalized = deepcopy(state)
    for key in ("seen_article_ids", "month_article_ids", "month_common_article_ids"):
        values = normalized[key]
        if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
            raise ValueError("news state article IDs must be string lists")
        if len(values) != len(set(values)):
            raise ValueError("news state contains duplicate article IDs")
        normalized[key] = sorted(values)
    seen = set(normalized["seen_article_ids"])
    month_ids = set(normalized["month_article_ids"])
    common_ids = set(normalized["month_common_article_ids"])
    if (not month_ids <= seen or not common_ids <= month_ids
            or len(common_ids) > COMMON_MONTHLY_CAP or len(month_ids) > attention_tier):
        raise ValueError("news memory counters do not match seen article IDs")
    if normalized["month"] is None:
        if normalized["last_cutoff"] is not None or month_ids or common_ids:
            raise ValueError("empty news state has monthly fields")
    else:
        if not isinstance(normalized["month"], str) or len(normalized["month"]) != 7:
            raise ValueError("news state month must use YYYY-MM")
        if normalized["last_cutoff"] is None:
            raise ValueError("nonempty news state needs its last cutoff")
        last = _cutoff(normalized["last_cutoff"]).astimezone(NEW_YORK)
        if last.strftime("%Y-%m") != normalized["month"]:
            raise ValueError("news state cutoff and month disagree")
    return normalized


def _filter_by_cutoff(rows, cutoff: datetime) -> tuple[list[dict], int]:
    eligible, future_count = [], 0
    for row in rows:
        published = parse_time(row["pub_date"])
        if published.tzinfo is None or published.utcoffset() is None:
            raise ValueError("article publication times must include a timezone")
        if published <= cutoff:
            eligible.append(row)
        else:
            future_count += 1
    return eligible, future_count


def _validate_pool_ids(rows, label: str) -> None:
    ids = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("article_id"), str) or not row["article_id"]:
            raise ValueError(f"{label} requires nonempty article_id values")
        if "pub_date" not in row:
            raise ValueError(f"{label} requires pub_date")
        ids.append(row["article_id"])
    if len(ids) != len(set(ids)):
        raise ValueError(f"{label} contains duplicate article IDs")


def _cutoff(value: str) -> datetime:
    parsed = parse_time(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("weekly cutoff must include a timezone")
    return parsed


def _check_tier(attention_tier: int) -> None:
    if type(attention_tier) is not int or attention_tier not in ATTENTION_TIERS:
        raise ValueError("attention tier must be one of 4, 8, 16 or 32")
