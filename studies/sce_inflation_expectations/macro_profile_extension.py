"""Small fixed models of delayed SCE population margins, never answers.

Income unknown share is carried from the donor, not economically imputed.
"""
import calendar
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np

from .macro_population import month_shift, employment_shares

EMPLOYMENT_MODELS = {'unrate_ols': (0,), 'epop_ols': (1,), 'epop_lfpr_ridge': (1, 2)}
INCOME_MODELS = {'weekly_wage_ols': (0,), 'hourly_wage_ols': (1,),
                 'weekly_wage_personal_income_ridge': (0, 2),
                 'bea_wages_personal_income_ridge': (3, 2)}
INCOME_CATEGORIES = ('under_50k', '50k_to_100k', 'over_100k', 'unknown')


def select_visible(observations, cutoff, *, initial_only=False):
    """Latest recorded historical version <= cutoff; never today's snapshot."""
    result = {}
    for row in observations:
        if row['eligibility'] != 'eligible':
            continue
        if initial_only and row['reference_period'] != row['release_reference_period']:
            continue
        published = datetime.fromisoformat(row['published_at'])
        if published > cutoff:
            continue
        key = (row['series'], int(row['reference_period'].replace('-', '')))
        if key not in result or published > datetime.fromisoformat(result[key]['published_at']):
            result[key] = row
        elif published == datetime.fromisoformat(result[key]['published_at']) and row['value'] != result[key]['value']:
            raise ValueError('conflicting same-release observations')
    return result


def composition_logratios(values):
    p = np.asarray(values, dtype=float)
    if p.ndim != 1 or len(p) < 2 or not np.isfinite(p).all() or (p < 0).any() or not np.isclose(p.sum(), 1):
        raise ValueError('invalid composition')
    p = np.maximum(p, 1e-6); p /= p.sum()
    return np.log(p[:-1]/p[-1])


def forecast_composition(rows, test, feature_indices, *, ridge=False, drift=False, min_train=24):
    if test['donor_end'] >= test['month']:
        raise ValueError('label cutoff must precede target')
    train = [r for r in rows if r['month'] <= test['donor_end']]
    if len(train) < min_train:
        raise ValueError('not enough previously available labels')
    y = np.array([composition_logratios(r['truth'])-composition_logratios(r['base']) for r in train])
    audit = {'train_n': len(train), 'max_train_month': max(r['month'] for r in train),
             'label_cutoff': test['donor_end'], 'ridge_alpha': 1 if ridge else 0,
             'feature_indices': list(feature_indices)}
    if drift:
        update = y.mean(axis=0)
    else:
        x = np.array([[r['features'][i] for i in feature_indices] for r in train])
        center = x.mean(axis=0); scale = x.std(axis=0); scale[scale < 1e-12] = 1
        design = np.column_stack([np.ones(len(x)), (x-center)/scale])
        penalty = np.diag(np.r_[0, np.ones(len(feature_indices))])
        coef = np.linalg.solve(design.T@design + penalty, design.T@y) if ridge else np.linalg.lstsq(design, y, rcond=None)[0]
        tx = np.r_[1, (np.array([test['features'][i] for i in feature_indices])-center)/scale]
        update = tx@coef
        audit.update(center=center.tolist(), scale=scale.tolist(), coefficients=coef.tolist())
    z = np.r_[composition_logratios(test['base'])+update, 0]
    p = np.exp(z-z.max()); p /= p.sum()
    return p.tolist(), audit


def income_shares(margin):
    p = np.array([margin.get(k, 0) for k in INCOME_CATEGORIES])
    if not np.isclose(p.sum(), 1) or (p < 0).any() or p[-1] >= 1:
        raise ValueError('invalid income margin')
    return p


