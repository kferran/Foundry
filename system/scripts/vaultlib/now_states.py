"""The Now line's states and the changes code may make to them (factory F7 spec §3). Every mark or stamp a code writer
puts on a line comes from transition(); a change the table does not allow leaves the line as it was and is logged to
system/logs/now-<YYYY-MM>.jsonl. The owner's hand edits are not governed."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from . import now   # now imports this module too: its names are read at call time

STATE = {" ": "open", "x": "done", "X": "done", "-": "dropped"}   # any other mark is "unknown"
STATES = ("open", "open stamped", "done", "done stamped", "dropped", "dropped stamped", "unknown")
MARK = {"open": " ", "done": "x", "dropped": "-"}
ALLOWED = {   # (writer, from) -> the states it may write; from None is a line that is not there yet
    ("brief", None): {"open"},                                   # T1: the brief only adds open lines
    ("check", "open"): {"done stamped", "dropped stamped"},      # T7 evidence, T8 expiry
    ("stamp", "done"): {"done stamped"},                         # T9
    ("stamp", "dropped"): {"dropped stamped"},                   # T9
    ("stamp", "open stamped"): {"open"},                         # T10
    ("filer", "done"): {"done stamped", "open"},                 # T14 filed, T15 reopen (an extension's ticket filer)
    ("filer", "done stamped"): {"done stamped", "open"},
    ("filer", "dropped"): {"open"},
    ("filer", "dropped stamped"): {"open"},
}


def state(line):
    """The line's state, one of STATES; None for a line that is no checkbox."""
    if not (line and line.startswith("- [") and line[4:6] == "] "):
        return None
    base = STATE.get(line[3], "unknown")
    return base if base == "unknown" or not now.STAMP.search(line) else f"{base} stamped"


def allowed(writer: str, frm, to: str) -> bool:
    return to in ALLOWED.get((writer, frm), ())


def transition(line, writer: str, to: str, how: str = "", day: str = "", vault=None):
    """line in state `to`, stamped `_(closed: <how> <day>)_` when `to` is a stamped state; None when the table refuses
    the change (logged when vault is given) and for a line that is not there yet (the brief's add, checked only)."""
    frm = state(line)
    if not allowed(writer, frm, to):
        if vault is not None:
            _refused(vault, line, writer, frm, to, day)
        return None
    if line is None:
        return None
    base = to.split(" ")[0]
    body = now.STAMP.sub("", line).rstrip()
    out = f"- [{line[3] if STATE.get(line[3]) == base else MARK[base]}]{body[5:]}"
    return f"{out} _(closed: {how} {day})_" if to.endswith(" stamped") else out


def _refused(vault, line, writer, frm, to, day) -> None:
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    key = now.STAMP.sub("", line or "").rstrip()[5:]
    record = {"ts": ts, "writer": writer, "from": frm, "to": to,
              "statement_hash": hashlib.sha256(key.encode()).hexdigest()[:16]}
    log = Path(vault) / "system" / "logs" / f"now-{(day or ts)[:7]}.jsonl"
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except (OSError, ValueError):
        pass   # a refusal never fails its unit
