from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from studies.sce_inflation_expectations.experiments.state_continuity_execution import execute, node_key, reserve, run
from studies.sce_inflation_expectations.state_continuity_runtime import (
    initialize_state, STATE_TOKEN, TIMING_TOKEN, advance_state,
)
from studies.sce_inflation_expectations.evaluation.state_continuity import assemble_cases, summarize, field_view


def fixture():
    inputs = {}; nodes = []
    for month, previous, point in [('202505', 202504, 3.), ('202506', 202505, 7.)]:
        state = initialize_state(dict(fields={
            'q8': dict(value=point, source_period=previous, source_kind='own_observed'),
            'q9': dict(value=[10.] * 10, source_period=previous, source_kind='own_observed')},
            own_history_centers=[], comparison_reference_day=f'{previous // 100}-{previous % 100:02}-15',
            comparison_day_source='own_observed_survey_day'))
        context = dict(as_of=f'{month[:4]}-{month[-2:]}-15T23:59:59-04:00', common_news=[], personal_news=[],
                       policy_published_at=f'{month[:4]}-{month[-2:]}-01T12:00:00-04:00',
                       food_published_at=f'{month[:4]}-{month[-2:]}-15T08:30:00-04:00')
        inputs[month, 'a'] = ([dict(role='user', content='SAME E\n' + TIMING_TOKEN + STATE_TOKEN + '\nSAME Q')], state, context)
        for repeat in [1, 2]:
            for arm in ['observed_history', 'simulated_history']:
                dep = (dict(month='202505', agent_id='a', repeat=repeat, arm=arm)
                       if month == '202506' and arm == 'simulated_history' else None)
                nodes.append(dict(month=month, agent_id='a', repeat=repeat, arm=arm,
                    dependency=dep, source_kind='simulated_previous' if dep else 'observed_previous',
                    survey_entry_status='returning', core_entry_status='continued_core' if month == '202506' else 'first_core_appearance',
                    logical_reuse_key=f'{month}|a|{repeat}|' + ('initial' if month == '202505' else arm)))
    p = dict(months=['202505', '202506'], planned_calls=6, model='test-model', expected_provider='test-provider',
             max_tokens=1024, max_prompt_bytes=10000, max_prompt_chars=10000,
             price_input_per_mtok=.259, price_output_per_mtok=.8, budget_cap_usd=1.,
             technical_gate=dict(calls=2, minimum_usable=2), concurrency_stages=[dict(after_completed=0, workers=2)])
    return p, nodes, inputs


def reply(point=4., provider='test-provider'):
    return dict(returned_model='test-model', returned_provider=provider, finish_reason='stop',
                raw_response_text=json.dumps(dict(point_pct=point, q9={f'bin{i}': 10 for i in range(1, 11)})),
                api_reported_cost_usd=.0001)


