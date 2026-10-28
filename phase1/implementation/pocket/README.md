# Isolated Evolution Phase 1 copy — NOT the installed Pocket

This copy is private staging only. Do not run the legacy installation/deployment instructions below. No APK was built or installed for Evolution. start.py is deliberately disabled; bridge.py refuses the live data directory/port and cannot launch the installed Hermes agent. Test harnesses use disposable stage-owned data and synthetic messages only. Read ../README.md, ../ACCEPTANCE_REPORT.md and ../SECOND_APPROVAL.md first.

The remainder is preserved baseline documentation, not authorization to start or change live services.

# Hermes Pocket — installed Termux setup

Source copied from `/storage/emulated/0/HERMESAGENT/1328/hermes-pocket` without changing that source or replacing existing user work. This directory contains source, the working loopback web bridge, and a locally built and signed native Android launcher APK. The APK does not bundle Python/Hermes/Ollama; Termux services must remain running.

## Current interface — 0.2.0

The current installer is `/storage/emulated/0/Download/Hermes-Pocket-0.2.0-release.apk` (package unchanged, version code 2, same signing identity). Install it as an update, not after uninstalling; uninstalling clears WebView pairing. The old 0.1.0 packaging evidence below is historical.

- **Attach** uses Android’s document picker. Select up to six PNG/JPG/WebP/GIF photos, PDF/DOCX/XLSX documents, or UTF-8 text/code/CSV files, up to 10 MB each. Files are copied to private phone storage, not sent to a provider merely by selecting them. Tap the filename for an image or extracted-text preview. Remove unused attachments from the composer. Unsent uploads are recoverable when reopening that conversation; unsent typed text is only retained while this page stays loaded.
- **Send with attachments:** Cloud requires the visible sharing-consent checkbox. Text is bounded (48k characters/file, 60k/turn), PDF reading inspects up to 100 pages; Office parsing reads document paragraphs or stored cell values, not formulas, charts or layout. Truncation/errors are explicit. Scanned/encrypted PDFs need a text/unlocked copy or page photos; no automatic OCR is claimed. Selected photo bytes use Hermes’s native image routing with the configured vision-capable Cloud model; no automatic auxiliary provider is called. Tools the agent runs may access the network. Local text budget is smaller; the installed local model cannot accept photos and is still not a reliable tool agent.
- **Tool cards:** expand to inspect bounded arguments/results. Completed means the tool returned, not that its operation succeeded; inspect its output. Safety approvals are still denied, not bypassed; there is no interactive approval UI. Common credential patterns are masked in tool cards, but masking is not a complete secret detector. Review exports before sharing.
- **Copy / Share / Save:** available for messages and tool details. Export chat includes message text, attachment filenames and visible tool details, not attachment bytes. Attachment preview offers Share file / Save file separately. Android Share grants the chosen recipient read access to an app-cache copy. Save uses Android’s create-document picker and confirms completion with a toast. Browser fallback uses browser clipboard/share/download APIs; unsupported sharing reports an error rather than pretending success.
- **Files:** ask Hermes to create a downloadable file. Its per-chat `outputs/` folder is listed here; tap a file to Share or Save. Only top-level regular files up to 10 MB appear (maximum 50), not arbitrary filesystem paths or symlinks. The app does not automatically expose pre-existing files elsewhere on the phone.
- Private attachments/workspaces live under `~/.hermes-pocket/workspaces/`; a 200 MB upload quota protects phone storage. Once sent, attachments are retained for conversation continuity; there is no automatic deletion of conversation evidence. Share-cache copies are removed on a later share after 24 hours. The HTTP file APIs require the pairing token in a header and validate conversation ownership. Uploaded HTML/XML is shown as text, never rendered as active content.
- The native launcher retains loopback-only navigation, disabled file/content URL access and WebView debugging, no JavascriptInterface, no camera/storage permission, and disabled Android backups. Picker URI grants and the private read-only share ContentProvider are explicit exceptions for user-selected transfers. Back closes an open preview/export dialog or sidebar before leaving the app.

Runtime attachment parsing uses the already-installed Pillow and pypdf packages. No global Hermes/provider settings or signing key were replaced. This app still depends on the Termux bridge, and local mode additionally depends on Ollama.

Verification commands:

```sh
cd ~/hermes-pocket
python -m unittest discover -s tests -v
node --check web/app.js
node tests/web_pairing.cjs
node tests/web_interface.cjs
python tests/security_live.py --restart
python tests/interface_live.py  # real Cloud usage; synthetic fixtures only
python build_android.py
python verify_apk.py
```

`web_interface.cjs` uses linkedom from `~/.cache/pocket-ui-qa/node_modules/linkedom` (override with POCKET_LINKEDOM). DOM/transport tests and APK bytecode/lint checks do not verify native picker, share-target, save destination, keyboard, or visual behavior on this phone. Those require operator testing after installation.

## Run / reopen

```sh
python ~/hermes-pocket/start.py --open
```

