"""``emtk.tasks`` -- long work beside an immediate-mode frame, on any host.

An emtk app draws a frame, returns, and draws the next. Work that takes longer
than a frame (a clustering over a hundred thousand rows, an embedding, an
install) must not sit inside ``draw``, or the window freezes until it is done.

On a desktop the answer is a thread. In a browser under Pyodide there are no
threads, and the same work has to be done a slice at a time between frames.
This module is the one API over both, so an application writes its work once:

.. code-block:: python

    def cluster(task, data, k):
        yield 0.1, "Preparing"             # a checkpoint: progress and a message
        if task.cancelled:                 # cancellation is cooperative
            return None
        labels = kmeans(data, k)
        yield 0.9, "Labelling"
        return labels                      # the task's result

    task = emtk.tasks.start(cluster, data, 3)
    ...
    # every frame
    task.poll()                            # advances it in a browser; cheap on a desktop
    if task.done:
        use(task.result)

Work is a callable taking the :class:`Task` first. A *generator* function
yields checkpoints -- ``fraction``, ``"message"``, ``(fraction, message)`` or
``None`` -- and returns its result; a plain function just returns it and may
report through :meth:`Task.report`. Where it runs is the runner's choice:

``"thread"``
    a daemon thread runs it to the end; :meth:`Task.poll` only reads state;
``"cooperative"``
    :meth:`Task.poll` advances the generator until the frame's time budget is
    spent (a plain function runs whole inside one poll -- the best a host with
    no threads can do);
``"inline"``
    it runs to the end inside :func:`start` -- deterministic, for tests and
    scripted captures.

The default is ``"thread"`` where threads exist and ``"cooperative"`` where
they do not (:func:`threads_available`). A host keeps redrawing while any task
it started is :attr:`~Task.running`, so a result appears without an input
event to wake it.
"""
from __future__ import annotations

import sys
import threading
import time
import traceback
from typing import Any, Callable, List, Optional

__all__ = ["Task", "TaskCancelled", "start", "threads_available", "default_mode", "MODES"]

#: How work can be run; see the module docstring.
MODES = ("thread", "cooperative", "inline")

#: Seconds of work a cooperative :meth:`Task.poll` does before it returns.
DEFAULT_BUDGET = 0.012


class TaskCancelled(Exception):
    """Raised inside work by :meth:`Task.check` once the task was cancelled."""


def threads_available() -> bool:
    """Whether this interpreter can start a thread (not so under Pyodide)."""
    if sys.platform == "emscripten" or "pyodide" in sys.modules:
        return False
    return True


def default_mode() -> str:
    """``"thread"`` on a desktop, ``"cooperative"`` in a browser."""
    return "thread" if threads_available() else "cooperative"


