"""Declaration-level scanning: enum families, fields, params, ctor lists."""
from __future__ import annotations

import re

from autoport.lex import (find_matching_brace, statements, split_args,
                          strip_comments, _skip_string)
from autoport.tables import ENUM_FAMILIES, CPP_TYPES, TYPE_WORDS, PRELUDE
from autoport.expressions import Porter  # type annotations only

FUNC_RE = re.compile(
    # `const` before the return type, and `&`/`*` after it: `const DataPoint
    # &ring_at(size_t i) {` is a method, and a pattern that cannot see the
    # `&` does not merely misparse it -- the method is never found, so it is
    # never ported *and* never counted as one of the class's own, so every
    # call to it comes out unqualified too.
    r"^[ \t]*(?:(?:static|inline|virtual|explicit|constexpr|extern|const)\s+)*"
    # the separator carries the `*`/`&`, because `DataPoint &ring_at` has no
    # space after the `&` -- the same shape DEC_RE uses for a declaration
    r"(?:(?P<ret>[\w:]+(?:<[^<>]*>)?)(?:\s*[*&]+\s*|\s+))?"
    r"(?P<name>(?!if\b|for\b|while\b|switch\b|return\b|case\b|default\b|else\b|do\b|sizeof\b)[\w:~]+)\s*"
    r"\((?P<params>[^;{]*)\)\s*(?:const\s*)?(?:noexcept\s*)?\{",
    re.S | re.M)

CLASS_RE = re.compile(r"(?:class|struct)\s+(?:[A-Z_]+\s+)?(\w+)\s*(?::[^{]*)?\{")
ENUM_RE = re.compile(r"enum(?:\s+\w+)?\s*(?::\s*\w+)?\s*\{([^}]*)\}", re.S)
#: A member declaration. The type is *any* identifier-shaped token sequence,
#: not only one CPP_TYPES knows: an application's members are its own types
#: (`StatsSnapshot current_stats_;`, `AcquisitionConfig config_;`) and a
#: field the scraper misses is a field the port does not qualify with
#: `self.` -- so the method reads a module global that does not exist and
#: NameErrors the first time it runs.
FIELD_RE = re.compile(
    r"^(?:(?:static|const|constexpr|mutable|inline|volatile|thread_local)\s+)*"
    # ``unsigned int texture_id_`` is two words before the name, and a
    # pattern that reads only one took `int` for the name and then failed on
    # the rest -- so the field was never found, and every use of it came out
    # unqualified. The run is captured whole because the *last* word is the
    # one that says what a default-construction means (`unsigned long long`
    # is an integer, `long double` is not).
    r"(?P<words>(?:(?:unsigned|signed|long|short)\s+)*)"
    r"(?P<type>[A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*)"
    r"(?P<ptr>\s*[*&]+\s*|\s+)"
    # DOTALL: a table of colours is written over several lines, and an
    # initialiser the pattern cannot see makes the whole declaration fail to
    # match -- so the member is not a member, and every use of it comes out
    # unqualified.
    r"(?P<name>\w+)\s*(?:\[(?P<extent>[^\]]*)\])?"
    # `= x` and `{x}` are both default member initialisers, and reading only
    # the first lost `std::atomic<bool> stop_requested_{false};` entirely --
    # the member came out None and the first `if not stop_requested_` read
    # the wrong way round.
    r"\s*(?:=\s*(?P<init>.+?)|\{(?P<binit>.*)\})?\s*;$", re.S)



def extension_enum_families(text: str) -> dict[str, str]:
    """``ImGui<ToggleFlags>_X`` families the extension defines itself."""
    fams: dict[str, str] = {}
    for m in ENUM_RE.finditer(text):
        for mm in re.finditer(r"\b(ImGui[A-Za-z]+)_", m.group(1)):
            fam = mm.group(1)
            if fam not in ENUM_FAMILIES:
                fams[fam] = fam[len("ImGui"):]
    return fams


NAMED_ENUM_RE = re.compile(
    r"enum(?:\s+class)?\s+(?P<name>\w+)(?:\s*:\s*[\w:]+)?\s*\{(?P<body>[^}]*)\}",
    re.S)


