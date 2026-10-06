---
type: schema
schema_for: nightshift_item
folders: ["raw/work/nightshift/", "raw/personal/nightshift/", "raw/shared/nightshift/"]
fields:
  type: {kind: const, value: nightshift_item, required: true}
  id: {kind: string, required: true}
  partition: {kind: enum, values: [work, personal, shared], required: true, matches_folder: true}
  kind: {kind: enum, values: [plan, research], required: true}
  state: {kind: enum, values: [queued, running, waiting_reset, delivering, done, blocked, failed, cancelled], default: queued}
  queued_at: {kind: datetime, required: true}
  start: {kind: enum, values: [window, at, now], default: window}
  start_at: {kind: datetime}
  budget: {kind: string}
  model: {kind: string, default: sonnet}
  repo: {kind: string}
  base: {kind: string}
  pr_base: {kind: string, default: master}
  plan: {kind: string}
  tasks: {kind: string}
  verify: {kind: list, of: string}
  hosts: {kind: list, of: string}
  output: {kind: string}
  session_id: {kind: string}
  started_at: {kind: datetime}
  finished_at: {kind: datetime}
  attempts: {kind: int, min: "0"}
  reset_at: {kind: datetime}
  result: {kind: string}
  reason: {kind: string}
---
# Nightshift item
One unit of unattended work (Nightshift spec §4), written by `/nightshift` and updated by `system/scripts/nightshift.py`. The body is the research brief (`kind: research`) or a free note. The runner writes only `state` and the runner fields, and never changes an item the user cancelled.
