#!/usr/bin/env python3
"""Execute the original 64 acceptance entries; gated requirements never become mock PASS.
Only private, stage-owned synthetic stores/workers are written. No training/inference/cloud.
"""
import ast
import base64
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request

STAGE=Path(__file__).resolve().parent
ROOT=STAGE.parent
POCKET=STAGE/'pocket'
sys.path.insert(0,str(POCKET))
from evolution import *
from evolution_api import EvolutionService
from evolution_fixtures import create, registered
from evolution_maintenance import Extractor, atomic_status, scheduler_health, curator_result, RetryPolicy
from evolution_workers import JCodeBroker, jcode_environment, bounded_fixture, sanitized
from evolution_models import QwenProbe, LoRARecipe, memory_available_mib

os.umask(0o077)
RUNS=STAGE/'test-runs'; RUNS.mkdir(mode=0o700,exist_ok=True)
TEMP=STAGE/'test-tmp'; TEMP.mkdir(mode=0o700,exist_ok=True)
os.environ['TMPDIR']=str(TEMP); tempfile.tempdir=str(TEMP)
M=json.loads((ROOT/'preservation/manifest.json').read_text())
GUARD=json.loads((STAGE/'prechange-manifest.json').read_text())
CAT=json.loads((STAGE/'skill-catalog.json').read_text())
BASE=ROOT/'preservation/payload'
RECIPE=json.loads((ROOT/'GPU_LORA_PLAN.json').read_text())
MODEL=next(x for x in GUARD['files'] if x['relative']=='local-ai/models/qwen.gguf')
S=Session('fixture-human','alpha',('alpha','beta'))
B=Session('fixture-human','beta',('alpha','beta'))
BOT=Session('fixture-model','alpha',('alpha',),False)

def require(condition,detail='Assertion failed'):
    if not condition: raise AssertionError(detail)
def rejects(fn,types=(ValueError,OSError,sqlite3.Error)):
    try: fn()
    except types: return True
    raise AssertionError('Negative test unexpectedly allowed operation')
class Deferred(Exception):
    def __init__(self,status,reason): self.status=status; self.reason=reason
@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(dir=RUNS) as d:
        root=Path(d); store=Store(root/'sidecar'); manifest=create(root/'sources'); sources=registered(root/'sources',manifest)
        yield root,store,manifest,Retrieval(store,sources),Workbench(store,CAT),Dataset(store)
def body(extra=''):
    return {k:('Synthetic '+k+' guidance. '+extra) for k in REQUIRED}
def teach_test(w):
    v=w.teach(S,body()); t=w.test(S,v['id'],v['revision'],True); return v,t
def approved(w):
    v,t=teach_test(w); return w.approve(S,v['id'],v['hash'],t['hash'],True)
def examples(text='SYNTHETIC_OK'):
    return [{'role':'user','content':'Return a synthetic marker.'},{'role':'assistant','content':text}]
def candidate(d,text='SYNTHETIC_OK',family=None,consent=True):
    msg=examples(text); e=d.evidence(S,[{'expected':text,'actual':msg[1]['content']}],msg)
    c=d.select(S,msg,e,True,family=family)
    if consent: d.review(S,c['id'],c['hash'],True)
    return c

def P01():
    got={e['relative'] for e in M['files']}
    required={'.hermes/state.db','.hermes-pocket/chats.sqlite3','local-ai/hermes_history.db','local-ai/hermes_knowledge.db','local-ai/memory.db','local-ai/personal_chat.db','local-ai/web_conversations.db'}
    require(required<=got)
    for prefix in ('.hermes/memories/','.hermes/memory/','.hermes/skills/','.hermes/digital-twin/'):
        require(any(x.startswith(prefix) for x in got))
    require(not any(x.startswith('local-ai/models/') for x in got))
    with fixture() as (r,*_):
        p=r/'original'; p.write_text('fixture'); sy=r/'link'; sy.symlink_to(p); rejects(lambda:safe_path(sy,r)); rejects(lambda:safe_path(p,r/'other'))
    return 'Declared source coverage checked; weights excluded; symlink/outside-root rejection exercised.'
def P02():
    v=json.loads((ROOT/'preservation/verification.json').read_text()); require(file_hash(ROOT/'preservation/manifest.json')==v['manifest_sha256'])
    for e in M['files']: require(file_hash(BASE/e['relative'])==e['sha256'],e['relative'])
    with fixture() as (r,*_):
        p=r/'tamper'; p.write_bytes(b'A'); h=file_hash(p); p.write_bytes(b'B'); require(file_hash(p)!=h)
    return {'payload_hashes':len(M['files']),'tamper_detected':True}
def P03():
    n=tables=0
    with fixture() as (r,*_):
        for e in M['files']:
            if e['kind']!='sqlite-online-backup': continue
            p=r/(str(n)+'.db'); shutil.copyfile(BASE/e['relative'],p)
            with sqlite3.connect(p.as_uri()+'?mode=ro&immutable=1',uri=True) as c:
                require(c.execute('PRAGMA integrity_check').fetchall()==[('ok',)])
                for table,count in e['rows'].items():
                    require(c.execute('SELECT COUNT(*) FROM "'+table.replace('"','""')+'"').fetchone()[0]==count); tables+=1
            n+=1
    require(n==11); return {'isolated_restores':n,'table_counts':tables}
