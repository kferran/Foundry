#!/usr/bin/env python3
"""Append one alert line to system/logs/alerts_<date>.md (alert tags spec §3.3). Exit 0 written, 2 usage.

  alert.py <tag> <text>    a tag from vaultlib/alerts.py; a session uses foreman to tell the owner something now
"""
import re
import sys
from datetime import datetime
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VAULT / "system" / "scripts"))
from vaultlib.alerts import TAGS  # noqa: E402

CONTROL = re.compile(r"[\x00-\x1f\x7f]+")   # one line per alert: a newline in the text cannot forge a second


def main(argv) -> int:
    text = CONTROL.sub(" ", argv[2]).strip() if len(argv) == 3 else ""
    if len(argv) != 3 or argv[1] not in TAGS or not text:
        print(f"usage: alert.py <{'|'.join(TAGS)}> <text>", file=sys.stderr)
        return 2
    t = datetime.now()
    logs = VAULT / "system" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with open(logs / f"alerts_{t:%Y-%m-%d}.md", "a", encoding="utf-8") as fh:
        fh.write(f"- {t:%H:%M:%S} [{argv[1]}] {text}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
