#!/usr/bin/env python3
"""Preparation acceptance only. Does not run planned implementation/model tests."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

ROOT=Path(__file__).resolve().parent
HOME=Path.home()
results=[]


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def check(name, fn):
    try:
        detail=fn()
        results.append({'check':name,'passed':True,'detail':detail})
    except Exception as e:
        results.append({'check':name,'passed':False,'error':type(e).__name__+': '+str(e)})


def require(value):
    if not value:raise AssertionError('Required invariant failed')


def main():
    os.umask(0o077)
    # Only this new private staging tree; never chmod original source stores.
    for base,dirs,files in os.walk(ROOT,followlinks=False):
        Path(base).chmod(0o700)
        for name in files:
            p=Path(base)/name
            require(not p.is_symlink());p.chmod(0o600)
    b=ROOT/'preservation';m=json.loads((b/'manifest.json').read_text());v=json.loads((b/'verification.json').read_text())
    def hashes():
        for e in m['files']:require(sha(b/'payload'/e['relative'])==e['sha256'])
        require(sha(b/'manifest.json')==v['manifest_sha256'])
        return {'payload_hashes':len(m['files']),'manifest_hashes':1}
    check('backup_payload_and_manifest_hashes',hashes)
    def perms():
        for e in m['files']:require(stat.S_IMODE((b/'payload'/e['relative']).stat().st_mode)==0o600)
        for p in [ROOT,b,b/'payload',b/'restore-drill']:require(stat.S_IMODE(p.stat().st_mode)==0o700)
        return {'private_payloads':len(m['files']),'private_roots':4}
    check('private_permissions',perms)
    def sqlite_drills():
        n=tables=0
        for e in m['files']:
            if e['kind']!='sqlite-online-backup':continue
            p=b/'restore-drill'/e['relative'];require(sha(p)==e['sha256'])
            c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
            try:
                require(c.execute('PRAGMA integrity_check').fetchall()==[('ok',)])
                for table,count in e['rows'].items():
                    require(c.execute('SELECT COUNT(*) FROM "'+table.replace('"','""')+'"').fetchone()[0]==count);tables+=1
            finally:c.close()
            n+=1
        require(n==11)
        return {'databases':n,'table_counts':tables}
    check('isolated_sqlite_restore_integrity_and_counts',sqlite_drills)
    def source_preserved():
        n=0
        prefixes=['.hermes/memories/','.hermes/memory/','.hermes/digital-twin/','.hermes/scripts/','.hermes/cron/','hermes-pocket/','.hermes/skills/']
        for e in m['files']:
            rel=e['relative']
            if e['kind']=='byte-copy' and (any(rel.startswith(p) for p in prefixes) or rel=='.hermes/config.yaml') and rel!='.hermes/skills/.usage.json':
                require(sha(Path(e['source']))==e['sha256']);n+=1
        return {'source_files_unchanged':n,'usage_json_excluded':'Hermes tool usage telemetry naturally updates'}
    check('original_memory_sources_skills_pocket_config_preserved',source_preserved)
    def coverage():
        got={e['relative'] for e in m['files']}
        expected={'.hermes/state.db','.hermes/kanban.db','.hermes-pocket/chats.sqlite3',
            'local-ai/hermes_history.db','local-ai/hermes_knowledge.db','local-ai/memory.db',
            'local-ai/personal_chat.db','local-ai/web_conversations.db'}
        require(expected<=got)
        for prefix in ['.hermes/memories/','.hermes/memory/','.hermes/skills/','.hermes/digital-twin/']:
            require(any(p.startswith(prefix) for p in got))
        # A skill documentation category named models/ is not a weight directory.
        require(not any(p.startswith('local-ai/models/') or p.endswith(('.gguf','.safetensors')) for p in got))
        return {'required_active_databases':len(expected),'models_excluded':True}
    check('declared_preservation_coverage',coverage)
    def skills():
        count=sum(1 for e in m['files'] if e['relative'].startswith('.hermes/skills/') and e['relative'].endswith('/SKILL.md') and '/.archive/' not in e['relative'] and '/.curator_backups/' not in e['relative'])
        require(count==23);return {'active_reference_skills':count}
    check('baseline_active_skill_inventory',skills)
    def plan_status():
        t=json.loads((ROOT/'TEST_PLAN.json').read_text());require(t['test_count']==len(t['tests'])==64)
        require(len({x['id'] for x in t['tests']})==64)
        require(all(x['status']=='NOT_RUN' for x in t['tests']))
        return {'planned_not_run_cases':64,'false_passes':0}
    check('test_plan_unique_and_honest',plan_status)
    def training_disabled():
        g=json.loads((ROOT/'GPU_LORA_PLAN.json').read_text())
        for k in ['enabled','training_approved','weights_download_approved','gpu_provisioning_approved','personal_dataset_export_approved','model_promotion_approved']:require(g[k] is False)
        require(g['dataset']['real_records_approved']==0 and g['base']['revision'] is None)
        require(not list(ROOT.glob('*.jsonl')))
        return {'training_download_export_promotion':'disabled','real_dataset_exported':False}
    check('gpu_and_personal_export_gates_closed',training_disabled)
    def jcode():
        p=ROOT/'jcode-review-retry';d=json.loads((p/'result.json').read_text())
        require(d['exit_code']==1 and d['tools']=='none' and d['memory_enabled'] is False)
        require('No Antigravity tokens found' in (p/'stderr.private.log').read_text())
        require(d['config_unchanged'] is True)
        require(sha(p/'config.before.private')==sha(HOME/'.jcode/config.toml'))
        require(d['elapsed_seconds']<90 and d['stdout_bytes']+d['stderr_bytes']<98304)
        return {'bounded_attempt_logged':True,'config_unchanged':True,'actual_inference':'BLOCKED_MISSING_ANTIGRAVITY_AUTH'}
    check('jcode_boundary_failure_record_and_config',jcode)
    def diagnostics():
        d=json.loads((ROOT/'diagnostic-evidence.json').read_text())
        require(d['extractor_role_regression']['provenance_lost'] is True)
        f=d['curator_failure_fields'];require('HTTP 429' in f['llm_final'] and 'capacity upstream' in f['llm_final'] and f['llm_error'] is None)
        return {'extractor_bug_reproduced':True,'curator_capacity_error_and_status_gap_evidenced':True}
    check('root_cause_evidence_retained',diagnostics)
    def document_contract():
        text=(ROOT/'PLAN.md').read_text()
        for heading in ['Unified read-only retrieval','Teach -> Test -> Approve -> Reuse','Bounded JCode','Consent-reviewed dataset','Isolated Qwen','Optional GPU LoRA','Root causes','Gate A','Gate B','Gate C','Gate D','Rollback']:
            require(heading in text)
        require('JCode advisory response NOT obtained' in text)
        require('Inference remains NOT RUN' in text)
        return {'required_plan_sections':12,'deployment_training_inference_claimed':False}
    check('plan_sections_approval_and_claim_boundaries',document_contract)
    summary={'scope':'PREPARATION_ONLY_NOT_IMPLEMENTATION_TESTS','passed':sum(x['passed'] for x in results),
             'failed':sum(not x['passed'] for x in results),'checks':results,
             'implementation_cases_run':0,'model_inference_run':False,'training_run':False}
    (ROOT/'PREPARATION_QA.json').write_text(json.dumps(summary,indent=2));(ROOT/'PREPARATION_QA.json').chmod(0o600)
    print(json.dumps(summary,indent=2))
    raise SystemExit(1 if summary['failed'] else 0)

if __name__=='__main__':main()
