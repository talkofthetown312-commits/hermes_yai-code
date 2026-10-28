#!/usr/bin/env python3
"""Explicit real Cloud test: synthetic photo/text only; no user document access."""
import base64
import io
import json
import os
from pathlib import Path
import time
import urllib.request
from PIL import Image,ImageDraw

DATA=Path.home()/'.hermes-pocket'
TOKEN=(DATA/'pairing-token').read_text().strip()
BASE='http://127.0.0.1:8766/api/'

def api(route,body=None):
    req=urllib.request.Request(BASE+route,data=json.dumps(body).encode() if body is not None else None,headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as r:return json.load(r)

def main():
    cid=api('chats',{'mode':'cloud'})['id']
    image=Image.new('RGB',(360,180),'white');draw=ImageDraw.Draw(image)
    draw.rectangle((10,10,150,165),fill=(240,20,20));draw.text((165,70),'POCKET 73',fill='black',font_size=24)
    stream=io.BytesIO();image.save(stream,format='PNG')
    ids=[]
    for name,raw in [('synthetic-note.txt',b'Synthetic attachment test only. Verification code: pocket-ui-amber-73.\n'),('synthetic-photo.png',stream.getvalue())]:
        f=api('files/upload',{'chat':cid,'name':name,'data':base64.b64encode(raw).decode()});ids.append(f['id'])
    api('send',{'id':cid,'message':'This is a synthetic interface test. Read only the two attached fixtures. State the verification code from the note and the main block colour and printed text in the photo. Then use your terminal tool to create a file named interface-check.csv in the output folder specified below with exactly this content: code,status\\npocket-ui-amber-73,ok\\n (use actual line breaks). Do not read other files or private memories. Reply concisely with the observed code, colour, printed text and whether file creation succeeded.','attachments':ids,'consent':True})
    deadline=time.monotonic()+240
    while True:
        chat=api('chats/'+cid)
        if chat['state']!='running':break
        if time.monotonic()>deadline:raise TimeoutError('Synthetic live turn still running; not retried or cancelled.')
        time.sleep(1)
    assistant=chat['messages'][-1];text=assistant.get('text','').lower()
    files=api('artifacts?chat='+cid)
    file=next((f for f in files if f['name']=='interface-check.csv'),None)
    downloaded=base64.b64decode(api('files/'+file['id']+'?chat='+cid)['data']) if file else b''
    tools=assistant.get('tools',[])
    checks={
        'completed_turn':chat['state']=='idle',
        'attachment_text_read':'pocket-ui-amber-73' in text,
        'native_photo_observed':'red' in text and 'pocket 73' in text,
        'real_tool_details':any(t.get('arguments') and t.get('output') and t['status']=='completed' for t in tools),
        'generated_file_download_exact':downloaded==b'code,status\npocket-ui-amber-73,ok\n',
        'private_memory_not_attached':assistant.get('private_memory_attached') is False,
        'attachment_ids_persisted':[a['id'] for a in chat['messages'][0]['attachments']]==ids,
    }
    report={'checks':checks,'passed':all(checks.values()),'chat_id':cid,'provider':assistant.get('provider'),'model':assistant.get('model'),'tool_count':len(tools),'download_bytes':len(downloaded),'error':chat.get('error','')}
    path=DATA/'interface-live-report.json';fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))
    if not report['passed']:
        print('Synthetic fixture reply:',assistant.get('text','')[:1500])
        raise SystemExit(1)

if __name__=='__main__':main()
