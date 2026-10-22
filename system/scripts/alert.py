#!/usr/bin/env python3
"""Append one alert line to system/logs/alerts_<date>.md (alert tags spec §3.3). Exit 0 written, 2 usage, 3 on a
client (no notifier and no brief run there, so the line would reach nobody).

  alert.py <tag> <text>    a tag from vaultlib/alerts.py or an enabled extension's manifest; a session uses foreman to tell the owner something now
"""
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib import frontmatter  # noqa: E402
from vaultlib.alerts import TAGS, extension_tags  # noqa: E402

# One line per alert: no newline, other control character or Unicode line break may forge a second one.
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]+")


def config() -> dict:
    try:
        return frontmatter.parse((VAULT / "system" / "config.md").read_text(encoding="utf-8")).data or {}
    except (OSError, UnicodeDecodeError):
        return {}


def main(argv) -> int:
    text = CONTROL.sub(" ", argv[2]).strip() if len(argv) == 3 else ""
    tags = [*TAGS, *(t for t in extension_tags(VAULT) if t not in TAGS)]
    if len(argv) != 3 or argv[1] not in tags or not text:
        print(f"usage: alert.py <{'|'.join(tags)}> <text>", file=sys.stderr)
        return 2
    cfg = config()
    if cfg.get("machine_role") == "client":
        print("alert.py: a client keeps its alerts on this machine and nothing reads them; tell the user in this "
              "session or add a Now line", file=sys.stderr)
        return 3
    try:
        t = datetime.now(ZoneInfo(str(cfg.get("timezone") or "UTC")))   # the vault's day, as the other writers
    except (ZoneInfoNotFoundError, ValueError):
        t = datetime.now(ZoneInfo("UTC"))
    logs = VAULT / "system" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with open(logs / f"alerts_{t:%Y-%m-%d}.md", "a", encoding="utf-8") as fh:
        fh.write(f"- {t:%H:%M:%S} [{argv[1]}] {text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
