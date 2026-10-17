---
type: schema
schema_for: nightshift_item
folders: ["raw/work/nightshift/", "raw/personal/nightshift/", "raw/shared/nightshift/"]
fields:
  type: {kind: const, value: nightshift_item, required: true, readers: [system/scripts/vaultlib/schema.py]}
  id: {kind: string, required: true, readers: [system/scripts/vaultlib/nightshift_run.py]}
  partition: {kind: enum, values: [work, personal, shared], required: true, matches_folder: true, readers: [system/scripts/vaultlib/nightshift_check.py, system/scripts/vaultlib/nightshift_run.py]}
  kind: {kind: enum, values: [plan, research], required: true, readers: [system/scripts/vaultlib/nightshift_run.py, system/scripts/vaultlib/nightshift_sched.py]}
  state: {kind: enum, values: [queued, running, waiting_reset, delivering, done, blocked, failed, cancelled], default: queued, readers: [system/scripts/vaultlib/nightshift_sched.py, system/scripts/vaultlib/nightshift_run.py]}
  queued_at: {kind: datetime, required: true, readers: [system/scripts/vaultlib/nightshift_sched.py]}
  start: {kind: enum, values: [window, at, now], default: window, readers: [system/scripts/vaultlib/nightshift_sched.py]}
  start_at: {kind: datetime, readers: [system/scripts/vaultlib/nightshift_sched.py, system/scripts/vaultlib/nightshift_check.py]}
  budget: {kind: string, readers: [system/scripts/vaultlib/nightshift_sched.py, system/scripts/vaultlib/nightshift_run.py]}
  model: {kind: string, default: sonnet, readers: [system/scripts/vaultlib/nightshift_run.py]}
  repo: {kind: string, readers: [system/scripts/vaultlib/nightshift_run.py, system/scripts/vaultlib/nightshift_check.py]}
  base: {kind: string, readers: [system/scripts/vaultlib/nightshift_check.py, system/scripts/vaultlib/nightshift_run.py]}
  pr_base: {kind: string, default: master, readers: [system/scripts/vaultlib/nightshift_run.py]}
  plan: {kind: string, readers: [system/scripts/vaultlib/nightshift_check.py, system/scripts/vaultlib/nightshift_session.py]}
  tasks: {kind: string, readers: [system/scripts/vaultlib/nightshift_session.py, system/scripts/vaultlib/nightshift_check.py]}
  verify: {kind: list, of: string, readers: [system/scripts/vaultlib/nightshift_check.py, system/scripts/vaultlib/nightshift_run.py]}
  hosts: {kind: list, of: string, readers: [system/scripts/vaultlib/nightshift_run.py, system/scripts/vaultlib/nightshift_check.py]}
  output: {kind: string, readers: [system/scripts/vaultlib/nightshift_run.py, system/scripts/vaultlib/nightshift_check.py]}
  session_id: {kind: string, readers: [system/scripts/vaultlib/nightshift_run.py]}
  started_at: {kind: datetime, readers: [system/scripts/vaultlib/nightshift_run.py]}
  finished_at: {kind: datetime, readers: [system/scripts/vaultlib/nightshift_run.py]}
  attempts: {kind: int, min: "0", readers: [system/scripts/vaultlib/nightshift_run.py]}
  reset_at: {kind: datetime, readers: [system/scripts/vaultlib/nightshift_sched.py]}
  result: {kind: string, readers: [system/scripts/vaultlib/nightshift_run.py]}
  reason: {kind: string, readers: [system/scripts/vaultlib/nightshift_run.py]}
---
# Nightshift item
One Work Order, a unit of unattended work (Nightshift spec §4), written by `/order` and updated by `system/scripts/nightshift.py`. The body is the research brief (`kind: research`) or a free note. The runner writes only `state` and the runner fields, and never changes an item the user cancelled.
