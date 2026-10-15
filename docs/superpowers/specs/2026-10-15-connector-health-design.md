# Connector health: say which credential expired, how to renew it, and show every source on one line

**Date:** 2026-10-15
**Status:** Draft for the owner's review (feature lane: it changes alerting and the brief command text).
**Plan:** phase 1 item 9 of `docs/superpowers/2026-10-15-next-phase-plan.md` (live finding L1). Builds on #184 (timer liveness, unit drift), merged.

## 1. Problem

Live use, 10-05 to 10-14: every connector recovery was manual, and the owner learned of most failures by reading the brief.

| Date | What broke | What the system said |
|---|---|---|
| 10-13 | Jira token expired | `[handoffs] Jira fetch failed (exit 6): the connector returned an error: …`; brief: "the Jira connector returned an error (if it persists, reconnect Atlassian at claude.ai)" |
| 10-12, 10-13 | Drive search failed | `[meetings] Drive fetch failed (exit 1): …` |
| 10-13 | Slack notices failed | `[notify] Notices failed (exit 3)` |
| 10-12, 10-13 | Network key for the telemetry host lapsed | 23 failed runs logged as `network: URLError`; one `[telemetry]` alert after the third |
| 10-10 to 10-13 | No mail or chat connector in headless runs | "Mail and chat skipped" in every brief, under Communication Debt |

