# Source-only Git publication

This tree is derived from the Downloads Hermes Evolution portability-fixed v4 ZIP.
Original ZIP SHA-256:
2600a59d182e4e8cbbfbe3bff52ae4733a0a1e80f6f271e84851acc25c552445

At the initial import, the archive's enclosing hermes-evolution-handoff directory
was represented by the repository root, with retained files preserving original
relative paths and bytes. Subsequent reviewed integration/CI changes are separate
Git commits, not alterations to the pinned ZIP. Public-release preparation replaces
the root README with current instructions and preserves its previous bytes at
docs/HISTORICAL_HANDOFF_README.md. Both Phase 1/2 application trees remain unchanged
by that documentation preparation.

Generated historical reports, logs, inventories, old authorization records and
generated patch/diff outputs are omitted. Older documents may refer to those
omitted artifacts; they are not current verification evidence. No databases,
private memories, credentials, signing keys, weights, caches or builds belong in
this repository. Synthetic fixture text is test input, not personal memory.
.gitignore guards future test/build outputs. The ZIP remains unchanged.

Portability/security audit: original pinned ZIP passed independent read-only
inspection; 48 verifier self-tests passed. Retained source bytes and these
publication additions are scanned again before publication. This is static
verification, not a new execution of the archived runtime test suites.

For approved synthetic execution only, use a fresh disposable copy and follow
PORTABILITY_REPAIR.md. Do not run historical preview launch/stop utilities against
installed apps. Publishing this source does not authorize installation,
deployment, live-provider activation, training, private-data import or production
cutover. Native Android and live-provider behavior remain unverified.

The proposed MIT license applies only to rights contributors hold or are authorized
to license. Archive possession/hash verification does not establish those rights.
Review THIRD_PARTY_NOTICES.md and docs/PUBLIC_RELEASE_CHECKLIST.md before making
the repository public. A preparation PR does not change visibility or select/promote
the public default branch.
