"""Offline state-dependency preparation from materialized P and past beliefs.

This is deliberately not a paid runner or a prompt-ready trial. It never reads
current answers, regime labels or evaluation files. Existing LLM transport and
scoring remain the execution path once the missing input adapters are ready.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARMS = ("observed_history", "simulated_history")


def month_index(month):
    value = int(month)
    year, number = divmod(value, 100)
    if not 1 <= number <= 12:
        raise ValueError("Invalid YYYYMM")
    return year * 12 + number - 1


def legal_prior_fields(prior):
    """Q8 and Q9 are independent; missing probabilities are never invented."""
    q8 = prior.get("q8_point_pct")
    q8_ok = type(q8) in (int, float) and math.isfinite(q8)
    bins = prior.get("q9_bins")
    q9_ok = (isinstance(bins, list) and len(bins) == 10
             and all(type(v) in (int, float) and math.isfinite(v)
                     and 0 <= v <= 100 for v in bins)
             and abs(sum(bins) - 100) <= 1e-6)
    return {"q8": q8_ok, "q9": bool(q9_ok)}


def select_frame(population, sampling, n):
    """Use delivered stable random priorities; marginal SRS probability n/N.

    The continuity pilot stays unstratified. The separate six-cell/512 proposal
    belongs to the final design and is not silently applied at a 96-person scale.
    """
    people = population["personas"]
    index = {p["agent_id"]: p for p in people}
    sidecar = {p["agent_id"]: p for p in sampling["persons"]}
    if len(index) != len(people) or set(index) != set(sidecar):
        raise ValueError("Unique matching population/sampling IDs required")
    if type(n) is not int or not 1 <= n <= len(people):
        raise ValueError("Requested Core size exceeds the monthly frame")
    if len(sidecar) != len(sampling["persons"]):
        raise ValueError("Duplicate sampling ID")
    if any(type(v.get("stable_priority")) is not int for v in sidecar.values()):
        raise ValueError("Delivered stable priorities required")
    chosen = sorted(index, key=lambda aid: (sidecar[aid]["stable_priority"], aid))[:n]
    pi = n / len(people)
    rows = []
    for aid in chosen:
        w = sidecar[aid]["survey_weight"]
        if type(w) not in (int, float) or not math.isfinite(w) or w <= 0:
            raise ValueError("Survey weight needs explicit resolution before preparation")
        persona = deepcopy(index[aid])
        persona["weight"] = 1.0  # evaluation weight is never a model instruction
        rows.append({"persona": persona, "inclusion_probability": pi,
                     "survey_weight_as_delivered": w,
                     "analysis_weight_as_delivered": w / pi})
    return rows


def build_dependency_plan(selected, beliefs, entry_state, *, months, repeats=2):
    if repeats < 1 or len(months) != len(set(months)):
        raise ValueError("Unique consecutive months and positive repeats required")
    if any(month_index(b) - month_index(a) != 1 for a, b in zip(months, months[1:])):
        raise ValueError("Continuity check requires consecutive calendar months")
    last_selected = {}
    nodes, by_month, missing_priors = [], {}, Counter()
    for month in months:
        entries, transfers, sources = Counter(), Counter(), Counter()
        for item in selected[month]:
            aid = item["persona"]["agent_id"]
            initial = deepcopy(beliefs[month][aid])
            if initial["source_kind"] not in {"observed_previous", "observed_older", "donor_initial"}:
                raise ValueError("Historical source must be declared")
            if initial.get("source_period") is None or month_index(initial["source_period"]) >= month_index(month):
                raise ValueError("Initial belief must strictly precede the target")
            validity = legal_prior_fields(initial["q8_q9"])
            missing_priors.update(k for k, valid in validity.items() if not valid)
            previous = last_selected.get(aid)
            core_status = ("first_core_appearance" if previous is None else
                           "continued_core" if month_index(month) - month_index(previous) == 1
                           else "core_gap_return")
            entries[entry_state[month][aid]["survey_entry_status"]] += 1
            transfers[core_status] += 1
            sources[initial["source_kind"]] += 1
            for repeat in range(1, repeats + 1):
                shared_key = f"{month}|{aid}|{repeat}|initial"
                for arm in ARMS:
                    use_simulated = arm == "simulated_history" and previous is not None
                    dependency = ({"arm": arm, "month": previous, "agent_id": aid,
                                   "repeat": repeat} if use_simulated else None)
                    kind = ("simulated_previous" if previous is not None
                            and month_index(month) - month_index(previous) == 1
                            else "simulated_older") if use_simulated else initial["source_kind"]
                    nodes.append({"month": month, "agent_id": aid, "arm": arm, "repeat": repeat,
                                  "core_entry_status": core_status,
                                  "survey_entry_status": entry_state[month][aid]["survey_entry_status"],
                                  "source_kind": kind, "dependency": dependency,
                                  "initial_belief": None if use_simulated else initial,
                                  "prior_fields_valid": None if use_simulated else validity,
                                  "logical_reuse_key": (f"{month}|{aid}|{repeat}|{arm}"
                                                        if previous is not None else shared_key)})
            last_selected[aid] = month
        by_month[month] = {"selected_n": len(selected[month]), "survey_entry": dict(entries),
                           "core_entry": dict(transfers), "observed_sources": dict(sources)}
    return nodes, {"monthly": by_month, "distinct_people": len(last_selected),
                   "person_months": sum(len(v) for v in selected.values()),
                   "logical_positions": len(nodes),
                   "potential_unique_calls_before_prompt_hash": len({v["logical_reuse_key"] for v in nodes}),
                   "initial_fields_needing_resolution_person_months": dict(missing_priors)}


def prepare(source, out, *, months=("202505", "202506", "202507"), n=96, repeats=2):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError("Fresh output directory required")
    selected, beliefs, entries, hashes, missing_environments = {}, {}, {}, {}, []
    for month in months:
        paths = {name: source / month / name for name in
                 ("population.json", "sampling_private.json", "belief_state_private.json", "population_state_private.json")}
        data = {}
        for name, path in paths.items():
            raw = path.read_bytes()
            hashes[str(path)] = hashlib.sha256(raw).hexdigest()
            data[name] = json.loads(raw)
        selected[month] = select_frame(data["population.json"], data["sampling_private.json"], n)
        beliefs[month] = {r["agent_id"]: r for r in data["belief_state_private.json"]["persons"]}
        entries[month] = {r["agent_id"]: r for r in data["population_state_private.json"]["persons"]}
        if not (source / month / "environment.json").exists():
            missing_environments.append(month)
    nodes, summary = build_dependency_plan(selected, beliefs, entries, months=list(months), repeats=repeats)
    summary.update(status="offline_state_roster_prepared_not_prompt_ready", new_api_calls=0,
                   months=list(months), repeats=repeats,
                   sampling="stable_priority_srs_from_delivered_full_monthly_frames",
                   source_sha256=hashes,
                   missing_environment_months=missing_environments,
                   blockers=["Environment and existing CE/confidence/procurement/news prompt adapters not yet assembled",
                             "Resolve invalid past fields using prior-only rules; retain every selected person",
                             "Delivered survey weights require valid/missing provenance before final analysis",
                             "Only initialized state histories may update recursive summaries; no monthly true-history refresh",
                             "Final prompt hashes, cost, concurrency and authorization not yet prepared"],
                   claims="A-line state-continuity pilot; current profiles and monthly mid-month E are not strict B forecasts")
    out.mkdir(parents=True)
    for name, obj in [("selected_private.json", selected), ("state_dependencies_private.json", nodes),
                      ("summary.json", summary)]:
        (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return summary
