# Probe: the shape of a list_events page (#436 S8)

Plan `docs/superpowers/plans/2026-11-03-run-time-resilience-2.md` Task 9. Run 2026-11-03 by the controller with the owner's OK: `calendar_fetch.sh` for one day, real `claude`, in a `.scratch/` clone of master, with one added line (scratch copy only) that kept the session's stream. The day had 13 events on 5 pages of 3; `calendar_tsv.py` wrote 13 rows. The raw stream was read for its shape only and deleted; nothing from it is committed.

## Where the page is

Each `list_events` result reaches the stream twice, and the two copies are equal:

- the `tool_result` block's `content`, a string holding the page as JSON (what `connector.text_json` reads);
- the line's top-level `tool_use_result.structuredContent`, the same page as an object (what `connector.structured` reads; `calendar_tsv.py` already walks the stream with `structured=True`).

`tool_use_result.content` is the same string again. The call's input keys were `startTime`, `endTime`, `timeZone`, `pageSize`, plus `pageToken` after the first page.

## The page

Top-level keys: `accessRole`, `defaultReminders`, `events`, `nextPageToken` (absent on the last page), `summary`, `timeZone`, `updated`.

Each event in `events` has `id`, `status` (`confirmed` on every event seen), `eventType` (`DEFAULT`, or `OUT_OF_OFFICE` on one), `summary` (the title), `start`, `end`, and fields the check ignores (`created`, `updated`, `creator`, `organizer`, `htmlLink`, `conferenceData`, `attendees`, `attachments`, `description`, `location`, `recurringEventId`, `originalStartTime`, reminders, visibility).

- **Timed event:** `start.dateTime` is ISO 8601 with a numeric offset (`2026-10-05T09:00:00-04:00` form), with `start.timeZone` beside it. An out-of-office event has the same form.
- **All-day event:** `start` and `end` have only `date`, and **`date` is a midnight UTC time, not a bare date**: `start.date` `2026-10-05T00:00:00Z`, `end.date` `2026-10-06T00:00:00Z` (the end is exclusive, the next day). `verify()` must take the first 10 characters as the date and must not convert it to the run's timezone, or a zone west of UTC moves the event to the day before.

Of the 13 events: 11 timed `DEFAULT`, 1 timed `OUT_OF_OFFICE`, 1 all-day; 13 distinct ids; every event had a `summary`.

## The fixture

`system/tests/fixtures/calendar/list_events_page.jsonl` is one stream line in the shape a real result line had (`type`, `message.content[0]` a `tool_result` for `tool_use_id` `t1`, `tool_use_result` with `content` and `structuredContent`, `session_id`, `timestamp`, `uuid`, `tool_result_meta`). Every value is invented: an all-day "Holiday", a timed "Standup" at 09:00-09:30 `-04:00`, and an "Out of office" at 17:00-18:00 `Z`, on 2026-10-05.