URL: http://127.0.0.1:8766/

The helper starts missing services in dedicated tmux sessions (`hermes-pocket` and `hermes-pocket-ollama`) and reuses existing services. It never kills another service, installs Hermes, changes credentials, or downloads a model. Services survive leaving this terminal, but Android can still kill Termux; tmux is not a boot service or a battery-exemption mechanism.

The bridge prints the pairing token ONLY in its local tmux pane:

```sh
tmux attach -t '=hermes-pocket'
```

Detach with Ctrl+B then D. `--open` opens a token-bearing browser fragment, which the app removes and stores locally before requesting APIs. Fragments are not sent as HTTP URLs. You can instead open the URL and enter the locally printed token manually. Never share the token. No secrets are embedded in web assets.

Foreground alternative: `python ~/hermes-pocket/bridge.py`. The default Hermes executable is `~/.hermes/venv/bin/hermes`; HERMES_BIN can override it. Keep this project in Termux private storage.

## Installed Hermes compatibility

Actual installed version: **Hermes Agent v0.15.2 (2026.5.29.2)**, Python 3.14.6, OpenAI SDK 2.24.0.

`HERMES_COMPATIBILITY.txt` records the exact installed `hermes --version` and `hermes chat --help` output. `--resume`, `--provider` and `--model` exist; `--format stream-json`, `--base-url` and `--api-key` do not.

`hermes_adapter.py` therefore runs the INSTALLED `cli.HermesCLI` and its actual `AIAgent` in a separate process for each turn, wrapping callbacks as JSON-line events. It passes provider overrides to the supported Python constructor, restores history through Hermes's own SessionDB, and preserves the resulting session ID (including compression continuation IDs). This is not a direct model chatbot and does not upgrade or patch Hermes site-packages. The SDK surface is version-specific; a future Hermes change needs rechecking rather than automatic upgrading.

Cloud uses the existing configured provider/model: `openai-codex` / `gpt-6.1-sol`. No cloud key or provider configuration is copied into the project or replaced. Hermes may naturally refresh its own OAuth tokens while making a Cloud request; that occurred during live tests. Do not restore an older refresh token over the live auth file.

## Local inference and limits

Ollama is served at http://127.0.0.1:11434/ and the adapter explicitly resolves `provider=custom`, `base_url=http://127.0.0.1:11434/v1`, and the non-secret dummy key `ollama`. Available models were already installed:

- `android-1b:latest` — 1.2B Llama, Q8_0, approximately 1.3 GB on disk; used in tests.
- `explysm/android-1b:latest` — another existing 1.2B Q8_0 model.

No model was downloaded. The active runner reports a 4096-token context and CPU inference.

Local turns retain the actual Hermes agent, but use only its terminal toolset, at most three iterations, and 160 output tokens to constrain the installed small model. Existing configured inference fallbacks are disabled IN THIS LOCAL WORKER ONLY; automatic compression is also disabled because an auxiliary compressor could route history to a cloud provider. Global configuration is untouched. Long local conversations can exceed context rather than silently moving to cloud.

**Important observed limitation:** Cloud chat and follow-up passed. Local chat and exact follow-up passed in the explicit tools-disabled synthetic test. With normal agent tools enabled, this 1B model was slow, emitted malformed tool-like text with a larger toolset, and still failed exact hyphenated-code-word recall after narrowing the toolset. Hermes persisted the correct session and two user turns; model reliability is not a session-storage guarantee. Do not treat this model as a verified reliable local tool agent. A stronger model requires a user choice; none was downloaded automatically. The interrupted runaway test chat is marked as an error; semantic test failures are recorded in reports, not silently retried or transferred.

**Local inference is NOT an offline-only guarantee.** Terminal commands and other user-requested tools can use the network. Existing global fallback configuration was inspected: neither `fallback_model` nor `fallback_providers` was configured. External memory providers were not configured. These findings do not make all tools offline.

## Privacy, approvals, storage

Pocket deliberately passes `ignore_rules=True` for both modes: persistent memory, user profile, SOUL.md, AGENTS.md and project rules are not automatically attached. Existing memory files are preserved; synthetic live tests did not upload them. This changes Pocket's prompt composition only, not the existing Hermes CLI's behavior. Explicit tools can still access local files if a user requests it; do not ask a cloud model to read private files unless you intend to share their contents.

The bridge never enables yolo mode. Dangerous-command approval requests are denied in this noninteractive worker; clarification requests are returned to the user as text. There is no interactive approval UI or a verified agent-cancellation button.

- Pocket conversations and session mapping: `~/.hermes-pocket/chats.sqlite3`.
- Actual Hermes history: existing `~/.hermes/state.db` via the installed Hermes runtime.
- Pairing token: `~/.hermes-pocket/pairing-token`, mode 0600, private directory 0700.
- Diagnostics: `~/.hermes-pocket/last-hermes-diagnostic.log`, mode 0600; do not publish it.
- A private `~/.hermes-pocket/preservation-*` snapshot holds configuration/auth/memories and an SQLite backup taken before agent tests. Do not upload it.

