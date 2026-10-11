"""emtk.audio: PCM clips through the system player, without Qt and without a real player."""
from __future__ import annotations

import threading
import wave

from emtk.audio import AudioOutput, find_player

PCM = b"\x00\x10" * 4410  # 0.1 s at 44.1 kHz


class FakeProc:
    def __init__(self, argv, log, hold):
        self.argv, self.log, self.hold = argv, log, hold
        self.done = threading.Event()
        if not hold:
            self.done.set()
        self.terminated = False

    def poll(self):
        return 0 if self.done.is_set() else None

    def wait(self):
        self.done.wait(2)

    def terminate(self):
        self.terminated = True
        self.done.set()


class Launcher:
    def __init__(self, hold=True):
        self.procs, self.hold = [], hold

    def __call__(self, argv):
        proc = FakeProc(argv, self, self.hold)
        self.procs.append(proc)
        return proc


def make(hold=True):
    launcher = Launcher(hold)
    out = AudioOutput(player=("/usr/bin/afplay", ("-v", "{volume}", "{path}")), launcher=launcher)
    return out, launcher


def test_find_player_prefers_the_first_installed():
    assert find_player(which=lambda n: "/x/" + n if n == "aplay" else None)[0] == "/x/aplay"
    assert find_player(which=lambda n: None) is None


def test_without_a_player_nothing_plays_and_nothing_raises():
    out = AudioOutput(player=None, launcher=Launcher())
    assert not out.available
    assert out.play("a", PCM, 44100) is False
    out.stop()
    out.close()


def test_play_writes_a_wav_and_passes_volume():
    out, launcher = make()
    assert out.play("blip", PCM, 44100, volume=0.5)
    argv = launcher.procs[0].argv
    assert argv[:3] == ["/usr/bin/afplay", "-v", "0.500"]
    with wave.open(argv[3]) as handle:
        assert (handle.getnchannels(), handle.getframerate(), handle.getnframes()) == (1, 44100, 4410)
    assert out.playing("blip")
    out.close()
    assert not out.available


def test_replaying_a_key_restarts_it_and_stop_terminates():
    out, launcher = make()
    out.play("m", PCM, 44100)
    first = launcher.procs[0]
    out.play("m", PCM, 44100)
    assert first.terminated and len(launcher.procs) == 2
    out.stop("m")
    assert launcher.procs[1].terminated and not out.playing("m")
    out.close()


def test_a_loop_is_tiled_and_relaunched_until_stopped():
    out, launcher = make()
    assert out.play("music", PCM, 44100, loop=True)
    with wave.open(launcher.procs[0].argv[-1]) as handle:
        assert handle.getnframes() >= 44100 * 30  # tiled toward a minute
    launcher.procs[0].done.set()  # the player exits: the watcher starts it again
    for _ in range(200):
        if len(launcher.procs) > 1:
            break
        threading.Event().wait(0.01)
    assert len(launcher.procs) == 2
    out.stop("music")
    assert launcher.procs[1].terminated
    threading.Event().wait(0.05)
    assert len(launcher.procs) == 2  # no relaunch after stop
    out.close()


def test_too_many_effects_at_once_drops_the_extra():
    out, launcher = make()
    results = [out.play(f"e{i}", PCM, 44100) for i in range(12)]
    assert results.count(True) == 8 and results.count(False) == 4
    out.close()


def test_a_failing_launcher_reports_false():
    def boom(argv):
        raise OSError("no")

    out = AudioOutput(player=("/p", ("{path}",)), launcher=boom)
    assert out.play("a", PCM, 44100) is False
    out.close()


def test_the_default_lookup_goes_through_the_module_attribute(monkeypatch):
    import emtk.audio as audio

    monkeypatch.setattr(audio, "find_player", lambda: None)
    assert not AudioOutput().available
