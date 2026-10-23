"""The Now page (Now page spec): vaultlib/now.py and system/scripts/now.py."""
import fcntl
import os
import shutil
import subprocess
import sys

import pytest

from helpers import REPO, write
from vaultlib import now

TODAY = "2026-10-09"
KEY = "ghp_" + "a" * 36
CONFIG = ('---\ntype: config\ntimezone: "America/Denver"\nbrief_time: "06:00"\ndebrief_time: "17:00"\n'
          'remote_mode: "none"\ndefault_partition: "work"\n---\n')


def page(vault, partition="work"):
    return (vault / "wiki" / partition / "Now.md").read_text(encoding="utf-8")


def prepare(vault):
    shutil.copytree(REPO / "system" / "templates", vault / "system" / "templates", dirs_exist_ok=True)
    write(vault, "system/config.md", CONFIG)


def gh_stub(tmp_path, state="MERGED", rc=0):
    stub = tmp_path / "gh"
    stub.write_text(f"#!/bin/bash\necho \"$@\" >> {tmp_path}/gh.args\necho {state}\nexit {rc}\n")
    stub.chmod(0o755)
    return str(stub)


def order(vault, item_id, state, partition="work"):
    write(vault, f"raw/{partition}/nightshift/{item_id}.md",
          f'---\ntype: "nightshift_item"\nid: "{item_id}"\npartition: "{partition}"\nkind: "plan"\nstate: "{state}"\n---\n')


def test_add_creates_the_page_and_files_each_kind_under_its_section(vault):
    prepare(vault)
    assert now.add(vault, "work", "owed", "Review the export PR", TODAY, "Blake Sample",
                   "https://github.com/acme/shop/pull/7")[0] == "added"
    now.add(vault, "work", "waiting", "Access to the staging logs", TODAY, "Blake Sample", "EX-12")
    now.add(vault, "work", "draft", "Reply to the vendor about the delay", TODAY, "vendor")
    text = page(vault)
    assert text.startswith('---\ntype: concept\ntags: [now]\ncompiled_at: "2026-10-09"\npartition: work\n---\n')
    needs, waiting = text.split("## Needs you\n")[1].split("## Waiting\n")
    assert needs.strip().splitlines() == [
        "- [ ] owed: Review the export PR [due:: 2026-10-12] (Blake Sample, since 2026-10-09, "
        "https://github.com/acme/shop/pull/7)",
        "- [ ] draft: Reply to the vendor about the delay [due:: 2026-10-12] (vendor, since 2026-10-09)"]
    assert waiting.strip().splitlines() == [
        "- [ ] waiting: Access to the staging logs [due:: 2026-10-12] (Blake Sample, since 2026-10-09, EX-12)"]


def test_the_same_open_statement_is_not_added_twice(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Send the report", TODAY)
    assert now.add(vault, "work", "owed", "Send the report", "2026-10-10") == (
        "exists", "- [ ] owed: Send the report [due:: 2026-11-08] (since 2026-10-09)")
    assert page(vault).count("Send the report") == 1


def test_a_statement_with_parentheses_parses(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Fix the 409 (export) bug", TODAY)
    assert now.add(vault, "work", "owed", "Fix the 409 (export) bug", TODAY)[0] == "exists"


AFTER = ("- [ ] owed: Pick the export format [rec:: CSV: the vendor's loader reads it] [due:: 2026-10-18] "
         "(vendor contact, since 2026-10-15)")


def test_the_fields_parse_inside_the_statement_in_either_order():
    # Now clock spec §3: LINE is unchanged; fields() reads each field once, anywhere, and returns the bare statement.
    m = now.LINE.match(AFTER)
    assert (m.group("who"), m.group("since")) == ("vendor contact", "2026-10-15")
    want = ("Pick the export format", "CSV: the vendor's loader reads it", "2026-10-18")
    assert now.fields(m.group("statement")) == want
    assert now.fields("Pick the export format [due:: 2026-10-18] [rec:: CSV: the vendor's loader reads it]") == want
    assert now.fields("Pick [due:: 2026-10-18] the  export [rec:: CSV: the vendor's loader reads it] format") == want
    assert now.fields("Fix the 409 (export) bug") == ("Fix the 409 (export) bug", "", "")
    assert now.render("owed", "Pick the export format", "2026-10-15", "vendor contact",
                      rec="CSV: the vendor's loader reads it", due="2026-10-18") == AFTER


def test_hand_typed_field_variants_are_read_as_the_fields(vault):
    # #166 clock spec §3, review finding 1: Dataview reads `[due::2026-10-20]` and any case of the key, so a hand
    # edit in that form still counts as the clock and a repeat add finds the line.
    assert now.fields("Pick [due::2026-10-20] x") == ("Pick x", "", "2026-10-20")
    assert now.fields("Pick [Due:: 2026-10-20] [REC::CSV: it loads ] x") == ("Pick x", "CSV: it loads", "2026-10-20")
    prepare(vault)
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          "---\n# Now\n\n## Needs you\n- [ ] owed: Pick format [DUE::2026-10-20] (since 2026-10-01)\n\n## Waiting\n")
    before = page(vault)
    assert now.add(vault, "work", "owed", "Pick format", TODAY)[0] == "exists"
    assert page(vault) == before
    assert now.overdue(vault, "2026-10-25") == (
        "**1 to 7 days over**\n- owed: Pick format [DUE::2026-10-20] (since 2026-10-01)")


def test_an_invalid_due_on_the_page_counts_as_no_clock(vault):
    prepare(vault)  # #166 clock spec §5, review finding 1: --due sets a clock on it, never "would loosen"
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-02-01\"\npartition: work\n"
          "---\n# Now\n\n## Needs you\n- [ ] owed: Pick format [due:: 2026-02-30] (since 2026-02-01)\n\n## Waiting\n")
    assert now.overdue(vault, "2026-03-05") == "1 of 1 open line carries no clock."
    assert now.add(vault, "work", "owed", "Pick format", "2026-02-01", due="2026-03-01") == (
        "tightened", "- [ ] owed: Pick format [due:: 2026-03-01] (since 2026-02-01)")


def test_add_writes_the_default_clock(vault):
    # Now clock spec §4: 3 days with who or a standalone ISO date (a Work Order id does not count), else 30.
    prepare(vault)
    assert now.add(vault, "work", "owed", "Pick it", TODAY, "vendor")[1] == (
        "- [ ] owed: Pick it [due:: 2026-10-12] (vendor, since 2026-10-09)")
    assert now.add(vault, "work", "owed", "Ship by 2026-10-20", TODAY)[1] == (
        "- [ ] owed: Ship by 2026-10-20 [due:: 2026-10-12] (since 2026-10-09)")
    assert now.add(vault, "work", "waiting", "Decide 2026-10-08-export-fix", TODAY)[1] == (
        "- [ ] waiting: Decide 2026-10-08-export-fix [due:: 2026-11-08] (since 2026-10-09)")
    assert now.add(vault, "work", "draft", "Reply to the vendor", TODAY)[1] == (
        "- [ ] draft: Reply to the vendor [due:: 2026-11-08] (since 2026-10-09)")
    assert now.add(vault, "work", "owed", "Named", TODAY, "vendor", rec="CSV: it loads", due="2026-12-01")[1] == (
        "- [ ] owed: Named [rec:: CSV: it loads] [due:: 2026-12-01] (vendor, since 2026-10-09)")


