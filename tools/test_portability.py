"""Host-resolved fake-worker portability; never imports or starts an installed agent."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def worker_source(phase):
    path = ROOT / phase / 'pocket/tests/test_bridge.py'
    tree = ast.parse(path.read_text(), str(path))
    writes = [node for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
              and node.func.attr == 'write_text'
              and isinstance(node.func.value, ast.Name) and node.func.value.id == 'fake']
    if len(writes) != 1:
        raise AssertionError('Expected exactly one fake-worker constructor')
    expression = ast.Expression(writes[0].args[0])
    return eval(compile(expression, str(path), 'eval'), {'sys': sys})


class PortableWorkers(unittest.TestCase):
    def check_worker(self, phase):
        source = worker_source(phase)
        self.assertEqual(source.splitlines()[0], '#!' + sys.executable)
        self.assertTrue(os.access(sys.executable, os.X_OK))
        with tempfile.TemporaryDirectory(dir=ROOT / 'portable-test-runtime') as directory:
            worker = Path(directory) / 'fake-hermes'
            worker.write_text(source)
            worker.chmod(0o700)
            result = subprocess.run([str(worker), 'chat', '--help'],
                                    cwd=directory, capture_output=True, text=True,
                                    env={'PATH': os.environ.get('PATH', '')}, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--format stream-json --resume', result.stdout)

    def test_phase1_worker_executes_with_current_python(self):
        self.check_worker('phase1/implementation')

    def test_phase2_worker_executes_with_current_python(self):
        self.check_worker('phase2')

    def test_no_fixed_python_absolute_paths_in_executable_source(self):
        import re
        fixed = re.compile(r'(?m)^\s*#!\s*/(?!usr/bin/env\s+python)[^\n]*python[0-9.]*\s*$')
        for path in ROOT.rglob('*.py'):
            if any(part in {'portable-test-runtime', 'runtime-home', 'qa-temp', 'test-tmp', 'test-runs'}
                   for part in path.relative_to(ROOT).parts):
                continue
            text = path.read_text()
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertIsNone(fixed.search(text))
                self.assertNotRegex(text, r'/opt/[^\s\"\x27]*bin/python(?:3)?\b')

    def test_runner_does_not_rewrite_test_source(self):
        text = (ROOT / 'tools/run_portable_tests.py').read_text()
        self.assertNotIn('f.write_text(text)', text)
        self.assertNotIn('text.replace(', text)


if __name__ == '__main__':
    (ROOT / 'portable-test-runtime').mkdir(mode=0o700, exist_ok=True)
    unittest.main()
