"""Evaluation-only inverse diagnostic, NEVER an Agent input or scoring rule.

Recover one beta curve compatible with published mean/quartiles for selected
discrepancies. This is not proof of the NY Fed's original parameters/optimizer.
Run diagnose_sce_beta.py --per-stratum 0 --variants base relaxed_tail_skip_zero
--tag full_two_month first. Results remain in ignored outputs/.
"""
import json
import numpy as np
from scipy.optimize import least_squares
from scipy.special import betaincinv, betainc
from diagnose_sce_beta import OUT, load_rows, EDGES


def main():
    audit = json.loads((OUT / "full_two_month_n0.json").read_text())
    rows = {r["excel_row"]:r for r in load_rows()}
    selected = []
    for kind in ("closed_contiguous", "open_contiguous", "open_gapped"):
        group = sorted((r for r in audit["records"] if r["stratum"]==kind),
                       key=lambda r:r["fits"]["relaxed_tail_skip_zero"]["abs_mean_error"],
                       reverse=True)
        selected.extend(group[:4])
    results = []
    for rec in selected:
        row = rows[rec["excel_row"]]
        y = np.array([row[k] for k in ("Q9_mean","Q9_cent25","Q9_cent50","Q9_cent75")])

        def predicted(v):
            a,b,l,span = v
            return np.r_[l+span*a/(a+b),l+span*betaincinv(a,b,[.25,.5,.75])]

        attempts = [least_squares(lambda v: predicted(v)-y, st,
                    bounds=([1.00001,1.00001,-150,.01],[500,500,12,300]),
                    max_nfev=2500,ftol=1e-11,xtol=1e-11,gtol=1e-11)
                    for st in ([2,2,-20,50],[2,8,-20,60],[8,2,-38,60])]
        best = min(attempts,key=lambda z:float(z.fun@z.fun))
        a,b,l,span=best.x
        p=np.asarray(rec['bins'])[::-1]/100
        cdf=betainc(a,b,np.clip((EDGES[1:-1]-l)/span,0,1))
        results.append({"excel_row":rec['excel_row'],"stratum":rec['stratum'],
                        "bins":rec['bins'],"official_stats":y.tolist(),
                        "compatible_params_a_b_left_right":[a,b,l,l+span],
                        "max_stats_residual":float(max(abs(best.fun))),
                        "full_cdf_loss":float(sum((cdf-np.cumsum(p)[:-1])**2)),
                        "original_fit":rec['fits']['base']})
    (OUT/'reference_support_diagnostic.json').write_text(json.dumps({
        "warning":"Inverse diagnostic only; not uniquely identified official parameters, not a scorer",
        "cases":results},indent=2)+'\n')
    print('saved',len(results),'inverse diagnostic cases')


if __name__ == '__main__':
    main()
