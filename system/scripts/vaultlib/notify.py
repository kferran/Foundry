"""Slack notices (Slack notices spec): what happened since the last notice, as one message, and the check of the
confined session that posts it. Events come from files scripts write (the run ledger, the alerts, Work Order
outcomes); no note text from wiki/ is sent."""
import json
import re
import shlex
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from . import alerts as alertsmod, frontmatter, now as nowmod
from .redact import redact
from .stream import blocks

STATE = Path("system/logs/notify/state.json")
LINE_MAX = 300
MESSAGE_MAX = 4000
TRIAGE_TEXT = re.compile(r"(?<=\[triage\] )(\d+) new: .*$")
# Retries of an inbox file, a digest or a meeting file, which end poisoned or quarantined: that outcome goes out,
# the retries stay in the alerts file (#162). Every other "will retry" line goes out once a day.
INTERIM = re.compile(r"\[intake\] (?:ingest of raw/inbox/.+ failed \(exit \d+\); will retry"
                     r"|digest .+ failed \(exit \d+\); (?:will retry|retrying one at a time)"
                     r"|meeting import of .+ failed \(.*\); will retry"
                     r"|ingest \d{8}T\d{6}-ingest-[0-9a-f]{4}(?:: publish rejected or empty \(.*\)| failed \(exit \d+\)))$")
POISONED = re.compile(r"(?<=\[intake\] )poisoned (?P<when>.+?): (?P<origin>.+?) → (?P<dest>.+)$")
WIKILINK = re.compile(r"\[\[[^\[\]]+\]\]")
ORDER_ID = re.compile(r"\d{4}-\d{2}-\d{2}-[a-z0-9-]+")  # nightshift_check.ID
# What scripts write and redaction leaves alone (#162, #157): a vault path standing on its own (never inside a URL
# or glued to other text), a run id and a Work Order id. What follows one (":", "?", ",") is redacted as usual.
SAFE = re.compile(r"(?<![^\s(\"'`])(?:(?:raw|wiki|system|briefings|meetings)/[\w./-]+"
                  r"|\d{8}T\d{6}-[a-z]{1,16}-[0-9a-f]{4}(?![\w-])|\d{4}-\d{2}-\d{2}-[a-z0-9-]+(?![\w-]))")
NAME = re.compile(r"[\w.-]{1,64}")
POST_ARGS = {"channel_id", "message", "unfurl_app_links"}
EXTRA_TEXT = 500  # a posted text this much longer than the collected one carries text nobody collected
LIMIT = re.compile(r"usage limit|rate limit|limit reached|hit your limit", re.I)
OPEN_NEEDS = ("owed", "draft")


class Fail(Exception):
    def __init__(self, code, reason):
        super().__init__(reason)
        self.code, self.reason = code, reason


def config(vault) -> dict:
    path = Path(vault) / "system" / "config.md"
    return (frontmatter.parse(path.read_text(encoding="utf-8")).data or {}) if path.is_file() else {}


def prefix(connector: str) -> str:
    """The MCP tool prefix of a connector as `claude mcp list` names it."""
    return "mcp__" + re.sub(r"[^A-Za-z0-9]+", "_", connector)


def _git(vault, *args) -> str:
    r = subprocess.run(["git", "-C", str(vault), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def link(vault, rel: str) -> str:
    """A link to a path in the vault: with notify_links "obsidian", an obsidian:// URI that names no vault (#157);
    otherwise a GitHub file link, or "" when origin is not on github.com."""
    if config(vault).get("notify_links") == "obsidian":
        return "obsidian://open?file=" + quote(rel.removesuffix(".md"), safe="")
    m = re.match(r"^(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?/?$", _git(vault, "remote", "get-url", "origin"))
    branch = _git(vault, "symbolic-ref", "--short", "HEAD")
    return f"https://github.com/{m.group(1)}/blob/{branch}/{quote(rel)}" if m and branch else ""


def _load(vault) -> dict:
    try:
        return json.loads((Path(vault) / STATE).read_text())
    except (OSError, ValueError):
        return {}


def commit(vault, cursor: dict) -> None:
    path = Path(vault) / STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cursor, indent=1, sort_keys=True))
    tmp.replace(path)


