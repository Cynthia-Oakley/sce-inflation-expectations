"""Offline lifetime-background sidecars and paired prompts; no model calls."""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics

from pypdf import PdfReader

from .lifetime_sources import MONTHS, dump, sha

MARKER = "Question 1 (point estimate):"
ARMS = ("original", "age_only", "common_history", "age_matched_history")
HISTORY_NOTE = (
    "Historical U.S. background, not a forecast. These national statistics are "
    "a proxy for the economic environment across generations, not measurements "
    "of your own spending, attention, or recollection. No personal migration or "
    "residence history was observed. The inflation measure below is the percent "
    "change in the full-year average CPI-U index relative to the previous full "
    "year, not a monthly change or a December-to-December change."
)


def annual_inflation(rows, column, last_year):
    """Compute from all twelve NSA months; missing years are never interpolated."""
    monthly = defaultdict(dict)
    for row in rows:
        date, value = row["observation_date"], row[column]
        if value in ("", "."):
            continue
        year, month = int(date[:4]), int(date[5:7])
        if year > last_year:
            continue
        number = float(value)
        if month in monthly[year] or not math.isfinite(number) or number <= 0:
            raise ValueError("duplicate or invalid CPI month")
        monthly[year][month] = number
    means = {y: statistics.mean(m.values()) for y, m in monthly.items() if set(m) == set(range(1, 13))}
    return {y: {"year": y, "annual_average_index": means[y],
                "annual_average_yoy_pct": 100 * (means[y] / means[y-1] - 1)}
            for y in sorted(means) if y-1 in means}


def period_stats(annual, first, last):
    if first > last:
        return None
    if any(y not in annual for y in range(first, last+1)):
        raise ValueError("incomplete history period; no silent substitution")
    values = [annual[y]["annual_average_yoy_pct"] for y in range(first, last+1)]
    return {"first_year": first, "last_year": last, "n_years": len(values),
            "mean_annual_change_pct": statistics.mean(values),
            "min_annual_change_pct": min(values), "max_annual_change_pct": max(values)}


def stage_summaries(annual, birth_year, start_age, last_year):
    stages = ((6, 17), (18, 29), (30, 49), (50, 110))
    result = []
    for low, high in stages:
        low = max(low, start_age)
        first, last = birth_year + low, min(birth_year + high, last_year)
        if low > high or first > last:
            continue
        stats = period_stats(annual, first, last)
        result.append({"stage_ages": [low, min(high, last-birth_year)], **stats})
    return result


def event_matches(events, birth_years, start_age, last_year):
    matches = []
    for event in events:
        if event["end_year"] > last_year:
            continue
        overlaps = []
        for birth in birth_years:
            first = max(event["start_year"], birth+start_age)
            if first <= event["end_year"]:
                overlaps.append([first-birth, event["end_year"]-birth])
        if overlaps:
            matches.append({**event, "overlap_status": "all_birth_year_candidates" if len(overlaps) == len(birth_years) else "some_birth_year_candidates",
                            "age_during_overlap_range": [min(x[0] for x in overlaps), max(x[1] for x in overlaps)]})
    return matches


def age_text(record):
    low, high = record["target_month_age_conservative_range"]
    age = str(low) if low == high else f"{low}-{high}"
    text = (f"Age detail: approximately {age} years at this survey; "
            "based on a self-reported survey age. An exact birthday is unavailable.")
    if low == 60 and record["source_age_group"] == "Over 60":
        text += " In the observed survey data, the 'Over 60' category also includes age 60."
    return text


