"""No-network synthetic model-assistance policy tests."""
import copy
import io
import json
import urllib.error
from unittest.mock import patch
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from model_assist import FIELDS, MODEL, PolicyError, SyntheticSkillAssistant, ZeroCostClient, parse_json, zero_pricing

DRAFT = {key: 'Synthetic widget ' + key + ' guidance.' for key in FIELDS}
REVIEW = {'status': 'needs_human_review', 'issues': ['AI output is not verification.'],
          'suggested_corrections': ['Check the synthetic B,A,C result manually.']}


class FixtureTransport:
    def __init__(self):
        self.calls = []
        self.prices = {'prompt': '0', 'completion': '0'}
        self.endpoint = {'status': 0, 'pricing': dict(self.prices), 'context_length': 256000,
                         'supported_parameters': ['max_tokens', 'reasoning', 'temperature'], 'tag': 'synthetic-fixture'}
        self.responses = [DRAFT, REVIEW]
        self.cost = 0
        self.finish = 'stop'
        self.returned_model = MODEL
        self.tool_calls = []

    def __call__(self, path, body=None):
        self.calls.append((path, copy.deepcopy(body)))
        if path == '/models':
            return {'data': [{'id': MODEL, 'pricing': self.prices}]}
        if path.endswith('/endpoints'):
            return {'data': {'endpoints': [self.endpoint]}}
        self.assert_completion_path(path)
        return {'model': self.returned_model, 'usage': {'cost': self.cost},
                'choices': [{'finish_reason': self.finish, 'message': {
                    'content': json.dumps(self.responses.pop(0)), 'tool_calls': self.tool_calls}}]}

    @staticmethod
    def assert_completion_path(path):
        if path != '/chat/completions':
            raise AssertionError('Unexpected network shape')


