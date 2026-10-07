import copy
import unittest

from studies.sce_inflation_expectations.model_counterfactual import (
    billing, fits_budget, guarded_payload, preflight, request_bound,
)


def example():
    return {'route_candidate': 'deepinfra/fp8', 'input_price_per_million': .36,
            'output_price_per_million': .40, 'payload': {'model': 'qwen/test',
            'messages': [{'role': 'user', 'content': 'test'}], 'temperature': .5,
            'max_tokens': 1024, 'response_format': {'type': 'json_object'},
            'provider': {'order': ['deepinfra/fp8'], 'allow_fallbacks': False,
                         'require_parameters': True}}}


class CounterfactualGuards(unittest.TestCase):
    def test_real_billing_and_unknown_usage(self):
        r = example()
        self.assertEqual(billing({'usage': {'cost': .003}}, r, .02)['charged_or_reserved_usd'], .003)
        cost = billing({'usage': {'prompt_tokens': 2000, 'completion_tokens': 500}}, r, .02)
        self.assertAlmostEqual(cost['charged_or_reserved_usd'], .00092)
        self.assertEqual(billing({}, r, .02)['charged_or_reserved_usd'], .02)
        self.assertTrue(billing({}, r, .02)['uncertain'])

    def test_budget_reserves_next_call(self):
        self.assertTrue(fits_budget(.1, .1, .01))
        self.assertFalse(fits_budget(.499, .1, .002))
        self.assertFalse(fits_budget(.3, .249, .002))
        with self.assertRaises(ValueError):
            fits_budget(float('nan'), 0, .01)

    def test_no_prompt_mutation_or_fallback(self):
        r = example(); before = copy.deepcopy(r)
        p = guarded_payload(r)
        self.assertEqual(r, before)
        self.assertEqual(p['messages'], r['payload']['messages'])
        self.assertEqual(p['provider']['max_price'], {'prompt': .36, 'completion': .4})
        r['payload']['provider']['allow_fallbacks'] = True
        with self.assertRaises(ValueError):
            guarded_payload(r)

    def test_price_health_and_parameters_block_before_call(self):
        endpoint = {'tag': 'deepinfra/fp8', 'status': 0,
                    'pricing': {'prompt': '0.00000036', 'completion': '0.0000004'},
                    'supported_parameters': ['response_format', 'temperature', 'max_tokens']}
        d = {'data': {'endpoints': [endpoint]}}
        self.assertEqual(preflight(example(), d)['status'], 0)
        endpoint['status'] = -5
        with self.assertRaises(ValueError): preflight(example(), d)
        endpoint['status'] = 0; endpoint['pricing']['prompt'] = '0.000001'
        with self.assertRaises(ValueError): preflight(example(), d)
        endpoint['pricing']['prompt'] = '0.00000036'; endpoint['supported_parameters'] = []
        with self.assertRaises(ValueError): preflight(example(), d)

    def test_cost_bound_counts_utf8_bytes(self):
        r = example(); r['payload']['messages'] = [{'role': 'user', 'content': '中' * 500}]
        bound = request_bound(r['payload'], .36, .4)
        self.assertGreater(bound, (1500 * .36 + 1024 * .4) / 1e6)


if __name__ == '__main__': unittest.main()
