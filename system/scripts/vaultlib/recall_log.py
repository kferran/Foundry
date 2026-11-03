"""The recall log (recall R0 spec §3): what recall pushed and what sessions pulled, by count, id and path only, to
system/logs/recall-<YYYY-MM>.jsonl. Stdlib only, so the PostToolUse slow path loads no index or CLI."""
import hashlib
import hmac
import json
import os
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

from .state import append_jsonl

SID = re.compile(r"^[A-Za-z0-9-]{1,100}$")
VALUE_OPTS = {"--limit", "--codebase", "--type", "--per-source", "--budget-chars"}
PARTITIONS = {"work", "personal", "shared"}
RELATED_LINE = re.compile(r"^- .+ — (.+?\.md) \(", re.M)
MAX_PATHS = 10


def write(vault, record: dict) -> None:
    """Append one line with its ts first; a failure is swallowed, so logging never changes a caller's result."""
    try:
        now = datetime.now().astimezone()
        append_jsonl(Path(vault) / "system" / "logs" / f"recall-{now:%Y-%m}.jsonl",
                     {"ts": now.isoformat(timespec="seconds"), **record})
    except Exception:  # noqa: BLE001 - spec §3.1: every write is wrapped
        pass


def terms_hash(vault, text: str) -> str:
    """Keyed SHA-256 of the terms (lowercased, whitespace collapsed), 16 hex: a short term cannot be found by hashing
    guesses, and the same terms hash alike within one vault (Q8)."""
    path = Path(vault) / "system" / "logs" / "memory" / "recall.key"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(os.urandom(32))
    except FileExistsError:
        pass
    key = path.read_bytes()
    return hmac.new(key, " ".join(text.lower().split()).encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _tokens(command: str) -> list:
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:  # an unbalanced quote: the plain split still finds the subcommand
        return command.split()


def _calls(command: str) -> list:
    """(sub, first positional argument) for each vault_index.py invocation in a shell command."""
    tokens, calls = _tokens(command), []
    for i, tok in enumerate(tokens):
        if tok.rsplit("/", 1)[-1] != "vault_index.py":
            continue
        sub, arg, prev = None, None, ""
        for t in tokens[i + 1:]:
            if t and set(t) <= set("();<>|&"):
                break
            value = prev in VALUE_OPTS or (t in PARTITIONS and (prev == "--partition" or prev in PARTITIONS))
            if sub is None:
                sub = t
            elif not t.startswith("-") and not value:
                arg = t
                break
            prev = t
        calls.append((sub, arg))
    return calls


def _paths(sub: str, stdout: str) -> list:
    if stdout.lstrip().startswith("["):
        try:
            return [h.get("path") if isinstance(h, dict) else h for h in json.loads(stdout)]
        except (ValueError, AttributeError):
            return []
    if sub == "related":
        return RELATED_LINE.findall(stdout)
    return [line[2:] for line in stdout.splitlines() if line.startswith("- ")]


def pull(vault, event: dict) -> list:
    """Write and return one pull line per vault_index.py call in a Bash PostToolUse event (spec §3.3)."""
    sid = event.get("session_id")
    if not isinstance(sid, str) or not SID.match(sid) or event.get("agent_id") or event.get("tool_name") != "Bash":
        return []
    try:
        state = json.loads((Path(vault) / "system/logs/memory/sessions" / f"{sid}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    command = (event.get("tool_input") or {}).get("command") or ""
    # Probe (plan Task 1): PostToolUse carries tool_response {stdout, stderr, ...}; a call that exits non-zero fires
    # PostToolUseFailure instead, with no tool_response (its error text is never read).
    failed = event.get("hook_event_name") == "PostToolUseFailure"
    resp = event.get("tool_response")
    stdout = resp if isinstance(resp, str) else (resp.get("stdout") or "") if isinstance(resp, dict) else ""
    calls, records = _calls(command), []
    for sub, arg in calls:
        r = {"kind": "pull", "session": sid, "scope": state.get("scope"), "partition": state.get("partition"),
             "sub": sub, "terms": None, "hits": None, "paths": None, "note": None, "found": None}
        if sub in ("related", "query") and arg is not None:
            r["terms"] = terms_hash(vault, arg)
        if sub in ("show", "backlinks"):
            r["note"] = arg
        if len(calls) == 1 and failed and sub in ("related", "query", "show", "backlinks"):
            r.update(hits=0, paths=[], found=False)   # exit non-zero: nothing came back
        elif len(calls) == 1 and sub == "show":   # two calls share one stdout, so neither gets counts
            r["found"] = bool(stdout.strip())
        elif len(calls) == 1 and sub in ("related", "backlinks"):
            paths = _paths(sub, stdout)
            r.update(hits=len(paths), paths=paths[:MAX_PATHS], found=bool(paths))
        write(vault, r)
        records.append(r)
    return records


def main(argv=None) -> int:
    """recall_log.py pull: the hook JSON on stdin. Always exits 0: the hook must never fail a session."""
    try:
        if (argv if argv is not None else sys.argv[1:]) == ["pull"]:
            pull(Path(__file__).resolve().parents[3], json.loads(sys.stdin.read()))
    except Exception:  # noqa: BLE001 - fail open
        pass
    return 0
