# Work Order confinement: what a session can read, where it can send it, and what runner state it can change

**Date:** 2026-10-30
**Status:** draft, for the owner's review
**Grill:** 2026-10-29/30, two rounds, every recommendation approved (§7). Source: in-flight plan `docs/superpowers/2026-10-28-in-flight-plan.md` phase 3; issues #317, #318, #319, #320, #321, #326, and #301 S9.
**Builder check:** 2026-10-30, seven questions and five wrong claims; settled as my calls in §7 except two for the owner (§8)
**Blueprint:** none: changes to the Work Order runner, its CLI, the publish gate and intake; no new feature shape.
**Lane:** feature, three pull requests (§6). Each touches a safety surface (the Work Order runner, the publish gate, `.claude/settings.json`), so the owner merges each.

## 1. Why

A Work Order session runs unattended with Bash (sandboxed) and, for research, WebFetch to the order's hosts. Six audit findings share that surface:

- **#326:** the sandbox's `/**/.env` and `/**/.env.*` deny globs mask nothing on Linux, so a session can read any `.env` under the home directory.
- **#317:** `nightshift.py add:*` is pre-allowed, so any interactive session can queue a research order naming any host. With #326, a session can read a key and queue an order that sends it anywhere.
- **#318:** research hosts are checked only by a name regex (`nightshift_check.py:25`); a name that resolves to a loopback, private, link-local or metadata address passes.
- **#319:** a session is not denied the other orders' `nightshift-*` folders in `order_workspace`, nor the runner's bare `nightshift-runner.git`.
- **#320:** runner state lives in `system/logs/nightshift/`, inside the vault, where any interactive session can write it without a prompt: `items/<id>/delivery.json` can redirect a push, `alerts.json` can hide an alert, and the health file's usage readings drive the 5-hour hold.
- **#321:** a plan order's `--base` is a branch name resolved at tick (`nightshift_run.py:254`), so the code a session runs on can change after the owner queued it.
- **#301 S9:** a research report's Stale claims section becomes a session digest in `raw/<p>/notes/` (`nightshift_deliver.py:266-293`), so text from the web edits the wiki through ingest without the owner seeing it.

## 2. Goals, non-goals, anti-goals

