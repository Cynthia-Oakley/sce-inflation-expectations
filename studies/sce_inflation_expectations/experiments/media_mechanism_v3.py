"""Registered seven-month news mechanisms; prompt assembly is added separately."""
from __future__ import annotations

import hashlib
import random

from .media_mechanism_trial import INFLATION_PATTERN, external_count, parse_time

MONTHS = (201905, 202009, 202106, 202109, 202112, 202206, 202312)
ARMS = ("R0", "Q0", "Q1", "Q2", "Q3")
ARM_CONFIG = {
    "R0": {"alarming_boost": 1.0, "cpi_boost": 1.0, "fox_share": 0.0, "four_tiers": False},
    "Q0": {"alarming_boost": 1.0, "cpi_boost": 1.0, "fox_share": 0.0, "four_tiers": True},
    "Q1": {"alarming_boost": 2.0, "cpi_boost": 1.0, "fox_share": 0.0, "four_tiers": True},
    "Q2": {"alarming_boost": 1.0, "cpi_boost": 1.0, "fox_share": 0.25, "four_tiers": True},
    "Q3": {"alarming_boost": 1.0, "cpi_boost": 1.5, "fox_share": 0.0, "four_tiers": True},
}


def four_tier_levels(agent_ids, month, seed=20261025):
    ordered = sorted(agent_ids, key=lambda aid: (hashlib.sha256(f"{seed}|{month}|{aid}".encode()).hexdigest(), aid))
    return {aid: (4, 8, 16, 32)[index % 4] for index, aid in enumerate(ordered)}


def merge_supplemental_labels(rows, supplemental):
    merged = []
    for row in rows:
        article_id = row["article_id"]
        if article_id not in supplemental:
            raise ValueError("missing supplemental label: " + article_id)
        extra = supplemental[article_id]
        if set(extra) != {"tone", "persistence"}:
            raise ValueError("unexpected supplemental fields")
        merged.append(dict(row, semantic_label={**row["semantic_label"], **extra}))
    return merged


def is_alarming(row):
    return (row.get("semantic_label") or {}).get("tone") == "alarming"


def is_cpi_direct(row):
    label = row.get("semantic_label") or {}
    return bool(INFLATION_PATTERN.search(row.get("headline") or "")) and bool(
        set(label.get("topics") or []) & {"living_prices", "economic_outlook"})


def selection_probabilities(rows, interests, alarming_boost=1.0, cpi_boost=1.0):
    if alarming_boost < 1 or cpi_boost < 1:
        raise ValueError("registered boosts must be at least one")
    if not rows:
        return []
    scores = []
    for row in rows:
        score = 2.0 if set(row["routing_tags"]) & interests else 1.0
        score *= alarming_boost if is_alarming(row) else 1.0
        score *= cpi_boost if is_cpi_direct(row) else 1.0
        scores.append(score)
    total = sum(scores)
    return [0.5 / len(rows) + 0.5 * score / total for score in scores]


def draw_weighted(rows, count, seed, interests, alarming_boost=1.0, cpi_boost=1.0):
    if count < 0 or count > len(rows):
        raise ValueError("invalid personal news count")
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))
    available = sorted(rows, key=lambda row: row["article_id"])
    chosen = []
    for _ in range(count):
        probabilities = selection_probabilities(available, interests, alarming_boost, cpi_boost)
        draw = rng.random()
        cumulative = 0.0
        index = len(available) - 1
        for position, probability in enumerate(probabilities):
            cumulative += probability
            if draw < cumulative:
                index = position
                break
        chosen.append(available.pop(index))
    return chosen


def draw_personal(nyt, fox, count, seed, interests, alarming_boost=1.0, cpi_boost=1.0, fox_share=0.0):
    if fox_share not in (0.0, 0.25):
        raise ValueError("only registered Fox share is allowed")
    fox_n = external_count(count) if fox_share == 0.25 else 0
    chosen = draw_weighted(nyt, count - fox_n, seed + "|nyt", interests, alarming_boost, cpi_boost)
    chosen += draw_weighted(fox, fox_n, seed + "|fox", interests, alarming_boost, cpi_boost)
    return sorted(chosen, key=lambda row: (parse_time(row["pub_date"]), row["article_id"]))