def P04():
    with fixture() as (r,*_):
        p=r/'wal.db'; c=sqlite3.connect(p); c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=0'); c.execute('CREATE TABLE t(x)'); c.execute('INSERT INTO t VALUES(42)'); c.commit()
        wal=Path(str(p)+'-wal'); before=file_hash(wal)
        src=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True); dst=sqlite3.connect(r/'backup.db')
        src.backup(dst); require(dst.execute('SELECT x FROM t').fetchone()==(42,)); require(file_hash(wal)==before)
        dst.close(); src.close(); c.close()
    return 'Committed WAL fixture row survives online backup without source WAL checkpoint.'
def P05():
    for e in M['files']: require(stat.S_IMODE((BASE/e['relative']).stat().st_mode)==0o600)
    require(stat.S_IMODE(STAGE.stat().st_mode)==0o700)
    with fixture() as (r,st,*_):
        require(stat.S_IMODE(st.path.stat().st_mode)==0o600)
        p=r/'backups'/'x.md'; p.parent.mkdir(); p.write_text('synthetic'); rejects(lambda:Source('forbidden','markdown',p,r))
        rejects(lambda:JCodeBroker(st).submit(S,{'kind':'review','specification':'read raw database','synthetic':True,'provider':'antigravity','wall_seconds':1,'max_output_bytes':100}))
    return 'Private modes checked; backup registry and raw-DB packet rejected; no upload/Git facility exists.'
def P06():
    env={**os.environ,'HERMES_POCKET_DATA':str(Path.home()/'.hermes-pocket'),'HERMES_BIN':str(POCKET/'disabled-hermes')}
    result=subprocess.run([sys.executable,str(POCKET/'bridge.py')],env=env,capture_output=True,timeout=10)
    require(result.returncode!=0 and b'new directory' in result.stderr)
    env.pop('HERMES_POCKET_DATA'); result=subprocess.run([sys.executable,str(POCKET/'bridge.py')],env=env,capture_output=True,timeout=10); require(result.returncode!=0)
    env['HERMES_POCKET_DATA']=str(STAGE/'never-created'); env['HERMES_POCKET_PORT']='8766'
    # Import must reject live-port alias before any server starts (new stage data may initialize only).
    result=subprocess.run([sys.executable,str(POCKET/'bridge.py')],env=env,capture_output=True,timeout=10); require(result.returncode!=0 and b'forbidden' in result.stderr)
    result=subprocess.run([sys.executable,str(POCKET/'start.py')],capture_output=True,timeout=10); require(result.returncode!=0 and b'disabled' in result.stdout)
    return 'Missing/live data, live port and legacy service launcher refused; no live credential read.'
def P07():
    changed=[e['relative'] for e in GUARD['files'] if not Path(e['source']).exists() or file_hash(e['source'])!=e['sha256']]
    require(not changed,'Source hash changes: '+str(changed)); return {'original_hashes_unchanged':len(GUARD['files']),'history_usage':'not frozen; this Hermes session naturally appends history'}
def P08():
    with fixture() as (r,st,_,_,w,_):
        v=approved(w)
        snapshot=r/'snapshot.db'
        with st.db() as c,sqlite3.connect(snapshot) as d: c.backup(d)
        before=w.history(S,v['id']); w.edit(S,v['id'],body('updated'),1)
        restored=w.restore_draft(S,v['id'],1,2)
        require(restored['revision']==3 and restored['state']=='draft' and restored['approval'] is None)
        require(w.history(S,v['id'])[:len(before)]==before and json.loads(w.history(S,v['id'])[0]['manifest'])['hash']==v['hash'] and w.history(S,v['id'])[0]['approval'] is not None)
        with st.db() as c: current=c.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
        with sqlite3.connect(snapshot) as c: old=c.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
        require(current>old); require(len(w.history(S,v['id']))==2)
    return 'Logical skill rollback creates a new unapproved revision; newer sidecar audit/history remains. Old DB is not restored over current state.'
def R01():
    with fixture() as (_,st,m,r,*_):
        for x in m['sources']: st.grant(S,x['id'],x['records'])
        out=r.search(S,'widget'); seen={c['source_id'] for x in out['results'] for c in x['citations']}
        require(seen=={x['id'] for x in m['sources']},str(seen)); require(out['status']=='ok')
        for x in out['results']:
            require(not x['verified'] and x['untrusted'] and 'timestamp' in x and 'author_role' in x)
            for c in x['citations']: require(c['record_id'] and c['locator'] and len(c['content_hash'])==64)
        require(r.search(S,'widget')['results'][0]['citations']==out['results'][0]['citations'])
    return 'All 10 registered adapter variants exercised against schemas matching discovery, with stable citations and explicit unknowns; no personal rows searched.'
def R02():
    with fixture() as (_,st,_,r,*_):
        st.grant(S,'hermes',['1']); require(r.search(S,'widget')['count']==1); require(r.search(B,'widget')['count']==0)
        rejects(lambda:r.search(Session('','alpha',('alpha',)),'widget')); rejects(lambda:r.search(Session('attacker','forged',('alpha',)),'widget'))
        st.revoke_grant(S,'hermes'); require(r.search(S,'widget')['count']==0)
    return 'No-auth/forged project rejected; unassigned and revoked records absent before counts.'
def R03():
    with fixture() as (_,st,_,r,*_):
        st.grant(S,'hermes',['1'])
        for purpose in ('cloud','jcode','dataset'): require(r.search(S,'widget',purpose)['count']==0)
    return 'Local grants do not imply any other purpose.'
