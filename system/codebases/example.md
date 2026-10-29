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

`/setup` writes one file like this per codebase you register, as `system/codebases/<name>.md`, tracked like the rest of the vault. This example is committed, ships `default: "false"` so it never collides with your own default, and is skipped by `codebases_list`.

Optional Work Order keys, set by you in the frontmatter: `order_pr: "github:<owner>/<repo>"` (or `bitbucket-link`), `order_hosts` and `order_plugins`; `order_toolchain: ["~/.nvm/versions/node/<version>/bin", "~/.nvm/versions/node/<version>/lib"]`, the directories the toolchain really lives in (nvm's `npm` and `pnpm` are symlinks from `bin` into `lib`), bound read-only into the sealed verify and first on the plan session's PATH; and `order_install: "pnpm install --frozen-lockfile --ignore-scripts"`, one command run once before the verify commands, with the network open.
