# Third-party notices and source provenance

The repository's [MIT License](LICENSE) covers contributions only to the extent
that their contributors own or are authorized to license them. It does not
relicense third-party work, grant trademark rights or replace upstream notices.
Preserve any upstream copyright/license notices in source and distributions.

## Source provenance and ownership gate

The initial import was a reviewed, source-only Hermes Evolution portability-fixed
v4 handoff; its digest and omissions are recorded in
[SOURCE_PUBLICATION.md](SOURCE_PUBLICATION.md). Phase 1/2 source was retained from
that handoff. Later integration and CI changes are recorded separately in Git.
The former root README is preserved in
[docs/HISTORICAL_HANDOFF_README.md](docs/HISTORICAL_HANDOFF_README.md).

Archive integrity, a clean credential scan, AI-assisted authorship or possession
of a file does not establish copyright ownership or redistribution permission.
Before public release the owner must confirm rights for the supplied handoff and
later contributions, identify any copied third-party code and retain applicable
notices. This document records provenance and dependency metadata, **not a completed
legal/ownership audit**. Resolve missing permission before release; do not assume
MIT can override it or remove existing attribution.

## Referenced components and optional dependencies

The repository does not vendor the dependency distributions below. Downloaded
packages, SDKs and their bundled components retain their upstream terms.

| Component | Use/boundary | Upstream license reference |
| --- | --- | --- |
| Hermes Agent, Nous Research | Optional external integration target; no official affiliation or bundled agent distribution | [MIT, upstream LICENSE](https://github.com/NousResearch/hermes-agent/blob/main/LICENSE) |
| Pillow 12.3.0 | Optional image parser required by the complete file-format regressions; pinned Linux CI wheels only | [PyPI release metadata: MIT-CMU](https://pypi.org/pypi/Pillow/12.3.0/json), [source](https://github.com/python-pillow/Pillow) |
| pypdf 6.20.0 | Optional PDF parser required by the complete file-format regressions; pinned CI wheel | [PyPI release metadata: BSD-3-Clause](https://pypi.org/pypi/pypdf/6.20.0/json), [source](https://github.com/py-pdf/pypdf) |

These entries distinguish the currently pinned parser versions from the unpinned
external Hermes installation. Version/license metadata is evidence to check, not a
promise that future releases have the same terms. Pillow wheels may bundle native
libraries with additional notices; inspect the actual distribution when preparing
any binary package. Do not treat the top-level SPDX expression as a complete list
of bundled-library obligations.

Python, SQLite, Node.js, Git, Android/Gradle/JDK and GitHub Actions are external
runtime/build/verification tools, not code newly relicensed by this repository.
Consult their own licenses if distributing them. Referenced JCode, OpenRouter,
Qwen/llama.cpp or training integrations are not enabled, vendored model weights or
licensed runtime services merely because planning templates name them.

## Distribution rules

- Retain this project's MIT notice with copies or substantial portions of covered
  software; preserve independent upstream licenses and attribution.
- Do not bundle private data, model weights, credentials, signing material or an
  installed agent to make a source release appear self-contained.
- Dependency provisioning for CI is not a grant to redistribute every dependency
  or activate a hosted provider. Review actual package/model/service terms first.
- Correct this inventory when adding, copying, pinning or distributing components;
  do not assert that an inventory-only check proves compliance.
