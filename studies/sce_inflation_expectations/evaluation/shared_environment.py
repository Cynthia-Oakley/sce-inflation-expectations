"""Lossless public-E export for matched-information baselines. No target data.

Timestamp acceptance checks the supplied metadata, not the underlying vintage.
Inferred release dates remain explicitly uncertain in the audit.
"""
from copy import deepcopy
from datetime import datetime, time
import json
import math


def month_index(value):
    year, month = map(int, str(value).split("-"))
    if not 1 <= month <= 12:
        raise ValueError("invalid month")
    return year * 12 + month - 1


def available_time(stamp, cutoff):
    if not isinstance(stamp, str):
        raise ValueError("missing publication date")
    when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if when.tzinfo is None:
        if len(stamp) != 10:
            raise ValueError("unknown publication timezone")
        # Same-day date-only evidence is admissible only after that day's end.
        when = datetime.combine(when.date(), time(23, 59, 59), cutoff.tzinfo)
    if when > cutoff:
        raise ValueError("future item in shared environment")
    return when


def extract_shared_rows(bundle):
    args = bundle["provider_args"]
    targets = args["targets"]
    if not targets or len({t["target_month"] for t in targets}) != len(targets):
        raise ValueError("targets must be nonempty and unique")
    rows = []
    for step, target in enumerate(targets):
        cutoff = datetime.fromisoformat(target["as_of"])
        if cutoff.tzinfo is None:
            raise ValueError("as_of needs timezone")
        signals = deepcopy(args["signals_by_step"][str(step)])
        news = deepcopy(args.get("events_by_step", {}).get(str(step), []))
        features, uncertainties = {}, []
        signal_ids = set()
        for record in signals:
            if record.get("eligibility") != "eligible":
                raise ValueError("unapproved signal in shared input")
            if not record.get("source_url") or not record.get("source_version"):
                raise ValueError("signal source evidence missing")
            available_time(record.get("published_at"), cutoff)
            lag = month_index(target["target_month"]) - month_index(record["reference_period"])
            if lag < 0:
                raise ValueError("future reference month")
            key = json.dumps([record["measure"], record["unit"], record.get("role"), lag], separators=(",", ":"))
            value = float(record["value"])
            if not math.isfinite(value) or key in features or record["signal_id"] in signal_ids:
                raise ValueError("nonfinite or duplicate signal")
            signal_ids.add(record["signal_id"])
            features[key] = value
            note = record.get("note", "")
            if "conservative" in note.lower() or "last weekly obs" in note.lower():
                uncertainties.append({"signal_id": record["signal_id"], "issue": "inferred_release_date_or_unverified_vintage", "note": note})
        news_ids = set()
        for event in news:
            available_time(event.get("published_at") or event.get("pub_date"), cutoff)
            if event["event_id"] in news_ids:
                raise ValueError("duplicate news")
            news_ids.add(event["event_id"])
        broadcasts = [deepcopy(b) for b in bundle.get("information_program", {}).get("broadcasts", []) if b["at_step"] == step]
        rows.append({"target_month": target["target_month"], "as_of": target["as_of"],
                     "numeric_features": dict(sorted(features.items())), "signals": signals,
                     "news": news, "broadcasts": broadcasts,
                     "news_text": "\n\n".join(f"{e.get('headline', '')}\n{e.get('abstract', '')}" for e in news),
                     "evidence_uncertainties": uncertainties})
    return rows
