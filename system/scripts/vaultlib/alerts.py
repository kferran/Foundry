"""The alert tags (alert tags spec §2): who raises each one and whether Slack carries it now or it waits for the
brief. notify.py sends only `now` lines; an untagged line or a tag outside the table waits for the brief."""
import re

TAGS = {
    "foreman": ("a session's message to the owner", "now"),
    "orders": ("a Work Order that needs the owner, the self-test, the sandbox", "now"),
    "sync": ("sync blocked, a failed merge or push", "now"),
    "update": ("the daily template update", "now"),
    "rca": ("a ticket filed, or a filing that stopped", "now"),
    "intake": ("a failed brief or debrief, a publish refused, an input quarantined", "now"),
    "triage": ("mail that needs the owner, sent as a count", "now"),
    "commit_runs": ("a run the hook refused", "brief"),
    "smoke": ("the smoke check", "brief"),
    "calendar": ("the calendar fetch", "brief"),
    "meetings": ("the meetings fetch", "brief"),
    "handoffs": ("the Jira handoffs fetch", "brief"),
    "telemetry": ("the telemetry fetch", "brief"),
    "dtcc": ("the DTCC watcher", "brief"),
    "memory": ("the memory hooks", "brief"),
    "notify": ("the notifier itself", "never"),
}
LINE = re.compile(r"^- \d\d:\d\d:\d\d \[([a-z_]+)\] ")
# Two tags decide by their text: triage reaches Slack only as its "N new:" count (a failed triage fetch is a fetch
# failure like any other), and a stale timer from the smoke check goes now, since a stale brief timer means no brief
# would ever show it (the owner's rule: now when the next brief is too late).
NOW_WHEN = {"triage": re.compile(r"\d+ new: "), "smoke": re.compile(r"\S+\.timer stale: ")}


def severity(line: str) -> str:
    m = LINE.match(line)
    if not m or m.group(1) not in TAGS:
        return "brief"
    if m.group(1) in NOW_WHEN:
        return "now" if NOW_WHEN[m.group(1)].match(line, m.end()) else "brief"
    return TAGS[m.group(1)][1]
