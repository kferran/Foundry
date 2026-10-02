---
type: codebase
name: "example"
path: "~/code/example"
partition: "work"
default: "false"
stack: ["vue3", "dotnet"]
search_globs: ["*.vue", "*.ts", "*.js", "*.cs", "*.csproj"]
layers:
  ui: "example-ui/"
  api: "Example.Api/"
---
Free-form notes for agents: conventions, gotchas, owners.

`/setup` writes one file like this per codebase you register, as `system/codebases/<name>.md` (gitignored). This example is committed, ships `default: "false"` so it never collides with your own default, and is skipped by `codebases_list`.
