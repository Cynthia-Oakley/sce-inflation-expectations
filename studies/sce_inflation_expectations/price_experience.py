"""Joint CE basket assignment, without SCE answers or a behavioural response coefficient.

The donor is a DIFFERENT consumption unit. Its spending shares are a synthetic
proxy, not the target person's observed spending or purchase frequency. One
explicit FMLI interview wave is used, not a pooled pseudo-independent panel.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from math import isfinite
from typing import Any, Iterable

PROFILE_KEYS = {"age_group", "region", "state", "education_group",
                "household_income_band", "housing_tenure", "employment_status", "numeracy"}
MATCH_PRIORITY = ("housing_tenure", "household_income_band", "age_group", "region", "education_group")
CATEGORIES = ("food", "gasoline", "shelter", "other")
CE_COLUMNS = ("NEWID", "AGE_REF", "EDUC_REF", "CUTENURE", "REGION", "FINCBTXM", "FINLWT21",
              "TOTEXPPQ", "TOTEXPCQ", "FOODPQ", "FOODCQ", "GASMOPQ", "GASMOCQ", "SHELTPQ", "SHELTCQ")


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def clean_profile(profile: dict) -> dict:
    return {key: profile[key] for key in sorted(PROFILE_KEYS) if key in profile}


def profile_hash(profile: dict) -> str:
    return canonical_hash(clean_profile(profile))


def _number(row: dict, key: str) -> float:
    value = float(str(row[key]).strip())
    if not isfinite(value):
        raise ValueError(f"nonfinite {key}")
    return value


def normalize_ce_row(row: dict) -> dict:
    """FMLI PQ and CQ partition the reported three-month expenditures.

    Income uses the mean of the five imputed BEFORE-tax income values, FINCBTXM.
    These code mappings are tied to the CE dictionary, not inferred from SCE.
    """
    row = {str(k).strip().upper(): v for k, v in row.items()}
    missing = set(CE_COLUMNS) - row.keys()
    if missing:
        raise ValueError(f"missing CE columns: {sorted(missing)}")
    amounts = {"food": _number(row, "FOODPQ") + _number(row, "FOODCQ"),
               "gasoline": _number(row, "GASMOPQ") + _number(row, "GASMOCQ"),
               "shelter": _number(row, "SHELTPQ") + _number(row, "SHELTCQ")}
    total = _number(row, "TOTEXPPQ") + _number(row, "TOTEXPCQ")
    weight = _number(row, "FINLWT21")
    if total <= 0 or weight <= 0 or any(x < 0 for x in amounts.values()):
        raise ValueError("nonpositive total/weight or negative component")
    remainder = total - sum(amounts.values())
    if remainder < -1e-6:
        raise ValueError("overlapping or inconsistent component total")
    amounts["other"] = max(0.0, remainder)
    shares = {key: x / total for key, x in amounts.items()}
    attrs = {}
    for key, mapping, source in [
        ("region", {1: "Northeast", 2: "Midwest", 3: "South", 4: "West"}, "REGION"),
        ("housing_tenure", {1: "owner", 2: "owner", 3: "owner", 4: "renter", 5: "other", 6: "other"}, "CUTENURE"),
        ("education_group", {0: "high_school", 10: "high_school", 11: "high_school", 12: "high_school",
                             13: "some_college", 14: "some_college", 15: "college",
                             16: "college"}, "EDUC_REF"),
    ]:
        try:
            code = int(_number(row, source))
        except (ValueError, TypeError):
            continue
        if code in mapping:
            attrs[key] = mapping[code]
    try:
        age = _number(row, "AGE_REF")
        if age >= 18:
            attrs["age_group"] = "Under 40" if age < 40 else "40 to 60" if age <= 60 else "Over 60"
    except (ValueError, TypeError):
        pass
    try:
        income = _number(row, "FINCBTXM")
        attrs["household_income_band"] = "under_50k" if income < 50000 else "50k_to_100k" if income <= 100000 else "over_100k"
    except (ValueError, TypeError):
        pass
    return {"donor_id": str(row["NEWID"]).strip(), "attributes": attrs,
            "sampling_weight": weight, "spending_shares": shares,
            "reported_expenditure_usd": total}


def prepare_ce_donors(rows: Iterable[dict]) -> tuple[list[dict], dict]:
    donors, errors = [], Counter()
    for row in rows:
        try:
            donors.append(normalize_ce_row(row))
        except (ValueError, TypeError, KeyError) as exc:
            # Missing columns are a schema failure, not an ignorable individual row.
            if "missing CE columns" in str(exc):
                raise
            errors[str(exc)] += 1
    donors.sort(key=lambda x: x["donor_id"])
    ids = [x["donor_id"] for x in donors]
    if not donors or len(set(ids)) != len(ids):
        raise ValueError("need a nonempty unique CE interview wave")
    return donors, {"eligible_n": len(donors), "excluded_n": sum(errors.values()), "exclusion_reasons": dict(errors)}


class BasketAssigner:
    def __init__(self, donors: list[dict], source: dict, *, seed: int = 42, min_pool: int = 25):
        if min_pool < 1 or len(donors) < min_pool:
            raise ValueError("not enough donors for the declared minimum pool")
        if not source.get("source_url") or not source.get("data_sha256") or not source.get("interview_wave"):
            raise ValueError("donor source needs URL, hash and explicit interview wave")
        self.donors = sorted(donors, key=lambda x: x["donor_id"])
        self.source, self.seed, self.min_pool = dict(source), int(seed), int(min_pool)
        if len({x["donor_id"] for x in donors}) != len(donors):
            raise ValueError("duplicate donor ID")
        for d in donors:
            if (not isfinite(d["sampling_weight"]) or d["sampling_weight"] <= 0
                    or set(d["spending_shares"]) != set(CATEGORIES)
                    or any(not isfinite(v) or v < 0 for v in d["spending_shares"].values())
                    or abs(sum(d["spending_shares"].values()) - 1) > 1e-8):
                raise ValueError("invalid donor weight or basket")

    def assign(self, agent_id: str, profile: dict) -> dict:
        profile = clean_profile(profile)
        available = [k for k in MATCH_PRIORITY if profile.get(k) is not None]
        active = list(available)
        while True:
            pool = [d for d in self.donors if all(d["attributes"].get(k) == profile[k] for k in active)]
            if len(pool) >= self.min_pool:
                break
            if not active:
                raise ValueError("insufficient global donor pool")
            active.pop()
        weights = [d["sampling_weight"] for d in pool]
        total = sum(weights)
        # A stable uniform draw; donor ordering and other recipients do not affect it.
        # Persistent latent draw: employment/numeracy/state changes must not redraw
        # the budget when the actual CE matching pool stays the same.
        h = hashlib.sha256(f"{self.seed}|{agent_id}".encode()).digest()
        draw = (int.from_bytes(h[:8], "big") / 2**64) * total
        acc, chosen = 0.0, pool[-1]
        for d, weight in zip(pool, weights):
            acc += weight
            if draw < acc:
                chosen = d
                break
        return {"schema_version": "sce-ce-basket-v1", "agent_id": agent_id,
                "profile_sha256": profile_hash(profile), "evidence_class": "estimated_proxy",
                "assignment_class": "conditional_weighted_synthetic_donor",
                "donor_id": chosen["donor_id"], "source": self.source,
                "spending_shares": dict(chosen["spending_shares"]),
                "matched_fields": active, "relaxed_fields": [k for k in available if k not in active],
                "pool_n": len(pool), "pool_effective_n": total**2 / sum(w*w for w in weights),
                "conditional_draw_probability": chosen["sampling_weight"] / total,
                "seed": self.seed,
                "limitations": ["Different CE consumption unit, not this respondent's observed wallet",
                                "One interview wave; no measured purchase frequency, shopping or driving role",
                                "Gasoline includes motor oil; cash shelter spending differs from CPI rental equivalence",
                                "Total reported expenditure includes contributions and pensions; not a CPI consumption basket",
                                "No household expectation, future CPI or response coefficient used"]}
