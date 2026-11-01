# Hermes Evolution agent platform

The platform extends the existing PR #7 contracts and the current `develop`
workbench with a separate six-agent service. Existing Pocket integrations,
pairing fixes, synthetic model assistant, stores and tests are retained. No
installed Hermes instance is needed or discovered.

## Run locally

From this checkout, with Python 3.11+ on Linux or Termux:

```sh
python3 -B -m hermes_platform.server --data /tmp/hermes-platform-development --port 18878
```

The data path must be new, empty and owner-only, or already marked as a platform
workspace. It must not be an existing Hermes directory. The server creates its
own token and SQLite database with private permissions. Read the token from the
new workspace's `pairing-token` file locally and enter it in the dashboard.
It is kept in browser memory only, never in a URL or browser persistent storage.
The UI works in an Android browser at the same device's loopback address. The
cloud onboarding UI does not expose localhost previews.

By default every model role uses `qwen2.5-coder:7b` at the existing local Ollama
endpoint `http://127.0.0.1:11434`. Ollama and a model must already be installed
and running by the operator. The platform neither downloads models nor starts,
stops or reconfigures any model service. Choose a smaller installed model on
memory-limited devices. No Ollama runtime/weights are included in the package.

Generate an editable platform-only configuration:

```sh
python3 -c 'import json; from hermes_platform.server import default_config; print(json.dumps(default_config(), indent=2))' > /tmp/platform-config.json
python3 -B -m hermes_platform.server --data /tmp/hermes-platform-development --config /tmp/platform-config.json --port 18878
```

Stop the first foreground platform process before starting a second with the
same state. An exclusive process lock prevents two schedulers sharing a database.
The config contains `routes` for coordinator, research, developer, validator and
reviewer; `seconds` (1–120 per call); and `memory_sources` (empty by default).
The Memory agent is deterministic and never invokes a model itself.

## Delegation and review

1. Coordinator produces explicit Research and Developer instructions.
2. Memory reads only source IDs explicitly attached by the user from the host's
   authorized registry. With no attached IDs it reads nothing.
3. Research receives the task, delegated instruction, messages and shared state.
4. Developer receives research and proposes bounded relative-path source files.
5. Validator performs model review plus deterministic Python/JSON syntax checks.
6. Reviewer assesses the full result. A passing result waits for human approval.

Each stage is a real queued job with persisted attempts, structured messages,
outputs and status. The dashboard displays this activity and the code proposal.
Approval is tied to the current revision and a hash of all outputs; stale or
repeated decisions fail. Approval records acceptance only. Proposed artifacts
remain in isolated task storage; no repository files are automatically written,
no generated program is executed and no deployment or merge is performed.
Model validation is not execution evidence. Unknown source formats receive a
text-only check, explicitly labelled in the result.

One scheduler processes a stage at a time, fairly across queued tasks. Local
model calls run in owned child processes; total wall deadlines and cancellation
terminate those children. Transport/429/502/503/504 failures retry with bounded
backoff, at most three attempts per stage. Invalid outputs, auth and policy
errors stop immediately. Interrupted stages resume on restart without replaying
completed stages. A model call completed just before a crash can repeat: inference
is at-least-once, and enabled cloud routes can incur duplicate charges. There are
no model/provider fallbacks, tools, automatic patch application or account rotation.

The database holds up to 1,000 tasks and returns the latest 100 in the sidebar;
older IDs remain accessible through the API. Use a separate new workspace when
archiving old work. This is a single-owner development service, not a multi-user
authorization system or a production job cluster.

## Optional GPT and Claude

Change an explicit role's route in the platform config. GPT uses provider `gpt`,
endpoint `https://api.openai.com/v1/chat/completions`, and key environment name
`HERMES_PLATFORM_GPT_KEY`. Claude uses provider `claude`, endpoint
`https://api.anthropic.com/v1/messages`, and `HERMES_PLATFORM_CLAUDE_KEY`.
Set an exact model ID supported by that provider: a response reporting a different
model is refused, so use a versioned ID instead of an alias when necessary.
Use a provider/model supporting the respective API and JSON response contract.

Credentials are read only from those dedicated environment bindings when making
an explicitly configured request. Nothing reads Hermes auth/config files or
copies existing credentials. Do not put credentials into task text, source or
configuration JSON. Cloud endpoints are fixed HTTPS URLs; redirects are refused,
TLS verification remains enabled and configured proxy settings are preserved.

Each task must separately opt in to sending its text, previous outputs and
messages to configured cloud roles. This can cost money. When any memory source
is attached, cloud routing is refused for the entire task, including derived
outputs. Configure all roles locally for memory-assisted work. No cloud inference
was invoked during development or tests.

## Read-only memory

The host may explicitly register exact approved source paths in `memory_sources`:

```json
{
  "approved_excerpt": {"kind": "text", "path": "/absolute/approved/excerpt.md"},
  "approved_snapshot": {
    "kind": "sqlite", "path": "/absolute/approved/closed-snapshot.sqlite",
    "table": "notes", "id_column": "id", "text_column": "body"
  }
}
```

This is a schema example, not authorization to access a private source. Register
only paths whose read access has been explicitly approved. The code performs no
directory scanning, environment-based source discovery or automatic memory import.
Text sources are limited to 16 KB. SQLite sources must be closed standalone
snapshots with no WAL/journal sidecars; they use a pinned read-only descriptor,
immutable/query-only SQLite, an explicit identifier-checked schema mapping,
20-row and 16 KB context limits. No source database or schema is modified.
Symlinks, hardlinks and special files are refused. Schema differences require an
explicit mapping, not arbitrary model-generated SQL. Citation records include
source ID, row ID and content hash.

Selected excerpts and derived model output are retained inside the isolated
task database. Revocation means removing a source from configuration and restarting;
it does not erase already retained task context. Do not attach private sources
without authorization for that local retention. Same-UID processes can still read
one another's files; owner-only permissions are not an adversarial OS sandbox.

## API and verification

All API requests require the workspace bearer token. Host and Origin checks reject
cross-origin and DNS-rebinding requests. The service binds only `127.0.0.1`, uses
strict bounded JSON, serves fixed static files, sets restrictive CSP/no-store
headers, and never renders model output as HTML. It exposes no shell/file-write
endpoint. Keep it on loopback; this built-in HTTP server is for local development.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/state` | Role routes, source IDs, scheduler state, recent tasks |
| `POST /api/tasks` | `prompt`, `cloud_consent`, `memory_sources` |
| `GET /api/tasks/{id}` | Steps, messages, status and approval hash |
| `POST /api/tasks/{id}/decision` | `action`, `revision`, `result_hash` |

Run `python3 -B -m unittest discover -s hermes_platform/tests -v` for unit,
integration, security, transport/API and package tests. Run
`python3 -B tools/run_phase3_checks.py` for the entire existing Phase 1–3 suite
plus platform checks in a disposable copy. This remains the CI workflow.

With Playwright and Chromium installed, run
`python3 -B tools/test_platform_browser.py` for a real browser workflow at mobile
and desktop viewport sizes. It uses a local Ollama protocol fixture, performs
approval and restart checks, tests HTML injection handling and checks for
horizontal overflow. This is browser emulation, not native Android/device proof.
Live Qwen, GPT and Claude quality/compatibility still require actual operator
configuration and separately reported inference tests.

See [Termux packaging and rollback](TERMUX_PLATFORM.md) for the source release.
