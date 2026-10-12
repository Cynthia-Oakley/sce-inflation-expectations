"""Deterministic era narratives from vintage CPI paths; no LLM or target answers."""
import argparse
from copy import deepcopy
import csv
from datetime import datetime
import json
import math
from pathlib import Path

from .lifetime_experience import insert_block, json_hash, validate_source, MARKER
from .lifetime_sources import MONTHS, dump, sha

ARMS = ("original", "common_episodes", "age_matched_episodes")


def month_number(month):
    return int(month[:4])*12+int(month[5:7])-1


def monthly_changes(rows, column, last_year):
    indexes = {}
    for row in rows:
        value, month = row[column], row["observation_date"][:7]
        if value in ("", ".") or int(month[:4]) > last_year:
            continue
        number = float(value)
        if month in indexes or not math.isfinite(number) or number <= 0:
            raise ValueError("invalid or duplicate CPI observation")
        indexes[month] = number
    result = []
    for month, value in sorted(indexes.items()):
        lag = f"{int(month[:4])-1}-{month[5:7]}"
        if lag in indexes:
            result.append({"month": month, "cpi_yoy_pct": 100*(value/indexes[lag]-1)})
    return result


def select_landmarks(path, cap=8):
    """Keep endpoints/extremes and strongest December-to-December turning points.

    December observations are samples of monthly YoY, not annual-average rates.
    Selection uses observed CPI only, never SCE or the model's generated answer.
    """
    if not path or cap < 4:
        raise ValueError("nonempty path and at least four landmark slots required")
    values = [x["cpi_yoy_pct"] for x in path]
    chosen = {0, len(path)-1, max(range(len(path)), key=values.__getitem__), min(range(len(path)), key=values.__getitem__)}
    samples = sorted({0, len(path)-1} | {i for i, p in enumerate(path) if p["month"].endswith("-12")})
    turns = []
    for j in range(1, len(samples)-1):
        left, here, right = samples[j-1:j+2]
        if (values[here]-values[left])*(values[right]-values[here]) < 0:
            turns.append((abs(values[here]-values[left])+abs(values[right]-values[here]), here))
    # Fill with salient turns, then calendar samples if fewer turns exist.
    candidates = [i for _, i in sorted(turns, key=lambda x: (-x[0], x[1]))] + samples
    for i in candidates:
        if len(chosen) >= cap:
            break
        chosen.add(i)
    return [path[i] for i in sorted(chosen)]


def history_duration(path, peak, complete_history, threshold):
    # 'peak' denotes the maximum observed within this window. An endpoint
    # maximum must not be presented as a confirmed economic turning point.
    longest, current = 0, 0
    for p in path:
        current = current+1 if p["cpi_yoy_pct"] >= threshold else 0
        longest = max(longest, current)
    recovery = None
    peak_run = None
    if peak["cpi_yoy_pct"] >= threshold:
        recovery = next((p for p in complete_history if p["month"] > peak["month"] and p["cpi_yoy_pct"] < threshold), None)
        index = next(i for i, p in enumerate(complete_history) if p["month"] == peak["month"])
        first, last = index, index
        while first > 0 and complete_history[first-1]["cpi_yoy_pct"] >= threshold:
            first -= 1
        while last+1 < len(complete_history) and complete_history[last+1]["cpi_yoy_pct"] >= threshold:
            last += 1
        peak_run = {"start": complete_history[first]["month"], "end": complete_history[last]["month"],
                    "known_months": last-first+1, "left_censored": first == 0,
                    "right_censored": last == len(complete_history)-1}
    return {"threshold_pct": threshold, "longest_consecutive_months_shown_at_or_above_threshold": longest,
            "continuous_high_inflation_spell_around_peak": peak_run,
            "peak_month": peak["month"], "first_subsequent_month_below_threshold": None if recovery is None else recovery["month"],
            "months_from_peak_to_below_threshold": None if recovery is None else month_number(recovery["month"])-month_number(peak["month"]),
            "no_subsequent_fall_observed_by_history_end": peak["cpi_yoy_pct"] >= threshold and recovery is None}


