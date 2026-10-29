# Pull-request workflow

All subsequent changes go through pull requests. Do not push directly to main or
develop. Do not merge a pull request without the repository owner's approval.

1. Fetch origin and start a focused feature/fix/ci branch from origin/develop.
2. Keep changes scoped; never add private state, credentials, databases, models,
   generated reports or build products. Do not modify installed Hermes or Pocket.
3. In a reviewed test environment with the documented optional parsers available,
   run the source gate, checker fixtures and complete offline suite. See README.md
   for supported platforms and isolated dependency provisioning:
   ```sh
   python -B tools/check_source.py
   python -B -m unittest discover -s tools -p test_check_source.py -v
   python -B tools/run_phase3_checks.py
   git diff --check
   ```
4. Commit and push only the feature branch. Open a pull request with base develop,
   describe the change and verification limits, and wait for Source checks.
5. Review and merge only after checks pass and approval is given. Promotion from
   develop to main is a separate release pull request, never a direct push.

The workflow runs on pull requests targeting develop or main. Its jobs use
read-only repository permissions, pinned actions and no persisted checkout
credentials. It does not use repository secrets. The full-suite CI job installs
only the reviewed optional parser wheels from requirements-ci.txt with version/hash
pins and binary-only enforcement. This setup uses the network; the subsequent
application tests are offline/synthetic. The Linux CI lockfile is not a production
or Android/Termux dependency installation instruction.
It parses Python/JSON/XML and asks Node to check JavaScript syntax; the scanner
rejects excluded files, credential-pattern matches and fixed interpreter paths.
Its own generated-fixture tests prove selected failure cases fail closed.

Phase 3 additionally runs the existing Phase 1/2 offline application suites and
new integration tests in a fresh disposable source copy with a credential-stripped
environment and synthetic state. This approved offline scope includes router
safety, interpreter portability, regressions, HTTP and simulated DOM/export tests.
It does not start installed services, call real models/providers or perform native
Android verification. See phase3/README.md for the exact scope and outstanding
native acceptance checklist. Passing CI is not permission to merge, install, train,
import private data or deploy.

Only submit contributions you own or are authorized to license under LICENSE;
preserve independent upstream terms/notices. See THIRD_PARTY_NOTICES.md and
SECURITY.md. Public-release readiness, Git identity/privacy review and default-branch
selection are owner decisions in docs/PUBLIC_RELEASE_CHECKLIST.md, not consequences
of a green PR check.

This file records the collaboration policy; it does not enforce GitHub branch
protection. A repository administrator should enforce pull requests and required
checks on main and develop, disable force pushes/deletions, and select the Source
checks jobs after their first successful run. Collaborator write access alone
cannot configure those repository settings.