def test_only_a_named_date_within_30_days_gives_the_short_clock():
    # #166 clock spec §4, review ruling: a date gives since + 3 only when it falls within 30 days of since (a DTCC
    # deadline months out keeps since + 30); a date inside a URL or a path does not count; a date with a time does.
    short, long = "2026-10-18", "2026-11-14"
    for statement, want in (("DTCC: Release notes ([[dtcc-r]]) — Production 2026-10-25 (a1)", short),
                            ("DTCC: Release notes ([[dtcc-r]]) — Production 2027-01-13 (a1)", long),
                            ("Follow up on 2026-10-01", long), ("Due 2026-11-14", short), ("on 2026-10-20.", short),
                            ("Call at 2026-10-20T09:00", short), ("See https://x.example/blog/2026-10-20/post", long),
                            ("Read briefings/2026-10-20.md", long), ("Open 2026-10-20.md", long),
                            ("Merge 2026-10-20-export-fix", long), ("Release 2026-13-45", long)):
        assert now.default_due(statement, "2026-10-15", "") == want, statement


def test_add_refuses_a_field_in_the_statement_a_bracket_in_rec_and_a_bad_date(vault):
    prepare(vault)  # Now clock spec §3
    for kwargs in ({"statement": "Pick [due:: 2026-10-10]"}, {"statement": "Pick [rec:: CSV]"},
                   {"statement": "Pick [Due::2026-10-10]"}, {"statement": "Pick [REC:: CSV]"},
                   {"rec": "CSV] x"}, {"rec": "a\nb"}, {"due": "20261010"}, {"due": "2026-02-30"}):
        statement = kwargs.pop("statement", "Pick")
        try:
            now.add(vault, "work", "owed", statement, TODAY, **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"accepted {statement!r} {kwargs}")
    assert not (vault / "wiki/work/Now.md").exists()


def test_a_repeat_add_with_nothing_new_writes_nothing(vault):
    # Now clock spec §5: triage, the brief and sessions re-add every day; that path stays write-free, and a
    # clockless line (written before the clock) gets no clock from it.
    prepare(vault)
    now.add(vault, "work", "owed", "Pick it", TODAY, "vendor", "EX-1", rec="CSV: it loads")
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("## Waiting\n", "## Waiting\n- [ ] waiting: Old one (since 2026-09-01)\n"))
    before = path.read_bytes()
    assert now.add(vault, "work", "owed", "Pick  it", "2026-10-10")[0] == "exists"
    assert now.add(vault, "work", "owed", "Pick it", TODAY, "vendor", "EX-1", rec="CSV: it loads",
                   due="2026-10-12")[0] == "exists"
    assert now.add(vault, "work", "owed", "Pick it", TODAY, evidence="EX-2") == (
        "exists", "- [ ] owed: Pick it [rec:: CSV: it loads] [due:: 2026-10-12] (vendor, since 2026-10-09, EX-1)")
    assert now.add(vault, "work", "waiting", "Old one", TODAY, "someone")[0] == "exists"
    assert path.read_bytes() == before


def test_a_repeat_add_tightens_the_clock_and_refuses_to_loosen_it(vault):
    prepare(vault)  # Now clock spec §5
    now.add(vault, "work", "owed", "Pick it", TODAY, "vendor")
    now.add(vault, "work", "owed", "Other", TODAY)
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("## Waiting\n", "## Waiting\n- [ ] waiting: Old one (since 2026-09-01)\n"))
    assert now.add(vault, "work", "owed", "Pick it", TODAY, due="2026-10-11") == (
        "tightened", "- [ ] owed: Pick it [due:: 2026-10-11] (vendor, since 2026-10-09)")
    assert now.add(vault, "work", "waiting", "Old one", TODAY, due="2026-12-01")[0] == "tightened"
    before = path.read_bytes()
    try:
        now.add(vault, "work", "owed", "Pick it", TODAY, rec="CSV: it loads", due="2026-10-12")
        raise AssertionError("loosened")
    except ValueError as exc:
        assert str(exc) == "would loosen the clock (due 2026-10-11)"
    assert path.read_bytes() == before
    assert now.open_lines(page(vault)) == ["- [ ] owed: Pick it [due:: 2026-10-11] (vendor, since 2026-10-09)",
                                           "- [ ] owed: Other [due:: 2026-11-08] (since 2026-10-09)",
                                           "- [ ] waiting: Old one [due:: 2026-12-01] (since 2026-09-01)"]


def test_a_repeat_add_sets_or_replaces_rec_and_sets_evidence_once(vault):
    prepare(vault)  # Now clock spec §5
    now.add(vault, "work", "owed", "Pick it", TODAY)
    assert now.add(vault, "work", "owed", "Pick it", TODAY, rec="CSV: it loads") == (
        "updated", "- [ ] owed: Pick it [rec:: CSV: it loads] [due:: 2026-11-08] (since 2026-10-09)")
    assert now.add(vault, "work", "owed", "Pick it", TODAY, rec="JSON: smaller", evidence="EX-1")[1] == (
        "- [ ] owed: Pick it [rec:: JSON: smaller] [due:: 2026-11-08] (since 2026-10-09, EX-1)")
    assert now.add(vault, "work", "owed", "Pick it", TODAY, evidence="EX-2")[0] == "exists"
    assert now.open_lines(page(vault)) == [
        "- [ ] owed: Pick it [rec:: JSON: smaller] [due:: 2026-11-08] (since 2026-10-09, EX-1)"]


def test_invalid_lines_are_refused(vault):
    prepare(vault)
    for args in (("shared", "owed", "x", ""), ("work", "decision", "x", ""), ("work", "owed", "a\nb", ""),
                 ("work", "owed", " ", ""), ("work", "owed", "x", "A, B")):
        try:
            now.add(vault, args[0], args[1], args[2], TODAY, args[3])
        except ValueError:
            continue
        raise AssertionError(f"accepted {args}")
    assert not (vault / "wiki/work/Now.md").exists()


def test_a_missing_section_heading_is_added_back(vault):
    prepare(vault)
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: []\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          "---\n# Now\n\n## Needs you\n- [ ] owed: A (since 2026-10-01)\n")
    now.add(vault, "work", "waiting", "B", TODAY)
    assert page(vault).endswith("## Needs you\n- [ ] owed: A (since 2026-10-01)\n\n## Waiting\n"
                                "- [ ] waiting: B [due:: 2026-11-08] (since 2026-10-09)\n")


