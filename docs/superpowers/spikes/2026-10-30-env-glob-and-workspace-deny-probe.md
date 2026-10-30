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
- **Not checked:** paths outside the home directory, the Read tool (this probe tested Bash only), and an interactive session.
