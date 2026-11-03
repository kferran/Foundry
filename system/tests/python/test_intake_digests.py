import json
import os
import time
from pathlib import Path

import pytest

from helpers import write
from test_intake import calls, iv, ledger_month, later  # noqa: F401  (iv is a fixture)
from vaultlib import backfill, frontmatter
from vaultlib.intake import Intake


def digest(vault, partition, name, body="digest"):
    return write(vault, f"raw/{partition}/notes/{name}.md",
                 f'---\ntype: session_digest\npartition: {partition}\ncodebase: "vault"\nsession_id: "{name}"\n'
                 f'created_at: "2026-10-01T09:00:00-06:00"\n---\n{body}\n')


def alerts(vault):
    return "".join(p.read_text() for p in (vault / "system/logs").glob("alerts_*.md"))


def test_batch_of_digests_one_call_and_archived(iv):
    for n in ("d1", "d2", "d3"):
        digest(iv, "work", n)
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1 and len(calls(iv)[0]["args"]) == 4
    assert sorted(p.name for p in (iv / "raw/work/archive").iterdir()) == ["d1.md", "d2.md", "d3.md"]


def test_batches_capped_at_five(iv):
    for i in range(7):
        digest(iv, "work", f"d{i}")
    Intake(iv, now=later()).run()
    assert [len(c["args"]) - 1 for c in calls(iv)] == [5, 2]


def test_partitions_never_mixed(iv):
    digest(iv, "work", "w1")
    digest(iv, "personal", "p1")
    Intake(iv, now=later()).run()
    batches = [c["args"][1:] for c in calls(iv)]
    assert all(len({a.split("/")[1] for a in batch}) == 1 for batch in batches) and len(batches) == 2


def test_failed_batch_is_split_next_run(iv):
    for n in ("d1", "d2"):
        digest(iv, "work", n)
    (iv / "rc_queue.json").write_text(json.dumps([5]))
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    Intake(iv, now=later()).run()
    assert [len(c["args"]) - 1 for c in calls(iv)[1:]] == [1, 1]


def test_digest_poisoned_after_three_solo_failures(iv, monkeypatch):
    digest(iv, "work", "bad")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(3):
        Intake(iv, now=later()).run()
    assert (iv / "system/quarantine/poisoned/bad.md").is_file()
    origin = json.loads((iv / "system/quarantine/poisoned/bad.md.origin.json").read_text())
    assert origin["origin"] == "raw/work/notes/bad.md"


def test_cap_leaves_digests(iv, monkeypatch):
    digest(iv, "work", "d1")
    monkeypatch.setenv("STUB_RC", "4")
    Intake(iv, now=later()).run()
    assert (iv / "raw/work/notes/d1.md").exists()


def test_retry_all_restores_and_resets_attempts(iv, monkeypatch):
    write(iv, "raw/inbox/bad.md", "bad")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(3):
        Intake(iv, now=later()).run()
    assert Intake(iv, now=later()).retry(None) == ["raw/inbox/bad.md"]
    assert (iv / "raw/inbox/bad.md").exists()
    assert not list((iv / "system/quarantine/poisoned").glob("*.origin.json"))
    Intake(iv, now=later()).run()
    assert (iv / "raw/inbox/bad.md").exists()  # one failure since retry, not poisoned


def test_retry_by_run_id(iv, monkeypatch):
    write(iv, "raw/inbox/a.md", "a")
    write(iv, "raw/inbox/b.md", "b")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(3):
        Intake(iv, now=later()).run()
    ledger = (iv / "system/logs" / f"runs-{ledger_month()}.jsonl").read_text().splitlines()
    run_a = next(json.loads(l)["run_id"] for l in ledger if "a.md" in l)
    assert Intake(iv, now=later()).retry(run_a) == ["raw/inbox/a.md"]
    assert (iv / "system/quarantine/poisoned/b.md").is_file()


def test_retry_input_restores_only_the_named_file(iv, monkeypatch):
    # quarantine spec §2: one retry per input, no run id needed
    write(iv, "raw/inbox/a.md", "a")
    write(iv, "raw/inbox/b.md", "b")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(3):
        Intake(iv, now=later()).run()
    assert Intake(iv, now=later()).retry(name="a.md") == ["raw/inbox/a.md"]
    assert (iv / "system/quarantine/poisoned/b.md").is_file()
    assert not (iv / "system/quarantine/poisoned/a.md.origin.json").exists()
    ledger = (iv / "system/logs" / f"runs-{ledger_month()}.jsonl").read_text()
    assert '"command": "retry"' in ledger and "raw/inbox/a.md" in ledger.splitlines()[-1]
    assert Intake(iv, now=later()).retry(name="nope.md") == []


