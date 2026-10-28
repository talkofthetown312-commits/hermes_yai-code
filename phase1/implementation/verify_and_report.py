#!/usr/bin/env python3
"""Final stage-only QA, preservation checks, exact diff and approval reports."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
R=Path(__file__).resolve().parent
BASE=R.parent
sys.path.insert(0,str(R/'pocket'))
from evolution import file_hash,packed
from evolution_api import EvolutionService

def save(name,value):
    p=R/name; p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    p.write_text(json.dumps(value,indent=2,ensure_ascii=False)); p.chmod(0o600)
def rows(path,expected):
    with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True) as c:
        assert c.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        for table,count in expected.items(): assert c.execute('SELECT COUNT(*) FROM "'+table.replace('"','""')+'"').fetchone()[0]==count

def main():
    os.umask(0o077)
    hist=R/'debug-history/pre-final'; hist.mkdir(mode=0o700,parents=True,exist_ok=True)
    for p in R.glob('failure-*.log'): shutil.move(str(p),str(hist/p.name))
    if (R/'ACCEPTANCE_RESULTS.json').exists(): shutil.copyfile(R/'ACCEPTANCE_RESULTS.json',hist/'previous-acceptance.json')
    for script,log in [('test_edges.py','EXTRA_QA.log'),('run_acceptance.py','ACCEPTANCE_RUN.log')]:
        q=subprocess.run([sys.executable,str(R/script)],cwd=R,capture_output=True,text=True,timeout=300)
        (R/log).write_text(q.stdout+q.stderr)
        if q.returncode: print(q.stdout+q.stderr); raise SystemExit(q.returncode)
    extra_text=(R/'EXTRA_QA.log').read_text(); extra_count=int(re.search(r'Ran (\d+) tests',extra_text).group(1))
    save('EXTRA_QA.json',{'status':'PASS','tests':extra_count,'failed':0,'log':'EXTRA_QA.log'})
    results=json.loads((R/'ACCEPTANCE_RESULTS.json').read_text()); http=json.loads((R/'HTTP_QA.json').read_text())
    assert results['entries_assessed']==64 and results['counts'].get('FAIL',0)==0 and http['legacy_failures']==0 and http['legacy_errors']==0
    demo=EvolutionService(R/'data',R)
    with demo.store.db() as c: demo_counts={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('grants','skills','candidates','extracted','tasks')}
    assert all(v==0 for v in demo_counts.values())
    save('DATA_LOCATIONS.json',{'active':'staging_only_no_service_running','sidecar':str(demo.store.path),'synthetic_sources':str(R/'data/synthetic-sources'),'legacy_references':str(R/'skill-catalog.json'),'initial_workflow_counts':demo_counts,'private_stores_registered':False,'live_paths_written':[]})
    guard=json.loads((R/'prechange-manifest.json').read_text()); baseline=json.loads((BASE/'preservation/manifest.json').read_text()); verification=json.loads((BASE/'preservation/verification.json').read_text())
    assert file_hash(BASE/'preservation/manifest.json')==verification['manifest_sha256']
    for e in baseline['files']:
        p=BASE/'preservation/payload'/e['relative']; assert file_hash(p)==e['sha256']; assert stat.S_IMODE(p.stat().st_mode)==0o600
        if e['kind']=='sqlite-online-backup': rows(p,e['rows'])
    fresh_files=0
    for e in guard['files']:
        assert file_hash(Path(e['source']))==e['sha256'],e['relative']
        p=R/'prechange-backup'/e['relative']
        if p.exists(): assert file_hash(p)==e['sha256']; fresh_files+=1
    fresh_tables=0
    for e in guard['databases']:
        p=R/'prechange-backup'/e['relative']; assert file_hash(p)==e['sha256']; rows(p,e['tables']); fresh_tables+=len(e['tables'])
    preservation={'status':'PASS','baseline_payloads':len(baseline['files']),'baseline_sqlite_restores':sum(x['kind']=='sqlite-online-backup' for x in baseline['files']),'baseline_table_count_comparisons':sum(len(x.get('rows',{})) for x in baseline['files']),'fresh_database_snapshots':len(guard['databases']),'fresh_table_count_comparisons':fresh_tables,'fresh_ordinary_file_backups':fresh_files,'guarded_original_hashes_unchanged':len(guard['files']),'guarded_model_paths':[x['source'] for x in guard['files'] if x['relative'].endswith('.gguf')],'original_credentials_copied_by_refresh':False,'assistant_explicit_auth_file_reads_or_copies':False,'cli_internal_auth_reads':'not traced; only version/help discovery invoked','active_history_usage_frozen':False,'normal_current_session_metadata':'history, usage and task activity may advance through Hermes itself','original_databases_replaced_merged_or_migrated':False,'new_sidecar_initial_counts':demo_counts,'all_test_servers_stopped':http['all_test_owned_servers_closed'],'backup_location':'private_on_device_not_encrypted_not_off_device','checked_at':time.time()}
    save('PRESERVATION_FINAL.json',preservation)
    # Disabled production registration metadata only. No source content or grants are imported.
    proposals=[]
    kinds={'.hermes/state.db':'hermes','.hermes-pocket/chats.sqlite3':'pocket','local-ai/hermes_history.db':'history','local-ai/hermes_knowledge.db':'knowledge','local-ai/memory.db':'memories','local-ai/personal_chat.db':'chat','local-ai/web_conversations.db':'web'}
    for e in guard['databases']:
        if e['relative'] in kinds: proposals.append({'id':kinds[e['relative']],'kind':kinds[e['relative']],'path':e['source'],'enabled':False,'grants':[],'record_selection':None})
    for e in guard['files']:
        rel=e['relative']; kind=None
        if rel in {'.hermes/memories/MEMORY.md','.hermes/memories/USER.md'}: kind='markdown'
        elif rel.startswith('.hermes/digital-twin/') and rel.endswith('.md'): kind='twin'
        elif rel=='.hermes/memory/facts.jsonl': kind='facts'
        if kind: proposals.append({'id':kind+'-'+hashlib.sha256(rel.encode()).hexdigest()[:12],'kind':kind,'path':e['source'],'enabled':False,'grants':[],'record_selection':None})
    save('SOURCE_REGISTRY_PROPOSAL.json',{'enabled':False,'requires_path_specific_user_approval':True,'entries':proposals,'backups_credentials_other_profiles_excluded':True})
    copied=json.loads((R/'pocket-baseline.json').read_text()); originals={x['path']:x for x in copied}; modified=[]; new=[]; unchanged=0; diff=[]
    for p in sorted((R/'pocket').rglob('*')):
        if not p.is_file() or '__pycache__' in p.parts: continue
        rel=str(p.relative_to(R)); sha=file_hash(p)
        if rel in originals:
            if sha==originals[rel]['sha256']: unchanged+=1; continue
            item={'stage_path':rel,'original_live_path':str(Path.home()/'hermes-pocket'/str(p.relative_to(R/'pocket'))),'before_sha256':originals[rel]['sha256'],'after_sha256':sha,'live_file_modified':False}; modified.append(item)
            old=R/'prechange-backup/hermes-pocket'/p.relative_to(R/'pocket')
            diff.extend(difflib.unified_diff(old.read_text().splitlines(True),p.read_text().splitlines(True),fromfile='baseline/'+str(p.relative_to(R/'pocket')),tofile='staged/'+str(p.relative_to(R/'pocket'))))
        else:
            new.append({'stage_path':rel,'sha256':sha,'live_copy_authorized':False})
            diff.extend(difflib.unified_diff([],p.read_text().splitlines(True),fromfile='/dev/null',tofile='staged/'+str(p.relative_to(R/'pocket'))))
    save('CHANGE_LIST.json',{'scope':'private_stage_only','live_changes':[],'modified_copied_pocket_files':modified,'new_pocket_files':new,'unchanged_copied_pocket_files':unchanged,'diff_apply_authorized':False,'other_artifacts':'QA scripts/reports, empty-grant demo sidecar, schema-only fixtures, recovery copies, disabled registry and approval/rollback/runbooks; see FINAL_ARTIFACT_MANIFEST.json'})
    (R/'POCKET_DIFF.patch').write_text(''.join(diff))
    counts=results['counts']; blocked=sum(v for k,v in counts.items() if k.startswith('BLOCKED'))
    lines=['# Phase 1 acceptance results — NOT a production readiness certificate','',f"Original plan entries assessed: {results['entries_assessed']}",f"PASS: {counts.get('PASS',0)}",f"PARTIAL: {counts.get('PARTIAL',0)}",f"BLOCKED / not executed to completion: {blocked}",f"FAIL: {counts.get('FAIL',0)}",'',f"Existing Pocket regression tests: {http['legacy_regression_count']} passed, 0 failures/errors.",f"Additional hardening regressions: {extra_count} passed, 0 failures/errors.",'Authenticated staged HTTP and simulated DOM clicks passed. No claim of actual phone rendering or native picker/share/save testing.','No JCode inference, Qwen model load, weight download, GPU job, training, merge, conversion, live scheduler activation or deployment.','',f"Preservation: {preservation['baseline_payloads']} baseline payload checks; {preservation['baseline_sqlite_restores']} baseline restore drills / {preservation['baseline_table_count_comparisons']} table comparisons; {preservation['fresh_database_snapshots']} refreshed DB snapshots / {preservation['fresh_table_count_comparisons']} table comparisons; {preservation['guarded_original_hashes_unchanged']} original file/model hashes unchanged.",'Active Hermes session history/usage can advance naturally and is not described as frozen.','','## Per-entry evidence','']
    for x in results['results']:
        lines.extend([f"### {x['id']} — {x['status']}",x['assertion'], '',x['evidence'] if isinstance(x['evidence'],str) else json.dumps(x['evidence'],ensure_ascii=False,sort_keys=True),''])
    (R/'ACCEPTANCE_REPORT.md').write_text('\n'.join(lines))
    root_causes={
      'basis':'completed baseline inspection; historical assertions, not a new live service diagnosis',
      'six_hour_job':{'definition':'enabled 0 */6 * * *','scheduler_execution':'last_run_at null / completed 0 at inspection','observed_cause':'no evidenced active gateway cron ticker; CLI/Pocket does not start it','historical_android_kill':'not proven','odd_next_run_at_timezone_cause':'unknown; stale recurring jobs are fast-forwarded by native scheduler','extractor_defects':['hardcoded profile root','shared/stale temporary export reuse','lost source role/session','lowercased candidate text','missing consent review/early failure status'],'fix':'staged profile/project/source candidate queue, no auto promotion; independently approved observable ticker activation later'},
      'curator_429':{'historical_run':'20261023-054129','reported_cause':'requested model temporarily at capacity upstream, explicitly not API-key rate limit','status_bug':'normal failure text copied to llm_final/llm_summary without failed/error/interrupted checks, leaving llm_error null','prior_mutations':'archive/prune activity existed; failure does not prove no mutation','fix':'staged structured failure normalization/Retry-After bounded defer/circuit decisions; native integration/governance require separate patch/approval','automatic_provider_or_credential_change':False}}
    save('ROOT_CAUSES.json',root_causes)
    # Everything here is private; exclude DBs, source-content backups and test pairing values from code inventory.
    artifacts=[]
    for p in sorted(R.rglob('*')):
        if p.is_symlink(): raise RuntimeError('Unexpected stage symlink')
        if p.is_dir(): p.chmod(0o700); continue
        if p.is_file():
            p.chmod(0o600)
            rel=p.relative_to(R)
            if any(x in rel.parts for x in ('prechange-backup','data','never-created','test-runs','test-tmp','__pycache__')) or p.name=='FINAL_ARTIFACT_MANIFEST.json': continue
            artifacts.append({'path':str(rel),'bytes':p.stat().st_size,'sha256':file_hash(p)})
    save('FINAL_ARTIFACT_MANIFEST.json',{'private':True,'not_for_cloud_or_git_upload':True,'files':artifacts,'excludes':'private recovery payloads/sidecar DB/fixtures/test pairing values/runtime caches','code_changes':{'modified':len(modified),'new':len(new),'unchanged':unchanged},'authorization':'no live deployment'})
    print(json.dumps({'entries':64,'counts':counts,'blocked_total':blocked,'legacy_regressions':http['legacy_regression_count'],'additional_regressions':extra_count,'original_hashes_unchanged':len(guard['files']),'modified_staged_files':[x['stage_path'] for x in modified],'new_staged_files':[x['stage_path'] for x in new],'stage':str(R),'live_changes':[]},indent=2))
if __name__=='__main__': main()
