import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from hermes_platform.contracts import PolicyError, ROLES, artifact_path, output, strict_json, validate_artifacts
from hermes_platform.engine import Engine
from hermes_platform.memory import MemoryAdapter
from hermes_platform.storage import Store
from hermes_platform.tests.support import FakeRouter, body


class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'isolated')
        self.router = FakeRouter()
        self.engine = Engine(self.store, self.router)

    def tearDown(self):
        self.engine.close()
        self.temp.cleanup()

    def complete(self, identifier):
        for _ in ROLES:
            self.assertTrue(self.engine.tick())
        return self.store.get(identifier)

    def test_delegation_messages_shared_state_and_hash_approval(self):
        task = self.engine.create(body())
        result = self.complete(task['id'])
        self.assertEqual(result['status'], 'awaiting_approval')
        self.assertEqual(len(result['steps']), 6)
        self.assertEqual(len([m for m in result['messages'] if m['kind'] == 'delegation']), 2)
        developer = next(context for role, context in self.router.calls if role == 'developer')
        self.assertIn('research', developer['shared_state'])
        self.assertTrue(any(m['kind'] == 'delegation' for m in developer['messages']))
        with self.assertRaises(PolicyError):
            self.store.decision(task['id'], result['revision'], 'approve', 'old-hash')
        approved = self.store.decision(task['id'], result['revision'], 'approve', result['result_hash'])
        self.assertEqual(approved['status'], 'approved')
        self.assertFalse((self.root / 'sorter.py').exists())
        with self.assertRaises(PolicyError):
            self.store.decision(task['id'], result['revision'], 'approve', result['result_hash'])

    def test_restart_preserves_completed_steps_and_recovers_inflight(self):
        task = self.engine.create(body())
        self.engine.tick()
        self.assertEqual(self.store.claim(), (task['id'], 'memory'))
        restored = Store(self.root / 'isolated')
        restored.recover()
        second = Engine(restored, self.router)
        for _ in range(5):
            second.tick()
        result = restored.get(task['id'])
        self.assertEqual(result['status'], 'awaiting_approval')
        self.assertEqual(result['steps'][0]['attempts'], 1)
        self.assertEqual(result['steps'][1]['attempts'], 2)
        self.assertTrue(any(m['kind'] == 'recovery' for m in result['messages']))

    def test_transient_retry_budget_and_permanent_failure(self):
        task = self.engine.create(body())
        self.router.failures = 5
        for _ in range(3):
            self.engine.tick()
            with self.store.db() as db:
                db.execute('UPDATE steps SET retry_at=0')
        result = self.store.get(task['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['steps'][0]['attempts'], 3)
        self.assertFalse(self.engine.tick())

    def test_cancel_wins_over_late_result(self):
        task = self.engine.create(body())
        self.store.claim()
        current = self.store.get(task['id'])
        self.store.decision(task['id'], current['revision'], 'cancel')
        self.store.finish(task['id'], 'coordinator', {})
        self.assertEqual(self.store.get(task['id'])['status'], 'cancelled')
        self.assertFalse(self.engine.tick())

    def test_task_context_isolation(self):
        first = self.engine.create(body(prompt='First synthetic request'))
        second = self.engine.create(body(prompt='Second synthetic request'))
        for _ in range(12):
            self.engine.tick()
        for _, context in self.router.calls:
            task = self.store.get(context['task_id'])
            self.assertEqual(context['request'], task['prompt'])
            self.assertTrue(all(m['task'] == task['id'] for m in context['messages']))
        self.assertNotEqual(first['id'], second['id'])

    def test_invalid_generated_python_blocks_approval_even_if_models_approve(self):
        original = self.router.generate
        def bad(role, *args):
            value = original(role, *args)
            if role == 'developer':
                value['artifacts'][0]['content'] = 'def invalid('
            return value
        self.router.generate = bad
        task = self.engine.create(body())
        result = self.complete(task['id'])
        self.assertEqual(result['status'], 'rejected')
        self.assertFalse(result['steps'][4]['output']['checks'][0]['passed'])

    def test_sources_require_registration_and_never_cloud(self):
        with self.assertRaises(PolicyError):
            self.engine.create(body(memory_sources=['private']))
        source = self.root / 'explicit.txt'; source.write_text('Synthetic local reference')
        memory = MemoryAdapter({'fixture': {'kind': 'text', 'path': str(source)}})
        engine = Engine(self.store, self.router, memory)
        with self.assertRaises(PolicyError):
            engine.create(body(memory_sources=['fixture'], cloud_consent=True))
        self.router.routes['research']['provider'] = 'gpt'
        with self.assertRaises(PolicyError):
            engine.create(body(memory_sources=['fixture']))
        self.assertEqual(self.store.listing(), [])

    def test_memory_reads_text_and_sqlite_without_mutation(self):
        source = self.root / 'memory.txt'; source.write_text('Synthetic fact')
        database = self.root / 'snapshot.sqlite'
        db = sqlite3.connect(database)
        db.execute('CREATE TABLE notes(id INTEGER, body TEXT)')
        db.execute('INSERT INTO notes VALUES(1,?)', ('Synthetic row',)); db.commit(); db.close()
        before = database.read_bytes()
        adapter = MemoryAdapter({'text': {'kind': 'text', 'path': str(source)}, 'rows': {
            'kind': 'sqlite', 'path': str(database), 'table': 'notes', 'id_column': 'id', 'text_column': 'body'}})
        result = adapter.read(['text', 'rows'])
        self.assertEqual(len(result['records']), 2)
        self.assertEqual(database.read_bytes(), before)
        self.assertFalse(Path(str(database) + '-shm').exists())
        self.assertFalse(result['cloud_allowed'])

    def test_memory_aliases_and_schema_injection_refused(self):
        source = self.root / 'source'; source.write_text('Synthetic fact')
        alias = self.root / 'alias'; alias.symlink_to(source)
        with self.assertRaises(PolicyError):
            MemoryAdapter({'test': {'kind': 'text', 'path': str(alias)}}).read(['test'])
        with self.assertRaises(PolicyError):
            MemoryAdapter({'test': {'kind': 'sqlite', 'path': str(source), 'table': 'x; DROP TABLE notes', 'id_column': 'id', 'text_column': 'body'}})

    def test_existing_data_and_insecure_paths_refused(self):
        foreign = self.root / 'foreign'; foreign.mkdir(); (foreign / 'keep').write_text('preserve')
        with self.assertRaises(PolicyError):
            Store(foreign)
        self.assertEqual((foreign / 'keep').read_text(), 'preserve')
        alias = self.root / 'alias'; alias.symlink_to(self.store.root)
        with self.assertRaises(PolicyError):
            Store(alias)
        with self.assertRaises(PolicyError):
            Store(self.root / '.hermes' / 'platform')
        self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.root.stat().st_mode & 0o777, 0o700)

    def test_contracts_reject_ambiguous_json_and_paths(self):
        for raw in ['{"a":1,"a":2}', '{"a":NaN}']:
            with self.assertRaises(PolicyError):
                strict_json(raw)
        for path in ['../escape', '/absolute', '.hermes/auth.json', 'a\\b']:
            with self.assertRaises(PolicyError):
                artifact_path(path)
        self.assertFalse(validate_artifacts([{'path': 'bad.json', 'content': '{'}])[0]['passed'])


if __name__ == '__main__':
    unittest.main()
