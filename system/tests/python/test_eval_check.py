"""vaultlib/evals.py and eval_check.py: deterministic checks over an ingest tick's runs (ingest evals spec §3.3)."""
import json
import subprocess
import sys

from helpers import REPO, concept, write
from vaultlib import evals

RUN, RUN2 = "20261018T090000-ingest-ab12", "20261018T090100-ingest-cd34"
SCRIPT = REPO / "system" / "scripts" / "eval_check.py"


def run(vault, run_id=RUN, status="published", published=(), decisions=(), cost=0.25):
    rd = vault / "system" / "logs" / "runs" / run_id
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "publish.json").write_text(json.dumps({"run_id": run_id, "status": status, "published": list(published),
                                                 "conflicts": [], "problems": []}))
    (rd / "_decisions.jsonl").write_text("".join(json.dumps({"item": "i", "decision": d, "target": t,
                                                             "source": "s", "reason": "r"}) + "\n"
                                                 for d, t in decisions))
    (rd / "claude.json").write_text(json.dumps({"type": "result", "total_cost_usd": cost}))


def test_publish_accepts_one_status_or_a_list(vault):
    run(vault, status="noop")
    assert evals.check(vault, [RUN], {"publish": "noop"}) == []
    assert evals.check(vault, [RUN], {"publish": ["published", "noop"]}) == []
    assert evals.check(vault, [RUN], {"publish": "published"}) == [f"publish: {RUN} is noop, want published"]


def test_decisions_are_exact_order_free_and_take_globs(vault):
    run(vault, decisions=[("patch", "wiki/work/concepts/Kafka.md"), ("create", "wiki/work/concepts/New.md")])
    assert evals.check(vault, [RUN], {"decisions": [["create", "wiki/work/concepts/*.md"],
                                                     ["patch", "wiki/work/concepts/Kafka.md"]]}) == []
    assert evals.check(vault, [RUN], {"decisions": [["patch", "wiki/work/concepts/Kafka.md"]]}) == [
        "decisions: unexpected create on wiki/work/concepts/New.md"]
    assert evals.check(vault, [RUN], {"decisions": [["noop", "wiki/work/concepts/Kafka.md"],
                                                     ["create", "*"], ["patch", "*"]]}) == [
        "decisions: no noop on wiki/work/concepts/Kafka.md"]


def test_creates_checks_frontmatter_on_a_matching_published_path(vault):
    write(vault, "wiki/shared/concepts/Rust.md", concept("shared", "Rust", tags="[lang, systems]"))
    run(vault, published=["wiki/shared/concepts/Rust.md"])
    assert evals.check(vault, [RUN], {"creates": {"wiki/shared/concepts/*.md": {"type": "concept", "partition": "shared",
                                                                                 "tags": ["lang"]}}}) == []
    assert evals.check(vault, [RUN], {"creates": {"wiki/shared/concepts/*.md": {"partition": "work"}}}) == [
        "creates: no published wiki/shared/concepts/*.md with {'partition': 'work'}"]
    assert evals.check(vault, [RUN], {"creates": {"wiki/work/**": {}}}) == ["creates: no published wiki/work/**"]


def test_patches_need_new_text_and_keep_old_text(vault):
    write(vault, "wiki/work/concepts/Kafka.md", concept("work", "Kafka", "Kafka 3.7 runs on three brokers."))
    run(vault, published=["wiki/work/concepts/Kafka.md"])
    spec = {"wiki/work/concepts/Kafka.md": {"contains": ["3.7"], "still_contains": ["three brokers"]}}
    assert evals.check(vault, [RUN], {"patches": spec}) == []
    spec = {"wiki/work/concepts/Kafka.md": {"contains": ["3.8"], "still_contains": ["five brokers"]}}
    assert evals.check(vault, [RUN], {"patches": spec}) == [
        "patches: wiki/work/concepts/Kafka.md lacks '3.8' (contains)",
        "patches: wiki/work/concepts/Kafka.md lacks 'five brokers' (still_contains)"]
    assert evals.check(vault, [RUN], {"patches": {"wiki/work/concepts/Git.md": {}}}) == [
        "patches: wiki/work/concepts/Git.md was not published"]


