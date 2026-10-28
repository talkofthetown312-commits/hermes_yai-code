"""Phase 3 integration over the existing offline, project-scoped Pocket core.
Only the explicit synthetic staging launcher registers this service.
"""
import time
from evolution import Conflict, Denied
from evolution_api import EvolutionService

VIEWS = ('dashboard', 'memory', 'skills', 'conversation', 'files', 'advanced')


class IntegrationService(EvolutionService):
    def __init__(self, data, stage):
        super().__init__(data, stage)
        self.project = 'phase3-synthetic'
        with self.store.db() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS integration_ui(
                project TEXT, principal TEXT, view TEXT, revision INTEGER NOT NULL,
                PRIMARY KEY(project, principal))''')
            row = connection.execute('SELECT id FROM evidence WHERE project=? LIMIT 1',
                                     (self.project,)).fetchone()
        self.evidence_id = row[0] if row else self.dataset.evidence(
            self.session(), [{'expected': 'SYNTHETIC_FIXTURE_OK',
                              'actual': self.examples[1]['content']}], self.examples)

    def preferences(self):
        session = self.session()
        session.check()
        with self.store.db() as connection:
            row = connection.execute(
                'SELECT view,revision FROM integration_ui WHERE project=? AND principal=?',
                (session.project, session.principal)).fetchone()
        return dict(row) if row else {'view': 'dashboard', 'revision': 0}

    def dashboard(self):
        session = self.session()
        session.check()
        counts = {key: 0 for key in ('draft', 'tested', 'approved', 'revoked', 'expired')}
        with self.store.db() as connection:
            for row in connection.execute('SELECT state,expires FROM skills WHERE project=?',
                                          (session.project,)):
                state = ('expired' if row['state'] == 'approved' and
                         (not row['expires'] or row['expires'] <= time.time()) else row['state'])
                if state in counts:
                    counts[state] += 1
            audit_count = connection.execute('SELECT count(*) FROM audit WHERE project=?',
                                             (session.project,)).fetchone()[0]
        return {'stage_only': True, 'synthetic_only': True, 'phase': 3,
                'project': session.project, 'skills': counts, 'audit_events': audit_count,
                'granted_sources': len(self.store.scopes(session)),
                'preferences': self.preferences(), 'agent': 'disabled',
                'providers': 'disabled', 'training': 'disabled',
                'scheduler': 'not_started', 'reuse': 'guidance_only',
                'native_verification': 'NOT_VERIFIED'}

    def set_preferences(self, body):
        session = self.session()
        session.check(True)
        if (not isinstance(body, dict) or set(body) != {'view', 'revision', 'confirm'}
                or body['view'] not in VIEWS or type(body['revision']) is not int
                or body['revision'] < 0 or body['confirm'] is not True):
            raise Denied('Exact confirmed navigation revision required')
        with self.store.db() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT revision FROM integration_ui WHERE project=? AND principal=?',
                                     (session.project, session.principal)).fetchone()
            revision = row[0] if row else 0
            if revision != body['revision']:
                raise Conflict('Navigation changed in another window; refresh')
            connection.execute('INSERT OR REPLACE INTO integration_ui VALUES(?,?,?,?)',
                               (session.project, session.principal, body['view'], revision + 1))
        return {'view': body['view'], 'revision': revision + 1}
