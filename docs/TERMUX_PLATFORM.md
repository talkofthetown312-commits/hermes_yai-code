# Termux source packaging and rollback

This is an isolated Python/browser application package, not an APK. The commands
below are operator instructions for a later approved phone installation. No
phone deployment or existing Hermes service changes are part of this PR.

## Build and inspect on the development machine

```sh
python3 -B -m hermes_platform.package build --output /tmp/hermes-platform.tar.gz
```

The command prints the archive SHA-256. It includes only an explicit runtime
source allowlist, the dashboard, and the reused hybrid contract modules. It never
includes Git metadata, tests, model weights, task databases, tokens or config.
Each file also has a manifest checksum. Keep the archive and expected SHA-256
together through a trusted transfer; checksums provide integrity, not a signature
or independent publisher authentication. No public release/upload is performed.

## Later, after phone deployment approval

Use a maintained Termux distribution with Python 3.11+ and SQLite support.
`pkg install python` supplies the runtime; no pip/npm application dependencies
are needed. An optional installed Ollama service/model is a separate prerequisite
and is not installed or restarted by these commands. Select a model appropriate
to device memory. Background restrictions, battery use and model performance
must be tested on the actual device.

From a reviewed source checkout, use a new private release root outside `.hermes`:

```sh
python -B -m hermes_platform.package install \
  --archive /path/to/hermes-platform.tar.gz \
  --sha256 THE_VERIFIED_ARCHIVE_SHA256 \
  --root "$HOME/hermes-evolution-platform"
cd "$HOME/hermes-evolution-platform/current"
python -B -m hermes_platform.server \
  --data "$HOME/hermes-evolution-platform/data" --port 18878
```

Package installation verifies the archive and all members, rejects unknown paths,
symlinks, duplicates and traversal, and refuses existing foreign directories.
It stages a versioned release, then atomically switches `current`, retaining the
prior `previous` pointer. It starts no process and changes no existing service.
Pair the device browser privately with this workspace's `data/pairing-token`.
Never reuse a production token or production ports 8766/8877. Keep the application
in foreground during initial testing; no boot job, wake lock or service is added.

Check authentication, a small local task, visible six-agent progress, review and
approval, cancellation, keyboard/touch layout and restart persistence. Model
availability must be verified separately. Browser emulation on Linux does not
prove these native/device behaviors. Do not modify installed Hermes data to make
an integration test pass.

## Rollback without data loss

1. Stop only this platform's foreground process with Ctrl-C. Do not kill Hermes,
   Ollama or another service. Wait for the platform process to exit.
2. Preserve the entire platform `data` directory in a separate private backup
   while it is stopped. Never replace or restore Hermes production databases.
3. From the reviewed source checkout run:

```sh
python -B -m hermes_platform.package rollback --root "$HOME/hermes-evolution-platform"
```

4. Restart the prior `current` release using the same explicit platform data path.
   Verify pairing, task history and approvals before creating more work.

Rollback switches only source pointers. It does not delete releases, restore a
database, erase tasks or start services. This initial release uses additive schema
v1 only; future schema-changing releases must document backward compatibility and
a tested migration/restore plan before deployment. With only one installed release,
rollback refuses; stopping the isolated platform leaves existing Hermes untouched.

Automated tests verify package integrity, repeat installation, two-release pointer
rollback and preservation of a synthetic data sentinel on Linux. Actual Termux
installation, native Android rendering and phone rollback remain unverified.

## Timeout-fix update for an existing phone installation

The original client silently used a 30-second HTTP response timeout, even when
the configured model budget was 120 seconds. The corrected runtime honors the
configured budget while retaining the parent process deadline. Diagnostics now
distinguish timeout, refused connection and unreachable network without logging
raw provider/credential data.

`tools/update_phone.py` is a version-specific updater for this reviewed runtime.
It verifies a pinned digest of all runtime files from the source ZIP before
importing or installing them. Stop only the platform's port-18878 foreground
session with Ctrl-C, then invoke the updater from the verified source checkout:

```sh
python -B tools/update_phone.py /path/to/reviewed-source.zip --start
```

It refuses an active platform lock, preserves the platform task database, token
and Android model configuration, and retains the previous source release.
`--start` runs only the updated platform in the foreground. Existing Hermes and
Ollama services are not stopped or restarted. The failed task remains in history;
submit a new small test task after reconnecting. Phone inference completion still
needs to be checked; a working small JSON prompt does not prove all six stages.
