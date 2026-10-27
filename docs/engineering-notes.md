# Engineering notes

## macOS: run tests with `TMPDIR=/private/tmp`
- **Symptom:** fixtures that create workspaces under the default `/var/folders/...` can confuse
  path comparisons because `/var` is a symlink to `/private/var`.
- **Response:** run the suite with `TMPDIR=/private/tmp` as documented. Do not weaken production
  path checks to make a fixture pass.

## Tests and the build must not run concurrently
- **Mechanism:** `build/build.sh` swaps the five package directories; `test_mission_contract` and
  `test_runtime_contract` read those directories to assert byte-identity with `src/skills/`.
  Running both at once produces spurious failures.
- **Response:** build first, then test (or the other way round), never in parallel.

## `ci/verify.py` needs a completely clean tree, including untracked files
- **Symptom:** "verification requires a clean tree" listing a file you never touched.
- **Cause:** it runs `git status --porcelain --untracked-files=all` before and after the build.
  `.DS_Store`, `__pycache__/`, `*.pyc` and `.dryforge/` are git-ignored and do not count.
- **Response:** commit or remove stray files first; keep scratch work outside the repository.

## Everything under `src/skills/` is shipped
- **Mechanism:** `build.sh` copies `src/skills` into all five packages and `verify.py` requires the
  Antigravity package to be byte-identical to it. A developer file dropped into `src/skills/init/`
  ends up installed on every user's host.
- **Response:** developer material goes beside `src/` (e.g. `src/AGENTS.md`), never inside it.

## Frontmatter injection can silently no-op
- **Mechanism:** the build injects `disable-model-invocation` / `allowed-tools` with a perl
  substitution on `^---\n...\n---\n`. A stray blank line, CRLF or missing closing `---` makes perl
  match nothing and exit 0.
- **Response:** the build re-greps each generated SKILL.md and fails on zero or multiple matches.

## Codex reads the root `plugin.json`, older clients read `.codex-plugin/plugin.json`
- Both are generated and must carry the same identity and `interface`; `verify.py` cross-checks them.

## Headless Claude Code as L2: what was verified and what was not
- **Verified (2026-10-27, claude 2.1.311):** a headless `claude -p … --output-format json` can be
  started from inside a Claude Code session; `/dryforge:ready` sent as the user message loads the
  installed skill and the skill's questions come back as plain text with the turn ending;
  `--resume <session_id>` continues with memory; without `--allowedTools` a turn that needs Write or
  Bash does nothing and lists them in `permission_denials`, with the allow-list (including the
  `mcp__*` pattern, which the CLI accepts) the same turn runs with no denial; `claude plugin list`
  prints `dryforge@dryforge` with a `Status:` line the adapter parses.
- **Not verified:** a full Ready → Go cycle driven by L1, L3 behavior under the allow-list, cost and
  context growth across cycles. The unit tests use `ci/fixtures/fake_claude.py`; a green suite is
  not live evidence.
- A Claude Code **subagent** cannot be L2: it does not see user-invocable-only plugin skills and has
  no question tool.

## Detached turns: the `/bin/sh` wrapper and pid semantics
- The adapter launches `claude` through `/bin/sh -c '… >N.json 2>N.err; echo $? >N.exit'` in a new
  session so the exit code survives the short-lived CLI that started it. The recorded pid is the
  shell's; `session-stop` signals its process group. `alive()` uses `os.kill(pid, 0)`; a pid reused by
  an unrelated process after exit would read as RUNNING until it also exits (the `.exit` file is the
  stronger signal if that ever matters).
- `session-wait` does not hold the record lock while blocking; settlement of a result happens inside
  a transaction and is idempotent (`turn.cost_recorded`, `turn.state != RUNNING`).

## Owner pid is the host process, not the CLI
- Each CLI call is a short-lived process. `--owner` must carry the L1 host's pid (`$CLAUDE_PID` on
  Claude Code) or every owner record is immediately stale and the second-L1 refusal never fires.

## Per-command cost of the record CLI
- Every transaction re-runs `git rev-parse` and three `git check-ignore` calls (~100 ms). The full
  test suite takes ~40 s mostly from subprocess CLI calls; this is acceptable for now.

## Changelog heading regex
- Both `build.sh` and `verify.py` take the **first** line matching `^## v<version>`; an
  `## Unreleased — …` section above it is skipped. A typo like `## 1.4.2` (no `v`) makes the build
  fall through to the previous release and fail the version comparison.

## Local plugin trial
- `claude --plugin-dir ./claude` from another project loads the generated Claude package directly.
