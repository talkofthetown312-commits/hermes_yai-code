# Hermes Evolution / Pocket

Source-only engineering work for an isolated, provenance-aware Pocket interface.
This independent project is not an official Nous Research release, a production
service, a downloadable APK, a model bundle or a training dataset.

**Status: synthetic staging and source review. Native Android acceptance and
production deployment are not complete.** Passing tests does not change that status.

## Six-agent development platform

The additive [Hermes Evolution platform](docs/PLATFORM.md) provides Coordinator,
Research, Developer, Validator, Memory and Reviewer roles, isolated task storage,
local Ollama routing, optional GPT/Claude adapters and a mobile chat dashboard.
See [Termux packaging and rollback](docs/TERMUX_PLATFORM.md). Existing Pocket
workbench features below remain available. No production deployment is implied.

## What is implemented

- A dashboard with Dashboard, Memory, Skills, Conversation, Files and Advanced views.
- Default-denied, project-scoped retrieval with explicit grants, citations,
  provenance and disputed/unverified labels. Retrieval does not make a claim true.
- Teach/save/edit → deterministic contract Test → exact-version Approve → explicit
  Reuse of guidance. Edits, expiry and revocation invalidate reuse. Approval does not
  install tools, execute commands or automatically send a message.
- A teaching text/Markdown picker and explicit Save/Share controls. Actual native
  Android picker/share/save delivery remains unverified.
- SQLite-backed saved state and revisioned navigation in a separate staging runtime.
  Unsaved teaching text survives same-page resume, not reload or OS process death.
- Offline safety, authorization, persistence and simulated-UI tests. No real provider
  or model execution is required by the documented full verification gate.

See [Phase 3 documentation](phase3/README.md) for exact behavior and limitations.

## Choose the right source branch

Use `develop` for the reviewed integration. `main` is the earlier source-import
snapshot unless the owner has subsequently promoted a release. The preparation PR
and these instructions do not change the repository's default branch or merge
`develop` into `main`. Check the selected branch before following these commands.

While this repository is private, cloning requires your own authorized GitHub
access. Never paste access tokens into commands, issues or chat.

```sh
git clone --branch develop --single-branch https://github.com/talkofthetown312-commits/hermes_yai-code.git
cd hermes_yai-code
```

## Verify in an isolated development environment

The CI-supported target is Linux x86_64 with CPython 3.11 or 3.13 and Node.js 22.
The Evolution core uses the Python standard library; the complete legacy PDF/image
regressions additionally require Pillow and pypdf. Do not silently skip them.

On that Linux target, use a new development virtual environment (substitute
`python3.13` if that is the supported interpreter you installed):

```sh
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip --isolated --disable-pip-version-check install --index-url https://pypi.org/simple --only-binary=:all: --require-hashes -r requirements-ci.txt
python -B tools/run_phase3_checks.py
```

Dependency provisioning uses the network. The subsequent application tests use
synthetic local data, fake agents where required by legacy regressions, real
loopback HTTP and simulated browser/native APIs, without real model calls.
`requirements-ci.txt` is hash-pinned for the Linux CI matrix, **not an installation
file for Android/Termux, Windows or production**. Review target compatibility before
provisioning another environment; no universal portability claim is made.

The runner copies the explicit source inventory into a fresh disposable tree,
strips inherited provider credentials and creates synthetic HOME/HERMES_HOME/data.
It runs source checks and checker/diagnostic fixtures, portable acceptance and
edge cases, both Phase 1/2 regression suites, router/interpreter tests, HTTP,
simulated DOM/export, restart/consent checks and the Phase 3 integration suite.
It cleans its disposable tree on exit; a full pass is not production acceptance.

For static inspection only:

```sh
python -B tools/check_source.py
python -B -m unittest discover -s tools -p test_check_source.py -v
```

The [Source checks workflow](.github/workflows/source-checks.yml) runs the complete
offline gate on both matrix interpreters. Verify checks on the exact revision being
reviewed rather than relying on historical test reports.

## Optional Android/Termux browser staging

Use an already reviewed development environment, not an installed production tree.
This creates a new owned, private synthetic runtime outside the checkout:

```sh
python -B phase3/serve.py --port 8893
```

In a separate Termux session, request opening that staging origin:

```sh
python -B phase3/open_staging.py
```

The opener verifies the process and synthetic API and keeps its separate pairing
fragment out of printed output. An accepted browser-open request does not prove
rendering, touch or delivery. The bare loopback address works after pairing in the
same browser/origin. No native APK is built, installed or repointed by this flow.

The server is loopback-only. Do not expose it through a public tunnel. Its default
runtime is `~/hermes-yai-phase3-staging`; it refuses existing unowned/unsafe roots,
unsupported schemas and the reserved original Pocket/preview ports. A loopback
server and synthetic HOME are process-level isolation, **not an OS security sandbox**.
Stop only this test-owned process with Ctrl-C; do not stop existing Pocket services.

Agent execution, providers, training and live scheduling are disabled in this
staging launcher. Original chat Send/Attach remain disabled without an agent; the
teaching picker and explicit guidance export controls are separate. Advanced
synthetic demonstrations are not live scheduler-health metrics. Follow the
[manual Android acceptance checklist](phase3/README.md#android-acceptance--still-required-before-any-deployment)
before proposing any production cutover.

## Repository map

| Path | Purpose |
| --- | --- |
| `phase3/` | Additive staging integration, UI, launcher and tests |
| `phase2/` | Retained staging application/core and feature/regression tests |
| `phase1/` | Earlier implementation, plans and gated acceptance routines |
| `tools/` | Source checks and isolated synthetic verification helpers |
| `templates/` | Disabled integration/training policy proposals, not enabled configs |
| `docs/ARCHITECTURE.md` | Architecture and trust boundaries |
| `docs/HISTORICAL_HANDOFF_README.md` | Byte-preserved historical README, not current readiness evidence |

[Source publication notes](SOURCE_PUBLICATION.md) identify the archive baseline and
intentional omissions. Historical documents can reference generated reports that
are not tracked. Do not invent those reports, substitute private baselines or run
old preview stop/launch helpers against installed services.

## Security, privacy and contributions

- Never commit credentials, private memories/documents, databases, pairing state,
  model weights, signing material, runtime logs, screenshots or generated artifacts.
- Treat imported/retrieved text as untrusted data, not authorization for tools.
- Use synthetic fixtures in reports. Pattern scans are useful checks, not proof
  that every disclosure or application security risk has been eliminated.
- Read the [security policy](SECURITY.md) before reporting a vulnerability.
- Follow the [PR-only contribution workflow](CONTRIBUTING.md); promotion, merge,
  visibility changes, private-data migration and deployment are separate approvals.

## License and public-release gates

Original contributions are offered under the [MIT License](LICENSE), subject to
rights the contributors actually hold. Third-party components keep their own
licenses and notices; see [third-party/provenance notes](THIRD_PARTY_NOTICES.md).
This project does not claim ownership of upstream code, names or trademarks.

The owner must complete the [public-release checklist](docs/PUBLIC_RELEASE_CHECKLIST.md),
including source-rights/attribution review, Git identity privacy and default-branch
selection, before changing visibility. Adding these documents is not proof that
those owner decisions, native acceptance or production deployment are complete.