On master (merge of #202):

1. **Only telemetry knows what an auth failure is.** `vaultlib/http.py` classes HTTP 401/403 as `auth`, `kusto.py` classes an expired `az login` as `auth`, and `telemetry_run.py` alerts at once on `auth`. The claude.ai connector fetches (calendar, meetings, Jira, triage, notify, RCA) go through `lib_connector.sh`, which has exit codes (1 claude error, 3 no connector, 4 timeout, 6 connector error) and no class: an expired connector token and a Drive outage are both exit 6, and an expired `claude` login is exit 1.
2. **`telemetry_fetch.py --check` drops the class**, so the smoke check prints `telemetry: failed: <reason>` and cannot tell `run az login` from a dead network.
3. **The smoke check alerts once a day per source**, with the script's last line as the reason, and no way to renew.
4. **The brief shows a failed source in up to three places**: Unavailable Sources (`prep_unavailable` in `lib_prep.sh`), the Pipeline alerts, and the Communication Debt skipped line. Mail and chat, which no headless run can reach, take a line every day.

## 2. Decisions

- **One failure class, everywhere.** Every fetch's failure reason starts with one of `auth:`, `network:`, `timeout:`, `connector:`, `claude:` or `other:`.
  - `lib_connector.sh` `connector_outcome` sets `CONNECTOR_CLASS` from the exit and the reason text. Exit 3 is `auth` (no connector reachable, which is how a disconnected connector shows). Exit 6 is `auth` when the connector's error text matches `401|403|unauthori[sz]ed|forbidden|expired|reconnect|invalid_grant|token`, else `connector`. Exit 4 is `timeout`. Exit 1 is `claude` when claude's error result says it is logged out or out of credit (`/login`, `invalid api key`, `credit`), else `other`. Exit 127 is `claude`.
  - Each connector fetch prints `<name>: <class>: <reason>` on failure. Exit codes do not change.
  - `telemetry_fetch.py --check` prints the class it already has: `telemetry_fetch: <src>: auth: run az login`.
- **The smoke check names the credential and the renewal.** A failed source whose reason is `auth:` prints `<src>: expired: <credential>; renew: <command>` and alerts once a day per credential (key `expired <credential>`), so two expired credentials make two alerts. The credentials and commands are a table in `smoke_check.sh`:

  | Credential | Sources | Renew |
  |---|---|---|
  | `claude` login | every connector source | `claude` then `/login` on the server |
  | Google connector (Calendar, Drive, Gmail) | calendar, meetings, triage | reconnect it at claude.ai, Settings, Connectors |
  | Atlassian connector | handoffs, rca | reconnect it at claude.ai, Settings, Connectors |
  | Slack connector | notify | reconnect it at claude.ai, Settings, Connectors |
  | Azure CLI | telemetry (ADX) | `az login` on the server |
  | Sentry token | telemetry (Sentry) | write a new token to `~/.config/foundry/sentry.token` (mode 0600; `sentry.token_path()`) |

  A `network:` failure prints `<src>: unreachable: <host>` and, when the same source failed the same way at the previous smoke check, alerts once a day "unreachable since <date>; check the VPN or network route to <host>". The 10-12 telemetry case needed that line.
- **One Sources line in the brief.** `brief_prep.sh` writes `system/logs/inputs/<date>/sources.md`: one line per source the role has (calendar, meetings, handoffs, triage, telemetry per source, dtcc, notify), `ok`, `off` or `failed: <class>: <reason> (since <date>)`. The "since" date comes from `system/logs/smoke-<YYYY-MM>.jsonl`: the first of the consecutive failed readings. Sources the brief does not fetch (triage, notify, dtcc) take the smoke check's reading of the same morning.
  - `brief.md` replaces the Unavailable Sources bullets with one line: `Sources: <n> ok` followed by each source that is not ok, with its class and since date, and an expired credential's renewal. When every source is ok: `Sources: all <n> ok.`
  - Mail and chat move into that line as `mail and chat: off (no connector in headless runs)`. The Communication Debt skipped line goes.
  - Pipeline alerts that repeat a Sources entry (a fetch failure the line already shows) are left out of Pipeline.
- **Alert severity.** When the alert-tags registry (`2026-10-14-alert-tags-design.md`) lands, `expired` and `unreachable` lines are `now`: the owner can renew within the hour. Until then they are `[smoke]` alerts, which Slack notices already send.
- **#176 is confirmed live.** The calendar fetch listed 11 events on Claude Code 2.1.300 on 10-15 (feOS); nothing more to do for it here.

## 3. Changes

- `system/scripts/lib_connector.sh`: `CONNECTOR_CLASS` in `connector_outcome`.
- `calendar_fetch.sh`, `meetings_fetch.sh`, `jira_fetch.sh`, `triage_fetch.sh`, `notify.sh`, `rca_file.sh`: the class prefix on the printed reason and in their alert lines.
- `system/scripts/vaultlib/telemetry_run.py`: `--check` prints the class.
- `system/scripts/smoke_check.sh`: the credential table, the `expired` and `unreachable` lines, the per-credential alert key.
- `system/scripts/brief_prep.sh`, `lib_prep.sh`: `sources.md`; `prep_unavailable` callers keep working and feed it.
- `.claude/commands/brief.md`: the Sources line in Morning Alignment, the Communication Debt and Pipeline sentences.
- `FOUNDRY.md`: the smoke check paragraph and the brief's sections.

## 4. Tests

- bats (`connector.bats`): `connector_outcome` classes a 401 tool error as `auth`, a 500 as `connector`, exit 3 as `auth`, a timeout as `timeout`, a logged-out claude result as `claude`.
- bats (`smoke.bats`): an `auth:` failure on calendar prints `calendar: expired: Google connector; renew: …` and alerts once; calendar and handoffs both expired make two alerts; a `network:` telemetry failure on two consecutive checks alerts once with "unreachable since"; one failure does not.
- pytest (`test_telemetry_run.py`): `--check` prints the class.
- bats (`prep.bats`): `sources.md` lists every source of the role with ok, off or failed and the since date from the smoke log.
- bats (`commands.bats`): `brief.md` reads `sources.md`, has the one-line Sources rule, and no longer has the Communication Debt skipped line.

Each fails before the change. Bound tools: bats, pytest, the gate, and the live acceptance steps (the brief command text changes).

## 5. Out of scope

- Renewing anything automatically. Every renewal needs the owner's login.
- Mail and chat in headless runs. That is the chat-gateway research brief and the Slack captures grill.
- The alert-tags registry itself (#158).