def _new_lines(path: Path, offset: int) -> tuple:
    """(complete lines after offset, the offset after the last complete line)."""
    data = path.read_bytes()
    end = data.rfind(b"\n") + 1
    if end <= offset:
        return [], offset
    return data[offset:end].decode("utf-8", errors="replace").splitlines(), end


def _counts(vault, day: str) -> str:
    needs = waiting = 0
    for partition in nowmod.PARTITIONS:
        for line in nowmod.read(vault, partition).split("\n"):
            m = nowmod.LINE.match(line)
            if m and m.group("mark") == " ":
                needs += m.group("kind") in OPEN_NEEDS
                waiting += m.group("kind") == "waiting"
    path = Path(vault) / "system" / "logs" / f"alerts_{day}.md"
    alerts = sum(1 for x in path.read_text(errors="replace").splitlines() if x.startswith("- ")) if path.is_file() else 0
    return f"{needs} need you, {waiting} waiting, {alerts} alerts today"


def _run_event(vault, rec: dict):
    cmd = rec.get("command")
    if cmd not in ("brief", "debrief"):
        return None
    day = str(rec.get("started_at") or rec.get("finished_at") or "")[:10]  # the briefing is named for the start
    name = cmd.capitalize()
    if rec.get("exit") != 0:
        return f"{name} {day} failed (exit {rec.get('exit')})"
    if cmd == "brief":
        return " ".join(x for x in (f"Brief {day}: {_counts(vault, day)}", link(vault, f"briefings/{day}.md")) if x)
    return " ".join(x for x in (f"Debrief {day} is ready", link(vault, f"briefings/{day}.debrief.md")) if x)


def _redact(text: str) -> str:
    """redact() with SAFE paths and ids carried through (#162, #157): the high-entropy guess would eat a whole path.
    The named secret shapes run over the whole text first; inside a path, each piece between "/", "." and "-" still
    gets the high-entropy guess, so a secret used as a file name is caught and a slugged digest name is not."""
    # ponytail: a high-entropy secret that itself holds "-" or "." is split into pieces under 32 characters and
    # passes inside a path; the named shapes (sk-, ghp_, xox…, JWT) still catch the common ones.
    text, out, pos = redact(text, high_entropy=False)[0], [], 0
    for m in SAFE.finditer(text):
        out += [redact(text[pos:m.start()])[0], re.sub(r"[^/.-]+", lambda p: redact(p.group(0))[0], m.group(0))]
        pos = m.end()
    return "".join(out + [redact(text[pos:])[0]])


def _cut(text: str) -> str:
    text = " ".join(_redact(text).split())
    return text if len(text) <= LINE_MAX else text[:LINE_MAX - 1] + "…"


