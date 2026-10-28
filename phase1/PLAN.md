# Hermes Evolution Phase 1 — approval proposal

Status: backups and read-only diagnosis complete; application implementation NOT started. No live services/configuration, original skill bodies, original databases or model weights intentionally changed. JCode advisory response NOT obtained: configured Antigravity authentication is unavailable. This plan is Hermes-authored, not a claimed joint review.

## 1. Preservation and current evidence

Workspace: /data/data/com.termux/files/home/hermes-evolution-phase1-20261027-kfRRlK

- preservation/manifest.json: per-file source paths, SHA-256, source permissions, SQLite snapshot row counts, exclusions, UTC timestamps.
- preservation/verification.json: 367 snapshot files, 686019091 payload bytes; 734 checksum/permission assertions passed; 11 database snapshots passed full integrity checks and isolated byte-copy restore drills with every table count checked.
- Includes both Hermes memories/ and memory/, state.db, kanban.db, all skills (including archives/backups), Digital Twin, cron definitions/scripts, private Pocket data/workspaces/signing material, Pocket source/artifacts excluding generated dependency/build trees, all discovered local-ai databases including historical DB backups, and selected local-ai source/docs.
- DBs use sqlite3 online backup from mode=ro connections, not unsafe raw copies of live WAL databases. WAL/SHM/journal companions are represented by the coherent SQLite snapshot rather than copied as independent database files. Each DB snapshot is coherent; the set is NOT one cross-database transaction.
- Original GGUF/model directories, dependencies and generated build caches were excluded, not removed. Originals remain installed. Existing Pocket APK/signing material are preserved for update/rollback.
- Private root/directories are 0700; backup payload files are 0600. Backups can contain sensitive records and private key material: no cloud/JCode/Drive transfer, no Git commit. They are local, not encrypted or an off-device disaster-recovery guarantee. No automatic cleanup/pruning.
- 23 active SKILL.md files reconfirmed. Original bodies remain reference-only.
- A post-snapshot check found no changes in 63 original memory, Digital Twin, cron and Pocket source/artifact files. Live history and agent usage/log telemetry naturally continue as this session operates; no global freeze is claimed.
- Diagnostic evidence is in diagnostic-evidence.json. Original logs and live source files were inspected read-only, not executed as modules.

## 2. Proposed architecture

Pocket UI -> existing loopback authenticated bridge -> project/consent policy broker -> isolated Evolution modules.

Do not import bridge.py in tests: it initializes/migrates live chats at import. Use a copied source tree with HERMES_POCKET_DATA pointing to new fixture data, an unused loopback port and a new token. No feature points at the running bridge during staging.

New sidecar state is an evolution.sqlite3 in the staged data directory; originals receive no schema changes. Proposed tables: projects, source_grants, record_scopes, skill_refs, skill_versions, test_runs, approvals, task_runs, dataset_candidates, dataset_reviews, export_manifests and audit_events. Use transactional migrations, restrictive permissions and explicit schema versioning. These tables store workflow state, not a replacement merged personal-history database.

A private derived search index is optional, rebuildable and project-specific. Start with bounded direct adapter queries; add FTS only if measured latency justifies it. Indexing itself requires a source/project grant. Indexing is not consent for cloud use or training.

### A. Unified read-only retrieval