class ExecutionTests(unittest.TestCase):
    def test_shares_initialization_only_within_repeat_and_uses_own_chain(self):
        p, nodes, inputs = fixture(); received = []
        def send(messages):
            received.append(messages)
            return reply(point=float(len(received)))
        with TemporaryDirectory() as temp:
            folder = Path(temp) / 'calls'; receipt = execute(p, nodes, inputs, folder, send)
            rows = [json.loads(line) for line in (folder / 'positions_private.jsonl').read_text().splitlines()]
            index = {node_key(r): r for r in rows}
            self.assertEqual(receipt['attempts'], 6)
            self.assertEqual(receipt['logical_positions'], 8)
            for rep in [1, 2]:
                prior = index[f'202505|a|{rep}|simulated_history']['state_after']
                later = index[f'202506|a|{rep}|simulated_history']['state_before']
                self.assertEqual(prior, later)
                self.assertEqual(index[f'202506|a|{rep}|observed_history']['state_before']['fields']['q8']['value'], 7.)
            self.assertNotEqual(index['202505|a|1|simulated_history']['state_after']['fields']['q8']['value'],
                                index['202505|a|2|simulated_history']['state_after']['fields']['q8']['value'])
            with self.assertRaises(ValueError): execute(p, nodes, inputs, folder, send)

    def test_provider_mismatch_stops_and_does_not_retry(self):
        p, nodes, inputs = fixture(); received = []
        def send(messages): received.append(messages); return reply(provider='wrong')
        with TemporaryDirectory() as temp:
            folder = Path(temp) / 'calls'; receipt = execute(p, nodes, inputs, folder, send)
            self.assertEqual(len(received), 2)
            self.assertEqual(receipt['status'], 'stopped_no_retry')
            self.assertEqual(receipt['automatic_retries'], 0)
            rows = [json.loads(line) for line in (folder / 'positions_private.jsonl').read_text().splitlines()]
            self.assertTrue(all(not r['state_after']['transition']['field_updated_from_model']['q8'] for r in rows))

    def test_budget_is_checked_before_submission_and_reserves_unknown_cost(self):
        p, nodes, inputs = fixture(); p['budget_cap_usd'] = .00001; received = []
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'reservation exceeds cap'):
                execute(p, nodes, inputs, Path(temp) / 'calls', lambda m: received.append(m))
            self.assertEqual(received, [])
        p['budget_cap_usd'] = 1.
        def unknown(messages): result = reply(); result['api_reported_cost_usd'] = None; return result
        with TemporaryDirectory() as temp:
            receipt = execute(p, nodes, inputs, Path(temp) / 'calls', unknown)
            self.assertGreater(receipt['spent_or_reserved_usd'], 0)
            self.assertEqual(receipt['reported_cost_usd'], 0)
        self.assertLess(912 * reserve(dict(price_input_per_mtok=.259, price_output_per_mtok=.8, max_tokens=1024), 16744), 5.)

    def test_explicit_authorization_required_before_live_client(self):
        p, _, _ = fixture(); p.update(destination='fixed', route='locked')
        with TemporaryDirectory() as temp:
            folder = Path(temp); (folder / 'protocol.json').write_text(json.dumps(p))
            from studies.sce_inflation_expectations.experiments.frozen_batch import sha
            (folder / 'manifest.json').write_text(json.dumps(dict(protocol_sha256=sha(folder / 'protocol.json'), source_sha256={})))
            (folder / 'authorization.json').write_text(json.dumps({**{k: p[k] for k in
                ('planned_calls', 'budget_cap_usd', 'destination', 'model', 'route')}, 'approved': False}))
            with self.assertRaisesRegex(ValueError, 'Exact protocol authorization'): run(folder, folder / 'calls')

    def test_opt_in_rolling_budget_can_complete_below_full_reservation(self):
        p,nodes,inputs=fixture()
        # One maximum-sized request fits; six maximum-sized requests do not.
        p.update(budget_mode='spent_plus_inflight_reservation',budget_cap_usd=.006)
        with TemporaryDirectory() as temp:
            receipt=execute(p,nodes,inputs,Path(temp)/'calls',lambda m:reply(),engineering_only=True)
            self.assertEqual(receipt['attempts'],6)
            self.assertEqual(receipt['status'],'completed')
            self.assertGreater(receipt['remaining_worst_case_at_start_usd'],p['budget_cap_usd'])
            self.assertLessEqual(receipt['spent_or_reserved_usd'],p['budget_cap_usd'])

    def test_rolling_budget_preserves_unknown_charge_and_stops_before_excess(self):
        p,nodes,inputs=fixture()
        p.update(budget_mode='spent_plus_inflight_reservation',budget_cap_usd=.003)
        def unknown(messages):
            result=reply();result['api_reported_cost_usd']=None;return result
        with TemporaryDirectory() as temp:
            receipt=execute(p,nodes,inputs,Path(temp)/'calls',unknown,engineering_only=True)
            self.assertLess(receipt['attempts'],6)
            self.assertLessEqual(receipt['spent_or_reserved_usd'],p['budget_cap_usd'])
            self.assertEqual(receipt['automatic_retries'],0)
            self.assertIn('cap',receipt['halt_reason'])

    def test_size_overflow_sends_nothing(self):
        p, nodes, inputs = fixture(); p['max_prompt_bytes'] = 1; received = []
        with TemporaryDirectory() as temp:
            receipt = execute(p, nodes, inputs, Path(temp) / 'calls', lambda m: received.append(m))
            self.assertEqual(receipt['attempts'], 0); self.assertEqual(received, [])

    def test_continuation_skips_every_old_attempt_and_preserves_state_dependencies(self):
        p, nodes, inputs = fixture()
        with TemporaryDirectory() as temp:
            root=Path(temp)
            execute(p,nodes,inputs,root/'first',lambda m:reply(9.))
            old=[json.loads(s) for s in (root/'first'/'calls_private.jsonl').read_text().splitlines()][:2]
            seen=[]
            def send(messages):seen.append(messages);return reply(4.)
            receipt=execute(p,nodes,inputs,root/'next',send,completed_calls=old)
            fresh=[json.loads(s) for s in (root/'next'/'calls_private.jsonl').read_text().splitlines()]
            self.assertEqual(receipt['attempts'],4);self.assertEqual(receipt['logical_positions'],8)
            self.assertEqual(len(seen),4)
            self.assertFalse({r['reuse_key'] for r in old}&{r['reuse_key'] for r in fresh})
            self.assertTrue(all(r['state_before']['fields']['q8']['value']==9.
                for r in fresh if r['nodes'][0]['arm']=='simulated_history'))