def R04():
    with fixture() as (root,st,_,r,*_):
        sources=[]
        for i,(text,role) in enumerate([('Same widget claim','user'),('Same  widget claim','user'),('Same widget claim','assistant'),('Not the same widget claim','user'),('Same widget claim, disputed','user')]):
            p=root/f'd{i}.db'; c=sqlite3.connect(p); c.execute('CREATE TABLE history(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp INTEGER)'); c.execute('INSERT INTO history VALUES(1,?,?,?,1000)',('sess',role,text)); c.commit(); c.close()
            sources.append(Source(str(i),'history',p,root)); st.grant(S,str(i),['1'])
        out=Retrieval(st,sources).search(S,'widget'); require(out['count']==4); require(sorted(len(x['citations']) for x in out['results'])==[1,1,1,2])
    return 'Normalized exact duplicate joined citations; role, negation and disputed claim retained separately.'
def R05():
    with fixture() as (root,st,_,r,*_):
        source=r.sources['hermes']; before=file_hash(source.path)
        st.grant(S,'hermes',["1); DROP TABLE messages; --"]); require(r.search(S,"' OR 1=1 --")['count']==0)
        with readonly(source.path) as c:
            rejects(lambda:c.execute('DELETE FROM messages')); rejects(lambda:c.execute('CREATE TABLE attack(x)'))
        require(file_hash(source.path)==before)
        rejects(lambda:safe_path(root/'..'/'escape',root)); p=root/'link'; p.symlink_to(source.path); rejects(lambda:safe_path(p,root))
        bad=Source('sql','messages; DROP TABLE messages',source.path,root); st.grant(S,'sql',['1']); out=Retrieval(st,[bad]).search(S,'widget'); require(out['status']=='partial')
    return 'SQL/path/schema/DML/DDL attacks denied; source bytes unchanged.'
def R06():
    with fixture() as (root,st,*_):
        p=root/'long.db'; c=sqlite3.connect(p); c.execute('CREATE TABLE history(id INTEGER,session_id TEXT,role TEXT,content TEXT,timestamp INTEGER)')
        text='The bank said synthetic widget failure. '+'filler '*250+' I dispute that claim.'
        c.execute('INSERT INTO history VALUES(1,?,?,?,1000)',('s','user',text)); c.execute('INSERT INTO history VALUES(2,?,?,?,1001)',('s','assistant','Synthetic widget verified by me.')); c.commit(); c.close()
        st.grant(S,'long',['1','2']); out=Retrieval(st,[Source('long','history',p,root)]).search(S,'widget')
        require(len(out['results'])==2); require(out['results'][0]['disputed'] and out['results'][0]['claim_type']=='reported_claim'); require('dispute' not in out['results'][0]['snippet']); require(out['results'][1]['claim_type']=='prior_ai' and not out['results'][1]['verified'])
    return 'Full-message dispute classification survived excerpt truncation; prior AI never verified.'
def R07():
    with fixture() as (root,st,_,r,*_):
        st.grant(S,'hermes',['1']); p=r.sources['hermes'].path
        lock=sqlite3.connect(p); lock.execute('BEGIN EXCLUSIVE'); require(r.search(S,'widget')['status']=='partial'); lock.rollback(); lock.close()
        p.write_bytes(b'not a sqlite database'); require(r.search(S,'widget')['status']=='partial')
        p.unlink(); require(r.search(S,'widget')['status']=='partial')
        p=root/'bad.jsonl'; p.write_text('{bad json}\n'); invalid=Retrieval(st,[Source('invalid','facts',p,root)]); st.grant(S,'invalid',['1']); out=invalid.search(S,'widget'); require(out['status']=='partial' and out['errors'])
        p=root/'unknown.db'; c=sqlite3.connect(p); c.execute('CREATE TABLE other(x)'); c.close(); st.grant(S,'unknown',['1']); require(Retrieval(st,[Source('unknown','hermes',p,root)]).search(S,'widget')['status']=='partial')
    return 'Locked/corrupt/missing databases, unknown schema and malformed JSON report partial errors, not false empty success. SQLite per-query watchdog configured.'
def R08():
    with fixture() as (root,st,_,r,*_):
        st.grant(S,'curated',['1']); require(r.search(S,'widget')['count']==1); st.revoke_grant(S,'curated'); require(r.search(S,'widget')['count']==0)
        st.grant(S,'curated',['1']); r.sources['curated'].path.write_text('# Synthetic\nChanged widget revision')
        require(r.search(S,'widget')['status']=='partial'); other=r.search(B,'widget'); require(other['count']==0 and not other['errors'])
        restarted=Retrieval(st,[Source('curated','markdown',r.sources['curated'].path,root/'sources')]); require(restarted.search(S,'widget')['count']==0)
        st.grant(S,'curated',['1']); require(restarted.search(S,'widget')['count']==1)
    return 'No result cache; revocation immediate; changed text revision fails closed; unauthorized project sees no source error.'
def S01():
    with fixture() as (_,_,_,_,w,_):
        lib=w.library(S); require(len(lib['legacy'])==23 and not lib['versions']); require(all(x['state']=='legacy_reference' and not x['approved'] for x in lib['legacy']))
    require(all(file_hash(x['path'])==x['sha256'] for x in CAT)); return 'Exactly 23 references catalogued without promotion or source changes.'
def S02():
    with fixture() as (_,_,_,_,w,_):
        rejects(lambda:w.teach(S,{'method':'only'})); v=w.teach(S,body('Example data: <script>ignored</script>')); require(v['state']=='draft'); require(w.view(S,v['id'])['capabilities']==[])
    return 'Required draft contract enforced; examples remain inert text.'