def matched_text(record, annual, events, start_age, last_year):
    birth_years = list(range(record["birth_year_possible_range"][0], record["birth_year_possible_range"][1]+1))
    endpoints = {str(b): stage_summaries(annual, b, start_age, last_year) for b in birth_years}
    lines = [HISTORY_NOTE, f"Age-linked background uses years from about age {start_age} through {last_year}; "
             "the starting age is a research convention, not an observed memory threshold."]
    stages = defaultdict(list)
    for stats in endpoints.values():
        for stage in stats:
            stages[stage["stage_ages"][0]].append(stage)
    for key, values in sorted(stages.items()):
        means = [v["mean_annual_change_pct"] for v in values]
        lo, hi = min(means), max(means)
        value_text = f"{lo:.2f}%" if round(lo, 2) == round(hi, 2) else f"{lo:.2f}% to {hi:.2f}%"
        lines.append(f"- Approximately ages {key}-{max(v['stage_ages'][1] for v in values)}: "
                     f"mean annual CPI change {value_text}; covers complete calendar years only.")
    selected = event_matches(events, birth_years, start_age, last_year)
    for event in selected:
        lo, hi = event["age_during_overlap_range"]
        status = "possibly" if event["overlap_status"] == "some_birth_year_candidates" else "approximately"
        lines.append(f"- {event['start_year']}-{event['end_year']} ({status} ages {lo}-{hi} during the overlapping period): {event['fact']}")
    return "\n".join(lines) + "\n", {"birth_year_scenarios": endpoints, "events": selected}


def common_text(annual, events, last_year):
    # Fixed beginning for this draft; not selected using any SCE response.
    lines = [HISTORY_NOTE, f"Shared historical background, 1945-{last_year}; the same account is provided to everyone."]
    stats = []
    for decade in range(1940, last_year+1, 10):
        first, last = max(1945, decade), min(decade+9, last_year)
        value = period_stats(annual, first, last)
        stats.append(value)
        lines.append(f"- {first}-{last}: mean annual CPI change {value['mean_annual_change_pct']:.2f}%.")
    for event in events:
        if event["end_year"] <= last_year:
            lines.append(f"- {event['start_year']}-{event['end_year']}: {event['fact']}")
    return "\n".join(lines) + "\n", stats


def insert_block(messages, block):
    if len(messages) != 1 or messages[0]["role"] != "user" or messages[0]["content"].count(MARKER) != 1:
        raise ValueError("frozen message structure changed")
    result = deepcopy(messages)
    result[0]["content"] = messages[0]["content"].replace(MARKER, block+"\n\n"+MARKER, 1)
    return result


def json_hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_source(root, manifest, month):
    vintage = manifest["vintages"][month]
    date = vintage["as_of"][:10]
    if vintage["requested_vintage_date"] != date or vintage["response_column"] != "CPIAUCNS_"+date.replace("-", ""):
        raise ValueError("historical version must correspond to the declared cutoff")
    path = root / vintage["file"]
    if sha(path) != vintage["sha256"]:
        raise ValueError("CPI CSV source changed")
    with path.open() as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["observation_date", vintage["response_column"]]:
            raise ValueError("CPI vintage column mismatch")
        rows = list(reader)
    observed_dates = [r["observation_date"] for r in rows if r[vintage["response_column"]] not in ("", ".")]
    if max(observed_dates) != vintage["last_observation"] or max(observed_dates) >= date:
        raise ValueError("future or mismatched observation endpoint")
    ref = vintage["last_observation"][:7]
    pdfs = list((root / "data/raw/bls_initial_releases" / ref).glob("cpi_*.pdf"))
    if len(pdfs) != 1:
        raise ValueError("one independent CPI release PDF required")
    reader = PdfReader(pdfs[0])
    first = " ".join((reader.pages[0].extract_text() or "").split())
    cutoff = datetime.fromisoformat(vintage["as_of"])
    expected_date = cutoff.strftime("%B ") + str(cutoff.day) + cutoff.strftime(", %Y")
    if expected_date not in first or "8:30 a.m." not in first:
        raise ValueError("independent BLS release date mismatch")
    last = next(r for r in rows if r["observation_date"] == vintage["last_observation"])
    value = last[vintage["response_column"]]
    text = " ".join(p.extract_text() or "" for p in reader.pages)
    if value not in text:
        raise ValueError("latest ALFRED NSA CPI value absent in independent release")
    annual = annual_inflation(rows, vintage["response_column"], cutoff.year-1)
    return annual, {"vintage_date": vintage["requested_vintage_date"],
        "as_of": vintage["as_of"], "latest_reference_month": ref, "latest_nsa_index": float(value),
        "bls_release_pdf": str(pdfs[0].relative_to(root)), "bls_sha256": sha(pdfs[0]),
        "release_date_and_latest_value_cross_checked": True,
        "all_historical_rows_independently_cross_checked": False,
        "completed_annual_yoy_first_year": min(annual), "completed_annual_yoy_last_year": max(annual)}