def test_hand_ticks_are_stamped_and_closed_lines_stay_until_archived():
    text = ("## Needs you\n- [x] owed: Ticked (since 2026-10-01)\n- [-] owed: Dropped (since 2026-10-01)\n"
            "- [x] owed: Kept (since 2026-10-01) _(closed: ticked 2026-10-02)_\n"
            "- [x] owed: Old (since 2026-10-01) _(closed: PR merged 2026-09-01)_\n- [ ] owed: Open (since 2026-10-01)\n")
    assert now.stamp(text, TODAY) == (
        "## Needs you\n- [x] owed: Ticked (since 2026-10-01) _(closed: ticked 2026-10-09)_\n"
        "- [-] owed: Dropped (since 2026-10-01) _(closed: ticked 2026-10-09)_\n"
        "- [x] owed: Kept (since 2026-10-01) _(closed: ticked 2026-10-02)_\n"
        "- [x] owed: Old (since 2026-10-01) _(closed: PR merged 2026-09-01)_\n- [ ] owed: Open (since 2026-10-01)\n")


def test_check_closes_a_merged_or_closed_pr_and_leaves_an_open_one(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "Merged one", "2026-10-08", evidence="https://github.com/acme/shop/pull/7")
    alerts = []
    assert now.check(vault, TODAY, alerts.append, gh_stub(tmp_path, "MERGED")) == 1
    assert ("- [x] owed: Merged one [due:: 2026-11-07] (since 2026-10-08, https://github.com/acme/shop/pull/7) "
            "_(closed: PR merged 2026-10-09)_") in page(vault)
    now.add(vault, "work", "owed", "Closed one", TODAY, evidence="https://github.com/acme/shop/pull/8")
    now.check(vault, TODAY, alerts.append, gh_stub(tmp_path, "CLOSED"))
    assert "_(closed: PR closed 2026-10-09)_" in page(vault).split("Closed one")[1]
    now.add(vault, "work", "owed", "Open one", TODAY, evidence="https://github.com/acme/shop/pull/9")
    assert now.check(vault, TODAY, alerts.append, gh_stub(tmp_path, "OPEN")) == 0
    assert "- [ ] owed: Open one" in page(vault)
    assert alerts == []


def test_check_closes_a_finished_work_order_only(vault, tmp_path):
    prepare(vault)
    order(vault, "2026-10-08-done-item", "done")
    order(vault, "2026-10-08-running-item", "running")
    now.add(vault, "work", "waiting", "The done item", TODAY, evidence="2026-10-08-done-item")
    now.add(vault, "work", "waiting", "The running item", TODAY, evidence="2026-10-08-running-item")
    now.add(vault, "work", "waiting", "A ticket", TODAY, evidence="EX-12")
    assert now.check(vault, TODAY, [].append, gh_stub(tmp_path)) == 1
    text = page(vault)
    assert "- [x] waiting: The done item [due:: 2026-11-08] (since 2026-10-09, 2026-10-08-done-item) _(closed: Work Order done 2026-10-09)_" in text
    assert "- [ ] waiting: The running item" in text
    assert "- [ ] waiting: A ticket" in text
    assert not (tmp_path / "gh.args").exists()


def test_a_failed_check_leaves_the_line_open_and_the_third_failure_alerts_once(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "PR", TODAY, evidence="https://github.com/acme/shop/pull/7")
    alerts = []
    for _ in range(4):
        now.check(vault, TODAY, alerts.append, gh_stub(tmp_path, "", rc=1))
    assert "- [ ] owed: PR" in page(vault)
    assert len(alerts) == 1 and "failed 3 times today" in alerts[0]
    assert len((vault / "system/logs/now-2026-10.jsonl").read_text().splitlines()) == 4
    now.check(vault, TODAY, alerts.append, str(tmp_path / "no-such-gh"))
    assert "- [ ] owed: PR" in page(vault)


def test_check_writes_only_when_it_closes_a_line_and_the_next_write_stamps_hand_ticks(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "A", TODAY)
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("- [ ] owed: A", "- [x] owed: A"))
    before = path.read_text()
    now.check(vault, TODAY, [].append, gh_stub(tmp_path))
    assert path.read_text() == before  # fewer server rewrites of a page the client edits
    now.add(vault, "work", "owed", "B", TODAY, evidence="https://github.com/acme/shop/pull/7")
    assert "- [x] owed: A [due:: 2026-11-08] (since 2026-10-09) _(closed: ticked 2026-10-09)_" in page(vault)


def test_check_keeps_a_tick_made_while_gh_runs(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "Call vendor", TODAY)
    now.add(vault, "work", "owed", "PR", TODAY, evidence="https://github.com/acme/shop/pull/7")
    stub = tmp_path / "gh"
    stub.write_text(f"#!/bin/bash\nsed -i 's/- \\[ \\] owed: Call vendor/- [x] owed: Call vendor/' "
                    f"{vault}/wiki/work/Now.md\necho MERGED\n")
    stub.chmod(0o755)
    assert now.check(vault, TODAY, [].append, str(stub)) == 1
    text = page(vault)
    assert "- [x] owed: Call vendor [due:: 2026-11-08] (since 2026-10-09)" in text
    assert "_(closed: PR merged 2026-10-09)_" in text


def test_check_and_the_stamp_keep_both_fields(vault, tmp_path):
    prepare(vault)  # Now clock spec §5: check rewrites a line by prefix, so the fields survive a close
    now.add(vault, "work", "owed", "Pick it", TODAY, "vendor", "https://github.com/acme/shop/pull/7", rec="CSV: it loads")
    now.add(vault, "work", "owed", "Ticked", TODAY, rec="Yes: fine")
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("- [ ] owed: Ticked", "- [x] owed: Ticked"))
    assert now.check(vault, TODAY, [].append, gh_stub(tmp_path, "MERGED")) == 1
    closed = [line for line in page(vault).splitlines() if line.startswith("- [x] ")]
    assert closed == ["- [x] owed: Pick it [rec:: CSV: it loads] [due:: 2026-10-12] (vendor, since 2026-10-09, "
                      "https://github.com/acme/shop/pull/7) _(closed: PR merged 2026-10-09)_",
                      "- [x] owed: Ticked [rec:: Yes: fine] [due:: 2026-11-08] (since 2026-10-09) "
                      "_(closed: ticked 2026-10-09)_"]
    assert now.stamp(page(vault), "2026-10-30") == page(vault)  # kept until archived


