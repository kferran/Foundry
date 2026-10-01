import json

from helpers import write
from test_intake import calls, iv, ledger_month, later  # noqa: F401  (iv is a fixture)
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
