"""Sequential planner/worker/reviewer coordination using explicit adapters.

No SDK, network, subprocess, storage, credential discovery or patch application.
Adapters are trusted host integrations, not untrusted model-generated callables.
Synthetic mode is executable offline; live integration remains separately gated.
"""
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
import time
import uuid

from evolution_addons.free_router import NoFreeModel, select_free_models


class PolicyError(ValueError):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def text(value):
    if (not isinstance(value, str) or not value.strip()
            or len(value.encode()) > 8192
            or any(ord(c) < 32 and c not in '\n\t' for c in value)):
        raise PolicyError('Expected bounded plain text')
    if re.search(r'(?i)(<tool|tool_call|-----BEGIN .*PRIVATE KEY|\b(?:sk-|ghp_|gho_|xoxb-)[\w-]{8,}|bearer\s+[\w.-]{8,}|(?:api[_ -]?key|password|access[_ -]?token)\s*[:=]|/\.(?:hermes|jcode)(?:/|\b))', value):
        raise PolicyError('Sensitive content or tool markup rejected')
    return value


@dataclass(frozen=True)
class Agent:
    """Host-selected adapter; invoke(packet) must enforce its own hard timeout.

    The coordinator checks elapsed time after return; it cannot interrupt Python
    callbacks. Never register arbitrary user code or an unbounded provider client.
    """
    name: str
    location: str
    invoke: object


class HybridCoordinator:
    def __init__(self, planner, worker, reviewer, *, clock=time.monotonic):
        if any(not isinstance(a, Agent) or not callable(a.invoke)
               for a in (planner, worker, reviewer)):
            raise PolicyError('Three explicit host adapters required')
        if planner.location != 'local' or reviewer.location != 'local':
            raise PolicyError('Planning and review must remain local')
        if worker.location not in {'local', 'openrouter'}:
            raise PolicyError('Unsupported worker route')
        if len({a.name for a in (planner, worker, reviewer)}) != 3:
            raise PolicyError('Distinct agent identities required')
        for agent in (planner, worker, reviewer):
            text(agent.name)
        self.agents = (planner, worker, reviewer)
        self.clock = clock

    def run(self, task, *, catalog=None, catalog_observed_at=None, now=None,
            model=None, allow_cloud=False, cancelled=lambda: False):
        required = {'project', 'specification', 'synthetic', 'wall_seconds',
                    'max_output_bytes'}
        if not isinstance(task, dict) or set(task) != required:
            raise PolicyError('Strict task packet required')
        task = deepcopy(task)
        text(task['project']); text(task['specification'])
        if task['synthetic'] is not True:
            raise PolicyError('Only synthetic tasks are supported')
        if (type(task['wall_seconds']) is not int or not 1 <= task['wall_seconds'] <= 90
                or type(task['max_output_bytes']) is not int
                or not 1 <= task['max_output_bytes'] <= 98304):
            raise PolicyError('Invalid task budget')
        worker = self.agents[1]
        if worker.location == 'openrouter':
            # Authorization and catalog are supplied by the trusted host, never
            # inferred from model output or accepted as task fields.
            if allow_cloud is not True:
                raise PolicyError('Explicit cloud authorization required')
            if now is None:
                now = time.time()
            if any(type(v) not in (int, float) or not math.isfinite(v)
                   for v in (now, catalog_observed_at)):
                raise PolicyError('Verified catalog observation required')
            if not 0 <= now - catalog_observed_at <= 300:
                raise PolicyError('Catalog is stale or future dated')
            try:
                models = select_free_models(catalog, require_tools=False)
            except (ValueError, NoFreeModel) as exc:
                raise PolicyError('No verified free model available') from exc
            if model not in models:
                raise PolicyError('Explicit verified free model required')
        elif model is not None or allow_cloud:
            raise PolicyError('Cloud settings do not match local route')
        run_id = uuid.uuid4().hex
        started = self.clock()
        audit = []
        outputs = {}
        total = 0
        for role, agent in zip(('plan', 'work', 'review'), self.agents):
            remaining = task['wall_seconds'] - (self.clock() - started)
            if cancelled() or remaining <= 0:
                raise PolicyError('Task cancelled or deadline exhausted')
            packet = {'id': run_id, 'role': role, 'task': deepcopy(task),
                      'inputs': deepcopy(outputs), 'model': model if role == 'work' else None,
                      'remaining_seconds': remaining, 'tools': 'none'}
            # Adapters never receive the caller's mutable packet or audit log.
            raw = agent.invoke(deepcopy(packet))
            if cancelled() or self.clock() - started > task['wall_seconds']:
                raise PolicyError('Task cancelled or deadline exhausted')
            if not isinstance(raw, str):
                raise PolicyError('Agent must return JSON text')
            total += len(raw.encode())
            if total > task['max_output_bytes']:
                raise PolicyError('Aggregate output budget exceeded')
            try:
                result = json.loads(raw)
            except ValueError as exc:
                raise PolicyError('Invalid agent JSON') from exc
            expected = {'summary', 'steps'} if role == 'plan' else (
                {'summary', 'proposed_changes'} if role == 'work' else {'summary', 'approved', 'risks'})
            if not isinstance(result, dict) or set(result) != expected:
                raise PolicyError('Unexpected agent schema')
            text(result['summary'])
            if role == 'review':
                if type(result['approved']) is not bool:
                    raise PolicyError('Review decision must be boolean')
            key = 'steps' if role == 'plan' else ('proposed_changes' if role == 'work' else 'risks')
            if not isinstance(result[key], list) or len(result[key]) > 32:
                raise PolicyError('Expected bounded advisory list')
            for entry in result[key]:
                text(entry)
            outputs[role] = result
            audit.append({'role': role, 'agent': agent.name, 'location': agent.location,
                          'request_hash': fingerprint(packet), 'result_hash': fingerprint(result)})
        return {'id': run_id, 'project': task['project'], 'task_hash': fingerprint(task),
                'status': 'reviewed' if outputs['review']['approved'] else 'rejected',
                'outputs': outputs, 'audit': audit, 'model': model,
                'applied': False, 'deployed': False, 'provider_fallback': False}


def synthetic_coordinator():
    """Deterministic adapters exercise the protocol without claiming inference."""
    def plan(packet):
        return json.dumps({'summary': 'Synthetic plan', 'steps': ['Propose an isolated change', 'Review evidence']})
    def work(packet):
        return json.dumps({'summary': 'Synthetic proposal', 'proposed_changes': ['Add a synthetic regression fixture']})
    def review(packet):
        return json.dumps({'summary': 'Synthetic protocol review', 'approved': True,
                           'risks': ['No real model competence has been evaluated']})
    return HybridCoordinator(Agent('planner', 'local', plan),
                             Agent('worker', 'local', work),
                             Agent('reviewer', 'local', review))