def build_feature_rows(population, observations, *, target, weighting, bea=False):
    waves = {r['month']: r for r in population}; rows = []; skipped = []
    for month, wave in sorted(waves.items()):
        if month < 202001:
            continue
        donor = month_shift(month, -10)
        if donor not in waves:
            continue
        previous = month_shift(month, -1); y, m = divmod(previous, 100)
        cutoff = datetime(y, m, calendar.monthrange(y, m)[1], 23, 59, 59, tzinfo=ZoneInfo('America/New_York'))
        known = select_visible(observations, cutoff, initial_only=target == 'employment')
        used = []
        def get(series, ref):
            row = known[(series, ref)]; used.append(row); return row['value']
        try:
            if target == 'employment':
                latest = max(ref for (s, ref) in known if s == 'LNS14000000')
                features = [get(s, latest)-get(s, donor) for s in ['LNS14000000', 'LNS12300000', 'LNS11300000']]
                base = employment_shares(waves[donor]['margins']['employment_status'][weighting])
                truth = employment_shares(wave['margins']['employment_status'][weighting])
                mixture = np.mean([employment_shares(waves[month_shift(donor, -i)]['margins']['employment_status'][weighting]) for i in range(12)], axis=0)
                unknown = None
            elif target == 'income':
                def window_gap(series, saar=False):
                    latest = max(ref for s, ref in known if s == series)
                    # Mean weekly/hourly wage exposure across each preceding year.
                    # BEA SAAR / 12 summed across twelve months = annual nominal total.
                    now = sum(get(series, month_shift(latest, -i)) for i in range(12)) / 12
                    old = sum(get(series, month_shift(donor, -i)) for i in range(12)) / 12
                    return 100*np.log(now/old)
                features = [window_gap(s) for s in ['CES0500000011', 'CES0500000003']]
                if bea:
                    features += [window_gap(s, True) for s in ['BEA_PERSONAL_INCOME', 'BEA_WAGES_SALARIES']]
                b = income_shares(waves[donor]['margins']['household_income_band'][weighting])
                t = income_shares(wave['margins']['household_income_band'][weighting])
                mm = np.mean([income_shares(waves[month_shift(donor, -i)]['margins']['household_income_band'][weighting]) for i in range(12)], axis=0)
                base = b[:3]/(1-b[3]); truth = t[:3]/(1-t[3]); mixture = mm[:3]/(1-mm[3]); unknown = float(b[3])
            else:
                raise ValueError('unknown target')
        except (KeyError, ValueError) as error:
            skipped.append({'month': month, 'reason': str(error)}); continue
        rows.append({'month': month, 'donor_end': donor, 'as_of': cutoff.isoformat(), 'features': features,
                     'base': base.tolist(), 'truth': truth.tolist(), 'mixture': mixture.tolist(),
                     'unknown_donor': unknown,
                     'truth_full': t.tolist() if target == 'income' else truth.tolist(),
                     'base_full': b.tolist() if target == 'income' else base.tolist(),
                     'mixture_full': mm.tolist() if target == 'income' else mixture.tolist(),
                     'macro_max_published_at': max(r['published_at'] for r in used),
                     'macro_references': sorted({(r['series'], r['reference_period'], r['published_at']) for r in used})})
    return rows, skipped


def evaluate(rows, *, target, models):
    predictions = []
    for test in rows:
        if sum(r['month'] <= test['donor_end'] for r in rows) < 24:
            continue
        result = {'latest_public_wave': test['base_full'], 'past_12_public_waves': test['mixture_full']}; audits = {}
        for name, indices in {'historical_drift': (), **models}.items():
            p, audit = forecast_composition(rows, test, indices, ridge=name.endswith('_ridge'), drift=name == 'historical_drift')
            if target == 'income':
                p = [value*(1-test['unknown_donor']) for value in p] + [test['unknown_donor']]
            result[name] = p; audits[name] = audit
        predictions.append({**test, 'predictions': result, 'fit_audit': audits})
    if not predictions:
        raise ValueError('no available common evaluation months')
    labels = ['employed', 'sce_unemployed', 'remaining'] if target == 'employment' else list(INCOME_CATEGORIES)
    def metrics(part):
        out = {}
        for name in part[0]['predictions']:
            err = 100*np.array([np.array(r['predictions'][name])-r['truth_full'] for r in part])
            out[name] = {'mae_pp': dict(zip(labels, np.abs(err).mean(axis=0).tolist())),
                         'bias_pp': dict(zip(labels, err.mean(axis=0).tolist())),
                         'rmse_pp': dict(zip(labels, np.sqrt((err**2).mean(axis=0)).tolist())),
                         'distribution_mean_tvd': float(np.abs(err).sum(axis=1).mean()/200)}
        return out
    summary = {'feature_months': len(rows), 'evaluation_months': len(predictions),
               'evaluation_start': predictions[0]['month'], 'evaluation_end': predictions[-1]['month'],
               'metrics': metrics(predictions),
               'yearly': {str(y): metrics([r for r in predictions if r['month']//100 == y]) for y in sorted({r['month']//100 for r in predictions})},
               'rolling_12': [{'end': predictions[i]['month'], 'metrics': metrics(predictions[i-11:i+1])} for i in range(11, len(predictions))]}
    return predictions, summary
