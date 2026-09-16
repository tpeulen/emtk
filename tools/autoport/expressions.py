"""Expression-level translation: the Porter and its call/enum/member rules."""
from __future__ import annotations

import re

from autoport.lex import (split_args, _is_string, _unquote, _fix_printf,
                          upper_snake, _skip_string)
from autoport.tables import (ENUM_FAMILIES, MATH_FUNCS, CONSTANTS,
                             OUT_PARAM_INDEX, FMT_FUNCS, FMT_ARG_INDEX,
                             COLOUR_ARG_INDEX, IO_FIELDS)
from emtk.im_compat import mechanical_name  # the one naming rule, shared

# --------------------------------------------------------------------------- #
# Expression translation
# --------------------------------------------------------------------------- #

def _as_rgba(colour: str) -> str:
    """A Dear ImGui colour, in the units emtk paints in.

    ImGui spells a colour as four floats 0..1; emtk's painters take bytes
    0..255. Handing the floats over does not raise -- it draws (0, 0, 0),
    so the text is simply invisible, which is the worst kind of difference.

    A literal is converted here, so the ported line reads as numbers a human
    would have written. Anything else is wrapped in ``im.floats_to_rgba``,
    which is a no-op the port cannot do at rest: whether ``kAccent`` holds
    floats or bytes is not knowable from this call site.
    """
    inner = colour.strip()
    if not (inner.startswith("(") and inner.endswith(")")):
        return f"im.floats_to_rgba({inner})"
    parts = [p.strip() for p in split_args(inner[1:-1])]
    try:
        vals = [float(p) for p in parts]
    except ValueError:
        return f"im.floats_to_rgba({inner})"
    if not vals or any(v < 0.0 or v > 1.0 for v in vals):
        return colour          # already bytes, or not a colour at all
    out = [int(min(max(v, 0.0), 1.0) * 255.0 + 0.5) for v in vals]
    while len(out) < 3:
        out.append(0)
    if len(out) < 4:
        out.append(255)
    return "(" + ", ".join(str(v) for v in out) + ")"


_FORMAT_SPEC = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?(?:hh|h|ll|l|z|j|t|L)?[a-zA-Z%]")


def _mask_format_specs(e: str):
    """Hide ``%.1f``-style printf specs behind ``\x03<n>\x03`` markers."""
    specs: list = []

    def take(m):
        specs.append(m.group(0))
        return f"\x03{len(specs) - 1}\x03"

    return _FORMAT_SPEC.sub(take, e), specs


def _unmask_format_specs(e: str, specs: list) -> str:
    for i, spec in enumerate(specs):
        e = e.replace(f"\x03{i}\x03", spec)
    return e


def _group_is_brace_derived(inner: str) -> bool:
    """Does *inner* hold a top-level ``(...)`` that is not a call?

    ``_brace_call`` works innermost-first, so by the time an outer group is
    converted its children are already parenthesised -- and a child that no
    identifier precedes came from a brace, not from a call.
    """
    depth = 0
    for i, c in enumerate(inner):
        if c == "(":
            if depth == 0:
                before = inner[:i].rstrip()
                if not before or not (before[-1].isalnum() or before[-1] in "_."):
                    return True
            depth += 1
        elif c == ")":
            depth -= 1
    return False


def _as_lists(inner: str) -> str:
    """Turn the brace-derived ``(...)`` groups in *inner* into ``[...]``."""
    out, kinds = [], []
    for i, c in enumerate(inner):
        if c == "(":
            before = inner[:i].rstrip()
            call = bool(before) and (before[-1].isalnum() or before[-1] in "_.")
            kinds.append(call)
            out.append("(" if call else "[")
        elif c == ")" and kinds:
            out.append(")" if kinds.pop() else "]")
        else:
            out.append(c)
    return "".join(out)


def _bare_brace(m: "re.Match") -> str:
    """``{a, b}`` -> ``(a, b)``, and ``{x}`` -> ``(x,)``.

    The trailing comma is the whole point of not writing this inline:
    ``config.donor_channels = {0}`` is a one-element *list* in C++, and
    ``(0)`` is the integer nought. The failure lands wherever the value is
    finally used -- a SWIG typemap rejecting an int where it wanted a vector
    -- with nothing pointing back at the brace it came from.
    """
    inner = m.group(1).strip()
    # A *nested* initialiser is a container of containers and never an
    # ImVec: `decay_lifetimes = {{3.8, 1, 0}, {2.0, 1, 0}}` is rows of
    # numbers, and read as tuples the C++ line that assigns into
    # `decay_lifetimes[i][0]` on the next screen raises. Flat groups stay
    # tuples, which is what an ImVec2 wants and what emtk takes.
    if _group_is_brace_derived(inner):
        return "[" + _as_lists(m.group(1)) + "]"
    if inner and "," not in inner:
        return "(" + inner + ",)"
    return "(" + m.group(1) + ")"


#: Widths a ``static_cast`` names when it means "truncate to an integer".
_INT_CASTS = re.compile(
    r"^(?:size_t|ssize_t|ptrdiff_t|time_t|u?int(?:8|16|32|64)_t|intptr_t"
    r"|uintptr_t|ImU8|ImS8|ImU16|ImS16|ImU32|ImS32|ImU64|ImS64|int|long"
    r"|short|unsigned.*|signed.*|char)$")

#: A type a C cast can name, for telling `(float)*val` -- a cast of a
#: dereference -- apart from `(a) * b`, a multiplication. Only spellings from
#: the language and from imgui: an application's own type in front of a `*`
#: is far more likely to be a variable being multiplied.
_CAST_TYPE = (r"(?:const\s+)?(?:unsigned\s+|signed\s+)?"
              r"(?:float|double|bool|char|int|short|long(?:\s+long)?"
              r"|unsigned|signed|size_t|ssize_t|ptrdiff_t|time_t"
              r"|u?int(?:8|16|32|64)_t|intptr_t|uintptr_t"
              r"|Im[US](?:8|16|32|64)|ImWchar|ImTextureID|ImGuiID)")

#: A cast standing directly in front of a dereference or an address-of.
_CAST_OF_SIGIL_RE = re.compile(
    r"(\(\s*" + _CAST_TYPE + r"\s*\**\s*\))\s*[*&]\s*(?=[A-Za-z_(])")


def rewrite_static_cast(e: str) -> str:
    """``static_cast<T>(x)`` -> ``int(x)``, ``float(x)`` or ``x``.

    Dropping it outright loses the conversion, and the conversion is the
    whole point of writing one: ``static_cast<uint64_t>(ms * 1e6 / res)``
    truncates, and the float that came through instead was rejected by a
    SWIG setter several frames away from the cast that should have made it
    an integer.
    """
    for kind in ("static_cast", "reinterpret_cast", "const_cast", "dynamic_cast"):
        at = e.find(kind + "<")
        while at != -1:
            i = at + len(kind)
            depth = 0
            while i < len(e):
                if e[i] == "<":
                    depth += 1
                elif e[i] == ">":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            if depth != 0:
                break
            arg = e[at + len(kind) + 1:i].strip().split("::")[-1].strip("* &")
            if kind == "static_cast" and _INT_CASTS.match(arg):
                fn = "int"
            elif kind == "static_cast" and arg in ("float", "double"):
                fn = "float"
            elif kind == "static_cast" and arg == "bool":
                fn = "bool"
            else:
                fn = ""                      # a pointer cast: no value change
            e = e[:at] + fn + e[i + 1:]
            at = e.find(kind + "<", at + len(fn))
    return e


