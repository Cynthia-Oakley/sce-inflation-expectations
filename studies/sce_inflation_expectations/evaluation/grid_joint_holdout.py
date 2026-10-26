"""Human-answer conditional-distribution check for a frozen grid shortlist.

This is statistical feasibility, not an LLM experiment or a deployed Bayes model.
"""
from pathlib import Path
from collections import defaultdict
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance

from .grid_dimension_selection import ROOT, response_matrix, THRESHOLDS, DOMAIN_NAMES, ess, sha, dump, bootstrap_indices
from ..population_stratification import allocate_core


def empirical_joint_law(core_cells, target_cells, core_weights, target_weights, *, tau):
    """Integrate whole Core answer atoms; local and parent evidence disjoint.

    Conditional mean is only an auxiliary held-out score, not a synthetic Q9
    answer. Atom masses define the across-person predictive distribution.
    """
    cw = np.asarray(core_weights, float); tw = np.asarray(target_weights, float)
    if len(cw) == 0 or np.any(cw <= 0) or np.any(tw <= 0) or tau < 0:
        raise ValueError('Positive finite support and nonnegative tau required')
    core_cells, target_cells = np.asarray(core_cells), np.asarray(target_cells)
    conditional = np.empty((len(tw), len(cw)))
    unsupported = prior_mass = 0.
    for cell in np.unique(target_cells):
        target = target_cells == cell; local = core_cells == cell; parent = ~local
        p = np.zeros(len(cw)); neff = ess(cw[local])
        fraction = neff/(neff+tau) if neff else 0.
        if not parent.any():
            fraction = 1.
        if local.any():
            p[local] = fraction*cw[local]/cw[local].sum()
        else:
            unsupported += tw[target].sum()
        if parent.any():
            p[parent] = (1-fraction)*cw[parent]/cw[parent].sum()
        if not np.isclose(p.sum(), 1):
            raise ValueError('Predictive probability lost mass')
        conditional[target] = p
        prior_mass += (1-fraction)*tw[target].sum()
    atoms = tw@conditional/tw.sum()
    return conditional, atoms, unsupported/tw.sum(), prior_mass/tw.sum()


def ratio_domain_loss(y, predicted, baseline, w):
    se = np.sum(w[:, None]*(y-predicted)**2, axis=0)
    ss = np.sum(w[:, None]*(y-baseline)**2, axis=0)
    loss = se[:3]/ss[:3]
    delta = np.gradient(THRESHOLDS)
    return np.r_[loss, (se[3:]@delta)/(ss[3:]@delta)]