def prepare(root, sources, dest):
    root, sources, dest = Path(root).resolve(), Path(sources).resolve(), Path(dest).resolve()
    if dest.exists() or not dest.is_relative_to(root / "outputs"):
        raise ValueError("fresh ignored output required")
    protected = json.loads((root / "docs/sources/sol_handoff_protected_files_20261010.json").read_text())["files_sha256"]
    if any(sha(root/p) != h for p, h in protected.items()):
        raise ValueError("protected pending files changed")
    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["status"] != "downloaded_for_offline_source_validation":
        raise ValueError("incomplete source archive")
    for source in manifest["history_sources"].values():
        if sha(root/source["file"]) != source["sha256"]:
            raise ValueError("history source changed")
    age_dir = root / "outputs/sce_age_source_followup_20261012_v2"
    age_records = json.loads((age_dir / "age_sources_private.json").read_text())
    if sha(age_dir / "age_sources_private.json") != sha(root / "outputs/sce_age_source_followup_20261012_v1/age_sources_private.json"):
        raise ValueError("age source verification drift")
    base_dir = root / "outputs/sce_confidence_trial_20261011_v1"
    base_plan = json.loads((base_dir / "trial_manifest.json").read_text())
    source_hashes = {str(manifest_path.relative_to(root)): sha(manifest_path),
        str((age_dir / "age_sources_private.json").relative_to(root)): sha(age_dir / "age_sources_private.json"),
        str((base_dir / "trial_manifest.json").relative_to(root)): sha(base_dir / "trial_manifest.json")}
    dest.mkdir(parents=True)
    receipt = {"status": "offline_draft_not_runtime_configuration", "research_line": "A_historical_reconstruction",
        "months": list(MONTHS), "arms": list(ARMS), "respondent_month_rows": len(age_records),
        "new_llm_calls": 0, "new_paid_mcp_calls": 0, "existing_configuration_changed": False,
        "start_age_primary_candidate": 6, "start_age_alternative": 18, "start_age_frozen": False,
        "sources_sha256": source_hashes, "source_checks": {}, "per_month": {}, "acceptance": {},
        "limits": ["Older 13-month age sources remain flagged; pilot selection can omit them without deleting records.",
            "Age and residence/recall are not jointly observed; national history is a proxy.",
            "Common versus matched changes historical compression and retained information; not a pure matching-effect estimate.",
            "History essays are current downloaded bytes with a 2013 written-as-of date; not certified past byte versions.",
            "Existing NYT/gasoline version limitations remain; not strict route-B prediction.",
            "These four periods have been examined before; not an independent holdout.",
            "Inherited Q8/Q9 wording is preserved exactly; it is an existing project rendering, not verbatim official questionnaire."]}
    prompt_counts, age_spreads, stage_counts = Counter(), [], Counter()
    for month in MONTHS:
        folder = dest / month
        folder.mkdir()
        annual, evidence = validate_source(root, manifest, month)
        receipt["source_checks"][month] = evidence
        last_year = max(annual)
        dump(folder / "annual_cpi_public.json", list(annual.values()))
        common, common_stats = common_text(annual, manifest["events"], last_year)
        dump(folder / "shared_history_public.json", {"text": common, "stats": common_stats, "source_check": evidence})
        preview_path = base_dir / month / "preview_national_confidence.json"
        expected = base_plan["prepared_file_sha256"][str(preview_path.relative_to(base_dir))]
        if sha(preview_path) != expected:
            raise ValueError("old frozen preview changed")
        source_hashes[str(preview_path.relative_to(root))] = sha(preview_path)
        previews = {p["agent_id"]: p for p in json.loads(preview_path.read_text())}
        records = [r for r in age_records if r["month"] == month]
        prompts, sidecars = {arm: [] for arm in ARMS}, []
        for record in records:
            aid = record["local_agent_id"]
            original = previews[aid]["messages"]
            if hashlib.sha256(json.dumps(original, ensure_ascii=False).encode()).hexdigest() != previews[aid]["prompt_sha256"]:
                raise ValueError("frozen prompt hash mismatch")
            matched, details = matched_text(record, annual, manifest["events"], 6, last_year)
            adult, adult_details = matched_text(record, annual, manifest["events"], 18, last_year)
            age = age_text(record)
            blocks = {"original": "", "age_only": age,
                      "common_history": age+"\n\n"+common, "age_matched_history": age+"\n\n"+matched}
            original_suffix = original[0]["content"].split(MARKER, 1)[1]
            for arm, block in blocks.items():
                messages = deepcopy(original) if arm == "original" else insert_block(original, block)
                if messages[0]["content"].split(MARKER, 1)[1] != original_suffix:
                    raise ValueError("questionnaire/output changed")
                if arm != "original" and messages[0]["content"].replace(block+"\n\n", "", 1) != original[0]["content"]:
                    raise ValueError("P/E changed beyond declared inserted background")
                prompts[arm].append({"agent_id": aid, "messages": messages,
                    "canonical_messages_sha256": json_hash(messages), "base_prompt_sha256": previews[aid]["prompt_sha256"]})
                prompt_counts[arm] += 1
            scenarios = details["birth_year_scenarios"]
            means = [statistics.mean(annual[y]["annual_average_yoy_pct"] for y in range(int(b)+6, last_year+1)) for b in scenarios]
            age_spreads.append(max(means)-min(means))
            stage_counts[len(next(iter(scenarios.values())))] += 1
            sidecars.append({"agent_id": aid, "age_source": record, "primary_candidate_text": matched,
                "primary_candidate_details": details, "adult_alternative_text": adult,
                "adult_alternative_details": adult_details, "eligible_for_first_pilot": record["status"] != "older_report_review"})
        for arm, value in prompts.items():
            dump(folder / ("preview_"+arm+"_private.json"), value)
        dump(folder / "life_background_private.json", sidecars)
        receipt["per_month"][month] = {"n": len(records), "first_pilot_eligible": sum(r["status"] != "older_report_review" for r in records),
            "last_completed_year": last_year, "max_prompt_chars": max(len(p["messages"][0]["content"]) for ps in prompts.values() for p in ps)}
    receipt["prompt_counts"] = dict(prompt_counts)
    receipt["birth_year_interval_mean_rate_sensitivity_pp"] = {
        "median": statistics.median(age_spreads), "max": max(age_spreads),
        "definition": "Difference between mean annual CPI changes over complete years from age 6, for the two possible birth years; not SCE prediction uncertainty."}
    receipt["nonempty_stage_count_distribution"] = dict(stage_counts)
    receipt["acceptance"] = {"questionnaire_and_output_unchanged": True,
        "old_PE_policy_confidence_and_news_unchanged": True, "no_current_partial_years": True,
        "four_latest_nsa_values_match_independent_BLS_releases": True,
        "strict_B_inputs_accepted": False, "old_15_pending_files_unchanged": True,
        "real_LLM_effect_tested": False, "runtime_provider_connected": False}
    receipt["code_sha256"] = sha(__file__)
    receipt["prepared_file_sha256"] = {str(p.relative_to(dest)): sha(p) for p in dest.rglob("*.json")}
    dump(dest / "summary.json", receipt)
    print(json.dumps({"prompt_counts": receipt["prompt_counts"],
                      "birth_year_sensitivity": receipt["birth_year_interval_mean_rate_sensitivity_pp"],
                      "source_checks": receipt["source_checks"]}, ensure_ascii=False))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    prepare(Path(__file__).resolve().parents[2], args.sources, args.out)
