# Engineering notes

## macOS: 32 runtime tests error unless `TMPDIR=/private/tmp`
- **Symptom:** `python3 -B -m unittest discover -s ci` reports ~32 errors and 2 failures in
  `test_runtime_bridge` (store and gate tests) and `test_runtime_merge`, raising "ledger
  belongs outside this workspace", "path is outside the approved workspace" or similar.
- **Cause:** macOS `$TMPDIR` is `/var/folders/...`, and `/var` is a symlink to `/private/var`. The
  runtime compares `Path.resolve()` results and rejects symlinked parents on purpose; fixtures create
  workspaces under the unresolved path.
- **Response:** run with `TMPDIR=/private/tmp`. Do not weaken the symlink checks in production code
  to make tests pass; normalize the fixture paths instead if you fix it.

## `ci/verify.py` needs a completely clean tree, including untracked files
- **Symptom:** "verification requires a clean tree" listing a file you never touched.
- **Cause:** it runs `git status --porcelain --untracked-files=all` before and after the build, so
  any untracked, non-ignored file (a scratch doc, a new test, a note) fails it. `.DS_Store`,
  `__pycache__/`, `*.pyc` and `.dryforge/` are git-ignored and do not count.
- **Response:** commit or remove stray files first; keep scratch work outside the repository.

## Everything under `src/skills/` is shipped
- **Mechanism:** `build.sh` does `cp -R src/skills <package>/skills` for all five packages, and
  `verify.py` requires the Antigravity package to be byte-identical to `src/skills`. A file dropped
  into `src/skills/init/` for developer convenience ends up installed on every user's host.
- **Response:** developer material goes beside `src/` (e.g. `src/AGENTS.md`), never inside it.

## Frontmatter injection can silently no-op
- **Mechanism:** the build injects `disable-model-invocation` / `allowed-tools` with a perl
  substitution on `^---\n...\n---\n`. If a SKILL.md frontmatter has a stray blank line, CRLF or a
  missing closing `---`, perl matches nothing and exits 0.
- **Response:** the build re-greps each generated SKILL.md and fails on zero or multiple matches.
  Keep that guard when touching the build; a passing perl exit code proves nothing.

## Codex reads the root `plugin.json`, older clients read `.codex-plugin/plugin.json`
- Current Codex uses the Agent Plugins 1.0 root manifest with settings under
  `extensions["com.openai"]` and ignores the overlay entirely; older clients only read the overlay.
  Both are therefore generated and must carry the same identity and `interface`. `verify.py`
  cross-checks them field by field.

## Claude SDK: skill availability is read from the `init` system message
- `ClaudeAdapter.run` captures `slash_commands` from the first `SystemMessage(subtype='init')` and
  `resolve_skill` refuses to dispatch `/dryforge:<kind>` unless that list contains it. Loading a plugin
  requires `--dryforge-plugin <root>` (whose `.claude-plugin/plugin.json` must be named `dryforge`)
  or explicit `--load-settings user|project|local`; whether an ordinary subagent sees the plugin
  is not established by code, so verify the `slash_commands` list rather than assume.
- The connect step runs a no-tool bootstrap turn ("Reply CONNECTED") that costs tokens; it exists to
  obtain the session ID before any real work.

## Codex app-server: a parent turn can finish while child threads still hold callbacks
- `CodexAdapter` tracks `subAgentActivity` items to learn child thread IDs and refuses to settle the
  controller message until `children` is empty, no RPC callbacks are live and the event queue is
  drained. `Store.finish` likewise refuses while any request for that message is PENDING/ANSWERED.
  Settling early would expire a live L3 permission request as a side effect of L2 yielding.
- `item/fileChange/requestApproval` callbacks may omit file paths; the adapter re-reads the exact
  item via `thread/read` and only trusts `observed_changes` from there, never the reason string.

## Ledger digests bind to bytes, not paths
- `document_digest` hashes `handoff.md`, `spec.md`, `plan.md` in that fixed order with name and
  length prefixes; any byte change invalidates Ready approval. After result acceptance the three
  files may exist in `.dryforge/` or in the pinned archive dir, and duplicates must be identical.
- `migration_digest` requires `AGENTS.md`, `CLAUDE.md`, `.dryforge/status.json` and at least one
  `docs/*.md` in the path list, and rejects any path that is not documentation.

## Changelog heading regex
- Both `build.sh` and `verify.py` take the **first** line matching `^## v<version>`; an
  `## Unreleased — …` section above it is skipped, not an error. A typo like `## 1.4.2` (no `v`)
  makes the build fall through to the previous release and fail the version comparison.

## Local plugin trial
- `claude --plugin-dir ./claude` from another project loads the generated Claude package directly;
  no marketplace registration needed. For Codex, register this checkout through its local
  marketplace flow using `.agents/plugins/marketplace.json`.
