"""Offline SCE prior audit and conditional-update messages. No API client.

Observed t-1 answers are permitted only in the disclosed A-line diagnostic.
Current answers and weights never enter a candidate message. This module does
not add memory to the production simulation or certify a historical B vintage.
"""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from .age_reporting_audit import SOURCES

MONTHS = ("202203", "202209", "202303", "202403")
ARMS = ("no_prior", "own_previous", "permuted_previous")
MARKER = "Question 1 (point estimate):"
PRIOR_MARKER = "Your earlier survey response"
SUPPLEMENT = ["date", "userid", "tenure", "survey_date", "Q8v2", "Q8v2part2"]
MATCH = ["_AGE_CAT", "_EDU_CAT", "_NUM_CAT"]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def month_index(month):
    year, m = divmod(int(month), 100)
    if not 1 <= m <= 12:
        raise ValueError("Invalid calendar month")
    return year * 12 + m - 1


def month_offset(month, offset):
    year, m0 = divmod(month_index(month) + offset, 12)
    return year * 100 + m0 + 1


def valid_bins(values):
    try:
        p = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        return False
    return (p.shape == (10,) and np.isfinite(p).all() and (p >= 0).all()
            and (p <= 100).all() and abs(p.sum() - 100) <= 1e-6)


def signed_point(value):
    return float(value) if pd.notna(value) and np.isfinite(value) and abs(value) <= 100 else None


def label_panel(frame):
    f = frame.sort_values(["userid", "date"]).copy()
    if f.duplicated(["userid", "date"]).any():
        raise ValueError("Duplicate respondent-month")
    f["mi"] = f.date.map(month_index)
    f["tenure_valid"] = np.isfinite(f.tenure) & f.tenure.between(1, 12) & (f.tenure % 1 == 0)
    f["previous_date"] = f.groupby("userid").date.shift(1)
    f["previous_tenure"] = f.groupby("userid").tenure.shift(1)
    f["gap_months"] = f.mi - f.groupby("userid").mi.shift(1)
    # Flag inconsistencies observed up to each row, without letting future
    # records change historical entrant eligibility. Resets are not new IDs.
    pair_valid = f.tenure_valid & f.previous_tenure.between(1, 12)
    # Official files increment tenure once per observed response, including
    # after a skipped calendar month; elapsed time is tracked separately.
    mismatch = pair_valid & ((f.tenure - f.previous_tenure) != 1)
    f["timeline_consistent"] = mismatch.groupby(f.userid).cumsum().eq(0)
    f["panel_status"] = "unobserved_previous_or_left_boundary"
    f.loc[f.gap_months.gt(1), "panel_status"] = "returner_after_gap"
    f.loc[f.gap_months.eq(1), "panel_status"] = "adjacent_returner"
    f.loc[f.tenure.eq(1) & f.previous_date.isna(), "panel_status"] = "entry_tenure_1"
    f.loc[~f.timeline_consistent, "panel_status"] = "inconsistent_timeline"
    f.loc[~f.tenure_valid, "panel_status"] = "invalid_or_extended_tenure"
    f["raw_prior_valid"] = [valid_bins([r[f"Q9_bin{i}"] for i in range(1, 11)])
                            for r in f.to_dict("records")]
    return f


