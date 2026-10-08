import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reuse_analysis', ROOT / 'scripts/analyze_sce_reuse_probe.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


class ReuseAnalysisTests(unittest.TestCase):
    def test_known_constant_shift_metrics_and_panel_interval(self):
        arms = ['deepseek', 'qwen']
        private = [{'month': month, 'panel_case': f'p{i}',
                    'Q9': {'real': float(i + month % 100),
                           'deepseek': float(i + month % 100 + 2),
                           'qwen': float(i + month % 100 + 1)}}
                   for month in range(202101, 202113) for i in range(20)]
        monthly = {str(month): {'Q9': analysis.comparison_metrics(
            [r['Q9'] for r in private if r['month'] == month], arms)}
            for month in range(202101, 202113)}
        report = analysis.annual(monthly, arms)
        self.assertEqual(report['deepseek']['monthly_median_mae_pp'], 2)
        self.assertEqual(report['qwen']['monthly_median_rmse_pp'], 1)
        self.assertEqual(report['qwen']['monthly_median_bias_pp'], 1)
        self.assertEqual(report['qwen']['trend']['direction_matches_on_real_changes'], 11)
        self.assertTrue(report['development_gate']['worth_future_confirmation'])
        interval = analysis.bootstrap_panel(private, arms)
        self.assertEqual(interval['qwen_minus_deepseek_monthly_median_mae_pp_percentile_interval'], [-1., -1.])

    def test_common_mask_does_not_compare_missing_qwen_with_other_people(self):
        rows = [{'real': 1., 'deepseek': 4., 'qwen': 2.},
                {'real': 100., 'deepseek': 100., 'qwen': None}]
        report = analysis.comparison_metrics(rows, ['deepseek', 'qwen'])
        self.assertEqual(report['n_common'], 1)
        self.assertEqual(report['matched_real']['median'], 1)
        self.assertEqual(report['arms']['deepseek']['sample_median_absolute_error_pp'], 3)


if __name__ == '__main__': unittest.main()
