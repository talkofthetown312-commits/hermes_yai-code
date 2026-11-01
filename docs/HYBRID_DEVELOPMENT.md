# Hybrid agent development

The initial advisory protocol below is retained for compatibility. The executable
six-agent service, model adapters, persistent task queue and mobile dashboard are
documented in [PLATFORM.md](PLATFORM.md); packaging is in
[TERMUX_PLATFORM.md](TERMUX_PLATFORM.md).

Run `python3 -B tools/hybrid_demo.py` from the repository root for a fully
synthetic planner → worker → reviewer cycle. Run
`python3 -B tools/run_addon_tests.py` for policy and protocol regression tests.

`evolution_addons.hybrid.HybridCoordinator` accepts three explicit trusted host
adapters. Planning and review stay local; the worker can be local or an explicitly
authorized OpenRouter adapter. Each stage receives a copied, project-bound task
packet and prior structured results. Results are advisory: the coordinator never
executes tools, applies patches, writes Hermes stores or deploys services. Review
approval means advisory acceptance only, not permission to deploy or merge.

The OpenRouter route requires an explicitly selected concrete free model, trusted
catalog metadata observed within five minutes, and host authorization. The existing
free-router policy rejects paid/unknown prices. There are no retries, account
rotation or provider fallback. The built-in demo uses deterministic local adapters;
it performs no inference and does not contact providers. The existing Pocket JCode
broker remains disabled. This is an integration protocol, not an installed Hermes
SDK/JCode client or an operational live multi-agent service.

Adapters must enforce hard timeouts and transport/output limits themselves. The
coordinator checks cancellation/deadlines before and after each callback and caps
aggregate returned output; it cannot preempt a blocking Python callback or bound
its memory allocations. Treat adapters as trusted application code. Distinct
agent identities do not establish independent model judgment. Sensitive-text
checks reject common credential patterns and tool markup but are not a complete
privacy classifier: hosts must supply synthetic data only. A future live adapter
needs separately reviewed authentication, provider routing verification, hard
resource enforcement and real model behavior tests.

## Portable tests and preview

Python 3.10+ on POSIX, modern Node with fetch/Blob/File, Pillow and pypdf are needed
for complete tests. No npm dependencies are required. In the prepared cloud
instance Python 3.12.14, Node 24.19.0 and both parsers are already installed.

Use the existing checkout; cloud tasks are isolated and need no extra worktree.
Run the complete suite in a fresh disposable source copy:

```sh
cd /workspace/hermes_yai-code
scratch=$(mktemp -d /tmp/hermes-source-XXXXXXXX)
git archive HEAD | tar -x -C "$scratch"
cd "$scratch"
python3 -B tools/run_complete_portable_tests.py
```

This uses committed source. For uncommitted development, copy the source while
excluding `.git` and generated runtime directories instead. Do not reuse a
previous complete-test extraction; the runner intentionally refuses existing
preview state. Bootstrap rewrites catalogs to synthetic absolute paths in the
disposable copy, so do not run it in a checkout containing work to preserve.
The Git bootstrap checks source layout rather than requiring an omitted historical
authorization report; it neither creates evidence nor authorizes deployment.

For development startup in a disposable source copy:

```sh
python3 -B tools/serve_synthetic.py --port 0
```

Use the reported assigned loopback port internally and read the generated pairing
file privately to verify authenticated `/api/evolution/state`. Do not print the
pairing value or create a user-facing localhost link. Stop only your own process.
Never use the historical production/phone preview launchers. No credentials,
personal data, running services, models or Android deployment are needed here.
