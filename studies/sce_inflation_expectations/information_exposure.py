"""Explicit E/P routing diagnostic; CE spending is NOT measured attention.

Three arms share demographics, synthetic basket, questionnaire and renderer.
Only visible numeric facts differ; news is disabled in ALL arms. No targets,
survey answers or fitted forecast coefficients are used to construct routing.
"""
from copy import deepcopy
import hashlib
import math

from .price_experience import CATEGORIES, canonical_hash, profile_hash
from .experience_mechanism import _check_public_time

SCHEMA = "sce-information-exposure-v1"
PROMPT_VERSION = "sce-q8-q9-information-exposure-v1"
CHANNELS = ("food", "gasoline", "shelter")
ARMS = ("shared", "shuffled", "matched")
PREFIXES = {
    "food": ("bls_cpi_food_yoy_nsa_",),
    "gasoline": ("bls_cpi_gasoline_yoy_nsa_", "eia_gasoline_retail_regular_mean_", "eia_gasoline_retail_regular_yoy_"),
    "shelter": ("bls_cpi_shelter_yoy_nsa_",),
}
ROW_KEYS = {"agent_id", "profile_sha256", "spending_shares", "intended_channel", "delivered_channel"}


def validate_shares(shares):
    if (set(shares) != set(CATEGORIES) or
        any(type(x) not in (float, int) or not math.isfinite(x) or not 0 <= x <= 1 for x in shares.values()) or
        abs(sum(shares.values()) - 1) > 1e-8 or sum(shares[k] for k in CHANNELS) <= 0):
        raise ValueError("invalid or unsupported three-channel basket")


def route_channel(agent_id, shares, seed=42):
    """Seeded categorical draw, conditional on the three CE shares only.

    Same ID uses the same quantile across months. This is an unestimated design
    assumption; excluded 'other' share and lack of purchase frequency are logged.
    """
    validate_shares(shares)
    total = sum(shares[k] for k in CHANNELS)
    draw = int.from_bytes(hashlib.sha256(f"{seed}|{agent_id}|price-channel-v1".encode()).digest()[:8], "big") / 2**64
    acc = 0.
    for channel in CHANNELS:
        acc += shares[channel] / total
        if draw < acc:
            return channel
    return CHANNELS[-1]


def shuffled_channels(ids, channels, seed=42):
    """A cyclic permutation of people preserves the exact package multiset.

    No ID keeps its own package donor. Same-channel coincidences are permitted,
    reported, and NOT relabelled as mismatches or retried until significant.
    """
    if len(ids) < 2 or len(set(ids)) != len(ids) or set(ids) != set(channels):
        raise ValueError("shuffle requires unique complete IDs")
    order = sorted(ids, key=lambda aid: hashlib.sha256(f"{seed}|shuffle|{aid}".encode()).hexdigest())
    donor = {aid: order[(i + 1) % len(order)] for i, aid in enumerate(order)}
    return {aid: channels[donor[aid]] for aid in ids}, donor


def select_diagnostic_ids(personas, baskets, per_channel=16, seed=42):
    """Balanced diagnostic sampling without reading evaluation answers."""
    pools = {ch: [] for ch in CHANNELS}
    for p in personas:
        basket = baskets[p.agent_id]
        if basket["agent_id"] != p.agent_id or basket["profile_sha256"] != profile_hash(p.attributes):
            raise ValueError("source basket/profile mismatch")
        pools[route_channel(p.agent_id, basket["spending_shares"], seed)].append(p.agent_id)
    selected = []
    for channel, ids in pools.items():
        if len(ids) < per_channel:
            raise ValueError("insufficient channel support")
        selected.extend(sorted(ids, key=lambda aid: hashlib.sha256(f"{seed}|selection|{aid}".encode()).hexdigest())[:per_channel])
    return selected, {ch: len(ids) for ch, ids in pools.items()}


