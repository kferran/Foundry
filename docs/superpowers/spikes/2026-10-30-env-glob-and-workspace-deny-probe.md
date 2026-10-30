# Probe: anchored `.env` globs and a workspace-wide read deny

**Date:** 2026-10-30. **Binary:** Claude Code 2.1.311 on Linux (bwrap sandbox). **For:** the Work Order confinement spec (`docs/superpowers/specs/2026-10-30-work-order-confinement-design.md` §3.3, #326, #319).

**Setup:** a throwaway folder under `.scratch/`, with `claude -p … --restricted --strict-mcp-config --settings <file> --permission-mode dontAsk --tools Bash --model haiku`, launched from `<P>/s`. The settings file allowed Bash, enabled the sandbox with no network, and set:

```json
"filesystem": {"denyRead": ["~/**/.env", "~/**/.env.*", "<P>/ws"], "allowRead": ["<P>/ws/own"]}
```

Each command ran as its own Bash call, using `tac` so the sandbox and not the permission layer decides.

| Command | Result |
|---|---|
| `tac public.txt` (control) | its marker |
| `tac .env` | `Permission denied` |
| `tac sub/.env.local` | `Permission denied` |
| `tac <P>/ws/own/y.txt` | its marker |
| `tac <P>/ws/other/x.txt` | `No such file or directory` |
| `ls <P>/ws` | `own` only |
| `printf … > late/.env`, then `tac late/.env` (made during the session) | `Permission denied` |

## Findings

- The sandbox honours an anchored `.env` glob (`~/**/.env`, `~/**/.env.*`), and applies it to each command, so a file made after the session starts is masked too. #326's `**/.env*` and `/**/.env*` matched nothing because, on Linux, `denyRead` wildcards work only after the first directory name (Claude Code sandboxing docs).
- `allowRead` re-opens one folder inside a `denyRead` folder. The other folders under the denied one disappear (`ls` lists only the allowed one).
## The Read tool (second probe, the same day)

The same setup with `--tools Read` (and `Read,Bash` for the last case). Permission rules named in each case; the sandbox pair as above throughout.

| Case | Working directory | Rules | `.env` | `sub/.env.local` | own folder | sibling folder |
|---|---|---|---|---|---|---|
| S1 | `<P>/s` | allow `Read`, `Read(//<P>/ws/own/**)`; deny `Read(~/**/.env)`, `Read(~/**/.env.*)`, `Read(//<P>/ws/**)` | denied | denied | **denied** | denied |
| S2 | `<P>/s` | allow `Read(//<P>/s/**)`, `Read(//<P>/ws/own/**)`; deny the two `.env` rules | denied | denied | outside the working directory | outside the working directory |
| S3 | `<P>/s` | allow `Read`; deny the two `.env` rules | denied | denied | outside the working directory | outside the working directory |
| Production shape | `<P>/ws/own` | allow `Read`, `Bash`; deny `Read(//<home>/**/.env)`, `Read(//<home>/**/.env.*)` (the absolute form the runner writes) | denied (Read and Bash) | denied (Read and Bash) | read (Read and Bash) | outside the working directory (Read); `No such file or directory` (Bash) |

- An anchored `.env` rule holds for the Read tool, in both the `~/` and the absolute `//` form, and a `denyRead` glob still masks a `.env` inside an `allowRead` folder.
- A deny rule outranks an allow rule: a `Read(//<workspace>/**)` deny refuses the session's own folder however it is allowed back (S1). So the workspace deny is a sandbox entry only.
- `--restricted`, which every Work Order session runs with, keeps the Read tool inside its working directory ("is outside …; --restricted confines …"), so a sibling order's folder is refused with no rule.
- **Not checked:** Glob and Grep, paths outside the home directory, and an interactive session. The live acceptance run of PR A covers Glob, Grep and a seeded `.env` in a real order.

## Upstream report (draft, for the owner to file)

> **Title:** Warn when a sandbox `denyRead` entry or a `Read()` deny rule starts with a wildcard on Linux
>
> On Linux, a `sandbox.filesystem.denyRead` entry such as `**/.env*` or `/**/.env`, and a permission rule such as `Read(//**/.env)`, mask nothing: the docs say wildcards work only after the first directory name. The settings load without a word, so a user who wrote the rule believes `.env` files are hidden from the session. An anchored form (`~/**/.env`) works. Could settings loading print a warning for an entry whose first segment is a wildcard, as it does for other invalid settings?
>
> Seen on Claude Code 2.1.311, Linux (bubblewrap).