def _slack(text: str) -> str:
    """Slack's control characters escaped (#162): a name a model or a dropper chose cannot @-mention or format."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _gate_reason(vault, dest: str) -> tuple:
    """(run id, the publish gate's first reason) of the last failed run of a poisoned input, found by the hash in
    its sidecar (an inbox run's ledger names the staged copy, not the origin) and read from the run's publish.json.
    The reason stops before its detail (a shrink guard's detail quotes note headings) and before any path (a
    partition-wall reason names the other partition's note); a note name outside NAME is left out."""
    run = ""
    try:
        sha = json.loads((Path(vault) / f"{dest}.origin.json").read_text())["sha256"]
    except (OSError, ValueError, LookupError, TypeError):
        return run, ""
    for path in sorted((Path(vault) / "system" / "logs").glob("runs-*.jsonl"))[-2:]:
        for line in path.read_text(errors="replace").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("run_id") and rec.get("exit") and sha in (rec.get("input_sha256") or []):
                run = str(rec["run_id"])
    try:
        problem = json.loads((Path(vault) / "system/logs/runs" / run / "publish.json").read_text())["problems"][0]
        parts = str(problem["reason"]).split(": ")[:2]
        reason = ": ".join(p for p in parts[:1] + [x for x in parts[1:] if "/" not in x])
        stem = Path(str(problem["path"])).stem
        return run, (f"{stem}: " if NAME.fullmatch(stem) else "") + reason
    except (OSError, ValueError, LookupError, TypeError):
        return run, ""


def _alert(vault, line: str):
    """An alert line as sent, or None for a step the intake will retry (#162: Slack gets the outcome). Triage lines
    carry mail text (senders and asks a model wrote), so only their count goes out: text from outside the vault
    never reaches the posting session's prompt. A poisoned input says what, why and what to run."""
    body = line[2:]
    if INTERIM.search(body):
        return None
    m = TRIAGE_TEXT.search(body)
    p = POISONED.search(body)
    if p:
        _, why = _gate_reason(vault, p.group("dest"))
        name = shlex.quote(p.group("dest").rsplit("/", 1)[-1])   # one input, no run lookup (quarantine spec §2)
        head = body[:p.start()] + f"{p.group('origin')} was not published"
        tail = (f"; quarantined {p.group('when')}. Fix the cause, then run system/scripts/intake.py "
                f"--retry-input {name}")
        # The command must survive the line cap whole: the gate reason gives way first.
        room = LINE_MAX - len("Alert ") - len(head) - len(tail) - len(" ()")
        why = why if len(why) <= room else (why[:room - 1] + "…" if room >= 20 else "")
        body = head + (f" ({why})" if why else "") + tail
    elif m:
        body = body[:m.start()] + f"{m.group(1)} new"
    return _cut("Alert " + body)


def _sans_time(event: str) -> str:
    return re.sub(r"^Alert \d{2}:\d{2}:\d{2} ", "Alert ", event)


def collect(vault, now: datetime) -> tuple:
    """(new event lines, the cursor after them). The first run returns no events and a cursor at the end of every
    source, so turning notices on sends no backlog."""
    vault = Path(vault)
    logs = vault / "system" / "logs"
    state = _load(vault)
    first = not state
    cursor = {"ledger": dict(state.get("ledger", {})), "alerts": dict(state.get("alerts", {})),
              "outcomes": list(state.get("outcomes", [])), "sent": dict(state.get("sent", {}))}
    runs, orders, alerts = [], [], []
    months = {now.strftime("%Y-%m"), (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")}
    for month in sorted(months):
        path = logs / f"runs-{month}.jsonl"
        if not path.is_file():
            continue
        new, end = _new_lines(path, 0 if first else int(cursor["ledger"].get(path.name, 0)))
        cursor["ledger"][path.name] = end
        for line in [] if first else new:
            try:
                event = _run_event(vault, json.loads(line))
            except ValueError:
                continue
            if event:
                runs.append(event)
    ext_tags = alertsmod.extension_tags(vault)
    for day in sorted({(now - timedelta(days=1)).strftime("%F"), now.strftime("%F")}):
        path = logs / f"alerts_{day}.md"
        if not path.is_file():
            continue
        new, end = _new_lines(path, 0 if first else int(cursor["alerts"].get(path.name, 0)))
        cursor["alerts"][path.name] = end
        sent = cursor["sent"].setdefault(day, [])
        for x in [] if first else new:
            if alertsmod.severity(x, ext_tags) != "now":   # the rest waits for the brief; [notify] never (alert tags spec §2)
                continue
            event = _alert(vault, x)
            if event is None or _sans_time(event) in sent:  # an alert repeated each tick while a problem lasts goes out once a day
                continue
            sent.append(_sans_time(event))
            alerts.append(event)
    for path in sorted((logs / "nightshift" / "items").glob("*/outcome.json")):
        try:
            out = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        oid = str(out.get("id") or path.parent.name)
        if oid in cursor["outcomes"]:
            continue
        cursor["outcomes"].append(oid)
        if not first:
            detail = str(out.get("result") or next(iter(out.get("needs") or []), "") or out.get("reason") or "")
            # The id is written by a script in a fixed shape: never redacted (#157).
            head = f"Work Order {oid if ORDER_ID.fullmatch(oid) else _cut(oid)} {_cut(str(out.get('state')))}"
            output = str(out.get("output") or "")  # a research item's own note: no lookup by name (#157)
            url = link(vault, output) if WIKILINK.fullmatch(detail) and output else ""
            orders.append(head + _cut(f": {Path(output).stem}") + f" {url}" if url
                          else head + (_cut(f": {detail}") if detail else ""))
    keep = {f"alerts_{d}.md" for d in ((now - timedelta(days=1)).strftime("%F"), now.strftime("%F"))}
    cursor["alerts"] = {k: v for k, v in cursor["alerts"].items() if k in keep}
    cursor["sent"] = {k: v for k, v in cursor["sent"].items() if f"alerts_{k}.md" in keep}
    return [_slack(e) for e in runs + orders + alerts], cursor


def message(vault, events: list) -> tuple:
    """(the text, the event lines it carries): one bullet per event, cut at MESSAGE_MAX with "+N more"."""
    out = []
    for i, event in enumerate(events):
        tail = f"\n• +{len(events) - i - 1} more" if i < len(events) - 1 else ""
        if len("\n".join(f"• {e}" for e in out + [event])) + len(tail) > MESSAGE_MAX:
            break
        out.append(event)
    text = "\n".join(f"• {e}" for e in out)
    if len(out) < len(events):
        text += f"\n• +{len(events) - len(out)} more"
    return text, out


def _norm(text: str) -> str:
    return " ".join(text.split())


def check(stream, tool: str, channel: str, message_text: str, lines: list) -> str:
    """Read a posting session. Returns "" when it posted as asked, or the drift when the post reached the channel
    but not exactly (posted twice, an event line missing): the events count as sent either way, so a good post is
    never repeated. Raises Fail 7 when the session broke its rules (another tool, another channel, an argument
    other than the channel, the text and link previews, or text nobody collected), so notify.sh holds notices
    until the owner looks; Fail 1, 3, 4 or 6 when nothing was posted."""
    calls, named, errors, ok, result = {}, False, set(), set(), None
    for m in stream:
        if m.get("type") == "assistant":
            for b in blocks(m, "tool_use"):
                if b.get("name") not in ("ToolSearch", tool):
                    raise Fail(7, f"the session used an unexpected tool: {b.get('name')}")
                args = b.get("input") or {}
                if b.get("name") == tool and (args.get("channel_id") != channel or set(args) - POST_ARGS):
                    raise Fail(7, "the session posted to another channel or with other arguments")
                if b.get("name") == tool and len(str(args.get("message") or "")) > len(message_text) + EXTRA_TEXT:
                    raise Fail(7, "the session posted text nobody collected")
                calls[b.get("id")] = b
        if m.get("type") == "user":
            for b in blocks(m, "tool_result"):
                call = calls.get(b.get("tool_use_id")) or {}
                content = b.get("content")
                if call.get("name") == "ToolSearch" and isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("tool_name") == tool for c in content):
                    named = True
                if call.get("name") == tool:
                    (errors if b.get("is_error") else ok).add(b.get("tool_use_id"))
        if m.get("type") == "result":
            result = m
    posted = [c for i, c in calls.items() if c.get("name") == tool and i in ok]
    if not posted:
        if errors:
            raise Fail(6, "the connector returned an error")
        if result and result.get("is_error") and LIMIT.search(str(result.get("result") or "")):
            raise Fail(4, "the account usage limit stopped the session")
        if result is None or named:
            raise Fail(1, f"the session never called {tool}")
        # A plugin connector and the claude.ai one name their tools differently, and a headless session may load
        # only one of them (#133): name the Slack server it did load, so the fix is one config line.
        loaded = [s.get("name") for m in stream if m.get("type") == "system" and m.get("subtype") == "init"
                  for s in m.get("mcp_servers") or [] if isinstance(s, dict) and "slack" in str(s.get("name")).lower()
                  and prefix(str(s.get("name"))) != tool.rsplit("__", 1)[0]]
        hint = f'; this session loaded "{loaded[0]}": set slack_connector to "{loaded[0]}"' if loaded else ""
        raise Fail(3, f"no Slack connector reachable as {tool}{hint}")
    drift = [f"posted {len(posted)} times"] if len(posted) > 1 else []
    text = _norm(str(posted[0].get("input", {}).get("message") or ""))
    missing = [x for x in lines if _norm(x) not in text]
    if missing:
        drift.append(f"{len(missing)} of {len(lines)} event lines missing from the post")
    return "; ".join(drift)
