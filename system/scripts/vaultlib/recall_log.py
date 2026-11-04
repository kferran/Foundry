"""The recall log (recall R0 spec §3): what recall pushed and what sessions pulled, by count, id and path only, to
system/logs/recall-<YYYY-MM>.jsonl. Stdlib only, so the PostToolUse slow path loads no index or CLI."""
import hashlib
import hmac
import json
import os
import re
import shlex
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .state import append_jsonl

SID = re.compile(r"^[A-Za-z0-9-]{1,100}$")
VALUE_OPTS = {"--limit", "--codebase", "--type", "--per-source", "--budget-chars"}
PARTITIONS = {"work", "personal", "shared"}
RELATED_LINE = re.compile(r"^- .+ — (.+?\.md) \(", re.M)
NOTE_PATH = re.compile(r"(wiki|raw|briefings|system)/[^\n]*\.md")
SUBS = {"issues", "validate", "query", "related", "show", "backlinks", "orphans", "stale", "field", "tags", "set",
        "stage", "recall", "rebuild"}   # vaultlib/cli.py build_parser; anything else logs "other"
MAX_PATHS = 10


def write(vault, record: dict) -> None:
    """Append one line with its ts first; a failure is swallowed, so logging never changes a caller's result."""
    try:
        now = datetime.now().astimezone()
        append_jsonl(Path(vault) / "system" / "logs" / f"recall-{now:%Y-%m}.jsonl",
                     {"ts": now.isoformat(timespec="seconds"), **record})
    except Exception:  # noqa: BLE001 - spec §3.1: every write is wrapped
        pass


def _key(vault) -> bytes:
    """The vault's 32-byte key, made once (mode 600) and linked into place whole, so no reader sees it half-written."""
    path = Path(vault) / "system" / "logs" / "memory" / "recall.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(os.urandom(32))
            os.link(tmp, path)
        except FileExistsError:
            pass
        finally:
            os.unlink(tmp)
    return path.read_bytes()


def terms_hash(vault, text: str):
    """Keyed SHA-256 of the terms (lowercased, whitespace collapsed), 16 hex: a short term cannot be found by hashing
    guesses, and the same terms hash alike within one vault (Q8). None when there is no whole key."""
    try:
        key = _key(vault)
    except OSError:
        return None
    if len(key) != 32:
        return None
    return hmac.new(key, " ".join(text.lower().split()).encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _punct(t: str) -> bool:
    return bool(t) and set(t) <= set("();<>|&")


def _calls(command: str) -> tuple:
    """([(sub, first positional argument)] for each vault_index.py invocation, whether the command is exactly one
    invocation and parsed cleanly, so its output is that call's alone). A heredoc body is prose, never read."""
    command = command.split("<<", 1)[0]
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens, ok = list(lex), True
    except ValueError:  # an unbalanced quote: the plain split still finds the subcommand, but feeds no counts
        tokens, ok = command.split(), False
    calls, starts = [], []
    for i, tok in enumerate(tokens):
        if tok.rsplit("/", 1)[-1] != "vault_index.py":
            continue
        sub, arg, prev = None, None, ""
        for t in tokens[i + 1:]:
            if _punct(t):
                break
            value = prev in VALUE_OPTS or (t in PARTITIONS and (prev == "--partition" or prev in PARTITIONS))
            if sub is None:
                sub = t
            elif not t.startswith("-") and not value:
                arg = t
                break
            prev = t
        calls.append((sub if sub in SUBS else "other", arg))
        starts.append(i)
    whole = ok and len(calls) == 1 and starts[0] <= 1 and not any(_punct(t) for t in tokens)
    return calls, whole


def _paths(sub: str, stdout: str) -> list:
    """The vault note paths in a related or backlinks output; anything else (a title, a Now line) is dropped."""
    if stdout.lstrip().startswith("["):
        try:
            found = [h.get("path") if isinstance(h, dict) else h for h in json.loads(stdout)]
        except (ValueError, AttributeError, TypeError):
            return []
    elif sub == "related":
        found = RELATED_LINE.findall(stdout)
    else:
        found = [line[2:] for line in stdout.splitlines() if line.startswith("- ")]
    return [p for p in found if isinstance(p, str) and NOTE_PATH.fullmatch(p)]


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
    (calls, whole), records = _calls(command), []
    for sub, arg in calls:
        r = {"kind": "pull", "session": sid, "scope": state.get("scope"), "partition": state.get("partition"),
             "sub": sub, "terms": None, "hits": None, "paths": None, "note": None, "found": None}
        if sub in ("related", "query") and arg is not None:
            r["terms"] = terms_hash(vault, arg)
        if sub in ("show", "backlinks"):
            r["note"] = arg
        # Counts only when the call is the whole command: other commands, a pipe or a second call share its stdout.
        if whole and failed and sub in ("related", "query", "show", "backlinks"):
            r.update(hits=0, paths=[], found=False)   # exit non-zero: nothing came back
        elif whole and sub == "show":
            r["found"] = bool(stdout.strip())
        elif whole and sub in ("related", "backlinks"):
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
