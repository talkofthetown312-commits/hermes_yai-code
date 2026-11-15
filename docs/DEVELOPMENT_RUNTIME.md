# Hermes Evolution development runtime

This adds an opt-in runtime alongside the historical synthetic stages. It never
opens the installed Pocket data directory. Existing phone services, models and
chats stay in place. This is development source, not a deployed or verified APK.

## Start on the Android phone

Use the repository root in Termux with Python 3.10+ on POSIX. First inspect the
phone without scanning personal stores or loading a model:

```sh
python3 -B -m hermes_runtime.device
```

The initial inference transport is an already-running Ollama on
`http://127.0.0.1:11434`. It lists installed models only; it never downloads or
changes a model. An installed GGUF alone is not an Ollama installation. For an existing GGUF, configure `gguf` with absolute `path`, exact `sha256`, and
absolute `executable` pointing to the real llama-cli binary (without symlinks).
It appears as a separate explicitly selected `gguf:<hash-prefix>` model. The
short offline CPU adapter verifies the file hash and GGUF magic, requires 2560
MiB available RAM, uses two threads/context 512/output 64, and aborts at 1600 MiB
RSS or below 768 MiB available RAM. It never discovers or downloads other models.
Its CLI compatibility and output quality still need verification on your phone.
Installed Hermes SDK inference remains integration work after device inspection. Tool execution is deliberately disabled.

Start with a NEW private directory, separate from both existing Pocket and preview:

```sh
python3 -B -m hermes_runtime.server --data "$HOME/.hermes-evolution-dev" --port 18877
```

Open `http://127.0.0.1:18877/` on that same phone. Tap Connect and enter the value
from its private `pairing-token` file locally. Do not share or commit the token.
The CLI refuses production/old-preview ports 8766 and 8877. Stop the foreground
server with Ctrl-C; it cancels its owned workers only.

For a private local QR, install the optional reviewed QR dependency and run:

```sh
python3 -m pip install -r requirements-runtime.txt
python3 -B -m hermes_runtime.pair --data "$HOME/.hermes-evolution-dev"
```

`pairing-qr.svg` contains a credential. It is written with mode 0600 inside the
runtime directory and never sent to a QR service. It opens loopback on the device
that scans it; another device cannot reach the phone backend through this QR.
On a single phone, entering the token locally is usually easier than scanning
its own screen. QR URLs clear the fragment immediately after local pairing.

For cloud inference set `OPENROUTER_API_KEY` privately in the backend environment,
then select Cloud and refresh models. Never put the key in the browser, repository
or a message. Every inference request refreshes the catalog, rejects nonfree or
unknown pricing metadata, selects a concrete `:free` model, disables provider
fallback and sends zero price limits. There are no retries or paid fallback.
Explicit conversation consent is required for every cloud send. Availability and
provider terms still depend on OpenRouter. No live provider was called in tests.

## Workbench, sources and memory

Start with `hermes_runtime/config.example.json`. Put your edited configuration in
an ignored private directory and pass `--config /private/path/config.json`.
One data directory is bound to one project. Use a separate directory for another.
No private source is discovered, copied or granted automatically.

Each host-selected source needs `id`, `kind`, absolute `path`, absolute `root`,
and a list of exact string `records` IDs. The existing source adapters support
Hermes/history/knowledge/memories/chat/web/Pocket SQLite schemas, Markdown sections
and facts JSONL. Unknown schemas fail with a partial/unavailable result. Paths
must resolve under the configured root without symlinks. Do not select backups,
credentials or authentication stores. The host configuration is trusted code-level
configuration, not permission to transmit data to cloud providers.

In Skills & memory grant the listed records for local retrieval. In Tasks & setup,
separately grant exact records for memory extraction. Only granted user messages
with session/time provenance enter the candidate review queue. Reviews retain the
`not_verified` distinction and do not write native Hermes memory. Revoking a source
removes its retrieval and extraction grants. Previously reviewed candidates remain
visible as provenance; they are never automatically injected into chat.

The six-hour schedule is OFF until enabled. It runs within this runtime, records
observed heartbeat/completion/failure and counts missed intervals. It performs one
catch-up extraction rather than replaying every missed run. There is no Android
boot hook, wake lock, battery setting change or uptime promise.