class SyntheticModelPolicyTests(unittest.TestCase):
    def client(self, transport):
        return ZeroCostClient('synthetic-credential-only', request=transport)

    def test_complete_fixed_fixture_and_unapproved_staging_body(self):
        transport = FixtureTransport(); client = self.client(transport)
        assistant = SyntheticSkillAssistant(client); assistant.draft(); assistant.review()
        body = assistant.staging_body()
        self.assertEqual(set(body), set(FIELDS))
        self.assertIn('UNVERIFIED', body['trigger'])
        self.assertIn('No automatic execution', body['permissions'])
        self.assertIn('not success evidence', body['risks'])
        self.assertEqual(client.costs, ['0', '0'])
        self.assertEqual(sum(path == '/models' for path, _ in transport.calls), 2)
        for path, request in transport.calls:
            if path != '/chat/completions':
                continue
            self.assertEqual(request['model'], MODEL)
            self.assertEqual(request['provider']['max_price'], {'prompt': 0, 'completion': 0})
            self.assertFalse(request['provider']['allow_fallbacks'])
            self.assertTrue(request['provider']['require_parameters'])
            self.assertNotIn('tools', request)
            self.assertNotIn('synthetic-credential-only', json.dumps(request))

    def test_all_price_dimensions_must_be_explicitly_zero(self):
        for pricing in (None, {}, {'prompt': 0}, {'prompt': 0, 'completion': 0, 'request': '0.01'},
                        {'prompt': 'NaN', 'completion': 0}, {'prompt': '-1', 'completion': 0},
                        {'prompt': 'Infinity', 'completion': 0}, {'prompt': None, 'completion': 0}):
            with self.subTest(pricing='generated canary'):
                self.assertFalse(zero_pricing(pricing))
        self.assertTrue(zero_pricing({'prompt': '0', 'completion': '0', 'request': 0, 'discount': 0}))

    def test_paid_catalog_rejected_before_completion(self):
        transport = FixtureTransport(); transport.prices['request'] = '0.01'
        with self.assertRaises(PolicyError):
            SyntheticSkillAssistant(self.client(transport)).draft()
        self.assertFalse(any(path == '/chat/completions' for path, _ in transport.calls))

    def test_malformed_or_paid_endpoint_rejected_before_completion(self):
        cases = [('pricing', {'prompt': 0, 'completion': 0, 'image': 1}),
                 ('status', False), ('status', 1), ('context_length', True),
                 ('context_length', 100), ('supported_parameters', 'max_tokens reasoning temperature'),
                 ('supported_parameters', ['max_tokens', None]), ('tag', '')]
        for name, value in cases:
            with self.subTest(field=name):
                transport = FixtureTransport(); transport.endpoint[name] = value
                with self.assertRaises(PolicyError):
                    SyntheticSkillAssistant(self.client(transport)).draft()
                self.assertFalse(any(path == '/chat/completions' for path, _ in transport.calls))

    def test_nonzero_unknown_cost_or_unexpected_response_rejected(self):
        for field, value in [('cost', '0.001'), ('cost', None), ('cost', 'NaN'),
                             ('returned_model', 'unexpected-paid-model'), ('finish', 'length'),
                             ('tool_calls', [{'name': 'never_execute'}])]:
            with self.subTest(field=field):
                transport = FixtureTransport(); setattr(transport, field, value)
                with self.assertRaises(PolicyError):
                    SyntheticSkillAssistant(self.client(transport)).draft()

    def test_draft_schema_and_sensitive_looking_text_rejected(self):
        for body in ({}, {**DRAFT, 'extra': 'not allowed'}, {**DRAFT, 'method': []},
                     {**DRAFT, 'method': 'x' * 601}, {**DRAFT, 'method': 'fixture@example.com'},
                     {**DRAFT, 'method': 'https://example.invalid'},
                     {**DRAFT, 'method': 'password=' + 'SYNTHETIC_VALUE'}):
            transport = FixtureTransport(); transport.responses = [body]
            with self.subTest(fixture='invalid generated response'), self.assertRaises(PolicyError):
                SyntheticSkillAssistant(self.client(transport)).draft()

    def test_review_cannot_be_auto_approved(self):
        for review in ({**REVIEW, 'status': 'approved'}, {**REVIEW, 'issues': 'not a list'},
                       {**REVIEW, 'issues': ['x'] * 7}, {**REVIEW, 'issues': ['x' * 301]}):
            transport = FixtureTransport(); transport.responses = [DRAFT, review]
            assistant = SyntheticSkillAssistant(self.client(transport)); assistant.draft()
            with self.assertRaises(PolicyError):
                assistant.review()
            with self.assertRaises(PolicyError):
                assistant.staging_body()

    def test_no_arbitrary_private_input_interface(self):
        transport = FixtureTransport(); assistant = SyntheticSkillAssistant(self.client(transport))
        with self.assertRaises(TypeError):
            assistant.draft('PRIVATE_CANARY_NEVER_SEND')
        with self.assertRaises(PolicyError):
            assistant.review()
        self.assertEqual(transport.calls, [])

    def test_returned_mutable_objects_cannot_change_cached_cloud_input(self):
        transport = FixtureTransport(); assistant = SyntheticSkillAssistant(self.client(transport))
        body = assistant.draft(); body['method'] = 'PRIVATE_CANARY_NEVER_SEND'
        review = assistant.review(); review['issues'].append('PRIVATE_CANARY_NEVER_SEND')
        self.assertNotIn('PRIVATE_CANARY_NEVER_SEND', json.dumps(transport.calls))
        self.assertNotIn('PRIVATE_CANARY_NEVER_SEND', assistant.staging_body()['risks'])

    def test_failed_new_generation_clears_stale_review(self):
        transport = FixtureTransport(); assistant = SyntheticSkillAssistant(self.client(transport))
        assistant.draft(); assistant.review(); transport.responses = [{}]
        with self.assertRaises(PolicyError):
            assistant.draft()
        with self.assertRaises(PolicyError):
            assistant.staging_body()

    def test_credential_echo_rejected_without_output(self):
        transport = FixtureTransport(); transport.responses = [{**DRAFT, 'method': 'synthetic-credential-only'}]
        with self.assertRaisesRegex(PolicyError, '^Credential echo refused$'):
            SyntheticSkillAssistant(self.client(transport)).draft()

    def test_privacy_rejection_is_safe_and_not_retried(self):
        client = ZeroCostClient('synthetic-credential-only')
        error = urllib.error.HTTPError('https://example.invalid', 404, 'generated error', {},
                                      io.BytesIO(b'No endpoints matching data policy. PRIVATE_CANARY_NEVER_EMIT'))
        with patch.object(client._opener, 'open', side_effect=error) as opening:
            with self.assertRaises(PolicyError) as captured:
                client._json('/chat/completions', {'synthetic': True})
        self.assertIn('privacy/data-policy restriction', str(captured.exception))
        self.assertNotIn('PRIVATE_CANARY_NEVER_EMIT', str(captured.exception))
        self.assertNotIn('synthetic-credential-only', str(captured.exception))
        self.assertEqual(opening.call_count, 1)

    def test_redirects_cannot_forward_credentials(self):
        from model_assist import _NoRedirect
        with self.assertRaisesRegex(PolicyError, 'redirects refused'):
            _NoRedirect().redirect_request(None, None, None, None, None, None)

    def test_json_never_evaluates_code_or_accepts_partial_output(self):
        for value in ('[]', 'not JSON', '```python\nprint(1)\n```', '{"partial":'):
            with self.subTest(fixture='invalid JSON'), self.assertRaises(PolicyError):
                parse_json(value)
        self.assertEqual(parse_json('```json\n{"synthetic":true}\n```'), {'synthetic': True})


