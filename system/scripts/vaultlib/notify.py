"""Slack notices (Slack notices spec): what happened since the last notice, as one message, and the check of the
confined session that posts it. Events come from files scripts write (the run ledger, the alerts, Work Order
outcomes); no note text from wiki/ is sent."""
import json
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from . import frontmatter, now as nowmod
from .redact import redact
from .stream import blocks

STATE = Path("system/logs/notify/state.json")
LINE_MAX = 200
MESSAGE_MAX = 4000
TAG = "[notify]"
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
    """A GitHub file link for a path in the vault, or "" when origin is not on github.com."""
    m = re.match(r"^(?:git@github\.com:|https://github\.com/)([^/]+/[^/]+?)(?:\.git)?/?$", _git(vault, "remote", "get-url", "origin"))
    branch = _git(vault, "symbolic-ref", "--short", "HEAD")
    return f"https://github.com/{m.group(1)}/blob/{branch}/{rel}" if m and branch else ""


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
    day = str(rec.get("finished_at") or "")[:10]
    name = cmd.capitalize()
    if rec.get("exit") != 0:
        return f"{name} {day} failed (exit {rec.get('exit')})"
    if cmd == "brief":
        return " ".join(x for x in (f"Brief {day}: {_counts(vault, day)}", link(vault, f"briefings/{day}.md")) if x)
    return " ".join(x for x in (f"Debrief {day} is ready", link(vault, f"briefings/{day}.debrief.md")) if x)


def _cut(text: str) -> str:
    text = " ".join(redact(text)[0].split())
    return text if len(text) <= LINE_MAX else text[:LINE_MAX - 1] + "…"


def collect(vault, now: datetime) -> tuple:
    """(new event lines, the cursor after them). The first run returns no events and a cursor at the end of every
    source, so turning notices on sends no backlog."""
    vault = Path(vault)
    logs = vault / "system" / "logs"
    state = _load(vault)
    first = not state
    cursor = {"ledger": dict(state.get("ledger", {})), "alerts": dict(state.get("alerts", {})),
              "outcomes": list(state.get("outcomes", []))}
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
    for day in sorted({(now - timedelta(days=1)).strftime("%F"), now.strftime("%F")}):
        path = logs / f"alerts_{day}.md"
        if not path.is_file():
            continue
        text = path.read_text(errors="replace").splitlines()
        seen = len(text) if first else int(cursor["alerts"].get(path.name, 0))
        cursor["alerts"][path.name] = len(text)
        alerts += [_cut("Alert " + x[2:]) for x in text[seen:] if x.startswith("- ") and TAG not in x]
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
            detail = out.get("result") or next(iter(out.get("needs") or []), "") or out.get("reason") or ""
            orders.append(_cut(f"Work Order {oid} {out.get('state')}" + (f": {detail}" if detail else "")))
    keep = {f"alerts_{d}.md" for d in ((now - timedelta(days=1)).strftime("%F"), now.strftime("%F"))}
    cursor["alerts"] = {k: v for k, v in cursor["alerts"].items() if k in keep}
    return runs + orders + alerts, cursor


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


def check(stream, tool: str, channel: str, lines: list) -> None:
    """The session called `tool` once, on `channel`, with only channel_id and message, the message holding every
    event line; anything else raises Fail (exit codes as the connector fetches)."""
    calls, named, errors = {}, False, []
    for m in stream:
        if m.get("type") == "assistant":
            for b in blocks(m, "tool_use"):
                if b.get("name") not in ("ToolSearch", tool):
                    raise Fail(7, f"the session used an unexpected tool: {b.get('name')}")
                if b.get("name") == tool and any(c.get("name") == tool for c in calls.values()):
                    raise Fail(7, "the session posted more than once")
                calls[b.get("id")] = b
        if m.get("type") == "user":
            for b in blocks(m, "tool_result"):
                call = calls.get(b.get("tool_use_id")) or {}
                content = b.get("content")
                if call.get("name") == "ToolSearch" and isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("tool_name") == tool for c in content):
                    named = True
                if call.get("name") == tool and b.get("is_error"):
                    errors.append(json.dumps(content)[:200])
    posts = [c for c in calls.values() if c.get("name") == tool]
    if not posts:
        raise Fail(1 if named else 3, f"the session never called {tool}" if named else "no Slack connector reachable")
    args = posts[0].get("input") or {}
    if set(args) != {"channel_id", "message"} or args.get("channel_id") != channel:
        raise Fail(7, "the session posted with other arguments than the channel and the message")
    posted = _norm(str(args.get("message") or ""))
    missing = [x for x in lines if _norm(x) not in posted]
    if missing:
        raise Fail(7, f"the posted message lacks {len(missing)} of its event lines")
    if errors:
        raise Fail(6, f"the connector returned an error: {errors[0]}")
