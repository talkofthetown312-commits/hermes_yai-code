# Architecture and boundaries

## Data flow
Browser/Android WebView -> loopback HTTP bridge -> authenticated Evolution API ->
project-bound library services -> separate synthetic sidecar + registered read-only
source adapters. No original personal stores are registered by the shipped preview.

### Modules present in BOTH phases
- evolution.py: Session/Store/Source/Retrieval/Workbench/Dataset. SQLite sidecar,
  exact-record grants, provenance citations, conservative deduplication, skill
  revisions/test/approval/reuse and exact-row dataset consent/revocation/export.
- evolution_api.py: paired-owner server-derived project/session, strict operation
  field allowlists, synthetic fixture registry, state/history/review endpoints.
- evolution_fixtures.py: schema-driven SQL DDL and hard-coded synthetic rows;
  generated fixture stores, synthetic Markdown/facts and registered source list.
- evolution_maintenance.py: locked/idempotent candidate extraction, role/provenance,
  review-only promotion, watermarks/status, scheduler diagnostics, structured
  upstream errors and bounded retry decisions without autonomous retries.
- evolution_workers.py: synthetic bounded worker/process-group watchdog utilities;
  disabled JCode broker, strict packet/output checks and environment minimization.
- evolution_models.py: GGUF metadata validation/probe gates and disabled LoRA
  recipe/path validation; no model/trainer weights or running workers included.
- bridge.py, hermes_adapter.py, pocket_files.py, start.py: inherited Pocket bridge,
  optional installed-SDK adapter, selected-file handling and disabled staged
  legacy startup. Real inference is NOT used by the preview/test helpers.
- web/app.js, index.html, style.css, evolution.js, evolution.css: Pocket shell,
  visible teach/test/approve/reuse, grants/citations, candidate review, diagnostic
  health, dataset review/consent/save/share. Phase 2 adds staging-only labeling,
  paired read-only auto-open and synthetic fixture download/picker affordances.

### Native source
Phase 1 contains Android MainActivity/ExportProvider Java, manifest/resources and
Gradle source. Phase 2 copied no native project; the existing APK was NOT updated.
No APK, signing key, keystore, signing properties or installed-app state is present.
Android build/signing utilities are source references, not permission to run them.

## Runtime boundaries
Server data and HERMES_BIN must resolve inside the isolated implementation tree;
production port 8766 is forbidden by bridge guards. The new handoff development
helper additionally refuses existing preview port 8877. It uses a clean environment
and no-agent status; chat/uploads are blocked and local model discovery is disabled.
This is same-UID application isolation, not a kernel sandbox against malicious code.

## Trust and consent
- Server determines identity/project; clients cannot override scope.
- Read-only registered sources; never a merged private-history database.
- Grants bind exact record IDs, project, purpose and source revision.
- Citations keep source/record/session/role/time/content hash/locator.
- Assistant text remains unverified; dispute qualifiers are retained.
- Skill approval binds content revision/hash and static test evidence.
- Final dataset export recomputes stored hashes; edits revoke consent/evidence.
- Revocation stops future reuse/export; already downloaded/shared files cannot
  be recalled. Semantic PII detection still requires manual review.

## Non-implemented/gated areas
No live memory import, native skill install, genuine scheduler monitor, enabled
JCode worker/free-only fallback, trained adapter, actual model evaluation or live
production migration is established. Templates describe requirements, not success.
