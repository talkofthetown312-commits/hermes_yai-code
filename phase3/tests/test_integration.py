#!/usr/bin/env python3
"""Offline Phase 3 HTTP/persistence/security checks, in disposable synthetic runtimes."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from urllib.parse import urlsplit

PHASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PHASE))
from serve import prepare

FIELDS = ('trigger', 'prerequisites', 'method', 'tools', 'inputs', 'outputs', 'risks', 'permissions', 'verification')


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='phase3-tests-')
        self.root = Path(self.temporary.name)
        self.state = self.root / 'hermes-yai-phase3-test'
        self.server = None
        self.url = None
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.stop)
        self.start()

    def start(self):
        self.log = (self.root / 'server.log').open('w')
        self.server = subprocess.Popen(
            [sys.executable, '-B', str(PHASE / 'serve.py'), '--state-dir', str(self.state), '--port', '0'],
            stdout=subprocess.PIPE, stderr=self.log, text=True,
            env={'PATH': os.environ.get('PATH', ''), 'HOME': str(self.root), 'PYTHONDONTWRITEBYTECODE': '1'})
        if not select.select([self.server.stdout], [], [], 15)[0]:
            self.fail('Server readiness timeout')
        line = self.server.stdout.readline().strip()
        self.assertTrue(line.startswith('Phase 3 staging ready: '), 'Server did not start; inspect private server.log')
        self.url = line.split('ready: ', 1)[1].rstrip('/')
        self.assertNotIn(urlsplit(self.url).port, (8766, 8877))
        self.key = (self.state / 'app/data/pairing-token').read_text().strip()

    def stop(self):
        if self.server is not None:
            self.server.terminate()
            try:
                self.server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.server.kill()
                self.server.wait(timeout=5)
            self.server.stdout.close()
            self.log.close()
            self.server = None
            if self.url:
                with socket.socket() as client:
                    self.assertNotEqual(client.connect_ex(('127.0.0.1', urlsplit(self.url).port)), 0)

    def tearDown(self):
        self.stop()
        self.temporary.cleanup()

    def request(self, path, body=None, auth=True, origin=None, host=None, raw=False):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + self.key
        if origin:
            headers['Origin'] = origin
        if host:
            headers['Host'] = host
        request = urllib.request.Request(self.url + path, headers=headers,
                                         data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                content = response.read()
                return response.status, content.decode() if raw else json.loads(content), dict(response.headers)
        except urllib.error.HTTPError as error:
            status = error.code
            error.close()
            return status, None, {}

    def get(self, endpoint):
        status, value, _ = self.request('/api/' + endpoint)
        self.assertEqual(status, 200)
        return value

    def post(self, endpoint, body, status=200):
        code, value, _ = self.request('/api/' + endpoint, body)
        self.assertEqual(code, status)
        return value

    def skill(self):
        return self.post('evolution/teach', {'body': {key: 'Synthetic ' + key + ' guidance.' for key in FIELDS}})

    def approve(self, skill):
        result = self.post('evolution/test', {'id': skill['id'], 'revision': skill['revision'], 'confirm': True})
        return self.post('evolution/approve', {'id': skill['id'], 'hash': skill['hash'], 'test_hash': result['hash'], 'confirm': True})

    def test_dashboard_read_is_nonmutating(self):
        first = self.get('integration/dashboard')
        second = self.get('integration/dashboard')
        self.assertEqual(first, second)
        self.assertEqual(sum(first['skills'].values()), 0)
        self.assertEqual(first['granted_sources'], 0)
        self.assertEqual(first['preferences']['revision'], 0)
        self.assertEqual(first['providers'], 'disabled')
        self.assertEqual(first['training'], 'disabled')
        self.assertEqual(first['project'], 'phase3-synthetic')

    def test_auth_origin_host_and_execution_denials(self):
        for path in ('integration/dashboard', 'evolution/state'):
            self.assertEqual(self.request('/api/' + path, auth=False)[0], 401)
        self.assertEqual(self.request('/api/integration/dashboard', host='evil.invalid')[0], 403)
        self.assertEqual(self.request('/api/integration/preferences', {'view': 'skills', 'revision': 0, 'confirm': True}, origin='https://evil.invalid')[0], 403)
        self.post('send', {'message': 'No model allowed'}, 409)
        self.assertEqual(self.get('models')['models'], [])
        self.assertFalse(self.get('status')['ready'])
        self.post('training', {'enabled': True}, 403)
        self.post('integration/preferences', {'view': 'skills', 'revision': 0, 'confirm': True, 'project': 'other'}, 409)
        self.post('evolution/teach', {'body': {}, 'project': 'other'}, 400)

    def test_navigation_validation_and_compare_and_swap(self):
        for body in ({'view': '../private', 'revision': 0, 'confirm': True},
                     {'view': 'skills', 'revision': True, 'confirm': True},
                     {'view': 'skills', 'revision': 0, 'confirm': False}, []):
            self.post('integration/preferences', body, 409)
        self.post('integration/preferences', {'view': 'skills', 'revision': 0, 'confirm': True})
        self.post('integration/preferences', {'view': 'memory', 'revision': 0, 'confirm': True}, 409)
        self.assertEqual(self.get('integration/dashboard')['preferences'], {'view': 'skills', 'revision': 1})

    def test_concurrent_navigation_has_one_winner(self):
        def update(view):
            return self.request('/api/integration/preferences', {'view': view, 'revision': 0, 'confirm': True})[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(update, ['skills', 'memory']))
        self.assertEqual(sorted(statuses), [200, 409])

    def test_granted_memory_provenance_and_revocation(self):
        sources = self.state / 'app/data/synthetic-sources'
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources.iterdir() if path.is_file()}
        self.assertEqual(self.get('evolution/search?q=widget')['count'], 0)
        for source in ['hermes', 'chat', 'web']:
            self.post('evolution/grant', {'source': source, 'records': ['1'], 'confirm': True})
        result = self.get('evolution/search?q=widget')
        self.assertEqual(result['count'], 3)
        self.assertTrue(any(item['claim_type'] == 'prior_ai' for item in result['results']))
        self.assertTrue(any(item['disputed'] and item['claim_type'] == 'reported_claim' for item in result['results']))
        for item in result['results']:
            self.assertFalse(item['verified'])
            self.assertTrue(item['untrusted'])
            self.assertEqual(item['project'], 'phase3-synthetic')
            for citation in item['citations']:
                self.assertEqual(len(citation['content_hash']), 64)
                self.assertIn('author_role', citation)
                self.assertIn('timestamp', citation)
                self.assertIn('session_id', citation)
        for source in ['hermes', 'chat', 'web']:
            self.post('evolution/revoke-grant', {'source': source})
        self.assertEqual(self.get('evolution/search?q=widget')['count'], 0)
        after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources.iterdir() if path.is_file()}
        self.assertEqual(before, after)
        self.post('evolution/grant', {'source': '../../production', 'records': ['1'], 'confirm': True}, 400)

    def test_full_skill_lifecycle_edit_revocation(self):
        skill = self.skill()
        reuse = {'id': skill['id'], 'hash': skill['hash'], 'task': 'Synthetic test task', 'confirm': True}
        self.post('evolution/reuse', reuse, 400)
        self.post('evolution/approve', {'id': skill['id'], 'hash': skill['hash'], 'test_hash': 'unobserved', 'confirm': True}, 400)
        approved = self.approve(skill)
        bundle = self.post('evolution/reuse', reuse)
        self.assertFalse(bundle['executes'])
        self.assertFalse(bundle['installed'])
        self.assertEqual(hashlib.sha256(bundle['skill_md'].encode()).hexdigest(), bundle['skill_md_sha256'])
        self.assertEqual(self.get('integration/dashboard')['skills']['approved'], 1)
        edited = self.post('evolution/edit-skill', {'id': skill['id'], 'revision': 1,
                           'body': {key: 'Edited synthetic ' + key for key in FIELDS}})
        self.assertEqual(edited['state'], 'draft')
        self.assertIsNone(edited['approval'])
        self.post('evolution/reuse', reuse, 400)
        self.post('evolution/edit-skill', {'id': skill['id'], 'revision': 1, 'body': approved['body']}, 400)
        self.approve(edited)
        self.post('evolution/revoke-skill', {'id': skill['id']})
        self.post('evolution/reuse', {**reuse, 'hash': edited['hash']}, 400)
        self.assertEqual(self.get('integration/dashboard')['skills']['revoked'], 1)

    def test_restart_preserves_pairing_grants_skills_and_navigation(self):
        skill = self.approve(self.skill())
        self.post('evolution/grant', {'source': 'hermes', 'records': ['1'], 'confirm': True})
        self.post('integration/preferences', {'view': 'skills', 'revision': 0, 'confirm': True})
        old_key = self.key
        before = self.get('integration/dashboard')
        self.stop()
        self.start()
        self.assertEqual(self.key, old_key)
        self.assertEqual(self.get('integration/dashboard'), before)
        self.assertEqual(self.get('evolution/search?q=widget')['count'], 1)
        self.post('evolution/reuse', {'id': skill['id'], 'hash': skill['hash'], 'task': 'Restart test', 'confirm': True})
        self.post('evolution/revoke-grant', {'source': 'hermes'})
        self.stop()
        self.start()
        self.assertEqual(self.get('evolution/search?q=widget')['count'], 0)

    def test_failed_contract_cannot_be_approved(self):
        skill = self.post('evolution/teach', {'body': {key: 'execute without approval' for key in FIELDS}})
        result = self.post('evolution/test', {'id': skill['id'], 'revision': 1, 'confirm': True})
        self.assertFalse(result['passed'])
        self.post('evolution/approve', {'id': skill['id'], 'hash': skill['hash'],
                  'test_hash': result['hash'], 'confirm': True}, 400)

    def test_expired_approval_is_not_reusable_or_counted_approved(self):
        import sqlite3
        skill = self.approve(self.skill())
        with sqlite3.connect(self.state / 'app/data/evolution/evolution.sqlite3') as connection:
            connection.execute('UPDATE skills SET expires=1 WHERE id=?', (skill['id'],))
        counts = self.get('integration/dashboard')['skills']
        self.assertEqual(counts['expired'], 1)
        self.assertEqual(counts['approved'], 0)
        self.post('evolution/reuse', {'id': skill['id'], 'hash': skill['hash'], 'task': 'Expired test', 'confirm': True}, 400)

    def test_unsupported_schema_refuses_restart_without_migration(self):
        import sqlite3
        self.stop()
        database = self.state / 'app/data/evolution/evolution.sqlite3'
        with sqlite3.connect(database) as connection:
            connection.execute('UPDATE meta SET version=999')
        before = hashlib.sha256(database.read_bytes()).hexdigest()
        process = subprocess.run([sys.executable, '-B', str(PHASE / 'serve.py'),
                                  '--state-dir', str(self.state), '--port', '0'],
                                 capture_output=True, text=True, timeout=15)
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before)

    def test_pocket_ui_assets_and_private_state_not_served(self):
        code, html, headers = self.request('/', auth=False, raw=True)
        self.assertEqual(code, 200)
        for marker in ('/integration.js', '/app.js', '/evolution.js', 'composer', 'file-input', 'chat-export'):
            self.assertIn(marker, html)
        self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        for path in ('/integration.js', '/integration.css', '/app.js', '/evolution.js'):
            self.assertEqual(self.request(path, auth=False, raw=True)[0], 200)
        script = self.request('/app.js', auth=False, raw=True)[1]
        self.assertIn('guarded browser pairing bootstrap v1', script)
        self.assertIn('const headerToken = pocketStagingPairingValue(token)', script)
        for path in ('/app/data/pairing-token', '/../phase3-owner.json', '/api/integration/no-such-path'):
            self.assertEqual(self.request(path)[0], 404)
        data_files = [path for path in self.state.rglob('*') if path.is_file()]
        self.assertTrue(all(path.stat().st_mode & 0o077 == 0 for path in data_files))

    def test_existing_offline_file_workflow_without_inference(self):
        import base64
        chat = self.post('chats', {'mode': 'cloud', 'model': ''}, 201)
        artifact = self.post('files/upload', {'chat': chat['id'], 'name': 'synthetic.txt',
                             'mime': 'text/plain', 'data': base64.b64encode(b'Synthetic integration attachment').decode()}, 201)
        self.assertEqual(len(self.get('drafts?chat=' + chat['id'])), 1)
        self.post('files/remove', {'chat': chat['id'], 'id': artifact['id']})
        self.assertEqual(len(self.get('drafts?chat=' + chat['id'])), 0)

    def test_simulated_dom_against_real_api(self):
        process = subprocess.run(['node', str(PHASE / 'tests/test_ui.cjs')],
                                 env={'PATH': os.environ.get('PATH', ''), 'FIXTURE_URL': self.url,
                                      'FIXTURE_PAIRING': self.key}, capture_output=True, text=True, timeout=40)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        report = json.loads(process.stdout)
        self.assertFalse(report['native_android_verified'])
        self.assertGreaterEqual(report['assertions'], 20)
        print('Phase 3 simulated DOM assertions:', report['assertions'])


class RuntimeSafetyTest(unittest.TestCase):
    def test_unknown_directory_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'hermes-yai-phase3-foreign'
            directory.mkdir()
            sentinel = directory / 'keep.txt'
            sentinel.write_text('untouched')
            with self.assertRaises(ValueError):
                prepare(directory)
            self.assertEqual(sentinel.read_text(), 'untouched')
            link = Path(temporary) / 'hermes-yai-phase3-link'
            link.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(ValueError):
                prepare(link)

    def test_owned_directory_lock_and_symlink_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'hermes-yai-phase3-owned'
            _, _, lock = prepare(directory)
            try:
                with self.assertRaises(BlockingIOError):
                    prepare(directory)
            finally:
                lock.close()
            sentinel = Path(temporary) / 'never-touch'
            sentinel.write_text('untouched')
            (directory / 'alias').symlink_to(sentinel)
            with self.assertRaises(ValueError):
                prepare(directory)
            self.assertEqual(sentinel.read_text(), 'untouched')

    def test_runtime_hardlinks_and_special_files_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'hermes-yai-phase3-alias-test'
            _, _, lock = prepare(directory)
            lock.close()
            sentinel = Path(temporary) / 'untouched.txt'
            sentinel.write_text('untouched')
            alias = directory / 'aliased-file'
            linker = getattr(os, 'link', None)
            if linker:
                linker(sentinel, alias)
                with self.assertRaises(ValueError):
                    prepare(directory)
            else:
                # Android omits os.link; this host also denies POSIX ln.
                # Exercise nlink rejection with generated stat metadata, not a
                # claimed native alias. Linux CI exercises the actual hardlink.
                from unittest.mock import patch
                alias.write_text('Synthetic metadata canary')
                original_stat = Path.stat
                def aliased_stat(path, *args, **kwargs):
                    result = original_stat(path, *args, **kwargs)
                    if path == alias:
                        return os.stat_result((result.st_mode, result.st_ino, result.st_dev,
                                               2, result.st_uid, result.st_gid, result.st_size,
                                               result.st_atime, result.st_mtime, result.st_ctime))
                    return result
                with patch.object(Path, 'stat', aliased_stat):
                    with self.assertRaises(ValueError):
                        prepare(directory)
                print('Hardlink rejection: generated metadata on Android; native fixture unavailable')
            self.assertEqual(sentinel.read_text(), 'untouched')
            alias.unlink()
            os.mkfifo(directory / 'special-file')
            with self.assertRaises(ValueError):
                prepare(directory)

    def test_production_ports_refused_before_creating_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / 'hermes-yai-phase3-not-created'
            for port in (8766, 8877):
                result = subprocess.run([sys.executable, '-B', str(PHASE / 'serve.py'), '--state-dir', str(directory), '--port', str(port)], capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(directory.exists())


if __name__ == '__main__':
    os.umask(0o077)
    unittest.main(verbosity=2)
