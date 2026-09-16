"""Source cleanup and small pure text helpers shared by every pass."""
from __future__ import annotations

import keyword as _keyword
import re

# --------------------------------------------------------------------------- #
# Source cleanup
# --------------------------------------------------------------------------- #

#: C++ identifiers that Python reserves.
#:
#: A Python keyword that C++ *also* reserves -- `class`, `for`, `return`,
#: `and`, `not` -- can never be a C++ identifier, so it must be left alone:
#: those tokens in the source are the C++ keywords themselves. What remains
#: is the set C++ leaves free, and in C++ source every occurrence of one of
#: those is unambiguously an identifier. That is what makes renaming them
#: safe to do blindly, with no need to track which names were declared.
#:
#: `assert` is excluded deliberately: it is `<cassert>`'s macro far more
#: often than anyone's variable, and renaming the macro would break the call.
_CPP_KEYWORDS = {
    "and", "and_eq", "asm", "auto", "bitand", "bitor", "bool", "break",
    "case", "catch", "char", "class", "compl", "const", "constexpr",
    "continue", "decltype", "default", "delete", "do", "double", "else",
    "enum", "explicit", "export", "extern", "false", "float", "for",
    "friend", "goto", "if", "inline", "int", "long", "mutable", "namespace",
    "new", "noexcept", "not", "not_eq", "nullptr", "operator", "or", "or_eq",
    "private", "protected", "public", "register", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "template", "this",
    "throw", "true", "try", "typedef", "typeid", "typename", "union",
    "unsigned", "using", "virtual", "void", "volatile", "while", "xor",
}

PY_ONLY_KEYWORDS = frozenset(
    kw for kw in _keyword.kwlist
    if kw not in _CPP_KEYWORDS and kw != "assert")


def safe_name(name: str) -> str:
    """A C++ identifier Python reserves, made usable.

    ``std::ifstream in(path);`` is ordinary C++, and ``in = ...`` is a
    *syntax error* in Python -- not a wrong value but a file that will not
    parse, so autoport's repair loop cuts the whole enclosing function. Two
    of cmc's panels were lost to one stream named `in`.

    A trailing underscore is the conventional escape and cannot collide:
    ``in_`` is not a keyword, and any real ``in_`` in the source is left
    alone because it was never a keyword to begin with.
    """
    return name + "_" if name in PY_ONLY_KEYWORDS else name


def rename_reserved(text: str) -> str:
    """Rename every reserved identifier in a span of *C++*.

    Blind on purpose -- see :data:`PY_ONLY_KEYWORDS` for why that is safe.
    String literals are masked first, so a `"from"` inside a message is left
    as the word it is.
    """
    if not any(kw in text for kw in PY_ONLY_KEYWORDS):
        return text
    out, lits, k = [], [], 0
    while k < len(text):
        if text[k] in "\"'":
            j = _skip_string(text, k)
            out.append(f"\x04{len(lits)}\x04")
            lits.append(text[k:j])
            k = j
            continue
        out.append(text[k])
        k += 1
    masked = _re_sub_reserved("".join(out))
    for i, lit in enumerate(lits):
        masked = masked.replace(f"\x04{i}\x04", lit)
    return masked


def _re_sub_reserved(text: str) -> str:
    return re.sub(r"\b(" + "|".join(sorted(PY_ONLY_KEYWORDS)) + r")\b",
                  lambda m: m.group(1) + "_", text)


