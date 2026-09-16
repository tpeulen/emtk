"""Statement-level translation with brace-driven indentation."""
from __future__ import annotations

import re

from autoport.decls import _EMPTY, params_to_py
from autoport.lex import find_matching_paren, split_args, _skip_string
from autoport.tables import CPP_TYPES
from autoport.expressions import (Porter, _carry_duration_unit,
                                  drop_get_template,
                                  rewrite_static_cast)
from emtk.im_compat import mechanical_name

# --------------------------------------------------------------------------- #
# Statement translation
# --------------------------------------------------------------------------- #

DEC_RE = re.compile(
    rf"^(?:(?:static|inline|const|constexpr|thread_local)\s+)*"
    rf"(?P<type>{'|'.join(re.escape(t) for t in CPP_TYPES)})"
    # More than one dimension: `uint8_t palette[][3] = {{...}}` is a table,
    # and a pattern that reads a single `[...]` did not match it at all --
    # so the declaration was not a declaration, and the whole enclosing
    # function was cut. Only the first extent is captured; the rest are
    # consumed, because the initialiser already carries the shape.
    rf"(?P<ptr>\s*[&*]+|\s+)\s*(?P<name>\w+)\s*"
    r"(?:\[(?P<size>[^\]]*)\])?(?:\s*\[[^\]]*\])*\s*"
    r"(?:=\s*(?P<init>.*))?$")
# ``float a, b, c = 1.0f;`` -- one type, several declarators (the blob is
# split paren-aware afterwards, so initialisers may contain calls)
DEC_MULTI_RE = re.compile(
    rf"^(?:(?:static|inline|const|constexpr|thread_local)\s+)*"
    rf"(?P<type>{'|'.join(re.escape(t) for t in CPP_TYPES)})"
    rf"(?P<ptr>\s*[&*]+|\s+)\s*(?P<decls>\w[\w\s*&=,'\".()<>+\-]*\w)\s*$")
RANGE_FOR_RE = re.compile(
    r"for\s*\(\s*(?:const\s+)?(?:auto|[\w:]+)\s*[&*]?\s*(\w+)\s*:\s*(.+)\)")
C_FOR_RE = re.compile(r"for\s*\((.*?);(.*?);(.*?)\)$")

#: words that open a statement which is *not* a declaration, however much
#: ``<word> <name> = ...`` looks like one.
_NOT_A_TYPE = {"return", "delete", "new", "throw", "case", "goto", "using",
               "typedef", "friend", "template", "namespace", "struct",
               "class", "enum", "union", "public", "private", "protected",
               "operator", "else", "if", "while", "for", "do", "switch",
               "break", "continue", "sizeof", "co_return", "co_await"}

# --------------------------------------------------------------------------- #
# Lambdas that capture by reference
# --------------------------------------------------------------------------- #
# A C++ lambda writes straight through a `[&]` capture; the Python nested def
# it becomes does not, and the difference is silent until it isn't. Without a
# `nonlocal`, `row_str += buf` inside the def rebinds a *fresh local* -- the
# enclosing `row_str` never changes, and the first read of it inside the def
# raises `UnboundLocalError` at draw time, in a panel that ported cleanly.

#: Bindings a generated Python line makes. Only whole-identifier targets
#: count: `xs[i] = v` and `c.fit_ok = v` mutate an object that is already
#: bound, so they need no `nonlocal` and must not provoke one.
_PY_BIND_RE = re.compile(
    r"^(?P<lhs>[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*"
    r"(?:\*\*=|//=|>>=|<<=|[+\-*/%&|^]=|=(?!=))")
_PY_FOR_RE = re.compile(
    r"^for\s+(?P<lhs>[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s+in\s")
_PY_DEF_RE = re.compile(r"^def\s+(?P<lhs>\w+)")

#: A declaration inside the lambda body -- `char buf[32];`, `float v = *val;`,
#: `for (auto &c : xs)`. Deliberately generous: a name wrongly read as a local
#: only costs a `nonlocal` that is not emitted, while a local wrongly read as a
#: capture makes the def write the *enclosing* variable of the same name.
_CPP_DECL_RE = re.compile(
    r"(?:^|[;(])\s*"
    r"(?:(?:const|constexpr|static|volatile|mutable|thread_local|unsigned"
    r"|signed|struct|class)\s+)*"
    r"(?P<type>[A-Za-z_][\w:]*)\s*(?:<[^;{}]*>)?\s*[&*]*\s+[&*]*"
    r"(?P<name>[A-Za-z_]\w*)\s*(?:[=;,\[):]|$)")


#: A ``case X:`` / ``default:`` label, and nothing but a label. The value is
#: read with ``::`` excluded on both sides so a scoped enumerator --
#: ``case analysis::CpmRateSource::Sum:`` -- is not cut at its own scope
#: operator.
_CASE_LABEL_RE = re.compile(
    r"^(?:case\s+(?P<val>.+?)(?<!:):(?!:)|default\s*:)\s*$", re.S)

#: ``std::vector<T> v(100)`` / ``v(n, 0.0)`` -- a *sized* construction.
_SIZED_VECTOR_RE = re.compile(
    r"\b(?:std\s*::\s*)?vector\s*<(?P<elem>[^<>]*)>\s*(?P<name>\w+)\s*\(\s*"
    r"(?P<n>[^,()]+?)\s*(?:,\s*(?P<fill>[^()]+?)\s*)?\)\s*$")
#: What ``T()`` is, for the elements a sized construction fills with.
_VECTOR_ZERO = re.compile(
    r"^(?:unsigned\s+|signed\s+)?(?:int|char|short|long(?:\s+long)?|size_t"
    r"|u?int(?:8|16|32|64)_t|Im[US](?:8|16|32|64)|ImGuiID|unsigned|signed)$")


def _size_constructed_vector(s: str, porter) -> str:
    """``std::vector<float> pr_xs(100);`` -- a hundred default-constructed
    elements, not one element whose value is a hundred.

    The general rule sent the arguments straight through to ``std.vector``,
    which reads them as *the values*: the declaration produced a one-element
    vector and the loop that fills it raised ``IndexError: list assignment
    index out of range`` on its very first write.

    ``v(x)`` is genuinely ambiguous -- a count when ``x`` is a number, a copy
    when ``x`` is a container -- and nothing in the text settles it, so the
    one-argument form is only read as a count when the argument is a numeric
    literal, the one spelling that cannot be a container. Two arguments are
    unambiguous: a copy takes one, so ``(count, value)`` is the only reading
    left once an iterator pair is excluded.

    It runs before the template arguments are stripped because ``T`` is what
    says whether the fill is ``0``, ``0.0`` or ``False``, and a moment later
    ``T`` is gone.
    """
    m = _SIZED_VECTOR_RE.search(s)
    if not m:
        return s
    n, fill = m.group("n"), m.group("fill")
    if fill is None:
        if not re.fullmatch(r"\d+", n):
            return s
    elif ".begin(" in n or ".end(" in fill:
        return s                      # an iterator pair, not a count and a value
    elem = m.group("elem").replace("const", "").strip().rstrip("&*").strip()
    if fill is not None:
        value = porter.expr(fill)
    elif elem in ("float", "double"):
        value = "0.0"
    elif elem == "bool":
        value = "False"
    elif elem in ("std::string", "string"):
        value = '""'
    elif _VECTOR_ZERO.match(elem):
        value = "0"
    else:
        value = "None"
    return (s[:m.start()] + f"std::vector {m.group('name')} = "
            f"std.vector([{value}] * ({porter.expr(n)}))")