def test_a_failed_pr_check_skips_the_other_prs_this_tick(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "One", TODAY, evidence="https://github.com/acme/shop/pull/7")
    now.add(vault, "personal", "owed", "Two", TODAY, evidence="https://github.com/acme/shop/pull/8")
    order(vault, "2026-10-08-done-item", "done")
    now.add(vault, "work", "waiting", "Order", TODAY, evidence="2026-10-08-done-item")
    assert now.check(vault, TODAY, [].append, str(tmp_path / "no-such-gh")) == 1  # the Work Order still closes
    assert len((vault / "system/logs/now-2026-10.jsonl").read_text().splitlines()) == 1


def test_review_groups_closed_stale_and_duplicate_lines_and_writes_nothing(vault, tmp_path):
    # Lull review (#145): stale is open more than stale_days with no evidence; a duplicate is the same statement
    # after lowercasing and collapsing whitespace, whatever the kind, and without its [rec::] and [due::] fields
    # (Now clock spec §5: the two duplicates below carry different clocks).
    prepare(vault)
    now.add(vault, "work", "owed", "Merged one", "2026-09-01", evidence="https://github.com/acme/shop/pull/7")
    now.add(vault, "work", "owed", "Old one", "2026-09-24")
    now.add(vault, "work", "owed", "Fourteen days", "2026-09-25")
    now.add(vault, "work", "owed", "Send the  report", "2026-10-01")
    now.add(vault, "work", "draft", "send the report", TODAY)
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("## Waiting\n", "## Waiting\n- [ ] call the bank back\n"))
    before = path.read_text()
    assert now.review(vault, "work", TODAY, gh=gh_stub(tmp_path, "MERGED")) == {
        "closed": ["- [ ] owed: Merged one [due:: 2026-10-01] (since 2026-09-01, https://github.com/acme/shop/pull/7) "
                   "_(closed: PR merged)_"],
        "stale": ["- [ ] owed: Old one [due:: 2026-10-24] (since 2026-09-24)"],
        "duplicate": ["- [ ] owed: Send the  report [due:: 2026-10-31] (since 2026-10-01)",
                      "- [ ] draft: send the report [due:: 2026-11-08] (since 2026-10-09)"],
        "unreadable": [], "long": [], "page_bytes": len(before.encode())}
    assert now.review(vault, "work", TODAY, stale_days=13, gh=gh_stub(tmp_path, "OPEN"))["stale"] == [
        "- [ ] owed: Old one [due:: 2026-10-24] (since 2026-09-24)",
        "- [ ] owed: Fourteen days [due:: 2026-10-25] (since 2026-09-25)"]
    assert path.read_text() == before
    assert not (vault / "system/logs").exists()
    assert now.review(vault, "personal", TODAY) == {"closed": [], "stale": [], "duplicate": [], "unreadable": [],
                                                    "long": [], "page_bytes": 0}


HEAD = "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: {p}\n---\n# Now\n\n## Needs you\n"
# Blank lines between the groups and before the count, so Markdown renders each bold label on its own line and the
# count never folds into the last bullet (live acceptance, 2026-10-15).
OVERDUE = ("**1 to 7 days over**\n"
           "- owed: Seven days [due:: 2026-10-13] (since 2026-10-01)\n"
           "- owed: One day [rec:: Yes: cheap] [due:: 2026-10-19] (since 2026-10-01)\n"
           "\n"
           "**8 to 30 days over**\n"
           "- draft: Thirty days [due:: 2026-09-20] (since 2026-09-01)\n"
           "- waiting: Eight days [due:: 2026-10-12] (Avery Sample, since 2026-10-01, EX-1)\n"
           "\n"
           "**More than 30 days over**\n"
           "- owed: Thirty-one days [due:: 2026-09-19] (since 2026-09-01)\n"
           "\n"
           "2 of 8 open lines carry no clock.")


def overdue_pages(vault):
    write(vault, "wiki/work/Now.md", HEAD.format(p="work") +
          "- [ ] owed: One day [rec:: Yes: cheap] [due:: 2026-10-19] (since 2026-10-01)\n"
          "- [ ] owed: Seven days [due:: 2026-10-13] (since 2026-10-01)\n"
          "- [ ] owed: Due today [due:: 2026-10-20] (since 2026-10-01)\n"
          "- [ ] owed: No clock (since 2026-10-01)\n"
          "- [x] owed: Ticked [due:: 2026-09-01] (since 2026-08-01) _(closed: ticked 2026-10-19)_\n"
          "- [-] owed: Dropped [due:: 2026-09-01] (since 2026-08-01) _(closed: ticked 2026-10-19)_\n"
          "\n## Waiting\n- [ ] waiting: Eight days [due:: 2026-10-12] (Avery Sample, since 2026-10-01, EX-1)\n")
    write(vault, "wiki/personal/Now.md", HEAD.format(p="personal") +
          "- [ ] owed: Thirty-one days [due:: 2026-09-19] (since 2026-09-01)\n"
          "- [ ] draft: Thirty days [due:: 2026-09-20] (since 2026-09-01)\n"
          "\n## Waiting\n- [ ] call the bank back\n")


def test_overdue_groups_both_pages_by_days_over_and_counts_clockless_lines(vault):
    # Now clock spec §7: open lines with due before the date, oldest due first in each group, then the
    # count of open lines with no clock; ticked and dropped lines and a line due on the date are left out.
    prepare(vault)
    overdue_pages(vault)
    before = (page(vault), page(vault, "personal"))
    assert now.overdue(vault, "2026-10-20") == OVERDUE
    assert (page(vault), page(vault, "personal")) == before
    assert not (vault / "system/logs").exists()


def test_overdue_prints_ten_lines_fewest_days_over_first_then_a_count(vault):
    prepare(vault)  # Now clock spec §7; phase A follow-up: at most 10 lines
    write(vault, "wiki/work/Now.md", HEAD.format(p="work") + "".join(
        f"- [ ] owed: Item {i} [due:: 2026-10-01] (since 2026-09-01)\n" for i in range(40))
          + "- [ ] owed: Recent [due:: 2026-10-18] (since 2026-09-01)\n")
    out = now.overdue(vault, "2026-10-20").split("\n\n")
    assert out[0] == "**1 to 7 days over**\n- owed: Recent [due:: 2026-10-18] (since 2026-09-01)"
    assert out[1].splitlines()[0] == "**8 to 30 days over**" and len(out[1].splitlines()) == 10
    assert out[2] == "and 31 more of 41 overdue lines; the Now pages hold them all."


def test_overdue_prints_nothing_when_all_lines_are_on_time(vault):
    prepare(vault)  # Now clock spec §7
    write(vault, "wiki/work/Now.md", HEAD.format(p="work") + "".join(
        f"- [ ] owed: Item {i} [due:: 2026-10-01] (since 2026-09-01)\n" for i in range(40)))
    assert now.overdue(vault, "2026-10-01") == ""
    assert now.overdue(vault, "2026-09-01") == ""


