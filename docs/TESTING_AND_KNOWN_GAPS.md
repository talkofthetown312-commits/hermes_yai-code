# Evidence matrix and reproducibility

Historical Phase 1 acceptance assesses the original 64 IDs. Private preservation
snapshots and original models used by some checks are deliberately omitted.
run_acceptance.py is byte-preserved and is NOT independently runnable in this
archive as-is. Do not fabricate snapshots or reclassify those gates as passes.

New tools/run_portable_tests.py executes an explicit synthetic subset from that
runner in-memory, without the M/GUARD/BASE/MODEL private initializers. The selected
IDs are recorded in the generated verification result. It also runs original
12 edge hardening tests, both phases' fake-agent bridge/files/adapter regressions,
and the actual frontend export function against mocked platform APIs. Any generated
fake-worker shebang adaptation is confined to a disposable extracted working copy.
It executes no model, training or real JCode process and makes no provider calls.

Original Phase 1 test_http.py expects the old catalog shape/count; use synthetic
bootstrap references, not private skill bodies. Phase 2 test_preview_features.py
is pinned to the ORIGINAL port 8877 and data directory. It is included as source
but MUST NOT be run against the still-running preview for packaging. Adapt a COPY
for a new isolated endpoint when continuing development. The UI runner accepts
FIXTURE_URL/FIXTURE_PAIRING; do not print or persist those private runtime values.

Archive verification checks CRC, content-manifest hashes, required modules,
Python/Node/JSON syntax, unsafe/symlink paths, forbidden file types/directories,
credential patterns, PII patterns, opaque high-entropy literals and unchanged
original source/config/process identity/read-only HTTP status. It is not a
proof against every possible semantic secret. See SECURITY_SCAN_REPORT.json.

Actual browser layout, orientation/touch/keyboard/navigation, native file picker,
actual saved-file delivery, share chooser/local delivery/cancellation and Android
sleep/resume remain NOT VERIFIED. API calls, simulated DOM and platform mocks
must not be reported as native device passes. The manual checklist is retained
in phase2/PHONE_PREVIEW_REPORT.txt.