Sources and adapters:
1. ~/.hermes/memories/{MEMORY,USER}.md: curated sections, file/section citations; not automatically verified facts.
2. ~/.hermes/memory/facts/*.jsonl: unapproved extracted candidates, with unknown speaker if provenance was lost. The separate empty memory/{MEMORY,USER}.md pair is not mistaken for active memory.
3. ~/.hermes/state.db: sessions + messages; retain message ID, session lineage, author role and timestamp; exclude system prompts, reasoning, model_config, credentials and tool payloads by default.
4. ~/.hermes-pocket/chats.sqlite3: chat JSON messages and file metadata; attachments are NOT opened recursively or searched by default. Link to Hermes session only when exact IDs support it; never assume two titles identify the same conversation.
5. local-ai/hermes_history.db history; hermes_knowledge.db knowledge; memory.db memories; personal_chat.db chat; web_conversations.db conversations/messages.
6. ~/.hermes/digital-twin/: explicit document/section grants only. Sensitive business/financial documents default denied.
7. Existing skills: metadata catalog; bodies only on explicit selection. Archived skills are separately labelled, never auto-restored.

Historical backup directories, preservation copies and the Evolution backup tree are excluded from operational retrieval and dataset discovery. Otherwise every backup would reintroduce stale duplicates and private credentials.

Access contract:
- Default deny. The backend derives principal and active project from its authenticated session; a client-supplied project string alone never authorizes access.
- Grant specific source + record/session/document scopes. Unassigned history is quarantined; no keyword-inferred automatic project assignment or default global sharing. A user may explicitly share a skill or record with multiple projects.
- Grants separately specify local retrieval, cloud prompt inclusion, JCode packet inclusion and dataset candidacy. One permission never implies another.
- Filter BEFORE rank, dedup, counts, facets or citations. Avoid leaking unauthorized result existence through counts, errors or dedup metadata.
- Open SQLite mode=ro, query_only=ON, fixed SELECT queries and parameters; never accept SQL/paths from clients, ATTACH originals, VACUUM, checkpoint or migrate original stores. Do not use immutable=1 on a live WAL DB. A ro query can depend on existing WAL/SHM; account for SQLite's reader/sidecar behavior instead of promising zero filesystem activity.
- Bound rows, snippets, query duration, total returned bytes and source errors. Malformed JSON, corrupt/locked DB or missing source produces a labelled partial-result status, not a false no-records answer.
- Canonicalize allowlisted paths and reject symlinks/path traversal; refuse non-allowlisted sources and other Hermes profiles.

Result envelope: opaque source_id, source_kind, source_record_id, session/document locator, timestamp or explicit unknown, author role or unknown, content hash, snapshot/read timestamp, snippet boundaries, project scope, sensitivity, claim type, disputed/unverified status and citations[]. Internal absolute paths stay private behind an authorized source-view endpoint.

Dedup is conservative normalized-exact content hashing (Unicode normalization and whitespace only). Preserve all authorized provenance; do not collapse contradictions, speaker distinctions, dates, negations or differently verified claims into one fact. Near-duplicates are labelled candidates, never silently merged. Prior assistant text remains unverified AI output. Source documents remain untrusted data; retrieved instructions do not grant tools or change system policy. Test the existing reported-claim/dispute attribution defense explicitly, including documents whose dispute clause is outside the first excerpt.

### B. Pocket Teach -> Test -> Approve -> Reuse

Library: show the 23 existing skills, provenance, original content hash, project sharing and Legacy reference status. Importing/cataloging is not approval. Do not copy them into a new unrelated prompt collection or rewrite their original files.

Teach: user chooses a project, selected examples and either a manual draft or an explicitly approved drafting provider. Draft contains trigger, prerequisites, numbered method, required tools, input/output contract, risks, permission boundaries and verification. Teaching does not execute those steps.

Test: explicit Run test button. An unapproved draft may be tested ONLY as a human-authorized synthetic/fixture experiment with tools disabled by default. Any tool-assisted fixture test needs an exact, host-registered action allowlist and approved workspace/resources. No free-form shell, arbitrary network, real financial records or writes to original skill/memory stores. Test reports contain assertions and actual outputs; a model saying PASS is not test evidence.

Approve: separate deliberate user action AFTER reviewing exact content, required capabilities, scope, risks and test results. Store immutable version hash, test-evidence hash, capability manifest, project, approver, time and consent purpose. Server enforces transitions; draft/test output cannot self-approve. Changes to body, capabilities, linked executable templates or scope invalidate approval. Include stale-file hash checks for externally edited legacy skills.

Reuse: only an approved exact version, explicitly selected for the active task/project, may be attached as task guidance. It never expands permissions or causes automatic execution. Commands/actions still require their normal approvals. Show loaded skill/version in chat. Failed, expired, revoked or edited versions are blocked. Roll back by selecting an earlier still-approved immutable version, not overwriting history.

Reference/approval/activation states: legacy_reference -> draft -> tested -> approved -> user_selected; rejected, revoked, superseded and archived are explicit states. A failed or edited tested version returns to draft. No automated promotion, curator merge, memory promotion or test execution.

Integrate through existing Hermes skill formats and explicit contextual loading, while removing skill_manage/memory-write/arbitrary-shell capabilities from workbench draft/test agents. Existing Pocket ignore_rules=True/private-memory opt-out stays intact. Reuse the existing file picker/previews/outputs UI for examples, evidence and export review. Add visible Teach, Test, Approve, version history, source scope and Reuse controls; no terminal/file-path workaround is the end-user workflow.

### C. Bounded JCode task interface

Allowed task kinds: plan, review and propose_patch. Model output is advisory data; no automatic shell or patch application. Host applies a reviewed diff only after separate authorization, path allowlist and before/after hash checks.

Per-task packet: opaque task ID, explicit project, selected sanitized specification/fixtures or allowlisted code, requested output schema, approved provider, time/output budgets and expected checks. Never send credentials, auth/config stores, backups, real database rows or private documents by default. A process uses its own JCode auth; it never borrows Hermes tokens.

Use installed v0.99.1 help-verified one-shot run, no update/selfdev, tool-profile none and disable-base-tools. Supported child-local environment overrides disable memory, memory sidecar, persisted memory injection, swarm, auto-poke, hooks and cross-provider/account failover; scrub inherited secret environment variables. Empty scratch cwd, no global/project prompts, MCP configs or user skill metadata may be auto-attached. Revalidate these preconditions for EVERY task. If exposure cannot be eliminated, fail closed.

Parent watchdog: 90 seconds wall, 60 CPU seconds, low priority, bounded stdout/stderr, JSON schema validation and process-group cleanup. Do not use a small absolute RLIMIT_FSIZE against existing JCode session WAL/logs: a first harness attempt was killed with SIGXFSZ (-25). The corrected harness bounds task output instead; it then returned the real missing-auth error. Keep both attempt logs as evidence.

Log request hash, approved provider/model metadata if available, result hash, timing, exit reason and policy decisions; redact output before normal UI/audit display. Private raw diagnostics are not a training dataset. Never fallback to minimal/full tools or another provider silently. Repeated failures stop, not retry indefinitely.

Tools-disabled is an application boundary, NOT a same-UID OS security sandbox: a native JCode process can still access its own storage and perform native startup/logging. A stronger adversarial filesystem/credential boundary requires a dedicated OS identity/container/remote worker and separately approved deployment. Do not claim cwd isolation alone is a sandbox.

Current coordination outcome: jcode-review/ first attempt SIGXFSZ; jcode-review-retry/ corrected attempt exit 1: No Antigravity tokens found. Both verified JCode config unchanged. Current auth status has no Antigravity/OpenAI OAuth configured; existing OpenRouter key presence is NOT validated inference. No provider switch or credential copying was done. Options: user privately reauthenticates Antigravity, or explicitly authorizes a single bounded OpenRouter review with possible charges. Do not claim JCode-reviewed design until a response is parsed and checked.

### D. Consent-reviewed dataset pipeline

Selection -> provenance/success check -> minimization/redaction -> user preview/edit -> per-record consent -> split/dedup -> JSONL export -> final scan + manifest. All real records default denied. Blank/synthetic fixtures only during development; backups are never a candidate source.

Require observable successful task/test evidence plus a user-selected interaction, or a linked correction pair with the corrected answer explicitly accepted. Prior assistant claims of success are insufficient. Remove system prompts, chain-of-thought/reasoning, auth tokens, tool-secret traces and unrelated turns. Treat documents/attachments as excluded unless approved specifically.

Block secrets/private keys even when found in otherwise approved records; request repair/redaction rather than exporting them. Personal identifiers and sensitive documents require explicit record/field/purpose-specific approval; otherwise redact or exclude them. Regex scanning alone cannot guarantee PII removal: add structural detectors, user review and adversarial fixtures. Preserve role/dispute distinctions; do not train contested claims as facts. Scope and consent for cloud retrieval do not authorize training.

JSONL training rows: messages only, valid user/assistant roles and bounded content. Keep provenance, row hash, original selection ID, approved redacted-content hash, approver/time/purpose/expiry, sensitivity decisions, success evidence and license in a private sidecar manifest, not in the text sent to training. Record edits invalidate consent. Group exact/near duplicates, related sessions and correction families before train/validation/test splitting to prevent leakage. Revocation removes unexported/rebuild candidates and invalidates future exports; previously trained adapters must be marked affected and withdrawn/retrained, not claimed magically untrained.

Export through visible preview/download controls after a final explicit confirmation. No actual personal dataset is exported during this planning step. The staged dataset/training files are specifications, not a working or approved export pipeline.

### E. Isolated Qwen verification (after approval)

Only ~/local-ai/models/qwen.gguf (986048768 bytes) may be selected; never discover/load the 9B model. Validate SHA-256 and GGUF metadata against the original filename/model evidence before inference. Check actual MemAvailable, thermal/battery telemetry if accessible and other running workloads; never stop an existing service to make room.

Proposed budget: require at least 2560 MiB available memory, reserve 1024 MiB for Android/foreground use, two generation AND prompt threads, context 512, batch 64, microbatch 32, at most 32 generated tokens, low priority, CPU 120 seconds, wall 120 seconds, measured RSS ceiling 1600 MiB plus ongoing available-memory watchdog; abort if available RAM drops below 768 MiB. No swap reconfiguration, huge pages, GPU offload, network downloads or persistent model server. Android memory/thermal availability is variable: skipped/aborted is a legitimate result, not a reason to load at any cost.

Installed llama-cli help confirms --offline, --single-turn, --no-display-prompt and --no-warmup. Validate the final argument combination/chat template in staging. Use CLI with exact approved -m path, --offline, finite context/output and synthetic prompts. No HTTP service/port or Pocket provider change needed. Scrub model/provider URL variables, close stdin, monitor the owned process group, preserve the original file hash and clean up only test-owned processes.

Separate results for load, actual generation, exact synthetic instruction following, attribution fixtures, latency/RSS and shutdown. Passing a tiny reply is not validated tool use or reliable autonomous skills. Inference remains NOT RUN in this planning step. The earlier available-memory snapshot was below the proposed start threshold, so recheck immediately before any approved run.

### F. Optional GPU LoRA preparation (no execution/download)

Prepare a disabled GPU-only recipe, schema and runbook AFTER approval for staged implementation. Source model must be the original full-precision model matching the existing Qwen2.5-1.5B-Instruct derivative, tokenizer/vocabulary and chat template; proposed family Qwen/Qwen2.5-1.5B-Instruct, exact revision/license/metadata to be verified before any download. Do not try to train from the Q4 GGUF or substitute plain base Qwen2.5-1.5B silently. A different base is a separate evaluation branch requiring approval.

GPU runtime selection, provider/account/location, budget and data handling require separate consent. Then lock compatible CUDA/PyTorch/Transformers/PEFT/trainer versions for that host; do not invent an already-tested dependency lock. Start with a deterministic tiny synthetic smoke run, then an explicitly approved consent-manifest dataset. Example initial proposal only: LoRA r=8, alpha=16, dropout=0.05, sequence 512 and one seed-controlled short epoch; actual targets/hyperparameters/resource estimates require validation against the selected model/host.

Version each run with base revision/hash, tokenizer/template hash, dataset/split/consent hashes, recipe/dependency versions, seed, adapter weights and evaluation results. Use assistant-only loss masking and validate it. Hold out instruction-following, source attribution, corrections, project isolation/refusal, secret-canary leakage, tool-call formatting and baseline general-quality tests. Base vs adapter comparison uses identical prompts/seeds/resource budgets; block promotion on any privacy/security regression or a failed threshold declared BEFORE training.

Export in a new version directory: retain adapter-only safetensors + manifest; merge a copy with matching original full-precision weights; validate generation; convert the merged HF copy to F16 GGUF with a compatible pinned llama.cpp converter, then quantize a separate Q4_K_M file. Validate tokenizer/chat template, load/generation and held-out answers after conversion/quantization. GGUF conversion/export is a tested gate, not assumed from binary presence. Never overwrite qwen.gguf.

Human approval is required to select any new model version for serving. Keep the original GGUF and old served-model selection for rollback. If anything fails, leave the original selection unchanged. Training, weights downloads, GPU creation/billing and deployment are OFF by default and are NOT requested by the initial implementation approval.

## 3. Root causes and proposed repairs (not applied)

Memory schedule:
- cron/jobs.json has an enabled script-only job, schedule 0 */6 * * *, script auto_memory.py, last_run_at=null, completed=0 and an overdue next_run_at. Extractor last_run.json records 2026-10-18 18:07:28, which proves a script run but not scheduler execution.
- No Hermes gateway/crond was detected in the process inspection. Installed gateway/run.py owns _start_cron_ticker (line 18275); installed CLI/Pocket do not start it. An enabled JSON job is not a running scheduler. Observed operational cause: no evidenced active ticker; historical Android kill/reboot history is NOT proven.
- cron/jobs.py lines 1062-1085 deliberately fast-forwards stale recurring jobs. Starting a scheduler now is not proof it immediately executes missed extractions. The source of the unusual stored next_run_at is unknown; do not guess it is a timezone bug.
- Script defects independent of scheduling: hard-coded ~/.hermes (ignores active profile), shared temporary export with 48-hour reuse, lost role/session provenance, lowercased fact text, no consent/sensitivity review, no durable failure status for early return. Isolated pure-function AST test reproduced identical extraction from an assistant-only and user-only synthetic statement.
- Do NOT simply restart this extractor. Proposed fix: approved, locked, idempotent script-only candidate queue; source message IDs/roles + time watermark; profile-aware paths; no assistant-to-user fact conversion; retain original case; 0600 per-run temporaries; atomic success/failure status; review before memory promotion; no scheduled LLM calls. Then separately choose an Android-appropriate persistent ticker/service and verify actual execution and restart behavior under sleep/reboot constraints. Battery exemptions/wake locks/boot changes require explicit consent.