def load_reference(root, dest, reuse=None):
    root, dest = Path(root), Path(dest)
    cache = root / "outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet"
    cache_receipt = json.loads(cache.with_name("extraction_receipt.json").read_text())
    registry = json.loads((root / "data/evaluation/sce_baselines_latest_20261007/micro_reference_sources.json").read_text())
    if sha(cache) != cache_receipt["cache_sha256"]:
        raise ValueError("Q9 reference cache changed")
    for source in cache_receipt["sources"]:
        if sha(root / source["path"]) != source["sha256"] or registry["sources"][source["path"]] != source["sha256"]:
            raise ValueError("Official workbook source changed")
    if reuse is not None:
        reuse = Path(reuse).resolve()
        if not reuse.is_relative_to(root / "outputs"):
            raise ValueError("Reuse must be an ignored prior preparation output")
        receipt = json.loads(reuse.with_name("reference_receipt.json").read_text())
        if sha(reuse) != receipt["sha256"] or receipt["q9_cache_sha256"] != sha(cache):
            raise ValueError("Supplement cache changed")
        for source in receipt["sources"]:
            if sha(root / source["path"]) != source["sha256"]:
                raise ValueError("Supplement source changed")
        frame = pd.read_parquet(reuse)
        if len(frame) != receipt["rows"] or frame.duplicated(["userid", "date"]).any():
            raise ValueError("Supplement row structure changed")
        dump(dest / "reference_reuse_receipt.json", {"path": str(reuse.relative_to(root)), "original": receipt})
        return frame
    records, sources = [], []
    for name, start, stop in SOURCES:
        path = root / name
        book = load_workbook(path, read_only=True, data_only=True)
        it = book[book.sheetnames[0]].iter_rows(values_only=True)
        next(it)
        header = list(next(it))
        positions = {k: header.index(k) for k in SUPPLEMENT}
        n = 0
        for row in it:
            date = row[positions["date"]]
            if isinstance(date, (int, float)) and start <= date <= stop:
                records.append({k: row[v] for k, v in positions.items()})
                n += 1
        book.close()
        sources.append({"path": name, "sha256": sha(path), "rows": n})
        print("Supplement partition", start, stop, n, flush=True)
    extra = pd.DataFrame(records)
    for k in ["date", "userid", "tenure", "Q8v2part2"]:
        extra[k] = pd.to_numeric(extra[k], errors="coerce")
    extra["survey_date"] = pd.to_datetime(extra.survey_date, errors="coerce")
    reference = pd.read_parquet(cache)
    frame = reference.merge(extra, on=["date", "userid"], validate="one_to_one", how="outer", indicator=True)
    if len(frame) != cache_receipt["rows"] or not frame._merge.eq("both").all():
        raise ValueError("Supplement does not reconcile with verified Q9 cache")
    frame = frame.drop(columns="_merge")
    frame.to_parquet(dest / "reference_private.parquet", index=False)
    dump(dest / "reference_receipt.json", {"rows": len(frame), "sha256": sha(dest / "reference_private.parquet"),
        "sources": sources, "q9_cache": str(cache.relative_to(root)), "q9_cache_sha256": sha(cache),
        "supplement_fields": SUPPLEMENT, "code_sha256": sha(__file__), "actual_api_calls": 0})
    return frame


def prior_record(row):
    probabilities = [float(row[f"Q9_bin{i}"]) for i in range(1, 11)]
    if not valid_bins(probabilities):
        raise ValueError("No valid raw previous Q9")
    return {"source_month": int(row["date"]), "point_pct": signed_point(row["Q8v2part2"]),
            "q9": {f"bin{i}": probabilities[i - 1] for i in range(1, 11)}}


def eligible_previous(current, previous, target_month, cutoff_date):
    """Eligibility never reads the current respondent's Q8, Q9 or weights."""
    if previous is None:
        return False
    if current["userid"] != previous["userid"] or int(current["date"]) != int(target_month):
        raise ValueError("Prior person/target binding mismatch")
    if int(previous["date"]) != month_offset(target_month, -1):
        return False
    return bool(current["panel_status"] == "adjacent_returner" and previous["tenure_valid"]
                and previous["timeline_consistent"] and previous["raw_prior_valid"]
                and pd.notna(previous["survey_date"]) and previous["survey_date"].date() < cutoff_date)


def add_prior(messages, prior, target_month):
    source = prior["source_month"]
    if source != month_offset(target_month, -1):
        raise ValueError("Prior must be exactly the previous calendar month")
    if set(prior) != {"source_month", "point_pct", "q9"} or set(prior["q9"]) != {f"bin{i}" for i in range(1, 11)}:
        raise ValueError("Unexpected prior input field")
    if not valid_bins([prior["q9"][f"bin{i}"] for i in range(1, 11)]):
        raise ValueError("Invalid raw prior probabilities")
    p = prior["point_pct"]
    if p is not None and (not isinstance(p, (int, float)) or not np.isfinite(p) or abs(p) > 100):
        raise ValueError("Invalid signed prior point")
    result = deepcopy(messages)
    if len(result) != 1 or set(result[0]) != {"role", "content"} or result[0]["role"] != "user":
        raise ValueError("Frozen one-user-message format required")
    text = result[0]["content"]
    if text.count(MARKER) != 1 or PRIOR_MARKER in text:
        raise ValueError("Question boundary or duplicate prior")
    month = f"{source // 100:04d}-{source % 100:02d}"
    payload = {"point_pct": p, "q9": prior["q9"]}
    block = (f"{PRIOR_MARKER} ({month}):\n"
             "In that survey, you reported beliefs about the 12 months following that earlier survey.\n"
             "The bin numbers below use the same ten ranges listed in Question 2.\n"
             + json.dumps(payload, ensure_ascii=False) + "\n"
             "These were your reported expectations, not measured inflation. "
             "Today's questions concern the next 12 months from today's survey.\n\n")
    before, after = text.split(MARKER, 1)
    result[0]["content"] = before + block + MARKER + after
    return result, block


