# Rollback / preservation runbook — review only, no cutover executed

## Current staged state
There is no live rollback to perform: original installations/services/data were not modified. All HTTP servers and synthetic worker processes started by tests are closed/reaped by their harness. Keep the staged source, source hashes, recovery snapshots and reports for review. Deleting this private artifact tree is unnecessary and would destroy evidence/backups; no deletion command is supplied.

## Recovery evidence already available
- Original phase-one `../preservation/manifest.json` and `../preservation/payload/`: byte hashes/permissions verified; eleven SQLite online-backup restore drills with table-count comparisons, including committed WAL fixture coverage.
- `prechange-backup/` plus `prechange-manifest.json`: refreshed active database snapshots, selected source/configuration/memory/skill/Digital Twin files. Credentials/signing/auth stores were deliberately NOT duplicated into this refresh; prior originals/baseline remain private and untouched.
- `prechange-manifest.json`: pre-implementation hashes for guarded original source/configuration/memory/skills and existing model bytes. State/usage DBs actively appended by this session are not represented as frozen hashes.
- `PRESERVATION_FINAL.json`: final verification with exact counts, exclusions and any discrepancies. Backups are private on this same device, not encrypted/off-device disaster recovery.

## Triggers for any future approved cutover rollback
Authentication/origin checks regress; existing chat/attachment continuation fails; original storage path is unexpectedly written/migrated; source or project isolation leaks; stale/edited/unapproved guidance activates; consent or secret checks fail; provider fallback/model load/training occurs without approval; new bridge fails readiness; unexplained curator mutations appear. Stop ONLY the newly approved feature/service path; do not kill unrelated processes.

## Before an approved cutover
1. Refresh the scoped recovery baseline after checking disk/resource headroom. Online-backup each active SQLite DB using committed-WAL-aware backup, not a raw DB-only copy. Verify integrity and row counts on an isolated restore; hash and permission-check payloads.
2. Record exact old/new source/config hashes, dedicated bridge PID/start identity, data directory, feature selection and installed APK package/version/signing identity. If any expected hash or identity changed, abort and reconcile instead of overwriting.
3. Back up the NEW Evolution sidecar separately and retain its audit/approval/consent/version high-watermarks. Version every deployed release and schema. Do not include credential values in the runbook/logs or public artifacts.

## Code/feature rollback after a future approved rollout
1. Disable only the explicitly approved new feature selector or stop its dedicated service; leave original source databases/models and unrelated daemons untouched. Verify process ownership/start identity before any termination.
2. Restore/select the exact pre-cutover code/configuration version using its manifest, then restart ONLY the approved Pocket bridge and authenticate readiness without logging pairing credentials. Do not uninstall Android Pocket; if an APK rollback/update is required, use the verified same package/signing identity and supported install-over behavior. Stop if Android refuses a version rollback; never uninstall to bypass it.
3. Run baseline paired auth/origin/host, chat continuation, local-vs-cloud routing, attachments/picker/share/save and file ownership tests on-device. Verify original database/model integrity and the chosen model/service endpoint. Do not infer success from a process merely existing.
4. Keep all sidecar DB files and any intervening review/audit/consent changes. Code rollback does NOT mean restoring an older sidecar snapshot over newer records. If the old release cannot read the current sidecar schema, disable the feature and retain the newer sidecar pending a reviewed read-only adapter/migration. Never silently delete or downgrade it.

## Skill/consent logical rollback (tested in staging)
- Skill restore creates a NEW unapproved revision from the historical body, retains prior immutable version/approval records and requires testing + explicit approval again. It does not resurrect revoked approval or rewrite history.
- Content/capability/format/source changes invalidate selection. Reuse remains exact-version/hash/project/task-bound with no extra tools.
- Dataset edits invalidate consent AND observed-success evidence; new matching host-verified evidence is required before fresh consent/export. Revoke to exclude future exports/builds and invalidate local manifests. Already downloaded/exported files cannot be recalled by a local flag; record external copies and re-review any downstream training versions before future use.

## Database recovery only for demonstrated corruption/loss
Do not replace active Hermes/Pocket/local-ai databases as an ordinary code rollback. If genuine corruption is independently established: stop only the writer(s) under separate approval, make a forensic committed-WAL-aware copy, reconcile newer committed data/audit watermarks, test a candidate restore in isolation, compare counts/expected sessions, then request a path-specific replacement approval. Retain both versions. The current implementation has not performed a live restore.

## Maintenance/model rollback boundaries
No ticker or native curator patch was deployed, so there is nothing to disable now. Any future maintenance change gets its own manifest and reversal, preserves candidate/status/curator evidence and must not restart the old provenance-losing extractor. No model was loaded/promoted/trained; existing served selections remain unchanged and the original Qwen GGUF bytes are preserved. A future adapter promotion needs independent original-selection rollback and paired generation checks as described in GPU_LORA_RUNBOOK.md.
