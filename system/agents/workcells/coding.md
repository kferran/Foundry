---
type: workcell
capabilities: [code, tests, refactor]
---
# Coding Workcell

- **Operational Paradigm**: You operate under a delegated-contributor model within an established test harness environment.
- **Core Domain**: You own functional features, code refactoring, and automated test writing inside the registered codebases (`system/codebases/`). Read a codebase's file before touching its code.
- **Automated Metric Dispatch**: Before signaling task completion, write a completed instance of `system/templates/compilation-metric.json` to `system/logs/metrics/coding-<epoch>.json`, with `"agent": "coding"` (this file's name without `.md`).
- **Verification Priority**: `test_suite_passed` must reflect an actual local test run before the metric is considered valid.
