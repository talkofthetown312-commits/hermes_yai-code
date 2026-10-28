#!/usr/bin/env python3
"""Static source gate: never imports application code or starts a provider."""
import ast
from collections import Counter
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

from verify_handoff import inspect

ROOT = Path(__file__).resolve().parents[1]
FIXED_SHEBANG = re.compile(
    r'(?m)^\s*#!\s*/(?!usr/bin/env\s+python)[^\n]*python[0-9.]*\s*$'
)
FIXED_PYTHON = re.compile(r'/opt/[^\s\"\x27]*bin/python(?:3)?\b')


def check(root, names):
    """Inspect explicit repository-relative files; return counts, never file data."""
    counts = Counter()
    findings = Counter()
    for name in sorted(set(names)):
        relative = PurePosixPath(name)
        if (relative.is_absolute() or '..' in relative.parts or '\\' in name
                or not relative.parts):
            findings['unsafe_path'] += 1
            continue
        path = root.joinpath(*relative.parts)
        if any(root.joinpath(*relative.parts[:index]).is_symlink()
               for index in range(1, len(relative.parts) + 1)):
            findings['symlink'] += 1
            continue
        if not path.is_file():
            findings['missing_or_special_file'] += 1
            continue
        raw = path.read_bytes()
        counts['files'] += 1
        file_findings = inspect(name, raw)
        findings.update(item['rule'] for item in file_findings)
        if file_findings:
            continue
        text = raw.decode('utf-8')
        try:
            if path.suffix == '.py':
                counts['python'] += 1
                ast.parse(text, filename=name)
                if FIXED_SHEBANG.search(text) or FIXED_PYTHON.search(text):
                    findings['fixed_python_path'] += 1
            elif path.suffix == '.json':
                counts['json'] += 1
                json.loads(text)
            elif path.suffix == '.xml':
                counts['xml'] += 1
                ET.fromstring(text)
            elif path.suffix in {'.js', '.cjs', '.mjs'}:
                counts['javascript'] += 1
                result = subprocess.run(
                    ['node', '--check', str(path)], capture_output=True, timeout=30,
                    cwd=root,
                )
                if result.returncode:
                    findings['javascript_syntax'] += 1
        except (SyntaxError, ValueError, ET.ParseError):
            findings['source_syntax'] += 1
        except (OSError, subprocess.TimeoutExpired):
            findings['syntax_tool_unavailable'] += 1
    if not counts['files']:
        findings['empty_inventory'] += 1
    return {'counts': dict(counts), 'findings': dict(findings),
            'safe': not findings, 'application_runtime_tests': 'NOT_RUN'}


def main():
    # Include untracked non-ignored candidates locally; CI inspects the checkout.
    inventory = subprocess.run(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode('utf-8').split('\0')
    result = check(ROOT, [name for name in inventory if name])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['safe'] else 1


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    raise SystemExit(main())
