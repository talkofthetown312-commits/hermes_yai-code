"""Additional hardening regressions beyond the 64 original acceptance entries."""
import json
from pathlib import Path
import unittest
from run_acceptance import fixture,S,B,BOT,body,approved,require,rejects,examples,candidate
from evolution import *
from evolution_maintenance import Extractor,curator_result
import time

class Edges(unittest.TestCase):
    def test_registry_restart_requires_text_revision_reconsent(self):
        with fixture() as (root,st,_,r,*_):
            st.grant(S,'curated',['1']); self.assertEqual(r.search(S,'widget')['count'],1)
            p=r.sources['curated'].path; p.write_text('# New revision\nA revised widget reference.\n')
            again=Store(st.root); new=Retrieval(again,[Source('curated','markdown',p,root/'sources')]); self.assertEqual(new.search(S,'widget')['count'],0)
            again.grant(S,'curated',['1']); self.assertEqual(new.search(S,'widget')['count'],1)
    def test_scope_union_has_total_budget(self):
        with fixture() as (_,st,*_):
            st.grant(S,'source',[str(i) for i in range(200)])
            with self.assertRaises(Denied): st.grant(S,'source',['201'])
            self.assertEqual(len(st.scopes(S)['source']),200)
    def test_future_schema_not_mutated(self):
        with fixture() as (_,st,*_):
            with st.db() as c: c.execute('UPDATE meta SET version=999')
            before=file_hash(st.path)
            with self.assertRaises(Conflict): Store(st.root)
            self.assertEqual(file_hash(st.path),before)
    def test_body_unknown_fields_and_types_rejected(self):
        with fixture() as (_,_,_,_,w,_):
            bad=body(); bad['principal']='forged'
            with self.assertRaises(ValueError): w.teach(S,bad)
            v=w.teach(S,body())
            for val in (None,[],bad):
                with self.assertRaises(ValueError): w.edit(S,v['id'],val,1)
    def test_tamper_manifest_invalidates_even_passing_stored_approval(self):
        with fixture() as (_,st,_,_,w,_):
            v=approved(w)
            with st.db() as c: c.execute('UPDATE skills SET body=? WHERE id=?',(packed(body('external edit')),v['id']))
            with self.assertRaises(Conflict): w.reuse(S,v['id'],v['hash'],'task',True)
    def test_reuse_has_native_skill_format_without_installing(self):
        with fixture() as (_,_,_,_,w,_):
            v=approved(w); bundle=w.reuse(S,v['id'],v['hash'],'task',True)
            self.assertTrue(bundle['skill_md'].startswith('---\nname: evolution-'))
            self.assertEqual(digest(bundle['skill_md']),bundle['skill_md_sha256'])
            self.assertFalse(bundle['installed']); self.assertEqual(bundle['additional_tools'],[])
    def test_extracted_candidate_project_profile_and_review_boundaries(self):
        with fixture() as (_,st,m,*_):
            e=Extractor(st,'explicit-profile'); e.run(S,'history',m['extract_rows'],True,time.time())
            rows=e.candidates(S); self.assertEqual(len(rows),1); self.assertEqual(e.candidates(B),[])
            r=rows[0]
            for who,hash in [(B,r['hash']),(BOT,r['hash']),(S,'stale')]:
                with self.assertRaises(ValueError): e.review(who,r['id'],hash,'accept_reference',True)
            out=e.review(S,r['id'],r['hash'],'accept_reference',True)
            self.assertFalse(out['live_memory_written']); self.assertFalse(out['automatically_retrievable']); self.assertFalse(out['verified'])
            # Same source/profile in a separately granted project does not inherit another project's watermark.
            self.assertEqual(e.run(B,'history',m['extract_rows'],True,time.time())['queued'],1)
    def test_returned_http_success_and_empty_failure(self):
        self.assertEqual(curator_result({'http_status':200,'final_response':'Synthetic summary'})['status'],'ok')
        for v in ({},{'http_status':500},{'llm_error':'fixture'}):
            self.assertEqual(curator_result(v)['status'],'failed'); self.assertIsNone(curator_result(v)['summary'])
    def test_dataset_evidence_and_review_are_project_local(self):
        with fixture() as (_,_,_,_,_,d):
            v=candidate(d,consent=False)
            with self.assertRaises(ValueError): d.review(B,v['id'],v['hash'],True)
            with self.assertRaises(ValueError): d.select(B,examples(),v['data']['evidence'],True)
    def test_edited_answer_cannot_reuse_old_success_proof(self):
        with fixture() as (_,_,_,_,_,d):
            v=candidate(d); changed=d.edit(S,v['id'],examples('NEW_SYNTHETIC_TARGET'))
            with self.assertRaises(ValueError): d.review(S,v['id'],changed['hash'],True)
            with self.assertRaises(ValueError): d.reverify(S,v['id'],v['data']['evidence'])
            with self.assertRaises(ValueError): d.export(S,[v['id']],True)
    def test_external_dataset_content_edit_invalidates_hash(self):
        with fixture() as (_,st,_,_,_,d):
            v=candidate(d); data=v['data']; data['messages']=examples('TAMPERED')
            with st.db() as c: c.execute('UPDATE candidates SET data=? WHERE id=?',(packed(data),v['id']))
            with self.assertRaises(Conflict): d.export(S,[v['id']],True)
    def test_shared_reference_keeps_not_verified_label(self):
        with fixture() as (_,st,m,r,*_):
            for s in m['sources']: st.grant(S,s['id'],s['records'])
            result=r.search(S,'widget')
            self.assertTrue(all(not x['verified'] and x['untrusted'] for x in result['results']))
            self.assertTrue(all(x['project']=='alpha' for x in result['results']))

if __name__=='__main__': unittest.main(verbosity=2)
