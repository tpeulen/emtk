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


# -- images ------------------------------------------------------------------ #
def _png() -> bytes:
    from emtk.testing import png_encode

    return png_encode(2, 1, bytes([255, 0, 0, 255, 0, 0, 255, 255]))


def test_an_image_hook_takes_the_png():
    got = []
    clipboard.set_image_hook(got.append)
    try:
        assert clipboard.copy_image(_png()) is True
    finally:
        clipboard.set_image_hook(None)
    assert got == [_png()]
    assert clipboard.last_copied_image()[1] == _png()


def test_copy_image_takes_png_only():
    import pytest

    with pytest.raises(ValueError):
        clipboard.copy_image(b"GIF89a")


def test_the_platform_image_command_gets_the_file(monkeypatch):
    runs = []

    def run(cmd, input, check, timeout, capture_output):
        import pathlib

        runs.append((cmd, input, pathlib.Path(cmd[-1]).read_bytes()))

    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setattr(clipboard.shutil, "which",
                        lambda name: None if name == "wl-copy" else "/bin/" + name)
    monkeypatch.setattr(clipboard.subprocess, "run", run)
    assert clipboard.copy_image(_png()) is True
    (cmd, stdin, data), = runs
    assert cmd[:5] == ["xclip", "-selection", "clipboard", "-t", "image/png"]
    assert stdin is None and data == _png()


def test_macos_reads_the_file_as_png_through_applescript(monkeypatch):
    monkeypatch.setattr(clipboard.sys, "platform", "darwin")
    (cmd, stdin), = clipboard.image_commands('/tmp/a "b".png')
    assert cmd[0] == "osascript" and "«class PNGf»" in cmd[2] and '\\"b\\"' in cmd[2]


def test_no_way_to_copy_an_image_says_so(monkeypatch):
    monkeypatch.setattr(clipboard.sys, "platform", "linux")
    monkeypatch.setattr(clipboard.shutil, "which", lambda name: None)
    assert clipboard.copy_image(_png()) is False
