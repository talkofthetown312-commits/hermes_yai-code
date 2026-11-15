"""Runtime acceptance with deterministic adapters, real HTTP/SQLite/processes."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from hermes_runtime.server import Runtime, handler
from hermes_runtime.core import Tasks, Providers, Rejected
from hermes_runtime.workflows import validate_recipe, train
from evolution import Denied, digest


def wait(tasks, project, identifier):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        value = tasks.get(project, identifier)
        if value['status'] != 'running':
            return value
        time.sleep(.02)
    raise AssertionError('Task did not finish')


def echo(value):
    return value


def block():
    time.sleep(30)


def fail():
    raise RuntimeError('password=secret12345')


class FakeProviders:
    def models(self, mode):
        return ['fixture-local' if mode == 'local' else 'fixture:free']

    def complete(self, mode, model, messages, consent):
        if mode == 'cloud' and not consent:
            raise Rejected('Cloud consent required')
        return 'Fixture response: ' + messages[-1]['content']


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = Runtime(self.root / 'runtime', {'project': 'alpha'}, FakeProviders())

    def tearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    def test_chat_durable_history(self):
        r = self.runtime
        cid = r.post('chats', {'mode': 'local', 'model': 'fixture-local'})['id']
        job = r.post('send', {'id': cid, 'message': 'Hello'})
        self.assertEqual(wait(r.tasks, 'alpha', job['id'])['status'], 'completed')
        self.assertEqual(r.chat(cid)['messages'][-1]['text'], 'Fixture response: Hello')
        self.assertEqual(len(r.chat(cid)['messages']), 2)
        r.close()
        self.runtime = Runtime(self.root / 'runtime', {'project': 'alpha'}, FakeProviders())
        self.assertEqual(len(self.runtime.chat(cid)['messages']), 2)

    def test_cloud_requires_conversation_consent(self):
        cid = self.runtime.post('chats', {'mode': 'cloud', 'model': 'fixture:free'})['id']
        with self.assertRaises(Rejected):
            self.runtime.post('send', {'id': cid, 'message': 'Private text'})
        job = self.runtime.post('send', {'id': cid, 'message': 'Synthetic text', 'conversation_consent': True})
        self.assertEqual(wait(self.runtime.tasks, 'alpha', job['id'])['status'], 'completed')

    def test_secrets_blocked_for_cloud(self):
        cid = self.runtime.post('chats', {'mode': 'cloud', 'model': 'fixture:free'})['id']
        with self.assertRaises(Rejected):
            self.runtime.post('send', {'id': cid, 'message': 'password=private12345', 'conversation_consent': True})

    def test_cancel_timeout_and_project_scope(self):
        tasks = self.runtime.tasks
        job = tasks.submit('alpha', 'fixture', block)
        with self.assertRaises(Rejected):
            tasks.get('beta', job['id'])
        tasks.cancel('alpha', job['id'])
        self.assertEqual(wait(tasks, 'alpha', job['id'])['status'], 'cancelled')
        job = tasks.submit('alpha', 'fixture', block, seconds=.1)
        self.assertEqual(wait(tasks, 'alpha', job['id'])['status'], 'timed_out')
        self.assertFalse(tasks.active)

    def test_process_failure_never_exposes_secret_exception(self):
        job = self.runtime.tasks.submit('alpha', 'fixture', fail)
        value = wait(self.runtime.tasks, 'alpha', job['id'])
        self.assertEqual(value['status'], 'failed')
        self.assertNotIn('secret12345', json.dumps(value))

    def test_restart_marks_running_tasks_interrupted(self):
        with self.runtime.tasks.db() as c:
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?)', ('stopped', 'alpha', 'test', 'running', '{}', time.time(), None))
        self.runtime.close()
        self.runtime = Runtime(self.root / 'runtime', {'project': 'alpha'}, FakeProviders())
        self.assertEqual(self.runtime.tasks.get('alpha', 'stopped')['status'], 'interrupted')

    def test_second_runtime_cannot_open_same_data(self):
        with self.assertRaises(Rejected):
            Runtime(self.root / 'runtime', {'project': 'alpha'}, FakeProviders())

    def test_correction_consent_edit_revoke(self):
        service = self.runtime.service
        messages = [{'role': 'user', 'content': 'What color is the fixture?'}, {'role': 'assistant', 'content': 'Blue.'}]
        candidate = service.post('accept-correction', {'messages': messages, 'license': 'Owner authorized', 'confirm': True})
        with self.assertRaises(Denied):
            service.post('export', {'ids': [candidate['id']], 'confirm': True})
        service.post('review', {'id': candidate['id'], 'hash': candidate['hash'], 'confirm': True})
        out = service.post('export', {'ids': [candidate['id']], 'confirm': True})
        self.assertFalse(out['manifest']['synthetic_only'])
        self.assertEqual(out['manifest']['jsonl_sha256'], digest(out['jsonl']))
        service.post('edit-candidate', {'id': candidate['id'], 'messages': messages})
        with self.assertRaises(Denied):
            service.post('review', {'id': candidate['id'], 'hash': candidate['hash'], 'confirm': True})
        service.post('revoke-candidate', {'id': candidate['id']})
        with self.assertRaises(Denied):
            service.post('export', {'ids': [candidate['id']], 'confirm': True})

    def test_synthetic_preview_does_not_accept_private_rows(self):
        from evolution import Dataset
        ds = Dataset(self.runtime.service.store)
        s = self.runtime.service.session()
        messages = [{'role': 'user', 'content': 'Fixture'}, {'role': 'assistant', 'content': 'Answer'}]
        eid = ds.evidence(s, [{'expected': 1, 'actual': 1}], messages, correction={'accepted': True})
        with self.assertRaises(Denied):
            ds.select(s, messages, eid, True, source='accepted_correction')

    def test_http_auth_origin_size_and_assets(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler(self.runtime))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def request(path, data=None, **headers):
            req = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(), headers=headers)
            try:
                with urllib.request.urlopen(req) as response:
                    return response.status, response.read()
            except urllib.error.HTTPError as error:
                return error.code, error.read()
        try:
            self.assertEqual(request('/api/status')[0], 401)
            headers = {'Authorization': 'Bearer ' + self.runtime.token}
            self.assertEqual(request('/api/status', **headers)[0], 200)
            self.assertEqual(request('/api/chats', {}, Origin='https://evil.invalid', **headers)[0], 403)
            self.assertEqual(request('/api/chats', {'oversize': 'x' * 70000}, **headers)[0], 400)
            self.assertEqual(request('/../../etc/passwd')[0], 404)
            for asset in ('/', '/app.js', '/evolution.js', '/runtime.js'):
                code, content = request(asset)
                self.assertEqual(code, 200)
                self.assertTrue(content)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_scheduled_extraction_grants_and_observed_runs(self):
        self.runtime.close()
        source = self.root / 'source.sqlite3'
        with sqlite3.connect(source) as c:
            c.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY,content TEXT,role TEXT,timestamp REAL,session_id TEXT)')
            c.execute("INSERT INTO messages VALUES(1,'I prefer blue widgets.','user',1000,'session')")
        self.runtime = Runtime(self.root / 'runtime', {'project': 'alpha', 'sources': [
            {'id': 'history', 'kind': 'hermes', 'path': str(source), 'root': str(self.root), 'records': ['1']}]}, FakeProviders())
        service = self.runtime.service
        service.post('grant', {'source': 'history', 'records': ['1'], 'confirm': True})
        self.assertEqual(service.post('extract', {'confirm': True})['queued'], 0)
        service.post('grant', {'source': 'history', 'records': ['1'], 'purpose': 'memory', 'confirm': True})
        service.post('schedule', {'enabled': True, 'interval_seconds': 60, 'confirm': True})
        nxt = service.schedule['next_run']
        service.tick(nxt + 125)
        health = service.health()
        self.assertEqual(health['completed'], 1)
        self.assertEqual(health['missed'], 2)
        rows = service.get('memory-candidates', {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['role'], 'user')
        self.assertEqual(service.post('extract', {'confirm': True})['queued'], 0)
        service.post('revoke-grant', {'source': 'history'})
        self.assertEqual(service.get('search', {'q': ['widgets']})['count'], 0)

    def test_dataset_revocation_cancels_linked_training(self):
        r = self.runtime
        candidate = r.service.post('accept-correction', {
            'messages': [{'role': 'user', 'content': 'Fixture question'},
                         {'role': 'assistant', 'content': 'Checked answer'}],
            'license': 'Fixture rights', 'confirm': True})
        job = r.tasks.submit('alpha', 'training', block)
        with r.tasks.db() as c:
            c.execute('INSERT INTO training_inputs VALUES(?,?,?)', (job['id'], candidate['id'], 'alpha'))
        r.post('evolution/revoke-candidate', {'id': candidate['id']})
        result = wait(r.tasks, 'alpha', job['id'])
        self.assertEqual(result['status'], 'cancelled')
        self.assertTrue(result['result']['affected_by_revocation'])
        self.assertFalse(result['result']['model_promoted'])

    def test_training_recipe_and_missing_runner(self):
        with self.assertRaises(Rejected):
            validate_recipe({'base_model': 'unreviewed'})
        with self.assertRaises(Rejected):
            self.runtime.post('training', {'ids': ['unknown'], 'recipe': {}, 'confirm': True, 'allow_runner_data_access': True})



class ProviderTests(unittest.TestCase):
    def test_free_catalog_and_explicit_model_no_fallback(self):
        from unittest.mock import patch
        calls = []
        def request(url, body=None, **kwargs):
            calls.append((url, body))
            if url.endswith('/models'):
                return {'data': [{'id': 'fixture:free', 'pricing': {'prompt': '0', 'completion': '0', 'request': '0'}}]}
            return {'choices': [{'message': {'content': 'Real transport fixture'}}]}
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'fixture-private-key'}), patch('hermes_runtime.core.json_request', request):
            providers = Providers()
            self.assertEqual(providers.complete('cloud', 'fixture:free', [{'role': 'user', 'content': 'Hello'}], True), 'Real transport fixture')
            self.assertFalse(calls[-1][1]['provider']['allow_fallbacks'])
            with self.assertRaises(Rejected):
                providers.complete('cloud', 'unselected:free', [{'role': 'user', 'content': 'Hello'}], True)
            self.assertEqual(sum('/chat/completions' in url for url, _ in calls), 1)

    def test_paid_or_unknown_catalog_does_not_call_inference(self):
        from unittest.mock import patch
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'fixture-private-key'}), patch('hermes_runtime.core.json_request', return_value={'data': [{'id': 'bad:free', 'pricing': {'prompt': '1', 'completion': '0'}}]}) as request:
            with self.assertRaises(RuntimeError):
                Providers().complete('cloud', 'bad:free', [{'role': 'user', 'content': 'Hello'}], True)
            self.assertEqual(request.call_count, 1)

    def test_explicit_gguf_hash_and_memory_gates(self):
        from unittest.mock import patch
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / 'fixture.gguf'; model.write_bytes(b'GGUF-fixture-not-a-real-model')
            executable = root / 'fixture-llama'
            executable.write_text('#!/usr/bin/env python3\nprint("FIXTURE_ONLY")\n')
            executable.chmod(0o700)
            checksum = hashlib.sha256(model.read_bytes()).hexdigest()
            providers = Providers(gguf={'path': str(model), 'sha256': checksum, 'executable': str(executable)})
            messages = [{'role': 'user', 'content': 'Fixture'}]
            with patch('hermes_runtime.device.inspect', return_value={'memory': {'MemAvailable_kib': 5 * 1024 * 1024}}):
                self.assertEqual(providers.complete('local', 'gguf:' + checksum[:12], messages), 'FIXTURE_ONLY')
                model.write_bytes(b'GGUF-modified')
                with self.assertRaises(Rejected):
                    providers.complete('local', 'gguf:' + checksum[:12], messages)
            with patch('hermes_runtime.device.inspect', return_value={'memory': {'MemAvailable_kib': 100}}):
                with self.assertRaises(Rejected):
                    providers.complete('local', 'gguf:' + checksum[:12], messages)

    def test_redirects_and_context_budget_rejected(self):
        from hermes_runtime.core import NoRedirect
        with self.assertRaises(Rejected):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.invalid')
        with self.assertRaises(Rejected):
            Providers().complete('local', 'model', [{'role': 'user', 'content': 'x' * 70000}])

    def test_local_route_never_falls_back(self):
        from unittest.mock import patch
        calls = []
        def request(url, body=None, **kwargs):
            calls.append(url)
            if url.endswith('/api/tags'):
                return {'models': [{'name': 'installed'}]}
            raise Rejected('Local unavailable')
        with patch('hermes_runtime.core.json_request', request):
            with self.assertRaises(Rejected):
                Providers().complete('local', 'installed', [{'role': 'user', 'content': 'Hello'}])
        self.assertTrue(all(url.startswith('http://127.0.0.1:11434/') for url in calls))


class ToolTests(unittest.TestCase):
    def test_qr_url_rejects_other_ports_and_fragments(self):
        from hermes_runtime.pair import pairing_url
        self.assertIn('/#pair=', pairing_url('a' * 43, 18877))
        for port in (8766, 8877, 0, -1, 65536):
            with self.assertRaises(ValueError):
                pairing_url('a' * 43, port)
        with self.assertRaises(ValueError):
            pairing_url('x#stolen', 18877)

    def test_backup_stopped_runtime_and_restore(self):
        from hermes_runtime.backup import backup
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = Runtime(root / 'runtime', {'project': 'restore'}, FakeProviders())
            with self.assertRaises(ValueError):
                backup(root / 'runtime', root / 'blocked-backup')
            cid = runtime.post('chats', {'mode': 'local', 'model': 'fixture-local'})['id']
            runtime.close()
            files = backup(root / 'runtime', root / 'backup')
            self.assertTrue(files)
            restored = Runtime(root / 'backup', {'project': 'restore'}, FakeProviders())
            try:
                self.assertEqual(restored.chat(cid)['title'], 'New conversation')
            finally:
                restored.close()

class TrainingTests(unittest.TestCase):
    def recipe(self):
        return {'base_model': 'Qwen/Qwen2.5-1.5B-Instruct', 'revision': 'a' * 40,
                'seed': 42, 'rank': 8, 'epochs': 1, 'max_eval_loss': 3}

    def exported(self):
        rows = [json.dumps({'messages': [{'role': 'user', 'content': str(i)},
                                        {'role': 'assistant', 'content': 'fixture'}]}) for i in range(3)]
        text = '\n'.join(rows) + '\n'
        return {'jsonl': text, 'manifest': {'jsonl_sha256': digest(text),
            'rows': [{'split': split} for split in ('train', 'validation', 'test')]}}

    def test_synthetic_external_runner_artifact_registration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = root / 'fixture_runner.py'
            runner.write_text('''import argparse,json,struct
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('--run-dir'); a=p.parse_args()
r=Path(a.run_dir); m=json.loads((r/'manifest.json').read_text())
assert all((r/(s+'.jsonl')).is_file() for s in ('train','validation','test'))
(r/'adapter').mkdir()
h=json.dumps({'fixture.lora_A.weight':{'dtype':'F32','shape':[1],'data_offsets':[0,4]}}).encode()
(r/'adapter/adapter_model.safetensors').write_bytes(struct.pack('<Q',len(h))+h+bytes(4))
(r/'evaluation.json').write_text(json.dumps({'dataset_sha256':m['jsonl_sha256'],'base_revision':m['recipe']['revision'],'eval_loss':1.0,'privacy_regressions':0,'behavioral_suite_passed':True,'fixture_only':True}))
''')
            out = train([sys.executable, str(runner)], root / 'runs', self.exported(), self.recipe())
            self.assertFalse(out['model_promoted'])
            self.assertTrue(out['evaluation']['fixture_only'])
            self.assertEqual(len(out['artifacts']['adapter_sha256']), 64)

    def test_missing_holdouts_fail_before_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            out = self.exported()
            for row in out['manifest']['rows']:
                row['split'] = 'train'
            with self.assertRaises(Rejected):
                train(['/does/not/exist'], Path(directory), out, self.recipe())

    def test_invalid_adapter_is_rejected(self):
        from hermes_runtime.workflows import validate_adapter
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'adapter.safetensors'
            path.write_bytes(b'not actual tensors')
            with self.assertRaises(Rejected):
                validate_adapter(path)

    def test_recipe_rejects_mutable_revision_and_unbounded_values(self):
        for key, value in [('revision', 'main'), ('epochs', 100), ('rank', True), ('max_eval_loss', float('nan'))]:
            recipe = self.recipe(); recipe[key] = value
            with self.assertRaises(Rejected):
                validate_recipe(recipe)

if __name__ == '__main__':
    unittest.main()