def named_enum_families(text: str) -> dict[str, list[str]]:
    """``enum class FileDialogType { OpenFile, SelectFolder }`` -- a named
    enum whose members carry no prefix: the family is the enum's own name.
    Prefixed (``ImGuiToggleFlags_...``) and ImGui-named enums belong to the
    other collector, so they are skipped here."""
    fams: dict[str, list[str]] = {}
    for m in NAMED_ENUM_RE.finditer(text):
        name, body = m.group("name"), m.group("body")
        if name.startswith("ImGui") or name in fams or name in ENUM_FAMILIES:
            continue
        members = []
        for part in body.split(","):
            mm = re.match(r"\s*([A-Za-z_]\w*)", part)
            if mm and mm.group(1) not in members:
                members.append(mm.group(1))
        if members:
            fams[name] = members
    return fams


def strip_named_enums(text: str) -> str:
    """Cut named enum declarations out of *text*: their members ride the
    emitted IntFlag classes, and a leftover ``enum class X { }`` body would
    be scraped as class fields and shadow the family name."""
    while True:
        m = NAMED_ENUM_RE.search(text)
        if not m:
            return text
        text = text[:m.start()] + "/* autoport: enum collected */" + text[m.end():]


def enum_members(text: str, fam: str) -> list[str]:
    seen = []
    for m in ENUM_RE.finditer(text):
        for mm in re.finditer(rf"\b{fam}_([A-Za-z0-9]+)", m.group(1)):
            if mm.group(1) not in seen:
                seen.append(mm.group(1))
    return seen


OPERATOR_DEF_RE = re.compile(
    r"^[ \t]*(?:(?:static|inline|constexpr|virtual)\s+)*"
    r"(?:[\w:]+(?:<[^<>]*>)?(?:\s*\*)*?\s+)?"
    r"operator\s*(?:\(\s*\)|\[\s*\]|[^\s({;])+"
    r"\s*\([^;{]*\)\s*(?:const\s*)?(?:noexcept\s*)?\{",
    re.M)


def strip_operator_defs(text: str) -> str:
    """Remove ``ImVec2 operator+(...)`` / ``bool operator<(...)`` definitions.

    Python does not overload operators per-type; the port reads ``a + b``
    on vectors as the component-wise tuple the C++ meant (rewritten at the
    use sites), so the definitions themselves only get in the way.

    Returns ``(text, dropped)`` -- the definitions come back so the caller
    can put them in the module as a comment. The use-site rewrite is a
    *guess* about what the operator did, and checking that guess needs the
    operator.
    """
    dropped: list = []
    while True:
        m = OPERATOR_DEF_RE.search(text)
        if not m:
            return text, dropped
        end = find_matching_brace(text, m.end() - 1)
        dropped.append(text[m.start():end + 1].strip())
        text = text[:m.start()] + "/* autoport: operator overload dropped */" + text[end + 1:]



_BUILTIN_CALL_HEADS = {
    "im", "math", "str", "int", "float", "bool", "len", "abs", "min", "max",
    "round", "range", "tuple", "list", "dict", "set", "sorted", "chr", "ord",
    "sum", "enumerate", "zip", "bytes", "bytearray", "hash", "repr", "type",
}


def _unknown_runtime_call(value: str) -> bool:
    """True when *value* (already ported) calls something that is neither a
    builtin, cmtk, math, nor a prelude helper -- a C++ runtime call that
    would NameError the moment the module is imported."""
    for m in re.finditer(r"([A-Za-z_]\w*(?:\.\w+)*)\s*\(", value):
        head = m.group(1).split(".")[0]
        if head not in _BUILTIN_CALL_HEADS and "im_" + head not in PRELUDE:
            return True
    return False



def params_to_py(params: str, is_method: bool, out_src: str | None = None,
                 porter: "Porter | None" = None) -> list[str]:
    names: list[str] = []
    for raw in split_args(params):
        # C's varargs. `static void log_debug(const char *fmt, ...)` is a
        # printf-style helper, and `...` came out as a *required* parameter
        # named `_argN` -- so every existing call, which passes only the
        # format, raised "missing 1 required positional argument".
        if raw.strip() == "...":
            names.append("*args")
            continue
        p = re.sub(r"\b(const|volatile)\b", "", raw)
        default = None
        if "=" in p:
            p, default = p.split("=", 1)
            p = p.strip()
            default = default.strip()
        toks = re.findall(r"[A-Za-z_]\w*", p)
        name = None
        for tok in reversed(toks):
            if tok in TYPE_WORDS or tok in ("ImGui", "std"):
                continue
            name = tok
            break
        if name is None:
            name = f"_arg{len(names)}"
        if out_src and name == out_src:
            name = "value"
        if default is not None and porter is not None:
            names.append(f"{name}={porter.expr(default)}")
        else:
            names.append(name)
    if is_method:
        names = ["self"] + names
    return names


