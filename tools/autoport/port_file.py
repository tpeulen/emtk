"""Top-level orchestration: C++ sources in, one importable Python module out."""
from __future__ import annotations

import re

from autoport.lex import (rename_reserved, strip_comments,
                          strip_preprocessor, strip_namespaces,
                          statements, split_args, upper_snake, find_matching_brace)
from autoport.tables import PRELUDE
from autoport.expressions import Porter
from autoport.statements import StatementPorter, DEC_RE
from autoport.decls import (FUNC_RE, CLASS_RE, extension_enum_families,
                            named_enum_families, strip_named_enums, enum_members,
                            strip_operator_defs, _unknown_runtime_call,
                            params_to_py, out_value_param, out_param_index,
                            out_params,
                            _rewrite_ctor_init_lists, port_class_fields)
from emtk.im_compat import mechanical_name

#: How an embedded C++ line is marked. A distinctive prefix, so the block can
#: be found again by eye and by grep once a hand starts working through it.
CPP_MARK = "# cpp| "

#: How a *cross-reference* to the C++ is marked. Written as ``path:lo-hi``,
#: which is what an editor's go-to-file and a grep both understand.
REF_MARK = "# cpp: "

#: What to leave behind where a region was cut.
#:
#: ``full`` -- the reference *and* the C++ verbatim. Finishing the port is
#:   reading down the file; the cost is a long comment block.
#: ``ref``  -- the reference alone. Cheaper to read, and it cannot go stale
#:   the way a pasted copy does -- but it only points, so the C++ tree has
#:   to be at hand.
#: ``none`` -- neither.
CPP_MODES = ("full", "ref", "none")

#: An embedded block longer than this is truncated: a 400-line function
#: pasted into a comment buries the code that did port. The tail is never
#: dropped in silence -- the reference above it says where the rest is.
MAX_EMBED_LINES = 120


def _decl_start(text: str, body_start: int) -> int:
    """Back up from a function body's ``{`` to the start of its declaration,
    so the embedded block carries the signature and not only the body."""
    nl = text.rfind("\n", 0, body_start)
    while nl > 0:
        prev = text.rfind("\n", 0, nl)
        line = text[prev + 1:nl].strip()
        # keep walking up through a signature split over several lines
        if line.endswith((",", "(", ":")) or line.startswith(("const", "static")):
            nl = prev
            continue
        break
    return nl + 1


def _cpp_mode(embed_cpp) -> str:
    """Normalise the ``embed_cpp`` argument. ``True``/``False`` still mean
    what they meant before this became a three-way choice."""
    if embed_cpp is True:
        return "full"
    if embed_cpp is False:
        return "none"
    if embed_cpp not in CPP_MODES:
        raise ValueError(f"embed_cpp must be one of {CPP_MODES}, not {embed_cpp!r}")
    return embed_cpp


def _reference(where: tuple) -> str:
    """``path:lo-hi`` for a located block, or "" when it was not located."""
    path, lo, hi = where
    if not path:
        return ""
    return f"{path}:{lo}-{hi}" if hi > lo else f"{path}:{lo}"


def _original_cpp(raw_sources: list, name: str) -> tuple:
    """The function as it was *written*, comments and all.

    The text the porter works on has had its comments and preprocessor
    stripped, which is right for translating and wrong for reading: the
    comments are most of why the C++ does what it does, and they are what a
    hand finishing the port wants first. Found by name in the untouched
    source, and only when the name occurs once -- an overload set has no
    single answer, and a wrong one would be worse than the stripped text.
    """
    leaf = name.rsplit("::", 1)[-1]
    pattern = re.compile(
        r"^[^\S\n]*[\w:<>,&*\s]*?\b"
        + re.escape(name if "::" in name else leaf)
        + r"\s*\([^;{)]*\)[^;{]*\{", re.M)
    found = []
    for path, raw in raw_sources:
        for m in pattern.finditer(raw):
            found.append((path, raw, m))
    # an overload set has no single answer, and a wrong reference sends the
    # reader to code that is not the code that was cut
    if len(found) != 1:
        return "", ("", 0, 0)
    path, raw, m = found[0]
    end = find_matching_brace(raw, raw.index("{", m.end() - 1))
    start = _with_leading_comment(raw, m.start())
    return raw[start:end + 1], (path,
                                raw.count("\n", 0, start) + 1,
                                raw.count("\n", 0, end) + 1)


