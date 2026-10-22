"""What core did for telemetry until factory F2 (#307), now through this extension's manifest, schemas and lint module:
the same alert severities, inbox route, citation rows and reserved tag, with the extension on, and off."""
import subprocess
import sys

import pytest

from helpers import write
from vaultlib import alerts

ON = '---\ntype: config\nextensions: ["handoffs", "telemetry"]\n---\n'


@pytest.mark.parametrize("line,want", [
    ("- 06:10:00 [incident] prod-logs: new production error in api", "now"),
    ("- 06:10:00 [rca] filed EX-12 for 2026-10-11-orders", "now"),
    ("- 06:10:00 [telemetry] text", "brief"),
    ("- 06:10:00 [telemetry] prod-adx: a log line in raw/telemetry/prod-adx-a-0123456789ab.md holds a credential "
     "shape: assignment", "now"),
    ("- 06:10:00 [telemetry] prod-adx: and 2 more new groups hold a credential shape (see raw/telemetry/)", "now"),
    ("- 06:10:00 [telemetry] prod-adx: run az login", "brief"),
    ("- 06:10:00 [telemetry] prod-adx: 900 groups; only 500 kept", "brief"),
])
def test_the_moved_tags_keep_their_severity_with_the_extension_on(vault, line, want):
    write(vault, "system/config.md", ON)
    assert alerts.severity(line, alerts.extension_tags(vault)) == want


def test_with_the_extension_off_an_incident_waits_for_the_brief_and_alert_py_refuses_rca(vault, cli):
    write(vault, "system/config.md", '---\ntype: config\nextensions: []\n---\n')
    assert alerts.severity("- 06:10:00 [incident] x", alerts.extension_tags(vault)) == "brief"
    alert = [sys.executable, str(vault / "system/scripts/alert.py")]
    r = subprocess.run([*alert, "rca", "x"], capture_output=True, text=True)
    assert r.returncode == 2 and "usage" in r.stderr
    write(vault, "system/config.md", ON)
    r = subprocess.run([*alert, "rca", "HOTFIX candidate: x"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "[rca] HOTFIX candidate: x" in "".join(p.read_text() for p in (vault / "system/logs").glob("alerts_*.md"))