def run(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    out.mkdir(parents=True)
    summary = json.loads((source/'summary.json').read_text())
    recommended = summary['selection']['recommended']
    shortlist = {recommended: recommended.split('+'),
                 'education+numeracy+income+gender': ['education','numeracy','income','gender'],
                 'education+numeracy+income+age': ['education','numeracy','income','age'],
                 'education_x_attachment_6': ['education','attachment']}
    protocol = {'status': 'post_screen_shortlist_check_plan_saved_before_check_results',
        'shortlist': shortlist, 'core_budgets': [256,512], 'seeds': [20261023,20261024],
        'tau_main': 8, 'tau_sensitivity': [0,24], 'folds': 4,
        'source_summary_sha256': sha(source/'summary.json'),
        'method': 'Same-month human Core, held-out respondent folds. Identical Core per candidate, sampled using legacy six strata and known w/pi; whole answer atom distributions with disjoint outside-cell empirical parent.',
        'limits': ['Current human Core answers are evaluation-only statistical reference, never simulation input.',
                   'No claim that LLM Core has these distributions or that Normal recovers personal beliefs.',
                   'Empirical parent and tau are fixed diagnostic smoothing, not an implemented generative Bayes model.',
                   'Do not select a new grid on the temporal results.']}
    dump(out/'protocol.json', protocol)
    frame = pd.read_parquet(source/'analysis_frame_private.parquet')
    fold = {int(u): int.from_bytes(hashlib.sha256(f'20261023:{int(u)}'.encode()).digest()[:8], 'big') % 4 for u in frame.userid.unique()}
    frame['_fold'] = frame.userid.map(fold)
    record = defaultdict(list)
    for month, rows in frame.groupby('date', sort=True):
        labels = {name: rows[fields].astype(str).agg('|'.join, axis=1).to_numpy() for name, fields in shortlist.items()}
        old_cells = labels['education_x_attachment_6']
        y = response_matrix(rows); w = rows.weight.to_numpy(float)
        f = rows._fold.to_numpy()
        for heldout in range(4):
            pool = np.flatnonzero(f != heldout); target = np.flatnonzero(f == heldout)
            if not len(target):
                continue
            groups = {cell: pool[old_cells[pool] == cell] for cell in np.unique(old_cells[pool])}
            counts = {k: len(v) for k,v in groups.items()}
            masses = {k: float(w[v].sum()) for k,v in groups.items()}
            for budget in protocol['core_budgets']:
                alloc = allocate_core(counts, masses, min(budget,len(pool)), minimum=3)
                for seed in protocol['seeds']:
                    rng = np.random.default_rng(np.random.SeedSequence([seed,int(month),heldout,budget]))
                    core, dw = [], []
                    for k, ids in groups.items():
                        chosen = rng.choice(ids, alloc[k], replace=False)
                        core.extend(chosen.tolist()); dw.extend((w[chosen]/(alloc[k]/len(ids))).tolist())
                    core = np.array(core); dw = np.array(dw)
                    baseline = np.average(y[core], axis=0, weights=dw)
                    for name, all_cells in labels.items():
                        for tau in [0,8,24]:
                            p, atoms, unsupported, prior = empirical_joint_law(all_cells[core], all_cells[target], dw, w[target], tau=tau)
                            loss = ratio_domain_loss(y[target], p@y[core], baseline, w[target])
                            w1 = wasserstein_distance(y[core,0], y[target,0], atoms, w[target])
                            record[(int(month),budget,tau,name)].append([*loss,w1,unsupported,prior])
        if int(month)%100 in [1,6,12]:
            print('Joint holdout checked', int(month), flush=True)
    monthly = [{'month': month,'core_budget': budget,'tau': tau,'grid': name,
                'domain_losses': np.mean(values,axis=0)[:4].tolist(),
                'w1_pp': float(np.mean(values,axis=0)[4]),
                'unsupported_target_mass': float(np.mean(values,axis=0)[5]),
                'parent_mass': float(np.mean(values,axis=0)[6])}
               for (month,budget,tau,name),values in sorted(record.items())]
    periods = {'development': (201901,202212),'2023_2024': (202301,202412),'2025_01_10': (202501,202510)}
    results = {}
    for period,(start,end) in periods.items():
        results[period] = {}
        for budget in protocol['core_budgets']:
            for tau in [0,8,24]:
                key = f'core{budget}_tau{tau}'
                results[period][key] = {}
                for name in shortlist:
                    part = [r for r in monthly if start<=r['month']<=end and r['core_budget']==budget and r['tau']==tau and r['grid']==name]
                    loss = np.mean([r['domain_losses'] for r in part],axis=0)
                    results[period][key][name] = {'domain_gain':dict(zip(DOMAIN_NAMES,(1-loss).tolist())),
                        'composite_gain':float(1-loss.mean()), 'w1_pp':float(np.mean([r['w1_pp'] for r in part])),
                        'unsupported_target_mass':float(np.mean([r['unsupported_target_mass'] for r in part])),
                        'parent_mass':float(np.mean([r['parent_mass'] for r in part]))}
    result = {'status': 'human_answer_statistical_feasibility_not_llm_validation',
              'protocol':protocol,'new_api_calls':0,'q9_refits':0,
              'source_sha256':{str((source/'summary.json').relative_to(ROOT)):sha(source/'summary.json'),
                               str(Path(__file__).relative_to(ROOT)):sha(__file__)},
              'periods':results,'monthly':monthly}
    dump(out/'summary.json',result)
    print('Saved',out/'summary.json',flush=True)
    return result
