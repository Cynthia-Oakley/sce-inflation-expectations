"""One preregistered comparison; imports frozen algorithms without modifying them.

Run with the existing socioverse environment. No network/LLM. Private row-level
results go to a new ignored output directory. Never use Agent forecast outcomes.
"""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import sys
import time
import uuid

import numpy as np
import scipy
from scipy.special import betainc
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import diagnose_sce_beta as diagnostic

score_q9 = diagnostic.score_q9
weighted_quantile = diagnostic.weighted_empirical_quantile
MONTHS = (202004, 202110, 202212)
PLAN = ROOT / "docs/SCORER_HOLDOUT_PLAN_20261003.md"
SOURCE = diagnostic.SOURCE
CHART = SOURCE.with_name("chart.xlsx")
SCORER = ROOT / "studies/sce_inflation_expectations/scoring/sce_q9.py"
EXPECTED = {
    SCORER: "24bccc6581201003840b1c2c7d21cf4f0749ec937c47075e24b398fb03489c09",
    Path(diagnostic.__file__): "b45a29345f432288fe3b0b18e8c39066998bf19a803a0e7c661dc2a193987e57",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def valid_bins(bins):
    return (len(bins) == 10 and all(finite(v) and 0 <= v <= 100 for v in bins)
            and abs(sum(bins) - 100) <= 1e-6)


def score_pair(bins):
    """Workers receive probabilities only, never official labels or metadata."""
    try:
        base = asdict(score_q9(bins))
    except Exception as exc:
        base = {"status": "exception", "error": repr(exc)}
    candidate = dict(base)
    if valid_bins(bins) and sum(v > 0 for v in bins) >= 3:
        try:
            fit = diagnostic.fit(bins, "relaxed_tail_skip_zero", tail_start=20.)
            a, b, left, right = fit["params"]
            cdf = lambda x: float(betainc(a, b, np.clip((x-left)/(right-left), 0, 1)))
            candidate = {
                "status": "ok", "family": "generalized_beta", "mean": fit["mean"],
                "p25": fit["quartiles"][0], "p50": fit["quartiles"][1],
                "p75": fit["quartiles"][2], "iqr": fit["iqr"],
                "prob_deflation": cdf(0.), "fit_loss": fit["loss"], "diagnostics": fit,
                "quantile_cdf_max_residual": max(abs(cdf(x)-q) for x, q in
                                                 zip(fit["quartiles"], (.25, .5, .75))),
                "support_shrunk_inside_open_bin": bool((bins[0] > 0 and right < 12)
                                                       or (bins[9] > 0 and left > -12)),
                "support_invariant_ok": bool(-38 <= left < right <= 38
                                             and left <= fit["mean"] <= right),
            }
        except Exception as exc:
            candidate = {"status": "exception", "error": repr(exc)}
    return {"original": base, "candidate": candidate}


def stats(errors):
    if not errors:
        return None
    e = np.asarray(errors)
    return {"n": len(e), "mae": float(e.mean()), "median_abs": float(np.median(e)),
            "p95_abs": float(np.quantile(e, .95)), "max_abs": float(e.max()),
            "within_0_001": int((e <= .001).sum()),
            "within_0_001_fraction": float((e <= .001).mean())}


def errors(records, field, official):
    rows = [r for r in records if finite(r[official]) and all(
        r["fits"][v].get("status") == "ok" and finite(r["fits"][v].get(field))
        for v in ("original", "candidate"))]
    return {v: stats([abs(r["fits"][v][field]-r[official]) for r in rows])
            for v in ("original", "candidate")}


def summarize(records):
    beta = [r for r in records if r["family_input"] == "beta"]
    return {
        "n_rows": len(records),
        "status": {v: dict(Counter(r["fits"][v]["status"] for r in records))
                   for v in ("original", "candidate")},
        "input_families": dict(Counter(r["family_input"] for r in records)),
        "beta_mean": errors(beta, "mean", "Q9_mean"),
        "all_mean": errors(records, "mean", "Q9_mean"),
        "beta_iqr": errors(beta, "iqr", "Q9_iqr"),
        "beta_quantiles": {f: errors(beta, f, official) for f, official in
                           (("p25", "Q9_cent25"), ("p50", "Q9_cent50"), ("p75", "Q9_cent75"))},
        "by_stratum": {s: errors([r for r in beta if r["stratum"] == s], "mean", "Q9_mean")
                       for s in sorted({r["stratum"] for r in beta})},
        "new_probability_vectors_beta": errors([r for r in beta if not r["seen_vector"]], "mean", "Q9_mean"),
        "candidate_diagnostics": {
            "solver_not_success": sum(not r["fits"]["candidate"]["diagnostics"]["success"]
                                      for r in beta if "diagnostics" in r["fits"]["candidate"]),
            "rank_deficient": sum(r["fits"]["candidate"]["diagnostics"]["rank"] <
                                  r["fits"]["candidate"]["diagnostics"]["n_parameters"]
                                  for r in beta if "diagnostics" in r["fits"]["candidate"]),
            "shrunk_open_support": sum(r["fits"]["candidate"].get("support_shrunk_inside_open_bin", False) for r in beta),
            "max_quantile_cdf_residual": max([r["fits"]["candidate"].get("quantile_cdf_max_residual", 0.) for r in beta], default=0.),
        },
    }


def aggregate(records, chart):
    def entry(rows, field):
        if not rows:
            return {"n": 0, "median": None}
        return {"n": len(rows), "median": weighted_quantile([field(r) for r in rows], [r["weight"] for r in rows])}
    positive_weight = [r for r in records if finite(r["weight"]) and r["weight"] > 0]
    official = [r for r in positive_weight if finite(r["Q9_mean"])]
    common = [r for r in official if all(r["fits"][v]["status"] == "ok" and finite(r["fits"][v].get("mean")) for v in ("original", "candidate"))]
    result = {"official_chart": chart, "official_all": entry(official, lambda r:r["Q9_mean"]),
              "official_common": entry(common, lambda r:r["Q9_mean"])}
    for v in ("original", "candidate"):
        own = [r for r in positive_weight if r["fits"][v]["status"] == "ok" and finite(r["fits"][v].get("mean"))]
        result[v+"_own"] = entry(own, lambda r:r["fits"][v]["mean"])
        result[v+"_common"] = entry(common, lambda r:r["fits"][v]["mean"])
        result[v+"_common_abs_error"] = abs(result[v+"_common"]["median"]-result["official_common"]["median"])
        result[v+"_own_minus_chart"] = result[v+"_own"]["median"]-chart if finite(chart) else None
    result["official_common_minus_all"] = result["official_common"]["median"]-result["official_all"]["median"]
    return result


def main():
    for path, expected in EXPECTED.items():
        assert digest(path) == expected, f"Algorithm changed: {path}"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:8]
    out = ROOT / "outputs" / ("scorer_holdout_"+run_id)
    out.mkdir(parents=True, exist_ok=False)
    (out / "plan.md").write_bytes(PLAN.read_bytes())
    metadata = {"run_id": run_id, "months": MONTHS, "started_at": datetime.now(timezone.utc).isoformat(),
                "source_sha256": digest(SOURCE), "chart_sha256": digest(CHART), "plan_sha256": digest(PLAN),
                "algorithm_sha256": {str(p.relative_to(ROOT)): h for p,h in EXPECTED.items()},
                "runner_sha256": digest(Path(__file__)), "python": platform.python_version(),
                "numpy": np.__version__, "scipy": scipy.__version__}
    (out / "manifest.json").write_text(json.dumps(metadata, indent=2)+"\n")
    old = json.loads((diagnostic.OUT / "selected_micro.json").read_text())
    assert old["source_sha256"] == metadata["source_sha256"]
    assert {r["date"] for r in old["rows"]} == {202001,202206}
    seen = {tuple(r[f"Q9_bin{i}"] for i in range(1,11)) for r in old["rows"]}
    book = load_workbook(SOURCE, read_only=True, data_only=True)
    rows = book["Data"].iter_rows(values_only=True)
    next(rows); header = next(rows)
    fields = ["date", "weight", "Q9_mean", "Q9_iqr", "Q9_cent25", "Q9_cent50", "Q9_cent75"] + [f"Q9_bin{i}" for i in range(1,11)]
    indices = {f:header.index(f) for f in fields}
    selected = []
    for n,row in enumerate(rows,3):
        if row[indices["date"]] in MONTHS:
            selected.append({"excel_row":n, **{f:row[i] for f,i in indices.items()}})
        if n % 15000 == 0: print("Read source rows",n,flush=True)
    book.close()
    unique_bins = list(dict.fromkeys(tuple(r[f"Q9_bin{i}"] for i in range(1,11)) for r in selected))
    print("Selected",len(selected),"rows; unique probability vectors",len(unique_bins),"output",out,flush=True)
    fitted = {}
    start = time.monotonic()
    with ProcessPoolExecutor(max_workers=3) as pool:
        for i,(bins,pair) in enumerate(zip(unique_bins,pool.map(score_pair,unique_bins,chunksize=4)),1):
            fitted[bins] = pair
            if i % 100 == 0: print("Fitted",i,"/",len(unique_bins),"elapsed_s",round(time.monotonic()-start),flush=True)
    records=[]
    for r in selected:
        bins=tuple(r[f"Q9_bin{i}"] for i in range(1,11));positive=[i for i,v in enumerate(bins) if finite(v) and v>0]
        family="invalid" if not valid_bins(bins) else "uniform" if len(positive)==1 else "two_bins" if len(positive)==2 else "beta"
        stratum=("open" if positive and (positive[0]==0 or positive[-1]==9) else "closed") + ("_contiguous" if positive and len(positive)==positive[-1]-positive[0]+1 else "_gapped")
        records.append({**r,"family_input":family,"stratum":stratum,"seen_vector":bins in seen,"fits":fitted[bins]})
    with (out / "records.jsonl").open("w") as f:
        for r in records:f.write(json.dumps(r,ensure_ascii=False,allow_nan=False)+"\n")
    chartbook=load_workbook(CHART,read_only=True,data_only=True)
    chart={int(r[0]):r[1] for r in chartbook["Inflation expectations"].iter_rows(min_row=5,values_only=True) if r[0] in MONTHS}
    chartbook.close()
    report={"manifest":metadata,"all":summarize(records),"months":{},"monthly_aggregation":{}}
    for m in MONTHS:
        mr=[r for r in records if r["date"]==m]
        report["months"][str(m)]=summarize(mr)
        report["monthly_aggregation"][str(m)]=aggregate(mr,chart.get(m))
    invalid_output=[];extra_failures=[]
    for r in records:
        o,c=r["fits"]["original"],r["fits"]["candidate"]
        if o["status"]=="ok" and c["status"]!="ok":extra_failures.append(r["excel_row"])
        if c["status"]=="ok" and (not all(finite(c.get(k)) for k in ("mean","p25","p50","p75","iqr")) or not c["p25"]<=c["p50"]<=c["p75"] or not c.get("support_invariant_ok",True)):invalid_output.append(r["excel_row"])
    unchanged=all(r["fits"]["original"]==r["fits"]["candidate"] for r in records if r["family_input"]!="beta")
    a=report["all"];o,c=a["beta_mean"]["original"],a["beta_mean"]["candidate"]
    new=a["new_probability_vectors_beta"]
    gates={
        "coverage_and_output_invariants":not extra_failures and not invalid_output and unchanged,
        "pooled_beta_mae_lower":c["mae"]<o["mae"],
        "pooled_beta_p95_lower":c["p95_abs"]<o["p95_abs"],
        "pooled_match_fraction_not_lower":c["within_0_001_fraction"]>=o["within_0_001_fraction"],
        "per_month_mae_no_more_than_10pct_worse":all(d["beta_mean"]["candidate"]["mae"]<=1.1*d["beta_mean"]["original"]["mae"]+1e-12 for d in report["months"].values()),
        "pooled_iqr_mae_no_more_than_10pct_worse":a["beta_iqr"]["candidate"]["mae"]<=1.1*a["beta_iqr"]["original"]["mae"]+1e-12,
        "monthly_median_deterioration_at_most_0_05pp":all(d["candidate_common_abs_error"]<=d["original_common_abs_error"]+.05 for d in report["monthly_aggregation"].values()),
        "new_vectors_not_both_worse": bool(new["original"] and new["candidate"]) and not(new["candidate"]["mae"]>new["original"]["mae"] and new["candidate"]["p95_abs"]>new["original"]["p95_abs"]),
    }
    report["selection"]={"gates":gates,"recommend_candidate":all(gates.values()),"additional_failure_rows":extra_failures,"invalid_candidate_rows":invalid_output,"unchanged_nonbeta":unchanged}
    for p,h in EXPECTED.items():assert digest(p)==h
    report["finished_at"]=datetime.now(timezone.utc).isoformat()
    (out/"summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(json.dumps({"output":str(out),"all_beta_mean":a["beta_mean"],"selection":report["selection"]},indent=2),flush=True)


if __name__ == "__main__":
    main()