def _locate_line(raw_sources: list, needle: str) -> tuple:
    """Where a single line of C++ came from, when it occurs exactly once.

    For text taken from the *processed* source -- a dropped operator
    overload -- which has no span to look up by name.
    """
    needle = needle.strip()
    if not needle:
        return ("", 0, 0)
    hits = []
    for path, raw in raw_sources:
        for i, ln in enumerate(raw.splitlines(), 1):
            if ln.strip() == needle:
                hits.append((path, i, i))
    return hits[0] if len(hits) == 1 else ("", 0, 0)


def _with_leading_comment(raw: str, start: int) -> int:
    """Extend *start* back over the comment block above a definition.

    A doxygen block or a run of ``//`` lines immediately above a function is
    the explanation of what it is for, which is the first thing a hand
    finishing the port wants and the last thing that should be left behind.
    """
    pos = raw.rfind("\n", 0, start)
    while pos > 0:
        prev = raw.rfind("\n", 0, pos)
        line = raw[prev + 1:pos].strip()
        if line.startswith("//") or line.startswith("*") or line.startswith("/*"):
            pos = prev
            continue
        if line.endswith("*/"):
            opened = raw.rfind("/*", 0, pos)
            if opened == -1:
                break
            pos = raw.rfind("\n", 0, opened)
            continue
        break
    return pos + 1