def make_cards(history, catalogue, birth_range, start_age, cutoff):
    cutoff_date = cutoff[:10]
    if birth_range is None:
        first_year = 1945
    else:
        # Conservative first full calendar year after the assumed start birthday,
        # for both possible birth years. No exact birthday is invented.
        first_year = max(birth_range)+start_age+1
    personal_history = [p for p in history if int(p["month"][:4]) >= first_year]
    if not personal_history:
        return []
    for left, right in zip(personal_history, personal_history[1:]):
        if month_number(right["month"])-month_number(left["month"]) != 1:
            raise ValueError("missing month in experienced path; no interpolation")
    cards = []
    for era in catalogue["eras"]:
        part = [p for p in personal_history if era["start_year"] <= int(p["month"][:4]) <= era["end_year"]]
        if not part:
            continue
        first, last = part[0]["month"], part[-1]["month"]
        peak = max(part, key=lambda x: x["cpi_yoy_pct"])
        facts = []
        for fact in era["facts"]:
            source = catalogue["sources"][fact["source_id"]]
            # Review dates identify the actual archived source being used in A;
            # they are not certified first-publication or byte-vintage dates.
            if source["review_date"] > cutoff_date or fact["event_end"] > last:
                continue
            if fact["event_end"] < first or fact["event_start"] > last:
                continue
            facts.append(fact)
        ages = None if birth_range is None else [int(first[:4])-max(birth_range)-1, int(last[:4])-min(birth_range)]
        stages = [] if ages is None else [name for lo, hi, name in ((0, 11, "childhood"), (12, 17, "adolescence"), (18, 120, "adulthood")) if ages[0] <= hi and ages[1] >= lo]
        cards.append({"era_id": era["id"], "label": era["label"], "covered_start": first, "covered_end": last,
            "n_months": len(part), "age_range_approximate": ages, "life_stages": stages,
            "landmarks": select_landmarks(part, catalogue["landmark_cap_per_era"]),
            "duration": history_duration(part, peak, personal_history, catalogue["duration_threshold_pct"]),
            "context_facts": facts, "source_ids": sorted({f["source_id"] for f in facts})})
    return cards


def trend_sentence(points):
    values = [p["cpi_yoy_pct"] for p in points]
    if min(values) < 0 and values[0] >= 0 and values[-1] > 0:
        return "The year-over-year inflation rate turned negative during the episode and later became positive again."
    directions = []
    for left, right in zip(values, values[1:]):
        direction = "rose" if right > left else "eased" if right < left else None
        if direction and (not directions or direction != directions[-1]):
            directions.append(direction)
    if not directions:
        return "The sampled inflation rates were broadly unchanged."
    if len(directions) > 3:
        return "Inflation rose and eased repeatedly during this period."
    return "Inflation " + ", then ".join(directions) + "."


def render_cards(cards, intro, involvement=False):
    lines = [intro]
    shown_spells = set()
    for card in cards:
        ages = card["age_range_approximate"]
        stage = "" if ages is None else f"; roughly ages {ages[0]}-{ages[1]} ({'/'.join(card['life_stages'])})"
        lines.append(f"{card['covered_start']} to {card['covered_end']}: {card['label']}{stage}.")
        for fact in card["context_facts"]:
            lines.append("Context: "+fact["text"])
        lines.append(trend_sentence(card["landmarks"]))
        lines.append("Price path: "+" -> ".join(f"{p['month']} about {p['cpi_yoy_pct']:.1f}%" for p in card["landmarks"])+".")
        duration = card["duration"]
        spell = duration["continuous_high_inflation_spell_around_peak"]
        spell_key = None if spell is None else (spell["start"], spell["end"])
        new_spell = spell_key is not None and spell_key not in shown_spells
        if new_spell:
            qualifier = "at least " if spell["left_censored"] or spell["right_censored"] else ""
            lines.append(f"The stretch at/above {duration['threshold_pct']:g}% covers {spell['start']} to {spell['end']}: {qualifier}{spell['known_months']} observed months.")
            shown_spells.add(spell_key)
        if new_spell and duration["months_from_peak_to_below_threshold"] is not None:
            lines.append(f"From the highest observed rate in {duration['peak_month']}, inflation first fell below {duration['threshold_pct']:g}% in {duration['first_subsequent_month_below_threshold']}, {duration['months_from_peak_to_below_threshold']} months later.")
        elif new_spell and duration["no_subsequent_fall_observed_by_history_end"]:
            lines.append(f"No later fall below {duration['threshold_pct']:g}% appears in the history shown so far.")
        # Optional hypothesis, off in the main draft; no asserted shopping duties.
        if involvement and "childhood" in card["life_stages"]:
            lines.append("Childhood contact with prices may have come mainly through family shopping rather than managing household bills.")
        lines.append("")
    return "\n".join(lines).strip()+"\n"


