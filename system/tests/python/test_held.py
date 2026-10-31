"""Held stale claims (confinement spec §3.7, #301 S9): released on a ticked line, archived on a crossed one."""
import shutil
from pathlib import Path

import pytest

from helpers import REPO, write
from vaultlib import held, now

TODAY = "2026-10-12"
BODY = ('---\ntype: session_digest\npartition: {p}\ncodebase: "vault"\nsession_id: "order-{id}"\n'
        'created_at: "2026-10-10T09:00:00-06:00"\nwork_order: "{id}"\nprovenance: ["headless"]\n---\n'
        "## Stale claims\n- a → b (doc)\n- c → d (doc)\n")


@pytest.fixture
def hv(vault: Path) -> Path:
    shutil.copytree(REPO / "system" / "templates", vault / "system" / "templates", dirs_exist_ok=True)
    return vault


def hold(vault, p="work", oid="2026-10-10-x", line=True):
    f = write(vault, f"raw/{p}/held/{oid}.stale-claims.md", BODY.format(p=p, id=oid))
    if line:
        held.add_line(vault, f, 2, "2026-10-10")
    return f


def close(vault, page, mark):
    text = now.read(vault, page)
    (vault / "wiki" / page / "Now.md").write_text(text.replace("- [ ] owed: Review 2 stale", f"- [{mark}] owed: Review 2 stale"))


def alerts():
    got = []
    return got, got.append


def test_a_ticked_line_releases_the_file_to_notes(hv):
    f = hold(hv)
    close(hv, "work", "x")
    held.step(hv, TODAY, alerts()[1])
    assert not f.exists()
    assert (hv / "raw/work/notes" / f.name).read_text() == BODY.format(p="work", id="2026-10-10-x")


def test_a_crossed_line_archives_the_file_unread(hv):
    f = hold(hv)
    close(hv, "work", "-")
    held.step(hv, TODAY, alerts()[1])
    assert (hv / "raw/work/held/rejected" / f.name).is_file()
    assert not (hv / "raw/work/notes").exists()


def test_an_open_line_keeps_the_file(hv):
    f = hold(hv)
    held.step(hv, TODAY, alerts()[1])
    assert f.is_file()
    assert len([l for l in now.open_lines(now.read(hv, "work")) if "held/" in l]) == 1


def test_a_missing_line_is_added_again(hv):
    f = hold(hv, line=False)
    held.step(hv, TODAY, alerts()[1])
    assert f.is_file()
    (line,) = [l for l in now.open_lines(now.read(hv, "work")) if "held/" in l]
    assert f"Review 2 stale claims from a research Work Order before they reach the wiki: raw/work/held/{f.name}" in line


def test_a_line_moved_to_the_archive_still_counts(hv):
    f = hold(hv)
    close(hv, "work", "x")
    # the tick is stamped when the page is next written; archive moves it by that stamp
    (hv / "wiki/work/Now.md").write_text(now.stamp(now.read(hv, "work"), TODAY))
    assert now.archive(hv, "work", TODAY) == 1
    assert "held/" not in now.read(hv, "work")
    held.step(hv, TODAY, alerts()[1])
    assert (hv / "raw/work/notes" / f.name).is_file()


def test_a_shared_files_line_on_work_releases_to_shared_notes(hv):
    f = hold(hv, p="shared", oid="2026-10-10-s")
    close(hv, "work", "x")
    held.step(hv, TODAY, alerts()[1])
    assert (hv / "raw/shared/notes" / f.name).is_file()


def test_a_move_that_fails_is_alerted_and_the_file_stays(hv, monkeypatch):
    f = hold(hv)
    close(hv, "work", "x")
    (hv / "raw/work/notes").write_text("not a folder")
    got, alert = alerts()
    held.step(hv, TODAY, alert)
    assert f.is_file()
    assert any(f.name in a for a in got)


@pytest.mark.parametrize("other, mark", [
    ("- [ ] owed: Pat asked about raw/work/held/{f} [via:: mail] (since 2026-10-10)", "-"),        # an expired mail line
    ("- [ ] waiting: Merge raw/work/held/{f} (since 2026-10-10, https://github.com/o/r/pull/9)", "x"),   # closed by a merge
    ("- [ ] owed: Look again at raw/work/held/{f} (since 2026-10-10)", "x"),                       # another hand line
], ids=["expired-mail-line", "merged-pr-line", "other-hand-line"])
def test_only_the_runners_own_line_decides(hv, other, mark):
    # review of PR C: a line that merely names the path, closed by expiry, a merge or the owner, never moves the file
    f = hold(hv)
    page = hv / "wiki/work/Now.md"
    line = other.format(f=f.name).replace("- [ ] ", f"- [{mark}] ", 1)
    page.write_text(page.read_text().replace("## Waiting", f"## Waiting\n{line}"))
    held.step(hv, TODAY, alerts()[1])
    assert f.is_file()


def test_a_crossed_file_is_kept_out_of_the_index_and_recall(hv):
    # review of PR C: a rejected file never reaches an indexed folder (raw/<p>/archive/ is read by recall)
    f = hold(hv)
    close(hv, "work", "-")
    held.step(hv, TODAY, alerts()[1])
    assert (hv / "raw/work/held/rejected" / f.name).is_file()
    assert not (hv / "raw/work/archive").exists()


def test_a_line_too_long_for_the_cap_is_refused_not_cut(hv):
    # review of PR C: a cut line would lose the path, and the file would wait for ever unnoticed
    f = hold(hv, oid="2026-10-10-" + "a" * 200, line=False)
    got, alert = alerts()
    held.step(hv, TODAY, alert)
    assert any(f.name[:40] in a for a in got)
    assert [l for l in now.open_lines(now.read(hv, "work")) if "held/" in l] == []


def test_only_partition_folders_are_read(hv):
    f = write(hv, "raw/inbox/held/2026-10-10-x.stale-claims.md", BODY.format(p="work", id="2026-10-10-x"))
    held.step(hv, TODAY, alerts()[1])
    assert f.is_file()
    assert "held/" not in now.read(hv, "work")