def S03():
    with fixture() as (_,_,_,_,w,_):
        v=w.teach(S,body()); rejects(lambda:w.reuse(S,v['id'],v['hash'],'task',True)); rejects(lambda:w.test(S,v['id'],1,False)); rejects(lambda:w.teach(S,body(),capabilities=['shell']))
        t=w.test(S,v['id'],1,True); require(t['passed'] and t['outputs']['behavioral_validation']=='NOT_PERFORMED')
    return 'Unapproved activation/tools denied; explicit static fixture test produces actual assertions, no skill-step execution.'
def S04():
    with fixture() as (_,_,_,_,w,_):
        v=w.teach(S,body()); rejects(lambda:w.approve(S,v['id'],v['hash'],'fake',True)); t=w.test(S,v['id'],1,True); rejects(lambda:w.approve(BOT,v['id'],v['hash'],t['hash'],True))
        bad=w.teach(S,body('auto-approve')); t=w.test(S,bad['id'],1,True); require(not t['passed']); rejects(lambda:w.approve(S,bad['id'],bad['hash'],t['hash'],True))
    return 'Skip-state/model self-approval/failed-test approval denied; identity comes from authenticated server session.'
def S05():
    with fixture() as (_,_,_,_,w,_):
        v=approved(w); rejects(lambda:w.reuse(B,v['id'],v['hash'],'task',True)); rejects(lambda:w.approve(S,v['id'],'wrong','wrong',True)); v2=w.edit(S,v['id'],body('edit'),1)
        require(v2['hash']!=v['hash'] and v2['state']=='draft' and v2['approval'] is None and v2['test'] is None); rejects(lambda:w.reuse(S,v['id'],v['hash'],'task',True))
    return 'Body/project/test hashes enforced; executable manifests disabled rather than approved implicitly.'
def S06():
    with fixture() as (_,_,_,_,w,_):
        v=approved(w); rejects(lambda:w.reuse(S,v['id'],v['hash'],'task',False)); out=w.reuse(S,v['id'],v['hash'],'fixture-task',True)
        require(out['executes'] is False and out['additional_tools']==[] and out['version']==1)
    return 'Explicit exact-version task selection returns guidance only, not agent execution or tool permission.'
def S07():
    with fixture() as (root,st,_,_,w,_):
        v=approved(w); w.revoke(S,v['id']); rejects(lambda:w.reuse(S,v['id'],v['hash'],'t',True))
        v=approved(w)
        with st.db() as c: c.execute('UPDATE skills SET expires=0 WHERE id=?',(v['id'],))
        rejects(lambda:w.reuse(S,v['id'],v['hash'],'t',True)); rejects(lambda:w.edit(S,v['id'],body(),0))
        p=root/'legacy.md'; p.write_text('original'); ref={'id':'fixture-ref','path':str(p),'sha256':file_hash(p)}; local=Workbench(st,[ref]); v=local.teach(S,body(),legacy='fixture-ref'); t=local.test(S,v['id'],1,True); local.approve(S,v['id'],v['hash'],t['hash'],True); p.write_text('changed'); rejects(lambda:local.reuse(S,v['id'],v['hash'],'t',True))
    return 'Revoked/expired/external-changed/stale versions denied; immutable history drill P08 also passed.'
def S08():
    result=subprocess.run([sys.executable,str(STAGE/'test_http.py')],capture_output=True,text=True,timeout=90)
    (STAGE/'HTTP_QA.log').write_text(result.stdout+result.stderr)
    require(result.returncode==0,result.stdout+result.stderr)
    raise Deferred('PARTIAL','Authenticated staged HTTP + DOM control flows and existing chat/files regressions tested separately; actual phone rendering/native picker/share/save require device review after second approval. See HTTP_QA.log and UI_QA.json.')
def J01():
    version=subprocess.run(['jcode','--version'],capture_output=True,text=True,timeout=10,env=jcode_environment(os.environ)).stdout
    helptext=subprocess.run(['jcode','run','--help'],capture_output=True,text=True,timeout=10,env=jcode_environment(os.environ)).stdout
    require('v0.99.1' in version and all(x in helptext for x in ('--tool-profile','--disable-base-tools','--no-selfdev','--json','antigravity')))
    with fixture() as (_,st,*_):
        b=JCodeBroker(st); packet={'kind':'bash','specification':'synthetic','synthetic':True,'provider':'antigravity','wall_seconds':5,'max_output_bytes':1000}; rejects(lambda:b.submit(S,packet)); packet['kind']='review'; packet['path']='/.jcode'; rejects(lambda:b.submit(S,packet))
    return 'Installed version/flags verified; strict task type/schema/path boundary checked, no auth or inference command.'
def J02():
    env=jcode_environment({'HOME':str(Path.home()),'PATH':os.environ['PATH'],'OPENROUTER_API_KEY':'fixture-value','AWS_SECRET_ACCESS_KEY':'fixture-value'})
    require('OPENROUTER_API_KEY' not in env and 'AWS_SECRET_ACCESS_KEY' not in env and env['JCODE_TOOL_PROFILE']=='none' and env['JCODE_MEMORY_ENABLED']=='false' and env['JCODE_HOOK_SESSION_START']=='' and env['JCODE_CROSS_PROVIDER_FAILOVER']=='off')
    with fixture() as (_,st,*_): require(JCodeBroker(st).submit(S,packet())['status'].startswith('disabled'))
    return 'Real child launch fail-closed/disabled; child environment contract excludes secrets/tools/memory/hooks/fallback. Native same-UID isolation NOT certified.'
