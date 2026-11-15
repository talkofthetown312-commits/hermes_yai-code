#!/usr/bin/env python3
"""Run current-source runtime and portable checks without rewriting the checkout."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, check=True)
    for path in sorted((ROOT / 'hermes_runtime/web').glob('*.js')):
        subprocess.run(['node', '--check', str(path)], check=True)
    with tempfile.TemporaryDirectory(prefix='hermes-development-') as directory:
        copy = Path(directory) / 'source'
        # Use the current source, including uncommitted work, without runtime data.
        paths = subprocess.check_output(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
        for relative in filter(None, paths):
            source = ROOT / relative
            if source.is_symlink() or not source.is_file():
                raise RuntimeError('Source file unavailable or symlinked')
            target = copy / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        subprocess.run([sys.executable, '-B', str(copy / 'tools/run_complete_portable_tests.py')], cwd=copy, check=True)
    print('PASS: development runtime and complete applicable portable suites; no live models/providers or Android device used')


if __name__ == '__main__':
    main()
