# Research brief: a chat gateway in front of the Foundry

**Date:** 2026-10-11
**Status:** A research brief for a Work Order (`/order ask`, `--kind research`). Not a spec. It informs the Slack bridge grill (`2026-10-11-slack-bridge-design.md` §2) and does not block it.
**From:** the 2026-10-11 review ("who else solves these pieces").

## Question

Could an existing self-hosted chat gateway (OpenClaw, or another with the same shape: one process bridging Slack, Telegram, Signal and similar to an agent, with scheduled jobs and a periodic "anything need attention" check) serve as the Foundry's chat surface, with the Foundry's scripts as the only writers into the vault and the codebases, and would that be safer and cheaper than building the Slack bridge and later channels ourselves?

## Scope

- Candidates: OpenClaw (docs at `docs2.openclaw.ai`), Hermes Agent, and at most two others found through the first two's comparisons. Skip hosted services.
- For each: how a channel message reaches the agent and what the agent can do by default (the Foundry must deny shell and file access from chat); whether the gateway can be limited to calling a fixed set of commands (`slack_bridge.py fetch`, `now.py add`, `nightshift.py add` with a readiness check) and reading a fixed set of files; how its scheduled jobs and heartbeat compare with `foundry-*.timer` units; how it stores memory and whether that store would duplicate or fight the vault; its license, release cadence and security advisories in 2026; what it costs in processes, ports and credentials on the server.
- Compare against the Slack bridge spec: the same four notice events and the capture channel, delivered through the gateway, versus the model-free script. Name what the gateway adds (more channels, two-way chat, a heartbeat) and what it costs (an agent with a credential on the server, a second memory, another update stream).
- Sources: the Slack bridge spec and `system/scripts/run_headless.sh`, `lib_confine.sh` (read `template` under `code/` for the threat model), the candidates' documentation, at most eight web pages in all.
- Web hosts: `docs2.openclaw.ai`, `github.com`, `agentic-ai.readthedocs.io`.

## Done when

The findings note has: a table of candidates against the questions above; a verdict on whether any candidate can be confined to "fixed commands, fixed files" without forking it; a recommendation among three shapes (build the Slack bridge as specified; the gateway as a thin chat front over the Foundry's scripts; the gateway as the assistant with the vault as one of its tools) with the reason; and the questions a grill would have to settle.

## Output

`wiki/shared/summaries/ChatGatewayOptions.md`, a new note (`type: concept`, `partition: shared`, `tags: [foreman, research]`), `sources` holding vault wikilinks only, web pages under `## Web sources`.

## Queue line (for the Foreman session)

```
system/scripts/nightshift.py add --kind research --title "A chat gateway in front of the Foundry" --partition shared \
  --brief-file docs/superpowers/specs/2026-10-11-chat-gateway-research-brief.md \
  --output wiki/shared/summaries/ChatGatewayOptions.md \
  --host docs2.openclaw.ai --host github.com --host agentic-ai.readthedocs.io \
  --repo template
```
