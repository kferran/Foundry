# Probe: how `claude -p` fails logged out and offline (2026-11-02, #436 S1)

**Why:** spec `docs/superpowers/specs/2026-11-01-run-time-resilience-design.md` §3.1 rests on a short `claude -p` check telling an outage apart from a bad input; plan Task 2 confirms how claude behaves before the code depends on it.

**Setup:** a throwaway folder under `.scratch/`, real `claude`, the sandbox off. The check is `timeout -k 10s 60s claude -p "Reply with the word ok." --tools "" --strict-mcp-config --no-session-persistence --output-format json </dev/null`. Logged out is an empty `CLAUDE_CONFIG_DIR`; offline is `HTTPS_PROXY` and `HTTP_PROXY` set to `http://127.0.0.1:9`.

| Case | Exit | Time | Output |
|---|---|---|---|
| check, working | 0 | 4 s | one result object, `is_error: false`, `result: "ok"` |
| check, logged out | 1 | 1 s | one result object, `is_error: true`, `result: "Not logged in · Please run /login"` |
| check, offline | 124 | 60 s (the timeout) | nothing: claude keeps retrying the API |
| a run's shape (`stream-json --verbose`, `timeout -k 30s 120s`), offline | 124 | 120 s (the timeout) | init lines, no result line |

**Verdict:**
- The success test holds as specified: exit 0 and `.is_error == false`. Both outage cases fail it, so the check tells them apart. The contingency in spec §6 (the check passing while logged out or offline) did not occur.
- A logged-out run ends 1 at once; an offline run ends 124 at `HEADLESS_TIMEOUT` (15 minutes by default), since claude retries until killed. Both are in the trigger list (1, 124). No other code appeared: `timeout` sends TERM first and claude exits on it, so 137 did not occur.
- Cost of an offline tick: the run holds `run.lock` until its timeout, then the check takes up to 60 s more; intake stops at the first exit 7, so one tick spends one timeout, not five.
