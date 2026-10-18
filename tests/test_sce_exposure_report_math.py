"""Independent weighted-distribution checks for the vectorized report."""
import importlib.util
from pathlib import Path

import numpy as np
from scipy.stats import wasserstein_distance


def test_vectorized_distances_and_known_weighted_medians():
    path = Path(__file__).resolve().parents[1]/'scripts/report_sce_information_exposure.py'
    spec = importlib.util.spec_from_file_location('sce_exposure_report', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    x, y = np.array([-2., 1., 1., 6.]), np.array([0., 2., 3., 8.])
    weights = np.array([[1., 2., 3., 1.], [0., 3., 1., 2.], [4., 0., 0., 1.]])
    assert np.allclose(module.batch_w1(x, y, weights), [wasserstein_distance(x, y, w, w) for w in weights])
    assert np.allclose(module.batch_quantile(x, weights), [1., 1., -2.])