Curator:
- ~/.hermes/logs/curator/20261023-054129/run.json records HTTP 429 after three retries: requested model temporarily at capacity upstream, explicitly not the API key's rate limit. This establishes reported upstream capacity exhaustion, not its internal infrastructure cause and not a current outage. No new live curator run was triggered.
- run.json stores that failure as llm_final/llm_summary while llm_error=null. Installed agent/curator.py lines 1739-1745 copies final_response without checking failed/error/interrupted flags; lines 1766-1768 set error only for an exception. This explains misleading status when failure is returned as normal text. Historical run had archive/prune tool activity, so a final failure does NOT imply no earlier changes; do not auto-restore/re-run it.
- Proposed fix: structured failure propagation (failed/error/interrupted/partial, HTTP/retry metadata), Retry-After-aware bounded exponential backoff with jitter, circuit breaker and visible deferred status. No aggressive repeated retry, automatic new paid provider, or credential rotation. Keep maintenance proposals in the workbench review queue; block autonomous activation/consolidation of unapproved versions. Native curator changes belong in a reviewed version-controlled patch, not ad hoc edits inside installed site-packages.
- Existing enabled native curator is outside new workbench approvals. Before production rollout, explicitly decide whether to pause its automatic mutations or enforce shared governance. Leaving it active is a disclosed pre-existing risk; changing it needs approval. Workbench cannot honestly guarantee system-wide human-only promotion while another process can rewrite skills.

