# Intent conversation

Start from the user's words, corrections and the project itself. Build a model of what they are
trying to achieve, what they value, what constrains them and which facts they have given. Clarify
only uncertainties that would materially change the outcome; research technical facts instead of
asking for preferences. Use concrete examples rather than a questionnaire. Lead every question with
a recommended answer. Keep original excerpts beside your interpretation and distinguish what is
known, tentative and agreed.

## The proposal

A markdown file with these `##` sections (all required; `approve` refuses an incomplete one):

| Section | Content |
| --- | --- |
| Goal | the intended outcome in the user's terms |
| Completion criteria | observable evidence that the goal is met; one bullet per criterion |
| Constraints | what must hold (compatibility, style, platforms, data, time) |
| Priorities | what wins when criteria compete |
| Non-goals | what is explicitly out of scope |
| Delegated judgment | what L1 decides without asking; default: everything after approval |
| Workspace | absolute path of the target git root (one repository per run) |
| Limits | `max cycles: N`, `max stalled cycles: N`, `budget usd: <number>` or `budget usd: no cap` |

Add a line about Migration when the project is an existing codebase without documentation for
agents (L1 will run the installed Dryforge `migration` first).

The limits are the only thing that bounds L1 after approval, so they must be explicit. The run
stops when the cycle count or the stalled-cycle count reaches its limit, or when summed worker cost
exceeds the budget; the user can raise a limit by revising the proposal and approving again.

## Showing and recording

Every time the proposal is shown to the user, write it with `draft --proposal <file>` and then run
`shown`. Approval binds to the shown version: if the file changes afterwards, `approve` shows the
difference instead of approving.

## While the run is active or stopped

The user may keep talking. Clarification inside the agreed scope goes into the next worker message
or the next cycle with no new approval. A change to goal, completion criteria, constraints,
priorities, non-goals or limits is a proposal revision: write it with `draft` (which revises the
current run instead of starting a new one), run `shown`, and the user's next `approve` records the
amendment, applied at the next cycle boundary. The same path revises a stopped run, for example to
raise a limit; `approve` then resumes it. A different goal after a stop is a new run: `archive`
the stopped run first, then `draft`.
