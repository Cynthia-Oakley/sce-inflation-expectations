"""National-only evaluation of the sealed B proxy expansion; no re-tuning."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import csv
import math

from ..experiments.frozen_batch import ROOT, read_json, dump, sha
from ..experiments.state_continuity_execution import verify
from ..experiments.recent_b_review_materials import macro_prediction
from .metrics import distribution_summary, headline_errors
from .recent_b_readout import validate_catalog
from ..submission_tools.reproduce import no_network

CORE_RUN=ROOT/'outputs/sce_recent_b_sampled_terminal_20261026_v1'


def evaluate(prediction,out):
    prediction,out=Path(prediction).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored evaluation directory required')
    manifest=read_json(prediction/'manifest.json')
    for root,hashes in ((prediction,manifest['files_sha256']),(ROOT,manifest['source_sha256'])):
        for name,digest in hashes.items():
            f=(root/name).resolve()
            if not f.is_relative_to(root) or sha(f)!=digest:raise ValueError('Sealed expansion changed: '+name)
    summary=read_json(prediction/'summary.json');protocol=read_json(prediction/'protocol.json')
    if summary['tau']!=8 or protocol['target_n']!=1300 or summary['months']!=11:
        raise ValueError('Only the current sealed tau8/1300 B11 expansion is registered')
    corep,_=verify(CORE_RUN/'package')
    for name,digest in read_json(CORE_RUN/'evaluation/manifest.json')['files_sha256'].items():
        if sha(CORE_RUN/'evaluation'/name)!=digest:raise ValueError('Core evaluation changed')
    params=read_json(ROOT/corep['parameter_source']);alpha=params['blends']['mse']['simulation_weight']
    with (ROOT/corep['public_macro_review']).open() as f:public={r['month']:r for r in csv.DictReader(f)}
    core=read_json(CORE_RUN/'evaluation/summary.json')
    catalog=ROOT/corep['target_catalog_evaluation_only'];validate_catalog(catalog,corep['months'])
    truths={r['reference_period'].replace('-',''):r for r in read_json(catalog)['headline_releases']}
    # The expansion was sealed without target answers; only this subsequent
    # evaluator, requested explicitly by the user, opens national target values.
    rows=[]
    for before in core['monthly']:
        month=str(before['month']);atoms=read_json(prediction/month/'atoms_private.json')['atoms']
        weights=[a['weight'] for a in atoms]
        if not math.isclose(sum(weights),1300,abs_tol=1e-8):raise ValueError('Expected total proxy mass 1300')
        desc=distribution_summary([a['q9_mean'] for a in atoms],weights)
        q8=distribution_summary([a['q8'] for a in atoms],weights)
        truth=truths[month]['value_pp']
        if truth!=before['truth_pp']:raise ValueError('Core and expansion targets must match')
        r=dict(month=month,truth_pp=truth,baseline_pp=before['anchor_pp'],Core_pp=before['sim_pp'],
            expanded_pp=desc['median_pp'],Core_blend_pp=before['frozen_combination_pp'],
            expanded_blend_pp=(1-alpha)*before['anchor_pp']+alpha*desc['median_pp'],
            Core_iqr_descriptive_pp=before['sim_cross_person_iqr_pp_descriptive_only'],
            expanded_iqr_descriptive_pp=desc['iqr_pp'],expanded_q8_median_descriptive_pp=q8['median_pp'])
        if not math.isclose(r['Core_blend_pp'],(1-alpha)*r['baseline_pp']+alpha*r['Core_pp'],abs_tol=1e-12):
            raise ValueError('Fixed Core blend weight differs')
        cp=public[month]
        for label,value in (('Core',r['Core_pp']),('expanded',r['expanded_pp'])):
            x=dict(baseline_pp=r['baseline_pp'],sim_pp=value,cpi_yoy_pp=float(cp['cpi_yoy_pp']),cpi_change_pp=float(cp['cpi_change_pp']))
            r[label+'_macro_pp']=macro_prediction(x,params['fits']['macro_plus_sim'])
        r['macro_without_sim_pp']=macro_prediction(x,params['fits']['macro_without_sim'])
        rows.append(r)
    truth=[r['truth_pp'] for r in rows]
    keys=('baseline_pp','Core_pp','expanded_pp','Core_blend_pp','expanded_blend_pp','macro_without_sim_pp','Core_macro_pp','expanded_macro_pp')
    metrics={k:headline_errors([r[k] for r in rows],truth) for k in keys}
    result=dict(status='completed_national_only_Core_Normal_B_evaluation',months=11,n_per_month=1300,
        tau=8.,simulation_blend_weight=alpha,coefficients_refitted=False,new_API_calls=0,new_Q9_fits=0,
        metrics=metrics,unchanged_monthly_medians=sum(r['Core_pp']==r['expanded_pp'] for r in rows),
        mean_Core_iqr_descriptive_pp=sum(r['Core_iqr_descriptive_pp'] for r in rows)/11,
        mean_expanded_iqr_descriptive_pp=sum(r['expanded_iqr_descriptive_pp'] for r in rows)/11,
        expanded_win_months_vs_baseline=sum(abs(r['expanded_pp']-r['truth_pp'])<abs(r['baseline_pp']-r['truth_pp'])-1e-12 for r in rows),
        monthly=rows,evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
        limits=['National targets only; no recent human micro accuracy or W1/IQR error.',
                'Exact posterior-mean atom CDF, not random Normal inspection rows.',
                'Same fixed Core-trained blend/macro parameters used on both series; expanded macro is transfer sensitivity, not a re-trained model.',
                '1300 proxy rows add no independent model or monthly validation observations.',
                'B is retrospective and has already been inspected; no new blind-test claim.'])
    out.mkdir();dump(out/'summary.json',result)
    with (out/'monthly_national.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    sources={str(p.relative_to(ROOT)):sha(p) for p in (Path(__file__),prediction/'manifest.json',CORE_RUN/'evaluation/summary.json',
        ROOT/corep['parameter_source'],ROOT/corep['public_macro_review'],catalog,Path(__file__).with_name('metrics.py'))}
    dump(out/'manifest.json',dict(files_sha256={f.name:sha(f) for f in out.iterdir() if f.is_file()},
        source_sha256=sources,prediction_manifest_sha256=sha(prediction/'manifest.json'),new_API_calls=0))
    print(result['status'],metrics,flush=True)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prediction',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    a=parser.parse_args(argv)
    with no_network():evaluate(a.prediction,a.out)

