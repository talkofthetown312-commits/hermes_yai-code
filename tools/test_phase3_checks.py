"""Generated nested-diagnostic fixtures, without providers or private runtime data."""
import json
from pathlib import Path
import tempfile
import unittest
from run_phase3_checks import failure_summary


class DiagnosticsTest(unittest.TestCase):
    def test_missing_report_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(failure_summary(Path(directory)), {'portable_report': 'MISSING'})

    def test_nested_failures_and_parser_names_without_raw_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {
                'portable_acceptance': [{'test': 'P04', 'status': 'FAIL', 'error_type': 'AssertionError'}],
                'edge_tests': 12, 'edge_failures': 0, 'edge_errors': 0,
                'offline_regressions': [{'phase': 'phase2', 'exit_code': 1,
                                         'results': {'tests': 25, 'errors': 5,
                                                     'private_canary': 'DO_NOT_EMIT_CANARY'}}],
                'addon_tests': {'router': {'tests': 9, 'private_canary': 'DO_NOT_EMIT_CANARY'}},
                'addon_exit_code': 0,
                'mocked_export_exit_code': 0, 'private_canary': 'DO_NOT_EMIT_CANARY',
            }
            (root / 'PORTABLE_TEST_RESULTS.json').write_text(json.dumps(report))
            runtime = root / 'portable-test-runtime'
            runtime.mkdir()
            (runtime / 'core.log').write_text(
                "ModuleNotFoundError: No module named 'PIL'\n"
                "ModuleNotFoundError: No module named 'pypdf'\nDO_NOT_EMIT_CANARY\n")
            result = failure_summary(root)
            self.assertEqual(result['missing_optional_parsers'], ['PIL', 'pypdf'])
            self.assertEqual(result['portable_failures'], [
                {'test': 'P04', 'error_type': 'AssertionError'}])
            self.assertNotIn('DO_NOT_EMIT_CANARY', json.dumps(result))

    def test_missing_nested_log_does_not_hide_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = {'portable_acceptance': [], 'edge_tests': 12, 'edge_failures': 0,
                      'edge_errors': 0, 'offline_regressions': [], 'addon_tests': {},
                      'addon_exit_code': 0, 'mocked_export_exit_code': 0}
            (root / 'PORTABLE_TEST_RESULTS.json').write_text(json.dumps(report))
            self.assertEqual(failure_summary(root)['missing_optional_parsers'], [])


if __name__ == '__main__':
    unittest.main()
