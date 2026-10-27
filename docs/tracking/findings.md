# Findings

## Runtime tests depend on an un-symlinked temp directory
- **Observed:** on macOS with default `TMPDIR` (`/var/folders/...`), 32 tests error and 2 fail in
  `test_runtime_bridge` and `test_runtime_merge`; with
  `TMPDIR=/private/tmp` all 247 pass.
- **Why it matters:** a contributor running the suite as documented in `README.md` (no `TMPDIR`)
  sees red and may "fix" production symlink checks.
- **Why not now:** the affected modules are slated for removal in the rebuild; fixing fixtures for
  code that is going away is wasted effort. If the modules survive, resolve fixture paths with
  `Path.resolve()` before use.

## Bundled Dryforge-derived skills diverge from the installed Dryforge
- **Observed:** `src/skills/ready|go|migration` differ from the installed Dryforge 1.3.8 in
  `SKILL.md` and several references (e.g. an extra `go/references/agent-lifecycle.md`).
- **Why it matters:** a user who runs `ouroboros:ready` directly gets behavior that differs from
  the Dryforge L1 actually invokes, and three CI contract tests pin the bundled text.
- **Why not now:** the skills are being removed, not reconciled.