def strip_comments(text: str) -> str:
    """Drop ``//`` and ``/* */`` (a port keeps the code, not the prose)."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def strip_preprocessor(text: str, defines=()) -> str:
    """Drop includes/guards/pragma; keep simple ``#define`` constants; keep the
    first branch of ``#if``/``#else``/``#endif`` (the port targets this emtk,
    not the version the other branch was for).

    ``#ifdef X`` is different from ``#if``: it has a *right answer*, and the
    answer is no unless X is in *defines*. Keeping those bodies regardless
    ported code the C++ build itself excludes -- cmc's ``BUILD_WITH_LEGACY``
    defaults off, so ``#ifdef CMC_WITH_LEGACY`` blocks are dead there, and
    the port called an ``AppConfig`` method that does not exist in the
    library it was calling into. ``#ifndef X`` is the mirror image and keeps
    its body unless X is defined.

    *defines*: the macros to treat as set, matching how the C++ is built.
    """
    defines = set(defines)
    keep: list[str] = []
    #: one entry per open conditional: True while its lines are being kept
    stack: list[bool] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(("#include", "#pragma", "#define IMGUI_", "#define IM_")):
            continue
        m = re.match(r"#(ifdef|ifndef)\s+([A-Za-z_]\w*)", s)
        if m:
            has = m.group(2) in defines
            stack.append(has if m.group(1) == "ifdef" else not has)
            continue
        if s.startswith("#if"):
            stack.append(True)          # `#if`: the first branch is the port's
            continue
        if s.startswith(("#elif", "#else")):
            if stack:
                # the other branch of something already taken is not taken;
                # the other branch of something skipped is
                stack[-1] = not stack[-1]
            continue
        if s.startswith("#endif"):
            if stack:
                stack.pop()
            continue
        if not all(stack):
            continue
        # a function-like macro definition: never expanded here (the
        # invocations are flagged; expanding is the hand's job)
        if re.match(r"#define\s+[A-Za-z_]\w*\s*\(", s):
            continue
        # a valueless define is an include guard
        if re.fullmatch(r"#define\s+[A-Za-z_]\w*", s):
            continue
        m = re.match(r"#define\s+([A-Za-z_]\w*)\s+([^\s].*?)\s*$", s)
        if m and "(" not in m.group(1):
            value = m.group(2)
            if re.fullmatch(r"[A-Za-z_]\w*", value):
                continue          # an alias of another name, not a constant
            keep.append(f"static const {m.group(1)} = {value};")
            continue
        keep.append(line)
    return "\n".join(keep)


def statements(text: str) -> list[str]:
    """One C++ statement per output line; *paren* spans are joined.

    Braces do not join: a ``struct X {`` line is a statement of its own and the
    block-tokenizer below reads the braces.
    """
    out: list[str] = []
    depth = 0
    buf = ""
    in_str = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if in_str:
            buf += ch
            if ch == "\\" and i + 1 < len(text):
                buf += text[i + 1]; i += 2; continue
            if ch == in_str:
                in_str = ""
            i += 1
            continue
        if ch in "\"'":
            in_str = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "\n" and depth > 0:
            # a statement continues: newline + indent becomes one space
            if not in_str:
                buf += " "
                j = i + 1
                while j < len(text) and text[j] in " \t":
                    j += 1
                i = j
                continue
        buf += ch
        if ch == "\n" and depth <= 0:
            stripped = buf.rstrip()
            if stripped and stripped[-1] in "=&|+-*/<>?:,!":
                buf += " "            # an expression continues on the next line
                j = i + 1
                while j < len(text) and text[j] in " \t":
                    j += 1
                i = j
                continue
            out.append(buf.rstrip("\n"))
            buf = ""
        i += 1
    if buf.strip():
        out.append(buf)
    return [s for s in out if s.strip()]


def strip_namespaces(text: str) -> str:
    """Delete ``namespace X {`` heads and their matching ``}`` closers.

    The Python module *is* the namespace; keeping the braces would make the
    statement scanner indent everything inside it.
    """
    original = text
    head_re = re.compile(r"\bnamespace\s+\w+\s*\{")
    heads = list(head_re.finditer(text))
    closers: list[int] = []
    for m in heads:
        depth = 0
        for i in range(m.end() - 1, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    closers.append(i)
                    break
    pieces: list[str] = []
    last = 0
    for m, close_at in zip(heads, closers):
        pieces.append(text[last:m.start()])
        last = m.end()
    out: list[str] = []
    last = 0
    head_pos = {m.start(): m.end() for m in heads}
    i = 0
    while i < len(text):
        if i in head_pos:
            out.append(text[last:i])
            i = head_pos[i]
            last = i
            continue
        if i in set(closers):
            out.append(text[last:i])
            i = i + 1
            last = i
            continue
        i += 1
    out.append(text[last:])
    text = "".join(out)
    # references to the removed namespaces lose their qualifier too
    for name in sorted(set(re.findall(r"\bnamespace\s+(\w+)", original))):
        text = re.sub(rf"\b{name}\s*::\s*", "", text)
        text = re.sub(rf"\b{name}\.\.+", "TODO.", text)
    return text


def split_args(s: str) -> list[str]:
    """Split on top-level commas."""
    parts: list[str] = []
    depth = 0
    cur = ""
    in_str = ""
    i = 0
    while i < len(s):
        c = s[i]
        if in_str:
            cur += c
            if c == "\\" and i + 1 < len(s):
                cur += s[i + 1]; i += 2; continue
            if c == in_str:
                in_str = ""
            i += 1
            continue
        if c in "\"'":
            in_str = c; cur += c
        elif c in "([{":
            depth += 1; cur += c
        elif c in ")]}":
            depth -= 1; cur += c
        elif c == "," and depth == 0:
            parts.append(cur.strip()); cur = ""
        else:
            cur += c
        i += 1
    if cur.strip():
        parts.append(cur.strip())
    return parts



def upper_snake(s: str) -> str:
    """``ButtonActive`` -> ``BUTTON_ACTIVE`` -- enum members, as emtk spells them."""
    out = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", s)
    out = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", out)
    return out.upper()


def _is_string(s: str) -> bool:
    s = s.strip()
    return len(s) >= 2 and s.startswith('"') and s.endswith('"')


def _unquote(s: str) -> str:
    return s.strip()[1:-1].replace('\\"', '"')


_PRINTF_INT = re.compile(
# The length modifiers a 64-bit application actually writes: `%zu` for
# a size_t and `%lu`/`%llu` for a count. Missing `z` and `l`, those
# specs reached Python's `%` verbatim and raised "unsupported format
# character" at the moment the line was printed.
                          r"%([-+ #0]*)(\d*)(?:\.(\d+))?(hh|h|ll|l|z|j|t|L)?([udixX])")


def _fix_printf(fmt: str) -> str:
    """printf specs Python's % accepts: %u/%lld/%5i -> %d forms."""
    def one(m):
        flags, width, prec, length, conv = m.groups()
        # `%x`/`%X` stay hex -- only the *length* modifier is meaningless in
        # Python. `%u` and `%i` have no Python spelling and become `%d`.
        out = conv if conv in "xX" else "d"
        return f"%{flags}{width}{'.' + prec if prec else ''}{out}"
    return _PRINTF_INT.sub(one, fmt)



def _skip_string(t: str, k: int) -> int:
    """*t[k]* is a quote (``"`` or ``'``): index just past the closing quote.
    Treats C++ char literals as strings, so ``'?'`` and ``':'`` are opaque."""
    quote = t[k]
    k += 1
    while k < len(t):
        if t[k] == "\\":
            k += 2
            continue
        if t[k] == quote:
            return k + 1
        k += 1
    return k


def find_matching_brace(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def find_matching_paren(text: str, start: int) -> int:
    """The index of the ``)`` closing the ``(`` at *start*, or ``len(text)``.

    The parenthesis twin of :func:`find_matching_brace`, and it exists for
    the same reason: telling "the condition *is* this call" from "the
    condition contains this call" is a question about where the call ends,
    and counting parens by eye in a regex cannot answer it.
    """
    depth = 0
    i = start
    while i < len(text):
        c = text[i]
        if c in "\"'":
            i = _skip_string(text, i)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text)


