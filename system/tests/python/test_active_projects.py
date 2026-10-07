"""active_projects.py: active projects with their next actions and decisions for the brief (issue #65)."""
import importlib.util
import subprocess
import sys

from helpers import REPO, write

SCRIPT = REPO / "system" / "scripts" / "active_projects.py"
_spec = importlib.util.spec_from_file_location("active_projects", SCRIPT)
ap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ap)


def listing(active: str, paused: str = "", done: str = "", partition: str = "work") -> str:
    return (f"---\ntype: concept\ntags: [\"active-projects\"]\ncompiled_at: 2026-10-07\npartition: {partition}\n---\n\n"
            f"# Active Projects\n\n## Active\n{active}\n## Paused\n{paused}\n## Done\n{done}")


def page(body: str, partition: str = "work") -> str:
    return f"---\ntype: concept\ntags: []\ncompiled_at: 2026-10-07\npartition: {partition}\n---\n\n# Project\n\n{body}"


def run(vault, date="2026-10-07"):
    return subprocess.run([sys.executable, str(SCRIPT), date], cwd=vault, capture_output=True, text=True)


# --- the list ---

def test_active_entries_keep_order_and_focus_and_ignore_paused_and_done():
    text = listing("- [[Alpha]]: main focus\n- [[Beta]]\nSome prose.\n  - [[Nested]]\n",
                   paused="- [[Gamma]]\n", done="- [[Delta]]: closed\n")
    assert ap.active_entries(text) == [("Alpha", "main focus"), ("Beta", "")]


def test_active_entries_survive_crlf_and_trailing_spaces_on_the_heading():
    text = listing("- [[Alpha]]: focus\n").replace("## Active\n", "## Active   \n").replace("\n", "\r\n")
    assert ap.active_entries(text) == [("Alpha", "focus")]


def test_active_entries_keep_an_alias_as_written():
    assert ap.active_entries(listing("- [[Alpha|Short]]: f\n")) == [("Alpha|Short", "f")]


# --- the page ---

def test_page_items_take_the_first_three_open_checkboxes_in_order():
    body = ("## Work\n- [x] done\n- [ ] one\n- [-] dropped\n- [X] capital is not open\n"
            "- [ ] two\n  - [ ] nested three\n- [ ] four\n")
    assert ap.page_items(page(body)) == (["one", "two", "nested three"], [])


def test_page_items_split_out_decisions_until_the_next_same_or_higher_heading():
    body = ("### Decisions waiting on me\n- [ ] pick a vendor\n#### Detail\n- [ ] still a decision\n"
            "### Questions\n- [ ] back to next\n")
    assert ap.page_items(page(body)) == (["back to next"], ["pick a vendor", "still a decision"])


def test_page_items_decisions_heading_is_case_insensitive_and_uncapped():
    body = "## DECISIONS\n" + "".join(f"- [ ] d{i}\n" for i in range(5))
    assert ap.page_items(page(body)) == ([], [f"d{i}" for i in range(5)])


def test_page_items_skip_fenced_code_and_keep_inline_code_verbatim():
    body = "```\n- [ ] in a fence\n```\n- [ ] Send the `105` message with **bold** and [[Link]]\n"
    assert ap.page_items(page(body)) == (["Send the `105` message with **bold** and [[Link]]"], [])


def test_page_items_read_a_page_without_frontmatter_and_with_crlf():
    assert ap.page_items("# P\r\n- [ ] one\r\n") == (["one"], [])


# --- the CLI ---

def test_cli_prints_blocks_per_partition_in_order(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Alpha]]: main focus\n- [[Beta]]\n"))
    write(vault, "wiki/work/concepts/Alpha.md", page("## Next\n- [ ] a1\n## Decisions\n- [ ] d1\n"))
    write(vault, "wiki/work/concepts/Beta.md", page("- [x] all done\n"))
    write(vault, "wiki/personal/ActiveProjects.md", listing("- [[Garden]]\n", partition="personal"))
    write(vault, "wiki/personal/concepts/Garden.md", page("- [ ] plant\n", partition="personal"))
    out = run(vault)
    assert out.returncode == 0, out.stderr
    assert out.stdout == (
        "# Active projects for 2026-10-07\n\n"
        "## work\n\n"
        "### [[Alpha]]: main focus\nNext:\n- a1\nDecisions waiting:\n- d1\n\n"
        "### [[Beta]]\nNext:\n- None open.\n\n"
        "## personal\n\n"
        "### [[Garden]]\nNext:\n- plant\n")


