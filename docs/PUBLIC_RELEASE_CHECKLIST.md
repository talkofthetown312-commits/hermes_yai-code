# Public-release checklist — owner decisions required

This is a preparation gate, not approval to make the repository public, change its
default branch, merge/promote source, rewrite history or deploy an application.
Unchecked items are deliberately unresolved; documentation does not prove them done.

## 1. Confirm source rights and attribution

- [ ] Confirm authority to license the handoff-derived source and later contributions.
- [ ] Approve the proposed [MIT License](../LICENSE) for rights actually held by the
  contributors. MIT was selected as the permissive recommendation, not as a way to
  override another author's terms.
- [ ] Review [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md), copied code and any
  notices/dependencies. Resolve unknown ownership or missing redistribution permission.
- [ ] Review any future binary distribution's bundled-library, SDK and model terms
  separately. This source preparation does not license or publish an APK/model bundle.

## 2. Review all publication surfaces while still private

- [ ] Refresh current remote heads, tags and pull-request refs; account for every
  reachable revision and any LFS/submodule/other uninspected object surface.
- [ ] Scan historical file contents and commit messages as well as the latest tree.
  Retain path associations when identical blobs appear at different paths.
- [ ] Privately review Git author/committer names and email addresses. These remain
  public in history even when no email appears in the current source files.
- [ ] Review issue/PR text, comments, Actions logs/artifacts, release notes/assets
  and enabled wiki/discussion/package surfaces. Missing/inaccessible checks are gaps.
- [ ] If a credential is suspected, privately verify and obtain owner-approved
  rotation/recovery steps. Do not print matches or silently rewrite/delete history.
- [ ] Keep a verified private recovery copy outside the repository. Do not publish
  backups, reports containing private material, live stores or authentication files.

Pattern scans and GitHub log masking are not proof of no sensitive content. Repeat
checks for the final source head and latest metadata before the visibility change;
earlier audit counts or a stale clean badge are not release evidence.

## 3. Decide the public landing branch

The source-import `main` and the integrated `develop` are different snapshots.
Choose explicitly; this PR performs none of these settings or merge operations:

- [ ] Retain `main` as default and promote the reviewed `develop` source through a
  separately approved release PR; **or** deliberately select `develop` as default
  through owner/admin settings after reviewing the intended public landing content.
- [ ] Confirm the preparation documents and selected license are present on the
  branch visitors will see. Merging preparation into `develop` alone does not update
  an older default `main`.
- [ ] Require the relevant PR checks and review before any promotion; preserve
  unrelated branches and do not direct-push, force-push or rewrite histories.

Neither visibility approval nor this preparation request selects a default branch
or authorizes a release merge. Refresh actual PR state instead of assuming an older
open/merged status remains current.

## 4. Verify the proposed public head

- [ ] Run the source scanner and generated checker/diagnostic fixtures.
- [ ] Run the complete offline synthetic gate on both CI-supported interpreters;
  provision only reviewed target-compatible parser dependencies in the test runner.
- [ ] Verify actual workflow results on the exact proposed head, not an old revision.
- [ ] Verify remote tree/blob identities and modes against the reviewed local commit.
- [ ] Check every local documentation link and ensure setup commands match the
  supported platform. Keep historical evidence separate from current instructions.
- [ ] Confirm no databases, secrets, weights, generated test reports, logs, builds or
  private recovery artifacts are committed or exposed through release assets.

The public README must not claim verified native touch/picker/share/background
behavior, working paid/live providers or production readiness from synthetic tests.
Native acceptance, backup/migration plans and explicit deployment authorization are
separate prerequisites for any later production cutover.

## 5. Apply only an owner-approved settings change

- [ ] Recheck repository visibility and administration permission. Write/push access
  alone is insufficient to change visibility or configure required protections.
- [ ] The owner acknowledges exposure of all branches, Git identities/history,
  discussions and available Actions/release metadata, not only the selected tree.
- [ ] An owner/admin applies the authorized visibility change and independently
  verifies that GitHub reports the intended visibility afterward.
- [ ] Review branch rules, secret scanning/push protection and private vulnerability
  reporting availability. Do not claim these are enabled because docs recommend them.

This checklist does not change settings, elevate access or start services. Keep
visibility, default-branch selection, merges, history rewrites, native acceptance
and production deployment as independent decisions and report each truthfully.