class EvaluationTests(unittest.TestCase):
    def test_independent_q8_q9_and_explicit_retained_input(self):
        p, nodes, inputs = fixture(); positions = []; truths = []
        for month in p['months']:
            state = inputs[month, 'a'][1]; prior = field_view(state)
            truths.append(dict(month=int(month), agent_id='a', survey_weight=2., raw_survey_weight=1., inclusion_probability=.5,
                real=dict(q9_mean=prior['mean'], q9_iqr=prior['iqr'], q9_zero_deflation=prior['zero_deflation'],
                          q9_bins=[10.] * 10, q8_point=5., previous_q9_mean=prior['mean']),
                monthly_past_reference=prior, genuinely_observed_previous_q9=True, genuinely_observed_previous_q8=True))
        for n in nodes:
            state = inputs[n['month'], 'a'][1]
            raw = json.dumps(dict(point_pct=5., q9={f'bin{i}': 0 for i in range(1, 11)}))
            after = advance_state(state, raw, n['month'], inputs[n['month'], 'a'][2]['as_of'])
            positions.append({**n, 'state_before': state, 'state_after': after})
        actual, operational, quality = assemble_cases(nodes, positions, truths, None)
        self.assertEqual(summarize(actual, [202505, 202506], [1, 2])['q8_person_months'], 2)
        self.assertEqual(summarize(actual, [202505, 202506], [1, 2])['q9_person_months'], 0)
        self.assertEqual(summarize(operational, [202505, 202506], [1, 2])['q9_person_months'], 2)
        self.assertEqual(quality['simulated_history:q9_retained_input'], 4)
        for row in operational:
            if row['month'] == 202505: row['arms']['monthly_past_reference']['mean'] = None
        result = summarize(operational, [202505, 202506], [1, 2])
        self.assertEqual(result['q9_person_months'], 2)
        self.assertEqual(result['monthly_past_reference_support']['q9_person_months'], 1)
        json.dumps(result, allow_nan=False)

    def test_unexecuted_or_duplicate_logical_positions_are_rejected(self):
        _, nodes, _ = fixture()
        with self.assertRaises(ValueError): assemble_cases(nodes, [], [], None)


if __name__ == '__main__': unittest.main()