_OUT_HINT_RE = re.compile(r"^(?:p_\w+|out_?\w*|\w+_out|value)$")
_SCALAR_TYPES_RE = re.compile(
    r"^(?:float|double|bool|int|unsigned|long|short|char|size_t|ImS8|ImU8"
    r"|ImS32|ImU32|ImS64|ImU64)$")


def out_value_param(params: str) -> tuple[str | None, list[str]]:
    """The parameter a C++ function writes its result through, if any.

    ``T* p_value`` (imgui's spelling), ``T* out_...`` / ``..._out`` (the
    common extension spellings), or a scalar ``T& v`` reference: Python
    returns ``(original_return, value)`` and call sites unpack. Const
    pointers and draw-list/IO/style references are inputs, not out-values.
    A second candidate cannot ride the one-value tuple: it comes back as
    *extras* so the port can flag it for a hand."""
    found: list[str] = []
    for raw in split_args(params):
        p = raw.strip()
        m = re.match(r"^(?:const\s+)?([\w:]+)\s*([*&])\s*(\w+)$", p)
        if not m:
            continue
        typ, kind, name = m.groups()
        if p.startswith("const") or typ in ("ImDrawList", "ImGuiIO",
                                            "ImGuiStyle", "ImFont", "ImVector"):
            continue
        if kind == "*":
            # A non-const pointer to a *scalar* is an out-parameter whatever
            # it is called: an input of scalar type is passed by value, so
            # the pointer is there to be written through. Requiring one of
            # ImGui's spellings (`p_value`, `out_*`) worked for extensions
            # and not for applications, which name theirs after what they
            # mean -- `DrawSplitter(..., float *size1, float *size2, ...)`
            # was not recognised as writing anything, so a splitter dragged
            # and nothing moved.
            if _OUT_HINT_RE.match(name) or _SCALAR_TYPES_RE.match(typ):
                found.append(name)
        elif _SCALAR_TYPES_RE.match(typ):
            found.append(name)
    if not found:
        return None, []
    return found[0], found[1:]


def out_params(params: str) -> list[tuple[int, str]]:
    """*Every* parameter a C++ function writes its result through.

    ``(position, name)`` in declaration order, which is the order the Python
    tuple carries them in and the order the call site unpacks them.

    :func:`out_value_param` answers the same question for the one-out case
    the ImGui widget tables assume. This is for application code, where a
    helper writing through three references at once is ordinary -- and where
    carrying only the first was not merely lossy: the call site guessed a
    different one, so a size ended up in a variable meant for a config
    object and the error surfaced a call later, inside SWIG.
    """
    wanted = set(sum(([n] for n in _all_out_names(params)), []))
    found: list[tuple[int, str]] = []
    for i, raw in enumerate(split_args(params)):
        m = re.search(r"(\w+)\s*$", raw.strip())
        if m and m.group(1) in wanted:
            found.append((i, m.group(1)))
    return found


def _all_out_names(params: str) -> list[str]:
    first, extras = out_value_param(params)
    return ([first] if first else []) + list(extras)


def out_param_index(params: str) -> int | None:
    """*Which* argument a call writes through -- the position of the parameter
    :func:`out_value_param` picked.

    The call site used to guess by looking for the last bare identifier in
    the argument list, and when a function had more than one out-parameter
    the two ends disagreed: the definition returned the *first*, the caller
    assigned it to the *last*. Nothing failed at the seam -- the caller
    simply got a number where it expected a config object, and the error
    surfaced a call later, inside SWIG.
    """
    name, _ = out_value_param(params)
    if name is None:
        return None
    for i, raw in enumerate(split_args(params)):
        m = re.search(r"(\w+)\s*$", raw.strip())
        if m and m.group(1) == name:
            return i
    return None


