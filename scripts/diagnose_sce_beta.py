"""Independent diagnostic experiments; NEVER imported by the production scorer.

Run from the research repository with the socioverse Python environment.
Uses two previously inspected measurement-audit months, not Agent test outcomes.
Official derived fields are read only AFTER fitting, to measure discrepancies.
Outputs contain evaluation microdata and remain in gitignored outputs/.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import least_squares, brentq
from scipy.special import betainc

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/beta_diagnosis_20261001"
SOURCE = ROOT / "data/raw/sce_audit_20260928/micro_2020_2024.xlsx"
sys.path.insert(0, str(ROOT / "studies/sce_inflation_expectations/scoring"))
from sce_q9 import score_q9, weighted_empirical_quantile  # noqa: E402

EDGES = np.array([-np.inf, -12, -8, -4, -2, 0, 2, 4, 8, 12, np.inf])


def load_rows():
    cache = OUT / "selected_micro.json"
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if cache.exists():
        data = json.loads(cache.read_text())
        if data["source_sha256"] == digest:
            return data["rows"]
    from openpyxl import load_workbook
    book = load_workbook(SOURCE, read_only=True, data_only=True)
    it = book["Data"].iter_rows(values_only=True)
    next(it)
    header = next(it)
    fields = ["date", "weight", "Q9_mean", "Q9_cent25", "Q9_cent50", "Q9_cent75", "Q9_iqr"]
    fields += [f"Q9_bin{i}" for i in range(1, 11)]
    ix = [header.index(k) for k in fields]
    result = []
    for n, row in enumerate(it, 3):
        if row[header.index("date")] in (202001, 202206):
            result.append({"excel_row": n, **dict(zip(fields, (row[i] for i in ix)))})
    book.close()
    cache.write_text(json.dumps({"source_sha256": digest, "rows": result}))
    return result


def fit(bins, variant="base", tail_start=20.0):
    p = np.asarray(bins, dtype=float)[::-1] / 100
    occupied = np.flatnonzero(p > 0)
    lo, hi = int(occupied[0]), int(occupied[-1])
    left_open, right_open = lo == 0, hi == 9
    edges = EDGES[lo + 1:hi + 1]
    cdf = np.cumsum(p)[lo:hi]
    # Diagnostics, not claims about the official procedure.
    mask = np.ones(len(edges), dtype=bool)
    if variant in ("skip_zero_cdf", "skip_zero_1001", "relaxed_tail_skip_zero"):
        mask = p[lo:hi] > 0
    relaxed_tail = variant.startswith("relaxed_tail")
    min_shape = .05 if variant == "relax_shape" else (
        1.001 if relaxed_tail or variant in ("shape_1001", "skip_zero_1001") else 1.0)
    max_shape = 2000.0 if variant == "cap_2000" else 200.0
    lower = [min_shape, min_shape] + ([-38.] if left_open else []) + ([12.000001] if right_open else [])
    upper = [max_shape, max_shape] + ([-12.000001] if left_open else []) + ([38.] if right_open else [])
    if relaxed_tail:
        if left_open: upper[2] = 12.0 if right_open else EDGES[hi+1] - 1e-6
        if right_open: lower[2 + int(left_open)] = -12.0 if left_open else EDGES[lo] + 1e-6

    def unpack(v):
        l = v[2] if left_open else EDGES[lo]
        r = v[2 + int(left_open)] if right_open else EDGES[hi + 1]
        return v[0], v[1], l, r

    def residual(v):
        a, b, l, r = unpack(v)
        if l >= r:
            return np.full(int(sum(mask)), 10.0 + l-r)
        pred = betainc(a, b, np.clip((edges - l) / (r - l), 0, 1))
        if variant == "bin_mass":
            return np.diff(np.r_[0., pred, 1.]) - p[lo:hi + 1]
        return (pred - cdf)[mask]

    starts = [(1.1, 1.1), (2., 2.), (5., 5.)]
    candidates = []
    for a, b in starts:
        init = [a, b] + ([-tail_start] if left_open else []) + ([tail_start] if right_open else [])
        res = least_squares(residual, init, bounds=(lower, upper),
                            ftol=1e-11, xtol=1e-11, gtol=1e-11, max_nfev=1200)
        candidates.append(res)
    best = min(candidates, key=lambda z: float(z.fun @ z.fun))
    a, b, l, r = unpack(best.x)
    # scipy 1.17.1 betaincinv is inaccurate at some shapes extremely near 1.
    # Invert the CDF independently; this does not affect the mean or fitting.
    q = np.array([l + (r-l)*brentq(lambda z: betainc(a,b,z)-p,0,1,xtol=1e-13)
                  for p in (.25,.5,.75)])
    return {"mean": float(l + (r-l)*a/(a+b)), "iqr": float(q[2]-q[0]),
            "quartiles": q.tolist(), "params": [float(v) for v in (a,b,l,r)],
            "loss": float(best.fun @ best.fun), "success": bool(best.success),
            "rank": int(np.linalg.matrix_rank(best.jac)), "n_parameters": len(best.x),
            "n_residuals": len(best.fun), "nfev": best.nfev,
            "shape_at_cap": bool(max(a,b) > max_shape - .001)}


def summarize(vals):
    a = np.asarray(vals)
    return {"n":len(a), "median_abs":float(np.median(a)),
            "p95_abs":float(np.quantile(a,.95)), "max_abs":float(max(a)),
            "within_0_001":int(sum(a<=.001))}


def compare_headlines(records):
    """Full-month aggregation; distinguishes fit error from eligibility changes."""
    fitted = {r['excel_row']:r for r in records}
    result = {}
    for month in (202001,202206):
        values = defaultdict(list)
        weights = defaultdict(list)
        for row in load_rows():
            if row['date'] != month: continue
            weight = row['weight']
            if not isinstance(weight,(int,float)) or weight <= 0: continue
            official = row['Q9_mean']
            if isinstance(official,(int,float)):
                values['official_all_valid'].append(official)
                weights['official_all_valid'].append(weight)
            if row['excel_row'] in fitted:
                fits = fitted[row['excel_row']]['fits']
                means = {name:fit['mean'] for name,fit in fits.items()}
            else:
                score = score_q9([row[f'Q9_bin{i}'] for i in range(1,11)])
                if score.mean is None: continue
                means = {name:score.mean for name in records[0]['fits']}
            for name,mean in means.items():
                values[name].append(mean);weights[name].append(weight)
            if isinstance(official,(int,float)):
                values['official_common_sample'].append(official)
                weights['official_common_sample'].append(weight)
        result[str(month)] = {key:{'median':weighted_empirical_quantile(vals,weights[key]),
                                 'n':len(vals)} for key,vals in values.items()}
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-stratum", type=int, default=30,
                    help="Deterministic sample per month x open/closed x gapped/contiguous; 0=all")
    ap.add_argument("--variants", nargs="+", default=["base", "cap_2000", "skip_zero_cdf",
                    "bin_mass", "relax_shape", "shape_1001", "skip_zero_1001",
                    "relaxed_tail", "relaxed_tail_skip_zero"])
    ap.add_argument("--tag", default="diagnostic_v3")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    scorer = ROOT / "studies/sce_inflation_expectations/scoring/sce_q9.py"
    before = hashlib.sha256(scorer.read_bytes()).hexdigest()
    groups = defaultdict(list)
    for row in load_rows():
        bins = [row[f"Q9_bin{i}"] for i in range(1,11)]
        if not all(isinstance(v,(int,float)) and 0 <= v <= 100 for v in bins): continue
        if abs(sum(bins)-100)>1e-6 or not isinstance(row["Q9_mean"],(int,float)): continue
        pos = np.flatnonzero(bins)
        if len(pos)<3: continue
        kind = ("open" if pos[0]==0 or pos[-1]==9 else "closed")
        kind += "_gapped" if len(pos)!=pos[-1]-pos[0]+1 else "_contiguous"
        groups[(int(row["date"]),kind)].append(row)
    variants = args.variants
    records=[]
    for key, group in sorted(groups.items()):
        count = len(group) if args.per_stratum==0 else min(len(group),args.per_stratum)
        selected = [group[i] for i in np.linspace(0,len(group)-1,count,dtype=int)]
        for row in selected:
            bins = [row[f"Q9_bin{i}"] for i in range(1,11)]
            fits={v:fit(bins,v) for v in variants}
            if "base" in fits:
                original = score_q9(bins)
                assert abs(original.mean-fits["base"]["mean"])<1e-7
            for f in fits.values():
                f["abs_mean_error"] = abs(f["mean"]-row["Q9_mean"])
                f["abs_iqr_error"] = abs(f["iqr"]-row["Q9_iqr"])
            records.append({"month":key[0],"stratum":key[1],"excel_row":row["excel_row"],
                            "bins":bins,"official_mean":row["Q9_mean"],"fits":fits})
        print(key,"finished",len(selected),flush=True)
    summary={}
    for variant in variants:
        summary[variant]={kind:summarize([r["fits"][variant]["abs_mean_error"] for r in records
                                        if kind=="all" or r["stratum"]==kind])
                          for kind in ["all",*sorted({r["stratum"] for r in records})]}
    # Same exact three-bin input, different tail initializations: no official labels used.
    example = [20,40,40,0,0,0,0,0,0,0]
    identifiability = [{"tail_start":t,**fit(example,tail_start=t)} for t in (14.,20.,30.,37.)]
    assert hashlib.sha256(scorer.read_bytes()).hexdigest()==before
    report={"source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "original_scorer_sha256":before,"per_stratum":args.per_stratum,
            "population_counts":{str(k):len(v) for k,v in groups.items()},
            "rows":len(records),"summary":summary,
            "identifiability":{"bins":example,"solutions":identifiability},"records":records}
    if args.per_stratum == 0:
        report['headline_comparison'] = compare_headlines(records)
    dest=OUT/f"{args.tag}_n{args.per_stratum}.json"
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"output":str(dest),"rows":len(records),
                      "overall":{v:summary[v]["all"] for v in variants},
                      "identifiability":identifiability},indent=2))


if __name__ == "__main__":
    main()
