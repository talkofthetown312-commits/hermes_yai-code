#!/usr/bin/env python3
"""Assert actual preview HTTP behavior plus explicitly labelled offline scope checks."""
from pathlib import Path
import os,sys,json,urllib.request,urllib.error,hashlib,sqlite3
r=Path(__file__).resolve().parent
os.umask(0o077);sys.dont_write_bytecode=True
sys.path.insert(0,str(r/'pocket'))
from urllib.parse import urlsplit
base=os.environ['FIXTURE_URL'].rstrip('/')
address=urlsplit(base)
if address.scheme!='http' or address.hostname!='127.0.0.1' or not address.port or address.port in (8766,8877):
    raise RuntimeError('Feature tests require a new ephemeral synthetic loopback server')
key_path=Path(os.environ['FIXTURE_TOKEN_FILE']).resolve()
if not key_path.is_relative_to(r/'handoff-runtime'):
    raise RuntimeError('Only the test-owned synthetic pairing file is permitted')
key=key_path.read_text().strip()
checks=[]
def check(name,ok,kind='HTTP'):
    checks.append({'name':name,'status':'PASS' if ok else 'FAIL','kind':kind})
    if not ok: raise AssertionError(name)
def req(path,data=None,auth=True,origin=None,host=None):
    headers={'Content-Type':'application/json'}
    if auth: headers['Authorization']='Bearer '+key
    if origin: headers['Origin']=origin
    if host: headers['Host']=host
    q=urllib.request.Request(base+path,headers=headers,data=json.dumps(data).encode() if data is not None else None)
    try:
        with urllib.request.urlopen(q,timeout=5) as out:
            raw=out.read(); code=out.status; hdr=dict(out.headers)
            return code,json.loads(raw) if 'application/json' in hdr.get('Content-Type','') else raw.decode(),hdr
    except urllib.error.HTTPError as e:
        code=e.code;e.close();return code,None,{}
def evo(path,data=None):
    code,out,_=req('/api/evolution/'+path,data);check('HTTP success '+path.split('?')[0],code==200);return out