def prepare(root, dest, start_ages=(6, 10, 12, 16), main_start_age=6):
    root, dest = Path(root).resolve(), Path(dest).resolve()
    if dest.exists() or not dest.is_relative_to(root/"outputs"):
        raise ValueError("fresh ignored episode output required")
    if any(a < 0 or a > 18 for a in start_ages):
        raise ValueError("invalid candidate start age")
    if not start_ages or main_start_age not in start_ages:
        raise ValueError("main start age must be present in candidate ages")
    protected = json.loads((root/"docs/sources/sol_handoff_protected_files_20261010.json").read_text())["files_sha256"]
    if any(sha(root/p) != h for p, h in protected.items()):
        raise ValueError("protected pending files changed")
    cat_path = root/"docs/literature/sce/heterogeneity_and_probability/episode_catalogue_20261012.json"
    catalogue = json.loads(cat_path.read_text())
    sources = {str(cat_path.relative_to(root)): sha(cat_path)}
    for src in catalogue["sources"].values():
        if not (root/src["file"]).exists():
            raise ValueError("missing documented context source")
        sources[src["file"]] = sha(root/src["file"])
    cpipath = root/"data/raw/lifetime_experience/20261012_v1/manifest.json"
    cpimeta = json.loads(cpipath.read_text())
    agepath = root/"outputs/sce_age_source_followup_20261012_v2/age_sources_private.json"
    age_rows = json.loads(agepath.read_text())
    base = root/"outputs/sce_confidence_trial_20261011_v1"
    base_plan = json.loads((base/"trial_manifest.json").read_text())
    old_selection_path = root/"outputs/sce_lifetime_trial_draft_20261012_v3/selection_private.json"
    old_bank = json.loads((root/"outputs/sce_lifetime_preparation_20261012_v3/summary.json").read_text())
    old_trial = json.loads(old_selection_path.with_name("trial_manifest.json").read_text())
    if sha(agepath) != old_bank["sources_sha256"][str(agepath.relative_to(root))] or sha(cpipath) != old_bank["sources_sha256"][str(cpipath.relative_to(root))]:
        raise ValueError("previously audited age/CPI source changed")
    if sha(old_selection_path) != old_trial["files_sha256"][old_selection_path.name]:
        raise ValueError("previous age-balanced sample changed")
    selection = json.loads(old_selection_path.read_text())
    for p in (cpipath, agepath, base/"trial_manifest.json", old_selection_path):
        sources[str(p.relative_to(root))] = sha(p)
    dest.mkdir(parents=True)
    summary = {"status": "offline_episode_draft_no_model_run", "research_line": "A_historical_reconstruction",
        "start_age_candidates": list(start_ages), "main_start_age_not_frozen": True, "main_start_age_candidate": main_start_age,
        "main_arms": list(ARMS), "age_precision_arm_removed_from_main": True,
        "optional_age_precision_probe_calls": 0, "template_probe_calls": 0, "new_llm_calls": 0,
        "n_respondent_months": len(age_rows), "source_checks": {}, "per_month": {}, "sources_sha256": sources,
        "involvement_weighting": "life-stage labels only; shopping-involvement text disabled, no numerical weights",
        "limits": ["National history is a background proxy, not observed personal recall or residence history.",
            "Era compression and retained information differ between common and matched arms; not a pure matching effect.",
            "Start ages and 5% duration threshold are research conventions, not estimated universal thresholds.",
            "Four previously studied periods remain development diagnostics; independent holdout not registered.",
            "Current-byte history essays and previous news/gasoline limitations remain; not strict forecast B."],
        "runtime_provider_connected": False}
    cases = []
    examples = {}
    for month in MONTHS:
        folder = dest/month
        folder.mkdir()
        _, evidence = validate_source(root, cpimeta, month)
        summary["source_checks"][month] = evidence
        v = cpimeta["vintages"][month]
        with (root/v["file"]).open() as handle:
            rows = list(csv.DictReader(handle))
        last_year = datetime.fromisoformat(v["as_of"]).year-1
        history = monthly_changes(rows, v["response_column"], last_year)
        dump(folder/"monthly_cpi_yoy_public.json", {"as_of": v["as_of"], "history": history})
        common_cards = make_cards(history, catalogue, None, 0, v["as_of"])
        common = render_cards(common_cards, catalogue["prompt_intro"])
        dump(folder/"shared_episodes_public.json", {"cards": common_cards, "text": common})
        preview_path = base/month/"preview_national_confidence.json"
        if sha(preview_path) != base_plan["prepared_file_sha256"][str(preview_path.relative_to(base))]:
            raise ValueError("original frozen prompts changed")
        sources[str(preview_path.relative_to(root))] = sha(preview_path)
        original = {r["agent_id"]: r for r in json.loads(preview_path.read_text())}
        records = [r for r in age_rows if r["month"] == month]
        selected_ids = {r["local_agent_id"] for r in selection if r["month"] == month}
        sidecars, max_chars = [], 0
        for record in records:
            aid = record["local_agent_id"]
            baseline = original[aid]["messages"]
            candidates = {}
            for age in start_ages:
                cards = make_cards(history, catalogue, record["birth_year_possible_range"], age, v["as_of"])
                text = render_cards(cards, catalogue["prompt_intro"])
                candidates[str(age)] = {"cards": cards, "text": text}
                for arm, block in (("common_episodes", common), ("age_matched_episodes", text)):
                    messages = insert_block(baseline, block)
                    if messages[0]["content"].replace(block+"\n\n", "", 1) != baseline[0]["content"]:
                        raise ValueError("old P/E or questionnaire changed")
                    max_chars = max(max_chars, len(messages[0]["content"]))
                    if age == main_start_age and aid in selected_ids:
                        cases.append({"case_id": f"{month}_{arm}_{aid}", "month": month, "arm": arm,
                            "local_agent_id": aid, "messages": messages, "messages_sha256": json_hash(messages)})
            if aid in selected_ids:
                cases.append({"case_id": f"{month}_original_{aid}", "month": month, "arm": "original",
                    "local_agent_id": aid, "messages": deepcopy(baseline), "messages_sha256": json_hash(baseline)})
            sidecars.append({"local_agent_id": aid, "age_source": record, "candidates": candidates})
        dump(folder/"episodes_private.json", sidecars)
        summary["per_month"][month] = {"n_person_months": len(records), "sample_n": len(selected_ids),
            "history_end": history[-1]["month"], "max_prompt_chars": max_chars,
            "common_card_n": len(common_cards)}
        if month == "202203":
            for label, birth in (("young_25", [1996, 1997]), ("older_75", [1946, 1947])):
                cards = make_cards(history, catalogue, birth, 6, v["as_of"])
                examples[label] = {"synthetic_not_real_respondent": True, "birth_range": birth,
                    "cards": cards, "text": render_cards(cards, catalogue["prompt_intro"])}
    with (dest/"main_cases_private.jsonl").open("w") as handle:
        for case in cases:
            handle.write(json.dumps(case, ensure_ascii=False)+"\n")
    dump(dest/"synthetic_examples_public.json", examples)
    summary.update(main_unique_prompts=len(cases), candidate_repeats=2,
        main_candidate_calls=len(cases)*2,
        unchanged_old_questionnaire_and_PE=True, old_15_pending_files_unchanged=True,
        old_plan_candidate_calls=384, main_call_count_reduction_fraction=1-len(cases)*2/384,
        code_sha256=sha(__file__), catalogue_sha256=sha(cat_path))
    summary["prepared_file_sha256"] = {str(p.relative_to(dest)): sha(p) for p in dest.rglob("*.json*")}
    dump(dest/"summary.json", summary)
    print(json.dumps({k: summary[k] for k in ("n_respondent_months", "main_unique_prompts", "main_candidate_calls", "per_month")}, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start-ages", default="6,10,12,16")
    parser.add_argument("--main-start-age", type=int, default=6)
    args = parser.parse_args()
    prepare(Path(__file__).resolve().parents[2], args.out, tuple(int(a) for a in args.start_ages.split(",")), args.main_start_age)
