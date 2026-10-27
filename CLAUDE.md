# Ouroboros

A coding-agent plugin (Claude Code first, Codex packaged) that puts one agent, **L1**, in charge of
a user's development goal: `init` is an interview that produces four documents (scenarios,
validation, spec, delegation), `approve`
is the single human handoff, and from then on L1 plans a work graph, runs installed-Dryforge
Ready–Go cycles in one persistent headless worker session, and finally beta-tests the result
itself. Small repository: skill text under
`src/skills/`, ~2k lines of standard-library Python runtime (run record, relay, Claude Code adapter), a
bash build that emits five host packages, and a unittest suite. Maintained by one person;
experimental; rebuilt from its concept on 2026-10-27, first live unattended run completed
2026-10-28 (see `docs/tracking/status.md`).

## Project structure

```
ouroboros/
├── CLAUDE.md / AGENTS.md            ← this entry point (identical)
├── docs/
│   ├── architecture.md              ← repo topology, runtime components, one-cycle flow, packaging
│   ├── business-rules.md            ← L1/L2/L3 vocabulary, init→approve→cycles lifecycle, invariants, edge cases
│   ├── security.md                  ← trust model, authority after approve, audit, sensitive data
│   ├── standards.md                 ← build/manifests/README gates, verification gates, Git practice
│   ├── engineering-notes.md         ← TMPDIR trap, clean-tree verify, shipped src/skills, host quirks
│   ├── operations.md                ← setup, test/build/verify, trying the plugin, runtime CLI, release
│   ├── contracts.md                 ← user commands, host packaging contract, internal CLI contract
│   ├── RESEARCH_MCP_SETUP.md        ← optional research MCP setup for Dryforge's research stage
│   └── tracking/
│       ├── status.md                ← direction, what is built/verified, ordered remaining work
│       ├── decisions/               ← index.md + 0001–0008 decision records
│       └── findings.md              ← unresolved problems with reasons
├── src/
│   ├── AGENTS.md                    ← skills source + Python runtime: scope, boundaries, invariants
│   └── skills/                      ← init, approve (shipped verbatim); init/scripts holds the runtime
├── platform/
│   ├── AGENTS.md                    ← per-host manifest/overlay inputs
│   └── {claude,codex,grok,agent-plugin,antigravity}/
├── build/
│   ├── AGENTS.md                    ← build.sh guards and output contract
│   └── build.sh
├── ci/
│   ├── AGENTS.md                    ← test suite layout, verify.py, how to run
│   └── test_*.py · verify.py · fixtures/fake_claude.py
└── claude/ codex/plugin/ grok/ agent-plugin/ antigravity/   ← generated packages (never hand-edit)
```

## Hard gates

1. **One approval, no further consent.** Nothing executes before `approve`; after it, L1 decides
   everything. Any design that asks the human to confirm an action during execution is wrong. The
   only thing L1 may ask afterwards is a verification only a human can perform (beta test
   ESCALATE); that is evidence, not consent.
2. **Installed Dryforge only.** L1 sends `/dryforge:ready|go|migration` as the user message of a
   headless worker session; a missing plugin is reported, never replaced by bundled or pasted text.
3. **Same L2 session for Ready and Go** of one cycle (and across cycles by default); L2 sees only
   an ordinary caller, never Ouroboros identity or private records. Its tools come from an
   allow-list, never a bypass flag.
4. **`src/skills/` is the only source; packages are regenerated, never edited.** `ci/verify.py`
   fails on any diff, and everything under `src/skills/` ships to users.
5. **Private run state stays in the target project's git-ignored `.dryforge/ouroboros/`**, never in Git.

## Before you work

- Read `docs/standards.md`, `docs/engineering-notes.md`, and the `AGENTS.md` of the directory you
  touch.
- **Before changing anything about authority, approvals or permissions:** read `docs/security.md`
  (authority table) and decisions 0001, 0002 and 0008.
- **Before touching `src/skills/`:** read `src/AGENTS.md`; remember the shipped-verbatim rule.
- **Before a release or any manifest edit:** read the version rules in `docs/standards.md` (ten
  manifests + CHANGELOG heading + tag).
- **Before running tests on macOS:** export `TMPDIR=/private/tmp`. Never run the tests and the
  build at the same time.
- **Before running `ci/verify.py`:** commit or remove every untracked file.

## When something goes wrong

Report to the user immediately if you observe: a path where a worker (L2/L3) could create an
approval, acceptance or completion on its own; L1 presenting its decision as the human's; private
`.dryforge/` content staged for commit; or a generated package that no longer matches `src/skills/`
after a build. Everything else goes into `docs/tracking/findings.md` with the condition, blast radius
and why it is not fixed now.