try:
    state=evo('state')
    check('synthetic-only phase2 project',state['synthetic_only'] and state['project']=='phase2-synthetic')
    check('only synthetic legacy reference',len(state['skills']['legacy'])==1 and state['skills']['legacy'][0]['id']=='synthetic-guidance-reference')
    ref=evo('reference?id=synthetic-guidance-reference');check('synthetic reference not executable',not ref['executes'] and 'Synthetic guidance' in ref['content'])
    check('no-model runtime capability',req('/api/status')[1]['ready'] is False)
    check('no live model inventory contacted',req('/api/models')[1]['models']==[])
    check('default deny after UI revocation',evo('search?q=widget')['count']==0)
    denials=[
      ('unauthenticated API','/api/evolution/state',None,{'auth':False},401),
      ('foreign Host','/api/evolution/state',None,{'host':'untrusted.invalid'},403),
      ('foreign Origin','/api/evolution/grant',{'source':'hermes','records':['1'],'confirm':True},{'origin':'https://untrusted.invalid'},403),
      ('client project override','/api/evolution/teach',{'body':{},'project':'another-project'},{},400),
      ('client principal override','/api/evolution/grant',{'source':'hermes','records':['1'],'confirm':True,'principal':'admin'},{},400),
      ('wildcard grant','/api/evolution/grant',{'source':'hermes','records':['*'],'confirm':True},{},400),
      ('unregistered path source','/api/evolution/grant',{'source':'../../state.db','records':['1'],'confirm':True},{},400),
      ('unknown reference','/api/evolution/reference?id=hermes-agent',None,{},400),
      ('paid JCode packet','/api/evolution/jcode',{'packet':{'provider':'openrouter'}},{},400),
      ('chat mutations disabled','/api/chats',{'mode':'cloud'},{},403),
      ('chat sends disabled','/api/send',{'message':'synthetic'},{},403),
      ('attachment uploads disabled','/api/files/upload',{'data':'synthetic'},{},403)]
    for name,path,data,kw,code in denials:check(name,req(path,data,**kw)[0]==code)
    for path in ('/.env','/data/pairing-token','/skill-catalog.json','/synthetic-reference.md','/../schema-fixtures.json','/api/evolution/../../data/pairing-token'):
        check('private route denied '+path,req(path)[0] in (400,404))
    _,html,headers=req('/')
    check('staging banner and mobile viewport', 'PHONE STAGING ONLY' in html and 'width=device-width' in html)
    check('self-only script CSP',"script-src 'self'" in headers.get('Content-Security-Policy',''))
    check('no-referrer and no-store',headers.get('Referrer-Policy')=='no-referrer' and headers.get('Cache-Control')=='no-store')
    for asset in ('/app.js','/evolution.js','/style.css','/evolution.css'):check('asset '+asset,req(asset)[0]==200)
    for source in ('hermes','history','web','chat'):
        evo('grant',{'source':source,'records':['1'],'confirm':True})
    result=evo('search?q=widget')
    merged=next(x for x in result['results'] if x['source_kind']=='hermes')
    check('dedup retains both source citations',len(merged['citations'])==2 and {x['source_id'] for x in merged['citations']}=={'hermes','history'})
    check('citation has record/session/role/hash',all(all(k in c for k in ('record_id','session_id','author_role','timestamp','content_hash','locator')) for c in merged['citations']))
    check('returned rows bound to project',all(x['project']=='phase2-synthetic' and x['sensitivity']=='synthetic' for x in result['results']))
    check('disputed reported claim labelled',any(x['disputed'] and x['claim_type']=='reported_claim' for x in result['results']))
    check('assistant draft not a verified user fact',any(x['author_role']=='assistant' and x['claim_type']=='prior_ai' and not x['verified'] for x in result['results']))
    for source in ('hermes','history','web','chat'):evo('revoke-grant',{'source':source})
    check('all revoked results unavailable',evo('search?q=widget')['count']==0)
    check('scheduler demonstration not falsely healthy',state['scheduler']['health']=='attention_required' and state['scheduler']['actions_taken']==[])
    check('429 structured and no false summary',state['curator_example']['summary'] is None and state['curator_example']['error']['code']=='UPSTREAM_CAPACITY')
    check('health fixture visibly labelled', 'SIMULATED HEALTH FIXTURE' in req('/evolution.js')[1])
    check('extractor replay idempotent',evo('extract-fixture',{'confirm':True})['queued']==0)
    memories=evo('memory-candidates')
    check('authorship and review not live promotion',len(memories)==1 and memories[0]['role']=='user' and memories[0]['state']=='reviewed_reference_not_verified' and not memories[0]['verified'])
    c=evo('select-example',{'confirm':True}); c=evo('candidate?id='+c['id'])
    check('unreviewed export blocked',req('/api/evolution/export',{'ids':[c['id']],'confirm':True})[0]==400)
    evo('review',{'id':c['id'],'hash':c['hash'],'confirm':True})
    out=evo('export',{'ids':[c['id']],'confirm':True})
    row=json.loads(out['jsonl']);check('exact synthetic messages-only JSONL',set(row)=={'messages'} and row['messages'][1]['content']=='SYNTHETIC_FIXTURE_OK')
    evo('revoke-candidate',{'id':c['id']})
    check('revoked export blocked',req('/api/evolution/export',{'ids':[c['id']],'confirm':True})[0]==400)
    j=evo('jcode',{'packet':{'kind':'review','specification':'Review synthetic widget guidance only.','synthetic':True,'provider':'antigravity','wall_seconds':5,'max_output_bytes':1000}})
    check('valid JCode task stays disabled with no fallback',j['status'].startswith('disabled') and not j['provider_fallback'] and not j['autonomous_execution'])
    # Scope/restart checks in a separate, wholly synthetic sidecar; no original store opens.
    from evolution import Store,Session,Retrieval,Workbench,Denied,REQUIRED
    from evolution_fixtures import create,registered
    fixture=r/'qa-scope/sources';manifest=create(fixture)
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in fixture.iterdir() if p.is_file()}
    store=Store(r/'qa-scope/sidecar'); sources=registered(fixture,manifest); ret=Retrieval(store,sources); work=Workbench(store,[])
    a=Session('fixture-owner','project-a',('project-a',)); b=Session('fixture-owner','project-b',('project-b',))
    store.grant(a,'hermes',['1']); check('project A grant works',ret.search(a,'widget')['count']==1,'OFFLINE_SCOPE')
    check('project B cannot inherit grant',ret.search(b,'widget')['count']==0,'OFFLINE_SCOPE')
    d=work.teach(a,{k:'Synthetic '+k+' fixture.' for k in REQUIRED})
    try:work.view(b,d['id']);denied=False
    except Denied:denied=True
    check('project B cannot view project A draft',denied,'OFFLINE_SCOPE')
    reconstructed=Store(r/'qa-scope/sidecar'); rr=Retrieval(reconstructed,registered(fixture,manifest))
    check('grant persists across reconstruction',rr.search(a,'widget')['count']==1,'OFFLINE_SCOPE')
    reconstructed.revoke_grant(a,'hermes');check('revoke persists across reconstruction',Retrieval(Store(r/'qa-scope/sidecar'),registered(fixture,manifest)).search(a,'widget')['count']==0,'OFFLINE_SCOPE')
    check('read-only fixture retrieval left sources byte-identical',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before.items()),'OFFLINE_SCOPE')
    css=req('/evolution.css')[1]
    check('mobile touch targets and readable input styles','min-height:44px' in css and 'font-size:16px' in css,'STATIC_UI')
    check('wrapping, scroll and narrow-screen CSS','overflow-wrap:anywhere' in css and '@media(max-width:600px)' in css and 'overscroll-behavior:contain' in css,'STATIC_UI')
    check('picker and visible share/save controls','picker.type = \'file\'' in req('/evolution.js')[1] and 'Share reviewed synthetic JSONL' in req('/evolution.js')[1],'STATIC_UI')
finally:
    report={'checks':checks,'passed':sum(x['status']=='PASS' for x in checks),'failed':sum(x['status']=='FAIL' for x in checks),'actual_phone_rendering':'NOT_VERIFIED','native_picker_share_save':'MANUAL_REQUIRED','production_deployment':False}
    (r/'FEATURE_RESULTS.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='checks'}))