def _rewrite_ctor_init_lists(text: str) -> str:
    """``Cls(params) : field(val), field2(val2) {`` -> assignments in the body.

    The initialiser list is turned into ``field = val;`` statements at the top
    of the constructor body, which is where the porter already puts field
    defaults -- the body wins, exactly as in C++.
    """
    out = []
    pat = re.compile(r"\)\s*:\s*([\w_]+\s*\([^)]*\)(?:\s*,\s*[\w_]+\s*\([^)]*\))*)\s*\{")
    last = 0
    for m in pat.finditer(text):
        inits = split_args(m.group(1))
        assigns = "; ".join(f"{i.split('(')[0].strip()} = {i.split('(', 1)[1].rsplit(')', 1)[0]}"
                            for i in inits) + "; "
        out.append(text[last:m.start()])
        out.append(") { " + assigns)
        last = m.end()
    out.append(text[last:])
    return "".join(out)


#: Words that open a member-section line which is not a declaration.
_NOT_A_FIELD_TYPE = {"public", "private", "protected", "return", "using",
                     "typedef", "friend", "template", "namespace", "struct",
                     "class", "enum", "union", "operator", "signals", "slots"}

#: What a C++ member with no initialiser is *born* as, by base type. This is
#: not a nicety: ``std::vector<T> v;`` is an empty vector, not a null one,
#: and porting it to ``None`` moves the failure to the first ``v.push_back``
#: or ``for x in v`` -- an AttributeError partway down a constructor, which
#: is the last place anyone looks for a mistake in a *declaration*. Four of
#: cmc's sub-windows failed to construct at all for exactly this reason.
#: ``std.vector()`` rather than ``[]``: ported code calls ``push_back`` and
#: ``resize`` on it, which a bare list has not got. cpp_compat's Vector *is*
#: a list, so nothing else has to care about the difference.
_EMPTY = {
    "vector": "std.vector()", "deque": "std.vector()",
    "list": "std.vector()", "forward_list": "std.vector()",
    "queue": "std.vector()", "stack": "std.vector()",
    "priority_queue": "std.vector()", "valarray": "std.vector()",
    "set": "std.set()", "multiset": "std.set()",
    "unordered_set": "std.set()", "unordered_multiset": "std.set()",
    "map": "{}", "multimap": "{}", "unordered_map": "{}",
    "unordered_multimap": "{}",
    "string": '""', "wstring": '""', "string_view": '""', "path": '""',
}

#: Arithmetic members. C++ leaves one declared without an initialiser
#: *indeterminate*, so there is no faithful value to copy -- but reading an
#: indeterminate member is undefined behaviour, so no correct program can be
#: relying on what it holds, and zero is the only choice that lets the port
#: run rather than TypeError on ``None``.
_ZERO = {"bool": "False", "float": "0.0", "double": "0.0", "char": "0"}
_INTEGRAL = {
    "int", "short", "long", "unsigned", "signed", "size_t", "ssize_t",
    "ptrdiff_t", "intptr_t", "uintptr_t", "time_t", "clock_t",
    "int8_t", "int16_t", "int32_t", "int64_t",
    "uint8_t", "uint16_t", "uint32_t", "uint64_t",
    "ImU8", "ImU16", "ImU32", "ImU64", "ImS8", "ImS16", "ImS32", "ImS64",
}

#: Types whose default really is nothing at all.
_NULLABLE = {"unique_ptr", "shared_ptr", "weak_ptr", "optional", "function",
             "any", "atomic"}


def _scalar_default(base: str, words: str = "") -> str:
    """The value a single ``base`` is born holding, or ``None`` if the port
    cannot know (a class of the application's own -- constructing one here
    would name a symbol this module has no way to import)."""
    if words.strip() and base in ("int", "char", "long", "short", "double"):
        # ``unsigned int``, ``long long``, ``long double``
        return "0.0" if base == "double" else "0"
    if base in _ZERO:
        return _ZERO[base]
    if base in _INTEGRAL:
        return "0"
    return "None"


