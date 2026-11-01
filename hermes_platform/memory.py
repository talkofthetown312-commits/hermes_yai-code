"""Explicit read-only memory sources. No discovery of Hermes paths or databases."""
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat

from .contracts import PolicyError
from .storage import no_alias


class MemoryAdapter:
    def __init__(self, sources=None):
        # Host configuration is explicit authorization to these exact sources.
        self.sources = sources or {}
        if not isinstance(self.sources, dict) or len(self.sources) > 8:
            raise PolicyError('Invalid memory registry')
        for name, spec in self.sources.items():
            if not name.isidentifier() or not isinstance(spec, dict):
                raise PolicyError('Invalid memory source')
            if spec.get('kind') == 'text':
                if set(spec) != {'kind', 'path'}:
                    raise PolicyError('Invalid text memory registry')
            elif spec.get('kind') == 'sqlite':
                if set(spec) != {'kind', 'path', 'table', 'id_column', 'text_column'}:
                    raise PolicyError('Invalid SQLite memory registry')
                for key in ('table', 'id_column', 'text_column'):
                    if not isinstance(spec[key], str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', spec[key]):
                        raise PolicyError('Invalid memory schema mapping')
            else:
                raise PolicyError('Unsupported memory source kind')
            if not isinstance(spec['path'], str) or not Path(spec['path']).is_absolute():
                raise PolicyError('Memory requires an explicit absolute path')

    def read(self, names):
        if any(name not in self.sources for name in names):
            raise PolicyError('Memory source has not been authorized locally')
        result = []
        for name in names:
            spec = self.sources[name]
            path = no_alias(spec['path'])
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                        or info.st_size > 16 * 1024 * 1024):
                    raise PolicyError('Memory source must be a bounded regular file')
                if spec['kind'] == 'text':
                    if info.st_size > 16000:
                        raise PolicyError('Select a smaller memory excerpt')
                    raw = os.read(fd, 16001)
                    rows = [('document', raw.decode('utf-8'))]
                else:
                    # Verify path identity before/after opening SQLite; mode=ro
                    # and query_only never create or mutate a source database.
                    if path.stat().st_ino != info.st_ino:
                        raise PolicyError('Memory path changed')
                    if any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-journal')):
                        raise PolicyError('Select a closed standalone SQLite snapshot')
                    # Pin the validated inode via the descriptor. Immutable mode
                    # avoids creating/writing SQLite shared-memory sidecars.
                    connection = sqlite3.connect(f'file:/proc/self/fd/{fd}?mode=ro&immutable=1', uri=True, timeout=1)
                    try:
                        connection.execute('PRAGMA query_only=ON')
                        connection.execute('PRAGMA trusted_schema=OFF')
                        connection.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 32768)
                        connection.set_progress_handler(lambda: 1, 100000)
                        table, identity, content = (spec[k] for k in ('table', 'id_column', 'text_column'))
                        rows = connection.execute(f'SELECT "{identity}","{content}" FROM "{table}" LIMIT 20').fetchall()
                        if path.stat().st_ino != info.st_ino:
                            raise PolicyError('Memory path changed')
                    finally:
                        connection.close()
                total = 0
                for identity, content in rows:
                    if not isinstance(content, str) or not isinstance(identity, (str, int)):
                        raise PolicyError('Unsupported memory row types')
                    total += len(content.encode())
                    if total > 16000:
                        raise PolicyError('Memory context exceeds source budget')
                    result.append({'source': name, 'record': str(identity)[:200],
                                   'content': content, 'sha256': hashlib.sha256(content.encode()).hexdigest()})
            finally:
                os.close(fd)
        return {'summary': 'Read explicitly selected local sources' if names else 'No memory access requested',
                'records': result, 'cloud_allowed': False}
