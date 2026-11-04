"""Parallel Work Orders (#229, parallel orders spec §3): one tick runs up to MAX_PARALLEL items at once, refills a slot
when one finishes, never runs two plans on one repo and base together, and checks the 5-hour ceiling before each start.
run_item is replaced by a fake that records when each item starts and ends. Overlap is proved by handshakes, never by
sleeps: the first `meet` orders wait at a barrier that opens only once all of them are running at the same time."""
import json
import threading
import time

import pytest

from test_nightshift_run import NOW, add, env, git, health_at  # noqa: F401  (env is a fixture)
from vaultlib import nightshift_item as ni
from vaultlib import nightshift_run as nr

WAIT = 30   # seconds a handshake waits before the test fails; a passing run never waits this long


class Fake:
    def __init__(self, fail=(), meet=0, hold=None):
        self.fail, self.lock, self.active = set(fail), threading.Lock(), 0
        self.peak, self.starts, self.ends, self.started = 0, {}, {}, []
        self.meet, self.barrier, self.hold = meet, threading.Barrier(meet) if meet else None, hold

    def __call__(self, ctx, path, fm, body):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.starts[fm["id"]] = time.monotonic()
            self.started.append(fm["id"])
            meets = len(self.started) <= self.meet
        try:
            if slug(fm) in self.fail:
                raise RuntimeError("boom")
            if meets:   # breaks (and the order fails) unless all `meet` orders are running at once
                self.barrier.wait(timeout=WAIT)
            if self.hold:
                assert self.hold.wait(timeout=WAIT)
            ni.update(path, state="done")
            return 0
        finally:
            with self.lock:
                self.active -= 1
                self.ends[fm["id"]] = time.monotonic()


def research(vault, tmp, title):
    brief = tmp / f"{title}.md"
    brief.write_text("## Question\nQ\n## Scope\nNotes.\n## Done when\nAnswered.\n## Output\nA note.\n")
    assert nr.main(["research", "--title", title, "--partition", "work", "--brief-file", str(brief),
                    "--output", f"wiki/work/concepts/{title}.md", "--now"], vault, NOW) == 0


def slug(fm):
    return fm["id"].split("-", 3)[3]


def ids(vault):
    return {slug(fm): fm["id"] for _, fm, _ in ni.items(vault)}


def states(vault):
    return {slug(fm): fm["state"] for _, fm, _ in ni.items(vault)}


def overlap(fake, a, b):
    return fake.starts[b] < fake.ends[a] and fake.starts[a] < fake.ends[b]


def test_four_research_orders_run_three_at_a_time_and_all_finish_in_one_tick(env, monkeypatch):
    vault, tmp = env
    fake = Fake(meet=3)
    monkeypatch.setattr(nr, "run_item", fake)
    for t in ("ra", "rb", "rc", "rd"):
        research(vault, tmp, t)
    assert nr.main(["tick"], vault, NOW) == 0
    assert fake.peak == 3
    assert {fm["state"] for _, fm, _ in ni.items(vault)} == {"done"}


def test_two_plans_on_one_repo_and_base_take_turns_while_research_runs_beside_them(env, monkeypatch):
    vault, tmp = env
    fake = Fake(meet=2)   # the first plan and the research order meet; the second plan waits its turn
    monkeypatch.setattr(nr, "run_item", fake)
    assert add(vault, "--now", "--title", "plan one") == 0
    assert add(vault, "--now", "--title", "plan two") == 0
    research(vault, tmp, "notes")
    assert nr.main(["tick"], vault, NOW) == 0
    i = ids(vault)
    p1, p2 = sorted([i["plan-one"], i["plan-two"]], key=lambda x: fake.starts[x])
    assert fake.starts[p2] >= fake.ends[p1]
    assert overlap(fake, p1, i["notes"])


def test_plans_on_different_bases_run_together(env, monkeypatch):
    vault, tmp = env
    git(vault, "branch", "feat/y")
    git(vault, "push", "-q", str(tmp / "remote.git"), "feat/y")
    fake = Fake(meet=2)
    monkeypatch.setattr(nr, "run_item", fake)
    assert add(vault, "--now", "--title", "on x") == 0
    assert add(vault, "--now", "--title", "on y", "--base", "feat/y") == 0
    assert nr.main(["tick"], vault, NOW) == 0
    i = ids(vault)
    assert overlap(fake, i["on-x"], i["on-y"])


