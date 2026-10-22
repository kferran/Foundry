"""The alert tags (alert tags spec §2): who raises each one and whether Slack carries it now or it waits for the
brief. notify.py sends only `now` lines; an untagged line or a tag outside the table waits for the brief. An
extension's tags live in its manifest's `alert_tags` (factory F2 §3.1)."""
import re

TAGS = {
    "foreman": ("a session's message to the owner", "now"),
    "orders": ("a Work Order that needs the owner, the self-test, the sandbox", "now"),
    "sync": ("sync blocked, a failed merge or push", "now"),
    "update": ("the daily template update", "now"),
    "intake": ("a failed brief or debrief, a publish refused, an input quarantined", "now"),
    "triage": ("mail that needs the owner, sent as a count", "now"),
    "commit_runs": ("a run the hook refused", "brief"),
    "smoke": ("the smoke check", "brief"),
    "calendar": ("the calendar fetch", "brief"),
    "meetings": ("the meetings fetch", "brief"),
    "memory": ("the memory hooks", "brief"),
    "extensions": ("an extension that will not load, once a day", "brief"),
    "notify": ("the notifier itself", "never"),
}
LINE = re.compile(r"^- \d\d:\d\d:\d\d \[([a-z_]+)\] ")
# Two tags decide by their text: triage reaches Slack only as its "N new:" count (a failed triage fetch is a fetch
# failure like any other), and a stale timer from the smoke check goes now, since a stale brief timer means no brief
# would ever show it (the owner's rule: now when the next brief is too late). An extension tag does the same with
# `now_when` in its manifest.
NOW_WHEN = {"triage": re.compile(r"\d+ new: "), "smoke": re.compile(r"\S+\.timer stale: ")}
SEVERITIES = ("now", "brief", "never")


def extension_tags(vault) -> dict:
    """{tag: severity, or (severity, pattern) for an entry with `now_when`} for every tag of the enabled manifests
    (phase D spec §2 decision 10, factory F2 §3.1). A bare tag, a severity outside SEVERITIES or a `now_when` that does
    not compile waits for the brief or keeps its severity; a core tag keeps core's rule."""
    from . import extensions
    try:
        loaded = extensions.enabled(vault)
    except (OSError, UnicodeDecodeError):
        return {}   # one unreadable manifest must not stop every Slack notice
    out = {}
    for _, d in loaded:
        for t in d.get("alert_tags") or []:
            entry = t if isinstance(t, dict) else {"tag": t}
            if not entry.get("tag"):
                continue
            sev = str(entry.get("severity", "brief"))
            sev = sev if sev in SEVERITIES else "brief"
            try:
                when = re.compile(str(entry["now_when"])) if entry.get("now_when") else None
            except re.error:
                when = None
            out[str(entry["tag"])] = (sev, when) if when else sev
    return out


def severity(line: str, extra: dict = None) -> str:
    m = LINE.match(line)
    if not m:
        return "brief"
    tag = m.group(1)
    if tag in NOW_WHEN:
        return "now" if NOW_WHEN[tag].match(line, m.end()) else "brief"
    if tag in TAGS:
        return TAGS[tag][1]
    sev = (extra or {}).get(tag, "brief")
    if isinstance(sev, tuple):
        sev, when = sev
        return "now" if when.match(line, m.end()) else sev
    return sev