class Task:
    """One piece of work and what is known about it.

    Attributes
    ----------
    state : str
        ``"pending"``, ``"running"``, ``"done"``, ``"failed"`` or ``"cancelled"``.
    progress : float or None
        Fraction done in ``[0, 1]``, ``None`` while unknown (an indeterminate
        bar).
    message : str
        The last status line the work reported.
    log : list of str
        Every line the work wrote with :meth:`write` -- a console to show.
    result : object
        What the work returned, once :attr:`state` is ``"done"``.
    error : str
        The exception's text, once :attr:`state` is ``"failed"``.
    traceback : str
        Its traceback, for a log.
    mode : str
        Where it runs (:data:`MODES`).
    """

    def __init__(self, work: Callable[..., Any], args: tuple = (), kwargs: Optional[dict] = None,
                 mode: Optional[str] = None, name: str = "") -> None:
        mode = mode or default_mode()
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
        if mode == "thread" and not threads_available():
            mode = "cooperative"
        self.work = work
        self.args = tuple(args)
        self.kwargs = dict(kwargs or {})
        self.mode = mode
        self.name = name or getattr(work, "__name__", "task")
        self.state = "pending"
        self.progress: Optional[float] = None
        self.message = ""
        self.log: List[str] = []
        self.result: Any = None
        self.error = ""
        self.traceback = ""
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None
        self._cancel = False
        self._lock = threading.Lock()
        self._gen = None
        self._thread: Optional[threading.Thread] = None
        self._callbacks: List[Callable[["Task"], None]] = []
        self._notified = False

    # ---------------------------------------------------------------- state
    @property
    def running(self) -> bool:
        """Started and not finished."""
        return self.state in ("pending", "running")

    @property
    def done(self) -> bool:
        """Finished, whichever way."""
        return self.state in ("done", "failed", "cancelled")

    @property
    def succeeded(self) -> bool:
        return self.state == "done"

    @property
    def cancelled(self) -> bool:
        """Whether :meth:`cancel` was asked for; work checks this at its checkpoints."""
        return self._cancel

    @property
    def elapsed(self) -> float:
        """Seconds since it started (to the end, once finished)."""
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return end - self.started_at

    def cancel(self) -> None:
        """Ask the work to stop at its next checkpoint.

        A thread cannot be killed, so a task that is inside a long call keeps
        running until it next yields or checks; its result is then dropped and
        its state becomes ``"cancelled"``.
        """
        self._cancel = True
        if self.state == "pending":
            self._finish("cancelled")

    def check(self) -> None:
        """Raise :class:`TaskCancelled` if the task was cancelled -- a checkpoint
        for plain-function work."""
        if self._cancel:
            raise TaskCancelled()

    def report(self, progress: Optional[float] = None, message: Optional[str] = None) -> None:
        """Set the progress and/or the status line (safe from the worker thread)."""
        with self._lock:
            if progress is not None:
                self.progress = min(max(float(progress), 0.0), 1.0)
            if message is not None:
                self.message = str(message)

    def write(self, text: str) -> None:
        """Append to :attr:`log`; a file-like ``write`` so work can print into it."""
        if not text:
            return
        with self._lock:
            if self.log and not self.log[-1].endswith("\n"):
                self.log[-1] += text
            else:
                self.log.append(text)

    def flush(self) -> None:
        """For the file-like protocol."""

    def log_text(self) -> str:
        """The log as one string."""
        with self._lock:
            return "".join(self.log)

    def on_done(self, callback: Callable[["Task"], None]) -> None:
        """Call *callback(task)* once, from :meth:`poll`, when the task finishes.

        Callbacks run on the thread that polls -- the frame's -- never on the
        worker, so they may touch the app's state.
        """
        if self._notified:
            callback(self)
            return
        self._callbacks.append(callback)
        if self.done:
            self._notify()

    # -------------------------------------------------------------- running
    def start(self) -> "Task":
        """Begin the work (called by :func:`start`)."""
        if self.state != "pending":
            return self
        self.state = "running"
        self.started_at = time.monotonic()
        if self.mode == "thread":
            self._thread = threading.Thread(target=self._run_all, name=f"emtk-task-{self.name}",
                                            daemon=True)
            self._thread.start()
        elif self.mode == "inline":
            self._run_all()
            self._notify()
        return self

    def _checkpoint(self, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, tuple) and len(value) == 2:
            self.report(value[0], value[1])
        elif isinstance(value, str):
            self.report(None, value)
        else:
            try:
                self.report(float(value), None)
            except (TypeError, ValueError):
                pass

    def _begin(self):
        """Call the work; a generator is kept to be stepped, anything else is the result."""
        out = self.work(self, *self.args, **self.kwargs)
        if hasattr(out, "__next__") and hasattr(out, "send"):
            self._gen = out
            return False, None
        return True, out

    def _step(self) -> bool:
        """Advance one checkpoint; ``True`` when the work has finished."""
        try:
            if self._gen is None:
                finished, value = self._begin()
                if finished:
                    self._complete(value)
                    return True
            value = next(self._gen)
        except StopIteration as stop:
            self._complete(stop.value)
            return True
        except TaskCancelled:
            self._finish("cancelled")
            return True
        except Exception as exc:  # noqa: BLE001 - the work's failure is the task's state
            self.error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            self.traceback = traceback.format_exc()
            self._finish("failed")
            return True
        self._checkpoint(value)
        if self._cancel:
            try:
                self._gen.close()
            except Exception:  # noqa: BLE001
                pass
            self._finish("cancelled")
            return True
        return False

    def _complete(self, value: Any) -> None:
        if self._cancel:
            self._finish("cancelled")
            return
        self.result = value
        self.progress = 1.0
        self._finish("done")

    def _finish(self, state: str) -> None:
        self.state = state
        self.finished_at = time.monotonic()

    def _run_all(self) -> None:
        while not self._step():
            pass

    def poll(self, budget: float = DEFAULT_BUDGET) -> str:
        """Advance or observe the work; returns :attr:`state`.

        Call once per frame. A cooperative task runs checkpoints until
        *budget* seconds have passed (at least one); a threaded one is only
        read. Callbacks of :meth:`on_done` run here, once.
        """
        if self.mode == "cooperative" and self.state == "running":
            deadline = time.monotonic() + max(float(budget), 0.0)
            while not self._step():
                if time.monotonic() >= deadline:
                    break
        if self.done:
            self._notify()
        return self.state

    def wait(self, timeout: Optional[float] = None) -> str:
        """Block until finished (tests and scripts; never from a frame).

        A cooperative task is stepped here; a threaded one is joined.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        if self.mode == "thread" and self._thread is not None:
            self._thread.join(timeout)
        else:
            while self.state == "running":
                self.poll(budget=0.05)
                if deadline is not None and time.monotonic() >= deadline:
                    break
        if self.done:
            self._notify()
        return self.state

    def _notify(self) -> None:
        if self._notified:
            return
        self._notified = True
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback(self)


def start(work: Callable[..., Any], *args: Any, mode: Optional[str] = None, name: str = "",
          **kwargs: Any) -> Task:
    """Start *work(task, \\*args, \\*\\*kwargs)* and return its :class:`Task`.

    Parameters
    ----------
    work : callable
        A generator function yielding checkpoints, or a plain function.
    mode : str, optional
        ``"thread"``, ``"cooperative"`` or ``"inline"``; the host's default
        (:func:`default_mode`) otherwise. ``"thread"`` where there are no
        threads becomes ``"cooperative"``.
    name : str, optional
        For the thread's name and logs.
    """
    return Task(work, args, kwargs, mode=mode, name=name).start()
