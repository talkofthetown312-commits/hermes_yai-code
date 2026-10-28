## Change

Describe the focused change. Feature/fix/ci branches target develop; release
promotion from develop to main requires a separate approved pull request.

## Verification

- [ ] Static source gate passes.
- [ ] Generated-fixture checker tests pass.
- [ ] Source checks CI passes on this PR revision.
- [ ] No secrets, private state, runtime files or generated outputs are included.
- [ ] Runtime/native/provider checks not performed are explicitly identified.
- [ ] No installed applications were modified and nothing was deployed.

## Review boundary

Do not merge without owner approval. Passing CI does not authorize deployment,
training, private-data migration or live-provider activation.
