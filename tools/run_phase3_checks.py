#!/usr/bin/env python3
"""Run all offline source/Phase 1-3 checks in a fresh disposable source copy.
No installed services, private data, model inference or training are used.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def failure_summary(source):
    """Only publish enumerated result fields, never nested raw runtime logs/tokens."""
    report = source / 'PORTABLE_TEST_RESULTS.json'
    if not report.is_file():
        return {'portable_report': 'MISSING'}
    data = json.loads(report.read_text())
    return {
        'portable_failures': [{'test': row['test'], 'error_type': row.get('error_type')}
                              for row in data['portable_acceptance'] if row['status'] != 'PASS'],
        'edges': {key: data[key] for key in ('edge_tests', 'edge_failures', 'edge_errors')},
        'regressions': [{'phase': row['phase'], 'exit_code': row['exit_code'],
                         'results': row['results']} for row in data['offline_regressions']],
        'addons': data['addon_tests'], 'addon_exit_code': data['addon_exit_code'],
        'mocked_export_exit_code': data['mocked_export_exit_code'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-dir', type=Path)
    options = parser.parse_args()
    os.umask(0o077)
    evidence = options.evidence_dir
    if evidence:
        evidence = evidence.absolute()
        if evidence.is_relative_to(ROOT) or evidence.is_symlink():
            parser.error('Evidence must be outside source')
        evidence.mkdir(parents=True, mode=0o700, exist_ok=False)
    inventory = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    with tempfile.TemporaryDirectory(prefix='hermes-yai-checks-') as temporary:
        scratch = Path(temporary)
        source = scratch / 'source'
        for name in sorted(set(filter(None, inventory))):
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise RuntimeError('Unsafe source inventory')
            original = ROOT / relative
            if any(path.is_symlink() for path in [original, *original.parents]):
                raise RuntimeError('Source symlink refused')
            if not original.is_file():
                raise RuntimeError('Missing inventory member')
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)
        home = scratch / 'home'
        (home / 'hermes').mkdir(parents=True)
        env = {'PATH': os.environ.get('PATH', ''), 'HOME': str(home),
               'HERMES_HOME': str(home / 'hermes'), 'TMPDIR': str(scratch),
               'PYTHONDONTWRITEBYTECODE': '1'}
        subprocess.run(['git', 'init', '--quiet', str(source)], env=env, check=True)
        # Index only the just-copied explicit source inventory, including retained
        # baseline files that publication ignore rules might otherwise hide.
        subprocess.run(['git', 'add', '--force', '--', '.'], cwd=source, env=env, check=True)
        checks = [
            ('source-gate', [sys.executable, '-B', 'tools/check_source.py']),
            ('source-gate-fixtures', [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tools', '-p', 'test_check_source.py', '-v']),
            ('phase1-phase2-complete', [sys.executable, '-B', 'tools/run_complete_portable_tests.py']),
            ('phase3-integration', [sys.executable, '-B', 'phase3/tests/test_integration.py']),
        ]
        outcomes = []
        for name, arguments in checks:
            result = subprocess.run(arguments, cwd=source, env=env, capture_output=True, text=True, timeout=480)
            if evidence:
                (evidence / (name + '.log')).write_text(result.stdout + result.stderr)
            outcomes.append({'name': name, 'exit_code': result.returncode})
            print(name + ': ' + ('PASS' if result.returncode == 0 else 'FAIL'), flush=True)
            if result.returncode:
                if name == 'phase1-phase2-complete':
                    print(json.dumps(failure_summary(source), indent=2))
                # Test output is exclusively synthetic, but keep logs private where possible.
                if not evidence:
                    print(result.stdout[-6000:] + result.stderr[-6000:])
                print('FAILED: ' + name + ('; inspect private evidence log' if evidence else ''))
                return 1
        report = json.loads((source / 'COMPLETE_PORTABLE_TEST_RESULTS.json').read_text())
        summary = {'status': 'PASS', 'checks': outcomes,
                   'phase1_phase2': report, 'native_android': 'NOT_VERIFIED',
                   'models_or_providers_called': False, 'training': False,
                   'production_changes': False, 'disposable_runtime_removed_on_exit': True}
        if evidence:
            (evidence / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        core = report['core']
        print(json.dumps({'status': 'PASS', 'portable_acceptance': core['portable_acceptance_passed'],
                          'edge_tests': core['edge_tests'],
                          'regression_suites': [item['results'] for item in core['offline_regressions']],
                          'addon_tests': core['addon_tests'],
                          'phase1_http_checks': len(report['phase1_http']['http_checks']),
                          'phase2_features': report['phase2_features']['passed'],
                          'phase2_dom': report['phase2_dom']['assertion_count'],
                          'restart_checks': len(report['dataset_edit_and_restart']),
                          'phase3_suite': 'PASS', 'native_android': 'NOT_VERIFIED'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