Teach, static test, exact-hash approval, version history, revocation and guidance
reuse use the existing workbench. Reuse selects guidance for the next local message
and revalidates its approval before sending. It grants no tools. A static contract
pass is not model-behavior evidence. Clear selected guidance in Tasks & setup.

## Coding and training

Coding uses local planner and reviewer models plus the explicitly selected local
or free-cloud worker. The host enables user-selected specification text; the
historical coordinator still defaults to synthetic-only. Schema checks, sensitive
text checks, hard outer task deadlines and process-group cleanup apply. Results
are advisory. No file is read automatically and no patch is applied or deployed.

For datasets, accept a correction you have actually checked and supply its usage
rights. The evidence is labeled human acceptance, not automated model success.
Review/redact and consent to the exact row in the workbench. Editing invalidates
consent and requires a newly accepted correction. Download/share is deliberate;
previously exported or trained data cannot be recalled through revocation.
Secret checks and regex PII checks require human review as well.

Training is an external **trusted host integration**, not a bundled GPU trainer.
Set `training_command` to an absolute executable followed by trusted argv. The
HTTP API cannot supply commands. The runner receives `--run-dir <private-dir>`
with train/validation/test JSONL and `manifest.json`. It runs offline with a clean
environment; base weights must already exist on that host. No account, GPU, model
weights or dependency stack is provisioned. To use a remote GPU, configure a host
adapter that enforces its independently selected data and budget policy.

A recipe selects `Qwen/Qwen2.5-1.5B-Instruct`, its exact 40-character commit,
`seed`, LoRA `rank` (1–64), `epochs` (1–3), and a predeclared `max_eval_loss`.
At least three independent reviewed families are needed for nonempty holdouts.
The runner must emit:

- `adapter/adapter_model.safetensors`: valid bounded floating-point safetensors.
- `evaluation.json`: `dataset_sha256`, `base_revision`, finite nonnegative
  `eval_loss`, integer `privacy_regressions: 0`, and `behavioral_suite_passed: true`.

The host runner is responsible for real assistant-only loss masking, pinned GPU
libraries and behavioral/privacy evaluation. The runtime validates provenance,
file framing and gates, then records artifact hashes. It cannot establish a
runner's honesty from JSON. No default trainer or trained-model competence is
claimed. GGUF conversion/parity and native model promotion are still separate
integration steps. The old model is never overwritten.

## Android development variant

The native project now has `legacy` and `development` flavors. Development uses
`com.hermespocket.app.development`, port 18877, its own browser storage and export
provider authority. It can coexist with the installed app. Native picker/save/share
code is retained; the UI is served by the new runtime.

With the Android 35 SDK, Java 17+, Gradle 8.9 and suitable aapt2 already installed:

```sh
cd phase1/implementation/pocket/android
gradle :app:assembleDevelopmentDebug :app:lintDevelopmentDebug
```

No APK was built here: Gradle/Android SDK/device tools are unavailable. Do not
uninstall the installed app or rotate its signing identity. Production update
requires separate review, backup and device verification.

## Tests and rollback

```sh
python3 -B -m unittest discover -s tests -v
python3 -B tests/browser_check.py  # optional Playwright + installed Chromium
```

Run the existing complete portable suite in a fresh disposable copy as described
in HYBRID_DEVELOPMENT.md. The runtime tests use actual SQLite, HTTP and child
processes with deterministic inference fixtures. Training tests validate a fake
runner protocol; they do not train. The browser check uses a mobile viewport and
real Chromium; it is not a native Android test.

Stop the new runtime, then take a private snapshot:

```sh
python3 -B -m hermes_runtime.backup --data "$HOME/.hermes-evolution-dev" --output "$HOME/hermes-dev-backup-001"
```

It refuses running sources, uses SQLite online backup/integrity checks, and copies
new-runtime attachments and training artifacts with hashes. Registered private
sources are never copied. Keep this backup private. Restore into a new directory,
verify its manifest, and re-pair; never copy old databases over a running runtime
or over installed Pocket history. Returning to the previous phone app needs no
history rollback because this runtime never changes its data.

Before calling this phone-ready, verify local inference, free-cloud availability,
rotation/touch/keyboard/back navigation, picker/save/share delivery and cancellation,
sleep/resume, consent revocation during long jobs, and backup/restore on the actual
phone. Live memory promotion, installed Hermes SDK chat, a selected GPU trainer,
GGUF conversion and production integration remain open roadmap milestones.
