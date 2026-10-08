"""Offline exact-case comparisons: score truth and all models the same way."""
import math
import numpy as np
from scipy.stats import wasserstein_distance
from .household_state_analysis import distribution


def comparison_metrics(rows, arms):
    """One common finite mask for all models, separate callers for Q8 and Q9."""
    common = [r for r in rows if all(type(r.get(k)) in (int, float) and math.isfinite(r[k]) for k in ['real', *arms])]
    result = {'n_selected': len(rows), 'n_common': len(common), 'n_excluded': len(rows)-len(common), 'arms': {}}
    if not common:
        raise ValueError('no common scored cases')
    observed = np.array([r['real'] for r in common]); result['matched_real'] = distribution(observed)
    for arm in arms:
        pred = np.array([r[arm] for r in common]); err = pred-observed
        result['arms'][arm] = {'distribution': distribution(pred),
                              'individual_mae_pp': float(np.abs(err).mean()),
                              'individual_rmse_pp': float(np.sqrt(np.mean(err**2))),
                              'mean_bias_pp': float(err.mean()),
                              'sample_median_absolute_error_pp': abs(float(np.median(pred)-np.median(observed))),
                              'sample_iqr_absolute_gap_pp': abs(float(np.subtract(*np.quantile(pred,[.75,.25])))-result['matched_real']['iqr']),
                              'wasserstein_1_pp': float(wasserstein_distance(pred,observed))}
    if 'deepseek_reference' in arms:
        base = np.array([r['deepseek_reference'] for r in common])
        result['paired_mae_changes_vs_deepseek_pp'] = {
            arm: float(np.mean(np.abs(np.array([r[arm] for r in common])-observed)-np.abs(base-observed)))
            for arm in arms if arm != 'deepseek_reference'}
    return result