def _as_comment(cpp: str, indent: str, squeeze: bool = False) -> list:
    """The C++ as comment lines, dedented and length-capped.

    ``squeeze`` drops blank lines, for a block taken from the *processed*
    text rather than the original file: the statement splitter puts a blank
    between every line it rewrote, and a comment twice as tall as the code
    it quotes reads badly. Blocks read from the source keep their blank
    lines, which are the author's paragraphing.
    """
    lines = [ln.rstrip() for ln in cpp.strip("\n").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    pad = min((len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()),
              default=0)
    lines = [ln[pad:] if ln.strip() else "" for ln in lines]
    if squeeze:
        lines = [ln for ln in lines if ln.strip()]
    dropped = 0
    if len(lines) > MAX_EMBED_LINES:
        dropped = len(lines) - MAX_EMBED_LINES
        lines = lines[:MAX_EMBED_LINES]
    out = [indent + CPP_MARK + ln if ln else indent + CPP_MARK.rstrip()
           for ln in lines]
    if dropped:
        out.append(f"{indent}{CPP_MARK}... {dropped} more line(s) -- see the "
                   f"reference above")
    return out


def _returns_last(body: list) -> bool:
    """Does *body* end on a ``return``, at the function's own indent level?

    A `return` nested inside an `if` does not count: the fall-through path
    still reaches the end.
    """
    for line in reversed(body):
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        return indent == 4 and line.lstrip().startswith("return")
    return False



#: A function *declaration* -- a prototype, ending in `;` rather than a body.
#: C++ puts a default argument on the declaration and forbids repeating it on
#: the definition, so the definition alone never carries one.
_PROTO_RE = re.compile(
    r"^[ \t]*(?:(?:static|inline|virtual|explicit|constexpr|extern|const)\s+)*"
    r"(?:[\w:]+(?:<[^<>]*>)?(?:\s*[*&]+\s*|\s+))?"
    r"(?P<name>[\w:~]+)\s*\((?P<params>[^;{()]*)\)\s*(?:const\s*)?"
    r"(?:noexcept\s*)?(?:override\s*)?;",
    re.M)


def _declared_defaults(text: str) -> dict:
    """``name -> [default or None, ...]``, from the prototypes in *text*.

    C++ says a default argument may appear once, and by convention that is
    the header. Port the *definition* -- which is what has a body, so it is
    what a porter walks -- and every default is silently gone: the ported
    ``save_settings(path)`` then needed an argument its forty callers do not
    pass, and each of them failed at the call rather than at the signature.
    """
    out: dict = {}
    for m in _PROTO_RE.finditer(text):
        name = m.group("name").rsplit("::", 1)[-1]
        params = m.group("params")
        if "=" not in params:
            continue
        out.setdefault(name, [
            (a.split("=", 1)[1].strip() if "=" in a else None)
            for a in split_args(params)])
    return out


def _with_declared_defaults(params: str, declared: list | None) -> str:
    """Put *declared*'s defaults back onto a definition's parameter list.

    By position, not by name: a declaration and its definition are free to
    spell a parameter differently, and the position is what C++ matches on.
    """
    if not declared:
        return params
    args = split_args(params)
    if len(args) != len(declared):
        return params
    merged = [a if ("=" in a or d is None) else f"{a} = {d}"
              for a, d in zip(args, declared)]
    return ", ".join(merged)


def _def_name(line: str) -> str:
    m = re.match(r"\s*def\s+(\w+)\s*\(", line)
    return m.group(1) if m else ""


def port_file(sources: list, module: str, origin: str,
              embed_cpp="full", defines=()) -> str:
    """Port one or more C++ sources (.h together with its .cpp) into one module.

    ``embed_cpp`` says what to leave where a region was cut. The repair loop
    has to cut something to keep the module importable, and what it used to
    cut was the only copy in the file: the reader got a ``pass``, a function
    name, and a trip back to the C++ tree to find out what belonged there.

    * ``"full"`` (default) -- a ``# cpp:`` reference *and* the C++ verbatim
      under ``# cpp|``. Finishing the port is reading down the file.
    * ``"ref"`` -- the reference alone, ``path:lo-hi``. Cheaper to read, and
      it cannot fall out of step with the C++ the way a pasted copy does;
      the trade is that it only points, so the tree has to be at hand.
    * ``"none"`` -- neither.

    ``True`` and ``False`` still mean ``"full"`` and ``"none"``.
    """
    mode = _cpp_mode(embed_cpp)
    texts = []
    raw_sources: list = []
    macro_names: set = set()
    for src in sources:
        t = src.read_text()
        raw_sources.append((str(src), t))
        t = t.replace("\\\n", " ")   # a multi-line macro definition becomes one line
        macro_names.update(re.findall(r"#define\s+([A-Za-z_]\w*)\s*\(", t))
        t = strip_comments(t)
        t = re.sub(r"\b(?:NOTIFY_INLINE|NOTIFY_API|IMGUI_API|IMGUI_IMPL_API)\b", "", t)
        # `defines` says which `#ifdef`s the C++ is built with; anything
        # else is dead code there and must be dead here too.
        t = strip_preprocessor(t, defines)
        t = re.sub(r"\btemplate\s*<[^<>]*>", " ", t)   # the port is generic
        t = strip_namespaces(t)
        # Reserved identifiers, renamed once for the whole file. Doing it here
        # rather than at each place a name is emitted means every later pass
        # -- declarations, parameters, fields, expressions -- sees a name it
        # can already use, and none of them has to know about the problem.
        # `raw_sources` above keeps the untouched text, so the C++ embedded
        # beside a cut region is still the C++ as written.
        t = rename_reserved(t)
        texts.append(t)
    text = "\n".join(statements("\n".join(texts)))

    families = extension_enum_families(text)
    named_fams = named_enum_families(text)
    # cut the named enum bodies before class scraping mistakes them for one
    text = strip_named_enums(text)
    porter = Porter()
    porter.module_enums = {fam: py for fam, py in families.items()}
    porter.macros = macro_names

    # file-level constants (from #define NAME value) and file-level variables
    # go above everything: C++ globals are Python module globals. Only
    # statements *outside* every function and class body qualify -- a local
    # with the same shape stays a local.
    covered: list = []
    for m in FUNC_RE.finditer(text):
        covered.append((m.start(), find_matching_brace(text, m.end() - 1)))
    for m in CLASS_RE.finditer(text):
        covered.append((m.start(), find_matching_brace(text, m.end() - 1)))

    def at_file_level(pos: int) -> bool:
        return not any(a <= pos < b for a, b in covered)

    global_consts: list = []
    kept: list = []
    offset = 0
    for s in text.splitlines(keepends=True):
        line_pos = offset
        offset += len(s)
        s2 = s.strip()
        m = re.match(r"^(?:static\s+)?const\s+(\w+)\s*=\s*(.+)$", s2)
        if m and at_file_level(line_pos):
            global_consts.append((m.group(1), m.group(2).rstrip(";")))
            continue
        # a file-level constant with a ctor/brace initialiser and no ``=``:
        # ``static const ImColor white{1.f, 1.f, 1.f, 1.f};`` -- but never a
        # function prototype, which has the same shape and no const
        gm = re.fullmatch(r"(?:static\s+)?(?:const\s+|constexpr\s+)+"
                          r"([A-Za-z_][\w:]*)\s*\*?\s*(\w+)\s*[({]([^;{}]*)[)}]\s*;", s2)
        if (gm and gm.group(1) != "void" and at_file_level(line_pos)
                and not re.search(r"\b(?:const|unsigned|signed|bool|float|double|int|long|short|char|size_t|void)\b"
                                  r"|\w+\s*(?:&|\*)\s*\w", gm.group(3))):
            value = porter.expr(f"{gm.group(1)}({gm.group(3)})")
            if _unknown_runtime_call(value):
                value = ("None  # TODO(autoport): initializer calls the C++ "
                         "runtime, default it by hand: " + value)
            global_consts.append((gm.group(2), value))
            continue
        if DEC_RE.match(s2) and "(" not in s2 and at_file_level(line_pos):
            dm = DEC_RE.match(s2)
            init = dm.group("init")
            value = porter.expr(init.strip().rstrip(";")) if init else "None"
            if init is None:
                value += "  # TODO(autoport): default the fields this C++ global needs"
            elif "(" in value and _unknown_runtime_call(value):
                # ``static string p = filesystem::current_path().string();``
                # runs at import on this side: not something the port can do
                value = ("None  # TODO(autoport): initializer calls the C++ "
                         "runtime, default it by hand: " + value)
            global_consts.append((dm.group("name"), value))
            continue
        kept.append(s)
    text = "\n".join(kept)

    # class fields first: bare names in methods become self.x
    class_bodies = [(m.group(1), m.end() - 1, find_matching_brace(text, m.end() - 1))
                    for m in CLASS_RE.finditer(text)]
    # A plain aggregate -- `struct DeviceInfo { std::string name; ... };`, and
    # every nested `FCSCurve`/`TracePlotSettings` -- declares no constructor,
    # so on this side it is default-constructible and a member of one can be
    # made rather than left None. Anything that declares a constructor cannot:
    # the port has no idea what to pass it.
    plain_structs = {cls for cls, a, b in class_bodies
                     if not re.search(rf"\b{re.escape(cls)}\s*\(", text[a + 1:b])}
    class_fields: dict = {}
    for cls, body_start, body_end in class_bodies:
        class_fields[cls] = port_class_fields(text[body_start + 1:body_end],
                                              porter, plain_structs)

    # C++ constructor with an initialiser list:
    # ``knob(a, b) : base(a), hovered(b) {`` -> the list becomes assignments
    text = _rewrite_ctor_init_lists(text)
    # operator overloads and destructors have no Python shape: ``a + b`` on
    # ImVec2 is component-wise by convention here, ``~X()`` has no hook --
    # both are dropped, visibly, where the C++ declared them
    text, dropped_operators = strip_operator_defs(text)
    #: ported free function -> the positions of the arguments it writes
    #: through, in declaration order
    out_funcs: dict = {}
    declared_defaults = _declared_defaults(text)
    file_todos: list = []
    dtor_spans: list = []
    func_spans = []
    class_spans = [(m.group(1), m.end() - 1, find_matching_brace(text, m.end() - 1))
                   for m in CLASS_RE.finditer(text)]

    def enclosing_class(pos: int):
        best = None
        for cls, s0, s1 in class_spans:
            if s0 < pos < s1:
                if best is None or (s1 - s0) < (best[2] - best[1]):
                    best = (cls, s0, s1)
        return best[0] if best else None

    for m in FUNC_RE.finditer(text):
        ret = (m.group("ret") or "").strip()
        name, params = m.group("name"), m.group("params")
        # ``~X()`` inline *and* ``X::~X()`` out of line: the second is the one
        # a .cpp actually contains, and its leading character is ``X``, not
        # ``~``, so a startswith test on the whole name misses it and emits
        # ``def ~x():`` -- a syntax error that costs the next function too.
        if name.rsplit("::", 1)[-1].startswith("~"):
            file_todos.append(
                f"destructor {name}() dropped: Python has no deterministic "
                f"destruction. What it released is the C++ below -- if any of "
                f"it matters, it belongs in a close() or a context manager.")
            dtor_spans.append(name)
            continue
        body_start = m.end() - 1
        body_end = find_matching_brace(text, body_start)
        # The header's defaults, put back: C++ allows a default argument on
        # the *declaration* only, and this is the definition.
        params = _with_declared_defaults(
            params, declared_defaults.get(name.rsplit("::", 1)[-1]))
        func_spans.append((ret, name, params, body_start, body_end,
                           enclosing_class(m.start())))
        if out_value_param(params)[0] is not None and "::" not in name \
                and enclosing_class(m.start()) is None:
            # *Which* arguments it writes through, in order -- the same order
            # the definition returns them in, so the call site unpacks into
            # the variables the C++ passed addresses of.
            out_funcs[mechanical_name(name)] = [i for i, _n in out_params(params)]

    #: class -> the names of its methods, in the C++ spelling *and* the
    #: Python one, so a call is caught whichever the surrounding rules have
    #: already rewritten it to.
    class_methods: dict = {}
    for _ret, fname, _params, fstart, _fend, fowner in func_spans:
        fcls = fowner
        if fcls is None and "::" in fname:
            maybe = fname.rsplit("::", 1)[0]
            if maybe in class_fields:
                fcls = maybe
        if fcls is None:
            continue
        leaf = fname.rsplit("::", 1)[-1]
        class_methods.setdefault(fcls, set()).update({leaf, mechanical_name(leaf)})

    # pass 2: translate. later definitions win (a .h inline, then the .cpp)
    free_defs: list = []
    class_defs: dict = {cls: [] for cls in class_fields}

    #: emitted Python name -> (C++ source, "path:lo-hi"). Keyed by the ``def``
    #: line's name because that is all the repair loop, which works on
    #: generated text, has left to look anything up by.
    cpp_source: dict = {}

    for ret, name, params, body_start, body_end, owner in func_spans:
        body_lines = text[body_start + 1:body_end].splitlines()
        found, where = _original_cpp(raw_sources, name)
        # the stripped slice is the fallback: it is always exactly the code
        # that was ported, where the raw lookup can be ambiguous
        cpp_here = (found or text[_decl_start(text, body_start):body_end + 1],
                    _reference(where))

        local = Porter()
        local.module_enums = porter.module_enums
        local.helpers = porter.helpers          # shared so the prelude is complete
        local.out_funcs = out_funcs
        local.structs = plain_structs
        local.macros = porter.macros

        cls = owner
        if cls is None and "::" in name:
            maybe_cls, _ = name.rsplit("::", 1)
            if maybe_cls in class_fields:
                cls = maybe_cls
        if cls is not None:
            meth = name.rsplit("::", 1)[-1]
            local.fields = {f for f, _ in class_fields.get(cls, [])}
            local.methods = class_methods.get(cls, set()) - {meth}
            is_ctor = meth == cls or meth == cls.strip("~")
            pyname = mechanical_name(meth)
            if is_ctor:
                n_ctor = sum(1 for n, _ in class_defs.get(cls, []) if n.startswith("__init__"))
                pyname = "__init__" if n_ctor == 0 else f"__init__{n_ctor + 1}"
            names = params_to_py(params, True, porter=local)
            body = StatementPorter(local).port(body_lines)
            if is_ctor:
                # one call, not the assignments inline: if the repair loop
                # has to cut this constructor, the fields must not go with
                # it. See `_init_fields` below.
                body = ["    self._init_fields()"] + body
            if not body:
                # four spaces, like every other body line: the class emitter
                # indents this block once more, and eight put the `pass` two
                # levels under its own docstring -- `IndentationError:
                # unexpected indent`, which the repair loop answered by
                # cutting the method. A C++ body that is only a comment is
                # commoner than it looks, and `update_config_from_ui() {}`
                # cost the whole window its render.
                body = ["    pass"]
            class_defs.setdefault(cls, [])
            # later definitions win; keep first-seen order
            if any(d[0] == pyname for d in class_defs[cls]) and not is_ctor:
                # C++ overloads on parameter type; Python has one name per
                # class, so only one of them can survive. Which is a real
                # loss and used to be a silent one -- `set_channel_color(ch,
                # r, g, b)` vanished behind `set_channel_color(ch, col)` and
                # the caller got a TypeError about argument counts with
                # nothing to say why. Say it here, at the definition.
                file_todos.append(
                    f"{cls}::{meth} overloads: only the last is emitted "
                    f"({pyname}({', '.join(names)})). Give the others their "
                    f"own names, or dispatch on len(args) in a subclass.")
            class_defs[cls] = [d for d in class_defs[cls] if d[0] != pyname]
            cpp_source.setdefault(pyname, cpp_here)
            class_defs[cls].append((pyname, [
                f"def {pyname}({', '.join(names)}):", f'    """{name}()."""'
            ] + [f"    # TODO(autoport): {t}" for t in local.todos] + body + [""]))
        else:
            local.out_src_name, local.out_extras = out_value_param(params)
            # More than one out-parameter: carry them all, under their own
            # names. The rename to `value` exists only because ImGui spells
            # its single one `p_value`; with several there is no one name to
            # rename *to*, and dropping the rest used to mean the definition
            # returned the first while the call site assigned the last.
            outs = out_params(params)
            local.out_names = [n for _i, n in outs]
            if len(outs) > 1:
                local.out_src_name = None
                local.out_extras = []
            local.func_name = name
            for raw in split_args(params):
                if "ImVec2" in raw or "ImVec4" in raw:
                    pm = re.search(r"(\w+)\s*$", raw.strip())
                    if pm:
                        local.vec_vars.add(pm.group(1))
            ret_base = ret.split()[-1] if ret else ""
            if ret_base in class_fields:
                local.ret_cls = ret_base
            py_free = mechanical_name(name.split("::")[-1])
            names = params_to_py(params, False, local.out_src_name, local)
            body = StatementPorter(local).port(body_lines)
            if not body:
                body = ["    pass"]
            # A function with an out-parameter returns it. The `return;`
            # statements inside were rewritten to carry it, but a C++ `void`
            # function is allowed to just *end* -- and falling off the end of
            # this one returned None, so the caller's
            # `_ret, value = f(...)` unpacked None and raised, in a function
            # that had otherwise ported perfectly.
            if local.out_names and not _returns_last(body):
                # One out-parameter is spelled `value` on this side --
                # params_to_py renames it and every read of it was rewritten
                # to match. Several keep their own names.
                carried = ("value" if local.out_src_name
                           else ", ".join(local.out_names))
                body += [f"    return None, {carried}"]
            lines = [f"def {py_free}({', '.join(names)}):",
                     f'    """{name}()."""']
            # every note the translation gathered, visible at the def site
            lines += [f"    # TODO(autoport): {t}" for t in local.todos]
            lines += body + [""]
            cpp_source.setdefault(py_free, cpp_here)
            free_defs.append((py_free, lines))
    # -- assemble ----------------------------------------------------------- #
    free_names = {name for name, _ in free_defs}
    out: list = [
        f'"""{module}: auto-ported from {", ".join(s.name for s in sources)}',
        f"({origin}) by tools/autoport.py.",
        "",
        "A mechanical port of Dear ImGui C++ to emtk. Lines flagged",
        "TODO(autoport) need a hand; everything else is the C++ under the",
        "naming rules in tools/autoport.py.",
        "",
        "A `# cpp:` line under a TODO says where in the C++ that region came",
        "from, as path:first-last. The `# cpp|` lines under it are that C++,",
        "kept verbatim so finishing the port is reading down this file rather",
        "than going back to the tree. `--embed-cpp ref` keeps the references",
        "and drops the copies; `none` keeps neither.",
        '"""',
        "import math",
        "",
        "import emtk.im as im",
    ]

    # An ImGui *extension* needs `im` and little else. An *application* is
    # written against the standard library and, if it plots, against ImPlot --
    # on nearly every screen. Emitted only when the source names them, so a
    # widget file stays as small as it was.
    if re.search(r"\bImPlot\s*::", text) or re.search(r"\bImPlot\w*_", text):
        out += ["import emtk.implot as ImPlot",
                "from emtk.implot import *  # the ImPlotFlags_/ImAxis_ spellings"]
    if re.search(r"\bstd\s*::|\bstatic_cast\b|\bsizeof\b|\bprintf\b"
                 r"|\bmem(?:set|cpy)\b|\bstrn?cpy\b|\bFLT_(?:MIN|MAX)\b", text):
        out += ["from emtk.cpp_compat import *  # std::, the casts, printf"]

    if re.search(r"\bIM_PI\b", text):
        # imgui_internal.h ships this constant; the port carries it, named
        out += ["", "IM_PI = math.pi"]

    if global_consts:
        out.append("")
        for name_c, value_c in global_consts:
            out.append(f"{name_c} = {porter.expr(value_c)}")
        out.append("")

    if families or named_fams:
        out += ["", "from enum import IntFlag", ""]
        for fam, py in families.items():
            out.append(f"class {py}(IntFlag):")
            out.append(f'    """{fam}, from {sources[0].name}."""')
            out.append("    NONE = 0")
            seen_members = set()
            i = 0
            for mem in enum_members(text, fam):
                name_m = upper_snake(mem)
                if name_m in seen_members or name_m == "NONE":
                    continue
                seen_members.add(name_m)
                out.append(f"    {name_m} = {1 << i}")
                i += 1
            out.append("")

    # named enums with unprefixed members (``enum class FileDialogType``):
    # their references flow through the CamelCase->snake member rule, so the
    # members are emitted spelled the same way, values 0.. as in the C++
    taken_names = {py for _, py in families.items()}
    taken_names |= {c.capitalize() if c in free_names else c for c in class_defs}
    for fam, members in named_fams.items():
        if fam in taken_names:
            file_todos.append(f"enum {fam} collides with a ported name: not emitted")
            continue
        taken_names.add(fam)
        out += ["", f"class {fam}(IntFlag):",
                f'    """{fam}, from {sources[0].name}."""']
        seen_members = set()
        for i, mem in enumerate(members):
            name_m = mechanical_name(mem)
            if name_m in seen_members:
                continue
            seen_members.add(name_m)
            out.append(f"    {name_m} = {i}")
        out.append("")

    if porter.helpers:
        out.append("")
        for h in sorted(porter.helpers):
            out.append(PRELUDE[h])
            out.append("")

    free_names = {name for name, _ in free_defs}
    for cls, methods in class_defs.items():
        # A struct with only data -- `DeviceInfo`, `GuiStartupOptions`, the
        # nested `FCSCurve` -- has no methods, and skipping on that alone
        # meant its fields were scraped, used to qualify every reference to
        # them, and then never emitted: the class the rest of the port names
        # simply did not exist.
        if not methods and not class_fields.get(cls):
            continue
        # a struct whose name a public function shares (knob/Knob): the class
        # takes the capitalised spelling so both are reachable
        label_cls = cls.capitalize() if cls in free_names else cls
        doc = "    " + chr(34) * 3 + label_cls + ", from " + sources[0].name + "." + chr(34) * 3
        out += ["", f"class {label_cls}:", doc, ""]

        # C++ initialises members where they are *declared*; Python has
        # nowhere to put that but a method. Its own method, called by every
        # constructor, rather than assignments inlined into one:
        #
        #   * a class with no C++ constructor still gets its fields, and
        #   * a constructor the repair loop has to cut still gets them too,
        #     because the call survives where the body did not.
        #
        # Inlined, a single unportable line in a constructor took all 114 of
        # a class's fields with it and every method that read one failed.
        declared = class_fields.get(cls, [])
        if declared:
            init = ["def _init_fields(self):",
                    '    """Members, at the values the C++ declares them with.',
                    "",
                    "    Called from every constructor. Separate from them so",
                    "    that a constructor which needed a hand does not take",
                    "    the fields with it.",
                    '    """']
            # Every line is checked before it goes in. `_init_fields` is the
            # one method that must never need repairing: if the repair loop
            # cuts *it*, every field in the class goes and every method that
            # reads one fails. A default that does not port -- a multi-line
            # brace initialiser, a constructor call -- becomes None with the
            # C++ named beside it, which is a field that exists and is
            # visibly wrong rather than a class that has none.
            for f, v in declared:
                line = f"    self.{f} = {v}"
                try:
                    compile(line.strip(), "<field>", "exec")
                except SyntaxError:
                    one = " ".join(str(v).split())[:60]
                    init.append(f"    self.{f} = None  # TODO(autoport): "
                                f"default did not port: {one}")
                else:
                    init.append(line)
            out += [("    " + ln) if ln.strip() else "" for ln in init]
            out.append("")
            if not any(n.startswith("__init__") for n, _ in methods):
                out += ["    def __init__(self):",
                        '        """Synthesised: the C++ declares no constructor,',
                        '        so the declared members are the whole of it."""',
                        "        self._init_fields()", ""]

        for pyname, lines in methods:
            out += [("    " + ln) if ln.strip() else "" for ln in lines]
            out.append("")

    for _, lines in free_defs:
        out += lines

    if file_todos:
        out += [""] + ["# TODO(autoport): " + t for t in file_todos]
    if dropped_operators:
        out += ["", "# TODO(autoport): operator overload(s) dropped: Python does "
                    "not overload per-type, so `a + b` on a vector was rewritten "
                    "at each use site instead. That rewrite is a guess about what "
                    "the operator did -- here is what it actually did."]
        if mode != "none":
            for op in dropped_operators:
                ref = _reference(_locate_line(raw_sources, op.splitlines()[0]))
                if ref:
                    out.append(REF_MARK + ref)
                if mode == "full":
                    out += _as_comment(op, "", squeeze=True)
    if mode != "none":
        for dname in dtor_spans:
            cpp, where = _original_cpp(raw_sources, dname)
            ref = _reference(where)
            if ref:
                out += ["", REF_MARK + ref]
            if mode == "full" and cpp:
                out += _as_comment(cpp, "")

    text_out = "\n".join(out).rstrip() + "\n"
    text_out = re.sub(r"\n{3,}", "\n\n", text_out)

    # ctor calls of a renamed class follow the rename
    for cls in class_defs:
        label_cls = cls.capitalize() if cls in free_names else cls
        if label_cls != cls:
            text_out = re.sub(rf"(?<!def )\b{re.escape(cls)}\(", label_cls + "(", text_out)

    # the output always imports: a line the rules mangled is commented out
    # under a TODO(autoport) marker, never left to break the module. When
    # marking the reported line does not move the error, the damage spans
    # lines (an unbalanced bracket, a stray quote) -- then the enclosing
    # def/region is cut down to a ``pass`` instead of sandpapered forever.
    last_error = None
    stuck = {}
    for _ in range(500):
        try:
            compile(text_out, module, "exec")
            break
        except (SyntaxError, IndentationError) as e:
            # count by message, not line: every marker inserted above shifts
            # the reported lineno, but a message that will not go away means
            # the damage spans lines and the region must go
            stuck[e.msg] = stuck.get(e.msg, 0) + 1
            lines = text_out.splitlines()
            ln = min(max(0, (e.lineno or 1) - 1), len(lines) - 1)
            marker = "# TODO(autoport): hand-translate (the rules mangled this line): "
            line = lines[ln]
            if stuck[e.msg] >= 3:
                start = ln
                base = len(line) - len(line.lstrip())
                while start > 0:
                    prev = lines[start - 1]
                    pind = len(prev) - len(prev.lstrip())
                    if prev.lstrip().startswith(("def ", "class ")) and pind < base:
                        start -= 1
                        break
                    if pind == 0 and prev.strip() and not prev.lstrip().startswith("#"):
                        start -= 1
                        break
                    start -= 1
                endg = ln + 1
                sind = len(lines[start]) - len(lines[start].lstrip())
                while endg < len(lines):
                    el = lines[endg]
                    if el.strip() and len(el) - len(el.lstrip()) <= sind:
                        break
                    endg += 1
                note = lines[start].strip() or "(region)"
                head = lines[start] if lines[start].lstrip().startswith("def ") else ""
                cut = [
                    " " * sind + marker + "this region resisted the mechanical port: " + note[:70],
                ]
                # The C++ this region was ported from, so the only copy in
                # the file is not the one being deleted. Without it the
                # reader gets a function name and a `pass`, and has to go
                # back to the C++ tree to find out what belonged there.
                cpp, ref = cpp_source.get(_def_name(head), ("", ""))
                if mode != "none" and ref:
                    cut.append(" " * sind + REF_MARK + ref)
                if mode == "full" and cpp:
                    # not CPP_MARK: a grep for `# cpp| ` should return the
                    # source and nothing else
                    cut.append(" " * sind + "# --- the C++ it came from "
                                            "(hand-translate below) ---")
                    cut += _as_comment(cpp, " " * sind)
                # A cut *constructor* still owes its object its fields. It
                # needs to know nothing about them to do that -- the call is
                # the same line whatever they are, which is exactly why the
                # assignments live in their own method.
                if _def_name(head).startswith("__init__"):
                    cut.append(" " * sind + "    self._init_fields()")
                else:
                    cut.append(" " * sind + "pass")
                lines[start:endg] = cut
                stuck[e.msg] = 0
                text_out = "\n".join(lines)
                continue
            if line.lstrip().startswith(marker):
                # already rescued once: collapse the pile of markers to one
                indent = line[:len(line) - len(line.lstrip())]
                lines[ln] = indent + "pass  " + marker + "pass"
            else:
                indent = line[:len(line) - len(line.lstrip())]
                lines[ln] = marker + line
                lines.insert(ln + 1, indent + "pass  # TODO(autoport): body of the line above")
            text_out = "\n".join(lines)
    else:
        # the cap never converges: comment the remainder of the file so the
        # guarantee still holds and the damage is plainly visible
        lines = text_out.splitlines()
        for i, l in enumerate(lines):
            if l.strip() and not l.lstrip().startswith("#"):
                lines[i] = "# TODO(autoport): rescue gave up: " + l
        text_out = "\n".join(lines)
    return text_out


