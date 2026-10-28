# Phase 3 — Pocket integration (synthetic staging only)

This additive integration uses Phase 2's actual retrieval, transactional SQLite
sidecar, skill workbench and original Pocket frontend. Phase 1/2 application
source and the installed Pocket remain unchanged. No fake dashboard metrics or
production memory connectors are installed. Synthetic fixtures are explicitly
registered only inside the new isolated staging runtime.

## Working features

- Dashboard/Memory/Skills/Conversation/Files/Advanced navigation, Back/Forward,
  active-section accessibility state and revisioned server-side section preference.
- Dashboard counts query actual staged skill states, including expired approvals,
  grants and audit events. An unavailable dashboard reports unknown counts, not
  fabricated zeros. Scheduler status is `not_started`, not simulated health.
- Default-denied, record-scoped, read-only retrieval. Cards show excerpts, author,
  classification, disputed/unverified labels, sensitivity, project and complete
  citation metadata (record/session IDs, timestamp, content hash). Revocation
  clears displayed results and discards late search responses.
- Teach/save/edit, deterministic contract Test, exact-hash Approve and explicit
  Reuse. Reuse can stage guidance in the original unsent composer or offer visible
  Save/Share controls. Each reuse/export revalidates approval on the server.
  Editing, revocation, expiry and stale revisions prevent reuse. Skills remain
  guidance only: no installation, new tools, command execution or automatic send.
- A visible text/Markdown picker imports into an unsaved teaching draft, with
  size/type checks and confirmation. A synthetic fixture Save control is supplied.
- Saved skills, approval evidence, consent/grants, revocations, history and section
  preference persist across restarts in the private staging sidecar. Background/
  pageshow handlers only read state and preserve unsaved teaching text while the
  page stays alive. Unsaved text is deliberately NOT written to browser storage;
  explicitly Save before a reload/OS process kill.
- Original Pocket chat/file/export UI remains available. Empty offline staging
  conversations and selected-file upload/remove are API-tested without inference.
  The original chat Send/Attach controls intentionally remain disabled when the
  agent is unavailable; the separate teaching picker/Save/Share controls are active.
  The production chat service is neither replaced nor contacted.
- The original Advanced workbench remains available, including its clearly labeled
  synthetic dataset/scheduler demonstrations; those are not live scheduler metrics.

## Start or reopen staging

From the source checkout:

```sh
python -B phase3/serve.py --port 8893
python -B phase3/open_staging.py
```

The default private runtime is `~/hermes-yai-phase3-staging`, OUTSIDE the checkout.
Its new pairing credential is unrelated to production. The opener validates the
process identity and synthetic server, then passes its pairing value privately in
a URL fragment to the Android browser. It never prints that fragment. Opening the
bare address after pairing works in the same browser/origin.

The server binds only 127.0.0.1. Ports 8766/8877 are refused. Do not expose it via a
public tunnel. Custom runtime names must start `hermes-yai-phase3-`; existing
unowned directories, symlink paths/contents and non-private filesystem permissions
are refused. A process lock prevents two servers using the same sidecar. Unsupported
schema versions fail closed without migration. Standard-library SQLite transactions
provide persistence; this is not a backup service or an OS sandbox.

The launcher copies only baseline application source into its owned runtime and
clears inherited provider/authentication environment variables before importing it.
No installed Hermes/Pocket code, databases, memories, model weights or credentials
are imported. No dependency installation, inference, paid providers, training,
cron scheduling, merge or deployment is performed. Stop only this test-owned server
with Ctrl-C (or its tracked process); do not stop production or the old preview.

## Verification

```sh
python -B tools/run_phase3_checks.py
```

This copies the explicit Git source inventory into a private disposable tree and
runs the static scanner, its fixture tests, the complete existing Phase 1/2 offline
suite and the new Phase 3 suite. A source-only publication does not include the
generated handoff acceptance report, so the bootstrap accepts SOURCE_PUBLICATION.md
plus the expected fixture layout instead. It does not invent an acceptance result.

The existing suites include portable acceptance/edge cases, both regression suites,
free-router safety, interpreter portability, HTTP, simulated DOM/export adapters,
dataset-edit revocation and restart behavior. New tests cover real loopback API
integration, authentication/origin/host denial, concurrent navigation conflicts,
source immutability, provenance, skill lifecycle/expiry, persistence, unsafe runtime
paths/schema refusal and selected-file workflow. Hardlink rejection uses generated
stat metadata on Android (native link creation is unavailable/denied) and an actual
test-owned hardlink on Linux CI. Phase 3 simulated-DOM tests use the
real API but mock browser/native export delivery; they are not native UI tests.

CI runs this offline gate with Python 3.11/3.13 and Node 22 using the existing
read-only, immutable-pinned actions. Passing CI does not authorize merge/deploy.
Generated runtime files, pairing values, logs, screenshots and reports stay outside
Git. The original pinned v4 ZIP is unchanged; the repository is a reviewed change
on top of that source baseline, not a new pinned archive.

## Android acceptance — still required before any deployment

Native accessibility/screenshot access is unavailable to this Termux session:
ADB has no connected device, local screencap fails and UIAutomator is denied access
to its required Android shell directory. The browser-open request can be accepted,
but that does NOT establish rendering, touch or file delivery. No native pass is
claimed. Inspect only this synthetic staging origin and synthetic files:

- [ ] Tap all six sections; confirm scroll, touch targets, keyboard and Back/Forward.
- [ ] Grant selected fixture sources, search `widget`, inspect citations, revoke.
- [ ] Teach → Save → Test → Approve → Reuse into unsent composer; edit/revoke and
      confirm reuse fails. No message may be sent to a provider.
- [ ] Save `phase3-teaching-synthetic.md`, choose it with the Android file picker,
      import and inspect text. Canceling the picker must not alter saved state.
- [ ] Save approved SKILL.md; confirm actual file bytes in Android Files.
- [ ] Open/cancel a share chooser with synthetic guidance only; confirm delivery
      separately if sharing to a local target. Browser sharing is capability-based.
- [ ] Background/resume while editing, screen rotation and OS process recreation;
      confirm unsaved-process-lifetime and explicit-Save semantics. Android may stop
      Termux; no foreground-service/wakelock or automatic server restart is added.

Native APK/WebView validation, live private-memory registration, real provider/model
integration, real skill behavioral validation, backups/migration, installation and
production cutover remain outside this change. The existing APK is not rebuilt or
repointed: this is an isolated browser staging URL for review.
