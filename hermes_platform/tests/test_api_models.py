import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from hermes_platform.contracts import MODEL_ROLES, PolicyError
from hermes_platform.engine import Engine
from hermes_platform.models import ModelError, Router, request, validate_route
from hermes_platform.server import handler
from hermes_platform.storage import Store
from hermes_platform.tests.support import FakeOllama, FakeRouter, OUTPUTS, body


class APIModelsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / 'state')
        self.engine = Engine(self.store, FakeRouter())
        self.token = (self.store.root / 'pairing-token').read_text()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.engine, self.token))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.engine.close(); self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def call(self, path, data=None, headers=None):
        request = urllib.request.Request(self.url + path, data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'} | (headers or {}))
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.read(), response.headers

    def test_auth_host_origin_and_unknown_routes(self):
        self.assertEqual(self.call('/api/state', headers={'Authorization': ''})[0], 401)
        self.assertEqual(self.call('/api/state', headers={'Host': 'evil.invalid'})[0], 403)
        self.assertEqual(self.call('/api/tasks', body(), {'Origin': 'https://evil.invalid'})[0], 403)
        self.assertEqual(self.call('/api/tasks/not-a-task')[0], 404)
        self.assertEqual(self.call('/../../etc/passwd')[0], 404)
        self.assertEqual(self.store.listing(), [])

    def test_api_task_lifecycle_and_stale_decision(self):
        status, raw, headers = self.call('/api/tasks', body())
        self.assertEqual(status, 201); task = json.loads(raw)
        for _ in range(6): self.engine.tick()
        status, raw, _ = self.call('/api/tasks/' + task['id']); current = json.loads(raw)
        self.assertEqual(current['status'], 'awaiting_approval')
        path = '/api/tasks/' + task['id'] + '/decision'
        decision = {'revision': current['revision'], 'action': 'approve', 'result_hash': current['result_hash']}
        self.assertEqual(self.call(path, decision)[0], 200)
        self.assertEqual(self.call(path, decision)[0], 409)
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_input_limits_and_dashboard_security_headers(self):
        self.assertEqual(self.call('/api/tasks', body(prompt='x' * 9000))[0], 409)
        self.assertEqual(self.call('/api/tasks', body() | {'path': '/private'})[0], 409)
        status, raw, headers = self.call('/')
        self.assertEqual(status, 200)
        self.assertIn('viewport', raw.decode())
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertNotIn(self.token, raw.decode())

    def test_real_ollama_protocol_all_roles_in_isolated_worker_processes(self):
        service = FakeOllama()
        try:
            self.engine.router = Router({role: dict(service.route) for role in MODEL_ROLES}, seconds=10)
            task = self.engine.create(body())
            for _ in range(6): self.engine.tick()
            self.assertEqual(self.store.get(task['id'])['status'], 'awaiting_approval')
            self.assertEqual(len(service.calls), 5)
            self.assertTrue(all(packet['stream'] is False for packet in service.calls))
        finally:
            service.close()

    def test_cloud_authorization_checked_before_transport(self):
        routes = {role: {'provider': 'gpt', 'model': 'gpt-configured', 'endpoint': 'https://api.openai.com/v1/chat/completions', 'key_env': 'HERMES_PLATFORM_GPT_KEY'} for role in MODEL_ROLES}
        router = Router(routes)
        for consent, memory in [(False, False), (True, True)]:
            with self.assertRaises(ModelError):
                router.generate('research', {}, consent, memory, lambda: False)

    def test_cloud_wire_formats_and_no_credential_echo(self):
        for provider in ('gpt', 'claude'):
            key_name = 'HERMES_PLATFORM_GPT_KEY' if provider == 'gpt' else 'HERMES_PLATFORM_CLAUDE_KEY'
            endpoint = 'https://api.openai.com/v1/chat/completions' if provider == 'gpt' else 'https://api.anthropic.com/v1/messages'
            route = {'provider': provider, 'model': provider + '-configured', 'endpoint': endpoint, 'key_env': key_name}
            content = json.dumps(OUTPUTS['research'])
            reply = ({'model': route['model'], 'choices': [{'finish_reason': 'stop', 'message': {'content': content}}]} if provider == 'gpt' else
                     {'model': route['model'], 'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': content}]})
            class Opener:
                def open(self, req, timeout):
                    packet = json.loads(req.data)
                    assert packet['model'] == route['model']
                    assert 'tools' not in packet
                    assert req.full_url == endpoint
                    return io.BytesIO(json.dumps(reply).encode())
            with patch.dict(os.environ, {key_name: 'synthetic-transport-key'}), patch('urllib.request.build_opener', return_value=Opener()):
                self.assertEqual(request(route, 'research', {}, 5), OUTPUTS['research'])

    def test_cloud_errors_echo_and_model_substitution_fail_closed(self):
        route = {'provider': 'gpt', 'model': 'gpt-pinned', 'endpoint': 'https://api.openai.com/v1/chat/completions', 'key_env': 'HERMES_PLATFORM_GPT_KEY'}
        key = 'synthetic-cloud-fixture'
        class Opener:
            def open(self, req, timeout):
                return io.BytesIO(json.dumps(reply).encode())
        for reply in [
            {'model': 'other-model', 'choices': [{'finish_reason': 'stop', 'message': {'content': '{}'}}]},
            {'model': 'gpt-pinned', 'choices': [{'finish_reason': 'stop', 'message': {'content': key}}]},
            {'model': 'gpt-pinned', 'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]},
        ]:
            with patch.dict(os.environ, {'HERMES_PLATFORM_GPT_KEY': key}), patch('urllib.request.build_opener', return_value=Opener()), self.assertRaises(ModelError):
                request(route, 'research', {}, 5)

    def test_redirect_and_oversized_response_rejected(self):
        from hermes_platform.models import NoRedirect
        with self.assertRaises(ModelError):
            NoRedirect().redirect_request(None, None, None, None, None, None)
        class Opener:
            def open(self, req, timeout):
                return io.BytesIO(b'x' * 262145)
        route = {'provider': 'ollama', 'model': 'qwen', 'endpoint': 'http://127.0.0.1:11434', 'key_env': None}
        with patch('urllib.request.build_opener', return_value=Opener()), self.assertRaises(ModelError):
            request(route, 'research', {}, 5)

    def test_deadline_terminates_owned_model_worker(self):
        import multiprocessing
        import time
        from http.server import BaseHTTPRequestHandler
        class SlowHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                time.sleep(3)
            def log_message(self, *args):
                pass
        slow = ThreadingHTTPServer(('127.0.0.1', 0), SlowHandler)
        slow.daemon_threads = True
        thread = threading.Thread(target=slow.serve_forever, daemon=True); thread.start()
        route = {'provider': 'ollama', 'model': 'qwen', 'endpoint': f'http://127.0.0.1:{slow.server_port}', 'key_env': None}
        router = Router({role: dict(route) for role in MODEL_ROLES}, seconds=1)
        before = {p.pid for p in multiprocessing.active_children()}
        started = time.monotonic()
        try:
            with self.assertRaises(ModelError):
                router.generate('research', {}, False, False, lambda: False)
            self.assertLess(time.monotonic() - started, 2.5)
            self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)
            with self.assertRaises(ModelError):
                router.generate('research', {}, False, False, lambda: True)
        finally:
            slow.shutdown(); slow.server_close(); thread.join()

    def test_route_validation_rejects_remote_local_endpoint(self):
        for url in ['http://remote.invalid:11434', 'http://127.0.0.1:11434/path', 'http://' + 'synthetic:fixture' + '@localhost:11434']:
            with self.assertRaises(PolicyError):
                validate_route({'provider': 'ollama', 'model': 'qwen', 'endpoint': url, 'key_env': None})

    def test_phone_budget_is_not_silently_capped_at_thirty_seconds(self):
        route = {'provider': 'ollama', 'model': 'android-1b:latest', 'endpoint': 'http://127.0.0.1:11434', 'key_env': None}
        reply = {'model': route['model'], 'done': True,
                 'message': {'content': json.dumps(OUTPUTS['research'])}}
        class Opener:
            def open(inner, req, timeout):
                self.assertEqual(timeout, 120)
                return io.BytesIO(json.dumps(reply).encode())
        with patch('urllib.request.build_opener', return_value=Opener()):
            self.assertEqual(request(route, 'research', {}, 120), OUTPUTS['research'])

    def test_transport_diagnostics_are_distinct_and_do_not_leak_error_text(self):
        import errno
        route = {'provider': 'ollama', 'model': 'qwen', 'endpoint': 'http://127.0.0.1:11434', 'key_env': None}
        cases = [(TimeoutError('synthetic-private-detail'), 'transport_timeout'),
                 (urllib.error.URLError(TimeoutError()), 'transport_timeout'),
                 (urllib.error.URLError(ConnectionRefusedError(errno.ECONNREFUSED, 'synthetic-private-detail')), 'connection_refused'),
                 (OSError(errno.EHOSTUNREACH, 'synthetic-private-detail'), 'network_unreachable'),
                 (urllib.error.URLError('synthetic-private-detail'), 'transport_unavailable')]
        for error, expected in cases:
            with self.subTest(expected=expected):
                class Opener:
                    def open(inner, req, timeout):
                        raise error
                with patch('urllib.request.build_opener', return_value=Opener()), self.assertRaises(ModelError) as caught:
                    request(route, 'research', {}, 5)
                self.assertEqual(caught.exception.code, expected)
                self.assertTrue(caught.exception.retryable)
                self.assertNotIn('synthetic-private-detail', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
