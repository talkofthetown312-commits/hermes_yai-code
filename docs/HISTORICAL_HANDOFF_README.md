# Repaired portability handoff

Read PORTABILITY_REPAIR.md first. Current repaired verification is in
REPAIR_TEST_RESULTS.json. Use `python -B tools/run_complete_portable_tests.py`
in a fresh extraction. The remainder is the original historical handoff README;
its byte-preservation and old test-count claims do not describe this repair.
No production cutover is authorized.

---

# Hermes Evolution — SOURCE-ONLY engineering handoff

Start here, then read CHATGPT_HANDOFF.md and docs/ARCHITECTURE.md.

This bundle contains BOTH the isolated Phase 1 implementation and Phase 2 phone
staging source. It is not a production release, an installed APK, a model, a backup,
or a training dataset. The original production application was not deployed,
restarted or replaced during packaging. Existing phone staging must remain running.
No authorization to train, activate autonomous skills, enable JCode, change models,
import private memory or cut over production is conveyed by this archive.

## Layout
- phase1/PLAN.md, TEST_PLAN.json, GPU_LORA_PLAN.json: original design and gates.
- phase1/implementation/pocket/: Python core/bridge, web UI, regression tests,
  Android Java/XML/Gradle source and source-only Android build/signing utilities.
- phase1/implementation/: original 64-entry acceptance runner, tests, change list,
  architecture/readiness/rollback documentation and historical acceptance evidence.
- phase2/: final phone staging Python/web source, isolated server/open/stop helpers,
  fixtures, feature tests, simulated DOM/export tests, final logs and phone report.
- templates/: DISABLED memory integration, proposed OpenRouter free-only policy,
  Qwen LoRA preparation. They contain no credentials or personal data.
- tools/: newly supplied portable synthetic bootstrap/test/development helpers.
- SOURCE_INVENTORY.json: original relative provenance and hashes for copied files.
- SANITIZATION_AND_OMISSIONS.json: exact packaging adaptations and exclusions.
- MANIFEST.sha256.json, SECURITY_SCAN_REPORT.json and HANDOFF_VERIFICATION.json:
  archive content hashes and packaging/test verification, not deployment approval.

## Safe reproduction (NEW extracted working copy only)
Use Python 3.10+ on a POSIX host with fcntl/resource and Node with fetch/Blob/File.
No pip/npm install is necessary for offline core tests. See DEPENDENCIES.json;
there was no original Python/Node dependency lockfile to export or invent.

    python3 tools/run_portable_tests.py

This generates synthetic-only catalogs and temporary stores INSIDE the extracted
working copy. It reuses an explicitly selected subset of original acceptance
functions, excludes private/model/live-provider evidence, runs edge regressions,
both phases' offline bridge/files/adapter tests and mocked export checks.
It does not reproduce the full original 64-entry acceptance run.
Never run this against the original phone staging directory.

To develop a NEW synthetic preview, on a separate loopback port:

    python3 tools/serve_synthetic.py --port 18877

The helper refuses ports 8766 and 8877, clears inherited credentials and uses new
handoff-owned data/HOME. Ctrl-C stops only that foreground process. It is not an
OS security sandbox. The archived phone banner/report may still refer to 8877;
18877 is this newly launched development server's actual port. The original
phase2/serve_preview.py and stop_preview.py are preserved as historical staging
source; do NOT use them to control the still-running original phone preview.

## Evidence limitations
Historical Phase 1: 64 entries, 51 PASS, 4 PARTIAL and 9 approval/auth/training gates.
Historical Phase 2: 25 regressions; 76 feature/security checks; 57 simulated-DOM
assertions using 46 real authenticated localhost calls; 9 mocked export checks;
4 additional dataset edit checks; staging-only restart persistence passed.
These are historical counts, not a claim that packaging reran every test.
Read HANDOFF_VERIFICATION.json for tests actually rerun on extracted archive bytes.
Android rendering, touch, native picker/share/save and sleep/resume remain MANUAL.
A successful Android URL dispatch is not a rendering pass.

## Privacy and portability
All existing database files (even synthetic runtime databases), conversation stores,
private snapshots, original skill catalog, credentials, signing material, .env,
model weights, artifacts and caches are excluded. Fixture code and schema-only DDL
regenerate synthetic stores. All copied source/report files are byte-preserved;
only catalog/registry replacements and NEW handoff files differ (see inventory).
Catalog placeholders are empty until bootstrap; Phase 1 uses 23 synthetic references
instead of exposing the original 23 personal skill references. Original preservation
hash manifests are intentionally absent; full acceptance routines relying on them
must remain blocked, not replaced by fake baseline evidence.

A future production patch must be derived/reviewed separately; DO NOT blindly apply
POCKET_DIFF.patch or LIVE_VS_PREVIEW_DO_NOT_APPLY.diff. Training/provider policies are
preparation only, not executable native configs. No externally compatible trainer
lock or verified free-provider setup is claimed.
