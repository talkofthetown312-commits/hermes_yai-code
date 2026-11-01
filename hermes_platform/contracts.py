"""Bounded task and model contracts shared by the API and scheduler."""
import ast
import json
from pathlib import PurePosixPath

from evolution_addons.hybrid import PolicyError, fingerprint, text

ROLES = ('coordinator', 'memory', 'research', 'developer', 'validator', 'reviewer')
MODEL_ROLES = tuple(role for role in ROLES if role != 'memory')
SCHEMAS = {
    'coordinator': {'summary': 'text', 'assignments': {'research': 'instruction', 'developer': 'instruction'}},
    'research': {'summary': 'text', 'findings': ['text']},
    'developer': {'summary': 'text', 'artifacts': [{'path': 'relative/path.py', 'content': 'source text'}]},
    'validator': {'summary': 'text', 'passed': True, 'issues': ['text']},
    'reviewer': {'summary': 'text', 'approved': True, 'risks': ['text']},
}


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise PolicyError('Duplicate JSON field')
            result[key] = value
        return result
    def invalid(value):
        raise PolicyError('Non-finite JSON number')
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)
    except (ValueError, TypeError, RecursionError) as error:
        raise PolicyError('Invalid JSON object') from error


def bounded(value, limit=16000):
    if not isinstance(value, str) or len(value.encode()) > limit or '\x00' in value:
        raise PolicyError('Invalid bounded text')
    return value


def task_input(body):
    if not isinstance(body, dict) or set(body) != {'prompt', 'cloud_consent', 'memory_sources'}:
        raise PolicyError('Expected prompt, cloud_consent and memory_sources')
    text(body['prompt'])
    if type(body['cloud_consent']) is not bool:
        raise PolicyError('Cloud consent must be boolean')
    sources = body['memory_sources']
    if (not isinstance(sources, list) or len(sources) > 8
            or any(not isinstance(x, str) or not x.isidentifier() for x in sources)
            or len(set(sources)) != len(sources)):
        raise PolicyError('Invalid registered memory sources')
    if sources and body['cloud_consent']:
        raise PolicyError('Tasks with memory access must remain local')
    return body


def artifact_path(value):
    bounded(value, 240)
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or '..' in path.parts or '\\' in value
            or any(p.startswith('.') for p in path.parts)
            or any(ord(c) < 32 for c in value)):
        raise PolicyError('Unsafe artifact path')
    return value


def output(role, value):
    if not isinstance(value, dict) or set(value) != set(SCHEMAS[role]):
        raise PolicyError('Unexpected agent output schema')
    text(value['summary'])
    if role == 'coordinator':
        assignments = value['assignments']
        if not isinstance(assignments, dict) or set(assignments) != {'research', 'developer'}:
            raise PolicyError('Research and developer delegation required')
        for instruction in assignments.values():
            text(instruction)
    elif role == 'developer':
        artifacts = value['artifacts']
        if not isinstance(artifacts, list) or not 1 <= len(artifacts) <= 8:
            raise PolicyError('Expected one to eight proposed artifacts')
        paths = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict) or set(artifact) != {'path', 'content'}:
                raise PolicyError('Unexpected artifact schema')
            path = artifact_path(artifact['path'])
            if path in paths:
                raise PolicyError('Duplicate artifact path')
            paths.add(path)
            bounded(artifact['content'], 32000)
    else:
        key = {'research': 'findings', 'validator': 'issues', 'reviewer': 'risks'}[role]
        if not isinstance(value[key], list) or len(value[key]) > 32:
            raise PolicyError('Invalid findings list')
        for item in value[key]:
            text(item)
        decision = {'validator': 'passed', 'reviewer': 'approved'}.get(role)
        if decision and type(value[decision]) is not bool:
            raise PolicyError('Explicit boolean decision required')
    if len(json.dumps(value).encode()) > 98304:
        raise PolicyError('Agent output exceeds budget')
    return value


def validate_artifacts(artifacts):
    """Deterministic syntax checks, never execute model-generated source."""
    checks = []
    for artifact in artifacts:
        path = artifact_path(artifact['path'])
        suffix = PurePosixPath(path).suffix
        kind = {'.py': 'python-syntax', '.json': 'json-syntax'}.get(suffix, 'text-only')
        passed = True
        try:
            if suffix == '.py':
                ast.parse(artifact['content'], filename=path)
            elif suffix == '.json':
                strict_json(artifact['content'])
        except (SyntaxError, ValueError, RecursionError):
            passed = False
        checks.append({'path': path, 'check': kind, 'passed': passed,
                       'hash': fingerprint(artifact), 'executed': False})
    return checks