def test_cli_resolves_an_alias_and_keeps_the_link_as_written(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Alpha|Short]]: f\n"))
    write(vault, "wiki/work/concepts/Alpha.md", page("- [ ] a1\n"))
    assert "### [[Alpha|Short]]: f\nNext:\n- a1\n" in run(vault).stdout


def test_cli_with_no_lists_prints_none(vault):
    out = run(vault)
    assert out.returncode == 0
    assert out.stdout == "# Active projects for 2026-10-07\n\nNone.\n"


def test_cli_notices_for_missing_ambiguous_and_cross_partition_targets(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Missing]]\n- [[Twin]]\n- [[Garden]]\n- [[Alpha]]\n"))
    write(vault, "wiki/work/concepts/Twin.md", page("- [ ] x\n"))
    write(vault, "wiki/work/entities/Twin.md", page("- [ ] y\n"))
    write(vault, "wiki/personal/concepts/Garden.md", page("- [ ] plant\n", partition="personal"))
    write(vault, "wiki/work/concepts/Alpha.md", page("- [ ] a1\n"))
    out = run(vault)
    assert out.returncode == 0, out.stderr
    assert "### [[Alpha]]\nNext:\n- a1\n" in out.stdout
    assert "Twin]]\nNext" not in out.stdout and "Garden]]\nNext" not in out.stdout
    assert out.stdout.endswith(
        "## Notices\n"
        "- work: [[Missing]] in ActiveProjects does not resolve to a note.\n"
        "- work: [[Twin]] in ActiveProjects matches more than one note; use a path link.\n"
        "- work: [[Garden]] is in personal; list it in that partition's ActiveProjects.\n")


def test_cli_notice_for_an_unreadable_page(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Broken]]\n"))
    (vault / "wiki/work/concepts").mkdir(parents=True, exist_ok=True)
    (vault / "wiki/work/concepts/Broken.md").write_bytes(b"\xff\xfe\x00bad")
    out = run(vault)
    assert out.returncode == 0
    assert "- work: [[Broken]] could not be read.\n" in out.stdout


def test_cli_caps_active_projects_at_ten(vault):
    names = [f"P{i:02d}" for i in range(12)]
    write(vault, "wiki/work/ActiveProjects.md", listing("".join(f"- [[{n}]]\n" for n in names)))
    for n in names:
        write(vault, f"wiki/work/concepts/{n}.md", page("- [ ] go\n"))
    out = run(vault).stdout
    assert out.count("### [[P") == 10 and "[[P10]]" not in out
    assert "- work: only the first 10 active projects are shown.\n" in out


def test_cli_only_notices_still_prints_none_first(vault):
    write(vault, "wiki/work/ActiveProjects.md", listing("- [[Missing]]\n"))
    assert run(vault).stdout == ("# Active projects for 2026-10-07\n\nNone.\n\n## Notices\n"
                                 "- work: [[Missing]] in ActiveProjects does not resolve to a note.\n")


def test_cli_notices_near_miss_active_lines(vault):
    write(vault, "wiki/work/ActiveProjects.md",
          listing("- [[Alpha]]\n1. [[Beta]]\n- **[[Gamma]]**: focus\nPlain prose is fine.\n"))
    write(vault, "wiki/work/concepts/Alpha.md", page("- [ ] a1\n"))
    out = run(vault)
    assert out.returncode == 0, out.stderr
    assert "### [[Alpha]]\nNext:\n- a1\n" in out.stdout
    assert "- work: line in ActiveProjects is not an entry: 1. [[Beta]]\n" in out.stdout
    assert "- work: line in ActiveProjects is not an entry: - **[[Gamma]]**: focus\n" in out.stdout
    assert "Plain prose" not in out.stdout


def test_cli_notices_a_list_without_an_active_heading(vault):
    write(vault, "wiki/work/ActiveProjects.md",
          "---\ntype: concept\ntags: []\ncompiled_at: 2026-10-07\npartition: work\n---\n## Active projects\n- [[Alpha]]\n")
    out = run(vault)
    assert out.returncode == 0, out.stderr
    assert '- work: ActiveProjects has no "## Active" heading.\n' in out.stdout


def test_cli_bad_date_exits_2(vault):
    assert run(vault, "yesterday").returncode == 2
