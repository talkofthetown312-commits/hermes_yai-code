import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from hermes_platform.package import FILES, build, install
from hermes_platform.server import default_config
from hermes_platform.storage import Store, private_file

ROOT = Path(__file__).resolve().parents[2]


class PhoneUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        archive = self.root / 'before.tar.gz'
        self.app = self.root / 'app'
        install(archive, build(archive), self.app)
        self.store = Store(self.app / 'data')
        self.task = self.store.create({'prompt': 'Synthetic retained task', 'cloud_consent': False, 'memory_sources': []})
        private_file(self.app / 'data/server.lock', '')
        private_file(self.app / 'android-local.json', json.dumps(default_config()))
        self.preserved = {name: (self.app / name).read_bytes() for name in (
            'data/tasks.sqlite3', 'data/pairing-token', 'android-local.json')}
        self.previous = os.readlink(self.app / 'current')
        self.zip = self.root / 'source.zip'
        with zipfile.ZipFile(self.zip, 'w') as source:
            for name in FILES:
                source.writestr('source/' + name, (ROOT / name).read_bytes())

    def tearDown(self):
        self.temporary.cleanup()

    def run_update(self):
        return subprocess.run([sys.executable, '-B', str(ROOT / 'tools/update_phone.py'),
                               str(self.zip), '--root', str(self.app)],
                              cwd=self.root, capture_output=True, text=True, timeout=10)

    def test_update_preserves_task_database_token_config_and_previous_source(self):
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(os.readlink(self.app / 'previous'), self.previous)
        for name, raw in self.preserved.items():
            self.assertEqual((self.app / name).read_bytes(), raw)
        self.assertEqual(self.store.get(self.task['id'])['status'], 'queued')
        self.assertIn('timeout=seconds', (self.app / 'current/hermes_platform/models.py').read_text())

    def test_running_platform_refused_before_release_switch(self):
        with (self.app / 'data/server.lock').open('r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Platform still running', result.stderr)
        self.assertEqual(os.readlink(self.app / 'current'), self.previous)
        for name, raw in self.preserved.items():
            self.assertEqual((self.app / name).read_bytes(), raw)

    def test_tampered_source_rejected_without_touching_workspace(self):
        with zipfile.ZipFile(self.zip, 'w') as source:
            for name in FILES:
                raw = (ROOT / name).read_bytes()
                if name.endswith('models.py'):
                    raw += b'\n# tampered fixture\n'
                source.writestr('source/' + name, raw)
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Source verification failed', result.stderr)
        self.assertEqual(os.readlink(self.app / 'current'), self.previous)



    def test_updated_runtime_completes_and_persists_a_six_agent_task(self):
        """Exercise the installed source after the updater, not just its files."""
        import time
        import urllib.error
        import urllib.request
        from hermes_platform.contracts import MODEL_ROLES
        from hermes_platform.tests.support import FakeOllama

        model = FakeOllama()
        process = None
        try:
            config = {'routes': {role: dict(model.route) for role in MODEL_ROLES},
                      'seconds': 10, 'memory_sources': {}}
            (self.app / 'android-local.json').write_text(json.dumps(config))
            self.preserved['android-local.json'] = (self.app / 'android-local.json').read_bytes()
            result = self.run_update()
            self.assertEqual(result.returncode, 0, result.stderr)
            for name, raw in self.preserved.items():
                self.assertEqual((self.app / name).read_bytes(), raw)

            token = (self.app / 'data/pairing-token').read_text()
            command = [sys.executable, '-B', '-m', 'hermes_platform.server',
                       '--data', str(self.app / 'data'),
                       '--config', str(self.app / 'android-local.json'), '--port', '0']

            def start():
                child = subprocess.Popen(command, cwd=self.app / 'current',
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         text=True)
                ready = child.stdout.readline()
                self.assertTrue(ready, child.stderr.read()[-2000:])
                payload = json.loads(ready)
                self.assertEqual(payload['status'], 'ready')
                return child, 'http://127.0.0.1:' + str(payload['port'])

            def stop(child):
                child.terminate()
                child.wait(timeout=10)
                child.stdout.close()
                child.stderr.close()

            def api(base, path, body=None):
                request = urllib.request.Request(
                    base + path,
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={'Authorization': 'Bearer ' + token,
                             'Content-Type': 'application/json'})
                try:
                    response = urllib.request.urlopen(request, timeout=5)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    return response.status, json.loads(response.read())

            process, base = start()
            self.assertEqual(api(base, '/api/state')[0], 200)
            deadline = time.monotonic() + 30
            current = None
            while time.monotonic() < deadline:
                status, current = api(base, '/api/tasks/' + self.task['id'])
                self.assertEqual(status, 200)
                if current['status'] in {'awaiting_approval', 'failed', 'rejected'}:
                    break
                time.sleep(.1)
            self.assertEqual(current['status'], 'awaiting_approval', current)
            self.assertEqual([step['status'] for step in current['steps']], ['done'] * 6)
            self.assertEqual(len(model.calls), 5)
            self.assertTrue(all(call['stream'] is False for call in model.calls))

            decision = {'revision': current['revision'], 'action': 'approve',
                        'result_hash': current['result_hash']}
            status, approved = api(base, '/api/tasks/' + self.task['id'] + '/decision', decision)
            self.assertEqual(status, 200)
            self.assertEqual(approved['status'], 'approved')
            stop(process)
            process = None

            process, base = start()
            status, restored = api(base, '/api/tasks/' + self.task['id'])
            self.assertEqual(status, 200)
            self.assertEqual(restored['status'], 'approved')
            self.assertEqual(restored['result_hash'], current['result_hash'])
            self.assertEqual((self.app / 'data/pairing-token').read_text(), token)
        finally:
            if process is not None:
                process.terminate()
                process.wait(timeout=10)
                process.stdout.close()
                process.stderr.close()
            model.close()

if __name__ == '__main__':
    unittest.main()
