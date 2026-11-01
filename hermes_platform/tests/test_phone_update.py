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


if __name__ == '__main__':
    unittest.main()
