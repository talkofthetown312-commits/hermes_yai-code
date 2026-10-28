# Rollback boundaries

Packaging changes: new handoff workspace plus requested Downloads ZIP only. No
production source/config/database/model changes and no staging stop/restart.

For NEW extracted development work: Ctrl-C the foreground tools/serve_synthetic.py
process that YOU started. Retain test evidence. Remove only that extracted copy's
synthetic runtime if desired; never restore an old database over active history.
Do not use broad pkill/killall or kill a PID from a historical report.

For the ORIGINAL phone preview, rollback was documented in
phase2/PHONE_PREVIEW_REPORT.txt: its own identity-checking stop_preview.py verifies
root, process command, bind and port. That source is included for review only.
Running it from this extracted archive cannot identify the original runtime
because RUNNING.json and pairing are deliberately absent. The current handoff
request explicitly says DO NOT STOP STAGING; no stop helper was run for packaging.

Production changes applied: NONE. No production restoration or migration rollback
is needed. A future live cutover requires its own exact-file/database compatibility
review, backup/verification strategy, separate approval and tested rollback.
The archived source diffs are not approved deployment patches.

Qwen/LoRA: served model selection stays unchanged; no weights were packaged, edited
or loaded. Keep unpromoted version outputs separate after any future approved run.
JCode: disabled; no provider or CLI configuration rollback is needed.
