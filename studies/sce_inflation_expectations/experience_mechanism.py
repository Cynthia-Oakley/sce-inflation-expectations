"""Auditable price-experience state and salience views; no forecast level tuning.

All public signals/news remain available. The focus arm only prioritizes price
trend lines and news associated with the synthetic budget, not an assumed
shopping role. Spending weights are a salience PROXY, not estimated attention.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from math import isfinite
import re

from .price_experience import CATEGORIES, canonical_hash, profile_hash

SCHEMA = "sce-price-experience-v1"
PROMPT_VERSION = "sce-q8-q9-experience-v1"
CONFIG_KEYS = {"schema_version", "arm", "show_experience", "view_mode", "research_line"}
CHANNELS = {
    "food": {"prefix": "bls_cpi_food_yoy_nsa_", "trend": "Food prices (12-month %)",
             "label": "food", "note": "All-food CPI, not an individual's store receipts"},
    "gasoline": {"prefix": "bls_cpi_gasoline_yoy_nsa_", "trend": "Regular gasoline price ($/gallon)",
                 "label": "gasoline and motor oil spending", "note": "CE includes motor oil; CPI here is gasoline only"},
    "shelter": {"prefix": "bls_cpi_shelter_yoy_nsa_", "trend": "Rent/shelter prices (12-month %)",
                "label": "cash shelter spending", "note": "CPI shelter includes owner rental equivalence, not mortgage bills"},
}
NEWS_PATTERNS = {
    "food": r"\b(food|grocery|groceries|supermarket|beef|meat|wheat|grain)\b",
    "gasoline": r"\b(gasoline|gas prices|fuel|oil prices|crude oil|oil pipeline|opec)\b",
    "shelter": r"\b(rent|rents|rental|eviction|housing costs|housing prices|home prices|mortgage)\b",
}
TREND_HEADER = "Recent trends (each lists the past 12 monthly releases, oldest to newest):"


def validate_config(config: dict) -> dict:
    if set(config) != CONFIG_KEYS or config.get("schema_version") != SCHEMA:
        raise ValueError("unsupported mechanism config keys/schema")
    if config["research_line"] != "A_historical_reconstruction":
        raise ValueError("this implementation accepts only retrospective A-line inputs")
    if type(config["show_experience"]) is not bool or config["view_mode"] not in {"shared", "budget_salience"}:
        raise ValueError("invalid show_experience/view_mode")
    if not isinstance(config["arm"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", config["arm"]):
        raise ValueError("arm must be a short explicit identifier")
    return deepcopy(config)


def needs_basket(config: dict) -> bool:
    return config["show_experience"] or config["view_mode"] == "budget_salience"


def _check_public_time(info: dict) -> None:
    cutoff = datetime.fromisoformat(info["as_of"])
    if cutoff.tzinfo is None:
        raise ValueError("as_of needs timezone")
    for signal in info["signals"]:
        if not signal.get("signal_id") or not signal.get("published_at"):
            raise ValueError("mechanism signals require ID and published_at")
        published = datetime.fromisoformat(signal["published_at"])
        if published.tzinfo is None or published > cutoff:
            raise ValueError(f"unavailable signal at cutoff: {signal['signal_id']}")
    ids = [s["signal_id"] for s in info["signals"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate public signal ID")
    event_ids = [e["event_id"] for e in info.get("events", [])]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("duplicate news ID")
    for event in info.get("events", []):
        stamp = event.get("published_at") or event.get("pub_date")
        if not event.get("event_id") or not stamp:
            raise ValueError("news needs ID and publication date")
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if when.tzinfo is None:
            if len(stamp) != 10 or when.date() > cutoff.date():
                raise ValueError("undated/future news")
            if when.date() == cutoff.date() and (cutoff.hour, cutoff.minute, cutoff.second) != (23, 59, 59):
                raise ValueError("date-only news cannot establish within-day availability")
        elif when > cutoff:
            raise ValueError("news later than cutoff")
    # Date checks do NOT certify the text vintage. Original source_status remains.


def build_experience_view(profile: dict, info: dict, config: dict, basket: dict | None) -> tuple[dict, dict]:
    config = validate_config(config)
    _check_public_time(info)
    view = deepcopy(info)
    state = {"schema_version": SCHEMA, "arm": config["arm"],
             "mechanism_sha256": canonical_hash(config), "config": config,
             "basket": None, "channel_states": [], "channel_priority": [],
             "source_signal_ids": [s["signal_id"] for s in info["signals"]],
             "master_event_ids": [e["event_id"] for e in info.get("events", [])],
             "public_facts_changed": False,
             "synthetic_spending_context_disclosed": config["show_experience"],
             "attention_rule_status": "design_assumption_not_measured_attention"}
    if needs_basket(config):
        if not basket or basket.get("schema_version") != "sce-ce-basket-v1":
            raise ValueError("selected arm requires a materialized CE basket")
        if basket.get("profile_sha256") != profile_hash(profile):
            raise ValueError("basket bound to a different profile")
        shares = basket.get("spending_shares", {})
        if set(shares) != set(CATEGORIES) or any(not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in shares.values()) or abs(sum(shares.values()) - 1) > 1e-8:
            raise ValueError("invalid materialized spending shares")
        state["basket"] = deepcopy(basket)
        for category, spec in CHANNELS.items():
            signals = [s for s in info["signals"] if s["signal_id"].startswith(spec["prefix"])]
            if not signals:
                raise ValueError(f"missing public price channel: {category}")
            s = max(signals, key=lambda x: x["reference_period"])
            if s.get("unit") != "percent":
                raise ValueError("price channel must be year-on-year percent")
            if not isinstance(s.get("value"), (int, float)) or not isfinite(s["value"]):
                raise ValueError("nonfinite/missing public price value")
            state["channel_states"].append({"category": category, "budget_share": shares[category],
                "signal_id": s["signal_id"], "reference_period": s["reference_period"],
                "public_yoy_pct": s["value"], "unit": s["unit"], "mapping_note": spec["note"]})
        priority = sorted(CHANNELS, key=lambda k: (-shares[k], list(CHANNELS).index(k)))
        state["channel_priority"] = priority
        if config["view_mode"] == "budget_salience":
            # Stable reorder, never threshold, omit, rewrite or silently add news.
            def score(event: dict) -> float:
                text = event.get("headline", "") + " " + event.get("abstract", "")
                return sum(shares[k] for k, pattern in NEWS_PATTERNS.items() if re.search(pattern, text, re.I))
            indexed = list(enumerate(info.get("events", [])))
            indexed.sort(key=lambda pair: (-score(pair[1]), pair[0]))
            view["events"] = [deepcopy(e) for _, e in indexed]
            state["news_salience"] = [{"event_id": e["event_id"], "proxy_score": score(e)} for e in view["events"]]
    state["view_event_ids"] = [e["event_id"] for e in view.get("events", [])]
    state["public_fact_ledger_sha256"] = canonical_hash({
        "target_month": info["target_month"], "as_of": info["as_of"],
        "signals": info["signals"], "events": info.get("events", [])})
    return view, state


def build_mechanism_messages(ob, base_messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Reuse the entire v2-abstract fact block and identical questionnaire.

    The expression control changes only headings and the respondent frame.
    Focus reorders existing trend lines/news; budget disclosure is its own switch.
    """
    state = ob.local_information.get("price_experience")
    if not state:
        raise ValueError("experience prompt needs mechanism state from the environment")
    config = validate_config(state["config"])
    messages = deepcopy(base_messages)
    text = messages[0]["content"]
    text = text.replace("Recent official statistics:", "Public figures about prices and jobs:")
    text = text.replace("Recent news headlines (with brief summaries):", "Recent news available to you (titles and summaries):")
    prefix = ("Answer as the household survey respondent described below. Use the supplied information "
              "to form your own expectation; the public price figures describe past changes, not a "
              "required answer about the next year.\n\n")
    if config["view_mode"] == "budget_salience" and TREND_HEADER in text:
        start = text.index(TREND_HEADER) + len(TREND_HEADER)
        end = text.find("\n\n", start)
        if end == -1:
            raise ValueError("cannot identify trend block")
        lines = text[start:end].strip().splitlines()
        titles = [CHANNELS[k]["trend"] for k in state["channel_priority"]]
        def rank(line):
            line = line.removeprefix("- ")
            return next((i for i, title in enumerate(titles) if line.startswith(title + ":")), len(titles))
        lines = [line for _, line in sorted(enumerate(lines), key=lambda pair: (rank(pair[1]), pair[0]))]
        text = text[:start] + "\n" + "\n".join(lines) + text[end:]
    if config["show_experience"]:
        basket = state["basket"]
        shares = basket["spending_shares"]
        # No weighted inflation forecast is computed; no answer is prescribed.
        block = ("\nSynthetic household spending context assigned for this simulation:\n"
                 f"- Reported spending mix: food {shares['food']*100:.1f}%; gasoline and motor oil "
                 f"{shares['gasoline']*100:.1f}%; cash shelter {shares['shelter']*100:.1f}%; other "
                 f"{shares['other']*100:.1f}%. These shares are drawn jointly from one separate "
                 "CE consumption unit, conditional on available profile attributes.\n"
                 f"- Source interview wave: {basket['source']['interview_wave']}; a fixed spending "
                 "proxy, not observed spending in the survey month.\n"
                 "- The reported total includes contributions and pensions; these are spending "
                 "allocation shares, not CPI index weights.\n"
                 "- This is a synthetic proxy, not your observed receipts or purchase frequency. "
                 "Zero reported spending does not establish that you never buy an item. No shopping "
                 "or driving role is assigned.\n"
                 "- Public food/gasoline/shelter indexes are category signals, not your exact bill; "
                 "cash shelter and CPI rental equivalence differ. Decide for yourself how relevant "
                 "past price changes are for the next 12 months.\n")
        pos = text.index("Question 1 (point estimate):")
        text = text[:pos] + block + "\n" + text[pos:]
    messages[0]["content"] = prefix + text
    return messages