def _lambda_def_name(name: str) -> str:
    """The Python spelling of a named lambda, matching what its *calls* get.

    ``Porter._call`` leaves an already-lowercase free call alone and spells
    every other one mechanically. A def that does not follow the same rule
    is simply never called: ``ParamControlSafe`` defined, seven
    ``param_control_safe(...)`` below it, and a ``NameError`` on the first
    draw of the panel.
    """
    return name if re.fullmatch(r"[a-z]\w*", name) else mechanical_name(name)


def _captures_by_reference(cap: str, name: str) -> bool:
    """Does capture list ``cap`` (the brackets' contents) take ``name`` by
    reference? ``[&]`` takes everything that way except an explicit by-value
    exception in ``[&, x]``; ``[=]``, ``[]`` and ``[this]`` take nothing."""
    items = [it.strip() for it in cap.split(",") if it.strip()]
    default_ref = bool(items) and items[0] == "&"
    by_ref = {it.lstrip("&").strip() for it in items
              if it.startswith("&") and it != "&"}
    by_value = {it.strip() for it in items
                if not it.startswith("&") and it not in ("=", "this")}
    return name in by_ref or (default_ref and name not in by_value)


def _cpp_declared(stmts) -> set:
    """Every name the lambda body *declares*, so it is a local of the def and
    not a capture. In the generated Python a declaration and a write to a
    captured variable are the same line, so only the C++ can tell them apart."""
    names = set()
    for raw in stmts:
        s = re.sub(r"\s*\n\s*", " ", raw.strip())
        for m in _CPP_DECL_RE.finditer(s):
            if m.group("type") in _NOT_A_TYPE:
                continue
            names.add(m.group("name"))
    return names


def _py_bound(lines) -> set:
    """Every name the given generated lines bind."""
    names = set()
    for line in lines:
        s = line.strip()
        m = _PY_BIND_RE.match(s) or _PY_FOR_RE.match(s) or _PY_DEF_RE.match(s)
        if m:
            names.update(n.strip() for n in m.group("lhs").split(","))
    return names


def _visible_bindings(out, pad_len: int) -> set:
    """Names bound in the scopes *enclosing* a def about to be emitted at
    ``pad_len`` columns, walking what has been emitted from the bottom up.

    A bare ``nonlocal x`` for a name with no enclosing binding is itself a
    SyntaxError -- and the repair loop answers a SyntaxError by cutting the
    whole function, so an unjustified ``nonlocal`` costs more than the bug it
    was meant to fix. Lines deeper than the running limit belong to some
    *other* nested scope, whose bindings are invisible from here.
    """
    names, limit = set(), pad_len
    for line in reversed(out):
        if not line.strip():
            continue
        ind = len(line) - len(line.lstrip())
        if ind > limit:
            continue
        limit = ind
        names.update(_py_bound([line]))
    return names


def _split_conjuncts(cond: str) -> list:
    """Split a loop condition on top-level ``&&``. Parens and strings are
    opaque, so ``f(a && b) && c`` splits into two, not three."""
    out, buf, depth, k = [], "", 0, 0
    while k < len(cond):
        c = cond[k]
        if c in "\"'":
            j = _skip_string(cond, k)
            buf += cond[k:j]
            k = j
            continue
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif depth == 0 and cond.startswith("&&", k):
            out.append(buf)
            buf = ""
            k += 2
            continue
        buf += c
        k += 1
    out.append(buf)
    return [p for p in out if p.strip()]


def kw_is_loop_or_branch(kw: str) -> bool:
    return kw in ("if", "while", "for", "else if")


