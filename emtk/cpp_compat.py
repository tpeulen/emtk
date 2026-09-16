"""What a *ported* C++ program reaches for that Python has no wordical for.

:mod:`emtk.im` covers Dear ImGui. This covers the rest of the C++ that comes
with it -- ``std::to_string``, ``static_cast``, ``sizeof``, ``printf`` -- so a
mechanically ported source is a module that imports rather than a module that
NameErrors on its first line. Every name here is a *thin* stand-in with the
same meaning, never a re-implementation: ``std.max`` is ``max``.

An ImGui *extension* barely needs this; an ImGui *application* needs it on
every screen, because the interface code is written against the standard
library as much as against the toolkit.

Where C++ and Python genuinely differ the difference is preserved rather than
papered over, and said out loud:

* ``std.string`` is ``str``, so ``s.append(x)`` is not ``s + x``. Ported code
  that mutates a string in place needs a hand, and autoport flags it.
* ``sizeof`` has no meaning here -- Python has no fixed-width storage. It
  returns the element count where that is what the C++ meant (``sizeof(buf)``
  for a char buffer) and raises otherwise, rather than returning a number
  that would be silently wrong.
"""

from __future__ import annotations

import math as _math
import time as _time
import re as _re
import sys as _sys

__all__ = ["std", "String", "Vector", "Set", "Duration",
           "json_is_object", "json_is_array", "json_is_string",
           "json_is_boolean", "json_is_number", "json_is_null",
           "json_is_number_integer", "json_is_number_float",
           "static_cast", "reinterpret_cast", "const_cast",
           "dynamic_cast", "sizeof", "memset", "memcpy", "strncpy", "strcmp",
           "popen", "pclose", "fgets", "stdout", "stderr", "stdin",
           "printf", "fprintf", "snprintf", "FLT_MIN", "FLT_MAX", "DBL_MAX",
           "INT_MAX", "INT_MIN", "UINT_MAX", "NULL", "nullptr"]

#: The C limits a ported source names as literals.
FLT_MIN = 1.175494351e-38
FLT_MAX = 3.402823466e+38
DBL_MAX = _sys.float_info.max
INT_MAX = 2 ** 31 - 1
INT_MIN = -(2 ** 31)
UINT_MAX = 2 ** 32 - 1
NULL = nullptr = None


#: ``nlohmann::json``'s type predicates, as functions over ordinary Python
#: values. A parsed document here is dicts, lists, str, int, float, bool and
#: None -- there is nothing to wrap, so ``j.is_array()`` becomes a question
#: about the value rather than a method it has to carry. autoport rewrites
#: the call sites; these are what it rewrites them to.
#:
#: ``is_number_integer`` is not ``isinstance(x, int)``: in Python a bool *is*
#: an int, and JSON's ``true`` is not a number.
def json_is_object(v) -> bool:
    return isinstance(v, dict)


def json_is_array(v) -> bool:
    return isinstance(v, (list, tuple))


def json_is_string(v) -> bool:
    return isinstance(v, str)


def json_is_boolean(v) -> bool:
    return isinstance(v, bool)


