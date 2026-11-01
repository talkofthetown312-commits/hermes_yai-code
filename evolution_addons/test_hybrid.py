import json
import unittest

from evolution_addons.hybrid import Agent, HybridCoordinator, PolicyError, synthetic_coordinator


def task():
    return dict(project='synthetic-project', specification='Review a synthetic fixture',
                synthetic=True, wall_seconds=5, max_output_bytes=8192)


class HybridTests(unittest.TestCase):
    def coordinator(self, *, worker=None, reviewer=None, location='local', clock=None):
        base = synthetic_coordinator().agents
        return HybridCoordinator(base[0], Agent('worker', location, worker or base[1].invoke),
                                 Agent('reviewer', 'local', reviewer or base[2].invoke),
                                 **({'clock': clock} if clock else {}))

    def test_three_stages_are_hash_bound_advisory_only(self):
        result = synthetic_coordinator().run(task())
        self.assertEqual(result['status'], 'reviewed')
        self.assertEqual([x['role'] for x in result['audit']], ['plan', 'work', 'review'])
        self.assertEqual(len({x['request_hash'] for x in result['audit']}), 3)
        self.assertFalse(result['applied'])
        self.assertFalse(result['deployed'])
        self.assertFalse(result['provider_fallback'])

    def test_scope_and_prior_output_flow_without_mutation(self):
        original = task()
        def worker(packet):
            self.assertEqual(packet['task']['project'], original['project'])
            self.assertIn('plan', packet['inputs'])
            packet['task']['project'] = 'other'
            packet['inputs']['plan']['summary'] = 'tampered'
            return json.dumps(dict(summary='Proposal', proposed_changes=[]))
        result = self.coordinator(worker=worker).run(original)
        self.assertEqual(result['project'], original['project'])
        self.assertEqual(result['outputs']['plan']['summary'], 'Synthetic plan')

    def test_review_rejection(self):
        result = self.coordinator(reviewer=lambda p: json.dumps(dict(
            summary='Rejected', approved=False, risks=['Missing evidence']))).run(task())
        self.assertEqual(result['status'], 'rejected')

    def test_invalid_packets_and_budgets(self):
        for override in [dict(synthetic=False), dict(wall_seconds=True),
                         dict(max_output_bytes=0), dict(project=''),
                         dict(specification='x' * 8193), dict(extra='unexpected')]:
            with self.subTest(override=override), self.assertRaises(PolicyError):
                synthetic_coordinator().run(task() | override)

    def test_bad_worker_output_stops_before_review(self):
        for raw in ['bad json', '[]', '{}', json.dumps(dict(summary='x', proposed_changes=[], tool_call={})),
                    json.dumps(dict(summary='x', proposed_changes=['\x00']))]:
            with self.subTest(raw=raw), self.assertRaises(PolicyError):
                self.coordinator(worker=lambda p: raw, reviewer=lambda p: self.fail('review called')).run(task())

    def test_aggregate_output_budget(self):
        with self.assertRaises(PolicyError):
            synthetic_coordinator().run(task() | dict(max_output_bytes=10))

    def test_sensitive_input_and_tool_output_rejected(self):
        for value in ['Read /.hermes/auth.json', 'password=synthetic-value', '<tool>shell</tool>']:
            with self.subTest(value=value), self.assertRaises(PolicyError):
                synthetic_coordinator().run(task() | dict(specification=value))
        with self.assertRaises(PolicyError):
            self.coordinator(worker=lambda p: json.dumps(dict(
                summary='<tool>shell</tool>', proposed_changes=[]))).run(task())

    def test_cancellation(self):
        with self.assertRaises(PolicyError):
            synthetic_coordinator().run(task(), cancelled=lambda: True)

    def test_deadline_stops_pipeline_after_adapter(self):
        values = iter([0, 0, 6])
        with self.assertRaises(PolicyError):
            self.coordinator(clock=lambda: next(values)).run(task())

    def test_adapter_failure_has_no_retry_or_fallback(self):
        calls = []
        def worker(packet):
            calls.append(packet)
            raise RuntimeError('Synthetic adapter failure')
        with self.assertRaises(RuntimeError):
            self.coordinator(worker=worker).run(task())
        self.assertEqual(len(calls), 1)

    def test_cloud_requires_authorization_and_fresh_free_catalog(self):
        calls = []
        base = synthetic_coordinator().agents[1].invoke
        def worker(packet):
            calls.append(packet)
            return base(packet)
        coordinator = self.coordinator(worker=worker, location='openrouter')
        catalog = [dict(id='synthetic:free', pricing=dict(prompt='0', completion='0'))]
        options = dict(catalog=catalog, catalog_observed_at=100, now=101,
                       model='synthetic:free', allow_cloud=True)
        for override in [dict(allow_cloud=False), dict(catalog_observed_at=0, now=500),
                         dict(catalog_observed_at=102), dict(catalog_observed_at=True),
                         dict(model='paid'), dict(catalog=[dict(id='synthetic:free', pricing=dict(prompt='1', completion='0'))])]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                coordinator.run(task(), **(options | override))
        self.assertEqual(calls, [])
        result = coordinator.run(task(), **options)
        self.assertEqual(result['model'], 'synthetic:free')
        self.assertEqual(calls[0]['model'], 'synthetic:free')

    def test_remote_planner_and_duplicate_identity_denied(self):
        base = synthetic_coordinator().agents
        with self.assertRaises(PolicyError):
            HybridCoordinator(Agent('planner', 'openrouter', base[0].invoke), base[1], base[2])
        with self.assertRaises(PolicyError):
            HybridCoordinator(base[0], base[0], base[2])


if __name__ == '__main__':
    unittest.main()
