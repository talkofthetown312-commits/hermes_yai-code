#!/usr/bin/env python3
"""Explicit live, synthetic-data-only Cloud/Local test; never loads memories.
Run separately, NOT via unittest discovery. Uses paired token without printing it.
"""
import json
import pathlib
import sqlite3
import sys
import time
import urllib.request

BASE = 'http://127.0.0.1:8766'
DATA = pathlib.Path.home()/'.hermes-pocket'
SMOKE = '--production' not in sys.argv
TOKEN = (DATA/'pairing-token').read_text().strip()


def api(path, body=None):
    req = urllib.request.Request(BASE+'/api/'+path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+TOKEN, 'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


def wait(cid, timeout=300):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        chat = api('chats/'+cid)
        if chat['state'] != 'running':
            return chat
        time.sleep(0.6)
    raise TimeoutError('Chat still running after test deadline; no retry was sent.')


def main():
    report = {'status':api('status'), 'models':api('models'), 'results':[]}
    print('Authenticated bridge:', report['status'], flush=True)
    for mode,word in [('cloud','pocket-orchid-47'),('local','pocket-copper-29')]:
        if '--local-only' in sys.argv and mode != 'local':
            continue
        params = {'mode':mode}
        if mode == 'local':
            params['model'] = 'android-1b:latest'
        chat = api('chats',params); cid=chat['id']
        started = time.monotonic()
        api('send',{'id':cid,'message':'For this conversation the code word is '+word+'. Remember it for my next message. Reply only SAVED. Do not use tools.','smoke':SMOKE})
        first=wait(cid)
        print(mode, 'first:', first['state'], first['error'], 'reply:',first['messages'][-1]['text'],flush=True)
        item={'mode':mode,'chat_id':cid,'first_state':first['state'],'first_reply':first['messages'][-1]['text'],'first_session':first['session']}
        if first['state'] == 'idle':
            api('send',{'id':cid,'message':'What code word did I give you in my preceding message? Reply only the code word. Do not use tools.','smoke':SMOKE})
            second=wait(cid)
            item.update(followup_state=second['state'],followup_reply=second['messages'][-1]['text'],followup_session=second['session'])
            item['continuity_passed']=second['state']=='idle' and first['session']==second['session'] and word in second['messages'][-1]['text']
            with sqlite3.connect('file:'+str(pathlib.Path.home()/'.hermes/state.db')+'?mode=ro',uri=True) as db:
                rows = db.execute('SELECT role FROM messages WHERE session_id=?',(second['session'],)).fetchall()
            item['hermes_persisted_user_turns']=sum(1 for r in rows if r[0]=='user')
            print(mode,'follow-up:',second['state'],'continuity:',item['continuity_passed'],'Hermes user turns:',item['hermes_persisted_user_turns'],'reply:',second['messages'][-1]['text'],flush=True)
        else:
            item['continuity_passed']=False
        item['elapsed_seconds']=round(time.monotonic()-started,1)
        report['results'].append(item)
        report_name = 'smoke-report.json' if SMOKE else ('local-production-report.json' if '--local-only' in sys.argv else 'production-report.json')
        path=DATA/report_name
        path.write_text(json.dumps(report,indent=2));path.chmod(0o600)
    return 0 if all(x.get('continuity_passed') and x.get('hermes_persisted_user_turns')==2 for x in report['results']) else 1

if __name__=='__main__':
    raise SystemExit(main())