def _is_brace_init(before: str) -> bool:
    """Does the ``{`` at the end of *before* open a member initialiser?

    ``std::atomic<bool> stop_requested_{false};`` and
    ``struct FCSCurve { ... };`` both put a ``{`` straight after an
    identifier, and only the second opens a body. What separates them is the
    *declaration* they belong to: a body-opening brace comes after ``)``,
    ``const``, ``noexcept`` or a base-class ``:``, or else the declaration
    began with ``struct``/``class``/``union``/``enum``/``namespace``.

    Getting this wrong is quiet: the initialiser was stripped as if it were
    a body, so the member kept its name and lost its value.
    """
    if not before or not (before[-1].isalnum() or before[-1] == "_"):
        return False
    if re.search(r"\b(?:const|noexcept|override|final|try|else|do|return)$", before):
        return False
    # back to the start of this declaration
    start = max(before.rfind(";"), before.rfind("{"), before.rfind("}"),
                before.rfind(":"))
    decl = before[start + 1:].strip()
    return not re.match(r"\b(?:struct|class|union|enum|namespace)\b", decl)


def _braces_to_lists(value: str) -> str:
    """Every brace-derived group in a container initialiser becomes a list.

    ``_brace_call`` turns ``{a, b}`` into ``(a, b)``, which is right for an
    ImVec2 and wrong for a row of an array: ``channel_colors_[ch][0] = r`` is
    an assignment into it, and a tuple does not take one. Only groups that
    are *not* a call are converted -- ``std.array(1, 2, 3)`` is an argument
    list and must stay one.
    """
    out = []
    depth_ok = []
    for i, c in enumerate(value):
        if c == "(":
            prev = value[:i].rstrip()
            call = bool(prev) and (prev[-1].isalnum() or prev[-1] in "_.")
            depth_ok.append(call)
            out.append("(" if call else "[")
        elif c == ")" and depth_ok:
            out.append(")" if depth_ok.pop() else "]")
        else:
            out.append(c)
    return "".join(out)


def _unelide(init: str) -> str:
    """Undo C++'s brace elision on an array initialiser.

    ``std::array<T, N> a = {{...}}`` writes *two* braces: the outer one
    initialises the array, the inner one the C array inside it. So the extra
    level is not nesting, and reading it as nesting turns
    ``{{"Ch 0", "Ch 1", "Ch 2", "Ch 3"}}`` into a list of one tuple -- four
    labels collapsed to one element, and an IndexError on the second.

    The test is whether the outer braces hold exactly one brace group and
    nothing besides: ``{{a, b, c}}`` is elision, ``{{a,b},{c,d}}`` is two
    real rows and is left alone.
    """
    s = init.strip()
    if not (s.startswith("{") and s.endswith("}")):
        return init
    inner = s[1:-1].strip()
    if not (inner.startswith("{") and inner.endswith("}")):
        return init
    if find_matching_brace(inner, 0) != len(inner) - 1:
        return init                        # several groups: real nesting
    return inner


def _member_default(words: str, base: str, is_ptr: bool, tmpl: list[str],
                    extent: str | None, structs: set) -> str:
    """The default for one member declaration, given its type as scraped.

    *tmpl* is the template argument list as written (``std::array<T, 3>`` ->
    ``["T", "3"]``), *extent* the ``[N]`` of a C array, *structs* the plain
    aggregates this file also ports -- one of those can be constructed by
    name, so ``std::array<FCSCurve, 3>`` becomes three real curves rather
    than three Nones that AttributeError on first use.
    """
    if is_ptr:
        return "None"                      # a raw pointer member: nothing yet
    if base in _NULLABLE:
        return "None"
    if base in _EMPTY:
        return _EMPTY[base]
    # ``std::array<T, N>`` and ``T name[N]`` are both N default-constructed
    # elements. N may be a constant member declared just above, which is why
    # the caller qualifies it against the fields found so far.
    n = None
    elem = base
    if base == "array" and len(tmpl) == 2:
        elem, n = tmpl[0].split("::")[-1].strip(), tmpl[1].strip()
    elif extent is not None:
        n = extent.strip() or None
    if n:
        if elem in structs:
            return f"[{elem}() for _ in range({n})]"
        if elem in _EMPTY:
            # `std::array<std::deque<DataPoint>, 4> buffers_;` is four empty
            # deques, not four Nones -- and a literal `[[]] * 4` would be one
            # list four times, so each element is built separately.
            return f"[{_EMPTY[elem]} for _ in range({n})]"
        return f"[{_scalar_default(elem, words)}] * ({n})"
    if base in structs:
        return f"{base}()"
    return _scalar_default(base, words)


