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


def test_an_inbox_production_error_routes_to_raw_telemetry_while_the_extension_is_present(vault):
    from vaultlib import extensions
    write(vault, "system/config.md", '---\ntype: config\nextensions: []\n---\n')   # present, not enabled
    assert extensions.importer_for(vault, "production_error") == "telemetry"


def _rca(stem, codebase, status, body, extra=""):
    return (f'---\ntype: rca\ntitle: "{stem}"\npartition: work\ncreated_at: "2026-10-11"\nsource: "raw/telemetry/a.md"\n'
            f'codebase: {codebase}\nrc_confidence: 4\nfix_confidence: 4\nstatus: {status}\n{extra}tags: [rca]\n---\n'
            f'# {stem}\n\n{body}\n')


def _citations(cli):
    import json
    return [(i["path"], i["line"], i["message"]) for i in json.loads(cli("issues", "--json").stdout)["issues"]
            if i["code"] == "citation"]


def test_an_open_rca_notes_citations_are_checked_live(cli, vault, tmp_path):
    """Moved from core's test_cli.py (#166): an rca names its codebase by file name; outside fences only."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("a\nb\nc\n")
    write(vault, "system/codebases/app.md", f'---\ntype: codebase\nname: app\npath: "{repo}"\npartition: work\n'
          'search_globs: ["*"]\n---\nEntry at `src/app.py:3`.\n')
    write(vault, "wiki/work/rca/2026-10-11-orders.md",
          '---\ntype: rca\ntitle: "Orders fail"\npartition: work\ncreated_at: "2026-10-11"\nsource: "raw/telemetry/a.md"\n'
          'codebase: app\nrc_confidence: 4\nfix_confidence: 4\nstatus: draft\ntags: [rca]\n---\n# Orders fail\n\n'
          'Root cause at `src/app.py:9`, see https://example.com:443/x.py:2 and `app.py:2`.\n'
          '```\nat src/trace.py:7\n```\n')
    assert _citations(cli) == [("wiki/work/rca/2026-10-11-orders.md", 15, "citation src/app.py:9: the file has 3 lines")]
    (repo / "src" / "app.py").write_text("a\n" * 9)   # read live: the code moved, the row goes without a reindex
    assert _citations(cli) == []


def test_only_open_active_rca_notes_are_cited(cli, vault, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    write(vault, "system/codebases/app.md", f'---\ntype: codebase\nname: "App Service"\npath: "{repo}"\npartition: work\n'
          'search_globs: ["*"]\n---\nNothing cited.\n')
    gone = "Gone `src/gone.py:1`."
    for stem, status, extra in (("open", "draft", ""), ("ok", "approved", ""), ("filed", "filed", ""),
                                ("rejected", "rejected", ""), ("old", "draft", 'superseded_by: "[[open]]"\n')):
        write(vault, f"wiki/work/rca/{stem}.md", _rca(stem, "app", status, gone, extra))
    write(vault, "wiki/work/rca/unset.md", _rca("unset", "app", "draft", gone).replace("status: draft\n", ""))
    assert [(p, m) for p, _, m in _citations(cli)] == [
        ("wiki/work/rca/ok.md", "citation src/gone.py:1: no such file in codebase app"),
        ("wiki/work/rca/open.md", "citation src/gone.py:1: no such file in codebase app"),
        ("wiki/work/rca/unset.md", "citation src/gone.py:1: no such file in codebase app"),   # status defaults to draft
    ]


def test_tag_rca_is_reserved_to_rca_notes(cli, vault):
    import json
    from helpers import concept
    write(vault, "wiki/work/concepts/Topic.md", concept("work", "Topic", tags="[rca]"))
    write(vault, "wiki/work/rca/2026-10-11-orders.md", _rca("2026-10-11-orders", "app", "draft", "Body."))
    rows = [(i["path"], i["code"]) for i in json.loads(cli("issues", "--json").stdout)["issues"]
            if i["code"] == "tag-reserved"]
    assert rows == [("wiki/work/concepts/Topic.md", "tag-reserved")]
    assert "rca" not in cli("tags", "--partition", "work").stdout.split()
