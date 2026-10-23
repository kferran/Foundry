# Health scorecard: metrics for the factory and the platform

**Date:** 2026-10-23
**Status:** grilled (owner, 2026-10-23); draft for the owner
**Grill:** 2026-10-23, see `## Grill` below.
**Builder check:** 2026-10-23, three questions, all settled as my calls in §6: the brief prompt's word cap, where gate dates live, how first-push CI is read.
**Blueprint:** none: a deterministic reader of local logs and GitHub that writes a brief section; it runs no connector session and no model.
**Lane:** feature, one plan (`plans/2026-10-23-health-scorecard.md`), built after the factory's F1 (grill Q5).

## Grill

Owner's idea (2026-10-23): "identify metrics of the system to make sure we're maintaining a healthy factory and platform". Grilled with `grilling`, three rounds, every recommendation taken:
1. **Worth building:** yes. Health is seen only when someone surveys or reads logs. Each of these was found days late: the Now page at 54 KB against 25, 159 open lines with 15 ever closed on evidence, 26 failed triage ticks, two briefs rejected over the Now page, and the RCA filer at 4 attempts and 0 tickets (live usage survey, 2026-10-21).
2. **For whom:** the owner first; the build agents second (headroom tells them a gate is near); other vault owners get it with the template.
3. **Without it:** not acceptable. The factory plan's own measure ("no defect class recurs after its gate exists") stays uncounted, and ad-hoc surveys keep finding problems late.
4. **Smallest version:** a deterministic script that reads existing logs and GitHub, a weekly scorecard, and one brief line when a metric crosses its threshold. No new logging (except session cost, item 12) and no dashboard.
5. **Displaces:** builds right after F1, whose retrofits change the sources it measures; ahead of the Now page work.
6. **Thresholds:** fixed where a target is known (sizes, success rates, an on-time brief); trend-only for cost and the dismissed share until 4 weeks of history exist.
7. **Surface:** a 🩺 Health section in Monday's brief, and one line under Pipeline on any day a threshold breaks. No new note type; history in `system/logs/health/<YYYY-MM>.jsonl`.
8. **Home:** an extension, `health`, off until listed. It reads core logs and uses the existing brief and debrief section hooks; core changes nothing.
9. **Factory half:** runs only when `template_remote` is on GitHub and `gh` is logged in; otherwise the section shows the platform half alone.
10. **CI gates:** none new. The scorecard reports the headroom of the gates that exist.
11. **Thresholds table:** §3.3, held in the extension's config so the owner can tune it.
12. **Cost coverage:** F1's shared `lib_fetch.sh` logging records each connector session's cost (one field; added to #306), so the cost metric covers every retrofitted source; until then the cost line names the sources it counts.

## 1. Problem

The vault writes plenty of records: the run ledger, each fetch's log, the smoke log, the alerts, the Now page and its archive, the briefings, the usage log, and on GitHub the pull requests with their `defect:` labels and CI runs. Nothing reads them together. Every health finding so far came from a survey someone ran by hand (2026-10-11, 10-17, 10-20, 10-21), and the factory plan's pass/fail measure has no counter.

## 2. Goals, non-goals, anti-goals

- **Goals:** one weekly scorecard of about 12 metrics, each with its number, its threshold and a pass or breach mark; a daily breach line in the brief; a month of history for trends; every number reproducible from the files it names.
- **Non-goals:** new logging beyond item 12; a dashboard or artifact; CI gates; measuring what no log records (`/query` results, interactive `/rca` quality).
- **Anti-goals:** a number the model writes (the brief prints the prep's lines verbatim); a metric with no threshold and no trend (it would be read once and ignored); a scorecard longer than one screen.

## 3. Design

### 3.1 The extension

```
extensions/health/
  extension.md          manifest: config keys, brief and debrief true, alert tag {tag: health, severity: brief}
  schemas/config.md     health_thresholds (map), health_defect_gates (map: class -> gate date)
  scripts/health.py     metrics, scorecard, breaches, history
  brief/prep.sh, brief/section.md
  tests/
```

`health.py score <date>` computes every metric for the 7 days ending the day before `<date>` and appends one JSON line per metric to `system/logs/health/<YYYY-MM>.jsonl` (`date`, `metric`, `value`, `threshold`, `state`: `ok`, `breach` or `trend`). It writes nothing else. The brief prep runs it every day; on Monday the section file holds the whole scorecard, on other days only the breached lines.

### 3.2 Metrics

Platform (this vault's logs):

| Metric | Read from |
|---|---|
| Source tick success, per source | each fetch's `system/logs/<source>_fetch-<YYYY-MM>.jsonl` (exit 0 or a logged skip counts as ok); the smoke log for sources with no fetch log |
| Headless runs published | `system/logs/runs-<YYYY-MM>.jsonl`: `publish.status` published or noop against rejected, conflict and quarantined |
| Brief on time | the run ledger's `brief` line `finished_at` on each workday, against 06:30 in the vault's timezone |
| Brief size, Now page size | the newest briefing's bytes; `wiki/<partition>/Now.md` bytes |
| Now open, inflow, closures, closed on evidence | the Now pages and `now-archive/` notes (`since` dates and close stamps, `closed: ticked` against an evidence close) |
| Dismissed share per source | archived lines closed `[-]` against all closed, grouped by evidence host (mail, Slack, GitHub, none) |
| Claude cost per day | `total_cost_usd` in `system/logs/runs/<id>/claude.json`, plus each fetch log's cost field where it has one (§1 item 12) |
| Sync blocked | `system/logs/sync-state.json` and `[sync]` alert lines |

Factory (GitHub, item 9):

| Metric | Read from |
|---|---|
| Fix PRs per defect class, and recurrences | merged PRs with a `defect:` label; a recurrence is one merged after its class's date in `health_defect_gates` |
| First-push CI green | for each PR merged in the window, the check runs on its first commit (`gh api .../commits/<sha>/check-runs`) |
| Review-fix commits per PR | commits in each merged PR whose message names a review fix ("review fix", "final review", "address review") |
| Budget and ratchet headroom | core script lines and schemas against `vault_integrity.bats`'s caps; `CLAUDE.md` lines against 50; brief prompt words against 2,500; each `conformance.bats` allowlist's length |

### 3.3 Thresholds (defaults in `health_thresholds`)

| Metric | Healthy |
|---|---|
| Source tick success, per source, 7 days | ≥ 95% |
| Headless runs published, 7 days | ≥ 95% |
| Brief by 06:30 | every workday |
| Brief / Now page size | ≤ 8 KB / ≤ 25 KB |
| Now open lines | ≤ 60, and closures ≥ inflow over 7 days |
| Dismissed share per source | trend only; any source ≥ 50% is flagged |
| Claude cost per day | trend only (4 weeks), then an owner cap |
| Sync blocked | 0 |
| Defect recurrence after a gate | 0 |
| First-push CI green | ≥ 80% |
| Budget and ratchet headroom | flag under 2% |

A trend metric breaches when it is worse than the median of the 4 weeks before by more than half (cost, dismissed share); with fewer than 4 weeks of history it shows `trend` and never breaches.

### 3.4 Surface

- **Monday brief:** a `## 🩺 Health` section, last before 📝 Notes, holding the prep's lines verbatim: one line per metric, `✅` or `⚠️`, the value, the threshold and the week before.
- **Other days:** each breached metric is one line under Pipeline, `⚠️ health: <metric> <value> (healthy <threshold>)`, and nothing when all pass.
- **Debrief:** nothing (the brief is the daily surface).
- **Alerts:** none; a breach is a brief line, never a Slack push (grill item 7).

## 4. Tests and validation

- pytest per metric against fixture logs (a passing week, a breaching week, missing files counting as unavailable, never as zero).
- The factory half with a stub `gh` (the debrief's PR tests use the same pattern), and its absence when `gh` or a GitHub `template_remote` is missing.
- The trend rule: no breach under 4 weeks of history; a breach at 1.5× the median.
- bats: the brief prep writes the whole scorecard on a Monday and only breaches on a Tuesday; the brief prompt stays within its word cap (§6).
- Live: the first Monday scorecard after the owner turns it on, checked by hand against the 2026-10-21 survey's method for three metrics.

**Done when:** a Monday brief carries the scorecard, a breached metric shows on the next weekday's brief, and three metrics match a hand count.

## 5. Out of scope

- Logging what nothing records today (triage thread counts per tick; per-command outcomes).
- A dashboard or chart (an artifact can read the history later).
- Changing any gate (grill item 10).

## 6. Builder check

1. **The brief prompt is at 2,495 of its 2,500 words.** The section prompt must say where the lines go, which costs about 15 words. My call: the plan's first task trims `brief.md` by at least that, cutting repetition and keeping every rule; the cap stays. If no cut keeps every rule, that task stops and asks the owner to raise the cap.
2. **Where gate dates live.** The factory plan defines a recurrence against "its gate", but no file records when each class's gate landed. My call: `health_defect_gates` in the extension's config, filled by hand as gates land (F3 is the first), with the class's PR as a comment.
3. **First-push CI.** The check runs on a PR's first commit are one `gh api` call per PR. My call: read only PRs merged in the window, at most 50 a week, and cache each PR's answer in the history file so a PR is read once.
