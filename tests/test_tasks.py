"""emtk.tasks: one API for long work, threaded on a desktop, stepped in a browser."""
from __future__ import annotations

import sys
import time

import pytest

from emtk import tasks


def counting(task, n, fail_at=None):
    total = 0
    for i in range(n):
        if fail_at is not None and i == fail_at:
            raise ValueError("boom")
        total += i
        yield (i + 1) / n, f"step {i + 1}"
    return total


def plain(task, value):
    task.report(0.5, "half")
    return value * 2


@pytest.mark.parametrize("mode", tasks.MODES)
def test_generator_work_returns_its_result_in_every_mode(mode):
    task = tasks.start(counting, 5, mode=mode)
    task.wait(timeout=5)
    assert task.state == "done"
    assert task.result == sum(range(5))
    assert task.progress == 1.0
    assert task.message == "step 5"


@pytest.mark.parametrize("mode", tasks.MODES)
def test_plain_work_is_a_single_step(mode):
    task = tasks.start(plain, 21, mode=mode)
    task.wait(timeout=5)
    assert task.succeeded and task.result == 42


@pytest.mark.parametrize("mode", tasks.MODES)
def test_a_failure_is_the_tasks_state_not_an_exception(mode):
    task = tasks.start(counting, 5, fail_at=2, mode=mode)
    task.wait(timeout=5)
    assert task.state == "failed"
    assert "ValueError: boom" in task.error
    assert "Traceback" in task.traceback


def test_cooperative_poll_spends_its_budget_and_returns():
    seen = []

    def slow(task):
        for i in range(10):
            time.sleep(0.01)
            seen.append(i)
            yield i / 10
        return "ok"

    task = tasks.start(slow, mode="cooperative")
    assert task.running and not seen          # nothing runs until polled
    task.poll(budget=0.0)                     # at least one checkpoint
    assert 1 <= len(seen) < 10 and task.running
    while task.poll(budget=0.02) == "running":
        pass
    assert task.result == "ok" and len(seen) == 10


def test_cancel_stops_at_the_next_checkpoint():
    def forever(task):
        while True:
            yield None

    task = tasks.start(forever, mode="cooperative")
    task.poll(budget=0.001)
    task.cancel()
    assert task.poll() == "cancelled"
    assert task.result is None


def test_cancel_of_a_thread_drops_the_result():
    def sleepy(task):
        for _ in range(200):
            time.sleep(0.005)
            task.check()
        return "late"

    task = tasks.start(sleepy, mode="thread")
    task.cancel()
    assert task.wait(timeout=5) == "cancelled"
    assert task.result is None


def test_on_done_runs_once_on_the_polling_thread():
    calls = []
    task = tasks.start(counting, 3, mode="cooperative")
    task.on_done(lambda t: calls.append(t.result))
    while task.poll() == "running":
        pass
    task.poll()
    assert calls == [3]
    late = []
    task.on_done(lambda t: late.append(t.state))   # already finished: called at once
    assert late == ["done"]


def test_write_collects_a_log_like_a_file():
    def printing(task):
        print("first line", file=task)
        task.write("partial ")
        task.write("line\n")
        return None

    task = tasks.start(printing, mode="inline")
    assert task.log_text() == "first line\npartial line\n"


def test_no_threads_in_a_browser(monkeypatch):
    monkeypatch.setattr(sys, "platform", "emscripten")
    assert not tasks.threads_available()
    assert tasks.default_mode() == "cooperative"
    task = tasks.start(counting, 2, mode="thread")   # asked for a thread, gets steps
    assert task.mode == "cooperative"
    task.wait()
    assert task.result == 1


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        tasks.Task(plain, (1,), mode="process")