class StatementPorter:
    """Statement-level translation with brace-driven indentation."""

    def __init__(self, porter: Porter):
        self.p = porter

    def port(self, body_lines: list[str], indent: str = "    ") -> list[str]:
        body = "\n".join(body_lines)
        toks = self._tokenize(body)
        out: list[str] = []
        self._block(toks, 0, len(toks), 1, out, indent)
        return out

    # -- token stream ------------------------------------------------------ #

    def _tokenize(self, body: str) -> list[tuple[str, str]]:
        """(kind, text) tokens: '{' '}' ';' statements; strings protected.

        A ``{`` that opens a *brace initialiser* (``color_set{...}``, ``= {...}``,
        ``, {...}``) is part of the current statement, not a block: the thing
        before it is an identifier, ``=``, ``,`` or ``(`` -- never ``)`` (a
        definition's parameter list), ``else`` or ``do``.
        """
        toks: list[tuple[str, str]] = []
        buf = ""
        in_str = ""
        depth = 0
        i = 0
        while i < len(body):
            ch = body[i]
            if in_str:
                buf += ch
                if ch == "\\" and i + 1 < len(body):
                    buf += body[i + 1]; i += 2; continue
                if ch == in_str:
                    in_str = ""
                i += 1
                continue
            if ch in "\"'":
                in_str = ch; buf += ch
            elif ch == "(":
                depth += 1; buf += ch
            elif ch == ")":
                depth -= 1; buf += ch
            elif ch == ";" and depth > 0:
                buf += ch              # a for-header's separators are not ends
            elif ch == "{":
                prev = buf.rstrip()
                last_word = re.split(r"[\W_]+", prev)[-1] if prev.strip() else ""
                # a lambda header ends in ``)`` or ``-> T`` and its ``{`` opens
                # a *block*, not an initialiser -- on one line the two are
                # otherwise indistinguishable, and swallowing the body loses it
                is_lambda = re.search(r"=\s*\[[^\]]*\]\s*\(.*\)\s*"
                                      r"(?:mutable\s*)?(?:noexcept\s*)?"
                                      r"(?:->[^{]*)?$", prev) is not None
                # A lambda passed as an *argument* --
                # `make_unique<ImageWindow>([this]() { return node(); })` --
                # ends in `)` like a function header, so the `{` was taken
                # for a block and the statement was torn in half mid-call.
                # Swallowed into the statement instead, `_lambdas` can turn
                # it into a Python lambda.
                inline_lambda = re.search(r"[(,]\s*\[[^\]]*\]\s*\([^()]*\)\s*"
                                          r"(?:mutable\s*)?(?:noexcept\s*)?"
                                          r"(?:->\s*[^{]*)?$", prev) is not None
                # `std::vector<std::array<int, 3>>{a, b, c}` -- a braced
                # construction of a *templated* type ends in `>`, not in an
                # identifier, so the brace read as a block and tore the
                # statement in half mid-argument. (The templates are not
                # stripped yet: that happens per statement, after this.)
                templated = (prev.endswith(">")
                             and re.search(r"[A-Za-z_]\w*\s*<", prev) is not None)
                # `templated` must yield to `is_lambda`: a lambda with a
                # trailing return type ends in `>` too
                # (`[&](int n) -> std::pair<double, double> {`), and reading
                # that `{` as a braced construction swallowed the lambda's
                # whole body, so no `def` was emitted and every call to it
                # was a NameError.
                if prev and (inline_lambda or (templated and not is_lambda)
                             or ((prev[-1].isalnum() or prev[-1] in "_=,(")
                                 # `try {` opens a block, not an initialiser:
                                 # swallowed, the whole try/catch became one
                                 # unparseable statement and took the
                                 # function with it.
                                 and last_word not in ("else", "do", "try")
                                 and not is_lambda)):
                    buf += ch              # brace initialiser: swallow to its `}`
                    # `braces`, not `depth`: `depth` is the *paren* nesting
                    # this loop is keeping, and `resize(8, {1, 2, 3})` reaches
                    # here inside a `(`. Reusing it left the count one low, so
                    # the semicolons of the *next* `for` header read as
                    # statement ends and the loop was torn into three pieces --
                    # one of which ported to `for _ in range(0)`, a loop that
                    # runs no times and says nothing.
                    braces = 1
                    i += 1
                    while i < len(body) and braces:
                        c2 = body[i]
                        if in_str:
                            buf += c2
                            if c2 == "\\" and i + 1 < len(body):
                                buf += body[i + 1]; i += 2; continue
                            if c2 == in_str:
                                in_str = ""
                            i += 1
                            continue
                        if c2 in "\"'":
                            in_str = c2
                        elif c2 == "{":
                            braces += 1
                        elif c2 == "}":
                            braces -= 1
                        buf += c2
                        i += 1
                    continue
                if buf.strip():
                    toks.append(("stmt", buf.strip()))
                buf = ""
                toks.append(("{", "{"))
            elif ch == "}":
                if buf.strip():
                    toks.append(("stmt", buf.strip()))
                buf = ""
                toks.append(("}", "}"))
            elif (ch == ":" and depth == 0
                  and body[i + 1:i + 2] != ":" and body[i - 1:i] != ":"
                  and re.match(r"^\s*(?:case\b|default\s*$)", buf)):
                # A `case X:` label ends a statement exactly as `;` does. Left
                # glued to what follows it, `case A:\n idx = 0;` arrived as one
                # token and `_switch` matched the label and threw the rest away
                # -- so the branch came out empty, `if ...:` with nothing under
                # it, and the repair loop cut the whole function.
                toks.append(("stmt", (buf + ch).strip()))
                buf = ""
            elif ch == ";":
                if buf.strip():
                    toks.append(("stmt", buf.strip()))
                buf = ""
            else:
                buf += ch
            i += 1
        if buf.strip():
            toks.append(("stmt", buf.strip()))
        return toks

    def _find_block_end(self, toks, open_idx) -> int:
        depth = 0
        for k in range(open_idx, len(toks)):
            if toks[k][0] == "{":
                depth += 1
            elif toks[k][0] == "}":
                depth -= 1
                if depth == 0:
                    return k
        return len(toks)

    def _captured(self, toks, start, end, cap, params, body, out,
                  pad_len: int) -> list:
        """The names a ``[&]`` lambda writes through, for its def's ``nonlocal``.

        Four things have to hold together, and every one of them is there to
        stop a ``nonlocal`` that will not compile or will write the wrong
        variable: the name is *bound* by the generated body, is not one of the
        def's own parameters, is not declared inside the lambda (that would
        shadow, not capture), is captured by reference, and -- last and
        strictest -- is visibly bound in an enclosing scope. C++ can only
        capture a variable that is already in scope, so an honest capture is
        always among the lines already emitted.
        """
        stmts = [t for kind, t in toks[start:end] if kind == "stmt"]
        local = _cpp_declared(stmts) | set(
            re.sub(r"=.*", "", p).strip() for p in params)
        visible = _visible_bindings(out, pad_len)
        return sorted(n for n in _py_bound(body)
                      if n not in local and n in visible
                      and _captures_by_reference(cap, n))

    def _body(self, toks, start, end, depth, out, indent, case_depth=None):
        """A nested block, guaranteed non-empty.

        C++ tolerates a branch whose body is empty or only a comment --
        ``if (done) { /* nothing to do */ }`` -- and Python does not. Without
        the ``pass``, the port is a syntax error the repair loop cannot
        sandpaper away, so it cuts the *enclosing function* down to ``pass``:
        one comment-only branch used to cost a whole panel.
        """
        mark = len(out)
        self._block(toks, start, end, depth, out, indent, case_depth)
        if len(out) == mark:
            out.append(indent * depth + "pass")

    def _block(self, toks, start, end, depth, out, indent, case_depth=None):
        """Walk statements; headers open nested blocks.

        ``case_depth``: while porting a switch case's block, a ``break`` at
        exactly that level ended the C++ case -- Python needs no terminator,
        so it is dropped (a break deeper inside an if/loop still ports).
        """
        k = start
        pad = indent * depth
        while k < end:
            kind, text = toks[k]
            if kind != "stmt":
                k += 1
                continue
            s = text.strip()
            if s == "break" and case_depth is not None and depth == case_depth:
                k += 1
                continue
            s = re.sub(r"\s*\n\s*", " ", s)   # a joined statement, one line
            # ``make_unique<T>()`` is the exception to the rule below: its
            # template argument is not an annotation, it is *what to
            # construct*, and dropping it left `std::make_unique()` -- a
            # call with nothing to make. This has to run here as well as in
            # Porter.expr, because a statement is stripped before it ever
            # reaches the expression porter.
            # `j.get<int>()` is the value itself -- see Porter.expr, which
            # cannot see this because a statement is stripped before it gets
            # there.
            # Before the template strip below, which would leave a bare
            # `static_cast(x)` -- the annotation gone and the conversion
            # with it.
            s = rewrite_static_cast(s)
            s = drop_get_template(s)
            # `duration_cast<milliseconds>(d)`: the unit IS the template
            # argument, so the generic strip below left `.count()` with no
            # idea what it counts. Carried across as a second argument.
            s = _carry_duration_unit(s)
            s = re.sub(r"\bmake_(unique|shared)\s*<([\w:]+)[^<>]*>\s*\(\s*\)",
                       r"make_\1(\2)", s)
            s = re.sub(r"\bmake_(unique|shared)\s*<([\w:]+)[^<>]*>\s*\(",
                       r"make_\1(\2, ", s)
            # explicit template arguments evaporate -- including non-type
            # ones, as in ``std::array<uint64_t, 4>``, where the ``4`` would
            # otherwise leave a stray ``<`` reading as a comparison.
            #
            # To a fixed point: only the innermost `<...>` matches, so one
            # pass over `std::vector<std::pair<int, int>>` left
            # `std::vector<std::pair>` -- still not a declaration, so the
            # local was never declared and every later use of it NameErrored
            # in a function that otherwise ported cleanly.
            s = _size_constructed_vector(s, self.p)
            prev_s = None
            while prev_s != s:
                prev_s = s
                s = re.sub(r"\b([A-Za-z_]\w*)<(?:[A-Za-z_][\w:.]*|\d+)"
                           r"(?:\s*,\s*(?:[A-Za-z_][\w:.]*|\d+))*>", r"\1", s)

            # ``auto f = [&](int x) -> T {`` is a named function, and Python
            # spells that ``def f(x):``. Ported as an expression instead, the
            # header is mangled and the body *leaks into the enclosing scope*
            # -- a stray ``return`` that truncates the caller.
            lam = re.match(
                r"^(?:const\s+)?auto\s*&?\s*(\w+)\s*=\s*"
                r"\[(?P<cap>[^\]]*)\]\s*\((?P<params>.*)\)\s*"
                r"(?:mutable\s*)?(?:noexcept\s*)?(?:->\s*[^{]+?)?$", s, re.S)
            if lam and k + 1 < end and toks[k + 1][0] == "{":
                names = params_to_py(lam.group("params"), False, porter=self.p)
                close = self._find_block_end(toks, k + 1)
                body: list[str] = []
                # A `return` inside the lambda belongs to the *lambda*, not to
                # the function around it -- so it must not carry that
                # function's out-parameters. `RenderSimulationSettings` has
                # four, and its inner `get_q_species` came out returning
                # `(qD, qA), brightness, rate_idx, changed`, which unpacked
                # into `d, a = ...` as "too many values". Out-parameters are
                # suspended for exactly the span of the lambda body.
                outer = (self.p.out_src_name, self.p.out_extras, self.p.out_names)
                self.p.out_src_name, self.p.out_extras, self.p.out_names = None, [], []
                try:
                    self._body(toks, k + 2, close, depth + 1, body, indent)
                finally:
                    (self.p.out_src_name, self.p.out_extras,
                     self.p.out_names) = outer
                captured = self._captured(toks, k + 2, close, lam.group("cap"),
                                          names, body, out, len(pad))
                out.append(f"{pad}def {_lambda_def_name(lam.group(1))}"
                           f"({', '.join(names)}):")
                if captured:
                    out.append(f"{pad}{indent}nonlocal {', '.join(captured)}")
                out += body
                k = close + 1
                continue

            # control headers with a { block after them
            m = re.match(r"^(else\s+if|else|if|while|for|do)\b(.*)$", s, re.S)
            if m and kw_is_loop_or_branch(m.group(1)):
                kw0, rest0 = m.group(1), m.group(2).strip()
                if kw0 in ("if", "while", "for", "else if") and rest0.startswith("("):
                    depth_c = 0
                    idx = None
                    for i2, ch2 in enumerate(rest0):
                        if ch2 == "(":
                            depth_c += 1
                        elif ch2 == ")":
                            depth_c -= 1
                            if depth_c == 0:
                                idx = i2
                                break
                    trailing = rest0[idx + 1:].strip() if idx is not None else ""
                    if idx is not None and trailing and not trailing.startswith("{"):
                        out.extend(self._header(kw0, rest0[:idx + 1], pad))
                        sub = self._tokenize(trailing)
                        self._body(sub, 0, len(sub), depth + 1, out, indent)
                        k += 1
                        continue
            # C++ try/catch, which lines up one for one: `catch (const
            # std::exception &e)` is `except Exception as e:`. Left
            # untranslated, the `try` was a bare statement and the block
            # under it was indented against nothing -- a syntax error the
            # repair loop could only fix by cutting the whole function.
            tm = re.match(r"^(?:(try)|catch\s*\((?P<exc>[^)]*)\))\s*$", s, re.S)
            if tm:
                if tm.group(1):
                    out.append(f"{pad}try:")
                else:
                    exc = (tm.group("exc") or "").strip()
                    nm = re.search(r"[&*]\s*(\w+)\s*$", exc)
                    out.append(f"{pad}except Exception"
                               + (f" as {nm.group(1)}:" if nm else ":"))
                if k + 1 < end and toks[k + 1][0] == "{":
                    close = self._find_block_end(toks, k + 1)
                    self._body(toks, k + 2, close, depth + 1, out, indent)
                    k = close + 1
                    continue
                k += 1
                continue

            m = re.match(r"^(else\s+if|else|if|while|for|do)\b(.*)$", s, re.S)
            if m:
                kw, rest = m.group(1), m.group(2).strip()
                if kw == "else":
                    out.append(f"{pad}else:")
                    # ``else out.emplace_back(b, a);`` -- an unbraced else has
                    # no parentheses to end its header, so the statement rides
                    # on the same token. The bracketed forms are caught above
                    # by the trailing-text rule; this is the one that is not,
                    # and the body was being dropped in silence.
                    if rest:
                        sub = self._tokenize(rest)
                        self._body(sub, 0, len(sub), depth + 1, out, indent)
                        k += 1
                        continue
                elif kw == "do":
                    out.append(f"{pad}while True:")
                else:
                    header = self._header(kw, rest, pad)
                    for line in header:
                        out.append(line)
                if k + 1 < end and toks[k + 1][0] == "{":
                    close = self._find_block_end(toks, k + 1)
                    self._body(toks, k + 2, close, depth + 1, out, indent)
                    k = close + 1
                    continue
                elif k + 1 < end and toks[k + 1][0] == "stmt":
                    # a single unbraced statement is the whole body
                    body_close = k + 2
                    bm = re.match(r"^(else\s+if|else|if|while|for|do)\b",
                                  toks[k + 1][1].strip())
                    if bm and k + 2 < end and toks[k + 2][0] == "{":
                        body_close = self._find_block_end(toks, k + 2) + 1
                    self._body(toks, k + 1, body_close, depth + 1, out, indent)
                    k = body_close
                    # "} while (cond);" closes a do-block
                    if kw == "do" and k < end and toks[k][0] == "stmt" \
                            and re.match(r"^while\s*\(", toks[k][1].strip()):
                        cond = toks[k][1].strip()
                        cm = re.match(r"^while\s*\((.*)\)$", cond, re.S)
                        c = self.p.expr(cm.group(1)) if cm else "True"
                        out.append(f"{pad}if not ({c}):")
                        out.append(f"{pad}    break")
                        k += 1
                    # "case" chains following a switch block are consumed there
                    continue
                k += 1
                continue

            # switch with its cases
            if re.match(r"^switch\b", s):
                sm = re.match(r"^switch\s*\((.*)\)$", s, re.S)
                subj = self.p.expr(sm.group(1)) if sm else "_"
                if k + 1 < end and toks[k + 1][0] == "{":
                    close = self._find_block_end(toks, k + 1)
                    self._switch(toks, k + 2, close, subj, depth, out, indent)
                    k = close + 1
                    continue

            out.extend(self._simple(s, pad))
            k += 1

    def _hoist(self, cond: str, pad: str, kw: str) -> list[str] | None:
        """``if (ImGui::Checkbox("x", &v))`` -- the pointer rule inside a test.

        The value-write call ports to ``_changed, v = im.checkbox("x", v)``,
        an assignment, and Python has no assignment inside an ``if``. The
        assignment is hoisted above the test, which is also the order C++
        runs it in. This is the single most common line in a settings panel,
        so getting it wrong costs whole panels, not single lines.
        """
        m = re.match(r"^_changed, (.+?) = (.+)$", cond, re.S)
        if not m:
            return None
        if kw != "if":
            self.p.todos.append(
                f"{kw} ({cond}): a value-write call in a {kw} test re-runs each "
                f"pass; hoisting it would change that -- translate by hand")
            return [f"{pad}pass  # TODO(autoport): value-write call in a {kw} test"]
        return [f"{pad}_changed, {m.group(1)} = {m.group(2)}",
                f"{pad}if _changed:"]

    def _hoist_out_call(self, rest: str, pad: str) -> list[str] | None:
        """``if (Intersect(a, b, &lo, &hi))`` -- a *user* out-value call in a test.

        :meth:`_hoist` handles the ImGui shape, which the call rules have
        already turned into an assignment. This is the application's own:
        ``Intersect`` writes through two references and returns a bool, so on
        this side it returns ``(ok, lo, hi)`` -- and a tuple in an ``if`` is
        always true. Left alone the branch was simply always taken, which is
        the worst kind of wrong: it runs, it draws, and it is wrong.

        Only a condition that is *entirely* the call (optionally negated) is
        hoisted. Anything compound would change how often the call runs.
        """
        s = rest.strip()
        negated = False
        while s.startswith("!"):
            negated = not negated
            s = s[1:].strip()
        if s.startswith("(") and s.endswith(")") and find_matching_paren(s, 0) == len(s) - 1:
            s = s[1:-1].strip()
        if not _calls_out_func(s, self.p.out_funcs):
            return None
        # the whole condition must be the call: `f(...)` and nothing after it
        m = re.match(r"^[\w.]*?\w+\s*\(", s)
        if not m or find_matching_paren(s, m.end() - 1) != len(s) - 1:
            return None
        target = _out_call_target(s, _out_index(s, self.p.out_funcs))
        if not target:
            return None
        return [f"{pad}_ret, {target} = {self.p.expr(s)}",
                f"{pad}if {'not _ret' if negated else '_ret'}:"]

    def _header(self, kw: str, rest: str, pad: str) -> list[str]:
        if kw == "else if":
            rest = rest.strip()
            cond = self.p.expr(rest[1:-1] if rest.startswith("(") else rest)
            # an elif cannot hoist: the assignment must not run when an
            # earlier branch already matched
            if re.match(r"^_changed, .+? = ", cond):
                self.p.todos.append(
                    f"else if ({cond}): hoisting the value-write call would run "
                    f"it even when an earlier branch matched -- translate by hand")
                return [f"{pad}elif False:  # TODO(autoport): value-write call in an else-if test"]
            return [f"{pad}elif {cond}:"]
        rest = rest.strip()
        if rest.startswith("(") and rest.endswith(")"):
            rest = rest[1:-1]
        if kw == "if":
            # `if (auto x = f())` -- C++17's if-with-initializer. Python has
            # no assignment in a test, so the declaration is hoisted above it
            # and the test becomes the name. That is the same order C++ runs
            # them in, and the same shape the `while` form below already
            # takes; without it the header ported as `if auto x = f():`,
            # which is a syntax error, so the repair loop cut the function.
            idecl = re.match(r"^(?:const\s+)?(?:auto|[A-Za-z_][\w:]*)"
                             r"\s*[&*]?\s*(\w+)\s*=\s*(.+)$", rest.strip(), re.S)
            if idecl and not re.match(r"^(?:return|delete|new|throw)\b", rest.strip()):
                name, init = idecl.group(1), idecl.group(2).strip()
                if not re.match(r"^[=<>!]", init):        # not `a == b`
                    return [f"{pad}{name} = {self.p.expr(init)}",
                            f"{pad}if {name} is not None:"]
            # `if (x = f())` -- an assignment in the test with no declaration.
            # The same hoist, and the same reason: `if x = f():` does not
            # parse. `(?<![=!<>])=(?!=)` is the whole difference between this
            # and a comparison.
            iassign = re.match(r"^([A-Za-z_][\w.\[\]]*)\s*(?<![=!<>])=(?!=)\s*(.+)$",
                               rest.strip(), re.S)
            if iassign:
                lhs = self.p.expr(iassign.group(1))
                return [f"{pad}{lhs} = {self.p.expr(iassign.group(2).strip())}",
                        f"{pad}if {lhs}:"]
            hoisted = self._hoist_out_call(rest, pad)
            if hoisted:
                return hoisted
            cond = self.p.expr(rest)
            return self._hoist(cond, pad, "if") or [f"{pad}if {cond}:"]
        if kw == "while":
            # ``while (auto x = f())`` -- C++ re-declares and re-tests each
            # pass. Python has no assignment in a test, so the loop becomes
            # unconditional and the test moves to a guarded ``break``, which
            # runs in exactly the same order.
            wd = re.match(r"^(?:auto|[A-Za-z_][\w:]*)\s*[&*]?\s*(\w+)\s*=\s*(.+)$",
                          rest.strip(), re.S)
            if wd and not re.match(r"^(?:return|delete|new|throw)\b", rest.strip()):
                return [f"{pad}while True:",
                        f"{pad}    {wd.group(1)} = {self.p.expr(wd.group(2).strip())}",
                        f"{pad}    if not {wd.group(1)}:",
                        f"{pad}        break"]
            cond = self.p.expr(rest)
            return self._hoist(cond, pad, "while") or [f"{pad}while {cond}:"]
        if kw == "for":
            return [f"{pad}{self._for(rest)}:"]
        return [f"{pad}{kw}:"]

    def _for(self, src: str) -> str:
        src = src.strip()
        if src.startswith("(") and src.endswith(")"):
            src = src[1:-1].strip()
        m = RANGE_FOR_RE.match(f"for ({src})")
        if m:
            return f"for {m.group(1)} in {self.p.expr(m.group(2))}"
        m = C_FOR_RE.match(f"for ({src})")
        if not m:
            self.p.todos.append(f"for ({src})")
            return "for _ in range(0):  # TODO(autoport)"
        init, cond, step = (x.strip() for x in m.groups())
        if re.match(r"^[A-Za-z_]\w*\s+[A-Za-z_]\w*\s*=", init):
            init = re.sub(r"^[A-Za-z_]\w*\s+", "", init)   # typed: SlotIndex i = 0
        init = re.sub(r"^(?:int|size_t|unsigned int|unsigned|float|ImS32|ImU32|auto)\s+", "", init)
        dm = re.match(r"(\w+)\s*=\s*(.*)", init)
        if not dm:
            self.p.todos.append(f"for ({init}; {cond}; {step})")
            return f"for _ in range(0):  # TODO(autoport)"
        var, start = dm.group(1), self.p.expr(dm.group(2))
        # `for (i = 0; i < 4 && i < (int)cols.size(); i++)` -- two bounds on
        # the same counter, which is one `min`. Matched before the single
        # comparison below, because that pattern's `(.*)` happily swallowed
        # the `&& ...` into the *stop* expression: the loop then ran
        # `range(0, int(4 and i < len(cols)))`, which is not a bound at all.
        conj = _split_conjuncts(cond)
        if len(conj) > 1:
            bounds = []
            for part in conj:
                pm = re.fullmatch(rf"{var}\s*<\s*(.*)", part.strip())
                if not pm:
                    bounds = []
                    break
                bounds.append(f"int({self.p.expr(pm.group(1))})")
            if bounds and step in (f"++{var}", f"{var}++"):
                return (f"for {var} in range(int({start}), "
                        f"min({', '.join(bounds)}))")
        cm = re.match(rf"{var}\s*(<=|<|!=|>=|>)\s*(.*)", cond)
        if cm:
            op, stop = cm.group(1), self.p.expr(cm.group(2))
            if step in (f"++{var}", f"{var}++"):
                if op == "<":
                    return f"for {var} in range(int({start}), int({stop}))"
                if op == "<=":
                    return f"for {var} in range(int({start}), int({stop}) + 1)"
            if step in (f"--{var}", f"{var}--"):
                if op in (">", ">="):
                    end = f"int({stop}) - 1" if op == ">=" else f"int({stop})"
                    return f"for {var} in range(int({start}), {end}, -1)"
            sm = re.match(rf"{var}\s*(\+=|-=)\s*([\w.]+)", step)
            if sm and op == "<":
                d = sm.group(2) if sm.group(1) == "+=" else f"-{sm.group(2)}"
                return f"for {var} in range(int({start}), int({stop}), {d})"
        self.p.todos.append(f"for ({init}; {cond}; {step})")
        return f"for _ in range(0):  # TODO(autoport): for({init}; {cond}; {step})"

    def _switch(self, toks, start, end, subj: str, depth, out, indent):
        """``switch`` -> if/elif/else.

        A run of labels with nothing between them is C++ *fallthrough* onto
        one body -- ``case Int:`` immediately followed by ``default:`` -- and
        it is one Python branch, not two. Emitted as two, the first got no
        body at all: ``elif ... :`` with the next ``else:`` under it, an
        `IndentationError` that cost the whole function.
        """
        pad = indent * depth
        k = start
        first = True
        while k < end:
            kind, text = toks[k]
            if kind != "stmt":
                k += 1
                continue
            s = text.strip()
            lm = _CASE_LABEL_RE.match(s)
            if lm:
                vals, has_default = [], lm.group("val") is None
                if not has_default:
                    vals.append(self.p.expr(lm.group("val")))
                j = k + 1
                while j < end and toks[j][0] == "stmt":
                    nm = _CASE_LABEL_RE.match(toks[j][1].strip())
                    if not nm:
                        break
                    if nm.group("val") is None:
                        has_default = True
                    else:
                        vals.append(self.p.expr(nm.group("val")))
                    j += 1
                if has_default:
                    # `default` alone cannot open the chain: a bare `else:` is
                    # a syntax error, and the repair loop answers that by
                    # cutting the function the switch was the point of.
                    out.append(f"{pad}else:" if not first else f"{pad}if True:")
                else:
                    cond = " or ".join(f"{subj} == {v}" for v in vals)
                    out.append(f"{pad}{'if' if first else 'elif'} {cond}:")
                first = False
                mark = len(out)
                branch_pad = indent * (depth + 1)
                # a case may open a { block: its statements are the branch body
                if j < end and toks[j][0] == "{":
                    close = self._find_block_end(toks, j)
                    self._body(toks, j + 1, close, depth + 1, out, indent,
                               case_depth=depth + 1)
                    k = close + 1
                    continue
                while j < end:
                    kj, tj = toks[j]
                    if kj == "stmt" and _CASE_LABEL_RE.match(tj.strip()):
                        break
                    if kj == "stmt":
                        ss = tj.strip()
                        # the terminator of a branch is not a statement: left
                        # in, `break` ported literally and Python read it as an
                        # exit from whatever loop the switch itself sat in
                        if re.fullmatch(r"break", ss):
                            j += 1
                            continue
                        if re.match(r"^(else\s+if|else|if|while|for|do)\b", ss) \
                                and j + 1 < end and toks[j + 1][0] == "{":
                            out.extend(self._header_if(ss, branch_pad))
                            close = self._find_block_end(toks, j + 1)
                            self._body(toks, j + 2, close, depth + 2, out, indent)
                            j = close + 1
                            continue
                        out.extend(self._simple(ss, branch_pad))
                    j += 1
                if len(out) == mark:
                    out.append(branch_pad + "pass")
                k = j
                continue
            out.extend(self._simple(s, pad))
            k += 1

    def _header_if(self, s: str, pad: str) -> list[str]:
        m = re.match(r"^(else\s+if|else|if|while|for|switch|do)\b(.*)$", s, re.S)
        kw, rest = m.group(1), m.group(2).strip()
        if kw in ("else", "do"):
            return [f"{pad}else:" if kw == "else" else f"{pad}while True:"]
        rest = rest.strip()
        if rest.startswith("(") and rest.endswith(")"):
            rest = rest[1:-1]
        return self._header(kw, rest, pad)

    # -- one statement ----------------------------------------------------- #

    def _drag_behavior_assign(self, lhs: str, rhs: str, pad: str):
        """``x = ImGui::DragBehavior(id, T, v, ...)`` -> ``x, v = im.drag_scalar(...)``."""
        mdrag = re.search(r"ImGui::(Drag|Slider)Behavior\(\s*([\w.:]+)\s*,"
                          r"\s*[\w:]+\s*,\s*\&?(\w+)", rhs)
        if not mdrag:
            return None
        val = mdrag.group(3)
        fn = "drag_scalar" if mdrag.group(1) == "Drag" else "slider_scalar"
        rhs_t = self.p.expr(rhs)
        inner = re.search(r'im\.(?:drag|slider)_scalar\(\s*([\w."#]+)\s*,', rhs_t)
        if not inner:
            return [f"{pad}{lhs} = {rhs_t}"]
        depth = 1
        i = inner.end()
        while i < len(rhs_t) and depth:
            if rhs_t[i] == "(":
                depth += 1
            elif rhs_t[i] == ")":
                depth -= 1
            i += 1
        tail = rhs_t[inner.end():i - 1]
        tail = re.sub(r"^\s*,?\s*" + re.escape(val) + r"\s*,", ",", tail)
        return [f"{pad}{lhs}, {val} = im.{fn}({inner.group(1)}, {val}{tail})"]

    def _simple(self, s: str, pad: str) -> list[str]:
        if not s:
            return []
        # imgui-internal window draw state (window->DC.*) has no emtk
        # counterpart: say so, and keep the module runnable
        if re.search(r"(?:\.|->)\s*DC\s*\.", s) or "GetCurrentWindow()" in s:
            return [f"{pad}pass  # TODO(autoport): internal window state, "
                    f"no emtk counterpart -- the C++ follows"] + \
                   [f"{pad}# cpp| {ln}" for ln in s.splitlines()]
        if s in ("break", "continue"):
            return [f"{pad}{s}"]
        # a function-like macro invocation: expansion is the hand's job
        mm = re.match(r"([A-Za-z_]\w*)\s*\(", s)
        if mm and mm.group(1) in self.p.macros:
            # the invocation itself follows: expanding it by hand means
            # knowing what was passed, and dropping the arguments took that
            # away along with the macro
            return [f"{pad}pass  # TODO(autoport): macro {mm.group(1)}(...) "
                    f"invocation dropped -- expand by hand"] + \
                   [f"{pad}# cpp| {ln}" for ln in s.splitlines()]
        if s == "default:":
            return [f"{pad}else:"]
        m = re.match(r"^case\s+(.+?)(?<!:):(?!:)", s)
        if m:
            return [f"{pad}if _ == {self.p.expr(m.group(1))}:  # TODO(autoport): case"]
        if s.startswith("else"):
            return [f"{pad}else:"]
        if s.startswith("return"):
            val = s[6:].strip()
            if val.startswith("{") and val.endswith("}"):
                if self.p.ret_cls:
                    val = f"{self.p.ret_cls}({val[1:-1]})"
                else:
                    val = "(" + val[1:-1] + ")"   # anonymous struct init -> tuple
            if val.startswith("*"):
                val = val[1:].strip()
            # What this function owes its caller besides its result: the
            # out-parameters, in declaration order. One is spelled `value`
            # (params_to_py renamed it); several keep their own names.
            carried = ("value" if self.p.out_src_name
                       else ", ".join(self.p.out_names) if self.p.out_names
                       else "")
            if not val:
                if carried:
                    return [f"{pad}return None, {carried}"]
                return [f"{pad}return"]
            ret = f"return {self.p.expr(val)}"
            if carried and not _calls_out_func(val, self.p.out_funcs):
                # a forwarded call already returns the (result, value) tuple
                ret = f"return {self.p.expr(val)}, {carried}"
            return [f"{pad}{ret}"]
        # `c.hist_count++` and `v[i]++` as well as `i++`: the target of an
        # increment is any lvalue, and matching only a bare name left the
        # member form as a bare `c.hist_count++` -- a syntax error, so the
        # repair loop cut the enclosing function.
        target = r"[A-Za-z_]\w*(?:\s*(?:\.|->)\s*\w+|\s*\[[^\[\]]*\])*"
        m = re.fullmatch(rf"(\+\+|--)\s*({target})|({target})\s*(\+\+|--)", s)
        if m:
            var = self.p.expr((m.group(2) or m.group(3)).strip())
            op = "-=" if (m.group(1) or m.group(4)) == "--" else "+="
            return [f"{pad}{var} {op} 1"]
        # a structured binding is Python's own tuple unpacking, spelled with
        # brackets: ``auto [d, a] = get(0);`` -> ``d, a = get(0)``
        sb = re.match(r"^(?:const\s+)?auto\s*&?\s*\[([^\]]+)\]\s*=\s*(.+)$", s, re.S)
        if sb:
            names = ", ".join(n.strip() for n in sb.group(1).split(","))
            return [f"{pad}{names} = {self.p.expr(sb.group(2).strip())}"]
        # An anonymous struct local: `struct { uint8_t r, g, b; } c = {1,2,3};`
        # C++ has no name for the type and neither does Python, but the code
        # goes on to read `c.r` -- so it becomes a namespace with those
        # fields. Left alone it did not parse, and the enclosing function was
        # cut for it.
        anon = re.match(
            r"^(?:(?:static|const)\s+)*struct\s*\{(?P<fields>[^{}]*)\}\s*"
            r"(?P<name>\w+)\s*(?:=\s*\{(?P<init>[^{}]*)\})?$", s, re.S)
        if anon:
            return self._anonymous_struct(anon, pad)
        if DEC_RE.match(s):
            return self._declaration(s, pad)
        dm = DEC_MULTI_RE.match(s)
        if dm and "," in dm.group("decls"):
            # ``float a, b = 1, c;`` -- each declarator keeps its own init
            out = []
            for part in split_args(dm.group("decls")):
                pm = re.fullmatch(r"[&*]*\s*(\w+)\s*(?:=\s*(.+))?", part.strip())
                if not pm:
                    out = []
                    break
                name, init = pm.group(1), pm.group(2)
                value = self.p.expr(init.strip()) if init else \
                    "0.0" if dm.group("type") in ("float", "double") else "0"
                out.append(f"{pad}{name} = {value}")
            if out:
                return out
        # A declaration whose type the table does not know. CPP_TYPES can
        # name the standard library, never the *application's* own types --
        # ``DeviceInfo info = probe();``, ``nlohmann::json &obj = doc[k];``.
        # Two identifier-shaped tokens before the ``=`` is the signature of a
        # declaration; no other C++ statement has that shape. Left alone it
        # ports to ``DeviceInfo info = probe()``, a syntax error whose repair
        # costs the enclosing function.
        ud = re.match(r"^(?:(?:static|const|constexpr|mutable|thread_local|inline|volatile)\s+)*"
                      r"(?P<type>[A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*)"
                      r"(?:\s*[&*]+\s*|\s+)"
                      r"(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<init>.+)$", s, re.S)
        if ud and ud.group("type").split("::")[0] not in _NOT_A_TYPE:
            return [f"{pad}{ud.group('name')} = {self.p.expr(ud.group('init').strip())}"]
        # assignment (not ==/<=/>=/!=)
        m = re.match(r"^([\w.\[\]()]+(?:\.\w+\[\d\])*)\s*(\+=|-=|\*=|/=|\|=|&=|\^=|<<=|>>=|=)\s*(.+)$", s, re.S)
        if m and not re.match(r".*[!<>=]=$", m.group(1)):
            lhs_raw, op, rhs = m.group(1), m.group(2), m.group(3)
            lhs = self.p.expr(lhs_raw)
            # the ctor-init idiom `field = field`: the right side is the
            # parameter, which must keep its bare name
            if op == "=" and lhs.startswith("self.") and rhs.strip() == lhs[5:]:
                return [f"{pad}{lhs} = {lhs[5:]}"]
            # a call to an out-value function returns a tuple: unpack it
            if _calls_out_func(rhs, self.p.out_funcs):
                target = _out_call_target(rhs, _out_index(rhs, self.p.out_funcs)) or "value"
                return [f"{pad}{lhs}, {target} = {self.p.expr(rhs)}"]
            forced = self._drag_behavior_assign(lhs, rhs, pad)
            if forced:
                return forced
            # a call to an ImGui out-param function already assigns itself,
            # unless the pointer was taken at the call site of a *local* var
            rhs_t = self.p.expr(rhs)
            if rhs_t.startswith("_changed, ") and " = " in rhs_t:
                return [f"{pad}{lhs}{rhs_t[len('_changed'):]}"]
            m2 = re.match(r"^(\w+)\[(\d)\]$", lhs)
            if m2 and m2.group(1) in self.p.vec_vars:
                i, var = int(m2.group(2)), m2.group(1)
                if op == "=":
                    if i == 0:
                        return [f"{pad}{var} = ({rhs_t}, {var}[1])"]
                    return [f"{pad}{var} = ({var}[0], {rhs_t})"]
            if op != "=":
                inner = op[:-1]
                # the `+` only exists once the two sides are put together, so
                # a `char buf[32]` appended with `s += buf` is invisible to
                # the expression rules until here
                return [f"{pad}{lhs} = " + self.p.char_array_concat(
                    f"{lhs} {inner} {rhs_t}")]
            return [f"{pad}{lhs} = {rhs_t}"]
        # bare out-value call: unpack into the name C++ wrote through
        if _calls_out_func(s, self.p.out_funcs):
            target = _out_call_target(s, _out_index(s, self.p.out_funcs)) or "value"
            return [f"{pad}_ret, {target} = {self.p.expr(s)}"]
        # a constructor call with a declared name: T name(args); -> name = T(args)
        bm = re.fullmatch(r"((?:const\s+|static\s+|constexpr\s+)*[A-Za-z_][\w:]*)"
                          r"\s+(\w+)\s*\{(.+)\}", s, re.S)
        if bm and "=" not in s and bm.group(1).split()[-1] not in ("struct", "class", "union", "enum"):
            # C++11 brace initialisation: ``ImColor c{...}`` is ``ImColor c(...)``
            s = f"{bm.group(1)} {bm.group(2)}({bm.group(3)})"
        m = re.fullmatch(r"((?:const\s+|static\s+|constexpr\s+)*[A-Za-z_][\w:]*)"
                         r"\s+(\w+)\((.*)\)", s, re.S)
        if m and "=" not in s:
            if m.group(1).split()[-1] in ("ImVec2", "ImVec4"):
                self.p.vec_vars.add(m.group(2))
            rhs = self.p.expr(f"{m.group(1).split()[-1]}({m.group(3)})")
            return [f"{pad}{m.group(2)} = {rhs}"]
        # an untyped declaration the type table does not know: T name;
        m = re.fullmatch(r"(?:[A-Za-z_][\w:]*\s+)+?(\w+)", s)
        if m and "(" not in s and "=" not in s:
            # A local of a plain struct this same file ports -- `DeviceInfo
            # demo;` -- is default-constructible here too. Left as None it
            # took the next line with it (`demo.name = ...`), which reads as
            # a fault in the *assignment* rather than in the declaration
            # three lines up that never made anything.
            typ = s.split()[0].split("::")[-1]
            if typ in self.p.structs:
                return [f"{pad}{m.group(1)} = {typ}()"]
            # Any other type: construct it by name anyway. It is an
            # identifier the module may well have -- cmc's
            # `AcquisitionConfig` is a wrapped C++ struct, in scope because
            # SWIG puts every name at module scope. If it is not in scope
            # the NameError lands *here*, on the declaration, which is where
            # the problem is. `None` moved the failure to the next line that
            # touched it and blamed the assignment instead.
            return [f"{pad}{m.group(1)} = {typ}()  "
                    f"# TODO(autoport): {s.split()[0]} -- verify this constructs"]
        # bare expression / call
        return [f"{pad}{self.p.expr(s)}"]

    def _anonymous_struct(self, m, pad: str) -> list[str]:
        """`struct { T a, b; } name = {1, 2};` -> `name = std.record(a=1, b=2)`."""
        names: list[str] = []
        for part in m.group("fields").split(";"):
            part = part.strip()
            if not part:
                continue
            # `uint8_t r, g, b` -- the type leads, the rest are names
            decls = [d.strip().lstrip("*&") for d in part.split(",")]
            first = decls[0].split()
            names.append(first[-1])
            names.extend(d for d in decls[1:] if d)
        values = [self.p.expr(v.strip())
                  for v in split_args(m.group("init") or "") if v.strip()]
        # An initialiser may name fewer fields than the struct has; the rest
        # are value-initialised in C++, and None here says "not set" rather
        # than inventing a zero for a type this has not been told.
        pairs = [f"{n}={values[i] if i < len(values) else 'None'}"
                 for i, n in enumerate(names)]
        return [f"{pad}{m.group('name')} = std.record({', '.join(pairs)})"]

    def _declaration(self, s: str, pad: str) -> list[str]:
        m = DEC_RE.match(s)
        name, init, size = m.group("name"), m.group("init"), m.group("size")
        if s.startswith("static"):
            self.p.todos.append(
                f"static {name}: C++ keeps it across calls; Python re-initializes")
        if size is not None and not init:
            n = self.p.expr(size) if size else "1"
            # `char buf[32]` is a C string once `snprintf` has written it,
            # and the slots past the NUL are still `None` here -- so record
            # it, and `Porter.char_array_concat` converts where the C++
            # appends it to a string.
            if m.group("type").split()[-1] == "char":
                self.p.char_arrays.add(name)
            return [f"{pad}{name} = [None] * ({n})"]
        if not init:
            t = m.group("type")
            # C++ default-constructs these; the mechanical default is exact
            if "std::string" in t:
                return [f'{pad}{name} = ""  # TODO(autoport): std::string -> str: methods differ (substr, append, c_str)']
            if "std::vector" in t or "ImVector" in t:
                # std.vector() *is* a list, and answers to push_back/resize
                # as well -- so the only thing still needing a hand is the
                # iterator-taking erase, which is what the note now says.
                return [f"{pad}{name} = std.vector()  # TODO(autoport): "
                        f"vector -> list; erase(it) has no Python shape"]
            if "std::map" in t or "std::unordered_map" in t:
                return [f"{pad}{name} = {{}}  # TODO(autoport): map -> dict: methods differ"]
            # Everything else the member scraper knows how to default-
            # construct, defaulted the same way. Two tables that disagree
            # about `std::set` is how a *local* set came out None while a
            # *member* set came out `set()`, and the local then failed on its
            # first insert -- in a function that had nothing else wrong.
            base = t.split("<")[0].strip().split("::")[-1]
            if base in _EMPTY:
                return [f"{pad}{name} = {_EMPTY[base]}"]
            if t == "ImVec2":
                self.p.vec_vars.add(name)
                return [f"{pad}{name} = (0.0, 0.0)"]
            if t == "ImVec4":
                self.p.vec_vars.add(name)
                return [f"{pad}{name} = (0.0, 0.0, 0.0, 0.0)"]
            return [f"{pad}{name} = None  # TODO(autoport): uninitialized {t}"]
        # several declarators: float a = 1, b = 2;
        if "," in init and "(" not in init.split(",")[1] and not init.strip().startswith("ImVec2") \
                and not init.strip().startswith("{"):
            parts = split_args(f"{name} = {init}")
            if len(parts) > 1 and all(re.match(r"\w+\s*=", p) for p in parts):
                return [f"{pad}{self.p.expr(p)}" for p in parts]
        # out-value call initialiser: unpack into the out name
        if _calls_out_func(init, self.p.out_funcs):
            return [f"{pad}{name}, value = {self.p.expr(init)}"]
        forced = self._drag_behavior_assign(name, init.strip().rstrip(";"), pad)
        if forced:
            return forced
        rhs = self.p.expr(init.strip())
        # `std::string row_str = channel_label;`, where `channel_label` is a
        # `char buf[32]`. That ports to a list of 32 slots with `snprintf`
        # filling only the front, so without the conversion the name keeps
        # the padding: the trailing `None`s ride all the way to a text draw
        # and land as `TypeError: ord() expected string of length 1, but
        # NoneType found`, a whole panel away from the declaration. `std.string`
        # stops at the first NUL exactly as `std::string(const char *)` does,
        # and the C++ line is asking for that conversion in so many words, so
        # emitting it is not a guess. A bare name only: any other initialiser
        # is an expression whose own rule already produced a value.
        if ("std::string" in m.group("type")
                and re.fullmatch(r"[A-Za-z_]\w*", init.strip())):
            return [f"{pad}{name} = std.string({rhs})"]
        if rhs.startswith("_changed, ") and " = " in rhs:
            # the value-write call already unpacks: rename its flag
            return [f"{pad}{name}{rhs[len('_changed'):]}"]
        if init.strip().startswith("{"):
            # A braced initialiser on a *declaration* is a container, so the
            # outer group is a list. Only the outer one: `strip("{}")` strips
            # characters rather than one balanced pair, so a table like
            # `{{0,255,0},{255,0,0}}` lost its inner braces too and came out
            # as `[0,255,0},{255,0,0]` -- which does not parse, so the
            # enclosing function was cut. `expr` already reads a nested
            # initialiser as nested lists, so it is left to do that.
            body = init.strip()
            ported = self.p.expr(body)
            rhs = (ported if ported.startswith("[")
                   else "[" + ported[1:-1] + "]" if ported.startswith("(")
                   else "[" + ported + "]")
        if init.strip().startswith("ImVec2"):
            self.p.vec_vars.add(name)
        return [f"{pad}{name} = {rhs}"]


