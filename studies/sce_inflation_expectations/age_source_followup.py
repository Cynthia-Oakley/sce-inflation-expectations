"""Read-only Q32 source audit, not a population builder or simulation provider."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import pandas as pd


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reported_age_bounds(age, source_month, target_month):
    """Birth-year bounds and conservative follow-up ages without birthday data.

    Same-month range denotes the self-report at that survey, not every day of
    the month. Other ranges allow unknown entry/target day and birthday.
    """
    age = int(age)
    gap = (target_month//100-source_month//100)*12+target_month%100-source_month%100
    if gap < 0 or not 18 <= age <= 110:
        raise ValueError("future or invalid reported age")
    birth = [source_month//100-age-1, source_month//100-age]
    current = [age, age] if gap == 0 else [age+max(0, (gap-1)//12), age+(gap+12)//12]
    return gap, birth, current


def audit(root, out):
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / "outputs"):
        raise ValueError("fresh ignored output required")
    cache = root / "outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet"
    receipt = json.loads(cache.with_name("extraction_receipt.json").read_text())
    if sha(cache) != receipt["cache_sha256"]:
        raise ValueError("Q32 extraction cache drift")
    link_path = root / "outputs/sce_confidence_trial_20261011_v1/evaluation_links_private.json"
    prior = json.loads((root / "outputs/sce_confidence_response_diagnostic_20261012_v2/summary.json").read_text())
    if sha(link_path) != prior["sources_sha256"][str(link_path.relative_to(root))]:
        raise ValueError("evaluation identity links changed")
    data = pd.read_parquet(cache, columns=["date", "userid", "Q32", "_AGE_CAT"])
    links = json.loads(link_path.read_text())
    records, counts, per_month = [], Counter(), {}
    for row in links:
        month = int(row["month"])
        person = int(row["source_agent_id"].removeprefix("sce_u"))
        candidates = data[(data.userid == person) & (data.date <= month) &
            data.Q32.between(18, 110) & (data.Q32.round() == data.Q32)].sort_values("date")
        if candidates.empty:
            raise ValueError("missing Q32 requires explicit new handling")
        source = candidates.iloc[-1]
        gap, birth, age_range = reported_age_bounds(int(source.Q32), int(source.date), month)
        status = "same_month_self_report" if gap == 0 else "prior_1_to_11_months" if gap <= 11 else "older_report_review"
        records.append({"month": row["month"], "local_agent_id": row["agent_id"],
            "source_age_month": int(source.date), "source_age_self_report": int(source.Q32),
            "source_age_group": source._AGE_CAT, "gap_months": gap, "status": status,
            "birth_year_possible_range": birth, "target_month_age_conservative_range": age_range,
            "not_added_to_P": True})
        counts[status] += 1
        per_month.setdefault(row["month"], Counter())[status] += 1
    out.mkdir(parents=True)
    result = {"checked_on": "2026-10-12", "scope": "Current four-period 48-person samples only; 192 respondent-months, not necessarily 192 different people.",
        "selected_rows": len(links), "status_counts": dict(counts), "per_month": {k: dict(v) for k, v in per_month.items()},
        "cache_sha256": receipt["cache_sha256"], "evaluation_links_sha256": sha(link_path),
        "age_question": "Q32, self-reported age at survey, normally entry-only",
        "inference": "Birth year interval, not exact birthday; follow-up ages are ranges. Older reports require separate review.",
        "new_api_calls": 0, "P_modified": False,
        "limits": ["Current retrospective files, not historical real-time B availability.",
            "Reported age is not independently verified chronological age.",
            "National economic history does not identify birthplace, migration, attention or personal recollection."]}
    for name, value in (("age_sources_private.json", records), ("summary.json", result)):
        (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")
    (out/"source_receipt.json").write_text(json.dumps({"code_sha256": sha(Path(__file__)), "new_api_calls": 0}, indent=2)+"\n")
    print(json.dumps(result["status_counts"]))
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    audit(Path(__file__).resolve().parents[2], args.out)
