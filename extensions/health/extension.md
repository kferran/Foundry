---
name: health
contract: 1
description: "A weekly health scorecard of the platform and the factory in Monday's brief, and a breach line on other days"
requires: []
brief: true
units: []
alert_tags: []
allow: []
deps: []
index_ignore: []
budget:
  values: {HEALTH_GH_SECONDS: 90}
  steps:
    - "brief 1 - HEALTH_GH_SECONDS"  # health.py score: every gh call shares this budget; the rest waits for the next brief
---
**Health.** Every brief, the prep runs `extensions/health/scripts/health.py score <date>`, which scores the 7 days ending yesterday and appends one line per metric to `system/logs/health/<YYYY-MM>.jsonl` (`date`, `metric`, `value`, `threshold`, `state`, `text`). It reads only files that exist and GitHub; it runs no model and writes nothing else (health scorecard spec §3). On a Monday the brief prints the whole scorecard under 🩺 Health; on other days it prints one `⚠️ health:` line under Pipeline per metric that breaks its threshold, and nothing when all pass.

What it measures, and from where:
- **Source ticks ok:** per fetch log (`system/logs/<name>-<YYYY-MM>.jsonl` with an `exit` on each line, less `runs`, `smoke` and `usage`), the share of lines with exit 0 (a logged skip is exit 0). A source with no line in the window is left out.
- **Headless runs published:** the run ledger's lines with a publish status, `published` or `noop` against the rest.
- **Brief on time:** each workday with a published brief that finished by `brief_by` in the vault's timezone.
- **Brief size, Now page size:** the newest briefing before today, and each partition's `Now.md`, in KB.
- **Now open lines, inflow and closures:** open lines on both Now pages; lines dated `since` in the window against lines closed in it (page and `now-archive/`), with how many closed on evidence.
- **Dismissed share:** closed lines marked `[-]` against all closed, per evidence host (mail, Slack, GitHub, other, none), for a host with at least 5 closed.
- **Claude cost per day:** `total_cost_usd` of each headless run's `claude.json`, plus each fetch log line's `cost_usd`; the line names the sources it counted.
- **Sync blocked:** `[sync] sync blocked` alerts in the window, plus one while `system/logs/sync-blocked` exists.
- **Headroom:** core lines, core schemas, `CLAUDE.md` lines and brief prompt words against the caps their tests set. Core lines and brief words break under `headroom_pct` left; schemas and `CLAUDE.md` are ratchets held full on purpose, so they break only over their cap.
- **Factory** (only with `gh` logged in and a GitHub `template_remote`): fix PRs per `defect:` class and recurrences after a class's date in `health_defect_gates`; the share of merged PRs green on their first commit's check runs (each PR read once, then cached in the history); review-fix commits per merged PR.

A metric whose files are missing or unreadable shows `unavailable`, never zero or ok. A trend metric (cost, dismissed share, review fixes) compares this week with the median of the 4 weeks before and breaks at 1.5 times it; until 4 weeks of history exist it shows `trend` and never breaks. Each gh call has a 15-second limit and all of them share `HEALTH_GH_SECONDS`; PRs not read by then count on a later day.

**Setup.** Add `health` to `extensions` in `system/config.md`. Optionally tune `health_thresholds` (see `extensions/health/schemas/config.md`) and fill `health_defect_gates` with each class's gate date as gates land. Run `system/scripts/vault_index.py validate system/config.md`, then `extensions/health/scripts/health.py score $(date +%F) --dry-run` and report its lines. Nothing to renew: it uses no connector.