# -- controller ruling X5 ---------------------------------------------------
def test_rc2_on_batch_marks_solo_and_poisons_nothing(iv):
    for n in ("d1", "d2"):
        digest(iv, "work", n)
    (iv / "rc_queue.json").write_text(json.dumps([2]))
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    assert not (iv / "system/quarantine/poisoned").exists() or not list((iv / "system/quarantine/poisoned").iterdir())
    assert (iv / "raw/work/notes/d1.md").exists() and (iv / "raw/work/notes/d2.md").exists()
    Intake(iv, now=later()).run()
    assert [len(c["args"]) - 1 for c in calls(iv)[1:]] == [1, 1]


def test_rc2_on_solo_digest_poisons_immediately(iv, monkeypatch):
    digest(iv, "work", "bad")
    monkeypatch.setenv("STUB_RC", "2")
    Intake(iv, now=later()).run()
    assert (iv / "system/quarantine/poisoned/bad.md").is_file()
    assert "rejected as invalid input" in alerts(iv)


def test_rc3_stops_all_partitions(iv, monkeypatch):
    digest(iv, "work", "w1")
    digest(iv, "personal", "p1")
    monkeypatch.setenv("STUB_RC", "3")
    Intake(iv, now=later()).run()
    assert len(calls(iv)) == 1
    assert (iv / "raw/work/notes/w1.md").exists() and (iv / "raw/personal/notes/p1.md").exists()


def test_retry_after_torn_ledger_line_is_parseable(iv, monkeypatch):
    write(iv, "raw/inbox/bad.md", "bad")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(3):
        Intake(iv, now=later()).run()
    ledger = iv / "system/logs" / f"runs-{ledger_month()}.jsonl"
    with open(ledger, "a") as fh:
        fh.write('{"run_id": "torn", "comm')  # torn, no newline
    assert Intake(iv, now=later()).retry(None) == ["raw/inbox/bad.md"]
    last = ledger.read_text().splitlines()[-1]
    assert json.loads(last)["command"] == "retry"


def test_retry_midway_oserror_still_records_ledger(iv, monkeypatch):
    import hashlib
    import shutil as shutil_mod
    write(iv, "raw/inbox/a.md", "a")
    write(iv, "raw/inbox/b.md", "b")
    monkeypatch.setenv("STUB_RC", "5")
    for _ in range(3):
        Intake(iv, now=later()).run()
    real_move = shutil_mod.move

    def flaky(src, dst, *a, **k):
        if str(src).endswith("b.md"):
            raise PermissionError("denied")
        return real_move(src, dst, *a, **k)

    monkeypatch.setattr("vaultlib.intake.shutil.move", flaky)
    assert Intake(iv, now=later()).retry(None) == ["raw/inbox/a.md"]
    monkeypatch.undo()
    ledger = iv / "system/logs" / f"runs-{ledger_month()}.jsonl"
    last = json.loads(ledger.read_text().splitlines()[-1])
    assert last["command"] == "retry" and hashlib.sha256(b"a").hexdigest() in last["input_sha256"]
    assert (iv / "system/quarantine/poisoned/b.md").is_file()
    assert (iv / "system/quarantine/poisoned/b.md.origin.json").is_file()
    assert "b.md" in alerts(iv)
    monkeypatch.setenv("STUB_RC", "5")
    Intake(iv, now=later()).run()
    assert (iv / "raw/inbox/a.md").exists()  # one failure since retry, not poisoned


# -- recall R1 (#438): the excerpt a backfilled digest is written from (recall spec §4.3) --
def prompt(ts, text, **extra):
    return {"type": "user", "isSidechain": False, "timestamp": ts, "message": {"role": "user", "content": text}, **extra}


def reply(ts, *blocks, **extra):
    return {"type": "assistant", "isSidechain": False, "timestamp": ts,
            "message": {"role": "assistant", "content": list(blocks)}, **extra}


