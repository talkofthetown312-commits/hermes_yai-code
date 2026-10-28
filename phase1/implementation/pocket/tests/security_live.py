#!/usr/bin/env python3
"""Read-only live security probes, optionally restart ONLY the idle Pocket bridge.
Never prints credentials, conversation contents, or request URLs containing tokens.
Acceptance: auth/Host/Origin failures enforced, private routes inaccessible, security
headers present, invalid requests cannot mutate chats, and restart preserves data,
pairing/signing keys, config and memories. No model calls are made.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DATA=Path.home()/'.hermes-pocket'
BASE='http://127.0.0.1:8766'
TOKEN=(DATA/'pairing-token').read_text().strip()
CHECKS=[]


def request(path, body=None, auth=True, headers=None):
    h={'Content-Type':'application/json'}
    if auth: h['Authorization']='Bearer '+TOKEN
    h.update(headers or {})
    req=urllib.request.Request(BASE+path, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        r=urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as e:
        r=e
    with r:
        return r.code, dict(r.headers), r.read()


def check(name, passed):
    CHECKS.append({'name':name,'passed':bool(passed)})
    print(('PASS: ' if passed else 'FAIL: ')+name,flush=True)
    if not passed: raise AssertionError(name)


def snapshot():
    with sqlite3.connect('file:'+str(DATA/'chats.sqlite3')+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT * FROM chats ORDER BY id').fetchall()
        assert not any(r[4]=='running' for r in rows), 'Active chat; restart refused'
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    files=[DATA/'pairing-token',*sorted((DATA/'signing').glob('*'))]
    home=Path(os.environ.get('HERMES_HOME',str(Path.home()/'.hermes')))
    files += [home/'config.yaml',home/'.env',*sorted((home/'memories').glob('*.md'))]
    return {'chat_count':len(rows),'chat_digest':hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
            'files':{str(p):(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mode&0o777) for p in files if p.is_file()}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restart',action='store_true')
    args=parser.parse_args()
    before=snapshot()
    status,headers,body=request('/')
    check('Served application identity',status==200 and b'<title>Hermes Pocket</title>' in body)
    for name,expected in [('X-Content-Type-Options','nosniff'),('Referrer-Policy','no-referrer'),('Cache-Control','no-store')]:
        check(name,headers.get(name)==expected)
    check('Content Security Policy',"frame-ancestors 'none'" in headers.get('Content-Security-Policy',''))
    check('No CORS wildcard','Access-Control-Allow-Origin' not in headers)
    for path in ['/api/status','/api/chats','/api/models','/api/artifacts','/api/drafts','/api/files/fixture']:
        check('Unauthenticated rejection '+path,request(path,auth=False)[0]==401)
    check('Invalid token rejected',request('/api/status',headers={'Authorization':'Bearer invalid'})[0]==401)
    check('Authenticated status ready',json.loads(request('/api/status')[2]).get('ready') is True)
    check('Updated interface served',json.loads(request('/api/status')[2]).get('interface_version')=='0.2.0')
    check('Untrusted Host rejected',request('/',headers={'Host':'untrusted.example'})[0]==403)
    check('Cross-origin mutation rejected',request('/api/chats',{},headers={'Origin':'https://untrusted.example'})[0]==403)
    for path in ['/.env','/bridge.py','/../.hermes/auth.json','/%2e%2e/.hermes/auth.json','/signing/release.properties','/pairing-token']:
        check('Private route blocked '+path,request(path)[0]==404)
    check('Invalid mode rejected',request('/api/chats',{'mode':'invalid'})[0]==400)
    check('Invalid message rejected',request('/api/send',{'id':'unknown','message':''})[0]==400)
    check('Unknown conversation rejected',request('/api/chats/does-not-exist')[0]==404)
    for path in ['/','/app.js','/style.css']:
        check('Token absent from '+path,TOKEN.encode() not in request(path)[2])
    check('Security probes changed no data',snapshot()==before)
    check('Private data directory',DATA.stat().st_mode&0o777==0o700)
    check('Pairing token permissions',(DATA/'pairing-token').stat().st_mode&0o777==0o600)
    if args.restart:
        # Verify exact singleton process in the dedicated session before signalling.
        lines=subprocess.check_output(['tmux','list-panes','-t','=hermes-pocket','-F','#{pane_pid}'],text=True).splitlines()
        assert len(lines)==1,'Refusing to restart a multi-pane session'
        pid=int(lines[0]); argv=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
        assert str(ROOT/'bridge.py').encode() in argv,'Unexpected service process; left untouched'
        check('Idle before controlled restart',snapshot()==before)
        os.kill(pid,signal.SIGTERM)
        deadline=time.monotonic()+10
        while subprocess.run(['tmux','has-session','-t','=hermes-pocket'],capture_output=True).returncode==0:
            if time.monotonic()>deadline: raise TimeoutError('Old bridge session did not exit')
            time.sleep(.1)
        result=subprocess.run(['python',str(ROOT/'start.py')],capture_output=True,text=True,timeout=80)
        check('Bridge restart helper succeeded',result.returncode==0)
        check('Restart retained exact conversations and private files',snapshot()==before)
        check('Same pairing token works after restart',request('/api/status')[0]==200)
    report={'passed':all(x['passed'] for x in CHECKS),'check_count':len(CHECKS),'restart_tested':args.restart,'chat_count':before['chat_count'],'checks':CHECKS}
    p=DATA/'security-report.json'
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f: json.dump(report,f,indent=2)
    print('TOTAL FAILURES: 0; checks='+str(len(CHECKS)))


if __name__=='__main__': main()