def test_cli_overdue_prints_the_groups_and_refuses_a_bad_date(vault):
    prepare(vault)  # Now clock spec §7
    overdue_pages(vault)
    r = cli(vault, "overdue", "--date", "2026-10-20")
    assert (r.returncode, r.stdout) == (0, OVERDUE + "\n"), r.stderr
    assert cli(vault, "overdue", "--date", "tomorrow").returncode == 2
    assert not (vault / "system/run.lock").exists()


def test_review_reports_a_failed_pr_check_and_skips_the_other_prs(vault, tmp_path):
    prepare(vault)  # (#145)
    now.add(vault, "work", "owed", "One", TODAY, evidence="https://github.com/acme/shop/pull/7")
    now.add(vault, "work", "owed", "Two", TODAY, evidence="https://github.com/acme/shop/pull/8")
    fails = []
    found = now.review(vault, "work", TODAY, gh=str(tmp_path / "no-such-gh"), on_fail=lambda l, r: fails.append(r))
    assert found["closed"] == []
    assert fails == ["gh is not installed"]


def test_review_lists_a_line_with_a_field_after_the_parenthesis_as_unreadable(vault):
    # #166 clock spec §3, review finding 1: the line no longer parses; review lists it and repairs nothing. A plain
    # hand-written line is not listed.
    prepare(vault)
    bad = "- [ ] owed: Pick format (since 2026-10-01) [due:: 2026-10-20]"
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          f"---\n# Now\n\n## Needs you\n{bad}\n- [ ] call the bank back\n\n## Waiting\n")
    before = page(vault)
    assert now.review(vault, "work", TODAY)["unreadable"] == [bad]
    r = cli(vault, "review", "--partition", "work")
    assert r.stdout == (f"## Unreadable lines (1): move the text or the [rec::] or [due::] field after the parenthesis "
                        f"back before it\n{bad}\n")
    assert page(vault) == before


def test_review_lists_a_line_with_an_update_appended_after_the_parenthesis(vault):
    # #211: a live page had 48 of 95 lines like this; review and check skipped them without a word
    prepare(vault)
    bad = "- [ ] owed: Send it (Ann, since 2026-10-01) *Update 2026-10-05:* sent the draft"
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          f"---\n# Now\n\n## Needs you\n{bad}\n- [ ] call the bank back\n\n## Waiting\n")
    assert now.review(vault, "work", TODAY)["unreadable"] == [bad]


def test_a_line_with_trailing_space_or_a_crlf_end_still_parses(vault, tmp_path):
    # Audit C12: an editor's trailing space or CRLF must not hide a line from dedupe and evidence checks.
    prepare(vault)
    now.add(vault, "work", "owed", "Spaced", TODAY, evidence="https://github.com/acme/shop/pull/7")
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("pull/7)", "pull/7)  \r"))
    assert now.add(vault, "work", "owed", "Spaced", TODAY)[0] == "exists"
    assert now.check(vault, TODAY, [].append, gh_stub(tmp_path, "MERGED")) == 1


def test_a_reopened_line_loses_its_stamp():
    text = "- [ ] owed: Again (since 2026-10-01) _(closed: ticked 2026-10-02)_\n"
    assert now.stamp(text, TODAY) == "- [ ] owed: Again (since 2026-10-01)\n"


def test_seed_turns_wikilinks_into_plain_text(vault):
    prepare(vault)
    write(vault, "briefings/2026-10-08.md", "### 1. Objectives\n- [ ] DTCC: Change ([[dtcc-c1|C1]]) and [[Plan]]\n### 2.\n")
    now.seed(vault, "work", TODAY)
    assert now.open_lines(page(vault)) == ["- [ ] owed: DTCC: Change (C1) and Plan (since 2026-10-08)"]


def test_seed_takes_the_previous_briefs_open_objectives_once(vault):
    prepare(vault)
    write(vault, "briefings/archive/2026-10/2026-10-07.md",
          "---\ntype: briefing\n---\n### 1. Active Objectives\n- [ ] **Ask** about the 409 _(open since 2026-10-01, 6 days)_\n"
          "- [ ] **stale** **Old** thing _(open since 2026-09-20)_\n- [x] **Done**\n- [ ] DTCC: Change ([[c1]])\n"
          "### 2. Unavailable Sources\n- [ ] not an objective\n")
    assert now.seed(vault, "work", "2026-10-09") == 3
    assert now.open_lines(page(vault)) == [
        "- [ ] owed: **Ask** about the 409 (since 2026-10-01)",
        "- [ ] owed: **Old** thing (since 2026-09-20)",
        "- [ ] owed: DTCC: Change (c1) (since 2026-10-07)"]
    assert now.seed(vault, "work", "2026-10-09") == 0


def test_seed_with_nothing_to_carry_writes_no_page(vault):
    # An empty page written by brief prep seconds before the brief publishes would trip the gate's 60 s check; the
    # brief creates the page itself when it has a line to add.
    prepare(vault)
    assert now.seed(vault, "work", TODAY) == 0
    assert not now.page_path(vault, "work").exists()
    assert now.seed(vault, "shared", TODAY) == 0


