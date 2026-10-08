import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reuse_runner', ROOT / 'scripts/run_sce_reuse_probe.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
MODEL = 'qwen/qwen-2.5-72b-instruct'


class ReuseProbeTests(unittest.TestCase):
    def prepare(self, root):
        folder = root / 'inputs'
        folder.mkdir()
        rows = [{'case_id': f'{m}_{i}', 'month': m,
                 'destination': 'https://openrouter.ai/api/v1', 'route_candidate': 'deepinfra/fp8',
                 'input_price_per_million': .36, 'output_price_per_million': .4,
                 'payload': {'model': MODEL, 'messages': [{'role': 'user', 'content': 'test'}],
                             'temperature': .5, 'max_tokens': 1024,
                             'response_format': {'type': 'json_object'},
                             'provider': {'order': ['deepinfra/fp8'], 'allow_fallbacks': False,
                                          'require_parameters': True}}}
                for m in range(202101, 202113) for i in range(20)]
        (folder / 'requests_prepared.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        plan = {'model': MODEL, 'budget_cap_usd': .5, 'source_sha256': {}, 'execution_code_sha256': {},
                'requests_sha256': runner.sha(folder / 'requests_prepared.jsonl'),
                'prompt_version': 'test', 'retry_protocol': 'identical', 'source_run_id': 'mock', 'scope': 'mock'}
        (folder / 'summary.json').write_text(json.dumps(plan))
        receipt = root / 'receipt.json'
        receipt.write_text(json.dumps({'summary_sha256': runner.sha(folder / 'summary.json'),
                                      'requests_sha256': plan['requests_sha256']}))
        return folder, receipt

    def test_offline_never_opens_network(self):
        with tempfile.TemporaryDirectory() as name, patch.object(runner.httpx, 'Client', side_effect=AssertionError('network')):
            root = Path(name)
            folder, receipt = self.prepare(root)
            runner.main(['--inputs', str(folder), '--receipt', str(receipt), '--out', str(root / 'run')])
            self.assertFalse((root / 'run').exists())

    def test_changed_input_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as name:
            folder, receipt = self.prepare(Path(name))
            (folder / 'requests_prepared.jsonl').write_text('{}\n')
            with self.assertRaises(AssertionError):
                runner.load_inputs(folder, receipt)

    def test_identical_retry_and_unknown_billing_stop(self):
        class Client:
            bodies = []
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def get(self, url):
                return runner.httpx.Response(200, request=runner.httpx.Request('GET', url), json={'data': {'endpoints': [{
                    'tag': 'deepinfra/fp8', 'status': 0, 'pricing': {'prompt': '.00000036', 'completion': '.0000004'},
                    'supported_parameters': ['response_format', 'temperature', 'max_tokens']}]}})
            def post(self, url, headers, json):
                self.bodies.append(json)
                n = len(self.bodies)
                if n == 4:
                    return runner.httpx.Response(429)
                answer = {'point_pct': 2, 'q9': {f'bin{i}': 10 for i in range(1, 11)}}
                if n == 2: answer['q9']['bin1'] = 9
                data = {'model': MODEL, 'provider': 'DeepInfra', 'usage': {'cost': .0001},
                        'choices': [{'message': {'content': __import__('json').dumps(answer)}}]}
                return runner.httpx.Response(200, json=data)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            folder, receipt = self.prepare(root)
            with patch.object(runner.httpx, 'Client', return_value=Client()), patch.dict(runner.os.environ, {'OPENROUTER_API_KEY': 'mock'}), patch.object(runner.time, 'sleep'):
                runner.main(['--inputs', str(folder), '--receipt', str(receipt), '--out', str(root / 'run'),
                             '--confirm-spend', '--authorization-note', 'mock only'])
            state = json.loads((root / 'run/run_summary.json').read_text())
            self.assertEqual(state['status'], 'audit_stopped')
            self.assertEqual(state['paid_attempts'], 4)
            self.assertEqual(state['valid_answers'], 2)
            self.assertGreater(state['spent_or_reserved_usd'], .0003)
            self.assertEqual(Client.bodies[1], Client.bodies[2])
            self.assertFalse((root / 'run/pending_request.json').exists())


if __name__ == '__main__': unittest.main()