def validate_bundle(bundle, personas, target_month):
    keys = {"schema_version", "research_line", "target_month", "arm", "news_policy", "routing_rule", "rows"}
    if (set(bundle) != keys or bundle["schema_version"] != SCHEMA or
        bundle["research_line"] != "A_historical_reconstruction" or bundle["arm"] not in ARMS or
        bundle["target_month"] != target_month or bundle["news_policy"] != "off_all_arms" or
        bundle["routing_rule"] != "conditional_ce_share_draw_seed42_v1"):
        raise ValueError("unsupported exposure bundle")
    if set(bundle["rows"]) != {p.agent_id for p in personas}:
        raise ValueError("exposure roster mismatch")
    for p in personas:
        row = bundle["rows"][p.agent_id]
        if set(row) != ROW_KEYS or row["agent_id"] != p.agent_id or row["profile_sha256"] != profile_hash(p.attributes):
            raise ValueError("exposure row/profile mismatch or extra fields")
        validate_shares(row["spending_shares"])
        expected = route_channel(p.agent_id, row["spending_shares"])
        if row["intended_channel"] != expected or row["delivered_channel"] not in CHANNELS:
            raise ValueError("invalid exposure channel")
        if bundle["arm"] == "matched" and row["delivered_channel"] != expected:
            raise ValueError("matched channel disagreement")
    if bundle["arm"] == "shuffled":
        mapping, _ = shuffled_channels(list(bundle["rows"]), {aid: row["intended_channel"] for aid, row in bundle["rows"].items()})
        if any(bundle["rows"][aid]["delivered_channel"] != ch for aid, ch in mapping.items()):
            raise ValueError("shuffle not frozen permutation")
    return deepcopy(bundle)


def build_exposure_view(profile, info, bundle, agent_id):
    _check_public_time(info)
    row = bundle["rows"][agent_id]
    if row["profile_sha256"] != profile_hash(profile):
        raise ValueError("exposure profile binding mismatch")
    validate_shares(row["spending_shares"])
    view = deepcopy(info)
    ch = row["delivered_channel"]
    if bundle["arm"] != "shared":
        view["signals"] = [s for s in info["signals"] if s["signal_id"].startswith(PREFIXES[ch])]
        if not view["signals"]:
            raise ValueError("missing selected price channel")
    view["events"] = []
    view["broadcasts"] = []  # avoid an alternate common-information path
    state = {"arm": bundle["arm"], "row": deepcopy(row),
             "bundle_sha256": canonical_hash(bundle),
             "source_ledger_sha256": canonical_hash(info),
             "source_signal_ids": [s["signal_id"] for s in info["signals"]],
             "visible_signal_ids": [s["signal_id"] for s in view["signals"]],
             "excluded_event_ids": [e["event_id"] for e in info.get("events", [])],
             "rule_status": "design_assumption_not_measured_attention"}
    return view, state


def build_exposure_messages(ob, base_messages):
    """Reuse v2 persona/time/questionnaire, replace only its environment block.

    Each series keeps its own reference months, unit and exact measure name.
    No generated receipts, suggested forecast, attention coefficient or arm ID
    is sent to the model. The synthetic basket is identical in all three arms.
    """
    state = ob.local_information["information_exposure"]
    shares = state["row"]["spending_shares"]
    text = base_messages[0]["content"]
    # Split at questionnaire, then at the end of the common survey/time paragraph.
    head, questions = text.split("\n\nQuestion 1 (point estimate):", 1)
    survey_end = head.index(".\n\n", head.index("You only know information")) + 1
    header = head[:survey_end]
    groups = {}
    for s in ob.macro_information["signals"]:
        groups.setdefault((s["measure"], s["unit"]), []).append(s)
    lines = []
    for (measure, unit), signals in groups.items():
        signals.sort(key=lambda s: s["reference_period"])
        values = "; ".join(f"{s['reference_period']}: {s['value']:g}" for s in signals)
        lines.append(f"- {measure} [unit: {unit}]: {values}.")
    basket = ("Synthetic household spending context for this simulation (not your observed receipts):\n"
              f"Food {shares['food']*100:.1f}%; gasoline and motor oil {shares['gasoline']*100:.1f}%; "
              f"cash shelter {shares['shelter']*100:.1f}%; other {shares['other']*100:.1f}%. "
              "These jointly drawn CE shares are not CPI weights or measured attention. "
              "CPI shelter includes owner rental equivalence; cash shelter is different.\n\n")
    frame = ("Answer as the described household survey respondent. The following public price and job "
             "figures describe past changes, not a required answer about the coming year. "
             "Use the information shown to form your expectation; no news articles are supplied.\n\n")
    return [{"role": "user", "content": frame + header + "\n\n" + basket +
             "Available public figures (each reference month is labelled):\n" + "\n".join(lines) +
             "\n\nQuestion 1 (point estimate):" + questions}]
