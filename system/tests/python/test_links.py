import time
from vaultlib import links


def ex(body):
    found, tags = links.extract(body, 10)
    return [(l.target, l.kind, l.line) for l in found], tags


def test_wikilink_forms():
    found, _ = ex("[[A]] [[B|alias]] [[C#Heading]] [[D#^block]] ![[E]] [[#Local]]")
    assert found == [("A", "link", 10), ("B", "link", 10), ("C", "link", 10),
                     ("D", "link", 10), ("E", "embed", 10), (None, "link", 10)]


def test_markdown_links_skip_urls_and_anchors():
    found, _ = ex("[x](notes/a.md) [y](https://example.com) [z](#top) [w](mailto:a@b)")
    assert found == [("notes/a.md", "md", 10)]


def test_code_is_ignored():
    body = "```\n[[InFence]]\n```\n`[[Inline]]` [[Real]]\n~~~\n#notatag\n~~~"
    found, tags = ex(body)
    assert found == [("Real", "link", 13)]
    assert tags == set()


def test_tags():
    _, tags = ex("Some #alpha and #beta/gamma, not a#b or # heading or url#frag")
    assert tags == {"alpha", "beta/gamma"}


def prefer_none(path):
    return (len(path), path)


def test_case_insensitive_basename():
    r = links.Resolver(["wiki/work/concepts/Kafka.md"])
    assert r.resolve("kafka", "wiki/Index.md", "wiki", prefer_none) == ("wiki/work/concepts/Kafka.md", False)


def test_path_target_and_extension():
    r = links.Resolver(["wiki/work/A.md", "raw/archive/report.pdf"])
    assert r.resolve("wiki/work/A", "x.md", "wiki", prefer_none)[0] == "wiki/work/A.md"
    assert r.resolve("report.pdf", "x.md", "wiki", prefer_none)[0] == "raw/archive/report.pdf"
    assert r.resolve("Missing", "x.md", "wiki", prefer_none) == (None, False)


def test_dotted_basename():
    r = links.Resolver(["briefings/2026-09-30.debrief.md"])
    assert r.resolve("2026-09-30.debrief", "briefings/2026-09-30.md", "wiki", prefer_none)[0] == "briefings/2026-09-30.debrief.md"


def test_markdown_relative_resolution():
    r = links.Resolver(["wiki/work/b/B.md"])
    assert r.resolve("b/B.md", "wiki/work/A.md", "md", prefer_none)[0] == "wiki/work/b/B.md"
    assert r.resolve("../nope.md", "wiki/work/A.md", "md", prefer_none)[0] is None


def test_self_link():
    r = links.Resolver([])
    assert r.resolve(None, "wiki/A.md", "wiki", prefer_none) == ("wiki/A.md", False)


def test_ambiguity_uses_prefer():
    r = links.Resolver(["wiki/work/X.md", "wiki/personal/X.md"])
    hit, amb = r.resolve("X", "wiki/personal/Y.md", "wiki", lambda p: (0 if "/personal/" in p else 1, p))
    assert (hit, amb) == ("wiki/personal/X.md", True)


def test_no_quadratic_backtracking():
    for s in ["[" * 100000, "[[" * 50000, "[[a" * 30000, "[a](" * 25000, "[x" * 50000]:
        start = time.monotonic()
        links.extract(s, 1)
        assert time.monotonic() - start < 1.0


def test_no_tags_from_links():
    _, tags = links.extract("[[#Local]] [z](#top) (#paren) #real", 1)
    assert tags == {"real"}


def test_dotted_path_target():
    r = links.Resolver(["wiki/2026.debrief.md"])
    assert r.resolve("wiki/2026.debrief", "x.md", "wiki", prefer_none)[0] == "wiki/2026.debrief.md"


def test_markdown_link_to_a_folder_resolves_when_the_folder_holds_a_file():
    r = links.Resolver(["docs/superpowers/specs/a.md"])
    assert r.resolve("docs/superpowers/specs/", "README.md", "md", prefer_none) == ("docs/superpowers/specs", False)
    assert r.resolve("docs/", "README.md", "md", prefer_none)[0] == "docs"
    assert r.resolve("docs/superpowers/spikes/", "README.md", "md", prefer_none)[0] is None
