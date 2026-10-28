# Pocket portability repair — isolated source release

This is a repaired source/testing handoff, NOT a production deployment patch.
No installed application, personal source, provider configuration, scheduler,
model or database is imported or migrated.

Run the complete applicable portable suites in a NEW extracted working copy:

    python -B tools/run_complete_portable_tests.py

The smaller tools/run_portable_tests.py remains available. It includes 38
synthetic acceptance entries (the original 32 plus six offline broker/watchdog
checks), 12 edge tests, 25 offline regressions per phase, nine mocked export
checks, every router safety test, and executable-worker portability tests.
The complete runner additionally runs Phase 1 authenticated HTTP and simulated
DOM, Phase 2 HTTP/security/scope and simulated DOM, dataset edit denials,
synthetic restart persistence, and JavaScript syntax checks. Both launch only
test-owned ephemeral loopback servers and close their owned processes.
A new extraction is required for each complete rerun; existing preview state is
rejected, not erased. Tests need POSIX Python 3.10+, Node with fetch/Blob/File,
and Pillow/pypdf for attachment regressions. No packages are installed for you.

Repairs:
- Both fake agents resolve sys.executable at construction. No fixed virtualenv
  Python path or platform-specific string-replacement patch is used.
- The portable runner no longer rewrites source or generates a duplicate runner.
  A validated --stage option chooses only the two extracted synthetic stages.
- Old regression/complete reports are invalidated before execution.
- Router/portability tests are mandatory and counted in portable gate results.
- Phase 2 feature tests require an explicit fresh synthetic URL and owned pairing
  path; production/current-staging ports are rejected. Development preview now
  supports port 0 and reports/validates its actual assigned port.
- Phase 1 simulated-DOM assertions are now counted explicitly.
- Generated machine-specific catalogs are reset; bootstrap regenerates them.

Evidence and provenance:
REPAIR_CHANGE_INVENTORY.json gives this repair's exact before/after source hashes.
INTERPRETER_AUDIT.json records the whole-bundle interpreter audit.
REPAIR_TEST_RESULTS.json is the current repair verification; older acceptance,
packaging, preservation and source-inventory reports remain historical evidence.
MANIFEST.sha256.json describes the complete current package and excludes itself.
SOURCE_INVENTORY.json is historical provenance, not a current integrity manifest.
The initial repair harness expected deletion of an old evidence ID; inspection
showed the correct contract retains provenance and sets needs_reverification.
The assertion was corrected to verify that flag AND actual reapproval/export
rejection; application code was not weakened or changed.

Limits and integration status:
All automated results are synthetic/offline contracts, not native Android
rendering/touch/picker/share/save/doze evidence or real model competence.
The original full 64-entry acceptance still needs omitted private preservation
baselines, model inputs and separate approval gates; no mock replaces them.
Legacy test_start tests target the original launcher, intentionally disabled in
staging; both stage startup refusals are exercised by portable P06 instead.
Free routing remains a standalone policy validator, NOT wired to JCode/Hermes or
a live verified provider catalog. Training, live memory and scheduler are disabled.
This package is suitable for a controlled synthetic Pocket integration rehearsal
and production-specific patch design/review, NOT wholesale replacement/cutover.
Actual integration needs a reviewed minimal patch, fresh private backup and
no-data-loss rollback, real auth/history/files checks, native device testing and
separate explicit deployment approval.

Preservation qualification: 291 of 292 guarded files stayed hash-identical.
The active .hermes/auth.json changed during this session (cause not independently
established; consistent with automatic OAuth refresh). No repair command writes
or restores it. This is not represented as a frozen authentication snapshot.