def _member_statements(inner: str):
    """Split a class body into member declarations, on `;` at brace depth 0.

    Not :func:`statements`, which also breaks at a brace -- and a default
    member initialiser *is* braced, so it cut
    ``std::array<...> colours_ = {`` off from its own value. The field then
    failed to match at all, so it was not a member, so every use of it came
    out unqualified and NameErrored at run time.
    """
    depth = 0
    buf: list = []
    k = 0
    while k < len(inner):
        c = inner[k]
        if c in "\"'":
            j = _skip_string(inner, k)
            buf.append(inner[k:j])
            k = j
            continue
        if c in "{([":
            depth += 1
        elif c in "})]":
            depth -= 1
        elif c == ";" and depth <= 0:
            text = "".join(buf).strip()
            if text:
                # the `;` rides along: FIELD_RE anchors on it, as it did when
                # these came from `statements()`
                yield text + ";"
            buf = []
            k += 1
            continue
        buf.append(c)
        k += 1
    tail = "".join(buf).strip()
    if tail:
        yield tail + ";"


def port_class_fields(inner: str, porter: Porter,
                      structs: set | None = None) -> list[tuple[str, str]]:
    """Scrape a class body into ``(name, python_default)`` pairs.

    *structs* names the plain aggregates this file also ports, so a member
    of one can be default-constructed by name instead of left ``None``.
    """
    structs = structs or set()
    # Prose first. A member is very often introduced by a `// what it is`
    # line, and the statement splitter breaks on `;` -- so the comment ends
    # up glued to the *front* of the declaration under it, where the
    # `startswith("//")` guard below threw the whole thing away. Eight of
    # ImageWindow's members were lost to that one, `texture_id_` among them,
    # and nothing said so: they simply were not members, so every use of
    # them ported unqualified.
    inner = strip_comments(inner)
    # Inline method bodies hide local declarations, so the braced blocks go
    # next -- but not *every* brace: a default member initialiser is braced
    # too (`int active_[4] = {1, 1, 1, 1};`), and stripping it left the field
    # with an empty default. A brace after `=` or `,` is an initialiser; one
    # after `)`, `const`, `noexcept` or `:` opens a body.
    pos = 0
    while True:
        m = re.search(r"\{", inner[pos:])
        if not m:
            break
        at = pos + m.start()
        before = inner[:at].rstrip()
        if before.endswith(("=", ",")) or _is_brace_init(before):
            pos = find_matching_brace(inner, at) + 1
            continue
        # A `;` goes in where the body was. `void show() { show_ = true; }`
        # carries no semicolon of its own, so removing the body left
        # `void show()` glued to everything after it up to the next `;` --
        # which is the next *field*, and that field was then skipped as a
        # method because the leftover declarator had brought a `(` with it.
        inner = inner[:at] + ";" + inner[find_matching_brace(inner, at) + 1:]
        pos = at + 1
    fields: list[tuple[str, str]] = []
    for line in _member_statements(inner):
        s = line.strip()
        # An access specifier carries no semicolon, so the statement splitter
        # leaves it glued to the declaration that follows -- and the *first
        # field of every section* then fails to match a pattern anchored at
        # the start of the line. Silently: the field is simply never found,
        # and every use of it comes out unqualified.
        s = re.sub(r"^(?:public|private|protected)\s*:\s*", "", s).strip()
        if s.startswith(("enum", "struct", "class", "union")):
            continue
        # The template arguments go before the `(`-means-method test, not
        # after it: `std::function<ImageNode *()> node_provider_;` is a
        # field whose *type* contains parentheses, and testing first read it
        # as a method and dropped it.
        # `std::array<std::deque<std::pair<double, double>>, 4>` nests three
        # deep, so one pass is not enough: strip the innermost each time
        # until nothing changes, keeping the outermost argument list -- it
        # says how many elements an array holds and of what.
        tmpl: list[str] = []
        prev = None
        while prev != s:
            prev = s
            mt = re.match(r"[^<>]*?\b([A-Za-z_]\w*)<([^<>]*)>", s)
            if mt and not tmpl:
                tmpl = split_args(mt.group(2))
            s = re.sub(r"\b([A-Za-z_]\w*)<[^<>]*>", r"\1", s)
        # A method declaration -- but only the *declarator* may be consulted.
        # An initialiser is allowed to be a call, and testing the whole
        # statement threw away every field that had one:
        # `nlohmann::json picoquant_settings_ = picoquant::default_document();`
        # was not a member, so `picoquant_settings_ = ...` inside a method
        # ported unqualified and assigned to a local that nothing ever read.
        if "(" in re.split(r"[={]", s, 1)[0]:
            continue
        fm = FIELD_RE.match(s)
        if not fm or fm.group("type").split("::")[0] in _NOT_A_FIELD_TYPE:
            continue
        name, init = fm.group("name"), fm.group("init")
        if init is None and fm.group("binit") is not None:
            # `x_{a, b}` is the same initialiser as `x_ = {a, b}`; `x_{}` is
            # value-initialisation, which is what the no-initialiser path
            # already produces.
            init = "{" + fm.group("binit") + "}" if fm.group("binit").strip() else None
        base = fm.group("type").split("::")[-1]
        # `cmc::tac::Calibration bhspc_calibration_{4096};` is a *constructor
        # call*, not an aggregate: braces on a class type with a constructor
        # pass arguments. Ported as an initialiser it came out as the bare
        # integer 4096 -- a member that looks like it holds a value and holds
        # the wrong kind of thing entirely. Say what it is instead.
        if (init and init.lstrip().startswith("{")
                and base not in structs and base not in _EMPTY
                and base not in _ZERO and base not in _INTEGRAL
                and base not in _NULLABLE and base != "array"
                and fm.group("extent") is None
                and not base.startswith("ImVec")):
            one = " ".join(init.split())[:50]
            fields.append((name, f"None  # TODO(autoport): {base}{one} "
                                 f"constructs a C++ type this port cannot make"))
            continue
        # How many elements the declaration says there are, when it says.
        n_decl = None
        if base == "array" and len(tmpl) == 2 and tmpl[1].strip().isdigit():
            n_decl = int(tmpl[1].strip())
        elif fm.group("extent") and fm.group("extent").strip().isdigit():
            n_decl = int(fm.group("extent").strip())
        is_seq = (base in _EMPTY or base == "array"
                  or fm.group("extent") is not None)
        if init:
            init = init.strip()
            if base == "array" or fm.group("extent") is not None:
                init = _unelide(init)
            value = porter.expr(init)
            # `std::vector<int> ch_ = {0};` ports its braces to a *tuple*,
            # which is right for an ImVec2 and wrong for a container: `(0)`
            # is the integer nought, not a one-element list, and a tuple
            # cannot take the `v[i] = x` the C++ goes on to do.
            if is_seq and value.lstrip().startswith("("):
                value = _braces_to_lists(value)
            # `std::array<double, 4> mean_ = {0};` is *four* doubles: an
            # aggregate initialiser value-initialises whatever it does not
            # name. Ported as written it was a one-element list, and the
            # first read of `mean_[1]` was an IndexError three files away.
            if n_decl and value.startswith("[") and value.endswith("]"):
                given = [a for a in split_args(value[1:-1]) if a.strip()]
                if 0 < len(given) < n_decl:
                    elem = tmpl[0].split("::")[-1].strip() if base == "array" else base
                    pad = (f"{elem}()" if elem in structs
                           else _scalar_default(elem, fm.group("words")))
                    value = "[" + ", ".join(given + [pad] * (n_decl - len(given))) + "]"
        else:
            extent = fm.group("extent")
            if extent:
                # `float hist_[n_bins_ * n_bins_];` -- the extent is a
                # constant member declared above, which on this side is an
                # attribute of the object being built.
                seen = {f for f, _ in fields}
                extent = re.sub(r"\b([A-Za-z_]\w*)\b",
                                lambda m: ("self." + m.group(1)
                                           if m.group(1) in seen else m.group(1)),
                                extent)
            value = _member_default(fm.group("words"), base,
                                    "*" in fm.group("ptr") or "&" in fm.group("ptr"),
                                    tmpl, extent, structs)
        fields.append((name, value))
    return fields


