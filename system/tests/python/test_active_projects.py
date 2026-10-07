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