def derangement(ids, seed):
    ids = sorted(ids)
    if len(ids) < 2 or len(ids) != len(set(ids)):
        raise ValueError("At least two unique people required")
    rng = random.Random(seed)
    for _ in range(10000):
        perm = ids.copy()
        rng.shuffle(perm)
        if all(a != b for a, b in zip(ids, perm)):
            return dict(zip(ids, perm))
    raise RuntimeError("Derangement generation failed")


def entry_inventory(frame, target_month, limit_month=None):
    upper = month_offset(target_month, -1) if limit_month is None else int(limit_month)
    lower = month_offset(upper, -11)
    # Eligible entrants are confirmed by their tenure and observed sequence;
    # no current target outcome is considered. Keep one joint donor record.
    pool = frame.loc[frame.date.between(lower, upper) & frame.panel_status.eq("entry_tenure_1")
                     & frame.raw_prior_valid & np.isfinite(frame.weight) & frame.weight.gt(0)].copy()
    if pool.userid.duplicated().any():
        raise ValueError("Duplicate observed entrant")
    return pool


def matched_entry_pool(pool, profile, min_support=30):
    """Hierarchical support; thresholds are research choices, not fitted to outcomes."""
    if min_support < 2:
        raise ValueError("A supported group is required")
    levels = [MATCH, MATCH[:2], MATCH[:1], []]
    for keys in levels:
        mask = pd.Series(True, index=pool.index)
        for key in keys:
            value = profile.get(key)
            if not isinstance(value, str) or not value.strip():
                mask &= False
            else:
                mask &= pool[key].eq(value)
        group = pool.loc[mask]
        if len(group) >= min_support:
            return group, list(keys)
    return pool.iloc[:0], None


def summarize_panel(frame, targets):
    f = label_panel(frame)
    transitions = f.loc[f.previous_date.notna() & f.tenure_valid & f.previous_tenure.between(1, 12)]
    out = {"rows": len(f), "months": int(f.date.nunique()), "unique_ids": int(f.userid.nunique()),
           "tenure_counts": {str(k): int(v) for k, v in f.tenure.value_counts(dropna=False).sort_index().items()},
           "panel_status_counts": dict(Counter(f.panel_status)),
           "transition_pairs": len(transitions),
           "tenure_increment_equals_calendar_gap": int(((transitions.tenure - transitions.previous_tenure) == transitions.gap_months).sum()),
           "tenure_increment_equals_one_response": int(((transitions.tenure - transitions.previous_tenure) == 1).sum()),
           "calendar_gap_transition_counts": [{"calendar_gap": int(g), "tenure_increment": int(d), "pairs": int(n)}
               for (g, d), n in transitions.assign(dt=transitions.tenure-transitions.previous_tenure).groupby(["gap_months", "dt"]).size().items()],
           "inconsistent_ids": int(f.loc[~f.timeline_consistent].userid.nunique()),
           "missing_survey_date_rows": int(f.survey_date.isna().sum()),
           "calendar_coding_statement": "Observed tenure increments once per completed response, even after calendar gaps. Calendar adjacency is checked separately. This is a data audit, not a recovered enrollment contract.",
           "monthly_targets": {}}
    for month in targets:
        block = f.loc[f.date.eq(int(month))]
        out["monthly_targets"][month] = {"wave_n": len(block), "status_counts": dict(Counter(block.panel_status)),
            "adjacent_returners_n": int(block.panel_status.eq("adjacent_returner").sum()),
            "tenure_1_entries_n": int(block.panel_status.eq("entry_tenure_1").sum())}
    return f, out
