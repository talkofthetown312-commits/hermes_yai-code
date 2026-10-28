#!/usr/bin/env python3
"""Private preservation + staged source creation; never imports live Pocket."""
import hashlib, json, os, shutil, sqlite3, stat, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent
HOME = Path.home()
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()
def private_json(p, v):
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    p.write_text(json.dumps(v,indent=2)); p.chmod(0o600)
def main():
    os.umask(0o077)
    manifest=json.loads((ROOT/'preservation/manifest.json').read_text())
    verification=json.loads((ROOT/'preservation/verification.json').read_text())
    assert sha(ROOT/'preservation/manifest.json')==verification['manifest_sha256']
    payload=ROOT/'preservation/payload'
    for e in manifest['files']:
        p=payload/e['relative']
        assert not p.is_symlink() and sha(p)==e['sha256'], e['relative']
        assert stat.S_IMODE(p.stat().st_mode)==0o600
    stage=ROOT/'implementation'
    assert not stage.exists(), 'Refuse to overwrite a prior implementation'
    stage.mkdir(mode=0o700)
    backup=stage/'prechange-backup'; backup.mkdir(mode=0o700)
    rows=[]; preserved=[]; catalog=[]; copied=[]; schemas={}
    exclusions=[]
    for e in manifest['files']:
        rel=e['relative']; src=Path(e['source'])
        if not src.exists():
            exclusions.append({'relative':rel,'reason':'source no longer present; baseline retained'}); continue
        assert not src.is_symlink()
        if e['kind']=='sqlite-online-backup':
            # Do not duplicate historical DB backups; verified baseline already preserves them.
            if 'backup' in rel or 'preservation-' in rel:
                exclusions.append({'relative':rel,'reason':'historical snapshot already verified'}); continue
            dst=backup/rel; dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            c=sqlite3.connect(src.as_uri()+'?mode=ro',uri=True,timeout=3)
            d=sqlite3.connect(dst)
            try:
                c.execute('PRAGMA query_only=ON'); c.backup(d)
                assert d.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
                tables={r[0]:d.execute('SELECT COUNT(*) FROM "'+r[0].replace('"','""')+'"').fetchone()[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                schemas[rel]={r[0]:[x[1] for x in d.execute('PRAGMA table_info("'+r[0].replace('"','""')+'")')] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '%fts%' AND name NOT LIKE 'sqlite_%'")}
            finally: d.close(); c.close()
            dst.chmod(0o600)
            rows.append({'source':str(src),'relative':rel,'sha256':sha(dst),'tables':tables})
            continue
        # Credential/signing material stays solely in its already verified private baseline.
        if any(s in rel.lower() for s in ('signing/','config.before','auth.json','oauth','token','.env','.p12','.jks','secret','pairing')):
            exclusions.append({'relative':rel,'reason':'credential material not copied; verified baseline retained'}); continue
        if rel.endswith(('.apk','.lock')) or rel=='.hermes/skills/.usage.json': continue
        current=sha(src)
        dst=backup/rel; dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        shutil.copyfile(src,dst); dst.chmod(0o600); assert sha(dst)==current
        preserved.append({'source':str(src),'relative':rel,'sha256':current})
        if rel.startswith('hermes-pocket/'):
            target=stage/'pocket'/rel.removeprefix('hermes-pocket/')
            target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            shutil.copyfile(src,target); target.chmod(0o600)
            copied.append({'path':str(target.relative_to(stage)),'sha256':current})
        if rel.startswith('.hermes/skills/') and rel.endswith('/SKILL.md') and '/.archive/' not in rel and '/.curator_backups/' not in rel:
            catalog.append({'id':src.parent.name,'path':str(src),'sha256':current,'state':'legacy_reference','approved':False})
    assert len(catalog)==23
    for p in [HOME/'.jcode/config.toml',HOME/'local-ai/models/qwen.gguf']:
        if p.exists(): preserved.append({'source':str(p),'relative':str(p.relative_to(HOME)),'sha256':sha(p),'note':'hash only; no credential/model copy'})
    private_json(stage/'prechange-manifest.json',{'at':time.time(),'files':preserved,'databases':rows,'exclusions':exclusions,'baseline_payloads_verified':len(manifest['files'])})
    private_json(stage/'pocket-baseline.json',copied)
    private_json(stage/'skill-catalog.json',catalog)
    private_json(stage/'source-schemas.json',schemas)
    private_json(stage/'STAGING_AUTHORIZATION.json',{'scope':'synthetic isolated implementation','live_deployment':False,'cloud':False,'training':False,'jcode':'disabled_until_private_antigravity_reauthentication','qwen':'separate resource-gated test; no service changes'})
    print(json.dumps({'stage':str(stage),'baseline_payloads_verified':len(manifest['files']),'fresh_databases':len(rows),'preservation_hashes':len(preserved),'active_skills':len(catalog),'pocket_source_files':len(copied),'schemas':schemas},indent=2))
if __name__=='__main__': main()
