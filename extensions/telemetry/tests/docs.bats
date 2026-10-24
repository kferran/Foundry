#!/usr/bin/env bats
# The telemetry extension's text: the /rca skill (#106), the brief section (#171), the setup steps (#94 A).
# Reads the repository's own files; the core helpers are three folders up.
load "$BATS_TEST_DIRNAME/../../../system/tests/helpers"

setup() {
  E="$(cd "$BATS_TEST_DIRNAME/.." && pwd)"
}

@test "/rca: read-only, nothing outward, the two scales, the humanizer and marker rules, the Now approval (#106)" {
  f="$E/skills/rca/SKILL.md"
  grep -qx 'name: rca' "$f"
  grep -qF 'Read-only on code: never edit code, run tests, or write outside the vault.' "$f"
  grep -qF 'Write nothing outward: never create or edit a Jira issue' "$f"
  grep -qF 'Run no live log query.' "$f"
  grep -qF '**Root-cause confidence (1–5):**' "$f"
  grep -qF '**Fix confidence (1–5):**' "$f"
  grep -qF '.claude/skills/humanizer/SKILL.md' "$f"
  grep -qF 'Proposed code never carries a teammate'"'"'s initials marker' "$f"
  grep -qF 'marked "meaning unconfirmed". Never guess a meaning.' "$f"
  grep -qF -- '--kind owed --statement "Review RCA draft: <note stem>" --evidence rca:<note stem>' "$f"
  grep -qF 'Never queue it yourself.' "$f"
  grep -qF 'Only with `--file` in the arguments' "$f"   # #333 Q8: no Review line by default; the draft is filed by hand
  grep -qF 'argument-hint: <raw/telemetry/<note>.md> [--file]' "$f"
  grep -qF 'from `extensions/telemetry/templates/rca.md`' "$f"
  grep -qF '**RCA.**' "$E/extension.md"
  grep -qF 'approved `/rca` drafts should be filed to Jira' "$E/extension.md"
  grep -qF 'rca_project: {kind: string}' "$E/schemas/config.md"
}

@test "/rca: the hotfix alert line and the within-minutes approval text (#106)" {
  grep -qF 'With `hotfix_candidate: true`, also run `system/scripts/alert.py rca "HOTFIX candidate: <title>"`.' "$E/skills/rca/SKILL.md"
  grep -qF 'approves filing, and the intake tick files it within minutes.' "$E/skills/rca/SKILL.md"
}

@test "the brief section lists the groups new first, capped per environment, from the prep's table (#171)" {
  f="$E/brief/section.md"
  grep -qF 'FROM v_production_error WHERE status = '"'"'active'"'"' OR resolved_at >= ' "$E/brief/prep.sh"
  grep -qF 'mock, partition, escalate, escalated_at FROM v_production_error' "$E/brief/prep.sh"
  grep -qF -- "-u -d '-24 hours' +%Y-%m-%dT%H:%M:%S+00:00" "$E/brief/prep.sh"
  grep -qF 'At most 10 rows per environment' "$f"
  grep -qF 'Skip groups with `covered` true.' "$f"
  grep -qF '**Escalated**, across all environments: active groups with `escalate` set and `last_seen` in the last 24 hours, by `count`' "$f"
  grep -qF 'At most 3 Escalated rows, then "and N more"' "$f"
  grep -qF 'A printed Escalated row is not repeated under New or Recurring' "$f"
  grep -qF 'each **Escalated** row whose `escalated_at` is in the last 24 hours, at most 3 per brief' "$f"
  grep -qF 'Telemetry <environment>: persistent, <service> on <exception>; decide an owner (proposed: read-only analysis by the Workcell with telemetry)' "$f"
  grep -qF -- '--evidence <note path>' "$f"
  grep -qF 'first an **Escalated** block' "$E/extension.md"
  grep -qF 'seen over at least 24 hours and is still firing' "$E/extension.md"
}

@test "setup checks each source, keeps the token out of chat, and documents the empty filter value (#94 A)" {
  f="$E/extension.md"
  grep -qF 'extensions/telemetry/scripts/telemetry_fetch.py --check <name>' "$f"
  grep -qF 'Never ask for the token in chat. Check it is mode 0600.' "$f"
  grep -qF 'Skipped on a client.' "$f"
  grep -qF 'A filter value of `""` selects the rows that lack the attribute' "$f"
  grep -qF 'An empty filter value (`adx_filter: {deployment.instance: ""}`) selects the rows that lack that attribute' "$f"
  grep -qF 'An empty value, `{deployment.instance: ""}`, selects the rows that lack the attribute' "$E/templates/telemetry-source.example.md"
}
