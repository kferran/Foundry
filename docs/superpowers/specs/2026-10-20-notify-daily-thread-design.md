# Notices in a daily thread, one channel for both ways

**Date:** 2026-10-20. **Issue:** #293 part 2 (part 1, telemetry source failures, builds separately). **Builds on:** the Slack notices spec (`2026-10-11-slack-notices-design.md`), phase D captures (`2026-10-19-phase-d-intraday-design.md` §3.7).

## Owner decisions (2026-10-20, binding)

1. Every notice (brief, debrief, alerts, Work Orders) is a reply in the day's thread. The parent is the only top-level Foundry post.
2. The owner's replies in a daily thread become inbox drops only, with the notice they answer as context. No chat commands.
3. The day's parent is posted with the day's first notice. A quiet day has none; a missed day starts a new one.
4. Capture takes the owner's top-level posts and their replies in Foundry's daily threads. Notify's own posts are excluded by recorded ts, never by text.

## Config

`slack_notify_thread: daily | off`, default `off`. Off keeps today's behaviour: one top-level post per notice, no thread state, and the watch still refuses `capture_channel == slack_notify_channel`. An existing vault changes nothing until the owner turns it on, and turning it on is the act that says the notify channel is also the capture channel's home. Daily needs a channel ID (`C…`/`G…`): a DM's link names its `D…` conversation, never the user ID, so notify.sh refuses a user ID with exit 2.

## State

`system/logs/notify/thread.json`, separate from the cursor file (the cursor in `collected.json` replaces `state.json` whole, so a record written between the two sessions would be lost):

```
{"parents": {"<date>": "<ts>"}, "posts": {"<ts>": {"day": "<date>", "thread": "<parent ts or empty>", "text": "<message>"}}}
```

`posts` holds every post notify made, the parent included. The date is the vault's day (config `timezone`). Each write goes to a temp file and is renamed; entries older than 7 days are dropped on write. notify.sh holds `notify.lock` for the whole tick, so only one writer exists. The watch only reads the file.

## Posting

With threading on, a tick reads today's parent (`notify.py parent`). With none, a first confined session posts `Foundry updates <date>` with no `thread_ts`; the checker reads it back and records it as today's parent before anything else happens. A second session then posts the notice with `thread_ts` set to that parent. `--check` takes the same path, so its test message is threaded and recorded too.

notify.sh writes `thread_ts` into the arguments it hands the session; the session never chooses a channel or a thread. `notify.check` locks both: `channel_id` must be the configured channel; `thread_ts` must equal the parent notify.sh passed and is refused on the parent post; `reply_broadcast` and every other argument stay refused. Either breach is exit 7 (hold).

**Reading the ts back.** The send tool returns the message link. The checker takes the first `https://<workspace>.slack.com/archives/<channel>/p<16 digits>` in the call's result, for the configured channel, as `<10 digits>.<6 digits>`. When that link carries `thread_ts`, it must equal the expected parent. The ts is then recorded with the message text notify asked for.

## Failure modes

- **A session fails before posting** (no connector, timeout, connector error): as today, nothing moves; the next tick tries again. A missing parent is posted again then; a recorded parent is reused, so a failed notice session never makes a second parent.
- **The post landed but its result has no readable link** (the parent or a notice): exit 7, hold. Without the ts the post cannot be excluded from capture, and every later notice would be unrecorded too. The hold stops notices after one such post (at most one notice can become a drop), and the `[notify]` alert names the hold file. A notice post moves the cursor, as exit 7 does today; a parent post does not, so the notice goes out once the hold is gone.
- **The parent post fails:** no notice goes top-level as a fallback (decision 1); the notice waits for the next tick.
- **State lost:** the next notice starts a new parent. The watch then cannot exclude the old posts it no longer knows; the capture cursor has normally read past them by then (it trails by the 5-minute overlap).

## Capture (intraday extension)

The #287 refusal stays unless `slack_notify_thread` is `daily`; then `capture_channel == slack_notify_channel` is allowed and needs `watch_user_id` (exit 2 without it). In that case the capture query adds `from:<@watch_user_id>`, and the capture results in that channel are kept (the notify-channel skip stays for the other queries). Then, per message:

- a recorded Foundry ts is dropped (parent and replies alike);
- a top-level post is kept;
- a reply (its permalink carries `thread_ts`, per the 2026-10-19 watch probe) is kept only when that `thread_ts` is a recorded parent; a reply in any other thread is dropped.

A kept reply carries as context the latest Foundry post in its thread before it (Slack threads are flat, so "the notice it answers" is the one just above it), quoted under the message in the drop. Drops stay one file per tick in `capture_partition`. With capture and notify in different channels nothing changes.

## Unchanged

The brief and debrief embeds, the today file, chat triage (it still skips the notify channel), the alert table. The search results give `Message_ts` and the permalink; they show no separate parent field, so the parent comes from the permalink's `thread_ts`.

## Live checks for the owner

1. The real `slack_send_message` result holds the message permalink with `p<ts>` (nothing in the repo has recorded its shape).
2. `in:<#channel> from:<@owner>` returns thread replies, and their permalinks carry `thread_ts`.
