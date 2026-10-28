"""Generated-fixture tests for the static gate; no application runtime imports."""
from pathlib import Path
import tempfile
import unittest

from check_source import check


class SourceGateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='source-gate-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_valid_source_is_parsed_without_execution(self):
        self.write('safe.py', 'raise RuntimeError("must not execute")\n')
        self.write('fixture.json', '{"synthetic": true}\n')
        self.write('fixture.xml', '<synthetic/>\n')
        result = check(self.root, ['safe.py', 'fixture.json', 'fixture.xml'])
        self.assertTrue(result['safe'])
        self.assertEqual(result['counts'], {'files': 3, 'json': 1, 'xml': 1, 'python': 1})
        self.assertEqual(result['application_runtime_tests'], 'NOT_RUN')

    def test_invalid_python_fails(self):
        self.write('broken.py', 'def invalid(\n')
        self.assertEqual(check(self.root, ['broken.py'])['findings'], {'source_syntax': 1})

    def test_invalid_json_fails(self):
        self.write('broken.json', '{')
        self.assertFalse(check(self.root, ['broken.json'])['safe'])

    def test_invalid_xml_fails(self):
        self.write('broken.xml', '<synthetic>')
        self.assertFalse(check(self.root, ['broken.xml'])['safe'])

    def test_valid_javascript_is_not_executed(self):
        self.write('safe.js', 'throw new Error("must not execute");\n')
        self.assertTrue(check(self.root, ['safe.js'])['safe'])

    def test_invalid_javascript_fails(self):
        self.write('broken.cjs', 'function invalid( {\n')
        self.assertEqual(check(self.root, ['broken.cjs'])['findings'], {'javascript_syntax': 1})

    def test_forbidden_runtime_file_fails(self):
        self.write('runtime.db', 'synthetic runtime\n')
        self.assertIn('forbidden_file', check(self.root, ['runtime.db'])['findings'])

    def test_vendor_credential_is_rejected_without_disclosure(self):
        canary = 'sk-' + 'A' * 32
        self.write('canary.txt', canary)
        result = check(self.root, ['canary.txt'])
        self.assertIn('credential_vendor', result['findings'])
        self.assertNotIn(canary, str(result))

    def test_fixed_interpreter_path_fails(self):
        self.write('worker.py', '#!' + '/opt/' + 'synthetic/bin/python3\npass\n')
        self.assertIn('fixed_python_path', check(self.root, ['worker.py'])['findings'])

    def test_symlink_file_fails(self):
        self.write('target.py', 'pass\n')
        (self.root / 'link.py').symlink_to('target.py')
        self.assertIn('symlink', check(self.root, ['link.py'])['findings'])

    def test_symlink_directory_fails(self):
        self.write('actual/target.py', 'pass\n')
        (self.root / 'linked').symlink_to('actual', target_is_directory=True)
        self.assertIn('symlink', check(self.root, ['linked/target.py'])['findings'])

    def test_path_traversal_fails(self):
        self.assertIn('unsafe_path', check(self.root, ['../outside.py'])['findings'])

    def test_missing_file_fails(self):
        self.assertIn('missing_or_special_file', check(self.root, ['missing.py'])['findings'])

    def test_empty_inventory_fails(self):
        self.assertFalse(check(self.root, [])['safe'])


if __name__ == '__main__':
    unittest.main()