def cli(vault, *args, env=None):
    shutil.copytree(REPO / "system" / "scripts", vault / "system" / "scripts", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__"))
    return subprocess.run([sys.executable, str(vault / "system/scripts/now.py"), *args], cwd=vault,
                          capture_output=True, text=True, env={**os.environ, **(env or {})})


def test_cli_add_list_and_usage(vault):
    prepare(vault)
    r = cli(vault, "add", "--partition", "work", "--kind", "owed", "--statement", "Send it", "--who", "Blake")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("added: - [ ] owed: Send it [due:: ")
    cli(vault, "add", "--partition", "personal", "--kind", "draft", "--statement", "Reply to Sam")
    out = cli(vault, "list").stdout.splitlines()
    assert out[0] == "## work" and out[1].startswith("- [ ] owed: Send it") and out[2] == "## personal"
    assert cli(vault, "list", "--partition", "personal").stdout.startswith("- [ ] draft: Reply to Sam")
    assert cli(vault, "add", "--partition", "shared", "--kind", "owed", "--statement", "x").returncode == 2
    assert cli(vault, "seed", "yesterday").returncode == 2


def test_cli_add_takes_rec_and_due_and_exits_2_on_a_later_due(vault):
    prepare(vault)  # Now clock spec §4, §5
    r = cli(vault, "add", "--partition", "work", "--kind", "owed", "--statement", "Pick it", "--who", "vendor",
            "--rec", "CSV: it loads", "--due", "2030-01-02")
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("added: - [ ] owed: Pick it [rec:: CSV: it loads] [due:: 2030-01-02] (vendor, since ")
    before = page(vault)
    r = cli(vault, "add", "--partition", "work", "--kind", "owed", "--statement", "Pick it", "--due", "2030-01-03")
    assert r.returncode == 2
    assert "would loosen the clock (due 2030-01-02)" in r.stderr
    assert page(vault) == before


def test_cli_review_prints_only_grouped_findings_and_exits_0(vault):
    prepare(vault)  # (#145)
    assert cli(vault, "review", "--partition", "work").stdout == ""
    now.add(vault, "work", "owed", "Old one", "2020-01-01")
    now.add(vault, "work", "owed", "Same thing", "2020-01-01")
    now.add(vault, "work", "waiting", "same  thing", TODAY)
    r = cli(vault, "review", "--partition", "work")
    assert r.returncode == 0, r.stderr
    assert r.stdout == ("## Stale: open more than 14 days with no evidence\n"
                        "- [ ] owed: Old one [due:: 2020-01-31] (since 2020-01-01)\n"
                        "- [ ] owed: Same thing [due:: 2020-01-31] (since 2020-01-01)\n"
                        "## Duplicates\n- [ ] owed: Same thing [due:: 2020-01-31] (since 2020-01-01)\n"
                        "- [ ] waiting: same  thing [due:: 2026-11-08] (since 2026-10-09)\n")
    assert cli(vault, "review", "--partition", "shared").returncode == 2


def test_set_replaces_the_statement_and_keeps_every_other_field(vault):
    # #211: rewrite a line instead of appending dated updates to it
    prepare(vault)
    now.add(vault, "work", "owed", "Send the deck 2026-10-01: drafted 2026-10-05: sent v1", TODAY, who="Ann",
            evidence="EX-1", rec="v2: shorter", due="2026-10-20")
    now.add(vault, "work", "waiting", "Other thing", TODAY)
    line = now.set_statement(vault, "work", "send the DECK", "Send the deck v2", TODAY)
    assert line == "- [ ] owed: Send the deck v2 [rec:: v2: shorter] [due:: 2026-10-20] (Ann, since 2026-10-09, EX-1)"
    assert now.open_lines(page(vault)) == [line, "- [ ] waiting: Other thing [due:: 2026-11-08] (since 2026-10-09)"]


def test_set_refuses_no_match_two_matches_and_a_clock_field_and_writes_nothing(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Call Ann", TODAY)
    now.add(vault, "work", "owed", "Call Ann's team", TODAY)
    before = page(vault)
    for match, statement in (("nobody", "x"), ("call ann", "x"), ("team", "x [due:: 2026-10-30]")):
        try:
            now.set_statement(vault, "work", match, statement, TODAY)
        except ValueError:
            continue
        raise AssertionError(f"set accepted {match!r} -> {statement!r}")
    assert page(vault) == before


def test_set_rewrites_a_line_with_text_after_its_parenthesis(vault):
    # review: the live case (update notes typed after the parenthesis) was a dead end for set
    prepare(vault)
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          "---\n# Now\n\n## Needs you\n- [ ] owed: Send it [due:: 2026-10-20] (Ann, since 2026-10-01) *Update:* sent\n"
          "\n## Waiting\n")
    assert now.set_statement(vault, "work", "send it", "Send it, v2 sent", TODAY) == (
        "- [ ] owed: Send it, v2 sent [due:: 2026-10-20] (Ann, since 2026-10-01)")


def test_set_refuses_an_empty_match_and_a_duplicate_statement(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Alpha", TODAY)
    now.add(vault, "work", "owed", "Beta", TODAY)
    before = page(vault)
    for match, statement in (("  ", "x"), ("beta", "Alpha")):
        try:
            now.set_statement(vault, "work", match, statement, TODAY)
        except ValueError:
            continue
        raise AssertionError(f"set accepted {match!r} -> {statement!r}")
    assert page(vault) == before


def test_a_hand_written_line_with_since_text_is_not_unreadable(vault):
    prepare(vault)
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          "---\n# Now\n\n## Needs you\n- [ ] call Bob (since 2026-10-01) about invoice\n\n## Waiting\n")
    assert now.review(vault, "work", TODAY)["unreadable"] == []


def test_cli_set_and_review_long_lines_and_page_size(vault):
    prepare(vault)
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          f"---\n# Now\n\n## Needs you\n- [ ] owed: Long {'update ' * 45}(since 2026-10-01, EX-1)\n")
    r = cli(vault, "review", "--partition", "work")
    assert r.returncode == 0, r.stderr
    assert ("## Long lines (over 300 characters): shorten with now.py set, history with now.py note\n"
            "- [ ] owed: Long update") in r.stdout
    r = cli(vault, "set", "--partition", "work", "--match", "long update", "--statement", "Short")
    assert r.returncode == 0, r.stderr
    assert r.stdout == "set: - [ ] owed: Short (since 2026-10-01, EX-1)\n"
    assert cli(vault, "review", "--partition", "work").stdout == ""
    assert cli(vault, "set", "--partition", "work", "--match", "nothing", "--statement", "x").returncode == 2
    for i in range(140):
        now.add(vault, "work", "owed", f"Item {i} " + "word " * 40, TODAY)
    assert "## Page size: " in cli(vault, "review", "--partition", "work").stdout


def test_cli_waits_for_run_lock_and_exits_4_when_busy(vault):
    prepare(vault)
    (vault / "system").mkdir(exist_ok=True)
    with open(vault / "system/run.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        r = cli(vault, "add", "--partition", "work", "--kind", "owed", "--statement", "x", env={"NOW_LOCK_WAIT": "0"})
    assert r.returncode == 4
    assert "run.lock busy" in r.stderr
    assert not (vault / "wiki/work/Now.md").exists()


def test_a_hand_written_line_is_listed_and_left_alone(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "A", TODAY)
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("## Waiting\n", "## Waiting\n- [ ] call the bank back\n"))
    assert now.check(vault, TODAY, [].append, gh_stub(tmp_path)) == 0
    assert now.open_lines(page(vault)) == ["- [ ] owed: A [due:: 2026-11-08] (since 2026-10-09)", "- [ ] call the bank back"]


def test_cli_add_seeds_the_missing_default_page_first(vault):
    prepare(vault)
    write(vault, "briefings/2026-10-01.md", "### 1. Objectives\n- [ ] **Old objective**\n### 2.\n")
    r = cli(vault, "add", "--partition", "work", "--kind", "owed", "--statement", "New")
    assert r.returncode == 0, r.stderr
    lines = now.open_lines(page(vault))
    assert lines[0] == "- [ ] owed: **Old objective** (since 2026-10-01)"
    assert lines[1].startswith("- [ ] owed: New [due:: ")


def test_cli_list_refuses_an_unknown_partition(vault):
    prepare(vault)
    assert cli(vault, "list", "--partition", "../x").returncode == 2


# --- phase A: the archive, notes under a line, the 300-character cap ---

