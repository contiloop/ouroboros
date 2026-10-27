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
- **Structured-question relay smoke run (2026-10-27, claude 2.1.311):** one real run from a temporary
  git project with `.dryforge/` ignored; L2 = `claude -p --input-format stream-json --output-format
  stream-json --verbose --permission-prompt-tool stdio` through `relay.py`, model `claude-opus-5-5`.
  - Commands, every one exit 0: `draft --proposal` → `shown` → `approve` (ACTIVE, `budget usd: 3`) →
    `doctor --host claude` (dryforge installed and enabled) → `cycle-start --kind development` →
    turn 1 `session-start --skill ready` → turn 2 `session-send` → turn 3 `session-send` +
    `session-stop` → turn 4 `session-send` → `show`. `session-wait --timeout 240` after each launch
    and each answer; it returned RUNNING once (turn 1, full 240 s) and the next call returned COMPLETE.
  - Turn 1 (`/dryforge:ready` + a one-line goal): the skill used the question tool at once —
    QUESTION round 1 (four questions, one `multiSelect`) → `session-answer` with the first label of
    each (the multiSelect answered with a single plain label) → QUESTION round 2 (four questions) →
    `session-answer` → RUNNING → COMPLETE after ~5.5 min: `num_turns` 31, `questions` 2,
    `auto_allowed` [], `permission_denials` [], `skills` = `dryforge:go`, `dryforge:migration`,
    `dryforge:ready`, session `98bd99f2-…`, `text` = the plan summary pointing at
    `.dryforge/spec.md`, `plan.md`, `handoff.md`.
  - Turn 2 ("use AskUserQuestion to ask exactly one question 'Which storage?' …"): QUESTION after
    3 s, `questions[0].options` labels `Plain text files` / `SQLite`, `multiSelect` false;
    `session-answer --answers '{"Which storage?": "SQLite"}'` → RUNNING; COMPLETE after 4 s with
    `text` = `STORAGE=SQLite`, `questions` 1, the same session id. `events.jsonl` holds `question`
    (actor L2) + `answer` (actor L1) per round. File modes: `2.stream.jsonl`, `2.q1.json`, `2.a1.json`
    and every other `turns/` file are 0600.
  - Turn 3 ('Which format?' Markdown / JSON): QUESTION after 3 s; `session-stop` → `state: STOPPED`,
    `run_status` ACTIVE; events `question` (L2), `unanswered` (L1), `stop`; no `3.exit`, no `3.json`.
    `session-stop` returns as soon as the wrapper shell is gone; the relay and `claude` were still
    visible for about 2 s afterwards (the relay's SIGTERM grace), then gone.
  - **Resume after a stop during a question: works.** Turn 4 `session-send` ("Reply with exactly:
    RESUMED") → COMPLETE after 4 s, `session_id` equal to the recorded `98bd99f2-…`, `text` =
    `RESUMED`, `num_turns` 1, `is_error` false; the host's `system/init` and `result` events carry
    the same id. So `orchestration.md` may continue the same session after such a stop.
  - **`total_cost_usd` of a `--resume`d session is cumulative over the session, not per turn:**
    turn 1 1.9033, turn 2 1.9897 (143 output tokens), turn 4 2.0467 (7 output tokens);
    `duration_api_ms` behaves the same, `num_turns` and `usage` are per turn. The runtime adds each
    value to `spent_usd`, so the run reached 3.89 after turn 2 and went STOPPED `limit:budget`
    although the session had cost 1.99; the proposal was amended to `budget usd: 20`
    (`draft`/`shown`/`approve` → `amended`, ACTIVE, session kept) to finish the procedure. Final
    `show`: `spent_usd` 5.94 recorded, actual session cost 2.05. Not fixed in this cycle.
  - Multi-select and `other` answers: not host-verified.

## Detached turns: the `/bin/sh` wrapper and pid semantics
- The adapter launches `claude` through `/bin/sh -c 'umask 077; … >N.json 2>N.err; echo $? >N.exit'`
  in a new session so the exit code survives the short-lived CLI that started it (the umask keeps
  the three files 0600). The recorded pid is the shell's; `session-stop` signals its process group.
  `alive()` consults the `.exit` file first: once it exists the turn is over, whatever the pid says;
  only without it does `os.kill(pid, 0)` decide, so a pid reused by an unrelated process cannot make
  a finished turn look RUNNING. A killed turn leaves no `.exit` file.
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