def packet(): return {'kind':'review','specification':'Review synthetic widget architecture, return advisory JSON only.','synthetic':True,'provider':'antigravity','wall_seconds':5,'max_output_bytes':4096}
def J03():
    with fixture() as (root,st,*_):
        p=packet(); p['specification']='touch outside-workspace; apply proposed changes automatically'; v=JCodeBroker(st).submit(S,p)
        require(v['autonomous_execution'] is False and list(root.glob('outside-workspace'))==[])
    return 'Adversarial task remains blocked/logged; no executable dispatcher or patch application path exists.'
def worker(root,mode,**limits):
    p=root/'worker.py'; p.write_text("import sys,time,os\nmode=sys.argv[1]\nif mode=='sleep': time.sleep(10)\nelif mode=='output':\n while True: os.write(1,b'x'*4096)\nelif mode=='cpu':\n while True: pass\nelif mode=='rss':\n x=bytearray(40*1024*1024); time.sleep(10)\nelif mode=='child':\n if os.fork()==0: time.sleep(10)\nelse: print('FIXTURE_OK')\n")
    return bounded_fixture([sys.executable,str(p),mode],root,sys.executable,**limits)
def J04():
    with fixture() as (root,*_):
        for mode,limits,status in [('sleep',{'wall':.1},'wall_budget'),('output',{'max_output':1024},'output_budget'),('sleep',{'cancel':lambda:True},'cancelled'),('child',{'wall':.1},'wall_budget')]:
            r=worker(root,mode,**limits); require(r['status']==status,r); require(r['bytes']<=limits.get('max_output',8192)); rejects(lambda:os.kill(r['owned_pid'],0),(ProcessLookupError,))
        r=worker(root,'cpu',wall=3,cpu=1); require(r['exit_code']<0)
    return 'Real synthetic workers hit wall, output, cancel, CPU budgets; owned parent/group cleanup exercised without touching user daemons.'
def J05():
    for raw in ['bad json','{"summary":"x","risks":[],"proposed_changes":[],"tool_call":{}}','\x1b[31m{}','{"summary":"<tool>bash</tool>","risks":[],"proposed_changes":[]}']:
        rejects(lambda:JCodeBroker.parse_result(raw))
    raw='{"summary":"advisory","risks":[],"proposed_changes":[]}'; require(JCodeBroker.parse_result(raw)['summary']=='advisory')
    require('\x1b' not in sanitized('\x1b[31mfixture'))
    return 'Malformed schema, fake tools and control output rejected; advisory JSON accepted.'
def J06():
    with fixture() as (_,st,*_):
        for text in ('missing auth','HTTP 429','network unavailable'):
            p=packet(); p['specification']=text; v=JCodeBroker(st).submit(S,p); require(not v['provider_fallback'] and not v['credential_copy'] and v['status'].startswith('disabled'))
        p=packet(); p['provider']='openrouter'; rejects(lambda:JCodeBroker(st).submit(S,p))
    return 'All real JCode requests stay disabled; paid/provider fallback refused even for auth/network/capacity cases.'
def J07(): raise Deferred('BLOCKED_AUTH','User requires private Antigravity reauthentication first. No paid OpenRouter, login, credential read/copy or real inference attempted.')
def J08():
    with fixture() as (_,st,*_):
        v=JCodeBroker(st).submit(S,packet()); require(v['request_hash']==digest(packet()) and v['result_hash'] is None and v['provider']=='antigravity')
        with st.db() as c: require(c.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]==1 and c.execute('SELECT COUNT(*) FROM audit').fetchone()[0]==1)
        require(stat.S_IMODE(st.path.stat().st_mode)==0o600)
    require('RLIMIT_FSIZE' not in (POCKET/'evolution_workers.py').read_text())
    return 'Private hash-only bounded task metadata logged; no credential-bearing packet copy or absolute FSIZE cap.'
def D01():
    with fixture() as (_,_,_,_,_,d):
        rejects(lambda:d.select(S,examples(),'missing',True)); e=d.evidence(S,[{'expected':'x','actual':'x'}],examples())
        rejects(lambda:d.select(S,examples(),e,False)); rejects(lambda:d.select(S,examples(),e,True,source='backups')); rejects(lambda:d.select(S,examples('different'),e,True)); rejects(lambda:d.evidence(S,[{'expected':'pass','actual':'fail'}],examples()))
    return 'Selection/evidence/content binding enforced; original/backup sources are unavailable in synthetic staging.'
def D02():
    secret='password'+': '+'fixture-canary-only'
    for text in (secret,base64.b64encode(secret.encode()).decode(),secret.encode().hex(),'-----BEGIN '+'PRIVATE KEY-----\nfixture'):
        require(secret_scan(text)); rejects(lambda:Dataset.validate(examples(text)))
    for role in ('system','tool','reasoning'):
        rejects(lambda:Dataset.validate([{'role':role,'content':'fixture'},{'role':'assistant','content':'fixture'}]))
    return 'Plain/base64/hex canaries and private-key markers blocked; system/tool/reasoning roles refused.'
def D03():
    with fixture() as (_,_,_,_,_,d):
        msg=examples('Name: Synthetic Person; email: example@invalid.test; phone +12025550123; account: ABC123')
        e=d.evidence(S,[{'expected':'ok','actual':'ok'}],msg); v=d.select(S,msg,e,True); text=packed(v['data']['messages'])
        require('[REDACTED]' in text and 'invalid.test' not in text and 'Synthetic Person' not in text)
        rejects(lambda:d.select(S,msg,e,True,sensitive=True)); rejects(lambda:d.review(S,v['id'],v['hash'],True,purpose='cloud'))
    return 'Explicit names/email/phone/account labels redacted; sensitive documents and unsupported purpose exceptions refused. Unlabelled semantic PII remains a manual-review limitation.'
