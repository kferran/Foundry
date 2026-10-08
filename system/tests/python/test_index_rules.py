import sqlite3

from helpers import concept, write
from vaultlib.index import Index, wall_blocked


def build(vault):
    idx = Index(vault)
    idx.refresh()
    return idx


def issues(idx, code=None):
    conn = sqlite3.connect(idx.db_path)
    try:
        sql = "SELECT path, severity, code FROM issues"
        rows = conn.execute(sql + (" WHERE code=?" if code else ""), ((code,) if code else ())).fetchall()
        return sorted(rows)
    finally:
        conn.close()


def issue_messages(idx, code=None):
    """Return (path, severity, code, message) tuples for all issues."""
    conn = sqlite3.connect(idx.db_path)
    try:
        sql = "SELECT path, severity, code, message FROM issues"
        rows = conn.execute(sql + (" WHERE code=?" if code else ""), ((code,) if code else ())).fetchall()
        return sorted(rows)
    finally:
        conn.close()


def query(idx, sql):
    conn = sqlite3.connect(idx.db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_fixture_vault_is_clean(vault):
    assert [i for i in issues(build(vault)) if i[1] == "error"] == []


def test_dead_link_is_warning(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", "[[Nowhere]] [[Index]]"))
    assert issues(build(vault), "dead-link") == [("wiki/work/concepts/A.md", "warning", "dead-link")]


def test_wall_matrix():
    assert wall_blocked("work", "personal") and wall_blocked("personal", "work")
    assert wall_blocked("shared", "work") and wall_blocked("shared", "personal")
    assert not wall_blocked("work", "shared") and not wall_blocked("personal", "shared")
    assert not wall_blocked("work", "work")


def test_partition_walls(vault):
    write(vault, "wiki/work/concepts/W.md", concept("work", "W", "[[Gardening]]"))
    write(vault, "wiki/shared/concepts/S.md", concept("shared", "S", "[[Kafka]]"))
    write(vault, "wiki/personal/concepts/P.md", concept("personal", "P", "[[Git]]"))
    found = issues(build(vault), "partition-wall")
    assert found == [("wiki/shared/concepts/S.md", "error", "partition-wall"),
                     ("wiki/work/concepts/W.md", "error", "partition-wall")]


def test_index_and_briefings_exempt_from_walls(vault):
    write(vault, "briefings/2026-09-30.md", '---\ntype: briefing\ndate: "2026-09-30"\n---\n[[Kafka]] [[Gardening]]')
    assert issues(build(vault), "partition-wall") == []


def test_ambiguous_link_prefers_partition(vault):
    write(vault, "wiki/work/concepts/Dup.md", concept("work", "Dup"))
    write(vault, "wiki/personal/concepts/Dup.md", concept("personal", "Dup"))
    write(vault, "wiki/personal/concepts/User.md", concept("personal", "User", "[[Dup]]"))
    idx = build(vault)
    assert query(idx, "SELECT target_path, ambiguous FROM links WHERE src='wiki/personal/concepts/User.md'") == [("wiki/personal/concepts/Dup.md", 1)]
    assert issues(idx, "partition-wall") == []


def test_ambiguous_link_prefers_active(vault):
    write(vault, "wiki/work/a/Topic.md", concept("work", "Topic", status="deprecated"))
    write(vault, "wiki/work/concepts/Topic.md", concept("work", "Topic"))
    write(vault, "wiki/work/concepts/Ref.md", concept("work", "Ref", "[[Topic]]"))
    assert query(build(vault), "SELECT target_path FROM links WHERE src='wiki/work/concepts/Ref.md'") == [("wiki/work/concepts/Topic.md",)]


def test_link_to_inactive_warns(vault):
    write(vault, "wiki/work/concepts/Old.md", concept("work", "Old", status="deprecated"))
    write(vault, "wiki/work/concepts/New.md", concept("work", "New", "[[Old]]"))
    assert ("wiki/work/concepts/New.md", "warning", "link-to-inactive") in issues(build(vault))


def test_supersession_pair_ok(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[B]]"'))
    write(vault, "wiki/work/concepts/B.md", concept("work", "B", supersedes='["[[A]]"]'))
    idx = build(vault)
    assert [i for i in issues(idx) if i[2].startswith("supersession")] == []
    assert query(idx, "SELECT active FROM notes WHERE path='wiki/work/concepts/A.md'") == [(0,)]


def test_supersession_pair_missing(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[B]]"'))
    write(vault, "wiki/work/concepts/B.md", concept("work", "B"))
    assert issues(build(vault), "supersession-pair") == [("wiki/work/concepts/A.md", "error", "supersession-pair")]


def test_supersession_dangling(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[Ghost]]"'))
    assert issues(build(vault), "supersession-dangling") == [("wiki/work/concepts/A.md", "error", "supersession-dangling")]


def test_supersession_cross_partition(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[B]]"'))
    write(vault, "wiki/shared/concepts/B.md", concept("shared", "B", supersedes='["[[A]]"]'))
    assert issues(build(vault), "supersession-partition") == [("wiki/work/concepts/A.md", "error", "supersession-partition")]


def test_supersession_cycles(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", superseded_by='"[[B]]"', supersedes='["[[C]]"]'))
    write(vault, "wiki/work/concepts/B.md", concept("work", "B", superseded_by='"[[C]]"', supersedes='["[[A]]"]'))
    write(vault, "wiki/work/concepts/C.md", concept("work", "C", superseded_by='"[[A]]"', supersedes='["[[B]]"]'))
    found = {p for p, _, _ in issues(build(vault), "supersession-cycle")}
    assert found == {"wiki/work/concepts/A.md", "wiki/work/concepts/B.md", "wiki/work/concepts/C.md"}


def test_unique_true(vault):
    body = '---\ntype: codebase\nname: {n}\npath: "/tmp"\npartition: work\ndefault: "true"\nsearch_globs: ["*.py"]\n---\n'
    write(vault, "system/codebases/a.md", body.format(n="a"))
    write(vault, "system/codebases/b.md", body.format(n="b"))
    assert len(issues(build(vault), "unique-true")) == 2


def test_orphans(vault):
    write(vault, "wiki/work/concepts/Lonely.md", concept("work", "Lonely"))
    assert issues(build(vault), "orphan") == [("wiki/work/concepts/Lonely.md", "warning", "orphan")]


def test_views_typed_with_defaults(vault):
    write(vault, "wiki/work/concepts/F.md", concept("work", "F", "[[Index]]", is_friction='"true"'))
    write(vault, "wiki/work/concepts/Old.md", concept("work", "Old", status="deprecated"))
    idx = build(vault)
    assert query(idx, "SELECT is_friction, status FROM v_concept WHERE path='wiki/work/concepts/F.md'") == [(1, "canonical")]
    assert query(idx, "SELECT is_friction FROM v_concept WHERE path='wiki/work/concepts/Kafka.md'") == [(0,)]
    assert query(idx, "SELECT count(*) FROM v_concept WHERE path='wiki/work/concepts/Old.md'") == [(0,)]
    assert query(idx, "SELECT active FROM v_concept_all WHERE path='wiki/work/concepts/Old.md'") == [(0,)]


def test_codebase_view_exposes_frontmatter_path_and_partition(vault):
    write(vault, "system/codebases/a.md",
          '---\ntype: codebase\nname: a\npath: "/srv/repo"\npartition: work\nsearch_globs: ["*"]\n---\n')
    idx = build(vault)
    assert query(idx, "SELECT path, fm_path, partition FROM v_codebase") == [("system/codebases/a.md", "/srv/repo", "work")]
    assert query(idx, "SELECT partition FROM v_concept WHERE path='wiki/work/concepts/Kafka.md'") == [("work",)]


def test_dead_link_messages_by_kind(vault):
    """Test that dead link messages are formatted correctly by link kind."""
    # Wikilink in body: [[Nowhere]]
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", "[[Nowhere]]"))
    # Frontmatter wikilink outside sources: supersedes: ["[[Ghost]]"]
    write(vault, "wiki/work/concepts/B.md", concept("work", "B", supersedes='["[[Ghost]]"]'))
    # Markdown link: [x](missing.md)
    write(vault, "wiki/work/concepts/C.md", concept("work", "C", "[x](missing.md)"))
    idx = build(vault)
    messages = issue_messages(idx, "dead-link")
    assert messages == [
        ("wiki/work/concepts/A.md", "warning", "dead-link", "dead link [[Nowhere]]"),
        ("wiki/work/concepts/B.md", "warning", "dead-link", "dead link [[Ghost]]"),
        ("wiki/work/concepts/C.md", "warning", "dead-link", "dead link missing.md"),
    ]


def test_meeting_sources_and_drops_are_not_indexed(vault):
    write(vault, "raw/meetings/FAKE-doc-0001.gdoc.md", '---\ndoc_id: "FAKE-doc-0001"\n---\nsee [[Nowhere]]\n')
    write(vault, "meetings/drop/work/standup.md", "Avery: see [[Nowhere]]\n")
    idx = build(vault)
    assert query(idx, "SELECT path FROM notes WHERE path LIKE 'raw/meetings/%' OR path LIKE 'meetings/%'") == []
    assert issues(idx, "dead-link") == []


def test_links_to_a_notes_own_sources_are_not_dead(vault):
    """Raw inputs are gitignored, so a source resolves only on the machine that compiled it (#31)."""
    body = "Body cites [[Nowhere]].\n\n## Audit Trail\n- Source Material: [[2026-10-05-digest]]"
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", body, sources='["[[2026-10-05-digest]]"]'))
    assert issue_messages(build(vault), "dead-link") == [
        ("wiki/work/concepts/A.md", "warning", "dead-link", "dead link [[Nowhere]]"),
    ]


def test_another_notes_source_is_still_dead(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", sources='["[[digest-a]]"]'))
    write(vault, "wiki/work/concepts/B.md", concept("work", "B", "See [[digest-a]]."))
    assert issues(build(vault), "dead-link") == [("wiki/work/concepts/B.md", "warning", "dead-link")]


def test_table_escaped_wikilink_resolves(vault):
    """Inside a table Obsidian needs [[Target\\|Alias]]; the backslash is not part of the target."""
    write(vault, "wiki/work/concepts/Target.md", concept("work", "Target"))
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", "| Who | Note |\n|---|---|\n| [[Target\\|Alias]] | x |"))
    idx = build(vault)
    assert issues(idx, "dead-link") == []
    assert query(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/A.md'") == [("wiki/work/concepts/Target.md",)]


def test_quarantined_or_staged_copy_does_not_make_a_name_ambiguous(vault):
    """A rejected run's staged copy keeps the note's name; bare links must still resolve cleanly."""
    write(vault, "wiki/work/concepts/Same.md", concept("work", "Same"))
    write(vault, "system/quarantine/20261005T000000-ingest-abcd/staged/wiki/work/concepts/Same.md", concept("work", "Same"))
    write(vault, "wiki/.staging/20261005T000001-ingest-ef01/wiki/work/concepts/Same.md", concept("work", "Same"))
    write(vault, "wiki/work/concepts/A.md", concept("work", "A", "See [[Same]]."))
    idx = build(vault)
    assert issues(idx, "ambiguous-link") == []
    assert query(idx, "SELECT target_path FROM links WHERE src='wiki/work/concepts/A.md'") == [("wiki/work/concepts/Same.md",)]


def test_a_markdown_link_to_a_folder_is_not_dead(vault):
    write(vault, "README.md", "Specs in [specs](docs/specs/), none in [x](docs/nothing/).\n")
    write(vault, "docs/specs/a.md", "# A\n")
    assert issue_messages(build(vault), "dead-link") == [
        ("README.md", "warning", "dead-link", "dead link docs/nothing/")]
