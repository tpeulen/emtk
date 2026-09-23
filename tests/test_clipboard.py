"""emtk.clipboard: the host hook first, then a platform command, and an answer."""
from __future__ import annotations

import subprocess

from emtk import clipboard


def test_a_host_hook_takes_the_text():
    got = []
    clipboard.set_hook(got.append)
    try:
        assert clipboard.copy("a\tb\n") is True
    finally:
        clipboard.set_hook(None)
    assert got == ["a\tb\n"]


def test_the_platform_command_gets_the_text(monkeypatch):
    runs = []
    monkeypatch.setattr(clipboard, "commands", lambda: [["missing-tool"], ["fakecopy"]])
    monkeypatch.setattr(clipboard.shutil, "which",
                        lambda name: None if name == "missing-tool" else "/bin/" + name)
    monkeypatch.setattr(clipboard.subprocess, "run",
                        lambda cmd, input, check, timeout: runs.append((cmd, input)))
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    assert clipboard.copy("x") is True
    assert runs == [(["fakecopy"], b"x")]


def test_no_way_to_copy_says_so(monkeypatch):
    monkeypatch.setattr(clipboard, "commands", lambda: [["nothing"]])
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: None)
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    assert clipboard.copy("x") is False


def test_a_failing_command_falls_through(monkeypatch):
    def fail(*_a, **_k):
        raise subprocess.CalledProcessError(1, "x")

    monkeypatch.setattr(clipboard, "commands", lambda: [["a"]])
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: "/bin/a")
    monkeypatch.setattr(clipboard.subprocess, "run", fail)
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    assert clipboard.copy("x") is False
