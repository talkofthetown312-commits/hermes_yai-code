# Synthetic AI workbench — explicit opt-in, not automatic training

The Skills view now has **Draft synthetic skill with free model**, **Review
synthetic AI draft**, and **Use AI suggestion in unsaved form** controls. The
protected backend is implemented, but disabled by default. This source review does
not install an APK, update production, or guarantee live endpoint availability.
Normal chat remains disabled in Phase 3.

## Learning boundary

The workflow is model suggestion → separate model critique → explicit adoption
into an unsaved teaching form → human correction/Save → static contract Test →
exact-version human Approve → explicit guidance Reuse. Neither a model critique
nor a static contract test proves real model behavior or a user fact.

No request runs automatically on page open, navigation, resume or import. The AI
route accepts only the fixed blue-widget example and the server-cached synthetic
AI output. It never sends the current teaching form, conversation, files, memories
or project source. Adopting a suggestion does not save/test/approve it, and a late
response cannot overwrite a form edited while it was waiting. Saved skill guidance
does not grant tools or imply installation/execution, and no weights are trained.

Model drafts remain explicitly AI-authored/UNVERIFIED, with draft ID/content hash.
The cached review is invalidated by a new/failed generation. A returned mutable
copy cannot change the later cloud input. Requests are serialized without a retry
queue; stale IDs/hashes and additional/private-input fields are rejected.

## Runtime activation (separate from publishing source)

The ordinary launcher performs no cloud requests and reads no provider credential:

```sh
python -B phase3/serve.py --port 8893
```

After explicit synthetic-cloud activation approval, use an **existing private**
OpenRouter env file selected by its owner. The example below is for the default
Hermes profile; choose the approved active-profile path if different. This reads
only the key field into memory, never loads the env file globally, never copies
another agent's login, and does not change account privacy/auth settings.

```sh
python -B phase3/serve.py --port 8893 --state-dir "$HOME/hermes-yai-phase3-staging" --enable-synthetic-cloud --synthetic-cloud-key-file "$HOME/.hermes/.env"
```

Both flags are required. The file must be private, regular, singly linked and not
aliased; no literal key belongs in a command, source, log or report. Do not launch
a second process against an active runtime. An approved source adoption/restart
must preserve existing pairing/data and verify the owned process, not stop production
or silently create another deployment. Private context requires separate authorization.

The page labels configured versus disabled and test-only transport states. A
configured client is **not a successful model connection**. Policy errors remain
visible; buttons never cause a fallback, automatic skill promotion or training.
The normal chat/agent remains off even when this fixed-fixture assistance is enabled.

## Protected API

All routes require the existing staging bearer token and the normal Host/Origin
checks. POST bodies are bounded and allowlisted; user prompts/content cannot be
smuggled through extra fields.

- `GET /api/integration/model-assist`: configuration/scope/state only; no model call.
- `POST /api/integration/model-assist/draft`: exactly fixture ID + explicit confirmation.
- `POST /api/integration/model-assist/review`: exact cached draft ID/hash + confirmation.
- `POST /api/integration/model-assist/suggestion`: same identity + confirmation, after
  model review. Returns unapproved form data without another model request or save.

No endpoint saves, tests, approves, installs or executes a skill. The existing
manual workbench retains those separate actions. There is no arbitrary chat/file/
memory-input route or public unauthenticated pairing bypass.

## Zero-cost transport

The selected candidate is an explicit `:free` ID, never the aggregate free router.
Every request rechecks model and endpoint pricing: all published dimensions must be
finite zero, with a healthy compatible endpoint and sufficient context. Requests
pin that provider, disable fallback and cap prompt/completion prices at zero.
Metadata/output sizes, individual network calls and response tokens are bounded.

Missing/nonzero reported cost, unexpected model, truncation, tool requests, malformed
JSON, oversized/sensitive-looking text and credential echoes are rejected. Requests
have no tools, attachments, retries or paid-model fallback. Credential-bearing
redirects are refused. Error text is reduced to safe categories, not raw provider
response contents. The module never persists/returns its credential.

During development, live synthetic probes for explicit Cohere and Nvidia free
candidates returned HTTP 404 privacy/data-policy restrictions with the selected
Hermes credential, despite zero-price metadata. That is a live blocker—not an
expired-key diagnosis, successful inference or an excuse to borrow another agent's
key. Account-wide retention/publication changes can affect other OpenRouter use;
only the owner may review/approve them. Do not relax them automatically or enable
cloud in the separate local-only bridge to hide the restriction.

## Verification and evidence limits

The offline policy tests cover price/endpoint shape, billing dimensions, costs,
output/schema limits, immutable synthetic cache, stale review, safe credential-file
selection, default disablement, serialized operations and redacted errors. Real
loopback HTTP tests inject a clearly labelled **fake model transport**, exercise
Host/Origin/token denials and show no automatic skill/audit writes. The simulated
UI checks consent cancellation, no private form upload, review-before-adoption,
late-edit retention and independent Save/Test/Approve/Reuse behavior.

These tests make no real provider request. They do not prove provider availability,
model quality, native Android rendering, picker/share/save delivery or a built APK.
The full offline gate includes these suites:

```sh
python -B tools/run_phase3_checks.py
```

## Token-free pairing diagnostics

A `pairing-check v2` error contains only link/valid-link/saved presence booleans and
a storage-status enum—not a credential, fragment, length or hash. A missing link
plus a present but rejected stored value requires replacing only that staging
browser value through Connect, not rotating server credentials or repeating links.
Ask for status text only; never collect the address bar or private token output.