class ModelWorkbenchTests(unittest.TestCase):
    def configured(self):
        from model_assist import ModelAssistWorkbench
        transport = FixtureTransport()
        assistant = SyntheticSkillAssistant(ZeroCostClient('synthetic-credential-only', request=transport))
        return ModelAssistWorkbench(assistant), transport

    def test_disabled_by_default(self):
        from model_assist import ModelAssistWorkbench, FIXTURE
        workbench = ModelAssistWorkbench()
        self.assertFalse(workbench.status()['configured'])
        with self.assertRaises(PolicyError):
            workbench.perform('draft', {'fixture': FIXTURE, 'confirm': True})

    def test_new_draft_review_adoption_never_saves_or_approves(self):
        from model_assist import FIXTURE
        workbench, transport = self.configured()
        draft = workbench.perform('draft', {'fixture': FIXTURE, 'confirm': True})
        request = {'draft_id': draft['draft_id'], 'hash': draft['hash'], 'confirm': True}
        with self.assertRaises(PolicyError):
            workbench.perform('suggestion', request)
        review = workbench.perform('review', request)
        suggestion = workbench.perform('suggestion', request)
        for row in (draft, review, suggestion):
            self.assertFalse(row['saved']); self.assertFalse(row['approved']); self.assertFalse(row['verified'])
        self.assertIn('UNVERIFIED', suggestion['body']['trigger'])
        self.assertEqual(sum(path == '/chat/completions' for path, _ in transport.calls), 2)
        self.assertTrue(workbench.status()['test_transport'])
        self.assertFalse(workbench.status()['normal_chat_enabled'])

    def test_private_or_unconfirmed_input_rejected_before_model_calls(self):
        from model_assist import FIXTURE
        for request in (None, [], {'fixture': FIXTURE, 'confirm': True, 'prompt': 'PRIVATE_CANARY'},
                        {'fixture': 'private-file', 'confirm': True}, {'fixture': FIXTURE, 'confirm': 1},
                        {'fixture': FIXTURE, 'confirm': False}):
            workbench, transport = self.configured()
            with self.assertRaises(PolicyError):
                workbench.perform('draft', request)
            self.assertEqual(transport.calls, [])

    def test_stale_identity_or_hash_cannot_review(self):
        from model_assist import FIXTURE
        workbench, transport = self.configured()
        draft = workbench.perform('draft', {'fixture': FIXTURE, 'confirm': True})
        before = len(transport.calls)
        for id, hash in (('stale', draft['hash']), (draft['draft_id'], 'wrong-hash')):
            with self.assertRaises(PolicyError):
                workbench.perform('review', {'draft_id': id, 'hash': hash, 'confirm': True})
        self.assertEqual(len(transport.calls), before)

    def test_busy_operation_is_not_queued(self):
        from model_assist import FIXTURE
        workbench, transport = self.configured(); workbench._lock.acquire()
        try:
            with self.assertRaisesRegex(PolicyError, 'already running'):
                workbench.perform('draft', {'fixture': FIXTURE, 'confirm': True})
        finally:
            workbench._lock.release()
        self.assertEqual(transport.calls, [])

    def test_unexpected_errors_never_echo_raw_data(self):
        from model_assist import FIXTURE
        workbench, _ = self.configured()
        with patch.object(workbench._assistant, 'draft', side_effect=RuntimeError('PRIVATE_CANARY_NEVER_EMIT')):
            with self.assertRaises(PolicyError) as caught:
                workbench.perform('draft', {'fixture': FIXTURE, 'confirm': True})
        self.assertNotIn('PRIVATE_CANARY_NEVER_EMIT', str(caught.exception))
        self.assertEqual(workbench.status()['state'], 'request-blocked')


class ExplicitCredentialTests(unittest.TestCase):
    def test_private_key_field_only_and_no_environment_loading(self):
        import tempfile
        from model_assist import load_approved_credential
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fixture.env'
            path.write_text('OPENROUTER_API_KEY=synthetic-credential-only\nIGNORED_SYNTHETIC=not-an-env-import\n')
            path.chmod(0o600)
            self.assertEqual(load_approved_credential(path), 'synthetic-credential-only')

    def test_public_alias_duplicate_or_invalid_key_file_refused(self):
        import tempfile
        from model_assist import load_approved_credential
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'fixture.env'
            for text, mode in [('OPENROUTER_API_KEY=synthetic-credential-only\n', 0o644),
                               ('UNRELATED_SYNTHETIC=not-a-key\n', 0o600),
                               ('OPENROUTER_API_KEY=synthetic-one\nOPENROUTER_API_KEY=synthetic-two\n', 0o600),
                               ('OPENROUTER_API_KEY="synthetic invalid whitespace"\n', 0o600)]:
                path.write_text(text); path.chmod(mode)
                with self.assertRaises(PolicyError):
                    load_approved_credential(path)
            alias = Path(temporary) / 'alias.env'; alias.symlink_to(path)
            with self.assertRaises(PolicyError):
                load_approved_credential(alias)


if __name__ == '__main__':
    unittest.main(verbosity=2)
