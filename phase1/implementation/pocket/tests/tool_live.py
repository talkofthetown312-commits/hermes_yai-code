#!/usr/bin/env python3
"""Explicit harmless live Cloud tool test. Requires a NEW persisted tool result.
A prior tool message or a model merely echoing the marker cannot pass this check.
"""
import json
import pathlib
import sqlite3
from smoke_live import api, wait

DATA=pathlib.Path.home()/'.hermes-pocket'
prior=json.loads((DATA/'production-report.json').read_text())
cloud=next(x for x in prior['results'] if x['mode']=='cloud')
cid=cloud['chat_id']


def tool_count(session):
    with sqlite3.connect('file:'+str(pathlib.Path.home()/'.hermes/state.db')+'?mode=ro',uri=True) as db:
        return db.execute("SELECT count(*) FROM messages WHERE session_id=? AND role='tool'",(session,)).fetchone()[0]


before=api('chats/'+cid)
assert before['state']=='idle','Test conversation is not idle; no duplicate request sent'
previous=tool_count(before['session'])
api('send',{'id':cid,'message':"Run exactly `printf '%s' hermes-pocket-tool-ok` using your terminal tool. Reply only with its output. Do not read any files or private memory."})
chat=wait(cid,180)
rows=tool_count(chat['session'])
new_rows=rows-previous if chat['session']==before['session'] else rows
reply=chat['messages'][-1]
passed=(chat['state']=='idle' and 'hermes-pocket-tool-ok' in reply['text'] and new_rows>0
        and 'terminal' in reply.get('tool_names',[]) and reply.get('private_memory_attached') is False)
report={'state':chat['state'],'provider':reply.get('provider'),'model':reply.get('model'),
        'private_memory_attached':reply.get('private_memory_attached'),'tool_names':reply.get('tool_names',[]),
        'hermes_tool_messages':rows,'new_tool_messages':new_rows,'passed':passed}
p=DATA/'tool-report.json';p.write_text(json.dumps(report,indent=2));p.chmod(0o600)
print(json.dumps(report))
raise SystemExit(0 if report['passed'] else 1)