## 4. Implementation order and acceptance gates

Gate A — approval now: implement ONLY in a copied staged Pocket tree and new private Evolution data directory. Use synthetic fixtures and separately approved snapshot records for adapter checks; no automatic import/cloud sharing of preserved personal history. Build retrieval adapters/policy, sidecar state, workbench UI/state machine, bounded JCode broker with deterministic mock tests, dataset validation/consent/export machinery on synthetic data and disabled GPU recipe/runbook. Keep originals/live bridge/APK/config/cron/curator unchanged. No package installs or updates without a reviewed dependency need. No commits/pushes/uploads.

Order: A1 policy/data contracts and 23-skill reference catalog; A2 read-only adapters + attribution/dedup; A3 skill lifecycle/API/UI and fixture test runner; A4 bounded JCode broker; A5 consent dataset pipeline; A6 disabled LoRA/version/export/rollback scaffolding; A7 complete negative/regression test matrix and isolated UI/API checks. QA before moving to the next dependency milestone; source-backed claims only.

Gate B — separate optional approval: one resource-capped local Qwen inference test; skip if preflight fails. No live provider/service change. JCode real review requires either private Antigravity login or explicit authorization to use existing JCode OpenRouter credentials/provider with possible charges; until then mock/interface tests are not real JCode inference proof.

