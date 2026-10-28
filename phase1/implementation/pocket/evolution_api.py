"""Authenticated staged Pocket feature API. No runtime registration of live paths."""
import json
from pathlib import Path
import time
from evolution import Session, Store, Retrieval, Workbench, Dataset, Denied, Conflict, safe_path, file_hash
from evolution_fixtures import create, registered
from evolution_maintenance import Extractor, scheduler_health, curator_result
from evolution_workers import JCodeBroker

class EvolutionService:
    def __init__(self,data,stage):
        self.data=Path(data); self.stage=Path(stage).resolve()
        if self.data.is_symlink() or not self.data.resolve().is_relative_to(self.stage) or self.data.resolve()==self.stage: raise Denied('Staged private data required')
        self.store=Store(self.data/'evolution'); self.manifest=create(self.data/'synthetic-sources'); self.sources=registered(self.data/'synthetic-sources',self.manifest)
        catalog=json.loads((self.stage/'skill-catalog.json').read_text())
        self.retrieval=Retrieval(self.store,self.sources); self.workbench=Workbench(self.store,catalog); self.dataset=Dataset(self.store); self.jcode=JCodeBroker(self.store)
        self.project='phase1-synthetic'
        self.examples=[{'role':'user','content':'Reply with the synthetic fixture marker.'},{'role':'assistant','content':'SYNTHETIC_FIXTURE_OK'}]
        with self.store.db() as c:
            r=c.execute('SELECT id FROM evidence WHERE project=? LIMIT 1',(self.project,)).fetchone()
        self.evidence_id=r[0] if r else self.dataset.evidence(self.session(),[{'expected':'SYNTHETIC_FIXTURE_OK','actual':self.examples[1]['content']}],self.examples)
    def session(self): return Session('paired-local-owner',self.project,(self.project,),True)
    def get(self,path,query):
        s=self.session()
        if path=='state':
            with self.store.db() as c: candidates=[{'id':r['id'],'hash':r['hash'],'reviewed':bool(r['review']),'revoked':bool(r['revoked'])} for r in c.execute('SELECT * FROM candidates WHERE project=?',(s.project,))]
            return {'stage_only':True,'synthetic_only':True,'project':s.project,'skills':self.workbench.library(s),'source_choices':[{'source_id':x['id'],'records':x['records'],'purpose':'local'} for x in self.manifest['sources']],'grants':{k:sorted(v) for k,v in self.store.scopes(s).items()},'candidates':candidates,'scheduler':scheduler_health({'enabled':True,'schedule':'0 */6 * * *','last_run_at':None,'completed':0,'next_run_at':time.time()-3600},{'status':'not_run'},None),'curator_example':curator_result({'failed':True,'http_status':429,'final_response':'HTTP 429: temporarily at capacity upstream'}),'jcode':'disabled_pending_private_antigravity_reauthentication','training':'disabled','execution':'guidance_only_no_tools'}
        if path=='memory-candidates': return Extractor(self.store,'stage-default').candidates(s)
        if path=='search': return self.retrieval.search(s,query.get('q',[''])[0])
        if path=='skill': return self.workbench.view(s,query.get('id',[''])[0])
        if path=='history': return self.workbench.history(s,query.get('id',[''])[0])
        if path=='candidate': return self.dataset.preview(s,query.get('id',[''])[0])
        if path=='reference':
            id=query.get('id',[''])[0]; ref=self.workbench.catalog.get(id)
            if not ref: raise Denied('Reference unavailable')
            p=Path(ref['path'])
            if file_hash(p)!=ref['sha256'] or p.is_symlink(): raise Conflict('Reference changed')
            return {'id':id,'state':'legacy_reference','sha256':ref['sha256'],'content':p.read_text(),'executes':False}
        raise Denied('Unknown Evolution endpoint')
    def post(self,path,body):
        s=self.session()
        fields={
          'grant':{'source','records','confirm'},'revoke-grant':{'source'},
          'teach':{'body','legacy'},'edit-skill':{'id','body','revision'},'test':{'id','revision','confirm'},'approve':{'id','hash','test_hash','confirm'},'reuse':{'id','hash','task','confirm'},'revoke-skill':{'id'},'restore-draft':{'id','old_revision','revision'},
          'extract-fixture':{'confirm'},'review-memory':{'id','hash','decision','confirm'},'select-example':{'confirm'},'edit-candidate':{'id','messages'},'review':{'id','hash','confirm'},'revoke-candidate':{'id'},'export':{'ids','confirm'},'jcode':{'packet'}
        }
        if path not in fields or not isinstance(body,dict) or set(body)-fields[path]: raise Denied('Unknown operation or unexpected fields')
        if path=='grant':
            allowed=next((x['records'] for x in self.manifest['sources'] if x['id']==body.get('source')),None)
            records=body.get('records')
            if body.get('confirm') is not True or not isinstance(records,list) or not allowed or not set(records)<=set(allowed): raise Denied('Exact synthetic source selection required')
            self.store.grant(s,body['source'],records); return {'ok':True}
        if path=='revoke-grant': self.store.revoke_grant(s,body['source']); return {'ok':True}
        if path=='teach': return self.workbench.teach(s,body['body'],legacy=body.get('legacy'))
        if path=='edit-skill': return self.workbench.edit(s,body['id'],body['body'],body['revision'])
        if path=='test': return self.workbench.test(s,body['id'],body['revision'],body.get('confirm'))
        if path=='approve': return self.workbench.approve(s,body['id'],body['hash'],body['test_hash'],body.get('confirm'))
        if path=='reuse': return self.workbench.reuse(s,body['id'],body['hash'],body['task'],body.get('confirm'))
        if path=='revoke-skill': self.workbench.revoke(s,body['id']); return {'ok':True}
        if path=='restore-draft': return self.workbench.restore_draft(s,body['id'],body['old_revision'],body['revision'])
        if path=='review-memory': return Extractor(self.store,'stage-default').review(s,body['id'],body['hash'],body['decision'],body.get('confirm'))
        if path=='extract-fixture': return Extractor(self.store,'stage-default').run(s,'fixture-history',self.manifest['extract_rows'],body.get('confirm'),time.time())
        if path=='select-example': return self.dataset.select(s,self.examples,self.evidence_id,body.get('confirm'))
        if path=='edit-candidate': return self.dataset.edit(s,body['id'],body['messages'])
        if path=='review': return self.dataset.review(s,body['id'],body['hash'],body.get('confirm'))
        if path=='revoke-candidate': self.dataset.revoke(s,body['id']); return {'ok':True}
        if path=='export': return self.dataset.export(s,body['ids'],body.get('confirm'))
        if path=='jcode': return self.jcode.submit(s,body['packet'])
        raise Denied('Unsupported action')
