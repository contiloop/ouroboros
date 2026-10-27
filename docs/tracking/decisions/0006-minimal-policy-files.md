# 0006 — Drop LICENSE, CONTRIBUTING and SECURITY files for now

## Context
The fork inherited full policy files from Dryforge. The project is experimental, has a single
maintainer and does not yet solicit contributions or vulnerability reports.

## Decision
Remove `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md` and the packaged license copies. Keep
`"license": "Apache-2.0"` in every manifest, keep the Apache link and the Dryforge/prekuter
attribution in the READMEs, and keep the upstream READMEs (`README.upstream.md`,
`README_ko.upstream.md`) for reference.

## Alternatives
- **Keep the files as inherited.** Rejected: they described Dryforge's processes, not this project's,
  and would need rewriting anyway.

## Consequences
- The repository declares Apache-2.0 only via manifest metadata and README text; adding a `LICENSE`
  file back is a one-line task when the project leaves the experimental stage.
- The branding test enforces that attribution to `prekuter` and the `Apache-2.0` string stay in
  `README.md`/`README_ko.md`.