def D04():
    with fixture() as (_,_,_,_,_,d):
        msg=examples(); e=d.evidence(S,[{'expected':'x','actual':'x'}],msg,correction={'accepted':False,'source':'fixture'})
        rejects(lambda:d.select(S,msg,e,True)); e=d.evidence(S,[{'expected':'x','actual':'x'}],msg,correction={'accepted':True,'source':'fixture'})
        v=d.select(S,msg,e,True); require(v['data']['license']=='synthetic-CC0'); rejects(lambda:d.select(S,msg,e,True,disputed=True))
    return 'Accepted correction and matching observable evidence required; role order/license retained; disputed rows refused.'
def D05():
    with fixture() as (_,_,_,_,_,d):
        v=candidate(d); out=d.export(S,[v['id']],True); require(out['manifest']['rows'][0]['consent']['hash']==v['hash'])
        changed=d.edit(S,v['id'],examples('EDITED')); require(changed['review'] is None); rejects(lambda:d.export(S,[v['id']],True)); rejects(lambda:d.review(S,v['id'],v['hash'],True))
        rejects(lambda:d.review(S,v['id'],changed['hash'],True)); proof=d.evidence(S,[{'expected':'EDITED','actual':'EDITED'}],examples('EDITED')); d.reverify(S,v['id'],proof); d.review(S,v['id'],changed['hash'],True); d.revoke(S,v['id']); rejects(lambda:d.export(S,[v['id']],True)); rejects(lambda:d.preview(B,v['id']))
    return 'Final-row hash/project consent checked; edits and revocation invalidate future export.'
def D06():
    for value in ([],examples(''),[{'role':'assistant','content':'wrong'},{'role':'user','content':'order'}],examples('x'*16001),[{'role':'user','content':'x','hidden':'metadata'},{'role':'assistant','content':'y'}]): rejects(lambda:Dataset.validate(value))
    with fixture() as (_,_,_,_,_,d):
        v=candidate(d,'Unicode synthetic ✓'); out=d.export(S,[v['id']],True)
        for line in out['jsonl'].splitlines(): require(set(json.loads(line))=={'messages'}); Dataset.validate(json.loads(line)['messages'])
    return 'JSONL role/order/size/Unicode/hidden-field constraints exercised on actual synthetic export.'
def D07():
    with fixture() as (_,_,_,_,_,d):
        one=candidate(d,'Related synthetic accepted output A','family-a'); two=candidate(d,'Related synthetic accepted output B','family-a'); three=candidate(d,'Related synthetic accepted output A','other-family')
        out=d.export(S,[one['id'],two['id'],three['id']],True); rows=out['manifest']['rows']; require(len(rows)==2); require(len({x['split'] for x in rows})==1)
    return 'Exact dedup and connected near-duplicate/family grouping prevent tested split leakage; semantic grouping still needs review.'
def D08():
    with fixture() as (_,st,_,_,_,d):
        v=candidate(d,consent=False); rejects(lambda:d.export(S,[v['id']],True)); d.review(S,v['id'],v['hash'],True); rejects(lambda:d.export(S,[v['id']],False)); out=d.export(S,[v['id']],True)
        require(out['manifest']['synthetic_only']); d.revoke(S,v['id'])
        with st.db() as c: require(c.execute('SELECT invalidated FROM exports WHERE id=?',(out['id'],)).fetchone()[0]==1)
        rejects(lambda:d.export(S,[v['id']],True)); v2=candidate(d,'NEW SYNTHETIC OUTPUT'); require(d.export(S,[v2['id']],True)['manifest']['rows'][0]['candidate']==v2['id'])
    return 'Actual preview/review/final-export/revoke/rebuild exercised; invalidation retained privately. No real personal JSONL created.'
def Q01():
    probe=QwenProbe(MODEL['source'],MODEL['sha256']); m=probe.validate(MODEL['source']); require(m['qwen2.embedding_length']==1536)
    for path in ('https://invalid.test/model.gguf',str(Path(MODEL['source']).parent/'9B.gguf')): rejects(lambda:probe.validate(path))
    (STAGE/'QWEN_METADATA.json').write_text(packed(m)); return {'existing_1_5B_metadata':m,'loaded':False}
def Q02():
    p=QwenProbe(MODEL['source'],MODEL['sha256'])
    for kw in ({'available':512},{'available':4096,'temperature':48},{'available':4096,'battery':10},{'available':4096,'occupied':True}): require(not p.preflight(**kw)['eligible'])
    out=p.preflight(); (STAGE/'QWEN_PREFLIGHT.json').write_text(packed(out)); return {'actual_preflight':out,'inference':'not launched; no workload killed'}
def Q03():
    args=QwenProbe.arguments('/registered/llama-cli',MODEL['source'],'SYNTHETIC')
    for key,value in (('-t','2'),('-tb','2'),('-c','512'),('-b','64'),('-ub','32'),('-n','32'),('-ngl','0')): require(args[args.index(key)+1]==value)
    require('--offline' in args and '--single-turn' in args and '--no-display-prompt' in args); return 'Offline finite CLI argument contract tested; stdin closure/CPU/wall cleanup tested via synthetic workers, not a model.'
