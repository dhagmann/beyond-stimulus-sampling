# Changes

## 0.3.0

- Expanded researcher review to show definitions, anchors, level instructions, shared content, pools, models, and criteria.
- Added optional multiple writer models, assigned across families while keeping each family's writer fixed across treatments and revisions.
- Passed exact judge evidence and explanations to the affected writers during targeted revision.
- Added diagnostic flags for unexpected constructs and a material check for departures from the shared argumentation style.
- Added automatic full reports, compact printable family audits, and the `bss audit` command.
- Added checksums for complete cached call records, protected frozen files from report/export overwrites, and improved malformed-record errors.
- Fixed duplicate proposal caching and construct-ID collisions during setup.
- Added regression tests and full command-line tests using an explicitly synthetic external provider. No tests call live models.

The protocol is now `bss-3`. Earlier frozen runs and proposal caches require their original software commit. This update leaves the submission manuscript, supplement, empirical data, and analyses unchanged.

## 0.2.0

- Added model-assisted content/style pool planning followed by explicit researcher review.
- Added deterministic sampling across families and shared sampled inputs within each family, including revisions.
- Added sampled-input display to the audit report and validation of the frozen sampling plan.
- Added the manuscript, reproducible analysis inputs, blinded build, APAquarto extension, and compilation instructions.
- Added a strict allowlist for the manuscript's data release. No raw survey exports, participant identifiers, or private model execution logs are included.

The protocol identifier is now `bss-2`. Existing frozen runs require their original software commit; this update does not rewrite their messages, ratings, or acceptance criteria.