def drop_get_template(e: str) -> str:
    """``j.get<T>()`` -> ``j``. *T* may be nested to any depth.

    On an ``nlohmann::json`` this is the value itself, so there is nothing
    left to call. The nesting is why this is a scan and not a pattern:
    ``get<std::vector<std::vector<double>>>()`` is three deep, and each
    regex written to cover one more level left the next one standing --
    silently, as a ``.get()`` that reads like ``unique_ptr::get`` and fails
    on whatever the value turned out to be.
    """
    out = e
    at = out.find(".get<")
    while at != -1:
        i = at + len(".get")
        depth = 0
        while i < len(out):
            if out[i] == "<":
                depth += 1
            elif out[i] == ">":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        tail = out[i + 1:]
        stripped = tail.lstrip()
        if depth == 0 and stripped.startswith("()"):
            keep = len(tail) - len(stripped)
            out = out[:at] + tail[keep + 2:]
        else:
            at = out.find(".get<", at + 1)
            continue
        at = out.find(".get<", at)
    return out


def _receiver_start(e: str, dot: int) -> int:
    """Where the expression whose member is at *dot* begins.

    Walks left over a balanced ``(...)``/``[...]`` and the identifier chain
    in front of it, so the receiver of
    ``config.value("k", std::string()).empty()`` is the whole call and not
    the four characters before the dot.
    """
    i = dot
    while i > 0:
        c = e[i - 1]
        if c in ")]":
            depth, i = 0, i
            while i > 0:
                ch = e[i - 1]
                if ch in ")]":
                    depth += 1
                elif ch in "([":
                    depth -= 1
                    if depth == 0:
                        i -= 1
                        break
                i -= 1
            continue
        if c.isalnum() or c in "_.":
            i -= 1
            continue
        break
    return i


def _carry_duration_unit(text: str) -> str:
    """``duration_cast<milliseconds>(d)`` -> ``duration_cast(d, "milliseconds")``.

    The *unit* of a chrono duration is its template argument, so the generic
    "template arguments evaporate" rule below left `.count()` counting
    nothing in particular -- a timeout compared in milliseconds against a
    value that was now seconds, silently off by a thousand.
    """
    def take(m):
        return f"{m.group(1)}({m.group(3) if False else ''}"
    out = []
    i = 0
    while True:
        m = re.search(r"\b(duration_cast|duration)\s*<([^<>]*)>\s*\(", text[i:])
        if not m:
            out.append(text[i:])
            break
        start = i + m.start()
        open_at = i + m.end() - 1
        close = _matching(text, open_at)
        if close == -1:
            out.append(text[i:i + m.end()])
            i += m.end()
            continue
        unit = m.group(2).split("::")[-1].strip() or "seconds"
        inner = text[open_at + 1:close]
        out.append(text[i:start])
        out.append(f'{m.group(1)}({inner}, "{unit}")')
        i = close + 1
    return "".join(out)


def _substr(e: str) -> str:
    """``s.substr(pos, count)`` -> ``s[pos:pos + count]``; ``s.substr(pos)``
    -> ``s[pos:]``.

    C++ takes a *count*, Python a stop index, which is the whole reason this
    cannot be a rename. cpp_compat's `String` carries a `substr`, but by the
    time a ported line runs its receiver is usually a plain `str` -- a value
    read back over SWIG, a literal, a member defaulted to `""` -- so the
    rewrite has to happen at the call site to reach all of them.
    """
    at = e.find(".substr(")
    while at != -1:
        start = _receiver_start(e, at)
        open_paren = at + len(".substr")
        close = _matching(e, open_paren)
        if close == -1 or not e[start:at]:
            at = e.find(".substr(", at + 1)
            continue
        args = [a.strip() for a in split_args(e[open_paren + 1:close]) if a.strip()]
        recv = e[start:at]
        if len(args) >= 2:
            rep = f"{recv}[{args[0]}:{args[0]} + {args[1]}]"
        elif len(args) == 1:
            rep = f"{recv}[{args[0]}:]"
        else:
            rep = recv
        e = e[:start] + rep + e[close + 1:]
        at = e.find(".substr(", start + len(rep))
    return e


