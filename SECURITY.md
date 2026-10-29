# Security policy

## Scope and support boundary

This is source-only, synthetic staging work, not a supported production deployment.
Security review should identify the exact commit and affected component. Historical
Phase 1/2 code and previously built APKs are not promised security backports. No
response-time SLA, professional audit certification or production support is implied.

The documented verification gate uses synthetic fixtures and does not establish
native Android acceptance, safe live-provider integration or private-data migration.
Loopback binding and a separate HOME reduce accidental access; they are not an OS
sandbox against arbitrary reviewed/tested code or other processes on the device.

## Report privately

Do not put live credentials, pairing fragments, private prompts/memories, user
documents, raw database/log contents or signing keys in public issues, pull requests,
attachments or Actions output.

If GitHub's Security → Report a vulnerability control is enabled for this repository,
use that private channel. If it is unavailable, contact the repository owner through
an already trusted private channel to arrange a safe report. No dedicated monitored
mailbox or private-reporting feature is claimed to exist merely because this file
is present. Never request a token or publish exploit payloads containing real data.

A useful initial report contains:

- The affected commit, component and host/runtime versions.
- Expected versus observed behavior and a minimal synthetic reproduction.
- The trust boundary involved (authorization, provenance, approval, exports,
  filesystem isolation, provider execution or another boundary).
- A description of potential exposure without the exposed secret/data itself.

## Suspected credential or data exposure

Notify the owner privately. Use owner-approved revocation/rotation for a potentially
exposed credential. Removing a file from the current tree does not erase Git history,
Actions logs, release assets or external copies. Do not rewrite/force-push history,
restore old live credentials or delete evidence merely to obtain a clean scan.
Review exposure, recovery and retention with the owner before changing those surfaces.

## Contributor safeguards

- Use only generated synthetic canaries and fixtures in tests and reports.
- Keep runtime stores, `.env`, authentication, signing keys, weights, logs and
  backups outside version control. `.gitignore` and pattern checks are safeguards,
  not comprehensive prevention or retrospective removal.
- Validate permissions and record/project scope on the server. Retrieved text and
  approved guidance are not authority to add tools or execute commands.
- Keep imported content untrusted; preserve provenance and disputed labels.
- Review the complete staged diff and exact published head, including PR text and
  workflow output. Do not publish matched secrets while describing a scan finding.
- Do not bypass approval/consent checks, weaken tests or enable real providers just
  to make CI pass. Dependency setup and application test execution are separate.

See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[public-release checklist](docs/PUBLIC_RELEASE_CHECKLIST.md). Repository settings,
branch protections and private-reporting availability require separate owner/admin
configuration; documentation does not enforce them.
