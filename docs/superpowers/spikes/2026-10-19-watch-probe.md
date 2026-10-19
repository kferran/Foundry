# Phase D Task 1: the watch query probe

**Date:** 2026-10-19
**Plan:** `docs/superpowers/plans/2026-10-19-phase-d-intraday.md` Task 1.
**How:** I ran read-only calls from an interactive Claude Code session with the claude.ai Slack and Gmail connectors (the same connectors the confined sessions load). The owner chose this over a Work Order, because Work Order sessions run with `--strict-mcp-config` and refuse to start when MCP servers are present. The stream shape a confined `claude -p` session sees was probed for triage on 2026-10-16 (chat triage spec §3.2): the result is text JSON with no `structuredContent`. Names, IDs and message text below are placeholders.

## Slack: `slack_search_public_and_private`

| Probe | Input | Result |
|---|---|---|
| Two channels in one query | `filters: "in:<#C1> in:<#C2> after:<date>"`, `sort: timestamp`, `include_context: false`, `content_types: messages` | Works. The tool's own description says a repeated modifier is an OR. Results came back newest first, with a `cursor` for the next page. |
| The owner's own messages | `filters: "from:<@U_OWNER> after:<date>"` | Works across every channel type: channels, DMs and group DMs. The tool's description names the logged-in user's ID, but a session cannot rely on that, so the ID becomes a setting. `from:me` was not tried. |
| Group DMs | `channel_types: "mpim"`, `filters: "after:<date>"` | Works. A filter-only query still needs one filter, so the date filter stays. `is:mpim` is not needed. |
| Gmail sent mail | `search_threads`, `query: "in:sent after:YYYY/MM/DD"`, `view: THREAD_VIEW_MINIMAL` | Works. Each thread has `id`, `viewUrl` and `messages[]`, each message with `date`, `internalDate` (epoch ms), `labelIds` (`SENT`), `sender`, `toRecipients`, and, in the minimal view, `subject` and `snippet`. There is no body: the full text needs `get_thread`, a second tool. |

**Result block shape.** It is the same as triage's, plus two variants:

```
### Result N of M
Channel: #<name> (ID: C…)           | Channel: Group DM (ID: C…|G…) | Channel: DM (ID: D…)
Participants: <name> (ID: U…), …     (group DMs and DMs only)
From: <name> <email> (ID: U…)
Time: YYYY-MM-DD HH:MM:SS <tz abbrev>
Message_ts: <epoch.micro>
Permalink: [link](https://<workspace>.slack.com/archives/<channel>/p<ts>[?thread_ts=<ts>&cid=<channel>])
Text:
<message, may span lines; links as <url|label>>

---
```

A thread reply's permalink carries `thread_ts`; a top-level message's has none. `Time:` is in the workspace user's timezone, so the checker uses `Message_ts` for ordering and cursors.

## What changes in the plan

1. **The owner's Slack user ID is a setting.** `watch_user_id` (string, empty turns off the own-messages query) joins the extension's config. `/setup` can read it from the connector.
2. **Group DMs are a separate query** with `channel_types: "mpim"`, so the watch runs two queries: the channel list with repeated `in:`, and group DMs. Both keep `after:<date>`, plus the epoch `after` from the cursor, as triage does.
3. **Sent mail is classified from `subject` and `snippet`.** The minimal view returns no body. Reading the body needs `get_thread`, which would mean a second Gmail session per thread. v1 classifies from the snippet. A commitment deeper in a long mail is missed, and the live check (Task 11) shows whether that matters.
4. **The evidence link for mail** is the thread's `viewUrl`.