def tool_result(ts, text):
    return {"type": "user", "isSidechain": False, "timestamp": ts, "toolUseResult": {"stdout": text},
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": text}]}}


def transcript(path, *entries, raw_lines=()):
    lines = [json.dumps(e) for e in entries]
    for at, line in raw_lines:
        lines.insert(at, line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


T1, T2, T3, T4 = (f"2026-11-03T13:49:1{n}.026Z" for n in range(4))


def test_excerpt_keeps_prompts_text_and_tool_lines_in_order(tmp_path):
    path = transcript(
        tmp_path / "s.jsonl",
        {"type": "permission-mode", "permissionMode": "default"},
        prompt(T1, "Tidy the export job"),
        reply(T2, {"type": "thinking", "thinking": "private reasoning"}, {"type": "text", "text": "Reading it now."},
              {"type": "tool_use", "name": "Read", "input": {"file_path": "/x/export.py"}},
              {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q\n" + "y" * 300, "description": "d"}}),
        {"type": "attachment", "timestamp": T3, "attachment": {"content": "attached text"}},
        reply(T4, {"type": "text", "text": "Done."}))
    text, cut, last = backfill.excerpt(path)
    assert text.split("\n") == [
        f"[{T1}] user: Tidy the export job",
        f"[{T2}] assistant: Reading it now.",
        f"[{T2}] tool Read /x/export.py",
        f"[{T2}] tool Bash " + ("pytest -q " + "y" * 300)[:200],
        f"[{T4}] assistant: Done."]
    assert (cut, last) == (0, T4)


def test_excerpt_drops_sidechain_and_tool_results(tmp_path):
    path = transcript(tmp_path / "s.jsonl", prompt(T1, "Go"), tool_result(T2, "secret tool output"),
                      prompt(T3, "subagent prompt", isSidechain=True), reply(T4, {"type": "text", "text": "ok"}))
    text, _, _ = backfill.excerpt(path)
    assert text == f"[{T1}] user: Go\n[{T4}] assistant: ok"


def test_excerpt_keeps_the_newest_100000_with_a_marker(tmp_path):
    entries = [prompt(T1, f"turn {i} " + "z" * 990) for i in range(150)] + [reply(T4, {"type": "text", "text": "the end"})]
    whole = "\n".join(f"[{T1}] user: turn {i} " + "z" * 990 for i in range(150)) + f"\n[{T4}] assistant: the end"
    text, cut, last = backfill.excerpt(transcript(tmp_path / "s.jsonl", *entries))
    marker, kept = text.split("\n", 1)
    assert cut == len(whole) - backfill.EXCERPT_CAP > 0
    assert marker == f"[… {cut} earlier characters left out …]"
    assert kept == whole[cut:] and len(kept) == backfill.EXCERPT_CAP
    assert last == T4


def test_excerpt_skips_bad_and_huge_lines(tmp_path):
    huge = json.dumps(prompt(T2, "h" * (backfill.LINE_CAP + 1)))
    path = transcript(tmp_path / "s.jsonl", prompt(T1, "before"), reply(T4, {"type": "text", "text": "after"}),
                      raw_lines=[(1, "not json {"), (2, huge), (3, '["a list"]')])
    text, cut, _ = backfill.excerpt(path)
    assert text == f"[{T1}] user: before\n[{T4}] assistant: after" and cut == 0


def test_excerpt_header_is_the_digest_frontmatter():
    state = {"partition": "work", "codebase": "vault"}
    head = backfill.header(state, "bf000001-aaaa", "2026-11-03T06:49:13-07:00", 2)
    data = frontmatter.parse(head + "body\n").data
    assert data == {"type": "session_digest", "partition": "work", "codebase": "vault", "session_id": "bf000001-aaaa",
                    "created_at": "2026-11-03T06:49:13-07:00", "redactions": "2"}


# -- recall R1 (#438): the tick's backfill step (recall spec §4.2, §4.4, §4.6) --
SID = "bf000001-aaaa-bbbb"
NAME = "2026-11-03-0649-bf000001-backfill"   # T4 (13:49:13Z) in America/Denver
STAGED = f"raw/inbox/.staging/{NAME}.md"
DIGEST = f"raw/work/notes/{NAME}.md"


@pytest.fixture
def bv(iv, tmp_path, monkeypatch):
    """A vault with one ended session queued: its state, its marker and its kept transcript (the default keep dir)."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    queue(iv, SID)
    return iv


def queue(vault, sid, partition="work"):
    sessions = vault / "system/logs/memory/sessions"
    write(vault, f"system/logs/memory/sessions/{sid}.json", json.dumps(
        {"scope": "vault", "partition": partition, "codebase": "vault", "tz": "America/Denver", "last_digest_at": 0}))
    (sessions / f"{sid}.backfill").touch()
    keep = Path(os.environ["XDG_STATE_HOME"]) / "foundry/transcripts"
    keep.mkdir(parents=True, exist_ok=True)
    transcript(keep / f"{sid}.jsonl", prompt(T1, "Tidy the export job, password: hunter2"),
               reply(T4, {"type": "text", "text": "Done."}))
    return sessions / f"{sid}.backfill"


def backfills(vault):
    return [c for c in calls(vault) if c["args"][0] == "digest-backfill"]


def rlog(vault):
    return [json.loads(l) for p in sorted((vault / "system/logs").glob("recall-*.jsonl"))
            for l in p.read_text().splitlines() if '"backfill"' in l]


MARKER = f"system/logs/memory/sessions/{SID}.backfill"


def test_backfill_writes_one_digest_from_a_marker(bv):
    Intake(bv, now=later()).run()
    [call] = backfills(bv)
    assert call["args"] == ["digest-backfill", STAGED]
    staged = call["staged"][STAGED]
    assert staged.startswith(f'---\ntype: session_digest\npartition: "work"\ncodebase: "vault"\nsession_id: "{SID}"\n'
                             f'created_at: "2026-11-03T06:49:13-07:00"\nredactions: "1"\n---\n')
    assert f"[{T1}] user: Tidy the export job" in staged and "hunter2" not in staged
    assert 'provenance: ["headless"]' in (bv / DIGEST).read_text()
    assert not (bv / MARKER).exists() and not (bv / STAGED).exists()
    [line] = rlog(bv)
    assert (line["session"], line["result"], line["cut"]) == (SID, "written", 0)
    assert line["run_id"].startswith("stub-") and line["chars"] > 0
    Intake(bv, now=later()).run()
    assert len(backfills(bv)) == 1


@pytest.mark.parametrize("folder", ["raw/work/notes", "raw/personal/archive", "system/quarantine/poisoned"])
def test_a_late_stop_digest_drops_the_marker(bv, folder):
    digest(bv, "work", "x")  # placeholder content; renamed below into the folder under test
    (bv / folder).mkdir(parents=True, exist_ok=True)
    (bv / "raw/work/notes/x.md").rename(bv / folder / "2026-11-03-0700-bf000001-shipped-it.md")
    Intake(bv, now=later()).run()
    assert backfills(bv) == [] and not (bv / MARKER).exists()
    assert [(l["result"], l["why"]) for l in rlog(bv)] == [("skipped", "has a digest")]


def test_backfill_without_state_or_transcript_drops_the_marker(bv, tmp_path):
    (tmp_path / "state/foundry/transcripts" / f"{SID}.jsonl").unlink()
    other = queue(bv, "bf000002-cccc")
    (bv / "system/logs/memory/sessions/bf000002-cccc.json").unlink()
    Intake(bv, now=later()).run()
    assert backfills(bv) == [] and not (bv / MARKER).exists() and not other.exists()
    assert sorted(l["why"] for l in rlog(bv)) == ["no kept transcript", "no session state"]


def test_backfill_waits_at_the_ceiling(bv, monkeypatch):
    monkeypatch.setattr(Intake, "held", lambda self: True)
    Intake(bv, now=later()).run()
    assert backfills(bv) == [] and (bv / MARKER).exists()


def test_backfill_exit_2_quarantines_the_marker(bv, monkeypatch):
    monkeypatch.setenv("STUB_RC", "2")
    Intake(bv, now=later()).run()
    assert not (bv / MARKER).exists()
    assert (bv / f"system/quarantine/backfill/{SID}.backfill").is_file()
    assert "exit 2" in (bv / f"system/quarantine/backfill/{SID}.backfill.reason.txt").read_text()
    assert alerts(bv).count(f"backfill of session {SID[:8]} quarantined") == 1


@pytest.mark.parametrize("rc", [3, 4, 6, 7])
def test_backfill_stop_tick_keeps_the_marker(bv, monkeypatch, rc):
    queue(bv, "bf000002-cccc")
    monkeypatch.setenv("STUB_RC", str(rc))
    Intake(bv, now=later()).run()
    assert len(backfills(bv)) == 1 and (bv / MARKER).exists()
    assert not (bv / "system/quarantine/backfill").exists()


def test_backfill_retries_then_quarantines_after_three(bv, monkeypatch):
    monkeypatch.setenv("STUB_RC", "5")
    for n in (1, 2):
        Intake(bv, now=later()).run()
        assert (bv / MARKER).exists() and alerts(bv).count("will retry") == n
    Intake(bv, now=later()).run()
    assert len(backfills(bv)) == 3 and not (bv / MARKER).exists()
    assert (bv / f"system/quarantine/backfill/{SID}.backfill").is_file()


@pytest.mark.parametrize("field, env", [
    ("session_id", {"STUB_BACKFILL_SUB": json.dumps([[f'session_id: "{SID}"', 'session_id: "bf000001-zzzz"']])}),
    ("provenance", {"STUB_BACKFILL_SUB": json.dumps([['["headless"]', '["session", "headless"]']])}),
    ("Corrections", {"STUB_BACKFILL_BODY": "Done.\n## Corrections\n- use tabs"}),
    ("redaction", {"STUB_BACKFILL_BODY": "Set password: hunter2 on the job."}),
])
def test_backfill_read_back_poisons_a_mismatch(bv, monkeypatch, field, env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    Intake(bv, now=later()).run()
    assert not (bv / DIGEST).exists() and (bv / f"system/quarantine/poisoned/{NAME}.md").is_file()
    assert f"backfill read-back failed ({field})" in alerts(bv)
    assert not (bv / MARKER).exists()


def test_backfill_shares_max_runs_with_digests(bv):
    digest(bv, "work", "w1")
    digest(bv, "personal", "p1")
    Intake(bv, now=later(), max_runs=2).run()
    assert backfills(bv) == [] and (bv / MARKER).exists()
    Intake(bv, now=later(), max_runs=2).run()
    assert len(backfills(bv)) == 1


def test_a_fresh_marker_waits(bv):
    Intake(bv, now=time.time()).run()
    assert backfills(bv) == [] and (bv / MARKER).exists()


# -- final review fixes --
def test_a_backfill_that_raises_quarantines_its_marker_and_the_queue_moves_on(bv, tmp_path):
    other = queue(bv, "bf000002-cccc")
    os.utime(bv / MARKER, (time.time() - 600, time.time() - 600))   # the stuck one is oldest
    (tmp_path / "state/foundry/transcripts" / f"{SID}.jsonl").chmod(0)
    Intake(bv, now=later()).run()
    assert (bv / f"system/quarantine/backfill/{SID}.backfill").is_file() and not (bv / MARKER).exists()
    assert "PermissionError" in (bv / f"system/quarantine/backfill/{SID}.backfill.reason.txt").read_text()
    assert [c["args"][1] for c in backfills(bv)] == ["raw/inbox/.staging/2026-11-03-0649-bf000002-backfill.md"]
    assert not other.exists()


def test_backfill_survives_a_lone_surrogate_in_the_transcript(bv, tmp_path):
    keep = tmp_path / "state/foundry/transcripts" / f"{SID}.jsonl"
    keep.write_text(json.dumps(prompt(T1, "x")).replace('"x"', '"bad \\ud83d here"') + "\n"
                    + json.dumps(reply(T4, {"type": "text", "text": "Done."})) + "\n")
    Intake(bv, now=later()).run()
    [call] = backfills(bv)
    assert "bad ? here" in call["staged"][STAGED] and (bv / DIGEST).is_file()


def test_excerpt_tool_paths_are_relative_to_the_session_cwd(tmp_path):
    path = transcript(tmp_path / "s.jsonl", reply(T2, *(
        {"type": "tool_use", "name": "Read", "input": {"file_path": f}}
        for f in ("/work/a-project/system/scripts/vaultlib/intake.py", "/elsewhere/notes.md"))))
    text, _, _ = backfill.excerpt(path, "/work/a-project")
    assert text == f"[{T2}] tool Read system/scripts/vaultlib/intake.py\n[{T2}] tool Read /elsewhere/notes.md"


def test_backfill_read_back_passes_prose_that_only_names_a_token(bv, monkeypatch):
    monkeypatch.setenv("STUB_BACKFILL_BODY", "The refresh token: expires after an hour.")
    Intake(bv, now=later()).run()
    assert (bv / DIGEST).is_file() and "read-back failed" not in alerts(bv)
