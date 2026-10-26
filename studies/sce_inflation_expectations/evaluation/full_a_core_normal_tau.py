"""Offline supervised tau sensitivity; original frozen expansion is read-only."""
from collections import defaultdict
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from ..experiments.full_a_core_normal import build_banks, checked, fresh, read, sha, write, ROOT
from ..submission_tools.reproduce import no_network
from .metrics import quantile

PREPARED = ROOT / 'outputs/sce_full_a_core_normal_prepared_20261026_v3'
EVALUATED = ROOT / 'outputs/sce_full_a_core_normal_evaluation_20261026_v3'
PROTOCOL = ROOT / 'docs/workstreams/20261026_core_normal_full_a/tau_sensitivity_protocol.json'


def kernel(payload):
    """Compile existing conditional() to exact finite-atom rational mass curves.

    For a supported cell, p(t)=p(0)+t/(neff+t)*(parent-local).
    p(1)-p(0) recovers that difference using the original implementation,
    rather than independently implementing its neighbour-selection rule.
    Empty-local fallback is fixed at every tau, including zero.
    """
    args = (payload['people'], payload['selected'], payload['answers'])
    zero = build_banks(*args, 0)['q9']
    one = build_banks(*args, 1)['q9']
    base = zero.atom_weights()
    groups = defaultdict(float)
    for uid, person in zero.population.items():
        if uid not in zero._donor_index:
            groups[zero.group_key(uid)] += person['weight']
    delta, ess = [], []
    for key, weight in groups.items():
        p0, _, audit = zero.conditional(key)
        p1, _, _ = one.conditional(key)
        n = audit['local_core_ess']
        if n > 0 and audit['outside_parent_core_n'] > 0:
            delta.append(weight * (p1-p0) * (n+1))
            ess.append(n)
    return dict(values=np.array([a.q9_mean for a in zero.answers]), base=base,
                delta=np.array(delta).reshape(-1, len(base)), ess=np.array(ess))


def masses(curve, taus):
    taus = np.asarray(taus, float)
    if np.isnan(taus).any() or (taus < 0).any():
        raise ValueError('Nonnegative tau or positive infinity required')
    finite = np.isfinite(taus)
    fraction = np.ones((len(taus), len(curve['ess'])))
    fraction[finite] = taus[finite, None] / (taus[finite, None] + curve['ess'])
    out = curve['base'][None, :] + fraction @ curve['delta']
    if np.any(out < -1e-8):
        raise ValueError('Negative population mass')
    out = np.maximum(out, 0)
    if not np.allclose(out.sum(axis=1), curve['base'].sum(), rtol=1e-12, atol=1e-9):
        raise ValueError('Population mass not conserved')
    return out


def medians(curve, taus):
    return np.array([quantile(curve['values'], w, .5) for w in masses(curve, taus)])


def pick(taus, errors):
    minimum = float(np.min(errors))
    indices = np.flatnonzero(errors <= minimum + 1e-12)
    index = min(indices, key=lambda i: taus[i])
    return float(taus[index]), minimum


def tau_label(tau):
    return 'infinity' if math.isinf(tau) else format(tau, '.12g')


