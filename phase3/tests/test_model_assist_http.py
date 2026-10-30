"""Real localhost HTTP/UI with an explicitly injected no-network model transport."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import unittest
from urllib.parse import urlsplit

import test_integration as fixtures
from model_assist import FIXTURE

PHASE = Path(__file__).resolve().parents[1]


class ModelAssistHTTPTests(unittest.TestCase):
    setUp = fixtures.IntegrationTest.setUp
    tearDown = fixtures.IntegrationTest.tearDown
    stop = fixtures.IntegrationTest.stop
    request = fixtures.IntegrationTest.request
    get = fixtures.IntegrationTest.get
    post = fixtures.IntegrationTest.post

    def start(self):
        keyfile = self.root / 'synthetic-key.env'
        keyfile.write_text('OPENROUTER_API_KEY=synthetic-credential-only\n')
        keyfile.chmod(0o600)
        wrapper = (
            'import sys; '
            'sys.path[:0]=[' + repr(str(PHASE)) + ',' + repr(str(PHASE / 'tests')) + ']; '
            'import model_assist; from test_model_assist import FixtureTransport; '
            'OriginalClient=model_assist.ZeroCostClient; '
            'model_assist.ZeroCostClient=lambda key:OriginalClient(key, request=FixtureTransport()); '
            'import serve; serve.main()')
        self.log = (self.root / 'server.log').open('w')
        self.server = subprocess.Popen(
            [sys.executable, '-B', '-c', wrapper, '--state-dir', str(self.state), '--port', '0',
             '--enable-synthetic-cloud', '--synthetic-cloud-key-file', str(keyfile)],
            stdout=subprocess.PIPE, stderr=self.log, text=True,
            env={'PATH': os.environ.get('PATH', ''), 'HOME': str(self.root), 'PYTHONDONTWRITEBYTECODE': '1'})
        if not select.select([self.server.stdout], [], [], 15)[0]:
            self.fail('Test server readiness timeout')
        line = self.server.stdout.readline().strip()
        self.assertTrue(line.startswith('Phase 3 staging ready: '), 'Test server failed; inspect private log')
        self.url = line.split('ready: ', 1)[1].rstrip('/')
        self.assertNotIn(urlsplit(self.url).port, (8766, 8877, 8893, 8894))
        self.key = (self.state / 'app/data/pairing-token').read_text().strip()

    def test_protected_draft_review_suggestion_without_skill_mutation(self):
        status = self.get('integration/model-assist')
        self.assertTrue(status['configured'])
        self.assertTrue(status['test_transport'])
        before = self.get('integration/dashboard')
        draft = self.post('integration/model-assist/draft', {'fixture': FIXTURE, 'confirm': True})
        request = {'draft_id': draft['draft_id'], 'hash': draft['hash'], 'confirm': True}
        self.post('integration/model-assist/suggestion', request, status=409)
        review = self.post('integration/model-assist/review', request)
        suggestion = self.post('integration/model-assist/suggestion', request)
        self.assertEqual(review['review']['status'], 'needs_human_review')
        self.assertIn('UNVERIFIED', suggestion['body']['trigger'])
        for response in (draft, review, suggestion):
            self.assertFalse(response['saved']); self.assertFalse(response['approved']); self.assertFalse(response['verified'])
        after = self.get('integration/dashboard')
        for key in ('skills', 'audit_events', 'granted_sources', 'preferences'):
            self.assertEqual(before[key], after[key])
        self.assertFalse(self.get('status')['ready'])

    def test_auth_origin_and_private_payload_rejection(self):
        endpoint = '/api/integration/model-assist/draft'
        body = {'fixture': FIXTURE, 'confirm': True}
        self.assertEqual(self.request(endpoint, body, auth=False)[0], 401)
        self.assertEqual(self.request(endpoint, body, origin='https://example.invalid')[0], 403)
        self.post('integration/model-assist/draft', {**body, 'prompt': 'PRIVATE_CANARY_NEVER_SEND'}, status=409)
        self.post('integration/model-assist/draft', {**body, 'confirm': False}, status=409)
        self.post('integration/model-assist/draft', {'fixture': 'private-file', 'confirm': True}, status=409)
        self.post('integration/model-assist/review', {'draft_id': 'stale', 'hash': 'stale', 'confirm': True}, status=409)
        self.assertEqual(self.get('integration/model-assist')['state'], 'configured-unverified')

    def test_opt_in_banner_and_script(self):
        _, page, _ = self.request('/', auth=False, raw=True)
        self.assertIn('synthetic AI assist is opt-in', page)
        _, script, _ = self.request('/integration.js', auth=False, raw=True)
        self.assertIn('Draft synthetic skill with free model', script)
        self.assertIn('Use AI suggestion in unsaved form', script)

    def test_simulated_ui_against_protected_http_with_fake_model(self):
        process = subprocess.run(['node', str(PHASE / 'tests/test_ui.cjs')],
                                 env={'PATH': os.environ.get('PATH', ''), 'FIXTURE_URL': self.url,
                                      'FIXTURE_PAIRING': self.key, 'FIXTURE_AI_MODE': 'enabled'},
                                 capture_output=True, text=True, timeout=45)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        report = json.loads(process.stdout)
        self.assertFalse(report['native_android_verified'])
        self.assertEqual(report['model_transport'], 'FAKE_FOR_TESTS')
        self.assertGreaterEqual(report['assertions'], 40)
        print('Synthetic AI UI assertions:', report['assertions'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
