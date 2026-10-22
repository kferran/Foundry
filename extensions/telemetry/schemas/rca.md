---
type: schema
schema_for: rca
folders: ["wiki/work/rca/", "wiki/personal/rca/"]
reserved_tag: "true"
fields:
  type: {kind: const, value: rca, required: true}
  title: {kind: string, required: true}
  partition: {kind: enum, values: [work, personal], required: true, matches_folder: true}
  created_at: {kind: date, required: true}
  source: {kind: string, required: true}
  codebase: {kind: string}
  environment: {kind: string}
  rc_confidence: {kind: int, min: "1", max: "5", required: true}
  fix_confidence: {kind: int, min: "1", max: "5", required: true}
  hotfix_candidate: {kind: bool, default: "false"}
  status: {kind: enum, values: [draft, approved, filed, rejected], default: draft}
  ticket: {kind: string}
  tags: {kind: list, of: string}
  provenance: {kind: list, of: {kind: enum, values: [headless, interactive, session]}}
---
# RCA
A root-cause analysis of one production error group (RCA spec, #106), written by `/rca`. `source` is the error-group note's path in `raw/telemetry/`. `rc_confidence` is how sure the diagnosis is; `fix_confidence` is derived from it with the fix's scope and blast radius (1–5 each, scales in `extensions/telemetry/skills/rca/SKILL.md`). Its Ticket draft section is filed to Jira only after the owner ticks its Now line; the intake tick then sets `status: approved`, the filer sets `ticket` and `status: filed`, and a dropped line sets a draft to `status: rejected`.
