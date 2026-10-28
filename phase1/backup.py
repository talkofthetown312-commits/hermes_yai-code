#!/usr/bin/env python3
"""One-shot private preservation snapshot; originals opened read-only, never restored."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
HH = Path(os.environ.get('HERMES_HOME', str(HOME/'.hermes'))).resolve()
BACKUP = ROOT/'preservation'
DB_EXT = {'.db', '.sqlite', '.sqlite3'}
EXCLUDES = {'node_modules', '.git', '.gradle', 'build', '__pycache__'}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def private_json(p, value):
    with p.open('x') as f:
        json.dump(value, f, indent=2)
    p.chmod(0o600)


def main():
    os.umask(0o077)
    ROOT.chmod(0o700)
    BACKUP.mkdir(mode=0o700)
    payload=BACKUP/'payload'; payload.mkdir(mode=0o700)
    sources=set(); omitted=[]
    def add_tree(root, excluded=frozenset()):
        if not root.exists():
            omitted.append({'path': str(root), 'reason':'absent'}); return
        for base, dirs, files in os.walk(root, followlinks=False):
            for d in list(dirs):
                p=Path(base)/d
                if d in excluded or p.is_symlink():
                    dirs.remove(d)
                    omitted.append({'path':str(p), 'reason':'excluded generated directory or symlink'})
            for name in files:
                p=Path(base)/name
                if name.endswith(('-wal','-shm','-journal')):
                    omitted.append({'path':str(p),'reason':'SQLite companion captured using online backup API'}); continue
                if p.is_symlink():
                    raise RuntimeError('Unexpected symlink: '+str(p))
                if p.is_file(): sources.add(p)
    for name in ['memories','memory','skills','digital-twin','scripts','cron']:
        add_tree(HH/name)
    for name in ['state.db','kanban.db','config.yaml']:
        p=HH/name
        if p.exists(): sources.add(p)
    add_tree(HOME/'.hermes-pocket')
    add_tree(HOME/'hermes-pocket', EXCLUDES)
    # Database preservation includes historical local-ai backup DBs, but not model weights.
    for base, dirs, files in os.walk(HOME/'local-ai', followlinks=False):
        dirs[:]=[d for d in dirs if d not in EXCLUDES and d!='models']
        for name in files:
            p=Path(base)/name
            if p.is_symlink(): raise RuntimeError('Unexpected local-ai symlink')
            if p.suffix in DB_EXT or p.suffix in {'.py','.sh','.md','.txt','.json'}:
                sources.add(p)
    estimate=sum(p.stat().st_size for p in sources)
    if shutil.disk_usage(ROOT).free < estimate*3+512*1024*1024:
        raise RuntimeError('Insufficient preservation and restore-verification headroom')
    manifest={'started_at':datetime.now(timezone.utc).isoformat(), 'hermes_home':str(HH),
              'sqlite_consistency':'Per-database online backup; not a global multi-store transaction.',
              'sensitivity':'PRIVATE: includes business records, history and existing private preservation/key material. Never share with JCode or a provider.',
              'original_models':'Excluded and untouched; no model replacement.', 'files':[], 'omitted':omitted}
    for p in sorted(sources):
        rel=p.relative_to(HOME)
        dst=payload/rel;dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        entry={'source':str(p),'relative':str(rel),'source_mode':oct(stat.S_IMODE(p.stat().st_mode))}
        if p.suffix in DB_EXT:
            began=time.monotonic()
            src=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=10)
            src.execute('PRAGMA query_only=ON')
            target=sqlite3.connect(dst)
            def progress(status,remaining,total):
                if time.monotonic()-began>120: raise TimeoutError('SQLite backup deadline exceeded')
            try:
                src.backup(target,pages=256,progress=progress,sleep=0.05)
                integrity=[r[0] for r in target.execute('PRAGMA integrity_check')]
                if integrity!=['ok']:raise RuntimeError('Snapshot integrity check failed: '+str(p))
                tables=[r[0] for r in target.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
                counts={t:target.execute('SELECT COUNT(*) FROM "'+t.replace('"','""')+'"').fetchone()[0] for t in tables}
                entry.update(kind='sqlite-online-backup',integrity='ok',rows=counts)
            finally:
                target.close();src.close()
        else:
            for attempt in range(3):
                before=sha(p);shutil.copyfile(p,dst);after=sha(p)
                if before==after==sha(dst):break
            else:raise RuntimeError('File was not stable during snapshot: '+str(p))
            entry.update(kind='byte-copy',source_sha256=before)
        dst.chmod(0o600)
        entry.update(sha256=sha(dst),bytes=dst.stat().st_size)
        manifest['files'].append(entry)
    manifest['finished_at']=datetime.now(timezone.utc).isoformat()
    private_json(BACKUP/'manifest.json',manifest)
    checks=[]
    for e in manifest['files']:
        p=payload/e['relative']
        checks.append(sha(p)==e['sha256'])
        checks.append(stat.S_IMODE(p.stat().st_mode)==0o600)
    restore=BACKUP/'restore-drill';restore.mkdir(mode=0o700)
    drill=[]
    # Restore only into a throwaway private tree, never over originals.
    for e in manifest['files']:
        if e['kind']!='sqlite-online-backup':continue
        dst=restore/e['relative'];dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copyfile(payload/e['relative'],dst);dst.chmod(0o600)
        assert sha(dst)==e['sha256']
        db=sqlite3.connect(dst.as_uri()+'?mode=ro',uri=True)
        try:
            assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
            for t,n in e['rows'].items():
                assert db.execute('SELECT COUNT(*) FROM "'+t.replace('"','""')+'"').fetchone()[0]==n
        finally:db.close()
        drill.append(e['relative'])
    assert all(checks)
    summary={'passed':True,'files':len(manifest['files']),'snapshot_bytes':sum(e['bytes'] for e in manifest['files']),
             'sha256_and_permission_checks':len(checks),'sqlite_snapshots_and_restore_drills':len(drill),
             'restored_databases':drill,'manifest_sha256':sha(BACKUP/'manifest.json'),
             'originals_restored_or_modified':False,'model_weights_copied_or_loaded':False,
             'finished_at':datetime.now(timezone.utc).isoformat()}
    private_json(BACKUP/'verification.json',summary)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