def test_the_ceiling_holds_new_starts_and_lets_a_running_item_resume(env, monkeypatch):
    vault, tmp = env
    fake = Fake()
    monkeypatch.setattr(nr, "run_item", fake)
    research(vault, tmp, "started")
    research(vault, tmp, "queued")
    path = next(p for p, fm, _ in ni.items(vault) if slug(fm) == "started")
    ni.update(path, state="running", attempts="1", session_id="old")
    health_at(vault, 0.9, 1)
    assert nr.main(["tick"], vault, NOW) == 0
    i = ids(vault)
    assert fake.started == [i["started"]]
    assert states(vault)["queued"] == "queued"


def test_a_worker_that_raises_leaves_the_others_running_and_is_alerted(env, monkeypatch):
    vault, tmp = env
    fake = Fake(fail={"bad"})
    monkeypatch.setattr(nr, "run_item", fake)
    for t in ("ok1", "bad", "ok2"):
        research(vault, tmp, t)
    assert nr.main(["tick"], vault, NOW) == 1
    assert states(vault)["ok1"] == "done"
    assert states(vault)["ok2"] == "done"
    alerts = (vault / "system/logs" / f"alerts_{NOW.astimezone(nr.ZoneInfo('America/Denver')).date()}.md").read_text()
    assert f"{ids(vault)['bad']}: the worker stopped: RuntimeError: boom" in alerts


def test_max_parallel_one_runs_one_at_a_time(env, monkeypatch):
    vault, tmp = env
    fake = Fake()
    monkeypatch.setattr(nr, "run_item", fake)
    monkeypatch.setattr(nr, "MAX_PARALLEL", 1)
    for t in ("ra", "rb"):
        research(vault, tmp, t)
    assert nr.main(["tick"], vault, NOW) == 0
    assert fake.peak == 1
    assert {fm["state"] for _, fm, _ in ni.items(vault)} == {"done"}


def test_an_order_started_later_in_the_tick_stamps_its_own_start(env, monkeypatch):
    # #229 acceptance: a slot freed mid-tick starts an order minutes after the tick began; its started_at, outcome and
    # ledger line must say when it started, not when the tick did.
    vault, tmp = env
    from test_nightshift_run import only_item, set_workspace
    assert add(vault, "--now") == 0
    set_workspace(vault, vault / ".scratch" / "ws")   # the item fails at once, after stamping its start
    ctx = nr.Ctx(vault, NOW)
    monkeypatch.setattr(nr.clock, "monotonic", lambda: ctx.t0 + 600)
    path, fm = only_item(vault)
    nr.run_item(ctx, path, fm, "")
    _, fm = only_item(vault)
    later = (NOW + nr.timedelta(seconds=600)).isoformat()
    assert fm["started_at"] == later
    ledger = (vault / "system/logs" / f"nightshift-{NOW:%Y-%m}.jsonl").read_text().splitlines()
    assert json.loads(ledger[-1])["time"] == later


class Clock:
    """A monotonic clock the fake run_item can move forward: an order that "runs for an hour" in a few ms."""

    def __init__(self, monkeypatch):
        real = time.monotonic   # nr.clock is the time module: the patch replaces time.monotonic itself
        self.base, self.offset = real(), 0.0
        monkeypatch.setattr(nr.clock, "monotonic", lambda: real() + self.offset)


class Timed(Fake):
    """The fake, plus: move the clock forward and record a usage reading as an order finishes."""

    def __init__(self, clock=None, advance=0, usage=None, **kw):
        super().__init__(**kw)
        self.clock, self.advance, self.usage = clock, advance, usage

    def __call__(self, ctx, path, fm, body):
        rc = super().__call__(ctx, path, fm, body)
        if self.clock:
            self.clock.offset += self.advance
        if self.usage is not None:
            with nr.SHARED:
                nr.rep.record_usage(ctx.vault, ctx.date, {"five_hour": self.usage, "seven_day": 0.1},
                                    ctx.clock_now().isoformat())
        return rc


def research_at(vault, tmp, title, at):
    brief = tmp / f"{title}.md"
    brief.write_text("## Question\nQ\n## Scope\nNotes.\n## Done when\nAnswered.\n## Output\nA note.\n")
    assert nr.main(["research", "--title", title, "--partition", "work", "--brief-file", str(brief),
                    "--output", f"wiki/work/concepts/{title}.md", "--at", at], vault, NOW) == 0