# --------------------------------------------------------------------------- #
# File structure: enums, classes, functions
# --------------------------------------------------------------------------- #


def _calls_out_func(s: str, out_funcs: set[str]) -> bool:
    """Does statement *s* consist of (or assign) a call to an out-value function?"""
    m = re.match(r"^\s*[\w.]*?(\w+)\s*\(", s)
    if not m:
        return False
    return mechanical_name(m.group(1)) in out_funcs



def _out_index(s: str, out_funcs):
    """Which argument(s) of the call in *s* its callee writes through.

    ``out_funcs`` maps a ported function name to those positions, recorded
    where the function was *defined* -- so the caller assigns to the same
    arguments the definition returns, in the same order.
    """
    if not isinstance(out_funcs, dict):
        return None
    # The same match `_calls_out_func` makes, through the same naming rule:
    # this is asked about *raw C++* as often as about ported text, and a
    # pattern that only accepted the ported spelling silently found nothing
    # for `RangeRangeIntersection(...)` -- so the call fell back to "the last
    # bare identifier" and unpacked one of its two out-parameters.
    m = re.match(r"^\s*[\w.]*?(\w+)\s*\(", s)
    return out_funcs.get(mechanical_name(m.group(1))) if m else None


def _out_call_target(s: str, index=None) -> str | None:
    """The C++ variable a write-through call modifies.

    ``Fn(a, b, rounding)`` binds a reference; ``x = Fn(a, &v)`` takes an
    address -- either way the port must hand the written value back to that
    exact name: the last bare-identifier argument (the ``&v`` form first)."""
    depth = 0
    group = None
    start = None
    for k, ch in enumerate(s):
        if ch in "\"'":
            k = _skip_string(s, k)
            continue
        if ch == "(":
            if depth == 0:
                start = k + 1
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0 and start is not None:
                group = (start, k)
                break
    if group is None:
        return None
    args = [a.strip().lstrip("&").strip() for a in split_args(s[group[0]:group[1]])]
    # The declaration says which arguments are written through, and there may
    # be several: `Intersect(a, b, &lo, &hi)` returns `(ok, lo, hi)` and the
    # call site has to unpack all three. Falling back to "the last bare
    # identifier" is for a call whose function this port never saw a
    # definition for.
    idx = [index] if isinstance(index, int) else (index or [])
    picked = [args[i] for i in idx
              if 0 <= i < len(args) and re.fullmatch(r"[A-Za-z_]\w*", args[i])]
    if len(picked) == len(idx) and picked:
        return ", ".join(picked)
    for a in reversed(args):
        if re.fullmatch(r"[A-Za-z_]\w*", a):
            return a
    return None


