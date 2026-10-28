"""Maintenance fixes for the isolated sidecar. No cron registration or live mutation."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import json
import os
import re
import tempfile
import time
from evolution import Denied, Conflict, classify, digest, packed

def atomic_status(root,value):
    fd,path=tempfile.mkstemp(prefix='.status-',dir=root)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as f: f.write(packed(value)); f.flush(); os.fsync(f.fileno())
        os.replace(path,root/'extraction-status.json')
    finally:
        if os.path.exists(path): os.unlink(path)

class Extractor:
    def __init__(self,store,profile):
        if not isinstance(profile,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',profile): raise Denied('Explicit profile required')
        self.store=store; self.profile=profile
    def run(self,s,source,rows,consent=False,exported_at=None):
        s.check(True)
        if consent is not True: raise Denied('Explicit synthetic extraction action required')
        if not isinstance(source,str) or not source or len(source)>64: raise ValueError('Source ID required')
        lock=self.store.root/'extraction.lock'
        fd=os.open(lock,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        try:
            try: fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError: raise Denied('Extractor already running')
            # Only the lock owner may update status; a concurrent refusal is silent.
            try:
                if exported_at is not None and (not isinstance(exported_at,(int,float)) or not 0<=time.time()-exported_at<=60): raise ValueError('Stale export refused; no cached export fallback')
                if not isinstance(rows,list) or len(rows)>1000: raise ValueError('Bounded row list required')
                queued=0; key=s.project+':'+self.profile+':'+source
                with self.store.db() as c:
                    c.execute('BEGIN IMMEDIATE'); r=c.execute('SELECT value FROM watermarks WHERE profile=?',(key,)).fetchone(); watermark=r[0] if r else 0; maximum=watermark
                    for row in rows:
                        if not isinstance(row,dict) or not all(k in row for k in ('id','session_id','role','timestamp','content')): raise ValueError('Missing provenance')
                        if not isinstance(row['id'],int) or row['id']<1 or not isinstance(row['session_id'],str) or not row['session_id'] or row['timestamp'] is None or not isinstance(row['content'],str) or len(row['content'])>32000: raise ValueError('Invalid provenance/text')
                        if row['role'] not in {'user','assistant','tool','system'}: raise ValueError('Invalid role')
                        maximum=max(maximum,row['id'])
                        if row['id']<=watermark or row['role']!='user': continue
                        text=row['content']; flags=classify(text,row['role'])
                        if flags['disputed'] or flags['claim_type']!='user_statement': continue
                        # A candidate is never a verified fact; skip tasks, pasted instructions and quotes.
                        if re.search(r'(?im)^\s*(?:[-*+>#]|\d+[.)]|please (?!remember)|can you|could you|i want|i need|build |fix |run |subject:|dear )',text) or '"' in text or '```' in text: continue
                        if not re.search(r'\b(my name is|i prefer|i like|my timezone|my device|my phone|remember that)\b',text,re.I): continue
                        id=digest([s.project,self.profile,source,row['session_id'],row['id']])
                        c.execute('INSERT OR IGNORE INTO extracted VALUES(?,?,?,?,?,?,?,?,?,?)',(id,s.project,self.profile,source,row['session_id'],str(row['id']),'user',str(row['timestamp']),text,'pending_human_review'))
                        queued+=c.execute('SELECT changes()').fetchone()[0]
                    c.execute('INSERT OR REPLACE INTO watermarks VALUES(?,?)',(key,maximum)); self.store.audit(s,'candidate_extract',{'profile':self.profile,'source':source,'rows':len(rows),'queued':queued,'watermark':maximum},c)
                value={'status':'ok','at':time.time(),'profile':self.profile,'source':source,'rows_seen':len(rows),'queued':queued,'watermark':maximum,'promoted':0,'export_reused':False}
                atomic_status(self.store.root,value); return value
            except Exception:
                atomic_status(self.store.root,{'status':'failed','at':time.time(),'profile':self.profile,'code':'EXTRACTION_REJECTED','promoted':0,'export_reused':False}); raise
        finally:
            os.close(fd)
    def candidates(self,s):
        s.check()
        with self.store.db() as c:
            rows=[dict(r) for r in c.execute('SELECT * FROM extracted WHERE project=? AND profile=? ORDER BY message',(s.project,self.profile))]
        for r in rows:
            r.update(hash=digest([r[k] for k in ('project','profile','source','session','message','role','timestamp','text')]),verified=False,untrusted=True)
        return rows
    def review(self,s,id,expected_hash,decision,confirm=False):
        s.check(True)
        if confirm is not True or decision not in {'accept_reference','reject'}: raise Denied('Explicit candidate review required')
        row=next((r for r in self.candidates(s) if r['id']==id),None)
        if not row or row['hash']!=expected_hash: raise Denied('Exact project candidate required')
        state='reviewed_reference_not_verified' if decision=='accept_reference' else 'rejected'
        with self.store.db() as c:
            c.execute('UPDATE extracted SET state=? WHERE id=? AND project=? AND profile=?',(state,id,s.project,self.profile)); self.store.audit(s,'memory_candidate_'+decision,expected_hash,c)
        return {'id':id,'state':state,'verified':False,'live_memory_written':False,'automatically_retrievable':False}

def epoch(v):
    if isinstance(v,(int,float)): return float(v)
    if isinstance(v,str):
        try:
            dt=datetime.fromisoformat(v.replace('Z','+00:00'))
            if dt.tzinfo is None: return None
            return dt.timestamp()
        except ValueError: return None
    return None

def scheduler_health(job,script_status,ticker_heartbeat=None,now=None,timezone_name=None):
    now=time.time() if now is None else now
    last=epoch(job.get('last_run_at')); nxt=epoch(job.get('next_run_at')); hb=epoch(ticker_heartbeat)
    ticker=hb is not None and 0<=now-hb<=120
    observed=bool(last and job.get('completed',0)>0)
    return {'definition_enabled':job.get('enabled') is True,'schedule':job.get('schedule'),'timezone':timezone_name or 'unknown','ticker':'observed_recent' if ticker else 'not_observed','execution':'observed' if observed else 'not_recorded','last_scheduler_run':last,'script_status':script_status.get('status','legacy_unknown'),'script_time':script_status.get('at',script_status.get('last_run')),'next_run':nxt,'overdue':nxt is not None and nxt<now,'health':'healthy' if ticker and observed and script_status.get('status')=='ok' else 'attention_required','actions_taken':[],'sleep_restart_validation':'NOT_OBSERVED'}

def curator_result(result):
    if not isinstance(result,dict): return {'status':'failed','error':{'code':'INVALID_RESULT'},'summary':None,'mutations_may_have_occurred':True}
    text=str(result.get('final_response',result.get('llm_final','')))
    code=result.get('http_status')
    if '429' in text and 'HTTP' in text: code=429
    failed=bool(result.get('failed') or result.get('error') or result.get('llm_error') or code not in (None,200) or not text.strip() or re.search(r'API call failed|rate limit|temporarily at capacity',text,re.I))
    interrupted=bool(result.get('interrupted')); partial=bool(result.get('partial'))
    state='interrupted' if interrupted else 'partial' if partial else 'failed' if failed else 'ok'
    return {'status':state,'error':None if state=='ok' else {'code':'UPSTREAM_CAPACITY' if code==429 and 'capacity' in text.lower() else 'HTTP_ERROR' if code else 'RETURNED_FAILURE','http_status':code,'retryable':code==429},'summary':text[:2000] if state=='ok' else None,'mutations_may_have_occurred':state!='ok' or bool(result.get('tool_activity')),'autonomous_actions':False}

class RetryPolicy:
    """Decisions only; no network calls, sleeping or provider switching."""
    def __init__(self,max_attempts=3,max_delay=60,circuit_seconds=300):
        self.max_attempts=max_attempts; self.max_delay=max_delay; self.circuit_seconds=circuit_seconds; self.failures=0; self.open_until=0
    def failure(self,result,retry_after=None,now=None,jitter=.5):
        now=time.time() if now is None else now
        if self.open_until>now: return {'action':'deferred','until':self.open_until,'provider_switch':False}
        state=curator_result(result); self.failures+=1
        if not state.get('error') or not state['error'].get('retryable') or self.failures>=self.max_attempts:
            self.open_until=now+self.circuit_seconds; return {'action':'deferred','until':self.open_until,'provider_switch':False}
        delay=0
        if retry_after is not None:
            try: delay=max(0,float(retry_after))
            except (ValueError,TypeError):
                try: delay=max(0,parsedate_to_datetime(str(retry_after)).timestamp()-now)
                except (ValueError,TypeError,OverflowError): delay=0
        exponential=2**self.failures+min(1,max(0,jitter))
        delay=max(delay,exponential)
        if delay>self.max_delay:
            self.open_until=now+max(delay,self.circuit_seconds); return {'action':'deferred','until':self.open_until,'provider_switch':False}
        return {'action':'manual_retry_eligible','delay':delay,'attempts_remaining':self.max_attempts-self.failures,'provider_switch':False}
    def success(self): self.failures=0; self.open_until=0