def archive_note(vault, month, partition="work"):
    return (vault / "wiki" / partition / "now-archive" / f"{month}.md").read_text(encoding="utf-8")


def test_archive_moves_closed_lines_with_their_notes_and_keeps_open_ones(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Done thing", TODAY)
    now.add(vault, "work", "owed", "Open thing", TODAY)
    now.note(vault, "work", "done thing", "asked Blake", TODAY)
    now.note(vault, "work", "open thing", "still going", TODAY)
    path = vault / "wiki/work/Now.md"
    path.write_text(path.read_text().replace("- [ ] owed: Done thing", "- [x] owed: Done thing"))
    assert now.archive(vault, "work", TODAY) == 1
    text = page(vault)
    assert "Done thing" not in text and "asked Blake" not in text
    assert "- [ ] owed: Open thing" in text and "  - 2026-10-09: still going" in text
    archived = archive_note(vault, "2026-10")
    assert archived.startswith('---\ntype: concept\ntags: [now-archive]\ncompiled_at: "2026-10-09"\npartition: work\n---\n')
    assert archived.endswith("- [x] owed: Done thing [due:: 2026-11-08] (since 2026-10-09) _(closed: ticked 2026-10-09)_\n"
                             "  - 2026-10-09: asked Blake\n")


def test_archive_appends_by_stamp_month_and_writes_a_line_once(vault):
    prepare(vault)
    write(vault, "wiki/work/Now.md", "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          "---\n# Now\n\n## Needs you\n- [x] owed: Sept (since 2026-09-01) _(closed: ticked 2026-09-30)_\n"
          "- [-] owed: Oct (since 2026-09-01) _(closed: ticked 2026-10-02)_\n- [ ] owed: Open (since 2026-10-01)\n")
    before = page(vault)
    assert now.archive(vault, "work", TODAY) == 2
    assert "Sept" in archive_note(vault, "2026-09") and "Oct" in archive_note(vault, "2026-10")
    (vault / "wiki/work/Now.md").write_text(before)  # a crash after the archive write, before the page write
    now.archive(vault, "work", TODAY)
    assert archive_note(vault, "2026-09").count("owed: Sept") == 1
    assert page(vault).endswith("## Needs you\n- [ ] owed: Open (since 2026-10-01)\n")
    assert now.archive(vault, "work", TODAY) == 0


def test_note_lands_after_the_last_note_of_the_one_matching_line(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Send the report", TODAY)
    now.add(vault, "work", "owed", "Send the invoice", TODAY)
    now.note(vault, "work", "report", "first", TODAY)
    now.note(vault, "work", "report", "second", "2026-10-10")
    lines = page(vault).split("\n")
    i = next(n for n, line in enumerate(lines) if "Send the report" in line)
    assert lines[i + 1:i + 4] == ["  - 2026-10-09: first", "  - 2026-10-10: second", "- [ ] owed: Send the invoice "
                                  "[due:: 2026-11-08] (since 2026-10-09)"]
    for bad in ("send the", "nothing"):
        try:
            now.note(vault, "work", bad, "x", TODAY)
            raise AssertionError("no error")
        except ValueError as exc:
            assert "open lines match" in str(exc)


def test_notes_follow_set_and_check_and_are_never_open_lines(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "Merge it", TODAY, evidence="https://github.com/acme/shop/pull/7")
    now.note(vault, "work", "merge it", "reviewer asked for a test", TODAY)
    now.set_statement(vault, "work", "merge it", "Merge the export PR", TODAY)
    assert now.open_lines(page(vault)) == [
        "- [ ] owed: Merge the export PR [due:: 2026-11-08] (since 2026-10-09, https://github.com/acme/shop/pull/7)"]
    now.check(vault, TODAY, [].append, gh_stub(tmp_path, "MERGED"))
    lines = page(vault).split("\n")
    i = next(n for n, line in enumerate(lines) if "Merge the export PR" in line)
    assert lines[i].startswith("- [x] ") and lines[i + 1] == "  - 2026-10-09: reviewer asked for a test"
    assert now.overdue(vault, "2027-01-01") == ""


def test_add_and_set_refuse_a_line_over_300_characters(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "short one", TODAY)
    for call in (lambda: now.add(vault, "work", "owed", "x" * 300, TODAY),
                 lambda: now.set_statement(vault, "work", "short", "y" * 300, TODAY)):
        try:
            call()
            raise AssertionError("no error")
        except ValueError as exc:
            assert "limit is 300" in str(exc)
    assert now.add(vault, "work", "owed", "z" * 240, TODAY)[0] == "added"


def test_fit_cuts_a_machine_writers_statement_to_the_cap(vault):
    prepare(vault)
    status, line = now.add(vault, "work", "owed", "x" * 400, TODAY, "Pat", "https://example.com/t/1", fit=True)
    assert status == "added"
    assert len(line) == now.MAX_LINE
    assert "x…" in line


def test_fit_staged_cuts_only_the_brief_added_long_lines(vault):
    head = "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n---\n# Now\n\n## Needs you\n"
    old = f"- [ ] owed: {'w' * 400} (since 2026-10-01)"
    added = f"- [ ] owed: {'e' * 320} [due:: 2026-11-08] (since {TODAY})"
    short = f"- [ ] owed: Short one [due:: 2026-11-08] (since {TODAY})"
    write(vault, "wiki/work/Now.md", head + old + "\n")
    write(vault, "wiki/.staging/r1/wiki/work/Now.md", head + "\n".join([old, added, short]) + "\n")
    assert now.fit_staged(vault, "r1") == 1
    lines = (vault / "wiki/.staging/r1/wiki/work/Now.md").read_text(encoding="utf-8").split("\n")
    assert lines[-4] == old
    assert lines[-2] == short
    assert len(lines[-3]) <= now.MAX_LINE
    assert lines[-3].endswith(f"e… [due:: 2026-11-08] (since {TODAY})")
    assert now.fit_staged(vault, "missing-run") == 0


def test_fit_staged_keeps_the_fields_and_leaves_what_it_cannot_rebuild(vault):
    head = "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n---\n# Now\n\n## Needs you\n"
    full = (f"- [ ] owed: {'f' * 250} [rec:: ship it: done] [due:: 2026-11-08] "
            f"(Pat Sample, since {TODAY}, https://github.com/acme/shop/pull/7)")
    trailing = f"- [ ] owed: {'t' * 200} (since {TODAY}) {'u' * 120}"
    floor = f"- [ ] owed: Decide vendor [rec:: {'r' * 280}] (since {TODAY})"
    write(vault, "wiki/.staging/r2/wiki/work/Now.md", head + "\n".join([full, trailing, floor]) + "\n")
    assert now.fit_staged(vault, "r2") == 1
    lines = (vault / "wiki/.staging/r2/wiki/work/Now.md").read_text(encoding="utf-8").split("\n")
    assert len(lines[-4]) == now.MAX_LINE
    assert lines[-4].endswith("f… [rec:: ship it: done] [due:: 2026-11-08] "
                              f"(Pat Sample, since {TODAY}, https://github.com/acme/shop/pull/7)")
    assert lines[-3:-1] == [trailing, floor]


def test_a_long_line_written_before_the_cap_keeps_working(vault):
    prepare(vault)
    long = f"- [ ] owed: {'w' * 400} (since 2026-10-01)"
    write(vault, "wiki/work/Now.md", f"---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n"
          f"---\n# Now\n\n## Needs you\n{long}\n")
    assert now.add(vault, "work", "owed", "w" * 400, TODAY)[0] == "exists"
    assert now.review(vault, "work", TODAY)["long"] == [long]
    now.set_statement(vault, "work", "wwww", "Short again", TODAY)
    assert now.review(vault, "work", TODAY)["long"] == []


def test_a_github_issue_url_is_evidence(vault, tmp_path):
    prepare(vault)
    now.add(vault, "work", "owed", "Closed issue", TODAY, evidence="https://github.com/acme/shop/issues/3")
    assert now.check(vault, TODAY, [].append, gh_stub(tmp_path, "CLOSED")) == 1
    assert "_(closed: issue closed 2026-10-09)_" in page(vault)
    assert "issue view https://github.com/acme/shop/issues/3" in (tmp_path / "gh.args").read_text()
    now.add(vault, "work", "owed", "Open issue", TODAY, evidence="https://github.com/acme/shop/issues/4")
    assert now.check(vault, TODAY, [].append, gh_stub(tmp_path, "OPEN")) == 0
    alerts = []
    for _ in range(3):
        now.check(vault, TODAY, alerts.append, gh_stub(tmp_path, "", rc=1))
    assert "- [ ] owed: Open issue" in page(vault) and len(alerts) == 1


def test_add_redacts_each_field_and_the_line_still_parses(vault):
    prepare(vault)
    status, line = now.add(vault, "work", "owed", f"Rotate {KEY} today", TODAY, "Pat",
                           "https://example.com/x?token=abc123", rec=f"rotate: password={KEY}")
    assert status == "added"
    assert KEY not in page(vault)
    m = now.LINE.match(line)
    assert m.group("evidence") is None
    assert now.fields(m.group("statement"))[1] == "rotate: password=REDACTED:github_token"
    assert now.add(vault, "work", "owed", f"Rotate {KEY} today", TODAY, "Pat")[0] == "exists"


def test_set_and_note_redact_and_note_fits(vault):
    prepare(vault)
    now.add(vault, "work", "owed", "Rotate the key", TODAY)
    assert KEY not in now.set_statement(vault, "work", "rotate", f"Rotate {KEY}", TODAY)
    assert KEY not in now.note(vault, "work", "rotate", f"token: {KEY}", TODAY)
    with pytest.raises(ValueError, match="limit is 300"):
        now.note(vault, "work", "rotate", "n" * 300, TODAY)
    noted = now.note(vault, "work", "rotate", "n" * 300, TODAY, fit=True)
    assert noted.endswith("n…")
    assert len(noted) == now.MAX_LINE


def test_a_link_across_the_wall_is_refused_and_index_and_shared_are_not(vault):
    prepare(vault)
    write(vault, "wiki/personal/concepts/diary.md", "---\ntype: concept\n---\n")
    write(vault, "wiki/shared/concepts/glossary.md", "---\ntype: concept\n---\n")
    with pytest.raises(ValueError, match="partition wall"):
        now.add(vault, "work", "owed", "Read [[diary]]", TODAY)
    assert now.add(vault, "work", "owed", "See [[glossary]] and [[Index]]", TODAY)[0] == "added"


def test_a_symlinked_now_page_is_refused(vault, tmp_path):
    prepare(vault)
    (tmp_path / "elsewhere").mkdir()
    shutil.rmtree(vault / "wiki" / "work")   # the fixture holds wiki/work/
    (vault / "wiki" / "work").symlink_to(tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="symlink"):
        now.add(vault, "work", "owed", "Anything", TODAY)
    assert not any((tmp_path / "elsewhere").iterdir())


def test_check_leaves_an_owner_reopened_long_or_walled_line_alone(vault, tmp_path):
    prepare(vault)
    write(vault, "wiki/personal/concepts/diary.md", "---\ntype: concept\n---\n")
    kept = [f"- [ ] owed: {'w' * 400} (since 2026-10-01)", "- [ ] owed: Read [[diary]] (since 2026-10-01)"]
    done = "- [ ] owed: Ship it (since 2026-10-01, https://github.com/acme/shop/pull/7)"
    write(vault, "wiki/work/Now.md", "---\ntype: concept\n---\n# Now\n\n## Needs you\n" + "\n".join(kept + [done]) + "\n")
    assert now.check(vault, TODAY, lambda m: None, gh_stub(tmp_path)) == 1
    assert all(line in page(vault).split("\n") for line in kept)


def test_screen_rebuilds_a_canonical_line_and_checks_a_hand_shaped_one_whole(vault):
    prepare(vault)
    line = now.render("owed", f"Rotate {KEY}", "2026-10-01", f"token={KEY}", "", f"rotate: password={KEY}", "2026-11-01")
    once = now.screen(vault, "work", line)
    assert KEY not in once
    assert now.LINE.match(once)
    assert now.screen(vault, "work", once) == once
    assert len(now.screen(vault, "work", now.render("owed", "e" * 320, "2026-10-01"))) == now.MAX_LINE
    hand = "- [ ] owed: two  spaces (since 2026-10-01)"
    assert now.screen(vault, "work", hand) == hand
    with pytest.raises(ValueError, match="credential"):
        now.screen(vault, "work", f"- [ ] owed: two  spaces {KEY} (since 2026-10-01)")


def test_fit_staged_redacts_and_cuts_added_lines(vault):
    head = "---\ntype: concept\ntags: [now]\ncompiled_at: \"2026-10-01\"\npartition: work\n---\n# Now\n\n## Needs you\n"
    old = f"- [ ] owed: Rotate {KEY} (since 2026-10-01)"
    added = f"- [ ] owed: Rotate {KEY} {'e' * 300} (since {TODAY})"
    write(vault, "wiki/work/Now.md", head + old + "\n")
    write(vault, "wiki/.staging/r3/wiki/work/Now.md", head + "\n".join([old, added]) + "\n")
    assert now.fit_staged(vault, "r3") == 1
    lines = (vault / "wiki/.staging/r3/wiki/work/Now.md").read_text(encoding="utf-8").split("\n")
    assert lines[-3] == old
    assert KEY not in lines[-2]
    assert len(lines[-2]) <= now.MAX_LINE
    assert lines[-2].endswith(f"e… (since {TODAY})")