The bridge binds only 127.0.0.1, checks Host, authenticates API calls, rejects cross-origin writes, serves an explicit static-asset allowlist, renders messages with textContent, uses a CSP and no-referrer policy, serializes turns, and closes SQLite connections after each operation. Private files are not HTTP assets. One failed/interrupted turn is never automatically retried.

## Verification

Regression tests and live bridge security checks (security checks require the bridge, make no model calls, and refuse to restart an active conversation):

```sh
cd ~/hermes-pocket
python -m unittest discover -s tests -v
node --check web/app.js
node tests/web_pairing.cjs
python tests/security_live.py --restart
```

The Python suite includes simulated CLI and SDK wiring tests; these are separate from actual model calls. The Node test checks pairing/auth frontend logic using a DOM stub, not a visual browser. A paired browser link was opened on the phone; rendered-screen interaction was not independently inspected.

Explicit real-provider synthetic tests, which can incur normal Cloud usage:

```sh
python tests/smoke_live.py
python tests/smoke_live.py --production
python tests/smoke_live.py --production --local-only
python tests/tool_live.py
```

Default live smoke mode disables tools and uses a small synthetic prompt. `--production` retains the normal Pocket worker settings. Reports live in the private data directory (`smoke-report.json`, `production-report.json`, `local-production-report.json`); report names and passing modes matter. Both use actual Hermes inference/session persistence, not the simulated regression-test CLI. All automatic private-memory/rule attachment remains disabled.

## Android APK — signed release built locally

Delivered installer: `/storage/emulated/0/Download/Hermes-Pocket-0.1.0-release.apk`.
Private build copy: `~/hermes-pocket/artifacts/Hermes-Pocket-0.1.0-release.apk`.
Package: `com.hermespocket.app`; version: `0.1.0` (code 1); minimum SDK 26, target SDK 35. This is a small native WebView launcher, not Capacitor; its 12,388-byte size is valid because Python, Hermes, Ollama and the web UI run separately in Termux.

Installed and used: JDK 21, Android platform 35, build-tools 35.0.0, AGP 8.7.3, Gradle 8.9 and the native Termux ARM64 `aapt2` package. The official Gradle ZIP was checked against its published SHA-256 before extraction. Gradle 9.8.1 was left installed and is not used by this build. Updating the mismatched `abseil-cpp` dependency repaired native `aapt2` and ADB; no global full-package upgrade was performed. SDK-provided Linux/x86 executables are not substituted into PATH.

Rebuild and inspect:

```sh
cd ~/hermes-pocket
python build_android.py
python verify_apk.py
```

The build helper selects `~/.local/share/gradle-8.9/bin/gradle`, disables unsupported Gradle native integration/file watching, limits workers/heap, and uses `android.aapt2FromMavenOverride` for the ARM64 compiler. It makes no new signing key if the existing one is present. No project or secret was uploaded to CI.

Verification passed: signed release build; 25 APK checks (identity, SDK/permission boundaries, compiled network/backup policy, ZIP/alignment, signature/certificate match, secret exclusion and tamper rejection); Android lint has zero errors and one benign warning about the API-33 predictive-back attribute being ignored on older supported Android versions. `testReleaseUnitTest` reports NO-SOURCE: there are no native Android unit tests. The separate bridge suite has 10 Python tests; frontend pairing logic and 32 live security/restart checks also passed.

The Android installer was requested using `termux-open` from shared Downloads. No ADB device was connected; actual installation, native rendering/keyboard/back-button behavior, pairing and chat in the installed APK remain unverified until tested on the phone. A successful installer-open request is not a confirmed installation. The launcher includes system-bar/keyboard insets, an icon, offline reconnect instructions, loopback-only navigation and disabled WebView debugging/file/content access. Android backup and device-transfer exclusions protect its local pairing state.

## Signing key versus pairing token

Persistent RSA-3072 signing identity:

- `~/.hermes-pocket/signing/hermes-pocket-release.p12`
- `~/.hermes-pocket/signing/release.properties`

Both originals remain byte-for-byte unchanged, with 0600 file permissions inside a 0700 directory. The APK certificate was independently matched against the existing key using a public certificate export. The signing key proves APK update ownership; it is NOT an AI API key or the token entered in Connect. Keep BOTH signing files backed up together privately. Losing them can prevent in-place signed updates. Never commit, publish or copy them to shared Downloads.

The Connect dialog expects the separate pairing token from `~/.hermes-pocket/pairing-token`. View it only in the local bridge pane:

```sh
tmux attach -t '=hermes-pocket'
```

Copy that token into Connect inside the APK, then detach from tmux with Ctrl+B, D. Browser pairing and APK pairing use separate WebView/browser storage; `start.py --open` pairs the browser only. Keep the bridge running (`python ~/hermes-pocket/start.py`). The APK does not automatically launch Termux or Ollama.