Gate C — separate deployment approval AFTER seeing staged results and exact diff: refresh/verify backups, review every live path/service/config delta, select project source grants, decide cron/curator governance and recovery steps, approve explicit cutover. Deploy via reversible feature selection on the loopback bridge. Update Pocket over the installed app with the same signing identity; never uninstall. Verify paired auth, chat continuation, files/attachments and skill/source controls on device. A tested APK/build is not proof of install/UI behavior.

Gate D — separate future permissions: any personal dataset export/cloud upload, GPU account/spend, base weights download, training, adapter/model promotion or deployment. Each needs explicit scope/content/budget approval; Gate A/B/C does not grant it.

Rollback: stop only Evolution-owned test processes; discard/reselect derived indexes/sidecar version, restore old code/config selection only after approval, keep every version and original model. Never copy an old history DB over a live one with newer messages; reconcile lost/added records with the user first. Migration rollback must preserve new sidecar audit/approval records too. The verified restore drill happened in isolation, not against live data.

## 5. Test plan and present limits

TEST_PLAN.json lists the planned acceptance/negative checks and their status as NOT RUN. Tests must exercise real policies, stores and outputs, not only mocks or an AI's explanation. Report unit/API/UI, actual model response, actual scheduler execution, APK build/install and GPU training as separate outcomes.

Current verified work: backup/hash/permission/SQLite integrity/restore checks; schema discovery; source-preservation check; extractor defect reproduction; installed JCode/llama CLI flags; bounded JCode failure logging and config preservation. New retrieval/workbench/dataset pipelines, inference and training have NOT passed or even run. No personal JSONL training dataset has been created.
