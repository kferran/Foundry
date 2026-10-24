---
type: schema
schema_for: config
fields:
  health_thresholds: {kind: map, fields: {tick_success_pct: {kind: int, min: "0", max: "100"}, runs_published_pct: {kind: int, min: "0", max: "100"}, brief_by: {kind: time}, brief_kb: {kind: int, min: "1"}, now_kb: {kind: int, min: "1"}, now_open: {kind: int, min: "1"}, dismissed_pct: {kind: int, min: "1", max: "100"}, cost_cap_usd: {kind: int, min: "0"}, first_push_green_pct: {kind: int, min: "0", max: "100"}, headroom_pct: {kind: int, min: "0", max: "100"}}}
  health_defect_gates: {kind: map, of: date}
---
The health extension's keys (health scorecard spec §3.3). `health_thresholds` overrides a default, one key each: `tick_success_pct` (95), `runs_published_pct` (95), `brief_by` (06:30), `brief_kb` (8), `now_kb` (25), `now_open` (60), `dismissed_pct` (50), `cost_cap_usd` (unset: cost is trend only), `first_push_green_pct` (80), `headroom_pct` (2). `health_defect_gates` maps a defect class to the date its gate merged, such as `{C3: "2026-10-24"}`; a fix PR of that class merged after the date counts as a recurrence.
