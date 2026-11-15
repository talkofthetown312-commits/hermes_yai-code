"""Real-source workbench and observed best-effort extraction; no fixture imports."""
import json
from pathlib import Path
import re
import threading
import time

from evolution import (Store, Session, Source, Retrieval, Workbench, Dataset,
                       Denied, digest, file_hash, safe_path, PII, packed)
from evolution_api import EvolutionService
from evolution_maintenance import Extractor
from hermes_runtime.core import Rejected


class Service(EvolutionService):
    def __init__(self, data, config):
        self.data = Path(data)
        self.project = config.get('project', 'personal')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', self.project):
            raise Rejected('Invalid project')
        self.store = Store(self.data / 'evolution')
        self.manifest = {'sources': []}
        sources = []
        for entry in config.get('sources', []):
            if set(entry) != {'id', 'kind', 'path', 'root', 'records'}:
                raise Rejected('Source requires id, kind, path, root, records')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', entry['id']):
                raise Rejected('Invalid source ID')
            if (not isinstance(entry['records'], list) or not 1 <= len(entry['records']) <= 200
                    or any(not isinstance(r, str) or not r or r == '*' for r in entry['records'])):
                raise Rejected('Select up to 200 exact source records')
            source = Source(entry['id'], entry['kind'], Path(entry['path']), Path(entry['root']))
            safe_path(source.path, source.root)
            sources.append(source)
            self.manifest['sources'].append({'id': source.id, 'records': entry['records']})
        self.retrieval = Retrieval(self.store, sources)
        self.workbench = Workbench(self.store)
        self.dataset = Dataset(self.store, allow_personal=True)
        self.extractor = Extractor(self.store, 'runtime')
        self.guard = threading.RLock()
        self.stop = threading.Event()
        self.heartbeat = None
        self.schedule_path = self.data / 'schedule.json'
        if self.schedule_path.is_symlink():
            raise Rejected('Symlink schedule refused')
        self.schedule = json.loads(self.schedule_path.read_text()) if self.schedule_path.exists() else {
            'enabled': False, 'interval_seconds': 21600, 'next_run': None,
            'last_run': None, 'last_status': 'not_run', 'completed': 0, 'missed': 0}
        self.thread = threading.Thread(target=self._ticker, daemon=True)
        self.thread.start()

    def health(self):
        with self.guard:
            return {**self.schedule, 'heartbeat': self.heartbeat,
                    'ticker': 'observed_recent' if self.heartbeat and time.time() - self.heartbeat < 120 else 'not_observed',
                    'guarantee': 'best_effort_while_runtime_is_running',
                    'sleep_restart_validation': 'requires_device_test'}

    def _persist(self):
        temporary = self.schedule_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.schedule))
        temporary.chmod(0o600)
        temporary.replace(self.schedule_path)

    def _ticker(self):
        while not self.stop.is_set():
            self.tick()
            self.stop.wait(1)

    def tick(self, now=None):
        now = time.time() if now is None else now
        with self.guard:
            self.heartbeat = now
            nxt = self.schedule['next_run']
            if not self.schedule['enabled'] or nxt is None or now < nxt:
                return
            interval = self.schedule['interval_seconds']
            self.schedule['missed'] += max(0, int((now - nxt) // interval))
            self.schedule['next_run'] = now + interval
            self.schedule['last_run'] = now
            try:
                self.extract()
                self.schedule['last_status'] = 'ok'
                self.schedule['completed'] += 1
            except (ValueError, OSError):
                self.schedule['last_status'] = 'failed'
            self._persist()

    def extract(self):
        s = self.session()
        queued = 0
        # Local retrieval consent alone does not authorize extraction.
        for sid, ids in self.store.scopes(s, 'memory').items():
            source = self.retrieval.sources[sid]
            for rid, content, role, stamp, session in self.retrieval.records(source, ids):
                if role != 'user' or stamp is None or session is None:
                    continue
                key = digest([sid, rid, content])[:48]
                result = self.extractor.run(s, key, [{'id': 1, 'session_id': session,
                    'role': role, 'timestamp': stamp, 'content': content}], True, time.time())
                queued += result['queued']
        return {'queued': queued, 'live_memory_written': False}

    def get(self, path, query):
        if path == 'state':
            s = self.session()
            with self.store.db() as c:
                rows = c.execute('SELECT id,hash,review,revoked FROM candidates WHERE project=?', (s.project,))
                candidates = [{'id': r['id'], 'hash': r['hash'], 'reviewed': bool(r['review']),
                               'revoked': bool(r['revoked'])} for r in rows]
            return {'stage_only': False, 'synthetic_only': False, 'project': s.project,
                    'skills': self.workbench.library(s), 'candidates': candidates,
                    'source_choices': [{'source_id': e['id'], 'records': e['records']}
                                       for e in self.manifest['sources']],
                    'grants': {k: sorted(v) for k, v in self.store.scopes(s).items()},
                    'scheduler': self.health(), 'jcode': 'advisory_model_proposals',
                    'training': 'external_host_runner_required', 'execution': 'guidance_only_no_tools'}
        if path == 'memory-candidates':
            return self.extractor.candidates(self.session())
        return super().get(path, query)

    def post(self, path, body):
        s = self.session()
        with self.guard:
            if path == 'grant':
                if set(body) - {'source', 'records', 'purpose', 'confirm'}:
                    raise Denied('Unexpected grant fields')
                purpose = body.get('purpose', 'local')
                choices = next((e['records'] for e in self.manifest['sources'] if e['id'] == body.get('source')), [])
                records = body.get('records')
                if (body.get('confirm') is not True or not isinstance(records, list)
                        or not records or not set(records) <= set(choices)
                        or purpose not in {'local', 'memory'}):
                    raise Denied('Exact records and purpose required')
                self.store.grant(s, body['source'], records, purpose)
                return {'ok': True}
            if path == 'schedule':
                if (set(body) != {'enabled', 'interval_seconds', 'confirm'} or body['confirm'] is not True
                        or type(body['enabled']) is not bool or type(body['interval_seconds']) is not int
                        or not 60 <= body['interval_seconds'] <= 604800):
                    raise Denied('Confirm a schedule between 60 seconds and one week')
                self.schedule.update(enabled=body['enabled'], interval_seconds=body['interval_seconds'],
                                     next_run=time.time() + body['interval_seconds'] if body['enabled'] else None)
                self._persist()
                return self.health()
            if path == 'extract':
                if body != {'confirm': True}:
                    raise Denied('Confirm extraction')
                return self.extract()
            if path == 'review-memory':
                if set(body) != {'id', 'hash', 'decision', 'confirm'}:
                    raise Denied('Exact review required')
                return self.extractor.review(s, body['id'], body['hash'], body['decision'], body['confirm'])
            if path == 'accept-correction':
                if (set(body) != {'messages', 'license', 'confirm'} or body['confirm'] is not True
                        or not isinstance(body['license'], str) or not 1 <= len(body['license']) <= 200):
                    raise Denied('Review and accept an exact correction and its license')
                messages = body['messages']
                self.dataset.validate(messages)
                if PII.search(packed(messages)):
                    raise Denied('Remove personal identifiers before accepting the correction')
                # Human acceptance is explicit correction evidence, never model success evidence.
                eid = self.dataset.evidence(s, [{'expected': digest(messages), 'actual': digest(messages)}],
                    messages, license=body['license'], correction={'accepted': True,
                    'kind': 'human_reviewed_correction', 'principal': s.principal})
                return self.dataset.select(s, messages, eid, True, source='accepted_correction')
            if path in {'select-example', 'extract-fixture', 'jcode'}:
                raise Denied('Historical fixture/disabled broker route unavailable in runtime')
            return super().post(path, body)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
