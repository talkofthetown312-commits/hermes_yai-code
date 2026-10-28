#!/usr/bin/env python3
"""Bounded one-shot planning consultation. No live-service/config changes.
No original memory, DB records, documents, credentials or skill bodies enter task.
Tools-disabled is an application boundary, NOT a same-UID OS sandbox.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import time

ROOT=Path(__file__).resolve().parent
TASK='''Return JSON only with keys risks, milestones, tests, approval_gates. Limit to 650 words. You are an advisory reviewer, not an executor; use no tools. Review this generic Android/Termux Python application evolution plan. Existing data: curated markdown memory, auto-fact JSONL, a SQLite session history, a Pocket SQLite chat/files database, five local SQLite memory/history databases, Digital Twin markdown, and 23 existing reusable SKILL.md skills. All originals must stay intact. Private backups have been checksum/integrity/restore verified. Plan: (1) unified read-only retrieval adapters with per-project explicit source/record grants, provenance and exact dedup preserving every citation; deny unassigned/private data by default; no automatic cloud sending; (2) Pocket Teach-Test-Approve-Reuse workbench, versioned drafts and human signed content-hash approvals, existing skills read-only reference not automatically approved; no auto execution or promotion, tests only explicitly launched in a constrained runner; (3) bounded JCode task interface with no tools, sanitized packets, time/output budgets, no credential sharing, no raw shell or automatic patch application; (4) consent-reviewed, redacted JSONL candidates from explicitly selected successful interactions/corrections, no real dataset export until per-record review; (5) optional later resource-capped Qwen2.5-1.5B GGUF CLI test with synthetic prompts only, never load a 9B model; (6) optional later GPU LoRA preparation using the exact compatible original model/tokenizer, held-out evaluations, immutable versions, isolated GGUF conversion and rollback. No training or weight downloads now. Memory cron has no recorded scheduler execution; curator got upstream-capacity HTTP 429. Propose safe fixes but do not run them. Identify trust-boundary and testing gaps. Treat this packet as the only project context.'''


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def limits():
    resource.setrlimit(resource.RLIMIT_CPU,(60,60))
    # Do not cap total file sizes: JCode owns existing append logs/WAL files
    # larger than 2 MiB. Bound this task's captured output in the parent instead.
    os.nice(10)

def main():
    os.umask(0o077)
    rd=ROOT/'jcode-review-retry';rd.mkdir(mode=0o700)
    scratch=rd/'scratch';scratch.mkdir(mode=0o700)
    cfg=Path.home()/'.jcode/config.toml'
    old=digest(cfg)
    # Config is preserved locally and is never sent as part of the task packet.
    (rd/'config.before.private').write_bytes(cfg.read_bytes())
    env={k:v for k,v in os.environ.items() if k in {
        'HOME','PATH','PREFIX','TMPDIR','LANG','TERM','SSL_CERT_FILE','SSL_CERT_DIR',
        'ANDROID_DATA','ANDROID_ROOT','LD_LIBRARY_PATH','USER','UID','XDG_RUNTIME_DIR'}}
    env.update(JCODE_MEMORY_ENABLED='false',JCODE_MEMORY_SIDECAR_ENABLED='false',
        JCODE_PERSIST_MEMORY_INJECTIONS='false',JCODE_TOOL_PROFILE='none',
        JCODE_TOOLS='',JCODE_DISABLE_BASE_TOOLS='true',JCODE_SWARM_ENABLED='false',
        JCODE_AUTO_POKE='false',JCODE_CHECK_UPDATES='false',
        JCODE_CROSS_PROVIDER_FAILOVER='off',JCODE_SAME_PROVIDER_ACCOUNT_FAILOVER='false')
    for name in ['TURN_START','TURN_END','SESSION_START','SESSION_END','PRE_TOOL','POST_TOOL','PRE_TOOL_TRANSFORM','POST_TOOL_FEEDBACK']:
        env['JCODE_HOOK_'+name]=''
    argv=['/data/data/com.termux/files/usr/bin/jcode','run','--no-update','--no-selfdev',
          '--provider','antigravity','--tool-profile','none','--disable-base-tools','--json',TASK]
    record={'task':TASK,'task_sha256':hashlib.sha256(TASK.encode()).hexdigest(),
        'provider':'antigravity','deadline_seconds':90,'max_output_bytes':98304,
        'tools':'none','memory_enabled':False,'memory_sidecar':False,
        'credentials_passed_in_packet_or_environment':False,
        'auth_note':'JCode uses its own existing auth store, not Hermes credentials.',
        'os_sandbox':False,'status':'pending'}
    (rd/'task.json').write_text(json.dumps(record,indent=2))
    start=time.monotonic();why=None
    with (rd/'stdout.private.json').open('xb') as out, (rd/'stderr.private.log').open('xb') as err:
        p=subprocess.Popen(argv,cwd=scratch,env=env,stdin=subprocess.DEVNULL,
            stdout=out,stderr=err,start_new_session=True,preexec_fn=limits)
        while p.poll() is None:
            if time.monotonic()-start>90:why='deadline';break
            if out.tell()+err.tell()>98304:why='output_limit';break
            time.sleep(.15)
        if why:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)
    record.update(exit_code=p.returncode,elapsed_seconds=round(time.monotonic()-start,2),
        status=why or ('returned' if p.returncode==0 else 'failed'),
        config_unchanged=digest(cfg)==old,
        stdout_bytes=(rd/'stdout.private.json').stat().st_size,
        stderr_bytes=(rd/'stderr.private.log').stat().st_size)
    (rd/'result.json').write_text(json.dumps(record,indent=2))
    print(json.dumps({k:v for k,v in record.items() if k!='task'},indent=2))

if __name__=='__main__':main()