def test_untouched_catches_a_one_byte_change(vault, tmp_path):
    overlay = tmp_path / "overlay"
    write(overlay, "wiki/Index.md", (vault / "wiki/Index.md").read_text())
    run(vault)
    assert evals.check(vault, [RUN], {"untouched": ["wiki/Index.md"]}, overlay) == []
    (vault / "wiki/Index.md").write_text((vault / "wiki/Index.md").read_text() + " ")
    assert evals.check(vault, [RUN], {"untouched": ["wiki/Index.md"]}, overlay) == ["untouched: wiki/Index.md changed"]


def test_walls_catch_a_cross_partition_link_and_a_shared_note_citing_work(vault):
    write(vault, "wiki/work/concepts/Bad.md", concept("work", "Bad", "See [[Gardening]]."))
    write(vault, "wiki/shared/concepts/Leak.md", concept("shared", "Leak", sources='["[[Kafka]]"]'))
    run(vault, published=["wiki/work/concepts/Bad.md", "wiki/shared/concepts/Leak.md"])
    lines = evals.check(vault, [RUN], {"walls": True})
    assert any("Bad.md" in line and "Gardening.md" in line for line in lines)
    assert any("Leak.md" in line and "Kafka.md" in line for line in lines)
    run(vault, published=["wiki/work/concepts/Kafka.md"])
    assert evals.check(vault, [RUN], {"walls": True}) == []


def test_absent_catches_a_published_or_held_path(vault):
    run(vault, status="rejected")
    held = vault / "system/quarantine" / RUN / "staged/wiki/Index.md"
    held.parent.mkdir(parents=True)
    held.write_text("x")
    assert evals.check(vault, [RUN], {"absent": ["wiki/Index.md"]}) == ["absent: wiki/Index.md was staged"]
    run(vault, RUN2, published=["wiki/Index.md"])
    assert evals.check(vault, [RUN2], {"absent": ["wiki/Index.md"]}) == ["absent: wiki/Index.md was published"]
    assert evals.check(vault, [RUN2], {"absent": ["wiki/work/concepts/Other.md"]}) == []


def test_body_contains_and_lacks_read_published_bodies_only(vault):
    write(vault, "wiki/work/concepts/Quarter.md", concept("work", "Quarter", "Revenue was 4.2 million."))
    run(vault, published=["wiki/work/concepts/Quarter.md"])
    assert evals.check(vault, [RUN], {"body_contains": {"wiki/work/**": ["4.2 million"]}}) == []
    assert evals.check(vault, [RUN], {"body_contains": {"wiki/work/**": ["5.1 million"]}}) == [
        "body_contains: no published wiki/work/** holds '5.1 million'"]
    assert evals.check(vault, [RUN], {"body_lacks": {"wiki/work/**": ["4.2 million"]}}) == [
        "body_lacks: wiki/work/concepts/Quarter.md holds '4.2 million'"]


def test_archived_finds_the_input_in_raw_archive(vault):
    run(vault)
    assert evals.check(vault, [RUN], {"archived": ["deck.pptx"]}) == ["archived: deck.pptx is not in raw/archive/"]
    write(vault, "raw/archive/deck.pptx", "x")
    assert evals.check(vault, [RUN], {"archived": ["deck.pptx"]}) == []


def test_two_runs_are_read_together_and_no_run_is_a_failure(vault):
    write(vault, "wiki/work/concepts/A.md", concept("work", "A"))
    run(vault, RUN, published=["wiki/work/concepts/A.md"], cost=0.5)
    run(vault, RUN2, status="noop", cost=0.25)
    assert evals.check(vault, [RUN, RUN2], {"publish": ["published", "noop"],
                                             "creates": {"wiki/work/concepts/A.md": {}}}) == []
    assert evals.cost(vault, [RUN, RUN2]) == 0.75
    assert evals.check(vault, [], {"publish": "published"}) == ["runs: the tick ran no ingest"]
    assert evals.check(vault, [RUN], {"publsh": "x"}) == ["expect: unknown keys publsh"]


