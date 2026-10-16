---
type: schema
schema_for: config
fields:
  rca_project: {kind: string}
  rca_issue_type: {kind: string, default: "Bug"}
  rca_labels: {kind: list, of: string}
  rca_assignee: {kind: string}
  rca_extra_fields: {kind: map, of: string}
---
`rca_project` (a Jira project key) turns on filing approved `/rca` drafts to the handoffs extension's `handoffs_site`, as `rca_issue_type` (default `Bug`) with `rca_labels`, the project's required fields in `rca_extra_fields` (Jira field id to value; a value written as JSON is sent as JSON, #175) and, when set, the Atlassian account ID `rca_assignee` (RCA spec §3.4); filing stays off while `rca_project` is empty.