def run(out):
    out = fresh(out)
    protocol = read(PROTOCOL)
    write(out/'protocol.json', protocol)
    checked(PREPARED, read(PREPARED/'manifest.json')['files_sha256'])
    checked(EVALUATED, read(EVALUATED/'manifest.json')['files_sha256'])
    summaries = read(PREPARED/'summary.json')['months']
    months = [r['month'] for r in summaries]
    coarse = np.unique(np.r_[np.arange(0, 128.000001, .125),
                             np.geomspace(128, 1000000, 257), np.inf])
    curves, predictions = {}, {}
    for i, month in enumerate(months):
        curves[month] = kernel(read(PREPARED/month/'inputs_private.json'))
        predictions[month] = medians(curves[month], coarse)
        if (i+1) % 12 == 0:
            print(f'Model-only tau curves: {i+1}/{len(months)}', flush=True)

    # Only training outcomes are parsed for selection. The CSV is frozen and
    # public aggregate-only; subsequent later parsing happens after the seal.
    train_rows = {}
    with (EVALUATED/'monthly_public.csv').open() as stream:
        for row in csv.DictReader(stream):
            if protocol['training'][0] <= row['month'] <= protocol['training'][1]:
                train_rows[row['month']] = {k: float(row[k]) for k in
                    ['truth_pp', 'before_model_pp', 'expanded_model_pp', 'baseline_pp']}
    if len(train_rows) != 48:
        raise ValueError('Expected 48 training months')
    taus = coarse.copy()
    train_months = sorted(train_rows)
    matrix = np.array([predictions[m] for m in train_months])
    targets = np.array([train_rows[m]['truth_pp'] for m in train_months])
    losses = np.mean(abs(matrix-targets[:, None]), axis=0)
    best, _ = pick(taus, losses)
    radius = .125
    for _ in range(2):
        if math.isfinite(best):
            refine = np.unique(np.maximum(0, np.linspace(best-radius, best+radius, 201)))
            added = np.array([medians(curves[m], refine) for m in train_months])
            matrix = np.column_stack([matrix, added])
            taus = np.r_[taus, refine]
            losses = np.mean(abs(matrix-targets[:, None]), axis=0)
            best, _ = pick(taus, losses)
        radius /= 100
    best_index = next(i for i, t in enumerate(taus) if t == best)
    selected = dict(selected_tau=tau_label(best), training_mae_pp=float(losses[best_index]),
        training_months=train_months, training_only_selection=True,
        unique_training_tau_values=int(len(np.unique(taus))),
        original_tau8_not_replaced=True, new_api_calls=0, new_q9_fits=0)
    write(out/'selection_sealed_before_later_evaluation.json', selected)
    print('Training selection sealed: '+json.dumps(selected, ensure_ascii=False), flush=True)

    with (EVALUATED/'monthly_public.csv').open() as stream:
        rows = list(csv.DictReader(stream))
    choices = [('original_Core', None), ('tau0', 0), ('tau8', 8), ('tau24', 24),
               ('trained_tau', best), ('parent_limit', np.inf)]
    public = []
    for row in rows:
        month = row['month']; curve = curves[month]
        for tau, old_key in [(0, 'tau_0_q9_pp'), (8, 'expanded_model_pp'), (24, 'tau_24_q9_pp')]:
            if not math.isclose(medians(curve, [tau])[0], float(row[old_key]), abs_tol=1e-10):
                raise ValueError('Existing expansion statistic changed: '+month)
        item = dict(month=month, truth_pp=float(row['truth_pp']), baseline_pp=float(row['baseline_pp']))
        for name, tau in choices:
            item[name] = float(row['before_model_pp']) if tau is None else float(medians(curve, [tau])[0])
        public.append(item)
    with (out/'monthly_public.csv').open('w') as stream:
        writer = csv.DictWriter(stream, fieldnames=public[0]); writer.writeheader(); writer.writerows(public)
    results = {}
    for name, _ in choices:
        result = {}
        for period, subset in [('training48', public[:48]), ('later34', public[48:]),
                               ('all82_descriptive', public), ('year2021', [r for r in public if r['month'].startswith('2021')])]:
            e = np.array([r[name]-r['truth_pp'] for r in subset])
            result[period] = dict(n=len(e), mae_pp=float(np.mean(abs(e))),
                                  rmse_pp=float(np.sqrt(np.mean(e**2))))
        results[name] = result
    search_rows = sorted({tau_label(t): float(e) for t, e in zip(taus, losses)}.items(),
                         key=lambda x: math.inf if x[0]=='infinity' else float(x[0]))
    write(out/'training_search.json', [dict(tau=t, mae_pp=e) for t, e in search_rows])
    summary = dict(protocol=protocol, selection=selected, results=results,
        later_selection_used=False, original_sources_modified=False,
        limits=protocol['limits'], no_global_optimum_certificate=True)
    write(out/'summary.json', summary)
    files = {p.name: sha(p) for p in out.iterdir() if p.is_file()}
    write(out/'manifest.json', dict(files_sha256=files, source_sha256={
        str(PROTOCOL.relative_to(ROOT)):sha(PROTOCOL),
        str((PREPARED/'manifest.json').relative_to(ROOT)):sha(PREPARED/'manifest.json'),
        str((EVALUATED/'manifest.json').relative_to(ROOT)):sha(EVALUATED/'manifest.json'),
        str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__))}))
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    with no_network():
        run(args.out)


if __name__ == '__main__':
    main()