def test_an_order_due_later_in_the_tick_starts_when_its_time_comes(env, monkeypatch):
    # Review: the loop read the tick's start time, so an --at order due an hour in waited for the tick to end.
    vault, tmp = env
    clock = Clock(monkeypatch)
    fake = Timed(clock=clock, advance=3600)
    monkeypatch.setattr(nr, "run_item", fake)
    monkeypatch.setattr(nr, "MAX_PARALLEL", 1)
    research(vault, tmp, "first")
    research_at(vault, tmp, "later", "12:30")   # NOW is 12:00 in Denver; "first" moves the clock to 13:00
    assert nr.main(["tick"], vault, NOW) == 0
    assert states(vault) == {"first": "done", "later": "done"}


def test_no_order_starts_that_would_run_the_tick_past_13_hours(env, monkeypatch):
    # The unit stops the tick at 14h and kills its sessions with it; a queued order that would run past 13h waits.
    vault, tmp = env
    clock = Clock(monkeypatch)
    fake = Timed(clock=clock, advance=12.5 * 3600)
    monkeypatch.setattr(nr, "run_item", fake)
    monkeypatch.setattr(nr, "MAX_PARALLEL", 1)
    research(vault, tmp, "long")
    research(vault, tmp, "next")   # a research order's default budget is 1h: 12.5h + 1h is past 13h
    assert nr.main(["tick"], vault, NOW) == 0
    assert states(vault) == {"long": "done", "next": "queued"}


def test_a_reading_at_the_ceiling_from_a_finished_order_holds_the_next(env, monkeypatch):
    # Review Focus 5: the ceiling is read afresh before each start, so a finished session's reading counts.
    vault, tmp = env
    fake = Timed(usage=0.9)
    monkeypatch.setattr(nr, "run_item", fake)
    monkeypatch.setattr(nr, "MAX_PARALLEL", 1)
    research(vault, tmp, "first")
    research(vault, tmp, "second")
    assert nr.main(["tick"], vault, NOW) == 0
    assert states(vault) == {"first": "done", "second": "queued"}
    assert "> Held: 5-hour usage 90%" in (vault / nr.rep.DIR / "2026-10-07.md").read_text()


def test_a_hold_lifts_within_the_tick_when_a_lower_reading_arrives(env, monkeypatch):
    # Review: one hold stopped every later start in the tick, though the ceiling is checked before each start.
    vault, tmp = env
    fake = Timed(usage=0.1)
    monkeypatch.setattr(nr, "run_item", fake)
    research(vault, tmp, "started")
    research(vault, tmp, "queued")
    path = next(p for p, fm, _ in ni.items(vault) if slug(fm) == "started")
    ni.update(path, state="running", attempts="1", session_id="old")
    health_at(vault, 0.9, 1)
    assert nr.main(["tick"], vault, NOW) == 0
    assert states(vault) == {"started": "done", "queued": "done"}


def test_a_claim_left_by_a_stopped_tick_is_cleared_and_the_attempt_runs(env, monkeypatch):
    # #229 minor: a SIGTERM between _claim and run_item's attempts update leaves claim-1 while the note still reads
    # attempts 0. The tick holds the global lock, so that claim's owner is dead and attempt 1 never began: it runs.
    vault, tmp = env
    fake = Fake()
    monkeypatch.setattr(nr, "run_item", fake)
    research(vault, tmp, "claimed")
    research(vault, tmp, "free")
    (nr.rep.item_dir(vault, ids(vault)["claimed"]) / "claim-1").mkdir(parents=True)
    assert nr.main(["tick"], vault, NOW) == 0
    assert states(vault) == {"claimed": "done", "free": "done"}


def test_an_error_on_the_tick_waits_for_its_workers_before_the_lock_goes(env, monkeypatch):
    # Review: an exception on the main thread released the global lock while workers still ran their sessions.
    vault, tmp = env
    release = threading.Event()   # the worker runs until the tick starts joining: a tick that skips the join leaves it running
    fake = Fake(hold=release)
    monkeypatch.setattr(nr, "run_item", fake)
    join = nr._Pool.join_all

    def join_all(self):
        release.set()
        join(self)
    monkeypatch.setattr(nr._Pool, "join_all", join_all)
    research(vault, tmp, "running")
    research(vault, tmp, "next")
    real, calls = nr.ns.pick, []

    def pick(*a, **k):
        calls.append(1)
        if len(calls) > 1:
            raise ValueError("a hand-edited budget")
        return real(*a, **k)
    monkeypatch.setattr(nr.ns, "pick", pick)
    monkeypatch.setattr(nr, "MAX_PARALLEL", 2)
    with pytest.raises(ValueError):
        nr.main(["tick"], vault, NOW)
    assert fake.active == 0
    assert len(fake.ends) == len(fake.starts) == 1
