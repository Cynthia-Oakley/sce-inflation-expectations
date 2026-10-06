#!/usr/bin/env python3
"""Audit a complete SCE population's synthetic CE baskets, fully offline.

The audit reads CE FMLI expenditure fields and SCE persona IDs, whitelisted
attributes, and persona weights only. It never reads SCE Q8/Q9 answers. CE
interview weights describe CE donors; ``persona.weight`` describes the
provided synthetic population. Their overall summaries have different target
populations and are not expected to agree.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from studies.sce_inflation_expectations.price_experience import (
    CATEGORIES,
    BasketAssigner,
    prepare_ce_donors,
    profile_hash,
)

QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
COMMON_GROUPS = (
    "age_group", "region", "education_group", "household_income_band",
    "housing_tenure",
)
ZERO_TOLERANCE = 1e-12


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_ce(path: Path, member: str | None) -> tuple[list[dict], bytes, str | None]:
    raw = path.read_bytes()
    if zipfile.is_zipfile(path):
        if not member:
            raise ValueError("ZIP input requires one explicit --member FMLI CSV")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            try:
                data = archive.read(member)
            except KeyError as exc:
                raise ValueError(f"CE ZIP has no member {member!r}") from exc
    else:
        if member:
            raise ValueError("--member only applies to ZIP input")
        data = raw
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    if not rows:
        raise ValueError("empty CE FMLI CSV")
    return rows, data, member


def _positive_weight(value, label: str) -> float:
    try:
        weight = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid {label}") from exc
    if not math.isfinite(weight) or weight <= 0:
        raise ValueError(f"{label} must be positive and finite")
    return weight


def _population(population: dict) -> dict[str, dict]:
    personas = population.get("personas")
    if not isinstance(personas, list) or not personas:
        raise ValueError("population needs nonempty personas")
    if population.get("materialized_count") != len(personas):
        raise ValueError("population materialized_count does not cover every persona")
    provider_args = population.get("provider_args") or {}
    if provider_args.get("sampling_design") != "census":
        raise ValueError("full population must declare sampling_design=census")
    people = {}
    for person in personas:
        if not isinstance(person, dict):
            raise ValueError("invalid persona record")
        agent_id = str(person.get("agent_id", "")).strip()
        attrs = person.get("attributes")
        if not agent_id or agent_id in people or not isinstance(attrs, dict):
            raise ValueError("population requires unique IDs and profile attributes")
        people[agent_id] = {
            "attributes": attrs,
            "weight": _positive_weight(person.get("weight"), f"persona weight for {agent_id}"),
        }
        if not math.isclose(people[agent_id]["weight"], 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("monthly PopulationBundle persona.weight must remain neutral at 1.0")
    return people


def _read_analysis_weights(path: Path, people: dict[str, dict], expected_month: str) -> dict[str, float]:
    weights = {}
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid analysis weights JSONL at line {line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"invalid analysis weights row at line {line_number}")
            agent_id = str(row.get("agent_id", "")).strip()
            if not agent_id or agent_id in weights:
                raise ValueError("analysis weights require unique nonempty agent_id values")
            row_month = _month_key(row.get("target_month", row.get("month")))
            if row_month != expected_month:
                raise ValueError(f"analysis weights month mismatch at line {line_number}")
            weights[agent_id] = _positive_weight(
                row.get("analysis_weight"), f"analysis_weight at line {line_number}",
            )
    if set(weights) != set(people):
        raise ValueError("analysis weights IDs do not exactly cover the census population")
    return weights


def _experience(experience: dict, label: str) -> tuple[dict, dict[str, dict]]:
    source = experience.get("source")
    baskets = experience.get("experience_by_id")
    if not isinstance(source, dict) or not isinstance(baskets, dict) or not baskets:
        raise ValueError(f"{label} experience needs source and nonempty experience_by_id")
    if any(not isinstance(k, str) or not isinstance(v, dict) for k, v in baskets.items()):
        raise ValueError(f"invalid {label} basket map")
    return source, baskets


def _assert_source(source: dict, ce_path: Path, ce_data: bytes,
                   member: str | None, label: str) -> None:
    actual_file_hash = _sha(ce_path.read_bytes())
    if source.get("data_sha256") != actual_file_hash:
        raise ValueError(f"{label} CE file hash differs from the supplied CE data")
    if source.get("member_sha256") != _sha(ce_data):
        raise ValueError(f"{label} CE member hash differs from the supplied FMLI CSV")
    if source.get("member") != member:
        raise ValueError(f"{label} CE member does not match --member")
    if not source.get("interview_wave"):
        raise ValueError(f"{label} source lacks the declared CE interview wave")


def _basket_signature(shares: dict) -> tuple[float, ...]:
    return tuple(round(float(shares[k]), 10) for k in CATEGORIES)


def _share_summary(records: list[tuple[dict, float]]) -> dict:
    if not records:
        raise ValueError("cannot summarize an empty weighted group")
    total_weight = sum(weight for _, weight in records)
    if not math.isfinite(total_weight) or total_weight <= 0:
        raise ValueError("group weights must have positive finite mass")
    result = {
        "n": len(records),
        "weight_sum": total_weight,
        "weight_effective_n": total_weight**2 / sum(weight**2 for _, weight in records),
        "weighted": {},
    }
    for category in CATEGORIES:
        values = sorted((float(shares[category]), weight) for shares, weight in records)
        mean = sum(value * weight for value, weight in values) / total_weight
        zero_weight = sum(weight for value, weight in values if value <= ZERO_TOLERANCE)
        quantiles = {}
        for q in QUANTILES:
            threshold = q * total_weight
            cumulative = 0.0
            selected = values[-1][0]
            for value, weight in values:
                cumulative += weight
                if cumulative + 1e-15 >= threshold:
                    selected = value
                    break
            quantiles[f"p{int(q * 100):02d}"] = selected
        result["weighted"][category] = {
            "mean": mean,
            "quantiles": quantiles,
            "zero_share_weight_fraction": zero_weight / total_weight,
        }
    return result


def _weighted_quantile(records: list[tuple[float, float]], q: float) -> float:
    values = sorted(records)
    total = sum(weight for _, weight in values)
    threshold = q * total
    cumulative = 0.0
    for value, weight in values:
        cumulative += weight
        if cumulative + 1e-15 >= threshold:
            return value
    return values[-1][0]


def _concentration(mass_by_key: dict) -> dict:
    total = sum(mass_by_key.values())
    if total <= 0:
        raise ValueError("concentration summary needs positive mass")
    probabilities = [mass / total for mass in mass_by_key.values() if mass > 0]
    hhi = sum(probability**2 for probability in probabilities)
    entropy = -sum(p * math.log(p) for p in probabilities)
    return {
        "support_n": len(probabilities),
        "hhi": hhi,
        "effective_support_n": 1.0 / hhi,
        "exp_shannon_entropy_n": math.exp(entropy),
        "max_share": max(probabilities),
        "top_10_share": sum(sorted(probabilities, reverse=True)[:10]),
    }


def _validate_and_summarize_baskets(
    label: str,
    baskets: dict[str, dict],
    people: dict[str, dict],
    donors: list[dict],
    source: dict,
    min_pool: int,
    analysis_weights: dict[str, float] | None = None,
) -> tuple[dict[str, dict], dict]:
    ids = set(baskets)
    if not ids:
        raise ValueError(f"{label} experience has no basket IDs")
    missing = ids - set(people)
    if missing:
        raise ValueError(f"{label} experience contains IDs absent from full population")
    seeds = set()
    for basket in baskets.values():
        seed = basket.get("seed")
        if not isinstance(seed, int):
            raise ValueError(f"{label} baskets need an integer assignment seed")
        seeds.add(seed)
    if len(seeds) != 1:
        raise ValueError(f"{label} baskets do not share one assignment seed")
    assigner = BasketAssigner(donors, source, seed=next(iter(seeds)), min_pool=min_pool)

    donor_by_id = {d["donor_id"]: d for d in donors}
    weight_schemes = {
        "persona_equal": {agent_id: person["weight"] for agent_id, person in people.items()},
    }
    if analysis_weights is not None:
        weight_schemes["survey_weighted"] = analysis_weights
    pool_sizes = {name: [] for name in weight_schemes}
    pool_effective_sizes = {name: [] for name in weight_schemes}
    match_patterns = Counter()
    relaxed_counts = Counter()
    candidate_basket_signatures = set()
    used_candidate_donors = set()
    candidate_mass = {name: defaultdict(float) for name in weight_schemes}
    assigned_mass = {name: defaultdict(float) for name in weight_schemes}
    assigned_signature_mass = {name: defaultdict(float) for name in weight_schemes}
    assigned_records = {name: [] for name in weight_schemes}
    matched_fields_share = Counter()

    for agent_id in sorted(ids):
        person = people[agent_id]
        basket = baskets[agent_id]
        attrs = person["attributes"]
        if basket.get("agent_id") != agent_id:
            raise ValueError(f"{label} basket key/agent_id mismatch for {agent_id}")
        if basket.get("profile_sha256") != profile_hash(attrs):
            raise ValueError(f"{label} profile hash mismatch for {agent_id}")
        shares = basket.get("spending_shares")
        if not isinstance(shares, dict) or set(shares) != set(CATEGORIES):
            raise ValueError(f"{label} basket categories are invalid for {agent_id}")
        try:
            vals = [float(shares[k]) for k in CATEGORIES]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} basket shares are invalid for {agent_id}") from exc
        if any(not math.isfinite(v) or v < 0 for v in vals) or abs(sum(vals) - 1.0) > 1e-8:
            raise ValueError(f"{label} basket shares do not sum to one for {agent_id}")
        if basket.get("source") != source:
            raise ValueError(f"{label} basket donor source mismatch for {agent_id}")

        expected = assigner.assign(agent_id, attrs)
        if basket != expected:
            raise ValueError(f"{label} donor, matched pool, fallback or assignment mismatch for {agent_id}")
        pool = [d for d in donors if all(d["attributes"].get(k) == attrs[k]
                                         for k in expected["matched_fields"])]
        if len(pool) != expected["pool_n"]:
            raise ValueError(f"{label} candidate pool size mismatch for {agent_id}")
        pool_weight = sum(d["sampling_weight"] for d in pool)
        for name, weights in weight_schemes.items():
            profile_weight = weights[agent_id]
            pool_sizes[name].append((float(len(pool)), profile_weight))
            pool_effective_sizes[name].append((float(expected["pool_effective_n"]), profile_weight))
        pattern = "|".join(expected["matched_fields"]) or "global"
        match_patterns[pattern] += 1
        if expected["relaxed_fields"]:
            relaxed_counts["people_with_relaxation"] += 1
            for field in expected["relaxed_fields"]:
                relaxed_counts[field] += 1
        for field in expected["matched_fields"]:
            matched_fields_share[field] += 1

        for donor in pool:
            probability = donor["sampling_weight"] / pool_weight
            for name, weights in weight_schemes.items():
                candidate_mass[name][donor["donor_id"]] += weights[agent_id] * probability
            candidate_basket_signatures.add(_basket_signature(donor["spending_shares"]))
            used_candidate_donors.add(donor["donor_id"])

        donor_id = basket["donor_id"]
        if donor_id not in donor_by_id:
            raise ValueError(f"{label} assigned donor is absent from eligible CE records")
        for name, weights in weight_schemes.items():
            weight = weights[agent_id]
            assigned_mass[name][donor_id] += weight
            assigned_signature_mass[name][_basket_signature(shares)] += weight
            assigned_records[name].append((shares, weight))

    weighted_audits = {}
    for name, weights in weight_schemes.items():
        total_person_weight = sum(weights[agent_id] for agent_id in ids)
        pool_n = pool_sizes[name]
        pool_ess = pool_effective_sizes[name]
        pool_quantiles = {
            "pool_n": {f"p{int(q * 100):02d}": _weighted_quantile(pool_n, q) for q in QUANTILES},
            "pool_effective_n": {f"p{int(q * 100):02d}": _weighted_quantile(pool_ess, q) for q in QUANTILES},
        }
        pool_quantiles["pool_n"].update(
            min=min(value for value, _ in pool_n), max=max(value for value, _ in pool_n),
            weighted_mean=sum(v * w for v, w in pool_n) / total_person_weight,
        )
        pool_quantiles["pool_effective_n"].update(
            min=min(value for value, _ in pool_ess), max=max(value for value, _ in pool_ess),
            weighted_mean=sum(v * w for v, w in pool_ess) / total_person_weight,
        )
        candidate_records = [(donor_by_id[donor_id]["spending_shares"], mass)
                             for donor_id, mass in candidate_mass[name].items()]
        weighted_audits[name] = {
            "weight_source": ("persona.weight (neutral 1.0)" if name == "persona_equal"
                              else "analysis_weights.jsonl analysis_weight"),
            "weight_sum": total_person_weight,
            "matched_candidate_pools": pool_quantiles,
            "candidate_pool_vs_synthetic_diversity": {
                "candidate_donors_in_any_matched_pool": len(used_candidate_donors),
                "candidate_basket_signatures_in_any_matched_pool": len(candidate_basket_signatures),
                "expected_candidate_mix": _share_summary(candidate_records),
                "assigned_unique_donors": len(assigned_mass[name]),
                "assigned_basket_signatures": len(assigned_signature_mass[name]),
                "matched_candidate_expected_mix_concentration": _concentration(dict(candidate_mass[name])),
                "assigned_synthetic_baskets_concentration": _concentration(dict(assigned_mass[name])),
            },
            "assigned_basket_summary": _share_summary(assigned_records[name]),
        }
    audit = {
        "n": len(ids),
        "matched_fields_person_counts": dict(sorted(match_patterns.items())),
        "matched_field_person_counts": dict(sorted(matched_fields_share.items())),
        "relaxation_person_counts": dict(sorted(relaxed_counts.items())),
        "weighting": weighted_audits,
    }
    return {u: baskets[u] for u in ids}, audit


def _group_summaries(donors: list[dict], people: dict[str, dict], baskets: dict[str, dict],
                     analysis_weights: dict[str, float] | None = None) -> dict:
    result = {}
    ce_total = sum(d["sampling_weight"] for d in donors)
    weight_schemes = {
        "persona_equal": {agent_id: person["weight"] for agent_id, person in people.items()},
    }
    if analysis_weights is not None:
        weight_schemes["survey_weighted"] = analysis_weights
    person_totals = {name: sum(weights.values()) for name, weights in weight_schemes.items()}
    for field in COMMON_GROUPS:
        ce_values = {d["attributes"][field] for d in donors if field in d["attributes"]}
        sce_values = {p["attributes"][field] for p in people.values() if field in p["attributes"]}
        groups = {}
        for value in sorted(ce_values & sce_values):
            ce_rows = [(d["spending_shares"], d["sampling_weight"])
                       for d in donors if d["attributes"].get(field) == value]
            matching_people = [agent_id for agent_id, person in people.items()
                               if agent_id in baskets and person["attributes"].get(field) == value]
            if not ce_rows or not matching_people:
                continue
            ce_mass = sum(weight for _, weight in ce_rows)
            groups[value] = {
                "ce_donor_n": len(ce_rows),
                "ce_sampling_weight_share": ce_mass / ce_total,
                "ce_weighted_baskets": _share_summary(ce_rows),
                "sce_person_n": len(matching_people),
                "synthetic_weighting": {},
            }
            for name, weights in weight_schemes.items():
                sce_rows = [(baskets[agent_id]["spending_shares"], weights[agent_id])
                            for agent_id in matching_people]
                sce_mass = sum(weight for _, weight in sce_rows)
                groups[value]["synthetic_weighting"][name] = {
                    "weight_share": sce_mass / person_totals[name],
                    "weighted_assigned_baskets": _share_summary(sce_rows),
                }
        result[field] = groups
    return result


def _month_key(value):
    if value is None:
        return None
    text = str(value).strip()
    if len(text) == 7 and text[4] == "-":
        return text.replace("-", "")
    if len(text) == 6 and text.isdigit():
        return text
    return text


def audit(args) -> dict:
    ce_path = Path(args.ce_data).resolve()
    full_path = Path(args.full_experience).resolve()
    core_path = Path(args.core_experience).resolve()
    pop_path = Path(args.population).resolve()
    out_path = Path(args.output).resolve()
    if out_path.exists():
        raise ValueError(f"output directory already exists: {out_path}")
    rows, ce_member_data, member = _load_ce(ce_path, args.member)
    donors, donor_audit = prepare_ce_donors(rows)
    if len(donors) != donor_audit["eligible_n"]:
        raise ValueError("CE eligible donor count is inconsistent")

    population = _read_json(pop_path)
    people = _population(population)
    full_exp, core_exp = _read_json(full_path), _read_json(core_path)
    full_source, full_baskets = _experience(full_exp, "full")
    core_source, core_baskets = _experience(core_exp, "Core")
    for source, label in [(full_source, "full"), (core_source, "Core")]:
        _assert_source(source, ce_path, ce_member_data, member, label)
    if full_source.get("interview_wave") != core_source.get("interview_wave"):
        raise ValueError("full and Core experiences use different CE interview waves")

    provider_args = population.get("provider_args") or {}
    population_month = provider_args.get("target_month")
    experience_month = full_exp.get("target_month")
    if (population_month is not None and experience_month is not None
            and _month_key(population_month) != _month_key(experience_month)):
        raise ValueError("full population and experience target months differ")
    expected_month = _month_key(population_month if population_month is not None else experience_month)
    analysis_weights_path = getattr(args, "analysis_weights", None)
    analysis_weights = None
    if analysis_weights_path:
        if expected_month is None:
            raise ValueError("cannot validate analysis weights without a population/experience month")
        analysis_weights_path = Path(analysis_weights_path).resolve()
        analysis_weights = _read_analysis_weights(analysis_weights_path, people, expected_month)

    if set(full_baskets) != set(people):
        raise ValueError("full experience IDs must exactly cover the census population")
    if not set(core_baskets).issubset(people):
        raise ValueError("Core experience includes IDs absent from full population")
    if not set(core_baskets).issubset(full_baskets):
        raise ValueError("Core experience IDs must be a subset of the full experience")

    full_checked, full_audit = _validate_and_summarize_baskets(
        "full", full_baskets, people, donors, full_source, args.min_pool, analysis_weights,
    )
    core_checked, core_audit = _validate_and_summarize_baskets(
        "Core", core_baskets, people, donors, core_source, args.min_pool, analysis_weights,
    )
    mismatches = [agent_id for agent_id in core_checked
                  if full_checked[agent_id] != core_checked[agent_id]]
    if mismatches:
        raise ValueError(f"Core baskets differ from full experience for {len(mismatches)} shared IDs")

    ce_records = [(d["spending_shares"], d["sampling_weight"]) for d in donors]
    ce_weight_sum = sum(d["sampling_weight"] for d in donors)
    ce_overall = _share_summary(ce_records)
    ce_overall["sampling_weight_sum"] = ce_weight_sum
    primary_synthetic_scheme = "survey_weighted" if analysis_weights is not None else "persona_equal"
    synthetic_weighting = full_audit["weighting"]
    synthetic_summary = {
        "primary_weighting": primary_synthetic_scheme,
        "primary_basket_summary": synthetic_weighting[primary_synthetic_scheme]["assigned_basket_summary"],
        "persona_equal": synthetic_weighting["persona_equal"]["assigned_basket_summary"],
        "survey_weighted": (synthetic_weighting["survey_weighted"]["assigned_basket_summary"]
                            if "survey_weighted" in synthetic_weighting else None),
    }
    result = {
        "status": "passed",
        "audit": "full_population_ce_basket_assignment",
        "target_month": experience_month,
        "ce_source": {
            "interview_wave": full_source["interview_wave"],
            "data_sha256": full_source["data_sha256"],
            "member_sha256": full_source["member_sha256"],
            "member": member,
            "eligible_n": donor_audit["eligible_n"],
            "excluded_n": donor_audit["excluded_n"],
            "exclusion_reasons": donor_audit["exclusion_reasons"],
            "weighted_overall_baskets": ce_overall,
        },
        "full_population": full_audit,
        "synthetic_population": synthetic_summary,
        "core_overlap": {
            "core_experience_n": len(core_checked),
            "core_ids_in_full_population_n": len(set(core_checked) & set(people)),
            "identical_baskets_n": len(core_checked) - len(mismatches),
            "identical_baskets": True,
            "basket_assignment_audit": core_audit,
        },
        "common_broad_groups": _group_summaries(donors, people, full_checked, analysis_weights),
        "input_sha256": {
            "ce_data": _sha(ce_path.read_bytes()),
            "full_experience": _sha(full_path.read_bytes()),
            "core_experience": _sha(core_path.read_bytes()),
            "population": _sha(pop_path.read_bytes()),
            "analysis_weights": (_sha(analysis_weights_path.read_bytes())
                                 if analysis_weights_path else None),
        },
        "method": {
            "ce_weight": "CE FINLWT21 sampling weight",
            "persona_weight": "PopulationBundle persona.weight is required to equal neutral 1.0; reported as persona_equal",
            "survey_weight": ("analysis_weights.jsonl analysis_weight; strict census ID coverage, matching target_month, and positive finite values"
                              if analysis_weights is not None else "not supplied; survey-weighted summaries unavailable"),
            "assignment_weight_isolation": "analysis weights are used only for post hoc summaries; basket matching and donor draws use profiles, CE FINLWT21 and the stored seed",
            "weighted_quantiles": "left-continuous inverse CDF at p10, p25, p50, p75 and p90",
            "zero_share": f"weighted fraction with category share <= {ZERO_TOLERANCE:g}",
            "candidate_pool": "for each SCE profile, CE donors matching the recorded fields after declared fallback; conditional CE weights are averaged over personas using each reported weighting scheme",
            "concentration": "HHI, inverse-HHI effective support, exponentiated Shannon entropy, max donor share and top-10 donor share",
            "group_dimensions": list(COMMON_GROUPS),
            "cross_month": "not compared; only the supplied population month is audited",
            "truth_access": "no real SCE Q8/Q9 outcome fields were read",
            "interpretation": "CE donor overall and SCE-profile synthetic overall describe different populations; equality is not expected",
        },
    }
    out_path.mkdir(parents=True, exist_ok=False)
    (out_path / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )
    report = [
        "# SCE CE basket population audit",
        "",
        f"- Status: **{result['status']}**",
        f"- Target month: {experience_month or 'not supplied'}; SCE personas: {full_audit['n']:,}",
        f"- CE wave: {full_source['interview_wave']}; eligible interviews: {donor_audit['eligible_n']:,}",
        f"- Core overlap: {len(core_checked):,}; identical baskets: {result['core_overlap']['identical_baskets_n']:,}",
        f"- Fallback used: {full_audit['relaxation_person_counts'].get('people_with_relaxation', 0):,} personas",
        f"- Primary synthetic weighting: {primary_synthetic_scheme}; food share mean: "
        f"{synthetic_summary['primary_basket_summary']['weighted']['food']['mean']:.4f}",
        f"- Assigned donors under primary weighting: "
        f"{synthetic_weighting[primary_synthetic_scheme]['candidate_pool_vs_synthetic_diversity']['assigned_unique_donors']:,}; "
        f"effective donor support: "
        f"{synthetic_weighting[primary_synthetic_scheme]['candidate_pool_vs_synthetic_diversity']['assigned_synthetic_baskets_concentration']['effective_support_n']:.1f}",
        "",
        "CE summaries use CE interview weights. PopulationBundle persona.weight is neutral 1.0; equal-person and "
        "survey-weighted synthetic summaries are reported separately. Survey weights are post hoc only and do not "
        "affect basket matching or donor assignment. "
        "The two overall populations differ, so their basket summaries are not expected to match.",
        "",
        "See `summary.json` for category means, weighted quantiles, zero-share rates, shared broad groups, "
        "matched candidate-pool diversity, and donor concentration.",
    ]
    (out_path / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ce-data", required=True, help="one official CE FMLI CSV or ZIP")
    parser.add_argument("--member", help="explicit FMLI CSV member when --ce-data is ZIP")
    parser.add_argument("--full-experience", required=True, help="full population experience.json")
    parser.add_argument("--core-experience", required=True, help="existing Core experience.json")
    parser.add_argument("--population", required=True, help="complete census population.json")
    parser.add_argument("--analysis-weights", help="optional census analysis_weights.jsonl for post hoc survey-weighted summaries")
    parser.add_argument("--output", required=True, help="new, non-existing audit output directory")
    parser.add_argument("--min-pool", type=int, default=25,
                        help="minimum CE candidate pool used by the basket assignment (default: 25)")
    args = parser.parse_args(argv)
    if args.min_pool < 1:
        parser.error("--min-pool must be positive")
    result = audit(args)
    print(json.dumps({"status": result["status"], "target_month": result["target_month"],
                       "population_n": result["full_population"]["n"],
                       "ce_eligible_n": result["ce_source"]["eligible_n"],
                       "core_identical_n": result["core_overlap"]["identical_baskets_n"],
                       "output": str(Path(args.output).resolve())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