- **Goals:** a session cannot read `.env` files, other orders' folders or runner state; nothing the owner did not approve sends data to a new host; a resolved internal address is refused; nothing a session or an interactive session writes in the vault steers the runner; a plan runs on the commit the owner queued; web-sourced stale claims reach ingest only after the owner ticks them.
- **Non-goals:** a host allowlist in config (wait until research orders are frequent); signing template updates (#301 S1, documented in #426); per-partition read denies for headless runs (#301 S10, accepted in #426); defending against DNS that changes between the check and the fetch.
- **Anti-goals:** a prompt on plan orders; a tick that runs sessions after a failed `.env` walk; a stale-claims line a headless run can tick.

## 3. Design

### 3.1 Research orders prompt (#317)

- `nightshift.py research` is a new subcommand taking `add`'s research flags (`--title`, `--partition`, `--repo`, `--brief-file`, `--output`, `--host`, the timing flags, `--budget`, `--model`). It writes the same queue note with `kind: research`.
- `add` keeps `--kind` for compatibility, accepts only `plan`, and refuses `research` with `use nightshift.py research for a research order`.
- Every subparser sets `allow_abbrev=False`.
- `.claude/settings.json` gets an `ask` list with `Bash(system/scripts/nightshift.py research:*)` and `Bash(system/scripts/nightshift.py requeue:*)` (§3.6). An ask rule prompts in auto mode too. Per the grill, the owner adds these lines in the PR; the build leaves them out and the PR body names them.
- `/order`, the Foreman persona, the research Workcell and FOUNDRY.md switch from `add --kind research` to `research`.

### 3.2 Hosts that resolve inside the network (#318)

A new `nightshift_check.resolve_problems(hosts)` resolves a research order's `hosts` with `socket.getaddrinfo` and returns `host <h> resolves to <a>, an internal address` when any address is not global (`ipaddress.ip_address(a)`: `not is_global or is_multicast`). It is not part of `screen()`, which runs no network and runs on every pass of the tick loop (`nightshift_check.py:158-159`). `research` calls it at add and refuses the order on a problem or on a name that does not resolve. The runner calls it once per order just before the session starts: an internal address fails the order with its Needs-you line; a name that does not resolve leaves the order queued for the next tick with one log line (my call: a DNS outage should not fail an approved order). The codebase's `order_hosts` are owner config and are not resolved (they may be wildcards such as `*.npmjs.org`, or an internal registry on purpose). Known ceiling: DNS can change between the check and the fetch.

### 3.3 Literal deny paths (#326, #319)

- **`.env` files, once per tick** before any session starts: an `os.walk` of the home directory, of every registered codebase's `path` and of `order_workspace` (each once, when outside home), not following symlinks, pruning directories named `node_modules`, `.cache`, `.git`, `.venv`, `venv` and `__pycache__`, collecting files named `.env` or `.env.*`. The walk has a 120 s cap. If it hits the cap or raises, the tick starts no session and raises one `[orders]` alert a day: `could not list .env files: <reason>; no Work Order ran`. A path holding `(`, `)` or `*`, which a `Read(//…)` rule cannot carry (`nightshift_session.py:49-50`), is handled the same way, with the path named.
- **Other orders, at each session start:** a tick runs for hours and refills its slots, so a list fixed at tick start would miss folders made later. The builder first probes whether a session profile can deny `order_workspace` as a whole and allow the session's own folder inside it (the sandbox supports an allow-within-deny for reads; whether settings expose it is unverified). If it can, that is the rule. If not, the list is every entry in `order_workspace` named `nightshift-*` except the session's own `nightshift-<id>`, plus `nightshift-runner.git` and `state/` (§3.4), each created first if missing, with every queued order's folder created before the list is built. Ceiling of the fallback: an order queued after a session started is not in its list.

`_deny` adds these literal paths to what it returns, so `ss.profile` puts them in `denyRead` and mirrors them as `Read(//…)` rules, as it does for the vault today. The `/**/.env` globs stay. An upstream report on the glob goes to the Claude Code repository, worded without vault details.

### 3.4 Runner state outside the vault (#320)

Runner state that the runner reads back moves to `<order_workspace>/state/`: `items/`, `alerts.json` and `health-<date>.json`. The daily report `system/logs/nightshift/<date>.md` (read by `brief_prep.sh` and `debrief_prep.sh`) and the monthly ledger `system/logs/nightshift-YYYY-MM.jsonl` stay in the vault. One helper gives the state directory; every reader uses it: `nightshift_report.py`, `nightshift_run.py`, `triage.py` (the health files' usage, which `intake.held()` reaches through `triage.hold`) and `notify.py:243` (`items/*/outcome.json` for Work Order notices). On its first tick after the update, the runner moves the old `items/`, `alerts.json` and `health-*.json` into `state/` when `state/` does not hold them yet, so orders in flight carry on. Sessions are denied `state/` (§3.3).

### 3.5 A plan runs on the commit the owner queued (#321)

- `add` records `base_sha` in the queue note: `git rev-parse <base>^{commit}` in the codebase, or `git ls-remote <template_remote URL> refs/heads/<base>` for `template` (the config URL the runner already fetches from, `nightshift_run.py:244`).
- Before the first clone (attempt 1), `_clone` resolves the base again. If it differs from `base_sha`, the order goes to `blocked` with a Needs-you line: `the base <base> moved since <id> was queued (<old7> → <new7>); read the plan at the new base, then run nightshift.py requeue <id>`. A reused clone is not checked again.
- An order queued before this change has no `base_sha` and runs as today. Research orders stay unpinned at add; they pin their code commit at the first run, as today.
- Ceiling: an order added on a client records the client's commit, and the server resolves the base in its own clone. A server clone that lags blocks the order, and the line names both commits.

### 3.6 `requeue` (#321)

`nightshift.py requeue <id>` sets a `blocked` or `failed` order back to `queued`, records the base's current commit as `base_sha` (plan orders), and clears what the runner counts for a fresh order. Any other state is refused with its state named. It prompts through the ask rule (§3.1). The three Needs-you messages that say "queue {id} again" (`nightshift_run.py:630, 637, 647`) name `requeue <id>` instead.

### 3.7 Stale claims wait for a tick (#301 S9)

- `stale_claims_input` writes the digest to `raw/<p>/held/<id>.stale-claims.md` instead of `raw/<p>/notes/`, and adds one `owed` Now line with no evidence: `Review <n> stale claims from research <id> before they reach the wiki: raw/<p>/held/<id>.stale-claims.md`.
- Intake's Now step (under `run.lock`) releases each held file whose line the owner closed with `[x]` into `raw/<p>/notes/`, where ingest takes it as today. A line closed with `[-]` moves the file to `raw/<p>/archive/`, never ingested. `stamp()` marks both `ticked` today (`now.py:143-144`), so the step reads the box. The runner's lines carry no `via`, so they never expire (`now.py:513`): a held file waits until the owner acts. The step finds the closed line wherever now.py keeps closed lines.
- A held file with no line (the add failed: lock busy or line refused, `nightshift_run.py:601-604`) gets the add retried at each intake Now step until it lands.
- A `shared` research order's line goes on the `work` Now page (`now.validate` refuses `shared`); the line names only the file path.
- The publish gate refuses a run that adds, removes or changes a Now line naming `raw/<p>/held/`: today the brief may publish `Now.md`, and the gate screens only new open lines (`publish.py:375-384`), so a brief could tick one.

## 4. Tests

Each test fails before its change.

- **§3.1:** `add --kind research` and an abbreviated flag are refused; `research` writes the note `add` wrote before; a docs test that `/order` and the Workcell name `research`.
- **§3.2:** a host resolving to `127.0.0.1`, `10.0.0.1`, `169.254.169.254` and `::1` is refused at add (stub resolver) and fails the order at session start; an unresolvable host is refused at add and leaves the order queued at session start; a codebase's `order_hosts` are not resolved.
- **§3.3:** a session's settings list a seeded `.env` under a fake home and under a codebase outside it, a pruned `node_modules/.env` is absent, a sibling `nightshift-*` folder made after the tick started, `nightshift-runner.git` and `state/` are denied, its own folder is not; a walk past its cap, or a path with `(`, starts no session and alerts once.
- **§3.4:** state is written under `state/`; an old `system/logs/nightshift/items/` is moved on the first tick; the daily report stays in the vault; triage reads usage from `state/`.
- **§3.5:** a base moved after add blocks the order with the line; an unmoved base runs; a note without `base_sha` runs.
- **§3.6:** `requeue` on a blocked order queues it with the new `base_sha`; on a `done` order it is refused.
- **§3.7:** a research delivery writes `held/` and the Now line; `[x]` releases it to `notes/`; `[-]` archives it; a failed line add is retried; a `shared` order's line lands on `work`; the gate refuses a run that ticks the line.

## 5. Docs

FOUNDRY.md's Security model and Work Orders sections: the literal deny list, the DNS check, where runner state lives, `research` and `requeue` and their prompts, `base_sha`, and the held stale claims. A change file per PR.

## 6. Delivery

1. **PR A, runner confinement:** §3.2, §3.3, §3.4, and the upstream report.
2. **PR B, the CLI:** §3.1, §3.5, §3.6. The owner adds the two ask lines before merging.
3. **PR C, stale claims:** §3.7.

Each raises the core cap with its measured count, recorded beside the cap. A live acceptance run in a throwaway clone runs one research and one plan order after PR A and PR B.

## 7. Grill

Round 1 (2026-10-29, approved 2026-10-30):

1. #317: an ask rule on research adds; plan orders stay prompt-free.
2. #318: resolve hosts at add and at each tick; refuse loopback, private, link-local and metadata addresses.
3. #326: literal `.env*` paths in each session's `denyRead`, plus an upstream report.
4. #319: deny sibling workspaces by literal path.
5. #320: move runner state under `order_workspace/state/`.
6. #321: record the base commit at add; hold the order if it moved; the owner queues it again.
7. S9: stale claims become a Now line the owner approves before ingest.
8. S10: accept and document (#426).
9. S1: revisit signing on a second template contributor, or a vault on a machine the owner does not run (#426).

Round 2 (2026-10-30, approved):

1. A `research` subcommand with an ask rule; `add` refuses research; abbreviations off.
2. The owner adds the settings lines in the PR.
3. Walk the home directory once per tick with pruning; a failed walk runs no sessions and alerts.
4. Move `items/`, `alerts.json` and the usage readings; keep the daily report and the monthly ledger.
5. `requeue <id>`, which prompts and records the current base.
6. The held digest waits in `raw/<p>/held/`, is released on a hand tick and archived on expiry, and the gate refuses headless changes to its line.

My calls: an unresolvable host at session start leaves the order queued; `nightshift-runner.git` and `state/` are denied with the sibling folders; `requeue` also gets an ask rule, since a missing allow rule does not prompt in auto mode; the walk's cap is 120 s; the whole `health-<date>.json` moves, since its usage readings and the held line are in one file.

Builder check (2026-10-30), settled as my calls: the DNS check is its own step at add and at session start, outside `screen()`, and skips owner-set `order_hosts` (round 1 named research hosts); the sibling deny is rebuilt at each session start, after a probe for a workspace-wide deny; the `.env` walk also covers codebases and the workspace outside home, and an unrepresentable path fails closed; `notify.py` and `intake.held()` read state through the helper; the `template` base pins through the `template_remote` URL; `[x]` releases and `[-]` archives, and runner lines never expire, which replaces round 2's "archived on expiry" (no runner line can expire); a failed line add is retried; a `shared` order's line goes on `work`; research orders stay unpinned at add; a lagging server clone blocks an order, named as a ceiling.

## 8. Open for the owner

1. **Vault files that steer the runner.** An interactive session can write a queue note in `raw/<p>/nightshift/` with sandboxed Bash and no prompt, and FOUNDRY.md says such a note runs. That skips the §3.1 and §3.6 ask rules. Codebase notes (`order_hosts`, `order_install`) and the session profiles in `system/nightshift/` are open the same way.
2. **What `requeue` resets.** A blocked or failed order may still have its clone, `before.json` and `elapsed`.