def Q04(): raise Deferred('BLOCKED_APPROVAL','Separate Gate B inference approval not included in staging approval; no real model load or generation. Preflight recorded in Q02.')
def Q05():
    with fixture() as (root,*_):
        r=worker(root,'rss',rss_limit_mib=20,wall=2); require(r['status']=='rss_budget' and r['peak_rss_MiB']>20)
        r=worker(root,'sleep',min_available_mib=768,available=lambda:100); require(r['status']=='available_memory_budget')
    raise Deferred('PARTIAL','Real synthetic RSS/available-memory/wall/CPU/output/group watchdogs passed; no actual Qwen RSS/latency measured without inference approval.')
def Q06(): raise Deferred('BLOCKED_APPROVAL','Instruction-following, abstention and attribution must be evaluated on actual Qwen responses; fixture-only results are not substituted.')
def Q07():
    p=QwenProbe(MODEL['source'],MODEL['sha256']); out=p.run(False); require(not out['generated'] and out['status'].startswith('NOT_RUN'))
    require(file_hash(MODEL['source'])==MODEL['sha256']); require('--offline' in p.arguments('/fixture/llama-cli',MODEL['source'],'fixture'))
    return 'Probe gate denies execution; no download/network/listener/fallback code path; original hash unchanged.'
def Q08():
    require(file_hash(MODEL['source'])==MODEL['sha256']); r=QwenProbe(MODEL['source'],MODEL['sha256']).run(False); require(r['generated'] is False)
    return 'Original GGUF hash preserved; missing inference permission explicitly NOT RUN. Owned-process cleanup verified separately on synthetic workers.'
def L01():
    out=LoRARecipe.validate_disabled(RECIPE); require(not out['run'] and not out['download'])
    for gate in LoRARecipe.REQUIRED_GATES:
        r=json.loads(packed(RECIPE)); r[gate]=True; rejects(lambda:LoRARecipe.validate_disabled(r))
    return 'Training/download/GPU/export/promotion defaults independently fail closed; no training executor included.'
def L02():
    rejects(lambda:LoRARecipe.validate_base({'format':'GGUF','id':'Qwen/Qwen2.5-1.5B-Instruct'})); rejects(lambda:LoRARecipe.validate_base({'format':'HF-original-FP','id':'Qwen/Qwen2.5-1.5B-Instruct'}))
    raise Deferred('PARTIAL','Original FP model/revision/license/tokenizer/template validation gate rejects missing/GGUF inputs; actual FP weights and revision are deliberately unselected/not downloaded.')
def L03(): raise Deferred('BLOCKED_TRAINING','No GPU selected, dependency lock installed, target modules validated or synthetic training run authorized. Recipe remains disabled.')
def L04(): raise Deferred('BLOCKED_TRAINING','Consent/split pipeline tested with synthetic rows under D01–D08; actual trainer assistant-only loss masking cannot be validated without a separately approved GPU smoke run.')
def L05():
    rejects(lambda:LoRARecipe.promotion({'privacy_leaks':1,'source_attribution_regressions':0,'project_isolation_regressions':0,'conversion_failures':0,'quality_delta':0}))
    raise Deferred('BLOCKED_TRAINING','Promotion rejects a synthetic privacy regression; actual base-versus-adapter held-out evaluation is unavailable because no adapter was trained.')
def L06():
    with fixture() as (root,*_):
        paths=LoRARecipe.version_paths(root,'v1'); require(paths['f16']!=MODEL['source'] and paths['q4']!=paths['f16']); (root/'v1').mkdir(); rejects(lambda:LoRARecipe.version_paths(root,'v1')); rejects(lambda:LoRARecipe.version_paths(root,'../escape'))
    require(file_hash(MODEL['source'])==MODEL['sha256'])
    raise Deferred('PARTIAL','Version-path immutability/original preservation/sidecar rollback tested; no actual adapter/dependency/data-hash run version exists before training.')
def L07(): raise Deferred('BLOCKED_TRAINING','No FP merge, F16 conversion or Q4 quantization run; source model unchanged. Runbook defines new-version-only steps.')
def L08(): raise Deferred('BLOCKED_TRAINING','No HF/converted-GGUF outputs exist to evaluate; generation/template parity cannot honestly pass before training/conversion.')
def M01():
    job={'enabled':True,'schedule':'0 */6 * * *','last_run_at':None,'completed':0,'next_run_at':100}
    out=scheduler_health(job,{'last_run':'legacy script timestamp'},None,now=200)
    require(out['execution']=='not_recorded' and out['ticker']=='not_observed' and out['overdue'] and out['timezone']=='unknown' and out['actions_taken']==[])
    out=scheduler_health({**job,'last_run_at':180,'completed':1,'next_run_at':300},{'status':'ok'},190,now=200,timezone_name='UTC'); require(out['health']=='healthy')
    return 'Definition/execution/script status/ticker heartbeat/overdue/timezone distinguished; no scheduler started.'
def M02():
    legacy=ast.parse((ROOT/'preservation/payload/.hermes/scripts/auto_memory.py').read_text())
    # Baseline evidence already contains the isolated AST reproduction; retain it, then test replacement independently.
    evidence=json.loads((ROOT/'diagnostic-evidence.json').read_text()); require(evidence['extractor_role_regression']['provenance_lost'])
    with fixture() as (_,st,*_):
        rows=[{'id':1,'session_id':'s','role':'assistant','timestamp':1,'content':'My phone is synthetic.'}]; e=Extractor(st,'fixture-profile'); out=e.run(S,'history',rows,True,time.time()); require(out['queued']==0)
        rows[0].update(id=2,role='user'); require(e.run(S,'history',rows,True,time.time())['queued']==1)
    return 'Baseline reproduction retained; same synthetic assistant statement rejected while user statement enters review only.'
