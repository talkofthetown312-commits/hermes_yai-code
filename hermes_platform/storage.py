"""Private platform-owned state; no existing Hermes database is opened."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import time
import uuid

from .contracts import PolicyError, ROLES, fingerprint, task_input

MARKER = 'hermes-evolution-platform-v1'


def no_alias(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise PolicyError('Symlink paths refused')
    return path


def private_file(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(content)


def owned_file(path):
    info = no_alias(path).stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o077):
        raise PolicyError('Private owner-only regular file required')


def prepare(directory):
    root = no_alias(directory)
    if root.name in {'.hermes', '.jcode'} or any(p.name in {'.hermes', '.jcode'} for p in root.parents):
        raise PolicyError('Choose a separate platform state directory')
    if root.exists():
        marker = root / 'platform-marker'
        if not marker.exists():
            if any(root.iterdir()):
                raise PolicyError('Existing unowned directory refused')
        else:
            owned_file(marker)
            if marker.read_text() != MARKER:
                raise PolicyError('Foreign platform directory refused')
        info = root.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise PolicyError('State directory must be owner-only (0700)')
    else:
        root.mkdir(parents=True, mode=0o700)
    marker = root / 'platform-marker'
    if not marker.exists():
        private_file(marker, MARKER)
    for name, content in [('pairing-token', secrets.token_urlsafe(32)), ('tasks.sqlite3', '')]:
        path = root / name
        if not path.exists():
            private_file(path, content)
        owned_file(path)
    for suffix in ('-wal', '-shm', '-journal'):
        path = root / ('tasks.sqlite3' + suffix)
        if path.exists() or path.is_symlink():
            owned_file(path)
    return root


class Store:
    def __init__(self, directory):
        self.root = prepare(directory)
        self.path = self.root / 'tasks.sqlite3'
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS tasks(
              id TEXT PRIMARY KEY, prompt TEXT NOT NULL, cloud INTEGER NOT NULL,
              sources TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
              created REAL NOT NULL, updated REAL NOT NULL, result_hash TEXT);
            CREATE TABLE IF NOT EXISTS steps(
              task TEXT NOT NULL REFERENCES tasks(id), role TEXT NOT NULL,
              status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
              output TEXT, error TEXT, retry_at REAL NOT NULL DEFAULT 0,
              PRIMARY KEY(task,role));
            CREATE TABLE IF NOT EXISTS messages(
              seq INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT NOT NULL REFERENCES tasks(id),
              sender TEXT NOT NULL, recipient TEXT NOT NULL, kind TEXT NOT NULL,
              body TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS approvals(
              task TEXT PRIMARY KEY REFERENCES tasks(id), result_hash TEXT NOT NULL,
              accepted INTEGER NOT NULL, created REAL NOT NULL);
            ''')

    @contextmanager
    def db(self):
        owned_file(self.path)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def message(db, task, sender, recipient, kind, body):
        db.execute('INSERT INTO messages(task,sender,recipient,kind,body,created) VALUES(?,?,?,?,?,?)',
                   (task, sender, recipient, kind, json.dumps(body), time.time()))

    def create(self, body):
        task_input(body)
        identifier = uuid.uuid4().hex
        now = time.time()
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # Bound retained jobs and pending work; no silently unbounded queue.
            if db.execute('SELECT count(*) FROM tasks').fetchone()[0] >= 1000:
                raise PolicyError('Task storage limit reached; archive this isolated workspace')
            db.execute('INSERT INTO tasks(id,prompt,cloud,sources,status,created,updated) VALUES(?,?,?,?,?,?,?)',
                       (identifier, body['prompt'], body['cloud_consent'], json.dumps(body['memory_sources']), 'queued', now, now))
            for role in ROLES:
                db.execute('INSERT INTO steps(task,role,status) VALUES(?,?,?)', (identifier, role, 'pending'))
            self.message(db, identifier, 'user', 'coordinator', 'request', {'text': body['prompt']})
        return self.get(identifier)

    def get(self, identifier):
        with self.db() as db:
            row = db.execute('SELECT * FROM tasks WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise KeyError('Task not found')
            result = dict(row)
            result['cloud_consent'] = bool(result.pop('cloud'))
            result['memory_sources'] = json.loads(result.pop('sources'))
            steps = {row['role']: dict(row) for row in db.execute('SELECT * FROM steps WHERE task=?', (identifier,))}
            result['steps'] = [steps[role] for role in ROLES]
            for step in result['steps']:
                step['output'] = json.loads(step['output']) if step['output'] else None
            result['messages'] = [dict(row) for row in db.execute('SELECT * FROM messages WHERE task=? ORDER BY seq', (identifier,))]
            for message in result['messages']:
                message['body'] = json.loads(message['body'])
            return result

    def listing(self):
        with self.db() as db:
            return [dict(row) for row in db.execute('SELECT id,prompt,status,revision,created,updated FROM tasks ORDER BY created DESC LIMIT 100')]

    def recover(self):
        # Only call while owning the server process lock. No concurrent scheduler.
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute("SELECT task,role,attempts FROM steps WHERE status='running'").fetchall()
            for row in rows:
                failed = row['attempts'] >= 3
                db.execute('UPDATE steps SET status=?,error=? WHERE task=? AND role=?',
                           ('failed' if failed else 'pending', 'interrupted', row['task'], row['role']))
                db.execute('UPDATE tasks SET status=?,revision=revision+1,updated=? WHERE id=?',
                           ('failed' if failed else 'queued', time.time(), row['task']))
                self.message(db, row['task'], 'system', row['role'], 'recovery', {'reason': 'interrupted'})

    def claim(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            tasks = db.execute("SELECT id FROM tasks WHERE status IN ('queued','running') ORDER BY updated").fetchall()
            for task in tasks:
                rows = {r['role']: r for r in db.execute('SELECT * FROM steps WHERE task=?', (task['id'],))}
                for role in ROLES:
                    step = rows[role]
                    if step['status'] == 'done':
                        continue
                    if step['status'] != 'pending' or step['retry_at'] > time.time():
                        break
                    db.execute("UPDATE steps SET status='running',attempts=attempts+1 WHERE task=? AND role=?", (task['id'], role))
                    db.execute("UPDATE tasks SET status='running',updated=?,revision=revision+1 WHERE id=?", (time.time(), task['id']))
                    self.message(db, task['id'], 'coordinator', role, 'started', {'attempt': step['attempts'] + 1})
                    return task['id'], role
        return None

    def finish(self, identifier, role, value):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM tasks WHERE id=?', (identifier,)).fetchone()
            if row['status'] != 'running':
                return  # Cancellation wins; late results cannot revive a task.
            db.execute("UPDATE steps SET status='done',output=?,error=NULL WHERE task=? AND role=?",
                       (json.dumps(value), identifier, role))
            next_role = ROLES[ROLES.index(role) + 1] if role != 'reviewer' else 'user'
            self.message(db, identifier, role, next_role, 'result', value)
            status, result_hash = 'queued', None
            if role == 'coordinator':
                for recipient, instruction in value['assignments'].items():
                    self.message(db, identifier, role, recipient, 'delegation', {'instruction': instruction})
            if role == 'reviewer':
                validator = json.loads(db.execute("SELECT output FROM steps WHERE task=? AND role='validator'", (identifier,)).fetchone()[0])
                status = 'awaiting_approval' if value['approved'] and validator['passed'] else 'rejected'
                outputs = [(r['role'], json.loads(r['output'])) for r in db.execute('SELECT role,output FROM steps WHERE task=? ORDER BY role', (identifier,))]
                result_hash = fingerprint(outputs)
            db.execute('UPDATE tasks SET status=?,result_hash=?,revision=revision+1,updated=? WHERE id=?',
                       (status, result_hash, time.time(), identifier))

    def fail(self, identifier, role, reason, retryable=False):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT status FROM tasks WHERE id=?', (identifier,)).fetchone()[0] != 'running':
                return
            attempt = db.execute('SELECT attempts FROM steps WHERE task=? AND role=?', (identifier, role)).fetchone()[0]
            retry = retryable and attempt < 3
            db.execute('UPDATE steps SET status=?,error=?,retry_at=? WHERE task=? AND role=?',
                       ('pending' if retry else 'failed', reason, time.time() + min(2 ** attempt, 8), identifier, role))
            db.execute('UPDATE tasks SET status=?,revision=revision+1,updated=? WHERE id=?',
                       ('queued' if retry else 'failed', time.time(), identifier))
            self.message(db, identifier, role, 'coordinator', 'retry' if retry else 'failure', {'reason': reason, 'attempt': attempt})

    def decision(self, identifier, revision, action, result_hash=None):
        if type(revision) is not int or action not in {'cancel', 'approve', 'reject'}:
            raise PolicyError('Invalid task decision')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            task = db.execute('SELECT * FROM tasks WHERE id=?', (identifier,)).fetchone()
            if task is None:
                raise KeyError('Task not found')
            if task['revision'] != revision:
                raise PolicyError('Task changed; refresh before deciding')
            if action == 'cancel':
                if task['status'] not in {'queued', 'running', 'awaiting_approval'}:
                    raise PolicyError('Task is already terminal')
                status = 'cancelled'
                db.execute("UPDATE steps SET status='cancelled' WHERE task=? AND status IN ('pending','running')", (identifier,))
            else:
                if task['status'] != 'awaiting_approval' or result_hash != task['result_hash']:
                    raise PolicyError('Approval requires the current reviewed result')
                status = 'approved' if action == 'approve' else 'rejected'
                db.execute('INSERT INTO approvals VALUES(?,?,?,?)', (identifier, result_hash, action == 'approve', time.time()))
            db.execute('UPDATE tasks SET status=?,revision=revision+1,updated=? WHERE id=?', (status, time.time(), identifier))
            self.message(db, identifier, 'user', 'coordinator', action, {'result_hash': result_hash})
        return self.get(identifier)
