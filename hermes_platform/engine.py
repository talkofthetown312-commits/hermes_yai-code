"""Persistent six-agent task delegation with bounded recovery."""
import threading

from .contracts import PolicyError, ROLES, output, validate_artifacts
from .memory import MemoryAdapter
from .models import ModelError


class Engine:
    def __init__(self, store, router, memory=None):
        self.store, self.router = store, router
        self.memory = memory or MemoryAdapter()
        self.stop = threading.Event()
        self.thread = None

    def create(self, body):
        from .contracts import task_input
        task_input(body)
        if any(name not in self.memory.sources for name in body['memory_sources']):
            raise PolicyError('Memory source is not authorized')
        cloud = any(r['provider'] != 'ollama' for r in self.router.routes.values())
        if cloud and (not body['cloud_consent'] or body['memory_sources']):
            raise PolicyError('Configured cloud roles require consent and no memory sources')
        return self.store.create(body)

    def tick(self):
        claimed = self.store.claim()
        if not claimed:
            return False
        identifier, role = claimed
        task = self.store.get(identifier)
        def cancelled():
            return self.stop.is_set() or self.store.get(identifier)['status'] == 'cancelled'
        try:
            if role == 'memory':
                result = self.memory.read(task['memory_sources'])
            else:
                prior = {step['role']: step['output'] for step in task['steps'] if step['status'] == 'done'}
                context = {'task_id': identifier, 'request': task['prompt'], 'shared_state': prior,
                           'messages': [m for m in task['messages'] if m['recipient'] == role]}
                result = output(role, self.router.generate(role, context, task['cloud_consent'], bool(task['memory_sources']), cancelled))
                if role == 'validator':
                    checks = validate_artifacts(prior['developer']['artifacts'])
                    result['checks'] = checks
                    result['passed'] = result['passed'] and all(c['passed'] for c in checks)
                    result['execution_tests_run'] = False
            self.store.finish(identifier, role, result)
        except ModelError as error:
            if not self.stop.is_set():
                self.store.fail(identifier, role, error.code, error.retryable)
        except (PolicyError, KeyError, OSError, ValueError):
            self.store.fail(identifier, role, 'invalid_output_or_source')
        except Exception:
            # No raw exception/provider/private data enters public diagnostics.
            self.store.fail(identifier, role, 'agent_internal_error')
        return True

    def start(self):
        self.store.recover()
        def run():
            while not self.stop.is_set():
                if not self.tick():
                    self.stop.wait(.2)
        self.thread = threading.Thread(target=run, name='hermes-scheduler', daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(5)
