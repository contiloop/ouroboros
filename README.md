# Dryforge Mission

### Keep the intent. Run a cycle. Verify the result. Decide what comes next.

[한국어](README_ko.md) · [Mission guide](docs/MISSION.md) · [Optional MCP setup](docs/RESEARCH_MCP_SETUP.md) · [Original Dryforge](https://github.com/prekuter/dryforge)

Dryforge Mission is an experimental fork that adds a **mission-level orchestrator** above Dryforge's existing `ready → go` workflow. The human defines the desired outcome; L1 preserves that intent, delegates one cycle at a time to L2, and evaluates the result before choosing the next cycle. L2 uses L3 agents when research, implementation, or independent review needs them.

> **A successful cycle is evidence of progress, not proof that the mission is complete.**
>
> **Current scope:** skills, session/delegation policies, and a tested local state ledger are included. A standalone Claude/Codex session controller and automatic Hook wiring are **not** included. Live three-level execution still needs validation on the target host. Loading the plugin alone does not create an unattended development service.

## Why three levels?

The goal is not to spawn more agents. It is to keep **long-lived user intent** separate from **cycle-level planning** and **task-level implementation context**.

```text
Human
  ↕ final intent, constraints, decisions outside delegated authority
L1 — Mission Orchestrator
  │ chooses one cycle goal; answers questions and approves within delegated authority
  ▼
L2 — Cycle Worker = the existing Dryforge main agent
  │
  │  SAME WORKER SESSION
  │  ready → questions ↔ L1 → spec/plan approval → go → result acceptance → handoff
  │    │                                          │
  │    ├─ L3 Researcher (conditional)              ├─ L3 Implementer(s)
  │    └─ L3 Independent intent/document checks   └─ L3 Independent Reviewer
  │
  └─ outcome + evidence + checkpoint → L1 evaluates against the mission
                                         │
                                         ├─ CONTINUE / REPLAN → choose next cycle
                                         │    ├─ REUSE the same L2, when safe
                                         │    └─ SPAWN a new L2 with explicit handoff
                                         ├─ ESCALATE → ask the human
                                         └─ COMPLETE → all success criteria evidenced
```

The diagram describes the execution contract. The host must supply real sessions, message routing, and child-agent execution; Markdown does not create them by itself.

| Level | Owns | Does not own |
| --- | --- | --- |
| **L1 — Mission Orchestrator** | The user's intent, priorities, delegated decisions, mission evaluation, next-cycle selection, and L2 reuse/replacement | Unapproved product policies, unrestricted authority, or every implementation detail |
| **L2 — Cycle Worker** | One `ready → go` cycle at a time, its persistent session, task dispatch, integration, and verification | A self-directed multi-cycle sector loop or the final mission goal |
| **L3 — Task agents** | A bounded research, implementation, or independent review assignment from L2 | Mission decisions or automatic inheritance of another agent's conversation |

## One cycle, then back to L1

L1 first aligns with the human on the outcome, observable success criteria, constraints, delegated authority, and finite execution limits. It then assigns a bounded cycle goal to L2.

L2 runs the existing `ready` procedure. Questions go through the decision relay to L1; L1 answers from the approved intent or asks the human when a decision exceeds its authority. L2 does not need a different development workflow depending on whether its decision provider is human or L1, but the approval record must preserve **who decided, on what basis, and within which scope**.

L1 reviews the actual Spec, Plan, and Handoff. Approval is bound to their content digest. The **same L2 session** then runs `go`, collects evidence, obtains result acceptance, archives the cycle, and returns a checkpoint. Changing the approved documents invalidates the approval.

Only after evaluating the result does L1 choose the next cycle. L2 does not assign itself the next task. Reusing a worker does not reuse its previous approval.

For example, a paper-reading mission might first verify that a note can be stored against the correct paper, then address source-linked highlights, then validate the combined workflow. These are illustrative cycle goals, not a fixed roadmap: evidence from one cycle may change the next one.

## Session continuity and context handoff

**L2 stays the same from ready through go and handoff.** Yielding while waiting for a decision is not termination. A session ID and a summary are not interchangeable.

| Boundary | Policy |
| --- | --- |
| Inside an active ready-go cycle | Keep or resume the same L2 session. Do not swap workers just to clear context. |
| After the cycle is completed and evaluated | **REUSE** only when resume support and sufficient context headroom are confirmed and old children have stopped writing. Otherwise **SPAWN** a fresh L2. |
| Interrupted session | Reconcile the workspace and side effects, then resume the recorded ID. If recovery is impossible, pause for an explicit abort/replacement decision. |
| Fresh worker | Pass approved intent, relevant decisions, accepted branch/commit, harness, cycle archive, evidence, and remaining work. Do not claim automatic memory transfer. |

Unknown headroom is not evidence that there is enough room. The host must report real capabilities and capacity rather than inventing token counts.

A new worker does **not** require `migration`. Migration introduces an existing codebase to the project harness; session handoff reads that harness. Because `.dryforge/` is ignored by Git, a new clone or worktree needs an explicit transfer of trusted local state or resolution of the existing-harness guard. Do not silently start from `main` while the accepted result still lives on a feature branch.

### L3: resume work, not self-review

The original `go` dispatch policy stays: simple sequential `MECHANICAL`/`NONE` file changes may be implemented by L2 directly; a single `RISKY` task or parallel work uses implementer subagents. Independent final review remains separate.

| L3 action | Use it when |
| --- | --- |
| **RESUME** | Continuing or fixing the same task, with an unchanged contract, matching workspace checkpoint, confirmed resume support, and sufficient context |
| **SPAWN + handoff** | Starting a new task, replacing an unavailable session, or handling insufficient/unknown capacity or a changed contract/workspace |
| **FRESH_REVIEW** | Starting an independent review; never reuse or fork the implementer's conversation as its reviewer |

Stop the previous writer before assigning the same workspace again. Reusing a Git worktree is not the same thing as reusing an agent session. Existing bounded retries and verification gates still apply. See [agent lifecycle](src/skills/go/references/agent-lifecycle.md).

## Research remains part of ready

This branch includes the earlier LANDSCAPE extension; Mission is built **on top of it**, not instead of it.

```text
L2: understand the request and check available research tools
  → optionally delegate LANDSCAPE to one read-only L3 Researcher
  ← receive candidates, source pointers, constraints, and uncertainty
L2: reopen decisive sources and challenge the recommendation
  → ELICIT: confirm intent and material choices with the decision provider
  → PLAN: research the chosen implementation mechanism
  → GO: test decisive uncertainty with an approved feasibility spike when needed
```

LANDSCAPE compares **reuse, extension, and new implementation**. It stops on coverage, adequate evidence, and decision stability, or reports a bounded search with explicit limits. Claims remain `VERIFIED`, `UNVERIFIED`, or `RULED_OUT` for a specific route/version. Failure to find an implementation is not evidence of impossibility. A negative feasibility experiment stops dependent work; it is not permission to silently change the architecture.

**Recommended tools (Optional):** **Grep MCP** for public code patterns and **Context7 MCP** for library/API documentation. Configure them in the agent host, not by merely naming them in a skill. Preflight checks actual access in the intended researcher; missing tools lead to available alternatives or explicit evidence gaps, never automatic installation or authentication. See [MCP setup](docs/RESEARCH_MCP_SETUP.md).

## What is implemented, and what the host must provide

| Included in this branch | Still supplied or verified by the host |
| --- | --- |
| `mission` skill and intent/delegation contracts | Actual L1/L2 sessions, message delivery, and L2-to-L3 spawning |
| Same-session L2 and L3 lifecycle policies | Resume behavior, question relay, tool access, and context telemetry |
| `mission_state.py`: approval/session checks, cycle and stall limits, event deduplication, and atomic local state updates | Authentication of decision providers, truth of evidence, tool permissions, and time/cost enforcement |
| Preserved ready/go procedures, LANDSCAPE, and five generated platform packages | Live end-to-end acceptance on the chosen client |

The ledger validates **submitted records**, not the identity of a human or the truth of a test. A trusted controller must verify authority and evidence before recording them.

Hooks may report observations, interruptions, and lifecycle events. A stop event, end of turn, or process exit is **not** an approval or proof of mission completion. No auto-go-on-stop hook or standalone SDK daemon is bundled. Missing mandatory host capability is a blocker, not permission to simulate three levels in one agent.

## Try this branch

Updating the upstream `prekuter/dryforge` installation does **not** install this fork. The extension is on **`feature/mission-session-orchestration`**, not `main`.

### Claude Code

Clone the branch, then launch from the project you actually want to work on:

```sh
git clone --branch feature/mission-session-orchestration --single-branch \
  https://github.com/contiloop/dryforge.git ~/dryforge-mission

cd /path/to/your-project
claude --plugin-dir ~/dryforge-mission/claude
```

This uses Claude Code's [local plugin testing interface](https://code.claude.com/docs/en/plugins). Check which Dryforge copy is loaded rather than mixing colliding installations. Explicitly invoke `/dryforge:mission` (or `/mission` if exposed by the host). Mission must pass its host preflight before delegating work.

### Codex

The generated plugin is in `codex/plugin/`; `.agents/plugins/marketplace.json` points to that directory. Register/install this checkout through the client's supported [local marketplace workflow](https://developers.openai.com/plugins/build/plugins), then explicitly invoke `$mission` once the skill is available. Local plugin installation and activation depend on the client; do not assume adding a marketplace alone finishes installation. Use a distinct test marketplace name when needed and avoid enabling colliding Dryforge copies.

Both packages retain the ordinary `ready`, `go`, and `migration` skills for manually supervised use. Package availability does not establish that a client can run Mission's persistent three-level workflow.

### Example mission request

```text
Help me turn useful insights from paper-reading conversations into source-linked Zotero notes
and highlights. First align with me on success criteria, delegated decisions, and finite limits.
Run one ready-go cycle per worker assignment and evaluate its evidence before choosing the next.
Reuse a worker only when session continuity and context headroom are confirmed.
Ask me before changing the goal, merging, deploying, spending money, or disclosing private data.
```

This is an example request, not a claim that the Zotero integration has been implemented or tested.

## Repository map

```text
src/skills/                         # canonical source
├── mission/
│   ├── SKILL.md                    # L1 mission loop
│   ├── references/
│   │   ├── intent-contract.md      # human intent and delegated authority
│   │   ├── cycle-contract.md       # L2 session, approvals, and handoff
│   │   └── host-adapter.md         # required runtime capabilities
│   └── scripts/mission_state.py    # local state ledger, not a session launcher
├── ready/
│   ├── SKILL.md                    # entrypoint and opt-in Mission connection
│   └── references/                 # preserved workflow, LANDSCAPE, research prompt, audits
├── go/
│   ├── SKILL.md                    # entrypoint and opt-in Mission connection
│   └── references/                 # preserved workflow, lifecycle, implementer/reviewer prompts
└── migration/                      # existing-project harness initialization

platform/                          # platform-specific build inputs
claude/ · codex/plugin/ · grok/     # generated packages
agent-plugin/ · antigravity/        # generated packages
docs/                              # Mission and MCP setup guides
ci/                                # state, contract, and package checks
```

Ready and go entrypoints force-load the complete `references/workflow.md`; their existing procedures were moved, not replaced with a summary. Mission/session rules extend them without removing their verification gates. Edit `src/skills/` and regenerate the packages rather than changing generated copies independently.

## Verification and development

From a Git checkout:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s ci -p 'test_*.py'
bash build/build.sh
# Commit intended changes and generated outputs before the clean-tree check:
python3 ci/verify.py
```

The tests exercise local state transitions, rejected approvals, session identity, lifecycle policy, and package consistency. They do **not** prove model compliance or live Claude/Codex execution. Before unattended use, validate same-ID ready/go, relayed questions, real L3 execution and independent review, L2 reuse and replacement, interruption recovery, and mission-level completion evidence. Details: [Mission guide](docs/MISSION.md).

## Credits and scope

Original Dryforge by **prekuter**, licensed under [Apache-2.0](LICENSE). This fork builds on that ready/go harness and the earlier LANDSCAPE/MCP changes. It retains the upstream **1.3.8** manifest version on this experimental branch; it is not an upstream release.

The earlier README snapshots are preserved in [English](README.upstream.md) and [Korean](README_ko.upstream.md). They describe the earlier baseline, not the Mission runtime contract. This English README and [한국어 README](README_ko.md) describe the fork's current architecture; the Japanese and Chinese README files have not yet been updated for Mission.