def test_summary_rates_skips_and_cost():
    records = [{"case": "a", "min_pass_rate": 0.67, "failed": [], "cost": 0.2},
               {"case": "a", "min_pass_rate": 0.67, "failed": ["x"], "cost": 0.4},
               {"case": "a", "min_pass_rate": 0.67, "failed": [], "cost": 0.3},
               {"case": "b", "min_pass_rate": 1.0, "failed": ["x"], "cost": 0.1},
               {"case": "c", "min_pass_rate": 1.0, "skipped": True}]
    lines, ok = evals.summary(records)
    assert lines == ["a: 2/3 (min 0.67) PASS, $0.30 a run", "b: 0/1 (min 1) FAIL, $0.10 a run", "c: skipped (budget)"]
    assert ok is False
    assert evals.summary(records[:3]) == (["a: 2/3 (min 0.67) PASS, $0.30 a run"], True)


def test_cli_check_rate_and_a_bad_expect(vault, tmp_path):
    run(vault, status="noop")
    good = write(tmp_path, "expect.yaml", "min_pass_rate: 0.67\npublish: noop\n")
    bad = write(tmp_path, "bad.yaml", "- just\n- a list\n")
    p = subprocess.run([sys.executable, str(SCRIPT), "check", str(vault), str(good), str(tmp_path), RUN],
                       capture_output=True, text=True)
    assert (p.returncode, p.stdout) == (0, "")
    p = subprocess.run([sys.executable, str(SCRIPT), "rate", str(good)], capture_output=True, text=True)
    assert p.stdout == "0.67\n"
    p = subprocess.run([sys.executable, str(SCRIPT), "rate", str(bad)], capture_output=True, text=True)
    assert p.returncode == 2 and "not a mapping" in p.stderr


def test_untouched_needs_the_path_in_the_overlay(vault, tmp_path):
    run(vault)
    assert evals.check(vault, [RUN], {"untouched": ["wiki/Index.md"]}, tmp_path) == [
        "untouched: wiki/Index.md is not in the case's overlay"]


def test_count_retired_and_keeps(vault):
    write(vault, "wiki/work/concepts/Old.md", concept("work", "Old", status="deprecated"))
    write(vault, "wiki/work/concepts/Gone.md", concept("work", "Gone", superseded_by='"[[New]]"'))
    write(vault, "wiki/work/concepts/Kept.md", concept("work", "Kept"))
    run(vault, published=["wiki/work/concepts/Old.md", "wiki/work/concepts/Gone.md", "wiki/work/concepts/Kept.md"])
    assert evals.check(vault, [RUN], {"count": {"wiki/work/**": 3, "wiki/shared/**": 0},
                                       "retired": ["wiki/work/concepts/Old.md", "wiki/work/concepts/Gone.md"],
                                       "keeps": {"wiki/work/concepts/Kafka.md": ["commit log"]}}) == []
    assert evals.check(vault, [RUN], {"count": {"wiki/work/**": 1}, "retired": ["wiki/work/concepts/Kept.md"],
                                       "keeps": {"wiki/work/concepts/Kafka.md": ["five brokers"]}}) == [
        "count: 3 published wiki/work/**, want 1",
        "retired: wiki/work/concepts/Kept.md is neither deprecated nor superseded",
        "keeps: wiki/work/concepts/Kafka.md lost 'five brokers'"]


def test_summary_names_a_skip_reason():
    assert evals.summary([{"case": "pdf", "skipped": True, "reason": "pdftotext missing"}]) == (
        ["pdf: skipped (pdftotext missing)"], False)
