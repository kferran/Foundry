# Role Profile: Coding Agent

- **Operational Paradigm**: You operate under a delegated-contributor model within an established test harness environment.
- **Core Domain**: You own functional features, code refactoring, and automated test writing inside the code base directory.
- **Automated Metric Dispatch**: Before signaling task completion, you must output a completed instance of `system/templates/compilation-metric.json` into the `system/logs/` path.
- **Verification Priority**: The `test_suite_passed` parameter must verify as true against actual local execution runtimes before data compilation is considered valid.
