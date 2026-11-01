#!/usr/bin/env python3
"""Run every offline router and portability regression; report exact unittest counts."""
from pathlib import Path
import importlib.util
import json
import os
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def main():
    os.umask(0o077)
    sys.dont_write_bytecode = True
    (ROOT / 'portable-test-runtime').mkdir(mode=0o700, exist_ok=True)
    sys.path.insert(0, str(ROOT))
    groups = {}
    success = True
    for group, files in [('router', sorted((ROOT / 'evolution_addons').glob('test_free_*.py'))),
                         ('hybrid', [ROOT / 'evolution_addons/test_hybrid.py']),
                         ('portability', [ROOT / 'tools/test_portability.py'])]:
        suite = unittest.TestSuite()
        for path in files:
            spec = importlib.util.spec_from_file_location('portable_' + path.stem, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        groups[group] = {'tests': result.testsRun, 'failures': len(result.failures),
                         'errors': len(result.errors), 'skipped': len(result.skipped)}
        success = success and result.wasSuccessful() and result.testsRun > 0
    (ROOT / 'ADDON_TEST_RESULTS.json').write_text(json.dumps(groups, indent=2) + '\n')
    print(json.dumps(groups, indent=2))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
