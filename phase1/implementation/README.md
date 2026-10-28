# Hermes Evolution Phase 1 — isolated implementation

This directory is private staging, not the installed app or a ready production release.

## Implemented
- `pocket/evolution.py`: default-deny record/project/purpose grants; read-only SQLite and text/JSONL adapters; citations, conservative exact deduplication, disputed/reported/prior-AI labels; sidecar skill/consent/audit workflow. Text-source revisions invalidate persisted grants across restarts. Guidance reuse includes Hermes-compatible SKILL.md text, never installation or additional tools.
- `pocket/evolution_maintenance.py`: profile/project/source-aware candidate extraction, user-role preservation, explicit candidate review (never live promotion), locking/idempotence/watermarks/atomic status; scheduler health interpretation; curator structured failure normalization and bounded Retry-After/circuit decisions, not autonomous retries.
- `pocket/evolution_workers.py`: disabled real JCode broker; strict bounded synthetic packet schema; private hash-only logs; output schema checks; synthetic process-group watchdog tests. CLI v0.99.1 flags verified. No credentials read/copied, no paid provider and no JCode inference run.
- `pocket/evolution_models.py`: existing 1.5B GGUF metadata/hash validation; disabled-by-approval offline CLI probe with 2 threads, finite context/output, CPU/wall/RSS/available-memory limits; disabled LoRA recipe validation and new-version-only paths. No model was loaded.
- `pocket/evolution_fixtures.py`, `schema-fixtures.json`: seven exact table definitions captured from verified baseline snapshots, populated ONLY with synthetic rows, plus synthetic Markdown/Digital Twin/facts fixtures. No original database rows are imported into the demo.
- `pocket/evolution_api.py`, `pocket/web/evolution.{js,css}`: authenticated staged Pocket workbench and visible Teach, Test, Approve, Reuse, history/restore, source grants, candidate review and synthetic dataset preview/review/revoke/save controls.

The 23 existing skills are host-registered references with pinned hashes, NOT automatically approved. New drafts retain the required skill sections and render into SKILL.md format; they stay in the separate sidecar. Reuse returns a version-bound guidance bundle, not an autonomous task or a native skill install. Static contract tests are real deterministic assertions but do NOT prove model behavior. No draft/test model or tool agent is launched.

## Data and trust boundaries
New staging data is under `data/`; disposable test state is under `test-runs/` and `test-tmp/`. No live data-directory or port fallback is permitted. The copied `start.py` refuses to start legacy services. The staged bridge uses an ephemeral test port and stage-owned data; its ordinary chat agent remains unavailable outside explicitly injected test fixtures. No daemon, cron job, model server or Android app update is installed.

All original source stores remain separate. There is no merged personal-history database. Original private stores are NOT active registry entries in this staged UI. The future registry proposal is disabled and all grants are empty. Snapshot freshness, exact-record source selection and a deployment-specific adapter registration remain approval gates.

Synthetic dataset selection requires stored observable success evidence bound to the selected messages, then minimization, final-row preview, explicit project/purpose/expiry/hash-bound consent and final export confirmation. Changes remove consent AND require new host-verified success evidence; arbitrary edited targets cannot be reapproved as successful through a client `success=true` field. Known secrets and one-level base64/hex canaries are blocked; common labelled PII is redacted. Semantic PII detection is incomplete: manual review and sensitive-document exclusion remain mandatory. Exported JSONL has messages only; identifying provenance stays in the private manifest. Revocation invalidates future eligibility and local export manifests, not files someone already downloaded.

## Verification
`ACCEPTANCE_RESULTS.json` preserves each of the original 64 entries and actual evidence/status. `ACCEPTANCE_REPORT.md` summarizes them. Gated tests are not mock passes. `HTTP_QA.json` and `UI_QA.json` cover actual isolated HTTP checks and simulated DOM clicks. Android phone rendering, the native document picker/share/save, and an installed Evolution APK are NOT tested. Existing chat/files/adapter regression tests run only against stage-owned fake-agent fixtures.

`PRESERVATION_FINAL.json` verifies the baseline and fresh snapshots and compares guarded original files/models. Active Hermes history/usage naturally changes because this session is running; it is not described as frozen or restored. Backups are private on-device, not encrypted or off-device disaster recovery. No existing credentials were duplicated into the refresh backup.

## Safe reproduction
These commands start and stop only test-owned, ephemeral localhost servers and synthetic workers:

    python run_acceptance.py
    python test_edges.py

Do not run inherited deployment instructions, copy a test pairing token into the installed app, run the Qwen worker, reauthenticate JCode on the assistant's behalf, schedule maintenance, install skills, download weights or start training. Read SECOND_APPROVAL.md and ROLLBACK.md first. No deployment command is included because this is a staging release, not a reviewed live-cutover package.
