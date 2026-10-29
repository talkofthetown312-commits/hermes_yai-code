"""Offline regressions for Phase 3-only browser pairing startup."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'phase3'))
from pairing import MARKER, harden_pairing_javascript


class PairingBootstrapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = ROOT / 'phase2/pocket/web/app.js'
        cls.original = cls.path.read_text()

    def test_actual_main_frontend_failure_and_recovery(self):
        result = subprocess.run(
            ['node', str(Path(__file__).with_suffix('.cjs'))],
            input=json.dumps({'legacy': self.original,
                              'fixed': harden_pairing_javascript(self.original)}),
            text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(report['assertions'], 20)
        self.assertFalse(report['real_credentials_used'])
        self.assertEqual(report['legacy_failures_reproduced'], 3)
        print(json.dumps(report), flush=True)

    def test_idempotent_and_original_source_unchanged(self):
        before = hashlib.sha256(self.path.read_bytes()).digest()
        fixed = harden_pairing_javascript(self.original)
        self.assertEqual(harden_pairing_javascript(fixed), fixed)
        self.assertEqual(fixed.count(MARKER), 1)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).digest(), before)

    def test_transformed_full_script_parses(self):
        result = subprocess.run(['node', '--check'],
                                input=harden_pairing_javascript(self.original),
                                text=True, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unknown_or_partial_layout_refused(self):
        for source in ('', self.original.replace('async function api(', 'async function other('),
                       MARKER + '\n' + self.original):
            with self.subTest(layout='generated fixture'), self.assertRaises(ValueError):
                harden_pairing_javascript(source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
