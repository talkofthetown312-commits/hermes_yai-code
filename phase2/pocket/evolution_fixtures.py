"""Host-registered synthetic fixtures matching the discovered store schemas."""
import json
from pathlib import Path
import sqlite3
from evolution import Source

def create(root):
    root=Path(root); root.mkdir(parents=True,exist_ok=True,mode=0o700)
    marker=root/'fixture-manifest.json'
    if marker.exists(): return json.loads(marker.read_text())
    sources=[]
    specs={
      'hermes':('CREATE TABLE messages(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,timestamp REAL)',"INSERT INTO messages VALUES(1,'fixture-session','user','I prefer synthetic blue widgets.',1000)"),
      'history':('CREATE TABLE history(id INTEGER PRIMARY KEY,session_id TEXT,role TEXT,content TEXT,timestamp TEXT)',"INSERT INTO history VALUES(1,'fixture-session','user','I prefer synthetic blue widgets.','1000')"),
      'knowledge':('CREATE TABLE knowledge(id INTEGER PRIMARY KEY,source TEXT,content TEXT,hash TEXT)',"INSERT INTO knowledge VALUES(1,'fixture-document','Synthetic widget knowledge.','fixture')"),
      'memories':('CREATE TABLE memories(id INTEGER PRIMARY KEY,date TEXT,content TEXT)',"INSERT INTO memories VALUES(1,'2000-01-01','Synthetic widget memory.')"),
      'chat':('CREATE TABLE chat(id INTEGER PRIMARY KEY,role TEXT,content TEXT,created_at TEXT)',"INSERT INTO chat VALUES(1,'assistant','Synthetic widget draft, not verified.','2000-01-01')"),
      'web':('CREATE TABLE messages(id INTEGER PRIMARY KEY,conversation_id TEXT,role TEXT,content TEXT,created_at TEXT)',"INSERT INTO messages VALUES(1,'fixture-conversation','user','The bank said the synthetic widget was wrong. I dispute that claim.','2000-01-01')"),
      'pocket':('CREATE TABLE chats(id TEXT PRIMARY KEY,title TEXT,session TEXT,messages TEXT,state TEXT,error TEXT,mode TEXT,model TEXT)',None)
    }
    schemas=json.loads((Path(__file__).resolve().parent.parent/'schema-fixtures.json').read_text())
    columns={'hermes':'id,session_id,role,content,timestamp','history':'id,session_id,role,content,timestamp','knowledge':'id,source,content,hash','memories':'id,date,content','chat':'id,role,content,created_at','web':'id,conversation_id,role,content,created_at'}
    for kind,(ddl,insert) in specs.items():
        ddl=schemas[kind]['ddl']
        if insert: insert=insert.replace(' VALUES','('+columns[kind]+') VALUES',1)
        path=root/(kind+'.sqlite3'); c=sqlite3.connect(path)
        try:
            c.execute(ddl)
            if insert: c.execute(insert)
            else: c.execute('INSERT INTO chats VALUES(?,?,?,?,?,?,?,?)',('fixture-chat','Synthetic','fixture-session',json.dumps([{'role':'user','text':'Synthetic widget Pocket message.'}]),'idle','','cloud',''))
            c.commit()
        finally: c.close()
        path.chmod(0o600); sources.append({'id':kind,'kind':kind,'file':path.name,'records':['fixture-chat:0'] if kind=='pocket' else ['1']})
    for id,kind,name,text in [('curated','markdown','curated.md','# Synthetic memory\nSynthetic widgets are reference material.\n'),('twin','twin','twin.md','# Synthetic project\nSynthetic widget Digital Twin fixture.\n'),('facts','facts','facts.jsonl',json.dumps({'fact':'Synthetic widget legacy candidate.','timestamp':None})+'\n')]:
        path=root/name; path.write_text(text); path.chmod(0o600); sources.append({'id':id,'kind':kind,'file':name,'records':['1']})
    manifest={'synthetic_only':True,'sources':sources,'extract_rows':[{'id':1,'session_id':'fixture-session','role':'assistant','timestamp':1000,'content':'My phone is a synthetic widget.'},{'id':2,'session_id':'fixture-session','role':'user','timestamp':1001,'content':'I prefer synthetic blue widgets.'}]}
    marker.write_text(json.dumps(manifest,indent=2)); marker.chmod(0o600); return manifest

def registered(root,manifest): return [Source(x['id'],x['kind'],Path(root)/x['file'],Path(root),'synthetic') for x in manifest['sources']]
