"""Qt-free audio output: play PCM clips and loops through the system player.

emtk draws and takes input; it did not make a sound.  :class:`AudioOutput` closes that with no
dependency: each clip is written as a WAV file in a private temp directory and handed to whatever
command-line player the machine has (``afplay`` on macOS, ``paplay``/``aplay`` on Linux, ``ffplay`` as
the fallback).  That is coarse next to a mixer, but it is enough for short effects and music loops, and
it works everywhere emtk runs.  Callers synthesise the samples (16-bit mono PCM) themselves.

A loop is a clip tiled to about :data:`LOOP_SECONDS` and restarted when the player exits, so the seam is
heard once a minute rather than once per bar.  Nothing here raises when no player exists:
:attr:`AudioOutput.available` says so and :meth:`AudioOutput.play` returns ``False``.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

#: Clips shorter than this are tiled up to it when looping.
LOOP_SECONDS = 60.0
#: Effects playing at once; a further one is dropped rather than queued (a late effect is worse than none).
MAX_VOICES = 8

#: ``(binary, argument template)``; ``{path}`` and ``{volume}`` are substituted.
PLAYERS = (
    ("afplay", ("-v", "{volume}", "{path}")),
    ("paplay", ("--volume={pa_volume}", "{path}")),
    ("aplay", ("-q", "{path}")),
    ("ffplay", ("-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", "{percent}", "{path}")),
)


def find_player(which=shutil.which):
    """Return the first installed player as ``(binary_path, template)``, or ``None``."""
    for name, template in PLAYERS:
        path = which(name)
        if path:
            return path, template
    return None


def write_wav(path: Path, pcm: bytes, rate: int) -> Path:
    """Write 16-bit mono *pcm* at *rate* Hz to *path* and return it."""
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(rate))
        handle.writeframes(pcm)
    return path


class AudioOutput:
    """Plays PCM clips by key; one voice per key (replaying a key restarts it).

    Parameters
    ----------
    player : tuple, optional
        ``(binary, template)`` as from :func:`find_player`; default is to look one up (``find``, default
        the module's :func:`find_player`, so a test can patch it).  ``player=None`` is an output that is
        not :attr:`available`.
    launcher : callable, optional
        ``launcher(argv) -> process`` with ``poll``/``terminate``/``wait``; default :class:`subprocess.Popen`
        with silenced output.  Tests inject a fake.
    """

    def __init__(self, player=..., launcher=None, find=None):
        self._player = (find or find_player)() if player is ... else player
        self._launch = launcher or self._popen
        self._dir = None
        self._voices: dict[str, _Voice] = {}
        self._lock = threading.RLock()
        self._closed = False

    @staticmethod
    def _popen(argv):
        return subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    @property
    def available(self) -> bool:
        """Whether a player exists and the output is open."""
        return self._player is not None and not self._closed

    def _argv(self, path: Path, volume: float):
        binary, template = self._player
        volume = max(0.0, min(1.0, float(volume)))
        fields = {
            "path": str(path),
            "volume": f"{volume:.3f}",
            "percent": str(int(round(volume * 100))),
            "pa_volume": str(int(round(volume * 65536))),
        }
        return [binary] + [part.format(**fields) for part in template]

    def _file(self, key: str, pcm: bytes, rate: int) -> Path:
        if self._dir is None:
            self._dir = Path(tempfile.mkdtemp(prefix="emtk-audio-"))
        digest = hashlib.sha1(pcm + str(rate).encode()).hexdigest()[:16]
        path = self._dir / f"{key.replace('/', '_')}-{digest}.wav"
        if not path.exists():
            write_wav(path, pcm, rate)
        return path

    def play(self, key: str, pcm: bytes, rate: int, *, loop: bool = False, volume: float = 1.0) -> bool:
        """Start *pcm* under *key*; a loop restarts until :meth:`stop`.  False when nothing can play."""
        if not self.available or not pcm:
            return False
        if loop:
            seconds = len(pcm) / 2 / float(rate)
            repeats = max(1, int(LOOP_SECONDS // max(seconds, 1e-3)))
            pcm = pcm * repeats
        with self._lock:
            self.stop(key)
            if not loop and sum(not v.finished for v in self._voices.values() if not v.loop) >= MAX_VOICES:
                return False
            path = self._file(key + ("-loop" if loop else ""), pcm, rate)
            voice = _Voice(self._launch, self._argv(path, volume), loop)
            if not voice.start():
                return False
            self._voices[key] = voice
            self._voices = {k: v for k, v in self._voices.items() if v.loop or not v.finished}
            return True

    def playing(self, key: str) -> bool:
        """Whether *key* is still sounding."""
        with self._lock:
            voice = self._voices.get(key)
            return voice is not None and not voice.finished

    def stop(self, key: str | None = None) -> None:
        """Stop one voice, or all of them when *key* is ``None``."""
        with self._lock:
            keys = list(self._voices) if key is None else [key]
            for name in keys:
                voice = self._voices.pop(name, None)
                if voice is not None:
                    voice.stop()

    def close(self) -> None:
        """Stop everything, remove the temp files and refuse further playback."""
        self.stop()
        self._closed = True
        if self._dir is not None:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None


class _Voice:
    """One running player process; a looping voice relaunches it from a watcher thread."""

    def __init__(self, launch, argv, loop):
        self._launch, self._argv, self.loop = launch, argv, loop
        self._proc = None
        self._stopped = False
        self._lock = threading.Lock()

    @property
    def finished(self) -> bool:
        proc = self._proc
        return self._stopped or proc is None or (not self.loop and proc.poll() is not None)

    def start(self) -> bool:
        try:
            self._proc = self._launch(self._argv)
        except OSError:
            return False
        if self.loop:
            threading.Thread(target=self._watch, name="emtk-audio-loop", daemon=True).start()
        return True

    def _watch(self):
        while True:
            proc = self._proc
            try:
                proc.wait()
            except Exception:
                return
            with self._lock:
                if self._stopped:
                    return
                try:
                    self._proc = self._launch(self._argv)
                except OSError:
                    self._stopped = True
                    return

    def stop(self):
        with self._lock:
            self._stopped = True
            proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
