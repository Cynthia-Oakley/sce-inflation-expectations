"""Offline questionnaire-to-metric reproduction from the v06 review data.

Raw API replies, effective states, human evaluation targets, and Normal draws
are distinct files. Never instantiate an LLM or choose answers using targets.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

from ..q9_normalization import response_point, response_view
from ..evaluation.metrics import compare_distributions, distribution_summary, headline_errors
from ..core_normal_joint import JointAnswer, PointAnswer, JointExpansion


def read(path):
    return json.loads(Path(path).read_text())


def load_rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def close(actual, expected, *, label="metric", tolerance=2e-8):
    if actual is None or expected is None:
        if actual is not expected:
            raise ValueError(label + ": null support changed")
    elif type(expected) in (int, float):
        if type(actual) not in (int, float) or not math.isclose(actual, expected, abs_tol=tolerance, rel_tol=1e-10):
            raise ValueError(f"{label}: {actual} != {expected}")
    elif isinstance(expected, dict):
        for key, value in expected.items():
            if key not in actual:
                raise ValueError(label + ": missing " + key)
            close(actual[key], value, label=label + "." + key, tolerance=tolerance)
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(label + ": array support changed")
        for i, (a, e) in enumerate(zip(actual, expected)):
            close(a, e, label=f"{label}[{i}]", tolerance=tolerance)
    elif actual != expected:
        raise ValueError(label + ": metadata changed")


def audit_response(record):
    text = record["response_text"]
    if hashlib.sha256(text.encode()).hexdigest() != record["delivered_response_sha256"]:
        raise ValueError("Delivered model reply hash mismatch")
    if not record["response_text_redacted"] and record["original_response_sha256"] != record["delivered_response_sha256"]:
        raise ValueError("Unredacted original response differs")
    if record["actual_model_results"] is not True:
        raise ValueError("Rule fixture cannot be passed off as a model output")
    point = response_point(text) if not record["error"] else None
    try:
        bins = response_view(text)["bins"] if not record["error"] else None
    except (ValueError, TypeError):
        bins = None
    return point, bins


def verify_answers(answers, responses):
    seen = set()
    previous = {}
    verified = normalized = retained = 0
    for a in answers:
        key = a["run"], a["period"], a["household"]
        if key in seen:
            raise ValueError("Duplicate effective logical answer")
        seen.add(key)
        if not math.isfinite(a["analysis_weight"]) or a["analysis_weight"] <= 0:
            raise ValueError("Invalid analysis weight")
        points = []
        for f in ("q8", "q9"):
            ref = a["selected_responses"][f]
            value = a["q8"] if f == "q8" else (a.get("selected_model_q9_bins")
                    if a.get("density_failure_retained_input") else a["q9_bins"])
            if ref:
                raw = responses[ref]
                if a["run"] != raw["run"] and not (a["run"] == "monthly" and a.get("root_reused") and raw["run"] == "B"):
                    raise ValueError("Response was taken from a different experiment")
                if raw["period"] != a["period"]:
                    raise ValueError("Response was taken from a different period")
                if raw["run"] == a["run"] and raw["household"] != a["household"]:
                    raise ValueError("Another household's response was substituted")
                if raw["run"]!=a["run"] and raw["household"]!=a.get("shared_B_root",{}).get("household"):
                    raise ValueError("Shared root must identify its exact B household")
                p, bins = audit_response(raw)
                if (p if f == "q8" else bins) is None:
                    raise ValueError("An unusable API field was selected")
                close(value, p if f == "q8" else bins, label="raw-to-effective." + f)
                points.append(raw["prompt_sha256"])
                if f == "q9":
                    normalized += response_view(raw["response_text"])["applied"]
                verified += 1
            else:
                retained += 1
                if a["run"] == "A" and f == "q9" and not a.get("fallback"):
                    raise ValueError("Undeclared missing-output fallback")
                prev = previous.get((a["run"], a["household"]))
                if a["run"] == "monthly" and not a.get("root_reused"):
                    if prev is None or prev["period"] != a["previous_period"]:
                        raise ValueError("Missing preceding monthly state")
                    close(value, prev["q8"] if f == "q8" else prev["q9_bins"], label="retained monthly field")
        if len(set(points)) > 1:
            raise ValueError("Q8/Q9 repairs used different prompts")
        previous[a["run"], a["household"]] = a
    return dict(effective_answers=len(seen), raw_fields_verified=verified,
                proportional_normalizations=normalized, retained_fields=retained)


def make_banks(payload, score, tau=8):
    if payload["run"] == "A_Normal":
        data = payload["inputs"]
        core = [r["id"] for r in data["selected"]]
        weights = {r["id"]:r["poststratified_weight"] for r in data["selected"]}
        records = data["answers"]
        frame = data["people"]
    else:
        frame, weights, records = payload["frame"], payload["core_weights"], payload["answers"]
        core = list(weights)
    joint, point = [], []
    for r in records:
        if r["q8"] is not None:
            point.append(PointAnswer(r["id"], r["q8"]))
        if r["q9_mean"] is not None:
            fitted = score(r["q9_bins"])
            close(fitted["mean"], r["q9_mean"], label="Normal donor density mean")
            close(fitted["iqr"], r["q9_iqr"], label="Normal donor density IQR")
            joint.append(JointAnswer(r["id"], tuple(r["q9_bins"]), fitted["mean"], fitted["iqr"], r["q8"]))
    return {name: JointExpansion(frame, core, rs, weights, prior_strength=tau)
            for name,rs in (("q9",joint),("q8",point))}


def replay(data, out, *, refit_density=False):
    data, out = Path(data).resolve(), Path(out).resolve()
    manifest = read(data / "manifest.json")
    for name, expected in manifest["files_sha256"].items():
        p = (data / name).resolve()
        if not p.is_relative_to(data) or digest(p) != expected:
            raise ValueError("Micro data hash mismatch: " + name)
    out.mkdir(parents=True, exist_ok=False)
    raw = load_rows(data / "model_outputs.jsonl.gz")
    responses = {r["response_id"]:r for r in raw}
    if len(responses) != len(raw):
        raise ValueError("Duplicate raw response identity")
    for r in raw:
        audit_response(r)
    answers = load_rows(data / "effective_answers.jsonl.gz")
    verification = verify_answers(answers, responses)
    print(f"Verified {len(raw):,} output records and {len(answers):,} effective states",flush=True)
    cases = load_rows(data / "A_paired_cases.jsonl.gz")
    expected = read(data / "expected.json")
    cache = {tuple(r["bins"]):r["score"] for r in load_rows(data / "density_cache.jsonl.gz")}
    normals = load_rows(data / "normal_mechanism.jsonl.gz")
    new_fits = 0
    if refit_density:
        from ..evaluation.cognition import _score_bins
        from concurrent.futures import ProcessPoolExecutor
        vectors = {tuple(a["q9_bins"]) for a in answers}
        for c in cases:
            vectors.add(tuple(c["real"]["q9_bins"]))
        for n in normals:
            records = n["inputs"]["answers"] if n["run"] == "A_Normal" else n["answers"]
            vectors.update(tuple(r["q9_bins"]) for r in records if r["q9_mean"] is not None)
        vectors = sorted(v for v in vectors if len(v) == 10 and all(type(x) in (int,float) for x in v))
        print("Refitting frozen numerical densities (not LLMs):", len(vectors), flush=True)
        with ProcessPoolExecutor(max_workers=6) as pool:
            for v, fitted in zip(vectors, pool.map(_score_bins, [list(v) for v in vectors], chunksize=16)):
                for k in ("mean", "iqr"):
                    close(fitted[k], cache[v][k], label="independent density refit", tolerance=1e-6)
                cache[v] = fitted
        new_fits = len(vectors)

    def score(bins):
        key = tuple(bins)
        if key not in cache:
            raise ValueError("Exact vector absent from density cache; no unannounced scorer change")
        return cache[key]

    grouped = defaultdict(list)
    for a in answers:
        fitted = score(a["q9_bins"])
        center = fitted["mean"]
        if center is None:
            center = a.get("fallback", {}).get("mean")
        if center is None and not (a["run"]=="A" and "fallback" in a):
            raise ValueError("Unscorable effective Q9 with no declared fallback")
        a["q9_mean"] = center
        a["q9_iqr"] = fitted["iqr"]
        grouped[a["run"], a["period"]].append(a)
    fullwave = defaultdict(list)
    for r in load_rows(data / "A_full_wave_targets.jsonl.gz"):
        fullwave[r["month"]].append(r)
    a_records = {(a["period"],a["household"]):a for a in answers if a["run"]=="A"}
    for c in cases:
        a = a_records[str(c["month"]),c["agent_id"]]
        arm = c["arms"]["monthly_reconstruction"]
        close(a["q9_mean"], arm["mean"], label="A individual density mean")
        close(a["q8"], arm["point"], label="A individual Q8")
        arm.update(mean=a["q9_mean"], point=a["q8"], q9_bins=a["q9_bins"])
        if not a.get("fallback"):
            close(a["q9_iqr"],arm["iqr"],label="A individual density IQR")
            arm["iqr"] = a["q9_iqr"]
        if len(c["real"]["q9_bins"])==10:
            fitted=score(c["real"]["q9_bins"])
            close(fitted["mean"],c["real"]["q9_mean"],label="paired human density")
    # Use the original shared same-support evaluator, not a new W1 convention.
    from ..evaluation.monthly_reconstruction import summarize
    months=sorted({c["month"] for c in cases})
    paired={}
    for key, arms in (("fixed_roster",["monthly_reconstruction","monthly_past_reference"]),
                      ("genuine_previous_only",["monthly_reconstruction","genuine_previous_only"])):
        actual=summarize(cases,months,arms,weight_definition=expected["A"]["weight_definition"])
        close(actual,expected["A"]["paired"][key],label=key)
        paired[key]=actual
    results=[]
    a_expected={str(r["month"]):r for r in expected["A"]["full_wave_monthly"]}
    for month in sorted(fullwave):
        model=grouped["A",month];truth=fullwave[month];fields={}
        for field,mk,tk in (("q9_mean","q9_mean","q9_mean"),("q8_point","q8","q8")):
            model_field=[a for a in model if a[mk] is not None and math.isfinite(a[mk])]
            truth_field=[r for r in truth if r[tk] is not None and math.isfinite(r[tk])
                         and r["weight"] is not None and math.isfinite(r["weight"]) and r["weight"]>0]
            fields[field]=compare_distributions([a[mk] for a in model_field],[a["analysis_weight"] for a in model_field],
                [r[tk] for r in truth_field],[r["weight"] for r in truth_field])
            close(fields[field],a_expected[month]["fields"][field],label="full-wave."+month+"."+field)
        results.append(dict(run="A",period=month,**fields))
    descriptive={}
    for run, rows, periodkey, centerkey, iqrkey, q8key in (
        ("B",expected["B"],"month","sim_pp","sim_cross_person_iqr_pp_descriptive_only","sim_q8_median_pp_descriptive_only"),
        ("monthly",expected["monthly"],"month","recursive_pp","simulated_cross_person_iqr_pp_descriptive","simulated_q8_median_pp_descriptive"),
        ("weekly",expected["weekly"],"step_key","sim_median_pp","sim_iqr_pp",None)):
        descriptive[run]=[]
        for ref in rows:
            period=str(ref[periodkey]);rs=grouped[run,period];w=[r["analysis_weight"] for r in rs]
            stats=distribution_summary([r["q9_mean"] for r in rs],w)
            close(stats["median_pp"],float(ref[centerkey]),label=run+" median "+period)
            close(stats["iqr_pp"],float(ref[iqrkey]),label=run+" IQR "+period)
            q8=distribution_summary([r["q8"] for r in rs],w)
            if q8key:close(q8["median_pp"],float(ref[q8key]),label=run+" Q8 "+period)
            descriptive[run].append(dict(period=period,q9=stats,q8=q8))
    normal_results=[]
    an={r["month"]:r for r in expected["A_Normal"]};bn={r["month"]:r for r in expected["B_Normal"]["monthly"]}
    for n in normals:
        banks=make_banks(n,score);fields={};month=n["period"]
        for f,bank in banks.items():
            mass=bank.atom_weights().tolist();atom=n["expected_atoms"]
            recorded=({r["id"]:w for r,w in zip(atom[f+"_atoms"],atom["by_tau"]["8"][f+"_mass"])}
                if n["run"]=="A_Normal" else {r["donor_id"]:r["weight"] for r in atom["atoms"]})
            # B expands joint Q8/Q9 together; its separate point bank is not used.
            if n["run"]=="B_Normal" and f=="q8":continue
            for a,w in zip(bank.answers,mass):close(w,recorded[str(a.id)],label="posterior mass")
            values=[a.q9_mean if f=="q9" else a.q8 for a in bank.answers]
            fields[f]=distribution_summary(values,mass)
            if n["run"]=="A_Normal":
                field="q9_mean" if f=="q9" else "q8_point"
                target=an[month]["fields"][field]["expanded_by_tau"]["8"]
                observed=fullwave[month];tk="q9_mean" if f=="q9" else "q8"
                actual=compare_distributions(values,mass,[r[tk] for r in observed],[r["weight"] for r in observed])
                close(actual["w1_pp"],target["w1_pp"],label="Normal W1")
                close(actual["simulated"]["median_pp"],target["simulated"]["median_pp"],label="Normal median")
                close(actual["simulated"]["iqr_pp"],target["simulated"]["iqr_pp"],label="Normal IQR")
                fields[f]["w1_pp"]=actual["w1_pp"]
            else:
                close(fields[f]["median_pp"],bn[month]["expanded_pp"],label="B Normal center")
                close(fields[f]["iqr_pp"],bn[month]["expanded_iqr_descriptive_pp"],label="B Normal IQR")
        normal_results.append(dict(run=n["run"],period=month,fields=fields))
    population=load_rows(data/"normal_population_rows.jsonl.gz")
    population_counts=Counter(r["run"] for r in population)
    if sum(population_counts.values())!=manifest["Normal_population_rows"]:
        raise ValueError("Normal inspection population row count differs")
    groups=[]
    for dim in ("age_group","education_group","numeracy","household_income_band","region","survey_entry_status","grid54"):
        subset=defaultdict(list)
        for c in cases:
            label=("|".join(str(c["profile"].get(k) or "unknown") for k in
                    ("education_group","numeracy","age_group","household_income_band"))
                   if dim=="grid54" else str(c.get(dim,c["profile"].get(dim))))
            subset[label].append(c)
        for value,cs in sorted(subset.items()):
            # Explicit support and month-by-month paired metrics, including small cells.
            bymonth=defaultdict(list)
            for c in cs:bymonth[c["month"]].append(c)
            for month,rs in sorted(bymonth.items()):
                valid=[r for r in rs if r["real"]["q9_mean"] is not None and r["arms"]["monthly_reconstruction"]["mean"] is not None]
                if not valid:continue
                v=[r["arms"]["monthly_reconstruction"]["mean"] for r in valid];w=[r["survey_weight"] for r in valid]
                d=compare_distributions(v,w,[r["real"]["q9_mean"] for r in valid],w)
                groups.append(dict(dimension=dim,level=value,month=month,n=len(valid),
                    supported=len(valid)>=20 and d["simulated"]["ess"]>=10,metrics=d))
    # National MAE is calculated from the reconstructed individual medians.
    a_nat=expected["A"]["official_national"]["monthly"]
    a_sim={r["period"]:r["q9_mean"]["simulated"]["median_pp"] for r in results}
    national={"A":headline_errors([a_sim[str(r["month"]).replace('-','')] for r in a_nat],[r["truth_pp"] for r in a_nat])}
    for run,refs,keep,key in (("B",expected["B"],lambda r:True,"month"),
                             ("monthly",expected["monthly"],lambda r:r["month"]!="202511","month"),
                             ("weekly",expected["weekly"],lambda r:r["main_score_point"]=="True","step_key")):
        targets={str(r[key]):float(r["target_release_value_pp"] if run=="weekly" else r["truth_pp"]) for r in refs if keep(r)}
        selected=[r for r in descriptive[run] if r["period"] in targets]
        national[run]=headline_errors([r["q9"]["median_pp"] for r in selected],[targets[r["period"]] for r in selected])
    for run in ("A_Normal","B_Normal"):
        rs=[r for r in normal_results if r["run"]==run]
        targets=({str(r["month"]).replace('-',''):r["truth_pp"] for r in a_nat}
                 if run=="A_Normal" else {r["month"]:r["truth_pp"] for r in expected["B_Normal"]["monthly"]})
        national[run]=headline_errors([r["fields"]["q9"]["median_pp"] for r in rs],[targets[r["period"]] for r in rs])
    # The paper uses the old/current common support (41,042), whereas the
    # retained-start comparison above requires valid starting-state scores.
    # Rebuild both supports rather than silently replacing one by the other.
    paper_check = None
    paper_path = data.parent / "paper_metric_crosswalk.json"
    if paper_path.exists():
        reference = read(paper_path)
        common = summarize(cases, months, ["monthly_reconstruction", "old_A82"],
                           weight_definition=expected["A"]["weight_definition"])
        weighted = common["arms"]["monthly_reconstruction"]["auxiliary_survey_weighted"]
        paper_check = dict(q9_person_months=common["q9_person_months"],
            q8_person_months=common["q8_person_months"],
            q9=weighted["q9"]["aggregate_equal_month_repeat_cells"],
            q8=weighted["q8"]["aggregate_equal_month_repeat_cells"])
        close(paper_check, reference["paper_paired_micro"], label="paper common-support metrics")
        comparison = []
        for row in csv.DictReader((data.parent / "paper_A82_comparison.csv").open()):
            month = row["month"].replace("-", "")
            close(a_sim[month], float(row["raw_pp"]), label="paper national center")
            raw_center, anchor = a_sim[month], float(row["anchor_pp"])
            for name, weight in reference["combination_weights"].items():
                value = (1-weight)*anchor + weight*raw_center
                close(value, float(row[name+"_pp"]), label="paper combination")
            comparison.append({k:(v if k=="month" else float(v)) for k,v in row.items()})
        for window, ref in reference["paper_national"].items():
            subset = [r for r in comparison if ref["first_month"] <= r["month"] <= ref["last_month"]]
            if len(subset) != ref["months"]:
                raise ValueError("Paper national comparison window changed")
            for name, metrics in ref["methods"].items():
                actual = headline_errors([r[name+"_pp"] for r in subset], [r["truth_pp"] for r in subset])
                close(actual, metrics, label="paper national "+window+" "+name)
        paper_check["national_windows_verified"] = list(reference["paper_national"])
    result=dict(status="passed_answer_level_reproduction",actual_LLM_calls=0,
        verification=verification,raw_model_output_records=len(raw),national=national,
        A_full_wave_monthly=results,paired=paired,descriptive_only=descriptive,
        normal=normal_results,normal_population_counts=dict(population_counts),
        paper_metric_verification=paper_check,
        scoring_mode="fresh_frozen_density_refit" if refit_density else "exact_vector_frozen_density_cache",
        new_numerical_density_fits=new_fits,parameter_refit=False,
        limits=["No recent human microdata: B/monthly/weekly dispersion is descriptive, not micro accuracy.",
                "Full-wave targets provide frozen public scalar scores/weights, not all original human ten-bin vectors.",
                "Normal inspection draws are distinct from the exact posterior atom CDF used for primary metrics.",
                "These are four final runs, not every exploratory pilot or all project invoices.",
                "Offline replay does not regenerate LLM answers or reconstruct unavailable historical news vintages."])
    (out/"summary.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    (out/"conditional_metrics.json").write_text(json.dumps(groups,ensure_ascii=False,indent=2,allow_nan=False))
    return result
