# 0007 — Project documentation in English

## Context
The maintainer communicates in Korean; the code, comments, `README.md` and CHANGELOG are in English
with Korean, Japanese and Chinese README translations. The repository is public.

## Decision
`CLAUDE.md`/`AGENTS.md`, everything under `docs/` (except pre-existing translations) and module
`AGENTS.md` files are written in English.

## Alternatives
- **Korean**, matching the maintainer's working language. Rejected: external readers and the code's
  own language are English; one documentation language avoids drift between two versions.

## Consequences
- Conversation with the maintainer may be in Korean while written artifacts stay English.
- README translations remain the only non-English documents and follow `README.md`.
