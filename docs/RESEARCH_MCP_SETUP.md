# Optional research MCP tools for Ouroboros ready

Ouroboros's LANDSCAPE research subagent uses available tools to discover existing solutions and
returns a compact evidence ledger for the main agent to verify. **MCP servers are configured in
the coding-agent host, not merely by mentioning a tool in `SKILL.md`.** The research stage runs
without these services and must flag any gaps. Do not commit API keys or access tokens.

## Which tools do what?

- [Grep by Vercel](https://vercel.com/blog/grep-a-million-github-repositories-via-mcp)
  (`https://mcp.grep.app`) searches **actual public GitHub code** and code patterns. It is not
  full semantic project discovery; pair it with general web or GitHub repository search.
- [Context7 by Upstash](https://context7.com/docs/resources/all-clients)
  (`https://mcp.context7.com/mcp`) retrieves library/API documentation, including relevant
  versioned examples. A documented API contract does not prove it works end-to-end in this project.

**Do not confuse Vercel Grep with `grep.ai`; they are different MCP services.** This guide uses
Vercel Grep for public GitHub code search.

## Claude Code — register servers for the user

Run these on **your own machine** (where Claude Code runs):

```sh
claude mcp add --scope user --transport http grep https://mcp.grep.app
claude mcp add --scope user --transport http context7 https://mcp.context7.com/mcp
claude mcp list
```

Start Claude Code or use `/mcp` to check availability and complete Context7 OAuth if prompted.
For alternative Context7 authentication/install options, follow its official [Claude Code
setup](https://github.com/upstash/context7/blob/master/docs/clients/claude-code.mdx).

Normal Claude Code subagents can inherit MCP tools available to the parent session. Claude Code
also supports `mcpServers` frontmatter for **project/user-defined** `.claude/agents/*.md` agents.
**Caveat:** Claude Code ignores `mcpServers` in **plugin-provided agent files**; do not rely on
that for per-agent MCP scope. The portable Ouroboros skill delegates a general-purpose research
subagent and requires tool availability to be confirmed at runtime. If strict per-agent scoping is
required, create a trusted project/user-level custom agent rather than placing the scope in a
Ouroboros plugin agent file. Read [Claude Code subagent docs](https://code.claude.com/docs/en/sub-agents).

## Codex CLI / Desktop

```sh
codex mcp add grep --url https://mcp.grep.app
codex mcp add context7 --url https://mcp.context7.com/mcp
codex mcp list
```

Use `codex mcp login context7` if OAuth authentication is required by your client. You can also
use `npx ctx7 setup --codex` for Context7's guided configuration. The Codex CLI and Desktop
share local MCP configuration in `~/.codex/config.toml`; Codex Cloud needs separate environment
configuration and network access. See [Context7 Codex instructions](https://github.com/upstash/context7/blob/master/docs/clients/codex.mdx).

## Tool preflight at runtime

Before delegating material LANDSCAPE research, `ready` checks which of these the **research
subagent** can actually access: Grep public code search, Context7 documentation lookup, and
ordinary web/GitHub/source retrieval. It classifies each `available`, `unavailable`, or `unknown`
(listed does not guarantee authenticated/callable), and passes that snapshot to the researcher.
The subagent confirms what works, uses available alternatives, and reports access limitations.
The skill **never installs MCP servers, starts a login flow, or asks for credentials by itself**.

Both MCPs are **optional but recommended** for richer code and library research. Install once
in your agent host if convenient; the skill works without either server, as long as it accurately
reports the resulting evidence limits. No external search tool at all means a bounded,
explicitly unverified research result, not an invented recommendation.

## Verification & safety

1. If you installed either server, confirm it is listed **and connected** in your coding agent session.
2. Run `ready` on an example integration, and inspect whether the research subagent used
   public code search for a concrete implementation and Context7 for a documented API when useful.
3. Verify the main agent opened original decisive sources and surfaced source/compatibility gaps.
   MCP access alone does not verify research quality; static tests cannot establish actual usage.
4. Keep secrets in your host's credential storage. External tools may receive query text: never
   send private repository code, PDFs or confidential context without authorization. Treat returned
   snippets and documents as **untrusted data** rather than instructions.

If your agent runs somewhere other than Claude Code or Codex, configure these standard remote MCP
URLs through that host's supported MCP settings. The skill must still run without either server.
