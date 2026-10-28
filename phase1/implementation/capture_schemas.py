#!/usr/bin/env python3
"""Capture schema metadata ONLY from verified private baseline snapshots (no rows)."""
import json
from pathlib import Path
import sqlite3
R=Path(__file__).resolve().parent.parent
maps={'hermes':('.hermes/state.db','messages'),'history':('local-ai/hermes_history.db','history'),'knowledge':('local-ai/hermes_knowledge.db','knowledge'),'memories':('local-ai/memory.db','memories'),'chat':('local-ai/personal_chat.db','chat'),'web':('local-ai/web_conversations.db','messages'),'pocket':('.hermes-pocket/chats.sqlite3','chats')}
result={}
for kind,(relative,table) in maps.items():
    with sqlite3.connect((R/'preservation/payload'/relative).as_uri()+'?mode=ro&immutable=1',uri=True) as c:
        sql=c.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone()[0]
        cols=[{'name':r[1],'type':r[2],'nullable':not r[3],'default':r[4],'primary_key':bool(r[5])} for r in c.execute('PRAGMA table_info("'+table+'")')]
    result[kind]={'table':table,'ddl':sql,'columns':cols,'origin_relative':relative,'rows_copied':0}
(Path(__file__).resolve().parent/'schema-fixtures.json').write_text(json.dumps(result,indent=2))
print('Seven baseline table definitions captured; zero source rows copied.')