def json_is_number_integer(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def json_is_number_float(v) -> bool:
    return isinstance(v, float)


def json_is_number(v) -> bool:
    return json_is_number_integer(v) or isinstance(v, float)


def json_is_null(v) -> bool:
    return v is None


class String(str):
    """``std::string`` -- a ``str`` that also carries ``npos``.

    ``s.find(x) == std::string::npos`` is *the* C++ idiom for "not found",
    and it ports unchanged because Python's ``str.find`` returns -1 for the
    same case. What it needs is somewhere for ``npos`` itself to resolve, and
    ``std.string`` being plain ``str`` gave an AttributeError on the constant
    rather than on anything to do with the search.

    Constructing one from a *character buffer* stops at the first NUL, as
    ``std::string(char *)`` does -- which is what makes the C idiom
    ``fgets(buf, sizeof buf, f); std::string s(buf);`` port as written.
    """

    __slots__ = ()
    npos = -1

    def __new__(cls, value=""):
        if isinstance(value, (list, tuple, bytearray)):
            chars = []
            for c in value:
                if c is None or c == "\0" or c == 0:
                    break
                chars.append(chr(c) if isinstance(c, int) else str(c))
            value = "".join(chars)
        elif isinstance(value, bytes):
            value = value.split(b"\0", 1)[0].decode("utf-8", "replace")
        return super().__new__(cls, value)

    def substr(self, pos=0, count=None):
        """``s.substr(pos, count)`` -- *count* characters, not an end index."""
        return String(self[pos:] if count is None else self[pos:pos + int(count)])


class Set(set):
    """A ``set`` that also answers to ``std::set``'s method names.

    Same bargain as :class:`Vector`: everything a set already does right is
    kept, and only the spellings are added. ``insert`` is not ``add`` and
    ``count`` is not ``in``, so a ported line said neither until now.
    """

    __slots__ = ()

    def insert(self, x):
        """``s.insert(x)`` -> ``(None, inserted)``.

        C++ returns ``pair<iterator, bool>`` and the idiom is to read the
        flag: ``if (seen.insert(v).second)`` -- "if it was not already
        there". That ports to ``seen.insert(v)[1]``, so the pair is what has
        to come back. The iterator half is ``None`` because a C++ iterator
        has no Python equivalent worth faking, and nothing reads it: the
        whole point of the idiom is the flag.
        """
        fresh = x not in self
        self.add(x)
        return (None, fresh)

    def count(self, x) -> int:
        """``s.count(x)`` -- 0 or 1 for a ``std::set``, as in C++."""
        return 1 if x in self else 0

    def contains(self, x) -> bool:
        return x in self

    def erase(self, x) -> int:
        self.discard(x)
        return 0

    def size(self) -> int:
        return len(self)

    def empty(self) -> bool:
        return not self


class Vector(list):
    """A ``list`` that also answers to ``std::vector``'s method names.

    Ported code says ``v.push_back(x)`` and ``v.resize(n)``, and a plain list
    has neither -- so a vector member ported to ``[]`` failed on its first
    *use* rather than where the mismatch is. Subclassing keeps everything a
    list already does right (indexing, slicing, iteration, ``len``, equality
    against a plain list, printing) and adds only the spellings, so nothing
    downstream has to know which of the two it was handed.

    The iterator-taking overloads are deliberately absent: C++ iterators have
    no Python equivalent worth faking, and ``v.erase(it)`` needs a hand.
    """

    __slots__ = ()

    def push_back(self, x):
        self.append(x)

    def pop_back(self):
        del self[-1]

    def emplace_back(self, *a, **kw):
        # ``emplace_back(a, b)`` constructs in place from the arguments; with
        # no type to construct, one argument is the value and several are a
        # tuple -- which is what a ported ``pair``/aggregate push comes to.
        self.append(a[0] if len(a) == 1 and not kw else a)
        return self[-1]

    def size(self):
        return len(self)

    def empty(self):
        return not self

    def resize(self, n, value=None):
        n = int(n)
        if n < len(self):
            del self[n:]
        else:
            self.extend([value] * (n - len(self)))

    def assign(self, n, value=None):
        """``v.assign(n, x)`` -- n copies of x. The iterator-pair overload
        (``assign(first, last)``) is not this; it needs a hand."""
        self[:] = [value] * int(n)

    def at(self, i):
        return self[i]

    def front(self):
        return self[0]

    def back(self):
        return self[-1]

    def data(self):
        return self

    def begin(self):
        """``v.begin()`` -- the container itself.

        A C++ iterator has no Python form, and every algorithm that takes a
        pair of them (`std::fill(v.begin(), v.end(), x)`, `std::sort`) means
        *the whole container* when handed `begin()` and `end()`. Returning
        `self` from both is what makes that idiom port as written; a
        sub-range still cannot be expressed, and the algorithms say so
        rather than guessing.
        """
        return self

    end = begin

    def reserve(self, _n):
        """No-op: a Python list has no separate capacity to reserve."""

    def shrink_to_fit(self):
        """No-op, for the same reason as :meth:`reserve`."""


class Duration:
    """A ``std::chrono`` duration: seconds inside, whatever unit was asked for
    at ``count()``.

    The unit is the C++ *template argument*
    (``duration_cast<milliseconds>``), which autoport carries across as a
    name -- without it ``.count()`` counted nothing in particular, and a
    timeout compared in milliseconds against a value that had become seconds
    is silently off by a thousand.
    """

    #: How many of each unit make a second. `double`/`float` are the
    #: `duration<double>` spelling, which is seconds by definition.
    PER_SECOND = {
        "nanoseconds": 1e9, "microseconds": 1e6, "milliseconds": 1e3,
        "seconds": 1.0, "minutes": 1.0 / 60.0, "hours": 1.0 / 3600.0,
        "double": 1.0, "float": 1.0,
    }

    __slots__ = ("seconds", "unit")

    def __init__(self, seconds: float, unit: str = "seconds") -> None:
        self.seconds = float(seconds)
        self.unit = unit

    def count(self) -> float:
        try:
            return self.seconds * self.PER_SECOND[self.unit]
        except KeyError:
            raise KeyError(
                f"std::chrono unit {self.unit!r} has no conversion here. Add "
                f"it to Duration.PER_SECOND if it has a fixed ratio to a "
                f"second.") from None

    def __float__(self) -> float:
        return self.count()


class _Clock:
    """``steady_clock`` / ``system_clock``. ``now()`` is seconds as a float,
    so subtracting two of them is already a duration in seconds -- which is
    what :class:`Duration` is handed."""

    @staticmethod
    def now() -> float:
        return _time.monotonic()


class _Chrono:
    steady_clock = _Clock()
    high_resolution_clock = _Clock()
    system_clock = _Clock()

    @staticmethod
    def duration_cast(value, unit: str = "seconds") -> Duration:
        return Duration(float(value), unit)

    #: `std::chrono::duration<double>(a - b)` -- the same thing spelled as a
    #: constructor rather than a cast.
    duration = duration_cast


class _Std:
    """``std::`` as an object, so ``std.max(a, b)`` resolves.

    Only the names a user interface actually uses. A missing one raises
    ``AttributeError`` naming itself, which is the honest outcome: better a
    clear failure at the call site than a stub returning something plausible.
    """

    # -- <algorithm> / <cmath>: the same functions, different spelling ----- #
    max = staticmethod(max)
    min = staticmethod(min)
    abs = staticmethod(abs)
    round = staticmethod(round)
    sort = staticmethod(sorted)
    floor = staticmethod(_math.floor)
    ceil = staticmethod(_math.ceil)
    sqrt = staticmethod(_math.sqrt)
    pow = staticmethod(_math.pow)
    exp = staticmethod(_math.exp)
    log = staticmethod(_math.log)
    log10 = staticmethod(_math.log10)
    sin = staticmethod(_math.sin)
    cos = staticmethod(_math.cos)
    tan = staticmethod(_math.tan)
    atan2 = staticmethod(_math.atan2)
    isnan = staticmethod(_math.isnan)
    isinf = staticmethod(_math.isinf)
    isfinite = staticmethod(_math.isfinite)

    chrono = _Chrono()

    @staticmethod
    def getenv(name, default=None):
        """``std::getenv``. Returns ``None`` when unset, as C does -- so the
        C++ idiom `if (const char *p = std::getenv("X"))` ports and still
        reads as "is it set"."""
        import os

        return os.environ.get(str(name), default)

    # -- the container and string types, as their Python equivalents ------- #
    string = String
    map = staticmethod(dict)
    unordered_map = staticmethod(dict)
    @staticmethod
    def set(values=()):
        """``std::set<T>`` -- a :class:`Set`, which is a ``set``."""
        return Set(values)

    unordered_set = set
    pair = staticmethod(lambda a=None, b=None: (a, b))

    @staticmethod
    def array(*args):
        """``std::array<int, 3>{46, 204, 113}``.

        A braced initialiser ports to a *call*, so this arrives as three
        arguments -- not as one iterable, which is what plain ``list`` would
        accept. Both spellings work: several arguments are the values, one
        iterable is a copy of it.
        """
        if len(args) == 1 and isinstance(args[0], (list, tuple, bytes, bytearray, range)):
            return list(args[0])
        return list(args)

    @staticmethod
    def vector(*args):
        """``std::vector<T>`` -- a :class:`Vector`, which is a ``list``.

        Same argument shape as :meth:`array`: the values, or one iterable to
        copy. ``std::vector<T> v;`` ports to ``std.vector()``, an empty one.
        """
        if len(args) == 1 and isinstance(args[0], (list, tuple, bytes, bytearray, range)):
            return Vector(args[0])
        return Vector(args)

    @staticmethod
    def lock_guard(*_mutexes):
        """``std::lock_guard`` / ``scoped_lock`` / ``unique_lock``.

        Does nothing, and that is the faithful answer rather than a
        convenience: a lock exists to keep *two threads* apart, and a port
        of a user interface has one. Where the C++ shares data with a worker
        it started itself, the worker did not come across the boundary -- it
        is still C++, behind the bridge, holding the real mutex. There is no
        second thread on this side for a stand-in to exclude.

        It is not a context manager on purpose: the C++ declares it as a
        local whose *scope* is the critical section, and that ports to a
        bare statement. Making it a ``with`` would need the port to find the
        end of the scope, which is exactly what it cannot do.
        """
        return None

    scoped_lock = unique_lock = lock_guard

    @staticmethod
    def record(**fields):
        """An anonymous ``struct`` local, as an object with those fields.

        ``struct { uint8_t r, g, b; } c = {255, 255, 255};`` is a throwaway
        record -- C++ has no name for its type and neither does this. What
        the code goes on to do is read ``c.r``, so a namespace is the whole
        of what it needs. Not a tuple: the members are reached by *name*.
        """
        from types import SimpleNamespace

        return SimpleNamespace(**fields)

    @staticmethod
    def fill(*args):
        """``std::fill(first, last, value)`` -- the whole container.

        C++ iterators do not survive the port: `v.begin()` and `v.end()`
        have no Python form, so what arrives is the container twice and the
        value. Filling the whole thing is the faithful reading of the idiom
        that is written 99 times in 100 -- and a *partial* fill, which is
        the other 1, cannot be expressed with what got here, so it is left
        to raise rather than quietly filling too much.
        """
        if len(args) == 2:
            seq, value = args
        elif len(args) == 3 and args[0] is args[1]:
            seq, value = args[0], args[2]
        else:
            raise TypeError(
                "std::fill over a sub-range: the iterators did not survive "
                "the port, so this cannot be done faithfully. Translate the "
                "line by hand.")
        for i in range(len(seq)):
            seq[i] = value
        return seq

    @staticmethod
    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    @staticmethod
    def to_string(v) -> str:
        """``std::to_string``. C++ prints a float with six decimals; Python's
        ``str`` does not, and a label that reads ``0.1`` where the C++ read
        ``0.100000`` is a visible difference, so the C++ form is kept."""
        if isinstance(v, bool):
            return "1" if v else "0"
        if isinstance(v, float):
            return f"{v:.6f}"
        return str(v)

    @staticmethod
    def stoi(s, *_a):
        return int(str(s).strip() or 0)

    @staticmethod
    def stod(s, *_a):
        return float(str(s).strip() or 0.0)

    @staticmethod
    def stof(s, *_a):
        return float(str(s).strip() or 0.0)

    @staticmethod
    def move(v):
        """``std::move`` is a cast, and Python has no ownership to transfer."""
        return v

    @staticmethod
    def make_unique(cls, *args, **kw):
        return cls(*args, **kw)

    make_shared = make_unique

    @staticmethod
    def swap(a, b):
        return b, a

    def __getattr__(self, name):
        raise AttributeError(
            f"std::{name} has no emtk.cpp_compat stand-in. Add one if it has a "
            f"faithful Python equivalent; translate the call by hand if it "
            f"does not.")


std = _Std()


# -- the casts ------------------------------------------------------------- #
def static_cast(value, _type=None):
    """``static_cast<T>(v)``. autoport strips the ``<T>``, so the type is
    gone by the time this is called and the value passes through -- which is
    what the cast meant in every numeric use. A cast that *changed* the value
    (a float truncated to int) is a difference autoport flags at the site."""
    return value


reinterpret_cast = const_cast = dynamic_cast = static_cast


def sizeof(obj) -> int:
    """``sizeof``, only where it has a meaning here.

    In ported code it appears as ``sizeof(buf)`` -- the capacity of a char
    buffer, which is its length. For anything without a length there is no
    honest answer, and a plausible number would be silently wrong, so this
    raises instead.
    """
    try:
        return len(obj)
    except TypeError:
        raise TypeError(
            f"sizeof({type(obj).__name__}) has no meaning in Python: there is "
            f"no fixed-width storage to measure. Translate this line by hand."
        ) from None


def memset(buf, value, count=None):
    """``memset``. Fills a mutable sequence; a read-only one is a bug worth
    hearing about rather than silently ignoring."""
    n = len(buf) if count is None else min(int(count), len(buf))
    for i in range(n):
        buf[i] = value
    return buf


def memcpy(dst, src, count=None):
    n = len(src) if count is None else int(count)
    for i in range(min(n, len(dst), len(src))):
        dst[i] = src[i]
    return dst


def popen(command, mode="r"):
    """``popen`` -- run a command and read its output as a stream.

    Application code shells out for device discovery (``sigrok-cli --scan``),
    and there is nothing un-Pythonic about that, so it is the same call.
    """
    import os as _os
    return _os.popen(command, mode)


def pclose(stream):
    """``pclose``. Returns the exit status, as the C does -- ``None`` from
    ``file.close()`` would read as success whatever happened."""
    return stream.close() or 0


def fgets(buf, size, stream):
    """``fgets(buf, size, stream)`` -- one line, written *through* the buffer.

    C returns the buffer and reports end-of-file by returning NULL, and the
    caller then reads the buffer. Python cannot write through an argument
    unless the argument is mutable, and the ported buffer is a list -- so it
    is filled here, NUL-terminated, and the line is returned as well. That
    makes ``while (fgets(b, sizeof b, p)) { std::string s(b); ... }`` port
    with no change at all: :class:`String` stops at the NUL.
    """
    line = stream.readline()
    if not line:
        return None
    line = line[:max(0, int(size) - 1)]
    if isinstance(buf, (list, bytearray)):
        for i, ch in enumerate(line):
            buf[i] = ch
        if len(line) < len(buf):
            buf[len(line)] = None if isinstance(buf, list) else 0
    return line


def strncpy(dst, src, count=None):
    """``strncpy``. Writes *through* a mutable buffer, and returns the copy.

    The C idiom is a `char` array filled in place and then handed to
    something that reads it::

        char buf[128];
        strncpy(buf, s.c_str(), sizeof(buf) - 1);
        buf[sizeof(buf) - 1] = '\\0';
        ImGui::InputText("##ip", buf, sizeof(buf));

    which ports line for line only if the buffer really is filled -- and a
    ``str`` cannot be written through, so the buffer on this side is a list
    and this fills it. The copy comes back as well, for the case where the
    destination is a ``str`` and there is nothing to write into.
    """
    text = str(src)
    if count is not None:
        text = text[:int(count)]
    if isinstance(dst, (list, bytearray)):
        for i, ch in enumerate(text[:len(dst)]):
            dst[i] = ch
        if len(text) < len(dst):
            dst[len(text)] = None if isinstance(dst, list) else 0
    return text


def strcmp(a, b) -> int:
    a, b = str(a), str(b)
    return 0 if a == b else (-1 if a < b else 1)


#: C length modifiers Python's ``%`` has never heard of. ``%zu`` for a
#: ``size_t`` and ``%llu`` for a count are what 64-bit code writes, and they
#: reach here verbatim -- autoport rewrites the *format strings* it knows are
#: formats (``ImGui::Text``), but a bare ``printf`` carries the C spelling
#: through to this stand-in, which is where it has to be understood.
_C_SPEC = _re.compile(r"%([-+ #0]*)(\d*)(?:\.(\d+))?(hh|h|ll|l|z|j|t|L)?([diuxXoeEfgGcs%])")


def _py_format(fmt: str) -> str:
    """A C format string as Python's ``%`` operator understands it."""
    def one(m):
        flags, width, prec, _length, conv = m.groups()
        if conv == "%":
            return "%%"
        if conv in "iu":                 # neither is a Python conversion
            conv = "d"
        return f"%{flags}{width}{'.' + prec if prec else ''}{conv}"
    return _C_SPEC.sub(one, fmt)


def printf(fmt, *args) -> None:
    print((_py_format(fmt) % args) if args else fmt, end="")


#: ``<cstdio>``'s three streams, so `fprintf(stderr, ...)` resolves. The
#: names exist for the *call* to name them -- `fprintf` below writes to the
#: stream it is handed, and a port that says `stderr` means Python's.
stdout = _sys.stdout
stderr = _sys.stderr
stdin = _sys.stdin


def fprintf(stream, fmt, *args) -> None:
    """``fprintf``. Honours the stream it is given.

    It used to send everything to stderr whatever it was handed, so a port's
    `fprintf(stdout, ...)` -- progress, a banner, a CSV row -- came out on
    the error stream and could not be piped. The C++ names the stream for a
    reason.
    """
    print((_py_format(fmt) % args) if args else fmt, end="",
          file=stream if hasattr(stream, "write") else _sys.stderr)


def snprintf(buf, size, fmt, *args) -> str:
    """``snprintf``. Writes *through* a mutable buffer, and returns the text.

    Same bargain as :func:`strncpy`, and for the same idiom::

        char label[32];
        std::snprintf(label, sizeof(label), "Ch%d", ch);
        std::string row = label;

    The third line is what the buffer is *for*, so filling it is the whole
    point -- returning the text alone left `label` a row of nulls and the
    failure landed on the line that read it.
    """
    text = (_py_format(fmt) % args) if args else fmt
    if size is not None:
        text = text[:max(0, int(size) - 1)]        # room for the NUL
    if isinstance(buf, (list, bytearray)):
        for i, ch in enumerate(text[:len(buf)]):
            buf[i] = ch
        if len(text) < len(buf):
            buf[len(text)] = None if isinstance(buf, list) else 0
    return text


# `<cstdio>` and `<cstring>` put these in namespace `std` as well as at
# global scope, and C++ code uses both spellings freely -- `std::snprintf` in
# one file and a bare `snprintf` in the next. They are the same function, so
# the qualified spelling resolves to the same object rather than a second
# copy that could drift.
for _c_name in ("printf", "fprintf", "snprintf", "memset", "memcpy",
                "strncpy", "strcmp", "popen", "pclose", "fgets"):
    setattr(_Std, _c_name, staticmethod(globals()[_c_name]))