def _matching(e: str, open_at: int) -> int:
    depth = 0
    for i in range(open_at, len(e)):
        if e[i] == "(":
            depth += 1
        elif e[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _size_and_empty(e: str) -> str:
    """``x.empty()`` -> ``not x``; ``x.size()``/``x.length()`` -> ``len(x)``.

    These are Python operators, not methods, and by the time a ported line
    runs its receiver is usually a plain ``str``/``list``/``dict``: a member
    defaulted to ``""``, a value read back over SWIG, a JSON document.
    Rewriting at the call site means it does not matter which -- cpp_compat's
    Vector answers to both spellings, but ``str`` does not, and
    ``config.get_output_path().empty()`` is a ``str``.
    """
    e = _substr(e)
    rules = [("empty", "not {}"), ("size", "len({})"), ("length", "len({})"),
             # `std::exception::what()`, and nothing else is ever called
             # `what`, so rewriting it globally is safe. It matters most
             # because it appears *inside error handlers*: a ported
             # `catch (const std::exception &e) { log(e.what()); }` reached a
             # Python exception, which has no such method, so the real error
             # was replaced by an AttributeError about reporting it.
             ("what", "str({})")]
    # ``nlohmann::json``'s type predicates. A parsed document on this side is
    # made of ordinary dicts, lists and scalars, so there is nothing for the
    # method to hang off -- but the *question* still has an answer, and
    # cpp_compat has the one-liner that gives it. Left alone these were an
    # AttributeError on the first settings document read back from disk.
    rules += [(f"is_{k}", "json_is_" + k + "({})") for k in
              ("object", "array", "string", "boolean", "null",
               "number", "number_integer", "number_float")]
    for name, wrap in rules:
        needle = "." + name + "()"
        at = e.find(needle)
        while at != -1:
            start = _receiver_start(e, at)
            recv = e[start:at]
            if not recv:
                at = e.find(needle, at + 1)
                continue
            rep = wrap.format(recv)
            e = e[:start] + rep + e[at + len(needle):]
            at = e.find(needle, start + len(rep))
    return e


def _paren_if_compound(operand: str) -> str:
    """Wrap *operand* unless it is a single term.

    ``%`` binds no tighter than ``*``, ``/`` or ``+``, so ``"%d" % a / b``
    formats ``a`` and then divides -- the parentheses are the fix, and on a
    bare name they are only noise.
    """
    depth = 0
    k = 0
    while k < len(operand):
        c = operand[k]
        if c in "\"'":
            k = _skip_string(operand, k)
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0 and c in "+-*/%<>|&^~ ":
            return f"({operand})"
        k += 1
    return operand


class Porter:
    """One translation pass over one file.

    Carries what the tables cannot: which locals are ``ImVec2`` (so ``.x`` is
    ``[0]``), which class is being ported (so a bare field becomes ``self.x``),
    which prelude helpers got used, and every TODO raised.
    """

    def __init__(self):
        self.module_enums: dict[str, str] = {}   # ImGuiToggleFlags -> ToggleFlags
        self.vec_vars: set[str] = set()
        #: ``char buf[32]`` locals of the function being ported. They come
        #: out as a fixed-length list of slots, of which `snprintf` fills
        #: only the front -- so where the C++ *concatenates* one onto a
        #: string it has to be converted first, or the padding rides along.
        self.char_arrays: set[str] = set()
        self.helpers: set[str] = set()
        self.todos: list[str] = []
        self.fields: set[str] = set()
        #: plain aggregates this file also ports, so a local of one
        #: can be constructed rather than left None
        self.structs: set[str] = set()
        #: The names of the class's *other* methods. A method calling one of
        #: them writes the bare name in C++ and must write ``self.`` here --
        #: without this the call resolves to a module global that is not
        #: there, and the panel dies the first time it is drawn.
        self.methods: set[str] = set()
        #: functions ported with a ``T* p_value`` param: their Python form
        #: returns ``(original_return, value)``. Call sites unpack.
        self.out_funcs: set[str] = set()
        #: this function's out value: the C++ param name it was spelled with
        self.out_src_name: str | None = None
        #: further write-through params beyond the one the tuple carries
        self.out_extras: list[str] = []
        #: *every* write-through param, in declaration order, under the name
        #: the Python function uses. One of them is renamed to `value`;
        #: several keep their own, because there is no one name to rename to.
        self.out_names: list[str] = []
        #: the C++ name of the function being ported (self-call detection)
        self.func_name: str | None = None
        #: a struct type this function returns, when one does
        self.ret_cls: str | None = None
        #: function-like macro names collected from the source: their
        #: invocations are flagged, never expanded (expansion is the hand's)
        self.macros: set[str] = set()

    def todo(self, what: str) -> str:
        note = what.replace("\n", " ")
        if note not in self.todos:
            self.todos.append(note)
        return f"  # TODO(autoport): {note}"

    # -- expression -------------------------------------------------------- #

    def expr(self, e: str) -> str:
        # `(float)*val` -- a cast of a dereference. The cast's own `)` is a
        # left operand as far as `_deref` can see, so the `*` read as a
        # multiplication and the whole thing was left standing: *valid
        # Python*, which multiplies the type object `float` by a value and
        # raises `TypeError: unsupported operand type(s) for *: 'type' and
        # 'float'` at draw time, not at import. Dropping the sigil here is
        # what leaves the cast rules below an operand they can bind to; it
        # has to happen before `_deref`, which would otherwise never see it.
        e = _CAST_OF_SIGIL_RE.sub(r"\1", e)
        e = self._deref(e)
        # receivers first: Obj->Method and NS::Func become dots, so the call
        # scan sees ``obj.method(...)`` and leaves the method name alone
        e = re.sub(r"\bthis\s*->\s*", "self.", e)
        e = rewrite_static_cast(e)
        # a cast on a qualified call is a no-op: ``(float)ImGui::GetTime()`` --
        # the token rules below would tear the receiver apart
        e = re.sub(r"\(\s*[A-Za-z_]\w*(?:::[A-Za-z_]\w*)?\s*\)\s*(?=[A-Za-z_]\w*\s*::)", "", e)
        # C casts: bind to the next single token (or parenthesised group) only
        e = re.sub(r"\(\s*(?:const\s+)?[\w:]+\s*\*+\s*\)\s*", "", e)
        e = re.sub(r"\(\s*(?:size_t|ImU8|ImS8|ImU16|ImS16|ImU64|ImS64|intptr_t"
                   r"|uintptr_t|unsigned(?:\s+\w+)?|signed|long(?:\s+long)?|short)\s*\)"
                   r"\s*\(", "int(", e)
        # A cast binds to the whole postfix expression, member chain and
        # trailing call included. Stopping at the first name turned
        # `(float)config_->get_image_controls_width()` into
        # `float(self.config_).get_image_controls_width()` -- the cast landed
        # on the *object* and the call was left dangling off the result.
        # A cast binds to the whole *postfix* expression -- trailing calls
        # and subscripts included, in any order and any number. Stopping at
        # the name gave `float(config.q_scatter)[0]` for
        # `(float)config.q_scatter[0]`: a cast of the container, subscripted
        # afterwards, which raises on the cast rather than anywhere near the
        # mistake.
        _POSTFIX = r"((?:[\w.]|->)+(?:\([^()]*\)|\[[^\[\]]*\])*)"
        e = re.sub(r"\(\s*(?:size_t|ImU64|ImS64|intptr_t|uintptr_t"
                   r"|unsigned(?:\s+\w+)*|signed|long(?:\s+long)?|short)\s*\)\s*"
                   + _POSTFIX, r"int(\1)", e)
        e = re.sub(r"\(\s*(?:float|double)\s*\)\s*" + _POSTFIX, r"float(\1)", e)
        e = re.sub(r"\(\s*(?:int|ImU32|ImS32)\s*\)\s*" + _POSTFIX, r"int(\1)", e)
        e = re.sub(r"\(\s*bool\s*\)\s*" + _POSTFIX, r"bool(\1)", e)
        e = re.sub(r"\(\s*(?:float|double)\s*\)\s*\(", "float(", e)
        e = re.sub(r"\(\s*(?:int|ImU32|ImS32)\s*\)\s*\(", "int(", e)
        e = re.sub(r"\(\s*bool\s*\)\s*\(", "bool(", e)
        # a cast on a qualified call is a no-op: ``(float)ImGui::GetTime()``
        e = re.sub(r"\(\s*[A-Za-z_]\w*(?:::[A-Za-z_]\w*)?\s*\)\s*(?=[A-Za-z_]\w*)", "", e)
        # A width-named cast onto a *literal* or a parenthesised group. The
        # rules above bind a cast to an identifier only, and the ones that do
        # not start with a letter are the ones that matter most:
        # ``(uint64_t)-1`` is the "nothing rendered yet" sentinel, and left
        # alone it is *valid Python* -- a name in parentheses, minus one --
        # so it compiled and then NameErrored at import, which is the one
        # kind of mistake the syntax check cannot catch.
        _WIDTH = (r"(?:size_t|ssize_t|ptrdiff_t|time_t|u?int(?:8|16|32|64)_t"
                  r"|intptr_t|uintptr_t|ImU8|ImS8|ImU16|ImS16|ImU32|ImS32"
                  r"|ImU64|ImS64|unsigned(?:\s+\w+)*|signed(?:\s+\w+)*"
                  r"|long(?:\s+long)?|short|char)")
        e = re.sub(r"\(\s*" + _WIDTH + r"\s*\)\s*(?=[-+]?\d|\()", "", e)
        e = re.sub(r"\(\s*" + _WIDTH + r"\s*\)\s*(?=[A-Za-z_])", "", e)
        # address-of at an argument/initialiser position: the value is the arg
        # `^` as well as a separator: an assignment ports its right-hand
        # side on its own, so `= &(x)` arrives as `&(x)` with nothing in
        # front of the `&` for a separator to match.
        e = re.sub(r"(^|[\(,=<\[])\s*&\s*([A-Za-z_(])", r"\1 \2", e)
        # ``j.get<int>()`` on an nlohmann::json *is* the value -- there is
        # nothing to call on this side. Dropped before the generic template
        # rule below, which would otherwise leave `.get()`: a no-argument
        # call that reads as unique_ptr::get and fails on whatever the value
        # turned out to be.
        e = drop_get_template(e)
        # ``make_unique<T>()`` first: for these the template argument is not
        # a type annotation to be dropped, it is *what to construct*, and the
        # generic rule below left ``std::make_unique()`` -- a call with no
        # idea what to make. cpp_compat's stand-in takes the class first.
        # `duration_cast<milliseconds>(d)`: the unit IS the template
        # argument, so the generic strip below left `.count()` with no
        # idea what it counts. Carried across as a second argument.
        e = _carry_duration_unit(e)
        e = re.sub(r"\bmake_(unique|shared)\s*<([\w:]+)[^<>]*>\s*\(\s*\)",
                   r"make_\1(\2)", e)
        e = re.sub(r"\bmake_(unique|shared)\s*<([\w:]+)[^<>]*>\s*\(",
                   r"make_\1(\2, ", e)
        # explicit template arguments evaporate: the port is generic
        # a template argument may be a *value*, not only a type:
        # ``std::array<uint64_t, 4>``. Left in place the ``<`` and ``>`` read
        # as comparisons and the declaration never parses.
        e = re.sub(r"\b([A-Za-z_]\w*)<(?:[A-Za-z_][\w:.]*|\d+)"
                   r"(?:\s*,\s*(?:[A-Za-z_][\w:.]*|\d+))*>", r"\1", e)
        e = re.sub(r"\bImGui\s*::\s*", "\x01ImGui\x01", e)   # shield the table key
        e = re.sub(r"(?<![\w])::(?=[A-Za-z_])", "", e)        # global scope ::X
        e = e.replace("::", ".")
        e = e.replace("\x01ImGui\x01", "ImGui::")
        e = e.replace("->", ".")
        e = self._lambdas(e)
        e = self._calls(e)
        e = self._enums(e)
        e = self._members(e)
        e = self._brace_call(e)
        e = self._operators(e)
        e = self._vec_operators(e)
        e = self._vec_literal_add(e)
        e = self._ternaries(e)
        # ImGui::Dummy takes an ImVec2; emtk spells the two coordinates out
        e = re.sub(r"\bdummy\(\s*\(([^()]+),\s*([^()]+)\)\s*\)", r"dummy(\1, \2)", e)
        if self.out_src_name:
            e = re.sub(rf"\b{self.out_src_name}\b", "value", e)
        e = self.char_array_concat(e)
        return e.replace("\x00\x00", "")

    def _deref(self, e: str) -> str:
        """``*p_value`` -> ``p_value`` (the Python param is the value itself).
        The same for whatever name this function's out value was spelled
        with, and for a second out-param -- reads through it must at least
        parse; the function-level TODO flags that it needs a hand."""
        names = ([self.out_src_name] if self.out_src_name else []) \
            + self.out_extras + self.out_names
        for nm in names:
            e = re.sub(rf"(?<![\w)\]])\s*\*\s*({nm})\b", r"\1", e)
        # Any name, not only ``p_*`` and the declared out-params: application
        # code dereferences whatever it was handed (``*sample_rate_idx``,
        # ``*res_opt``). What separates a dereference from a multiplication is
        # whether anything could be a *left operand*, so the rule matches the
        # token before the star rather than looking behind it -- a lookbehind
        # is checked at the star's own position, where the preceding character
        # is the separating space, and ``a * b`` reads as a dereference.
        e = re.sub(r"(^|[(,=<>+\-*/%!&|?:\[{;]|\breturn|\band|\bor|\bnot)"
                   r"\s*\*\s*([A-Za-z_]\w*(?:\.\w+)*)", r"\1\2", e)
        return e

    def char_array_concat(self, e: str) -> str:
        """``row_str += buf`` where ``buf`` is a ``char buf[32]``.

        In C++ that appends a C string, stopping at the NUL that `snprintf`
        wrote. Here the buffer is a fixed-length list whose tail is still
        `None`, so the concatenation either raises `TypeError: can only
        concatenate str (not "list") to str` or -- worse -- succeeds as a
        list concatenation and carries the padding into a text draw.
        `std.string` cuts at the first NUL, which is exactly the conversion
        C++ performs here without writing it down.

        Only next to a `+`: the same name passed to `snprintf` or `sizeof`
        is the buffer itself, and converting it there would throw away the
        write.
        """
        for nm in self.char_arrays:
            e = re.sub(rf"(?<![\w.]){nm}\b(?=\s*\+(?!\+))",
                       f"std.string({nm})", e)
            e = re.sub(rf"(?<=[+])(\s*)(?<![\w.]){nm}\b(?![\w.(])",
                       rf"\1std.string({nm})", e)
        return e

    def _lambdas(self, e: str) -> str:
        """``[cap](p) { return x; }`` -> ``lambda p: x``.

        Only the single-expression form, which is what a callback argument
        almost always is here -- an image provider, a colour hook. A body
        with more than one statement has no Python expression form at all,
        so it is left alone and flagged: the *function* still ports, and one
        argument needs a hand, instead of the whole function being cut.
        """
        out = e
        for _ in range(8):
            m = re.search(r"\[[^\]]*\]\s*\((?P<params>[^()]*)\)\s*"
                          r"(?:mutable\s*)?(?:noexcept\s*)?(?:->\s*[^{]*?)?"
                          r"\{(?P<body>[^{}]*)\}", out)
            if not m:
                break
            body = m.group("body").strip().rstrip(";").strip()
            names = [p.strip().split()[-1].lstrip("*&")
                     for p in split_args(m.group("params")) if p.strip()]
            if body.startswith("return "):
                body = body[len("return "):].strip()
            elif ";" in body or not body:
                # several statements, or none: not an expression
                self.todo(f"lambda body is not a single expression: "
                          f"{' '.join(body.split())[:50]}")
                out = (out[:m.start()] + f"lambda {', '.join(names)}: None"
                       + self.todo("").strip() + out[m.end():])
                continue
            out = (out[:m.start()] + f"lambda {', '.join(names)}: {body}"
                   + out[m.end():])
        return out

    def _brace_call(self, e: str) -> str:
        """``TypeName{a, b}`` -> ``TypeName(a, b)``; a bare ``{a, b}`` -> ``(a, b)``."""
        prev = None
        while prev != e:
            prev = e
            e = re.sub(r"([A-Za-z_]\w*)\{([^{}]*)\}", r"\1(\2)", e)
        # To a fixed point here too. Run once, this converted only the
        # *innermost* braces of a nested initialiser and left the outer pair
        # standing -- so ``{{4,4,4},{4,4,4},{4,4,4}}`` came out as a Python
        # set literal of three equal tuples, which is a set of ONE. A table
        # of per-species constants silently became a single row.
        prev = None
        while prev != e:
            prev = e
            e = re.sub(r"\{([^{}]*)\}", _bare_brace, e)
        return e

    def _ternaries(self, e: str) -> str:
        """``c ? a : b`` -> ``(a if c else b)``; innermost parentheses are
        converted first, so a ``?`` hiding in a sub-expression
        (``x + (c ? a : b)``, a nested arm) is still found. Strings and
        char literals are opaque; ``[]`` brackets nest like parens so a
        slice ``:`` is never read as a ternary colon."""
        e = e.strip()
        # bottom-up through the parentheses: by the time a group closes,
        # everything inside it is already ternary-free
        res: list[str] = []      # output pieces; groups splice in place
        stack: list[int] = []    # res length at each unmatched "("
        k = 0
        while k < len(e):
            ch = e[k]
            if ch in "\"'":
                end = _skip_string(e, k)
                res.append(e[k:end])
                k = end
                continue
            if ch == "(":
                stack.append(len(res))
                res.append("(")
                k += 1
                continue
            if ch == ")" and stack:
                start = stack.pop()
                inner = "".join(res[start + 1:])
                res[start] = "(" + self._ternary_flat(inner) + ")"
                del res[start + 1:]
                k += 1
                continue
            res.append(ch)
            k += 1
        return self._ternary_flat("".join(res))

    def _ternary_flat(self, t: str) -> str:
        """The top-level ``?`` of *t* only: groups are already converted."""
        def scan(x, want):
            """Position of the first top-level *want* (? or :)."""
            depth = 0
            k = 0
            while k < len(x):
                ch = x[k]
                if ch in "\"'":
                    k = _skip_string(x, k)
                    continue
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    depth -= 1
                elif ch == want and depth == 0:
                    return k
                k += 1
            return None
        q = scan(t, "?")
        if q is None:
            return t
        colon = scan(t[q + 1:], ":")
        if colon is None:
            return t
        colon += q + 1
        cond = self._ternary_flat(t[:q].strip())
        a = self._ternaries(t[q + 1:colon].strip())
        b = self._ternaries(t[colon + 1:].strip())
        return f"({a} if {cond} else {b})"

    def _calls(self, e: str) -> str:
        """Rewrite calls outermost-last: recurse into each argument first.

        A balanced-paren scan (not ``[^()]*``), so a call whose arguments
        contain rewritten nested calls is still seen as one call.
        """
        out: list = []
        i = 0
        n = len(e)
        while i < n:
            m = CALL_HEAD_RE.search(e, i)
            if not m:
                out.append(e[i:])
                break
            if m.group(1).split(".")[-1] in KEYWORDS:
                out.append(e[i:m.end()])
                i = m.end()
                continue
            out.append(e[i:m.start()])
            name = m.group(1)
            j = m.end()              # just past the open paren
            depth = 1
            while j < n and depth:
                c = e[j]
                if c == "(":
                    depth += 1
                elif c == ")":
                    depth -= 1
                j += 1
            args_src = e[m.end():j - 1]
            args = [self.expr(a) for a in split_args(args_src)] if args_src.strip() else []
            new = self._rewrite_call(name, args)
            out.append("\x00\x00" if new is None else new)
            i = j
        return "".join(out)

    def _rewrite_call(self, name: str, args: list):
        base = name.rsplit("::", 1)[-1].rsplit(".", 1)[-1]

        # a call on a receiver (draw_list.PathArcTo, im.button, math.sin):
        # arguments translate, the method name is the member pass's job.
        if "." in name:
            return f"{name}({', '.join(args)})"

        # a float colour must become bytes before anything else looks at the
        # argument list, so the folded call carries the converted one
        ci = COLOUR_ARG_INDEX.get(base)
        if ci is not None and len(args) > ci:
            args = list(args)
            args[ci] = _as_rgba(args[ci])

        fi = FMT_ARG_INDEX.get(base, 0)
        if base in FMT_FUNCS and len(args) > fi and _is_string(args[fi]):
            head = args[:fi]
            fmt = _fix_printf(_unquote(args[fi]))
            rest = args[fi + 1:]
            if len(rest) == 1:
                # ``"%d" % a / b`` parses as ``("%d" % a) / b``: % and /
                # share a precedence level, so an operand that is not a single
                # term needs its own parentheses or the format applies to the
                # wrong value. A bare name or call is left bare, which is what
                # the line would have been written as by hand.
                one = _paren_if_compound(rest[0])
                body = f'"{fmt}" % {one}'
            elif rest:
                body = f'"{fmt}" % ({", ".join(rest)})'
            else:
                body = f'"{fmt}"'
            return f'im.{mechanical_name(base)}({", ".join(head + [body])})'

        if base == "snprintf" and len(args) >= 3:
            fmt = _fix_printf(_unquote(args[2]))
            rest = args[3:]
            rhs = f'"{fmt}" % ({", ".join(rest)})' if rest else f'"{fmt}"'
            return f"({args[0]} := {rhs})"

        if base == "TextUnformatted" and args:
            return f"im.text({args[0]})"

        # the *Scalar family carries ImGuiDataType between label and value:
        # emtk's scalar widgets dispatch on the Python type, so the type arg
        # is dropped and the value is position 2
        if base in ("DragScalar", "SliderScalar", "InputScalar") and len(args) > 2 \
                and re.fullmatch(r"\w+", args[2].strip()):
            val = args[2].strip()
            fn = {"DragScalar": "drag_scalar", "SliderScalar": "slider_scalar",
                  "InputScalar": "input_scalar"}[base]
            tail = f", {', '.join(args[3:7])}" if len(args) > 3 else ""
            return f"_changed, {val} = im.{fn}({args[0]}, {val}{tail})"

        if base == "InputText" and len(args) > 2:
            # `InputText(label, buf, buf_size, flags, ...)`. A Python string
            # has no fixed buffer, so emtk's third positional is the *hint*
            # -- and the size landed there and was drawn as placeholder text.
            del args[2]
            if len(args) > 2:
                args[2] = "flags=" + args[2]
            del args[3:]                      # callback / user_data: no shape here
        if base == "InputTextMultiline" and len(args) > 2:
            del args[2]                       # the same buf_size, one later
            del args[3:]

        if base in OUT_PARAM_INDEX:
            vi = OUT_PARAM_INDEX[base]
            # Any *lvalue*, not just a bare name. Arguments are ported
            # recursively before this runs, so a widget writing through a
            # member arrives already qualified -- `&photon_hub_block_size_idx_`
            # is `self.photon_hub_block_size_idx_` by now, and `\w+` rejected
            # it. The call then kept its tuple return, so
            # `if (ImGui::Combo("##x", &member_, ...))` became
            # `if im.combo(...)` -- and a non-empty tuple is ALWAYS TRUE. Every
            # such widget reported itself changed on every frame: cmc rewrote
            # its settings file thirty times a second.
            if vi < len(args) and re.fullmatch(
                    r"[A-Za-z_]\w*(?:\.\w+|\[[^\[\]]*\])*", args[vi].strip()):
                var = args[vi].strip()
                args[vi] = var
                lhs = self._out_lhs(base, vi, args)
                return f"{lhs} = im.{mechanical_name(base)}({', '.join(args)})"

        if base == "Begin" and len(args) > 1:
            # `Begin(name, p_open, flags)`. emtk's second positional is the
            # window's *box*, so the p_open cannot simply be dropped and the
            # rest shuffled up -- the flags would land in `box` and place the
            # window at a bitmask. Drop the p_open however it is spelled and
            # hand the flags over by name.
            # Always: the reference's second argument to `Begin` is
            # `bool *p_open` and nothing else, so there is no case where it
            # means a box. (The `&` is long gone by here -- an earlier rule
            # strips address-of at argument position -- which is why testing
            # the spelling missed `Begin(name, &open, flags)` entirely.)
            opened = args[1].strip()
            if opened not in ("nullptr", "NULL", "None", "0"):
                self.todos.append(
                    "Begin p_open: emtk windows have no p_open; drop it "
                    "or read the close flag the host keeps")
            del args[1]
            if len(args) > 1:
                args[1] = "flags=" + args[1]

        if base in MATH_FUNCS:
            # a forwarding wrapper (ImLog(int) -> ImLog(float)) lands here for
            # its inner call: the table *is* the overload it forwards to
            fn = MATH_FUNCS[base]
            if fn.startswith("im_"):
                self.helpers.add(fn)
            return f"{fn}({', '.join(args)})"

        # imgui_internal behaviour cores: the facade spells them drag_scalar /
        # slider_scalar, and the value is returned, not written through
        if name.startswith("ImGui::") and base in ("DragBehavior", "SliderBehavior"):
            val = args[2].strip()
            fn = "drag_scalar" if base == "DragBehavior" else "slider_scalar"
            tail = f", {', '.join(args[3:7])}" if len(args) > 3 else ""
            return f"_changed, {val} = im.{fn}({args[0]}, {val}{tail})"

        if name in ("ImGui::BeginChild", "BeginChild"):
            # emtk's child is a box, not id+size+flags: anchor it at the
            # cursor and drop the id/border/flags the port cannot express
            size = args[1].strip() if len(args) > 1 else "(0, 0)"
            self.todos.append("BeginChild: emtk takes a box anchored at the "
                              "cursor; the id/border/flags are dropped")
            return (f"im.begin_child((*im.get_cursor_screen_pos(), "
                    f"{size}[0], {size}[1]))")
        if name in ("ImGui::EndChild", "EndChild"):
            return "im.end_child()"

        if name.startswith("ImGui::"):
            return f"im.{mechanical_name(name[7:])}({', '.join(args)})"

        # a call to a function this port gave an out-value: drop the ``&`` and
        # mark the call site for tuple unpacking
        if re.fullmatch(r"[a-z_]\w*", name) and name in self.out_funcs:
            args = [a[1:].strip() if a.startswith("&") else a for a in args]
            return f"{name}({', '.join(args)})"

        if name == "ImVec2":
            xy = (args + ["0.0", "0.0"])[:2]
            return f"({xy[0]}, {xy[1]})"
        if name == "ImVec4":
            xyzw = (args + ["0.0"] * 4)[:4]
            return f"({', '.join(xyzw)})"
        if name == "ImColor":
            if len(args) == 1:
                # ImColor(existing) is the identity: emtk colours are tuples
                return args[0]
            rgba = (args + ["255", "255", "255", "255"])[:4]
            return f"({', '.join(rgba)})"
        if name in ("IM_ASSERT", "IM_ASSERT_USER_ERROR"):
            call_args = args[:2] if name == "IM_ASSERT_USER_ERROR" else args[:1]
            return f"assert({', '.join(call_args)})"
        if name == "ImRect":
            # ImGuizmo's rectangle helper: the prelude ships a minimal one
            self.helpers.add("ImRect")
            return f"ImRect({', '.join(args)})"
        if name == "IM_COL32":
            return f"im.col32({', '.join(args)})"
        if name == "IM_ARRAYSIZE":
            return f"len({args[0]})"
        if name == "IM_COL32_WHITE":
            return "im.col32(255, 255, 255, 255)"
        if name in CONSTANTS:
            return CONSTANTS[name]
        if name in ("float", "int", "bool", "double", "ImU32", "ImS32", "ImU64"):
            return f"{ {'ImU32': 'int', 'ImS32': 'int', 'ImU64': 'int'}.get(name, name) }({', '.join(args)})"
        if name in ("ImGui::BeginChild", "BeginChild"):
            # emtk's child is a box, not id+size+flags: anchor it at the
            # cursor and drop the id/border/flags the port cannot express
            size = args[1].strip() if len(args) > 1 else "(0, 0)"
            self.todos.append("BeginChild: emtk takes a box anchored at the "
                              "cursor; the id/border/flags are dropped")
            return (f"im.begin_child((*im.get_cursor_screen_pos(), "
                    f"{size}[0], {size}[1]))")
        if name in ("ImGui::EndChild", "EndChild"):
            return "im.end_child()"
        if name.startswith("ImGui::"):
            return f"im.{mechanical_name(name[7:])}({', '.join(args)})"
        if re.fullmatch(r"[a-z]\w*", name):
            return f"{name}({', '.join(args)})"
        if re.fullmatch(r"[A-Za-z_]\w*", name):
            # any remaining free call: its mechanical spelling (an underscore
            # does not opt out: _GetStyleColor still becomes _get_style_color)
            return f"{mechanical_name(name)}({', '.join(args)})"
        if re.fullmatch(r"[A-Z]\w*", name) and name.startswith(("Im", "ImGui")):
            self.todos.append(f"type/constructor {name}")
            return None
        self.todos.append(f"call {name}()")
        return None

    def _out_lhs(self, base: str, vi: int, args: list[str]) -> str:
        first = args[vi]
        if base in ("DragFloatRange2", "DragIntRange2", "SplitterBehavior"):
            return f"_changed, {first}, {args[vi + 1]}"
        return f"_changed, {first}"

    def _enums(self, e: str) -> str:
        def repl(ns: str):
            return lambda m: f"{ns}.{upper_snake(m.group(1))}"
        for cpp, py in self.module_enums.items():
            e = re.sub(rf"\b{cpp}_([A-Za-z0-9]+)\b", repl(py), e)
        for cpp, py in ENUM_FAMILIES.items():
            e = re.sub(rf"\b{cpp}_([A-Za-z0-9]+)\b", repl(py), e)
        return e

    def _members(self, e: str) -> str:
        e = re.sub(r"\bthis\s*->\s*", "self.", e)
        e = re.sub(r"\bstatic_cast\s*<[^<>]*>\s*", "", e)
        e = re.sub(r"\breinterpret_cast\s*<[^<>]*>\s*", "", e)
        # C casts bind to the whole postfix expression, subscripts
        # included: `(float)q[0]` is a cast of the *element*, and
        # binding to the name alone gave `float(q)[0]` -- a cast of the
        # container, which raises on the cast instead of anywhere near
        # the mistake.
        e = re.sub(r"\(\s*(?:float|double)\s*\)\s*([\w.]+(?:\[[^\[\]]*\])*)", r"float(\1)", e)
        e = re.sub(r"\(\s*(?:int|ImU32|ImS32)\s*\)\s*([\w.]+(?:\[[^\[\]]*\])*)", r"int(\1)", e)
        e = re.sub(r"\(\s*bool\s*\)\s*([\w.]+(?:\[[^\[\]]*\])*)", r"bool(\1)", e)
        e = re.sub(r"\(\s*(?:float|double)\s*\)\s*\(", "float(", e)
        e = re.sub(r"\(\s*(?:int|ImU32|ImS32)\s*\)\s*\(", "int(", e)
        e = re.sub(r"\(\s*bool\s*\)\s*\(", "bool(", e)
        e = re.sub(r"\(\s*[A-Za-z_]\w*(?:::[A-Za-z_]\w*)?\s*\)\s*(?=[A-Za-z_]\w*)", "", e)
        e = e.replace("->", ".")
        e = re.sub(r"\bthis->\.?", "self.", e)
        e = re.sub(r"\.c_str\(\)", "", e)
        e = _size_and_empty(e)
        e = re.sub(r"\.\bx\b(?![\w])", "[0]", e)
        e = re.sub(r"\.\by\b(?![\w])", "[1]", e)
        e = re.sub(r"\.\bz\b(?![\w])", "[2]", e)
        e = re.sub(r"\.\bw\b(?![\w])", "[3]", e)
        # ``std::pair``/``std::map`` iteration: `.first`/`.second` on a
        # tuple. Skipped when the class being ported has a member of that
        # name -- a `first` of its own is a field, not half a pair.
        for word, idx in (("first", "[0]"), ("second", "[1]")):
            if word not in self.fields:
                e = re.sub(rf"\.{word}\b(?![\w(])", idx, e)
        for cpp, py in IO_FIELDS.items():
            e = re.sub(rf"\.{cpp}\b", f".{py}", e)
        # bare field or own-method of the class being ported -> self.<name>
        own = self.fields | self.methods
        if own:
            # Not after a dot: `buffers_[ch].clear()` is a call on the
            # element, and the class having a `clear` of its own turned it
            # into `self.buffers_[ch].self.clear()`. The name has to be at
            # the *start* of a term to be this object's.
            e = re.sub(rf"(?<![.\w])([A-Za-z_]\w*)\b",
                       lambda m: f"self.{m.group(1)}" if m.group(1) in own else m.group(1), e)
            e = re.sub(r"\bself\.self\.", "self.", e)
            e = e.replace("self.this.", "self.")
        # any other .CamelCase -> .snake_case (methods, style members);
        # ALL-CAPS members (enum constants) and snake names stay as they are
        def member(m):
            n = m.group(1)
            if n.isupper() or "_" in n:
                return "." + n
            return "." + mechanical_name(n)
        e = re.sub(r"(?<!im)\.([A-Za-z_]\w*)", member, e)
        return e

    @staticmethod
    def _mask_strings(e: str):
        """Split *e* into a template with ``\x02<n>\x02`` in place of each
        string literal, and the literals. The token rules below rewrite C++
        spelling -- ``1.0f``, ``true``, ``&&`` -- and every one of them is
        wrong *inside* a literal: ``"%.2f"`` is a format spec, not a float,
        and stripping its ``f`` silently changes what the program prints."""
        out, lits, k = [], [], 0
        while k < len(e):
            if e[k] in "\"'":
                j = _skip_string(e, k)
                out.append(f"\x02{len(lits)}\x02")
                lits.append(e[k:j])
                k = j
                continue
            out.append(e[k])
            k += 1
        return "".join(out), lits

    @staticmethod
    def _unmask_strings(e: str, lits: list) -> str:
        for i, lit in enumerate(lits):
            e = e.replace(f"\x02{i}\x02", lit)
        return e

    def _operators(self, e: str) -> str:
        e, _lits = self._mask_strings(e)
        e = re.sub(r"static_cast<[^>]*>\s*\(", "(", e)
        # pointer casts vanish outright (the port has no pointer types), and
        # the integer casts of every C spelling become int()
        e = re.sub(r"\(\s*(?:const\s+)?[\w:]+\s*\*+\s*\)\s*", "", e)
        e = re.sub(r"\(\s*(?:size_t|ImU8|ImS8|ImU16|ImS16|ImU64|ImS64|intptr_t"
                   r"|uintptr_t|unsigned(?:\s+\w+)?|signed|long(?:\s+long)?|short)\s*\)"
                   r"\s*\(", "int(", e)
        e = re.sub(r"\(\s*(?:size_t|ImU64|ImS64|intptr_t|uintptr_t"
                   r"|unsigned(?:\s+\w+)?|signed|long(?:\s+long)?|short)\s*\)\s*([\w.]+(?:\[[^\[\]]*\])*)",
                   r"int(\1)", e)
        e = re.sub(r"\(\s*(?:float|double)\s*\)(?=\s*[\w(])", "float(", e)
        e = re.sub(r"\(\s*int\s*\)(?=\s*[\w(])", "int(", e)
        e = re.sub(r"\(\s*bool\s*\)(?=\s*[\w(])", "bool(", e)
        e = re.sub(r"\(\s*ImU32\s*\)(?=\s*[\w(])", "int(", e)
        # address-of at an argument/initialiser position: the value is the arg
        # `^` as well as a separator: an assignment ports its right-hand
        # side on its own, so `= &(x)` arrives as `&(x)` with nothing in
        # front of the `&` for a separator to match.
        e = re.sub(r"(^|[\(,=<\[])\s*&\s*([A-Za-z_(])", r"\1 \2", e)
        # ``1.5f``, and the exponent form too: ``-1e9f`` is not a Python
        # literal at all, so leaving it is a syntax error, not a wrong value
        # printf specs first. `%.1f` and `%5.2f` are *format* specs whose
        # trailing `f` the float-suffix rule below reads as a C++ literal
        # suffix -- and stripping it turns "%.1f MB" into "%.1 MB", which is
        # not a wrong number but a ValueError at the moment the line draws.
        # Quoting cannot protect them: a format string reaches this rule as a
        # bare fragment, with its quotes already taken off.
        e, _specs = _mask_format_specs(e)
        e = re.sub(r"\b(\d+\.?\d*(?:[eE][+-]?\d+)?)[fF]\b", r"\1", e)
        e = _unmask_format_specs(e, _specs)
        # hex first: ``0xFFFFFFFFu`` is not matched by the decimal rule, and
        # Python rejects the suffix outright
        e = re.sub(r"\b(0[xX][0-9a-fA-F]+)(?:[uU]?(?:LL|ll|L|l)?)\b", r"\1", e)
        e = re.sub(r"\b(\d+)[uU]\b", r"\1", e)
        e = re.sub(r"\b(\d+)(?:ULL|LL|ul|L)\b", r"\1", e)
        e = e.replace("&&", " and ").replace("||", " or ")
        e = re.sub(r"!\s*([A-Za-z_[(])", r"not \1", e)
        e = re.sub(r"\bnot\s+not\s+", "", e)
        e = e.replace(" and and ", " and ").replace(" or or ", " or ")
        e = self._unmask_strings(e, _lits)
        e = re.sub(r'("[ \t]+)([A-Za-z_]\w*)([ \t]+")', r'" + \2 + "', e)
        e, _lits = self._mask_strings(e)
        e = re.sub(r"\bImGuiAxis_X\b", "0", e)
        e = re.sub(r"\bImGuiAxis_Y\b", "1", e)
        e = re.sub(r"\bImGuiAxis_NONE\b", "-1", e)
        e = re.sub(r"\btrue\b", "True", e)
        e = re.sub(r"\bfalse\b", "False", e)
        e = re.sub(r"\bnullptr\b", "None", e)
        e = re.sub(r"\bNULL\b", "None", e)
        return self._unmask_strings(e, _lits)

    def _vec_operators(self, e: str) -> str:
        """``a + b`` on two known ImVec2 locals -> the component tuple the
        C++ operator overloads produced; a vec scaled by a number scales
        every component; and a value plus a *literal* pair is component-wise
        too -- the C++ type system guarantees the operand was an ImVec2,
        while a Python ``tuple +`` would concatenate. Only simple operands:
        anything richer deserves a hand rather than a guess."""
        vec = self.vec_vars
        if not vec:
            return e
        saved: list[str] = []

        def mask(t: str) -> str:
            saved.append(t)
            return f"\x00{len(saved) - 1}\x00"

        def operand_ok(t: str) -> bool:
            t = t.strip()
            if t in vec:
                return True
            m = re.fullmatch(r"(\w+)\s*([*/])\s*(\d+(?:\.\d+)?)", t)
            return bool(m and m.group(1) in vec)

        prev = None
        while prev != e:
            prev = e
            m = re.search(r"\x00\d+\x00|([\w.\[\]]+\s*(?:[*/]\s*\d+(?:\.\d+)?)?)\s*([+\-*])\s*"
                          r"([\w.\[\]]+\s*(?:[*/]\s*\d+(?:\.\d+)?)?)", e)
            if not m:
                break
            if m.group(0).startswith("\x00"):
                continue
            lhs, op, rhs = m.group(1).strip(), m.group(2), m.group(3).strip()
            num_r = re.fullmatch(r"(\d+(?:\.\d+)?)", rhs)
            num_l = re.fullmatch(r"(\d+(?:\.\d+)?)", lhs)
            if lhs in vec and num_r and op in "*/-":
                a = self._vec_operand(lhs)
                rep = f"({a[0]} {op} {num_r.group(1)}, {a[1]} {op} {num_r.group(1)})"
                e = e[:m.start()] + rep + e[m.end():]
                continue
            if rhs in vec and num_l and op == "*":
                b = self._vec_operand(rhs)
                rep = f"({num_l.group(1)} * {b[0]}, {num_l.group(1)} * {b[1]})"
                e = e[:m.start()] + rep + e[m.end():]
                continue
            if not (operand_ok(lhs) and operand_ok(rhs)):
                # not ours to judge: park the span so the scan moves on
                e = e[:m.start()] + mask(e[m.start():m.end()]) + e[m.end():]
                continue
            a = self._vec_operand(lhs)
            b = self._vec_operand(rhs)
            e = (e[:m.start()] + f"({a[0]} {op} {b[0]}, {a[1]} {op} {b[1]})"
                 + e[m.end():])
        for i, t in enumerate(saved):
            e = e.replace(f"\x00{i}\x00", t)
        return e

    def _vec_literal_add(self, e: str) -> str:
        """``pos + (3, 3)`` / ``(3, 3) + pos`` / ``pos - (3, 3)`` with a
        two-component *literal*: component-wise, as the C++ overload did.
        A Python tuple ``+`` would concatenate, which is never what the
        C++ meant, so this one is safe to do even for unknown variables."""
        saved: list[str] = []

        def mask(t: str) -> str:
            saved.append(t)
            return f"\x00{len(saved) - 1}\x00"

        prev = None
        while prev != e:
            prev = e
            m = re.search(r"(?<![\w.])(\w+)\s*([+-])\s*\(([^()]*)\)"
                          r"|(?<![\w.])\(([^()]*)\)\s*([+-])\s*(\w+)(?![\w.(])", e)
            if not m:
                break
            if m.group(1) is not None:
                var, op, inner = m.group(1), m.group(2), m.group(3)
            else:
                inner, op, var = m.group(4), m.group(5), m.group(6)
            parts = split_args(inner)
            if (len(parts) != 2 or var in ("if", "while", "return", "for")
                    or any('"' in p or "'" in p for p in parts)):
                e = e[:m.start()] + mask(e[m.start():m.end()]) + e[m.end():]
                continue
            a = f"{var}[0] {op} {parts[0].strip()}"
            b = f"{var}[1] {op} {parts[1].strip()}"
            e = e[:m.start()] + f"({a}, {b})" + e[m.end():]
        for i, t in enumerate(saved):
            e = e.replace(f"\x00{i}\x00", t)
        return e

    def _vec_operand(self, t: str) -> tuple[str, str]:
        t = t.strip()
        m = re.fullmatch(r"(\w+)\s*([*/])\s*(\d+(?:\.\d+)?)", t)
        if m and m.group(1) in self.vec_vars:
            v, o, k = m.group(1), m.group(2), m.group(3)
            return (f"{v}[0] {o} {k}", f"{v}[1] {o} {k}")
        return (f"{t}[0]", f"{t}[1]")



CALL_HEAD_RE = re.compile(
    r"((?:\.)?[A-Za-z_][\w:]*(?:\.[A-Za-z_]\w*)*)\s*\(")

#: C keywords that may be followed by ``(``, which are not calls
KEYWORDS = {"if", "for", "while", "switch", "sizeof", "return", "case",
            "else", "do", "new", "delete", "catch", "and", "or", "not",
            "float", "int", "bool", "double", "char"}