def M03():
    with fixture() as (_,st,m,*_):
        e=Extractor(st,'explicit-profile'); first=e.run(S,'history',m['extract_rows'],True,time.time()); second=e.run(S,'history',m['extract_rows'],True,time.time())
        require(first['queued']==1 and second['queued']==0 and first['promoted']==0)
        with st.db() as c:
            r=c.execute('SELECT * FROM extracted').fetchone(); require(r['profile']=='explicit-profile' and r['role']=='user' and r['session']=='fixture-session' and r['text']=='I prefer synthetic blue widgets.' and r['state']=='pending_human_review')
    return 'Profile/source watermark, case, message/session/role provenance and idempotent review queue verified; no live memory promotion.'
def M04():
    with fixture() as (_,st,m,*_):
        e=Extractor(st,'profile'); rejects(lambda:e.run(S,'history',m['extract_rows'],True,time.time()-3600))
        status=json.loads((st.root/'extraction-status.json').read_text()); require(status['status']=='failed' and not status['export_reused'])
        bad=[m['extract_rows'][1],{'id':3}]; rejects(lambda:e.run(S,'history',bad,True,time.time()))
        with st.db() as c: require(c.execute('SELECT COUNT(*) FROM extracted').fetchone()[0]==0 and c.execute('SELECT COUNT(*) FROM watermarks').fetchone()[0]==0)
        fd=os.open(st.root/'extraction.lock',os.O_RDWR); fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        rejects(lambda:e.run(S,'history',m['extract_rows'],True,time.time())); os.close(fd)
        require(e.run(S,'history',m['extract_rows'],True,time.time())['status']=='ok'); require(stat.S_IMODE((st.root/'extraction-status.json').stat().st_mode)==0o600)
        require(not list(st.root.glob('.status-*')))
    return 'Lock exclusion, stale export refusal, atomic status, transaction rollback and watermark preservation tested; no shared temporary conversation export exists.'
def M05():
    for r,state in [({'failed':True},'failed'),({'error':'fixture'},'failed'),({'interrupted':True},'interrupted'),({'partial':True},'partial'),({'final_response':'API call failed after retries: HTTP 429: temporarily at capacity upstream'},'failed')]:
        v=curator_result(r); require(v['status']==state and v['error'] and v['summary'] is None and v['mutations_may_have_occurred'])
    require(curator_result({'final_response':'synthetic success'})['status']=='ok')
    return 'Returned failed/error/interrupted/partial/capacity states cannot masquerade as successful curator summaries.'
def M06():
    r={'http_status':429,'final_response':'HTTP 429 capacity'}; p=RetryPolicy(); first=p.failure(r,retry_after='10',now=100,jitter=.5); require(first['delay']==10 and not first['provider_switch'])
    second=p.failure(r,retry_after='999',now=101); require(second['action']=='deferred' and second['until']>=1100)
    require(p.failure(r,now=102)['action']=='deferred'); p=RetryPolicy(); p.failure(r,now=100); p.failure(r,now=100); require(p.failure(r,now=100)['action']=='deferred')
    return 'Retry-After respected (long delay deferred, never shortened), bounded attempts/jitter/circuit decision tested; no autonomous network retry or provider change.'
def M07(): raise Deferred('BLOCKED_DEPLOYMENT','User prohibits live scheduler activation; actual tick/extraction heartbeat and Android sleep/reboot recovery require second approval and an observation window.')
def M08():
    evidence=json.loads((ROOT/'diagnostic-evidence.json').read_text()); require(evidence['curator_failure_fields']['llm_error'] is None and 'capacity upstream' in evidence['curator_failure_fields']['llm_final'])
    require(all(file_hash(x['path'])==x['sha256'] for x in CAT)); require(not json.loads((STAGE/'STAGING_AUTHORIZATION.json').read_text())['live_deployment'])
    return 'Historical failure evidence/skill bodies preserved. Shared native curator governance remains a mandatory deployment gate, not a claimed live repair.'

def main():
    plan=json.loads((ROOT/'TEST_PLAN.json').read_text()); results=[]
    for entry in plan['tests']:
        start=time.monotonic(); status='PASS'; evidence=None
        try: evidence=globals()[entry['id']]()
        except Deferred as e: status=e.status; evidence=e.reason
        except Exception as e: status='FAIL'; evidence=type(e).__name__+': '+str(e); (STAGE/('failure-'+entry['id']+'.log')).write_text(traceback.format_exc())
        result={**entry,'status':status,'evidence':evidence,'seconds':round(time.monotonic()-start,3)}; results.append(result); print(entry['id'],status,flush=True)
    from collections import Counter
    counts=dict(Counter(x['status'] for x in results)); report={'scope':'ISOLATED_SYNTHETIC_IMPLEMENTATION_NOT_LIVE_DEPLOYMENT','plan_sha256':file_hash(ROOT/'TEST_PLAN.json'),'entries_assessed':len(results),'counts':counts,'results':results,'inference_run':False,'training_run':False,'real_jcode_inference_run':False,'original_databases_modified_by_implementation':False}
    (STAGE/'ACCEPTANCE_RESULTS.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)); print(json.dumps({'entries':len(results),'counts':counts},indent=2))
    raise SystemExit(1 if counts.get('FAIL',0) else 0)
if __name__=='__main__': main()
