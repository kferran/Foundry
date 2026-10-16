"""Parallel Work Orders (#229, parallel orders spec §3): one tick runs up to MAX_PARALLEL items at once, refills a slot
when one finishes, never runs two plans on one repo and base together, and checks the 5-hour ceiling before each start.
run_item is replaced by a fake that records when each item starts and ends."""
import threading
import time

import pytest

from test_nightshift_run import NOW, add, env, git, health_at  # noqa: F401  (env is a fixture)
from vaultlib import nightshift_item as ni
from vaultlib import nightshift_run as nr


class Fake:
    def __init__(self, delay=0.3, fail=()):
        self.delay, self.fail, self.lock, self.active = delay, set(fail), threading.Lock(), 0
        self.peak, self.starts, self.ends, self.started = 0, {}, {}, []

    def __call__(self, ctx, path, fm, body):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.starts[fm["id"]] = time.monotonic()
            self.started.append(fm["id"])
        try:
            if slug(fm) in self.fail:
                raise RuntimeError("boom")
            time.sleep(self.delay)
            ni.update(path, state="done")
            return 0
        finally:
            with self.lock:
                self.active -= 1
                self.ends[fm["id"]] = time.monotonic()


def research(vault, tmp, title):
    brief = tmp / f"{title}.md"
    brief.write_text("## Question\nQ\n## Scope\nNotes.\n## Done when\nAnswered.\n## Output\nA note.\n")
    assert nr.main(["add", "--kind", "research", "--title", title, "--partition", "work", "--brief-file", str(brief),
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
    fake = Fake()
    monkeypatch.setattr(nr, "run_item", fake)
    for t in ("ra", "rb", "rc", "rd"):
        research(vault, tmp, t)
    assert nr.main(["tick"], vault, NOW) == 0
    assert fake.peak == 3
    assert {fm["state"] for _, fm, _ in ni.items(vault)} == {"done"}


def test_two_plans_on_one_repo_and_base_take_turns_while_research_runs_beside_them(env, monkeypatch):
    vault, tmp = env
    fake = Fake()
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
    fake = Fake()
    monkeypatch.setattr(nr, "run_item", fake)
    assert add(vault, "--now", "--title", "on x") == 0
    assert add(vault, "--now", "--title", "on y", "--base", "feat/y") == 0
    assert nr.main(["tick"], vault, NOW) == 0
    i = ids(vault)
    assert overlap(fake, i["on-x"], i["on-y"])


def test_the_ceiling_holds_new_starts_and_lets_a_running_item_resume(env, monkeypatch):
    vault, tmp = env
    fake = Fake(delay=0.05)
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
    fake = Fake(delay=0.05)
    monkeypatch.setattr(nr, "run_item", fake)
    monkeypatch.setattr(nr, "MAX_PARALLEL", 1)
    for t in ("ra", "rb"):
        research(vault, tmp, t)
    assert nr.main(["tick"], vault, NOW) == 0
    assert fake.peak == 1
    assert {fm["state"] for _, fm, _ in ni.items(vault)} == {"done"}
