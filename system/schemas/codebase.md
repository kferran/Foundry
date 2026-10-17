---
type: schema
schema_for: codebase
folders: ["system/codebases/"]
fields:
  type: {kind: const, value: codebase, required: true, readers: [system/scripts/vaultlib/schema.py]}
  name: {kind: string, required: true, readers: [system/scripts/vaultlib/scope.py, system/hooks/lib_memory.sh]}
  path: {kind: path, required: true, must_exist: warn, readers: [system/scripts/vaultlib/scope.py, system/scripts/vaultlib/index.py, .claude/commands/impact.md]}
  partition: {kind: enum, values: [work, personal, shared], required: true, readers: [system/scripts/vaultlib/scope.py, system/hooks/lib_memory.sh]}
  default: {kind: bool, default: "false", unique_true: true, readers: [system/scripts/lib_config.sh]}
  stack: {kind: list, of: string, readers: []}
  search_globs: {kind: list, of: string, required: true, readers: [.claude/commands/impact.md]}
  layers: {kind: map, of: string, readers: [system/scripts/vaultlib/index.py, .claude/commands/impact.md]}
  order_hosts: {kind: list, of: string, readers: [system/scripts/vaultlib/nightshift_run.py]}
  order_plugins: {kind: list, of: string, readers: [system/scripts/vaultlib/nightshift_run.py]}
  order_pr: {kind: string, readers: [system/scripts/vaultlib/nightshift_check.py, system/scripts/vaultlib/nightshift_deliver.py, system/scripts/lib_prep.sh]}
  order_toolchain: {kind: list, of: string, readers: [system/scripts/vaultlib/nightshift_check.py]}
  order_install: {kind: string, readers: [system/scripts/vaultlib/nightshift_check.py, system/scripts/vaultlib/nightshift_run.py]}
  nightshift_hosts: {kind: list, of: string, readers: [system/scripts/vaultlib/nightshift_run.py]}
  nightshift_plugins: {kind: list, of: string, readers: [system/scripts/vaultlib/nightshift_run.py]}
  nightshift_pr: {kind: string, readers: [system/scripts/vaultlib/nightshift_check.py, system/scripts/vaultlib/nightshift_deliver.py, system/scripts/lib_prep.sh]}
---
# Codebase
One registered codebase, produced by `/setup` discovery and inspection. The body holds free-form notes for agents.

`nightshift_hosts`, `nightshift_plugins` and `nightshift_pr` are the old names of `order_hosts`, `order_plugins` and `order_pr`. They are still read when the new key is absent; the new key wins when both are set.

`order_toolchain` lists the directories (`~` allowed) that hold the codebase's toolchain executables; a Work Order's sealed verify binds them read-only and puts them first on its PATH, and the plan session's PATH starts with them too. `order_install` is one shell command that installs the project's dependencies; it runs once, before the verify commands, in the same private checkout, with the network open. Neither has an old name.
