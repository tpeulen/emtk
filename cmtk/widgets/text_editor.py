r"""A colourising text editor: the port of ImGuiColorTextEdit.

Where it comes from
-------------------
``junk/ImGuiColorTextEdit`` -- Johan A. Goossens' rewrite of Balázs Jákó's
syntax-highlighting editor for Dear ImGui, MIT licensed. It is the same
provenance as the rest of this package: :mod:`.tables` came from
``imgui_tables.cpp``, this came from ``TextEditor.cpp``, and both are read
against their source rather than reinvented.

The reference's own architecture note is the map, and this file keeps its
layer names so the two can be read side by side: a :class:`Document` of
:class:`Line`\\ s, with *overlays* that decorate it -- :class:`Colorizer` for
the per-character colour, :class:`Bracketeer` for bracket pairs,
:class:`Cursors` for the carets, :class:`Transactions` for undo -- and one
:class:`TextEditor` on top that owns the public API, the drawing and the keys.

Three deliberate divergences
----------------------------
**A line is a string and a colour array, not a vector of glyph structs.** The
reference's ``Line`` is a ``std::vector<Glyph>``, and a ``Glyph`` is a
codepoint plus a colour plus two overlay fields -- eight bytes, contiguous. The
literal port is a Python object per *character*: about fifty bytes each, and a
2000-line file becomes several million objects that the garbage collector then
walks. So a line here is its ``text`` plus a parallel ``colours`` bytearray,
one entry per character. Every algorithm below is the reference's, transcribed
against that representation; the only thing that changes is that "advance the
glyph iterator by *n*" is "advance an integer index by *n*".

**Tokenizers are regular expressions, not state machines.** The reference
generates its identifier and number scanners with re2c because a virtual call
per character was measurably too slow in C++. In Python the opposite holds: a
compiled ``re`` pattern runs in C and a hand-written character loop does not,
so :data:`_C_NUMBER` and friends are patterns anchored at the scan position.
The grammars are transcribed from the generated automata, not guessed.

**Colour is a token role, not a palette entry.** The reference's ``Color`` enum
mixes token roles (keyword, string) with chrome roles (background, cursor,
selection). Here :class:`Token` is only the former and the chrome colours come
from :mod:`.style`, because the chrome already has a palette and a second one
that drifts from it is the bug :mod:`.style` exists to prevent.

What is deliberately not ported
-------------------------------
Word wrap, line folding, the minimap, autocomplete, LSP hover, squiggly
underlines, line decorators and the Unicode Annex 14 line-breaking rules. Each
is a feature of the reference's *TypeSetter* -- the layer that separates
document position from visual position -- and none has a caller here: the
chrome draws a script in a dock, one document row per screen row. The port
keeps the single coordinate system (:class:`Pos`, a line and a character index)
that the reference had before that split, which is why the code below is a
third of the size and not one that has to be re-read to be trusted. Multilevel
comments and strings (Lua's ``[==[``) go with them; the languages that ship
here have none.

Everything draws through :class:`~cmtk.painter.Painter`'s six
operations, holds its own state, and hit-tests with :func:`.style.hit`, like
every other control in this package.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from typing import NamedTuple

from ..painter import ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER, Colour, Painter
from ..style import BORDER, FRAME_BG, TEXT, clamp, hit
from .basic import ScrollBar

__all__ = [
    "Token",
    "DARK_PALETTE",
    "LIGHT_PALETTE",
    "LineState",
    "Pos",
    "Language",
    "Line",
    "Document",
    "Colorizer",
    "Cursor",
    "Cursors",
    "Action",
    "Transaction",
    "Transactions",
    "BracketPair",
    "Bracketeer",
    "EditorConfig",
    "TextEditor",
]


# --------------------------------------------------------------------------
# Token roles and palettes -- the reference's Color enum, halved
# --------------------------------------------------------------------------
class Token(IntEnum):
    """What a run of characters *is*, which is what decides its colour.

    The values are indices into a palette, so a palette is a plain sequence and
    a lookup is a subscript rather than a dictionary hash per character.
    """

    TEXT = 0
    KEYWORD = 1
    DECLARATION = 2
    NUMBER = 3
    STRING = 4
    PUNCTUATION = 5
    PREPROCESSOR = 6
    IDENTIFIER = 7
    KNOWN_IDENTIFIER = 8
    COMMENT = 9
    WHITESPACE = 10
    BRACKET_LEVEL1 = 11
    BRACKET_LEVEL2 = 12
    BRACKET_LEVEL3 = 13
    BRACKET_ERROR = 14


#: The reference's ``GetDarkPalette``, token half only, converted to the
#: chrome's 0-255 int tuples. Indexed by :class:`Token`.
DARK_PALETTE: tuple[Colour, ...] = (
    (224, 224, 224),  # text
    (197, 134, 192),  # keyword
    (90, 179, 155),   # declaration
    (181, 206, 168),  # number
    (206, 145, 120),  # string
    (255, 255, 153),  # punctuation
    (64, 192, 128),   # preprocessor
    (156, 220, 254),  # identifier
    (79, 193, 255),   # known identifier
    (106, 153, 85),   # comment
    # whitespace. The reference's is (80, 80, 80), chosen against its own
    # #1e1e1e background; cmtk's frame is (50, 50, 56) over a lit scene, and
    # at that separation the dots are there in the pixels and not on the
    # screen -- which a recording-painter test cannot tell you and a rendered
    # sheet can. Lifted by the same margin the reference intended.
    (105, 105, 112),
    (246, 222, 36),   # matching bracket level 1
    (66, 120, 198),   # matching bracket level 2
    (213, 96, 213),   # matching bracket level 3
    (198, 8, 32),     # matching bracket error
)

#: The reference's ``GetLightPalette``, same halving. Nothing in cmtk selects
#: it yet -- the chrome is drawn over a lit 3-D scene and is dark throughout --
#: but a palette is data and dropping half the reference's would be a silent
#: loss the next reader could not see.
LIGHT_PALETTE: tuple[Colour, ...] = (
    (64, 64, 64),
    (170, 0, 220),
    (65, 0, 255),
    (40, 140, 90),
    (160, 32, 32),
    (0, 0, 0),
    (96, 96, 64),
    (64, 64, 64),
    (16, 96, 96),
    (35, 135, 5),
    (180, 180, 180),
    (246, 222, 36),
    (66, 120, 198),
    (213, 96, 213),
    (198, 8, 32),
)


class LineState(IntEnum):
    """What the colouriser was in the middle of when the previous line ended.

    This is the whole reason colourising is not per-line-independent: a line
    that opens ``/*`` changes how every following line is read, until one
    closes it. The state is stored *on* the line it starts, and a line whose
    incoming state changes is marked for re-colourising -- which is how opening
    a comment at the top of a document repaints the rest of it.
    """

    IN_TEXT = 0
    IN_COMMENT = 1
    IN_SINGLE_QUOTED_STRING = 2
    IN_DOUBLE_QUOTED_STRING = 3
    IN_OTHER_STRING = 4
    IN_OTHER_STRING_ALT = 5


class Pos(NamedTuple):
    """A logical position: a zero-based line and character index.

    A tuple, so ``<`` and ``==`` are the reference's operators for free and a
    position can be a dictionary key. The reference calls this ``DocPos`` and
    also carries a second, visual coordinate system for word wrap; there is no
    word wrap here, so there is one coordinate system and no conversions to get
    wrong.
    """

    line: int = 0
    index: int = 0


# --------------------------------------------------------------------------
# Language definitions
# --------------------------------------------------------------------------
#: The reference's ``isCStylePunctuation`` table, as the characters it marks
#: true. Note what is *absent*: ``@``, ``#``, ``$``, ``\`` and the quotes. Those
#: are either handled earlier (quotes start strings, ``#`` may start a
#: preprocessor line) or are not punctuation in the languages that ship here.
_C_PUNCTUATION = frozenset("!%&()*+,-./:;<=>?[]^{|}~")

#: An identifier, C style. The reference scans XID_Start/XID_Continue; Python's
#: ``\w`` with the ``str`` flavour of ``re`` is Unicode-aware and agrees on
#: everything either language actually contains.
_C_IDENTIFIER = re.compile(r"[^\W\d]\w*")

#: A C number: hex, octal-ish, decimal, float, with the suffix letters the
#: generated scanner accepts.
_C_NUMBER = re.compile(
    r"0[xX][0-9a-fA-F]+(?:[uUlL]*)"
    r"|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?[fFlLuU]*"
)

#: A Python number: the C set plus binary and octal prefixes, ``_`` separators
#: and the imaginary suffix.
_PY_NUMBER = re.compile(
    r"0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+"
    r"|(?:\d[\d_]*\.?[\d_]*|\.\d[\d_]*)(?:[eE][+-]?\d+)?[jJ]?"
)

#: A JSON number -- strictly the grammar from json.org, which is narrower than
#: C's: no hex, no leading ``.``, no suffix.
_JSON_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")

#: The reference's keyword, declaration and identifier tables, one entry per
#: ``static const char* const`` array in ``TextEditor.cpp``, keyed by the
#: language function that declares it.
#:
#: **Generated, not typed.** They are 873 words between them, they are not
#: alphabetical in the source, and a word dropped in transcription colours one
#: identifier wrong in one language and fails nothing. So they come out of
#: ``tools/port_imgui_widget.py``'s ``extract_word_lists``, and
#: a test re-extracts them and asserts they still agree -- which is the only
#: way anyone would ever find out that they had drifted.
_WORDS: dict[str, frozenset[str]] = {
    "C_keywords": frozenset(
        "_Alignas _Alignof _Atomic _Bool _Complex _Generic _Imaginary _Noreturn _Static_assert "
        "_Thread_local break case continue default do else for goto if return sizeof switch "
        "while "
        .split()
    ),
    "C_declarations": frozenset(
        "auto char const double enum extern float inline int long register restrict short "
        "signed static struct typedef union unsigned void volatile "
        .split()
    ),
    "Cpp_keywords": frozenset(
        "alignas alignof and and_eq asm atomic_cancel atomic_commit atomic_noexcept bitand "
        "bitor break case catch compl const_cast continue default delete do dynamic_cast else "
        "explicit export extern false for goto if import new noexcept not not_eq nullptr "
        "operator or or_eq reinterpret_cast requires return sizeof static_assert static_cast "
        "switch synchronized this thread_local throw true try while xor xor_eq "
        .split()
    ),
    "Cpp_declarations": frozenset(
        "auto bool char char16_t char32_t char8_t class concept const constexpr decltype double "
        "enum explicit export extern float friend inline int long module mutable namespace "
        "private protected public register restrict short signed static struct template typedef "
        "typeid typename union unsigned using virtual void volatile wchar_t "
        .split()
    ),
    "Python_keywords": frozenset(
        "False None True and as assert async await break class continue def del elif else "
        "except finally for from global if import in is lambda nonlocal not or pass raise "
        "return try while with yield "
        .split()
    ),
    "Json_keywords": frozenset(
        "false null true "
        .split()
    ),
    "Glsl_keywords": frozenset(
        "atomic_uint attribute bool break buffer bvec2 bvec3 bvec4 case centroid coherent const "
        "continue default discard dmat2 dmat2x2 dmat2x3 dmat2x4 dmat3 dmat3x2 dmat3x3 dmat3x4 "
        "dmat4 dmat4x2 dmat4x3 dmat4x4 do double dvec2 dvec3 dvec4 else false flat float for "
        "highp if iimage1D iimage1DArray iimage2D iimage2DArray iimage2DMS iimage2DMSArray "
        "iimage2DRect iimage3D iimageBuffer iimageCube iimageCubeArray image1D image1DArray "
        "image2D image2DArray image2DMS image2DMSArray image2DRect image3D imageBuffer "
        "imageCube imageCubeArray in inout int invariant isampler1D isampler1DArray isampler2D "
        "isampler2DArray isampler2DMS isampler2DMSArray isampler2DRect isampler3D "
        "isamplerBuffer isamplerCube isamplerCubeArray ivec2 ivec3 ivec4 layout lowp mat2 "
        "mat2x2 mat2x3 mat2x4 mat3 mat3x2 mat3x3 mat3x4 mat4 mat4x2 mat4x3 mat4x4 mediump "
        "noperspective out patch precise precision readonly restrict return sample sampler1D "
        "sampler1DArray sampler1DArrayShadow sampler1DShadow sampler2D sampler2DArray "
        "sampler2DArrayShadow sampler2DMS sampler2DMSArray sampler2DRect sampler2DRectShadow "
        "sampler2DShadow sampler3D samplerBuffer samplerCube samplerCubeArray "
        "samplerCubeArrayShadow samplerCubeShadow shared smooth struct subroutine switch true "
        "uimage1D uimage1DArray uimage2D uimage2DArray uimage2DMS uimage2DMSArray uimage2DRect "
        "uimage3D uimageBuffer uimageCube uimageCubeArray uint uniform usampler1D "
        "usampler1DArray usampler2D usampler2DArray usampler2DMS usampler2DMSArray "
        "usampler2DRect usampler3D usamplerBuffer usamplerCube usamplerCubeArray uvec2 uvec3 "
        "uvec4 varying vec2 vec3 vec4 void volatile while writeonly "
        .split()
    ),
    "Sql_keywords": frozenset(
        "abs absent acos all allocate alter and any any_value are array array_agg "
        "array_max_cardinality as asensitive asin asymmetric at atan atomic authorization avg "
        "begin begin_frame begin_partition between bigint binary blob boolean both btrim by "
        "call called cardinality cascaded case cast ceil ceiling char char_length character "
        "character_length check classifier clob close coalesce collate collect column commit "
        "condition connect constraint contains convert copy corr corresponding cos cosh count "
        "covar_pop covar_samp create cross cube cume_dist current current_catalog current_date "
        "current_default_transform_group current_path current_role current_row current_schema "
        "current_time current_timestamp current_transform_group_for_type current_user cursor "
        "cycle date day deallocate dec decfloat decimal declare default define delete "
        "dense_rank deref describe deterministic disconnect distinct double drop dynamic each "
        "element else empty end end-exec end_frame end_partition equals escape every except "
        "exec execute exists exp external extract false fetch filter first_value float floor "
        "for foreign frame_row free from full function fusion get global grant greatest group "
        "grouping groups having hold hour identity in indicator initial inner inout insensitive "
        "insert int integer intersect intersection interval into is join json json_array "
        "json_arrayagg json_exists json_object json_objectagg json_query json_scalar "
        "json_serialize json_table json_table_primitive json_value lag language large "
        "last_value lateral lead leading least left like like_regex limit listagg ln local "
        "localtime localtimestamp log log10 lower lpad ltrim match match_number match_recognize "
        "matches max member merge method min minute mod modifies module month multiset national "
        "natural nchar nclob new no none normalize not nth_value ntile null nullif numeric "
        "occurrences_regex octet_length of offset old omit on one only open or order out outer "
        "over overlaps overlay parameter partition pattern per percent percent_rank "
        "percentile_cont percentile_disc period portion position position_regex power precedes "
        "precision prepare primary procedure ptf range rank reads real recursive ref references "
        "referencing regr_avgx regr_avgy regr_count regr_intercept regr_r2 regr_slope regr_sxx "
        "regr_sxy regr_syy release result return returns revoke right rollback rollup row "
        "row_number rows rpad running savepoint scope scroll search second seek select "
        "sensitive session_user set show similar sin sinh skip smallint some specific "
        "specifictype sql sqlexception sqlstate sqlwarning sqrt start static stddev_pop "
        "stddev_samp submultiset subset substring substring_regex succeeds sum symmetric system "
        "system_time system_user table tablesample tan tanh then time timestamp timezone_hour "
        "timezone_minute to trailing translate translate_regex translation treat trigger trim "
        "trim_array true truncate uescape union unique unknown unnest update upper user using "
        "value value_of values var_pop var_samp varbinary varchar varying versioning when "
        "whenever where width_bucket window with within without year "
        .split()
    ),
    "Lua_keywords": frozenset(
        "and break do else elseif end false for function goto if in local nil not or repeat "
        "return then true until while "
        .split()
    ),
    "Lua_identifiers": frozenset(
        "_G _VERSION abs acos asin assert atan atan2 byte ceil char clock close collectgarbage "
        "concat coroutine cos cosh cpath create date debug deg difftime dofile dump error "
        "execute exit exp find floor flush fmod format frexp getenv getfenv gethook getinfo "
        "getlocal getmetatable getregistry getupvalue gmatch gsub huge input insert io ipairs "
        "ldexp len lines load loaded loaders loadfile loadlib loadstring log log10 lower match "
        "math max maxn min modf module next open os output package pairs path pcall pi popen "
        "pow preload print rad random randomseed rawequal rawget rawset read remove rename rep "
        "require resume reverse running seeall seek select setfenv sethook setlocal setlocale "
        "setmetatable setupvalue setvbuf sin sinh sort sqrt status stderr stdin stdout string "
        "sub table tan tanh time tmpfile tmpname tonumber tostring traceback type unpack upper "
        "wrap write xpcall yield "
        .split()
    ),
}


@dataclass
class Language:
    """How to tokenise one language.

    Every field is optional and an empty one switches its rule off, which is
    the reference's design: the colouriser reads the fields rather than
    branching on a language identifier, so adding a language is data.

    Attributes
    ----------
    name : str
        Shown in the editor's status line.
    case_sensitive : bool
        When false, keywords are matched lower-cased -- so the sets must be
        given lower-cased too, as the reference requires.
    preprocess : str
        The character that, first on a line, makes the whole line a
        preprocessor directive. Empty if the language has none.
    single_line_comment, single_line_comment_alt : str
        Sequences that comment out the rest of the line.
    comment_start, comment_end : str
        The multi-line comment delimiters.
    has_single_quoted_strings, has_double_quoted_strings : bool
    other_string_start / _end, other_string_alt_start / _alt_end : str
        Extra string delimiters -- Python's two triple quotes are exactly this.
    string_escape : str
        The in-string escape character, or empty.
    indentation_for_blocks : bool
        True for a language whose blocks are indentation (Python), which is
        what tells :class:`Bracketeer` there are invisible brackets to infer.
    keywords, declarations, identifiers : set of str
        The three highlighted word classes; they map to three palette entries.
    punctuation : frozenset of str
    identifier_pattern, number_pattern : re.Pattern or None
        Anchored at the scan position with ``match``.
    comment_prefix : str
        What :meth:`TextEditor.toggle_comments` inserts. Defaults to
        ``single_line_comment``.
    """

    name: str = "None"
    case_sensitive: bool = True
    preprocess: str = ""
    single_line_comment: str = ""
    single_line_comment_alt: str = ""
    comment_start: str = ""
    comment_end: str = ""
    has_single_quoted_strings: bool = False
    has_double_quoted_strings: bool = False
    other_string_start: str = ""
    other_string_end: str = ""
    other_string_alt_start: str = ""
    other_string_alt_end: str = ""
    string_escape: str = ""
    indentation_for_blocks: bool = False
    keywords: frozenset[str] = frozenset()
    declarations: frozenset[str] = frozenset()
    identifiers: frozenset[str] = frozenset()
    punctuation: frozenset[str] = _C_PUNCTUATION
    identifier_pattern: re.Pattern | None = _C_IDENTIFIER
    number_pattern: re.Pattern | None = _C_NUMBER
    comment_prefix: str = ""

    def __post_init__(self) -> None:
        """Default the comment prefix to the single-line comment sequence."""
        if not self.comment_prefix:
            object.__setattr__(self, "comment_prefix", self.single_line_comment)

    # -- the shipped languages ----------------------------------------- #
    # Word lists come from :data:`_WORDS` and are the reference's, unaltered.
    # Where a builder passes something *else* it is an addition, and each one
    # is here because the reference's table predates the thing it misses:
    # Python's ``match``/``case`` (soft keywords, 3.10), Python's builtins and
    # GLSL's built-in functions (the reference colours neither, and they are
    # what a shader or a script is mostly made of), and SQL's type names, which
    # the reference lumps in with its keywords.
    @staticmethod
    def c() -> Language:
        """C, as the reference defines it."""
        return Language(
            name="C",
            preprocess="#",
            single_line_comment="//",
            comment_start="/*",
            comment_end="*/",
            has_single_quoted_strings=True,
            has_double_quoted_strings=True,
            string_escape="\\",
            keywords=_WORDS["C_keywords"],
            declarations=_WORDS["C_declarations"],
        )

    @staticmethod
    def cpp() -> Language:
        """C++ -- C's rules with C++'s word lists."""
        return Language(
            name="C++",
            preprocess="#",
            single_line_comment="//",
            comment_start="/*",
            comment_end="*/",
            has_single_quoted_strings=True,
            has_double_quoted_strings=True,
            string_escape="\\",
            keywords=_WORDS["Cpp_keywords"],
            declarations=_WORDS["Cpp_declarations"],
        )

    @staticmethod
    def python() -> Language:
        """Python, as the reference defines it -- triple quotes included."""
        return Language(
            name="Python",
            single_line_comment="#",
            has_single_quoted_strings=True,
            has_double_quoted_strings=True,
            other_string_start='"""',
            other_string_end='"""',
            other_string_alt_start="'''",
            other_string_alt_end="'''",
            string_escape="\\",
            indentation_for_blocks=True,
            keywords=_WORDS["Python_keywords"] | {"match", "case"},
            declarations=frozenset(),
            identifiers=frozenset(
                "abs all any bool bytes callable dict enumerate filter float format frozenset "
                "getattr hasattr int isinstance len list map max min object open print range "
                "repr reversed round set setattr sorted str sum tuple type zip self cls".split()
            ),
            number_pattern=_PY_NUMBER,
        )

    @staticmethod
    def json() -> Language:
        """JSON. No comments, no single quotes, and its own number grammar."""
        return Language(
            name="JSON",
            has_double_quoted_strings=True,
            string_escape="\\",
            keywords=_WORDS["Json_keywords"],
            punctuation=frozenset("{}[],:"),
            number_pattern=_JSON_NUMBER,
        )

    @staticmethod
    def glsl() -> Language:
        """GLSL -- and near enough WGSL, which is what cmtk's shaders are."""
        return Language(
            name="GLSL",
            preprocess="#",
            single_line_comment="//",
            comment_start="/*",
            comment_end="*/",
            has_double_quoted_strings=True,
            string_escape="\\",
            keywords=_WORDS["Glsl_keywords"],
            declarations=frozenset(
                "bool bvec2 bvec3 bvec4 const double dvec2 dvec3 dvec4 float int ivec2 ivec3 "
                "ivec4 mat2 mat3 mat4 sampler1D sampler2D sampler3D samplerCube struct uint "
                "uvec2 uvec3 uvec4 vec2 vec3 vec4 void".split()
            ),
            identifiers=frozenset(
                "abs acos all any asin atan ceil clamp cos cross degrees distance dot exp "
                "faceforward floor fract gl_FragCoord gl_FragColor gl_Position inverse length "
                "log max min mix mod normalize pow radians reflect refract sign sin smoothstep "
                "sqrt step tan texture transpose".split()
            ),
        )

    @staticmethod
    def lua() -> Language:
        """Lua. Its long comment is ``--[[ ]]``, which the plain fields cover."""
        return Language(
            name="Lua",
            single_line_comment="--",
            comment_start="--[[",
            comment_end="]]",
            has_single_quoted_strings=True,
            has_double_quoted_strings=True,
            string_escape="\\",
            keywords=_WORDS["Lua_keywords"],
            identifiers=_WORDS["Lua_identifiers"],
        )

    @staticmethod
    def markdown() -> Language:
        """Markdown -- no keywords, but code spans and fences colour as strings."""
        return Language(
            name="Markdown",
            other_string_start="```",
            other_string_end="```",
            other_string_alt_start="`",
            other_string_alt_end="`",
            punctuation=frozenset("#*_>-[]()!"),
            identifier_pattern=None,
            number_pattern=None,
        )

    @staticmethod
    def sql() -> Language:
        """SQL. Case-insensitive, which is what the flag exists for."""
        return Language(
            name="SQL",
            case_sensitive=False,
            single_line_comment="--",
            comment_start="/*",
            comment_end="*/",
            has_single_quoted_strings=True,
            has_double_quoted_strings=True,
            keywords=_WORDS["Sql_keywords"],
            declarations=frozenset(
                "bigint blob boolean char date datetime decimal double float int integer numeric "
                "real smallint text time timestamp varchar".split()
            ),
        )

    @staticmethod
    def commands(
        commands: Iterable[str] = (),
        words: Iterable[str] = (),
        name: str = "commands",
    ) -> Language:
        """Build a command-script language out of an application's own verbs.

        The reference ships eleven languages and none of them is the one a
        user types into a tool's console. A command script is a list of verbs
        -- ``fetch``, ``show``, ``color``, ``select`` -- with ``#`` comments
        and selection strings, and any application with a command registry
        *already* enumerates its verbs. So they are passed in rather than
        duplicated here: a command added to that registry colours in the
        editor without anyone remembering to teach cmtk about it.

        Parameters
        ----------
        commands : iterable of str, optional
            Command names, e.g. ``registry.keys()``. Empty gives a language
            that still handles comments, strings and numbers.
        words : iterable of str, optional
            The application's second vocabulary -- the words its arguments are
            made of, such as a selection grammar's ``all``/``not``/``within``.
            Coloured as identifiers rather than as verbs. cmtk holds no such
            list of its own: it belongs to whoever defines the grammar.
        name : str, optional
            The language's name, as it appears in a picker.

        Returns
        -------
        Language
        """
        return Language(
            name=name,
            single_line_comment="#",
            has_single_quoted_strings=True,
            has_double_quoted_strings=True,
            string_escape="\\",
            keywords=frozenset(str(verb) for verb in commands),
            identifiers=frozenset(str(word) for word in words),
            number_pattern=_PY_NUMBER,
        )


#: Every shipped language, by name, for a picker. Built by asking
#: :class:`Language` rather than by repeating the list, so a language added
#: above appears here.
def shipped_languages() -> dict[str, Language]:
    """Return the built-in languages, keyed by name.

    Returns
    -------
    dict of str to Language
        Fresh instances -- a :class:`Language` is a mutable dataclass and
        handing every editor the same one would let one editor's edit reach
        another's.
    """
    builders = [
        getattr(Language, name)
        for name in vars(Language)
        if not name.startswith("_") and isinstance(vars(Language)[name], staticmethod)
    ]
    made = [build() for build in builders]
    return {one.name: one for one in made}


# --------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------
class Line:
    """One line: its text, one colour per character, and its overlay state.

    Parameters
    ----------
    text : str, optional
        The line's characters, without any terminator.
    """

    __slots__ = ("text", "colours", "state", "needs_colorizing", "marker")

    def __init__(self, text: str = "") -> None:
        self.text = text
        #: One :class:`Token` per character. A bytearray rather than a list of
        #: enums: same subscript, a byte per character instead of a pointer.
        self.colours = bytearray(len(text))
        #: The colouriser state this line *starts* in.
        self.state = LineState.IN_TEXT
        self.needs_colorizing = True
        #: ``(line_number_colour, text_colour, tooltip)`` or ``None``.
        self.marker: tuple[Colour, Colour, str] | None = None

    def __len__(self) -> int:
        """Number of characters."""
        return len(self.text)

    def set_text(self, text: str) -> None:
        """Replace the characters and reset the colours to plain text."""
        self.text = text
        self.colours = bytearray(len(text))
        self.needs_colorizing = True

    def paint(self, start: int, end: int, token: Token) -> None:
        """Colour ``text[start:end]`` as *token*."""
        for index in range(start, min(end, len(self.colours))):
            self.colours[index] = int(token)


class Document:
    """The text being edited, as a list of :class:`Line`.

    Invariant, and the reason a document is never an empty list: there is
    always at least one line, so a cursor always has somewhere to be. The
    reference makes the same guarantee in its constructor.
    """

    def __init__(self, text: str = "") -> None:
        self.lines: list[Line] = [Line()]
        self.updated = False
        if text:
            self.set_text(text)

    # -- content -------------------------------------------------------- #
    def set_text(self, text: str) -> None:
        r"""Replace the whole document.

        Parameters
        ----------
        text : str
            ``\r\n`` and a lone ``\r`` both split a line, because a file
            written on another platform is not the user's mistake.
        """
        body = str(text).replace("\r\n", "\n").replace("\r", "\n")
        self.lines = [Line(part) for part in body.split("\n")]
        self.updated = True

    def get_text(self) -> str:
        """The whole document as one newline-joined string."""
        return "\n".join(line.text for line in self.lines)

    def get_line_text(self, line: int) -> str:
        """The text of one line, or ``""`` past the end."""
        return self.lines[line].text if 0 <= line < len(self.lines) else ""

    def get_section_text(self, start: Pos, end: Pos) -> str:
        """The text between two positions, ``start`` inclusive, ``end`` exclusive."""
        start, end = self.normalize(start), self.normalize(end)
        if start >= end:
            return ""
        if start.line == end.line:
            return self.lines[start.line].text[start.index:end.index]
        parts = [self.lines[start.line].text[start.index:]]
        parts.extend(self.lines[one].text for one in range(start.line + 1, end.line))
        parts.append(self.lines[end.line].text[: end.index])
        return "\n".join(parts)

    def insert_text(self, start: Pos, text: str) -> Pos:
        r"""Insert *text* at *start* and return the position after it.

        Parameters
        ----------
        start : Pos
            Where to insert.
        text : str
            May contain newlines, which split the line at the insert point.

        Returns
        -------
        Pos
            Where the caret goes: the end of what was inserted.
        """
        start = self.normalize(start)
        body = str(text).replace("\r\n", "\n").replace("\r", "\n")
        if not body:
            return start
        line = self.lines[start.line]
        head, tail = line.text[: start.index], line.text[start.index:]
        parts = body.split("\n")
        if len(parts) == 1:
            line.set_text(head + parts[0] + tail)
            end = Pos(start.line, start.index + len(parts[0]))
        else:
            line.set_text(head + parts[0])
            made = [Line(part) for part in parts[1:]]
            made[-1].set_text(parts[-1] + tail)
            self.lines[start.line + 1: start.line + 1] = made
            end = Pos(start.line + len(parts) - 1, len(parts[-1]))
        self.updated = True
        return end

    def delete_text(self, start: Pos, end: Pos) -> None:
        """Delete everything between two positions."""
        start, end = self.normalize(start), self.normalize(end)
        if start >= end:
            return
        first, last = self.lines[start.line], self.lines[end.line]
        first.set_text(first.text[: start.index] + last.text[end.index:])
        if end.line > start.line:
            del self.lines[start.line + 1: end.line + 1]
        self.updated = True

    # -- queries -------------------------------------------------------- #
    @property
    def is_empty(self) -> bool:
        """True when the document is one empty line."""
        return len(self.lines) == 1 and not self.lines[0].text

    def __len__(self) -> int:
        """Number of lines."""
        return len(self.lines)

    def normalize(self, pos: Pos) -> Pos:
        """Clamp a position into the document.

        Every public entry point runs its arguments through this, which is why
        no algorithm below has to test bounds -- the reference does the same
        and for the same reason.
        """
        line = int(clamp(int(pos.line), 0, len(self.lines) - 1))
        return Pos(line, int(clamp(int(pos.index), 0, len(self.lines[line].text))))

    def top(self) -> Pos:
        """The very start."""
        return Pos(0, 0)

    def bottom(self) -> Pos:
        """The very end."""
        return Pos(len(self.lines) - 1, len(self.lines[-1].text))

    def start_of_line(self, pos: Pos) -> Pos:
        """Column zero of *pos*'s line."""
        return Pos(pos.line, 0)

    def end_of_line(self, pos: Pos) -> Pos:
        """Past the last character of *pos*'s line."""
        return Pos(pos.line, len(self.lines[pos.line].text))

    def left(self, pos: Pos, word_mode: bool = False) -> Pos:
        """One character (or one word) to the left, crossing a line boundary."""
        pos = self.normalize(pos)
        if word_mode:
            return self.find_word_start(self.left(pos))
        if pos.index > 0:
            return Pos(pos.line, pos.index - 1)
        if pos.line > 0:
            return self.end_of_line(Pos(pos.line - 1, 0))
        return pos

    def right(self, pos: Pos, word_mode: bool = False) -> Pos:
        """One character (or one word) to the right, crossing a line boundary."""
        pos = self.normalize(pos)
        if word_mode:
            return self.find_word_end(self.right(pos))
        if pos.index < len(self.lines[pos.line].text):
            return Pos(pos.line, pos.index + 1)
        if pos.line < len(self.lines) - 1:
            return Pos(pos.line + 1, 0)
        return pos

    @staticmethod
    def _is_word(char: str) -> bool:
        """Whether *char* can be part of a word."""
        return char.isalnum() or char == "_"

    def find_word_start(self, pos: Pos, word_only: bool = False) -> Pos:
        """Walk left to the start of the run *pos* is inside.

        A "run" is a word, or a stretch of whitespace, or a stretch of
        punctuation -- which is what makes ctrl+Left stop in the places a text
        editor is expected to stop.
        """
        pos = self.normalize(pos)
        text = self.lines[pos.line].text
        index = pos.index
        if index == 0:
            return pos
        kind = self._kind(text[index - 1])
        if word_only and kind != "word":
            return pos
        while index > 0 and self._kind(text[index - 1]) == kind:
            index -= 1
        return Pos(pos.line, index)

    def find_word_end(self, pos: Pos, word_only: bool = False) -> Pos:
        """Walk right to the end of the run *pos* is inside."""
        pos = self.normalize(pos)
        text = self.lines[pos.line].text
        index = pos.index
        if index >= len(text):
            return pos
        kind = self._kind(text[index])
        if word_only and kind != "word":
            return pos
        while index < len(text) and self._kind(text[index]) == kind:
            index += 1
        return Pos(pos.line, index)

    @classmethod
    def _kind(cls, char: str) -> str:
        """Which of the three run kinds *char* belongs to."""
        if char.isspace():
            return "space"
        return "word" if cls._is_word(char) else "punct"

    def word_at(self, pos: Pos) -> str:
        """The word under a position, or ``""`` if it is not on one."""
        pos = self.normalize(pos)
        start = self.find_word_start(pos, word_only=True)
        end = self.find_word_end(pos, word_only=True)
        return self.lines[pos.line].text[start.index:end.index]

    def is_whole_word(self, start: Pos, end: Pos) -> bool:
        """Whether a range is bounded by non-word characters on both sides."""
        if start.line != end.line:
            return False
        text = self.lines[start.line].text
        before = start.index == 0 or not self._is_word(text[start.index - 1])
        after = end.index >= len(text) or not self._is_word(text[end.index])
        return before and after

    def find_text(
        self,
        origin: Pos,
        needle: str,
        case_sensitive: bool = True,
        whole_word: bool = False,
    ) -> tuple[Pos, Pos] | None:
        """Search forward from *origin*, wrapping once at the end.

        Parameters
        ----------
        origin : Pos
            Where to start looking.
        needle : str
            What to look for. May contain newlines.
        case_sensitive : bool, optional
            Whether case must match.
        whole_word : bool, optional
            Whether the match must be bounded by non-word characters.

        Returns
        -------
        tuple of Pos, or None
            ``(start, end)`` of the first match, or ``None``.

        Notes
        -----
        The wrap is what makes "find next" reach a match above the caret, and
        it is bounded: the scan visits every line once and then the origin's
        line again, so a needle that is not there terminates rather than
        looping. The reference wraps in the same place.
        """
        if not needle:
            return None
        haystack = self.get_text()
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.escape(needle)
        if whole_word:
            pattern = rf"\b{pattern}\b"
        offset = self._offset_of(origin)
        found = re.compile(pattern, flags).search(haystack, offset)
        if found is None:
            found = re.compile(pattern, flags).search(haystack, 0, offset + len(needle))
        if found is None:
            return None
        return self._pos_of(found.start()), self._pos_of(found.end())

    def find_all(
        self,
        needle: str,
        case_sensitive: bool = True,
        whole_word: bool = False,
    ) -> list[tuple[Pos, Pos]]:
        """Every occurrence in the document, in order."""
        if not needle:
            return []
        haystack = self.get_text()
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.escape(needle)
        if whole_word:
            pattern = rf"\b{pattern}\b"
        return [
            (self._pos_of(one.start()), self._pos_of(one.end()))
            for one in re.finditer(pattern, haystack, flags)
        ]

    def _offset_of(self, pos: Pos) -> int:
        """Character offset of a position in :meth:`get_text`'s string."""
        pos = self.normalize(pos)
        return sum(len(self.lines[one].text) + 1 for one in range(pos.line)) + pos.index

    def _pos_of(self, offset: int) -> Pos:
        """Inverse of :meth:`_offset_of`."""
        for number, line in enumerate(self.lines):
            if offset <= len(line.text):
                return Pos(number, offset)
            offset -= len(line.text) + 1
        return self.bottom()

    def identifiers(self) -> set[str]:
        """Every run the colouriser marked as an identifier.

        The reference exposes this so an application can feed autocomplete.
        There is no autocomplete here, but the cmtk command line's completion
        can use it, and it is three lines given the colour array already exists.
        """
        found: set[str] = set()
        wanted = {int(Token.IDENTIFIER), int(Token.KNOWN_IDENTIFIER)}
        for line in self.lines:
            start = None
            for index, colour in enumerate(line.colours):
                if colour in wanted:
                    if start is None:
                        start = index
                elif start is not None:
                    found.add(line.text[start:index])
                    start = None
            if start is not None:
                found.add(line.text[start:])
        return found


# --------------------------------------------------------------------------
# Colorizer
# --------------------------------------------------------------------------
class Colorizer:
    """The overlay that decides each character's :class:`Token`.

    A transcription of the reference's ``Colorizer::updateLine``, one branch
    per line state, scanning left to right and never backing up. The only
    change is representational: where the reference advances a glyph iterator
    and calls ``setColor`` on a range, this advances an integer and calls
    :meth:`Line.paint`.
    """

    def __init__(self) -> None:
        self._language: Language | None = None

    def update(self, config: EditorConfig, document: Document) -> bool:
        """Re-colour whatever needs it.

        Parameters
        ----------
        config : EditorConfig
            Read for its ``language``. A language *change* invalidates every
            line; otherwise only lines flagged ``needs_colorizing`` are done.
        document : Document
            The document to colour, in place.

        Returns
        -------
        bool
            Whether the language changed, which is what tells the caller its
            other overlays (brackets) are stale too.
        """
        changed = self._language is not config.language
        self._language = config.language
        if not changed and not document.updated:
            return False

        if self._language is None:
            for line in document.lines:
                line.colours = bytearray(len(line.text))
                line.state = LineState.IN_TEXT
                line.needs_colorizing = False
            return changed

        for number, line in enumerate(document.lines):
            if not changed and not line.needs_colorizing:
                continue
            state = self._update_line(line)
            line.needs_colorizing = False
            if number + 1 < len(document.lines):
                following = document.lines[number + 1]
                if following.state != state:
                    following.state = state
                    following.needs_colorizing = True
        return changed

    # ------------------------------------------------------------------ #
    def _update_line(self, line: Line) -> LineState:
        """Colour one line; return the state the next line starts in."""
        language = self._language
        assert language is not None
        text = line.text
        line.colours = bytearray(len(text))
        state = line.state
        index = 0
        end = len(text)
        non_whitespace = False

        while index < end:
            start = index

            if state == LineState.IN_TEXT:
                if (
                    not non_whitespace
                    and language.preprocess
                    and text[index] != language.preprocess
                    and not text[index].isspace()
                ):
                    non_whitespace = True

                index, state = self._scan_text(line, text, index, end, state)
                if index == start:
                    index = self._scan_token(line, text, index, end, non_whitespace)

            elif state == LineState.IN_COMMENT:
                closer = language.comment_end
                if closer and text.startswith(closer, index):
                    line.paint(index, index + len(closer), Token.COMMENT)
                    index += len(closer)
                    state = LineState.IN_TEXT
                else:
                    line.paint(index, index + 1, Token.COMMENT)
                    index += 1

            else:
                index, state = self._scan_string(line, text, index, end, state)

        return state

    def _scan_text(
        self, line: Line, text: str, index: int, end: int, state: LineState
    ) -> tuple[int, LineState]:
        """Handle the openers a line in ``IN_TEXT`` can hit.

        Returns the (possibly unchanged) index and state; an unchanged index
        means nothing matched and the caller should tokenise instead. That
        two-step is the reference's ``if (glyph == start)`` chain, made
        explicit.
        """
        language = self._language
        assert language is not None
        char = text[index]

        if char.isspace():
            line.paint(index, index + 1, Token.WHITESPACE)
            return index + 1, state
        if language.comment_start and text.startswith(language.comment_start, index):
            size = len(language.comment_start)
            line.paint(index, index + size, Token.COMMENT)
            return index + size, LineState.IN_COMMENT
        for opener in (language.single_line_comment, language.single_line_comment_alt):
            if opener and text.startswith(opener, index):
                line.paint(index, end, Token.COMMENT)
                return end, state
        # The triple quotes must be tested before the single character ones,
        # or Python's ``"""`` opens and immediately closes an empty string.
        if language.other_string_start and text.startswith(language.other_string_start, index):
            size = len(language.other_string_start)
            line.paint(index, index + size, Token.STRING)
            return index + size, LineState.IN_OTHER_STRING
        if language.other_string_alt_start and text.startswith(
            language.other_string_alt_start, index
        ):
            size = len(language.other_string_alt_start)
            line.paint(index, index + size, Token.STRING)
            return index + size, LineState.IN_OTHER_STRING_ALT
        if language.has_single_quoted_strings and char == "'":
            line.paint(index, index + 1, Token.STRING)
            return index + 1, LineState.IN_SINGLE_QUOTED_STRING
        if language.has_double_quoted_strings and char == '"':
            line.paint(index, index + 1, Token.STRING)
            return index + 1, LineState.IN_DOUBLE_QUOTED_STRING
        if language.preprocess and char == language.preprocess and not _has_code_before(
            text, index
        ):
            line.paint(0, end, Token.PREPROCESSOR)
            return end, state
        return index, state

    def _scan_token(
        self, line: Line, text: str, index: int, end: int, non_whitespace: bool
    ) -> int:
        """Tokenise an identifier, a number or a punctuation character."""
        language = self._language
        assert language is not None

        if language.identifier_pattern is not None:
            found = language.identifier_pattern.match(text, index)
            if found is not None and found.end() > index:
                word = found.group()
                key = word if language.case_sensitive else word.lower()
                if key in language.keywords:
                    token = Token.KEYWORD
                elif key in language.declarations:
                    token = Token.DECLARATION
                elif key in language.identifiers:
                    token = Token.KNOWN_IDENTIFIER
                else:
                    token = Token.IDENTIFIER
                line.paint(index, found.end(), token)
                return found.end()

        if language.number_pattern is not None:
            found = language.number_pattern.match(text, index)
            if found is not None and found.end() > index:
                line.paint(index, found.end(), Token.NUMBER)
                return found.end()

        if text[index] in language.punctuation:
            line.paint(index, index + 1, Token.PUNCTUATION)
            return index + 1

        line.paint(index, index + 1, Token.TEXT)
        return index + 1

    def _scan_string(
        self, line: Line, text: str, index: int, end: int, state: LineState
    ) -> tuple[int, LineState]:
        """Stay inside a string until its closer, honouring the escape character."""
        language = self._language
        assert language is not None
        closers = {
            LineState.IN_SINGLE_QUOTED_STRING: "'",
            LineState.IN_DOUBLE_QUOTED_STRING: '"',
            LineState.IN_OTHER_STRING: language.other_string_end,
            LineState.IN_OTHER_STRING_ALT: language.other_string_alt_end,
        }
        closer = closers.get(state, "")

        escape = language.string_escape
        if escape and text[index] == escape:
            line.paint(index, min(index + 2, end), Token.STRING)
            return min(index + 2, end), state
        if closer and text.startswith(closer, index):
            line.paint(index, index + len(closer), Token.STRING)
            return index + len(closer), LineState.IN_TEXT
        line.paint(index, index + 1, Token.STRING)
        return index + 1, state


def _has_code_before(text: str, index: int) -> bool:
    """Whether anything other than whitespace precedes *index* on the line."""
    return bool(text[:index].strip())


# --------------------------------------------------------------------------
# Cursors
# --------------------------------------------------------------------------
class Cursor:
    """One caret, which is an anchor and a head.

    The pair is ordered by *interaction*, not by position: ``start`` is where
    the selection was anchored and ``end`` is where the caret is, so dragging
    leftwards gives ``start > end``. :meth:`selection` puts them back in
    document order for anything that reads the text.
    """

    __slots__ = ("start", "end", "main", "current", "preferred_column")

    def __init__(self, start: Pos = Pos(), end: Pos | None = None) -> None:
        self.start = start
        self.end = start if end is None else end
        self.main = False
        self.current = True
        #: Survives a run of up/down moves so the caret comes back to the
        #: column it left -- the reference's ``preferredColumn``, and the same
        #: trap :class:`~.inputs.InputTextMultiline` documents.
        self.preferred_column = 0

    def __repr__(self) -> str:
        """Debug representation."""
        return f"Cursor({tuple(self.start)}, {tuple(self.end)})"

    def update(self, pos: Pos, keep_selection: bool = False) -> None:
        """Move the caret; ``keep_selection`` leaves the anchor where it was."""
        self.end = pos
        if not keep_selection:
            self.start = pos

    @property
    def has_selection(self) -> bool:
        """Whether anything is selected."""
        return self.start != self.end

    def selection(self) -> tuple[Pos, Pos]:
        """The selection in document order."""
        return (self.start, self.end) if self.start <= self.end else (self.end, self.start)

    def grow(self, pos: Pos) -> None:
        """Extend the selection outwards to cover *pos*."""
        low, high = self.selection()
        self.start = min(low, pos)
        self.end = max(high, pos)


class Cursors(list):
    """The list of carets, with a *main* and a *current* one.

    The distinction is the reference's and it matters: the **main** cursor is
    the one the view scrolls to follow, and the **current** one is the most
    recently added, which is the one a "next occurrence" search continues from.
    They are usually the same and are not when multi-cursor is in use.
    """

    def __init__(self) -> None:
        super().__init__()
        self._main = 0
        self._current = 0
        self.clear_all()

    # ------------------------------------------------------------------ #
    def clear_all(self) -> None:
        """Drop every caret and leave one at the top."""
        del self[:]
        one = Cursor()
        one.main = True
        self.append(one)
        self._main = self._current = 0

    def clear_additional(self) -> None:
        """Keep only the main caret."""
        keep = self[self._main]
        del self[:]
        self.append(keep)
        self._main = self._current = 0

    def set_cursor(self, start: Pos, end: Pos | None = None) -> None:
        """Replace every caret with one."""
        del self[:]
        one = Cursor(start, end)
        one.main = True
        self.append(one)
        self._main = self._current = 0

    def add_cursor(self, start: Pos, end: Pos | None = None) -> Cursor:
        """Add a caret and make it the current one."""
        one = Cursor(start, end)
        self.append(one)
        self._current = len(self) - 1
        return one

    # ------------------------------------------------------------------ #
    @property
    def main(self) -> Cursor:
        """The caret the view follows."""
        return self[min(self._main, len(self) - 1)]

    @property
    def current(self) -> Cursor:
        """The most recently added caret."""
        return self[min(self._current, len(self) - 1)]

    @property
    def any_has_selection(self) -> bool:
        """Whether at least one caret has a selection."""
        return any(one.has_selection for one in self)

    @property
    def all_have_selection(self) -> bool:
        """Whether every caret has a selection."""
        return all(one.has_selection for one in self)

    def in_document_order(self) -> list[Cursor]:
        """The carets sorted by where their selection starts."""
        return sorted(self, key=lambda one: one.selection()[0])

    def merge_overlapping(self) -> None:
        """Collapse carets whose selections touch.

        Two carets on the same character are two of everything -- two inserts
        for one keystroke -- so the moment a move brings them together they
        become one. The reference does this in ``Cursors::update``; doing it
        anywhere later means the duplicate edit has already happened.
        """
        if len(self) < 2:
            return
        ordered = self.in_document_order()
        kept: list[Cursor] = [ordered[0]]
        for one in ordered[1:]:
            low, high = kept[-1].selection()
            other_low, other_high = one.selection()
            if other_low <= high:
                kept[-1].start = min(low, other_low)
                kept[-1].end = max(high, other_high)
                if one.main:
                    kept[-1].main = True
            else:
                kept.append(one)
        del self[:]
        self.extend(kept)
        self._main = next((i for i, one in enumerate(self) if one.main), 0)
        self[self._main].main = True
        self._current = min(self._current, len(self) - 1)


# --------------------------------------------------------------------------
# Transactions -- undo and redo
# --------------------------------------------------------------------------
@dataclass
class Action:
    """One insert or delete, with enough information to be run backwards."""

    insert: bool
    start: Pos
    end: Pos
    text: str


@dataclass
class Transaction:
    """Everything one user gesture did, plus the caret state either side.

    Restoring the carets is half of what makes undo feel right: undoing a
    multi-cursor edit must put the carets back, or the next keystroke lands
    somewhere the user did not leave them.
    """

    actions: list[Action] = field(default_factory=list)
    before: list[tuple[Pos, Pos]] = field(default_factory=list)
    after: list[tuple[Pos, Pos]] = field(default_factory=list)

    def add_insert(self, start: Pos, end: Pos, text: str) -> None:
        """Record an insertion."""
        self.actions.append(Action(True, start, end, text))

    def add_delete(self, start: Pos, end: Pos, text: str) -> None:
        """Record a deletion."""
        self.actions.append(Action(False, start, end, text))

    def __bool__(self) -> bool:
        """Whether anything was recorded."""
        return bool(self.actions)


class Transactions(list):
    """The undo stack: a list of transactions and an index into it."""

    def __init__(self) -> None:
        super().__init__()
        self.undo_index = 0

    def reset(self) -> None:
        """Forget everything -- what loading a new document does."""
        del self[:]
        self.undo_index = 0

    def add(self, transaction: Transaction) -> None:
        """Push a transaction, discarding any that were undone.

        Discarding the redo tail is what makes the stack linear: typing after
        an undo means the redone future never happened.
        """
        del self[self.undo_index:]
        self.append(transaction)
        self.undo_index = len(self)

    @property
    def can_undo(self) -> bool:
        """Whether there is anything to undo."""
        return self.undo_index > 0

    @property
    def can_redo(self) -> bool:
        """Whether there is anything to redo."""
        return self.undo_index < len(self)

    def undo(self, document: Document, cursors: Cursors) -> bool:
        """Run the last transaction backwards."""
        if not self.can_undo:
            return False
        self.undo_index -= 1
        transaction = self[self.undo_index]
        for action in reversed(transaction.actions):
            if action.insert:
                document.delete_text(action.start, action.end)
            else:
                document.insert_text(action.start, action.text)
        _restore(cursors, transaction.before)
        return True

    def redo(self, document: Document, cursors: Cursors) -> bool:
        """Run the next transaction forwards again."""
        if not self.can_redo:
            return False
        transaction = self[self.undo_index]
        self.undo_index += 1
        for action in transaction.actions:
            if action.insert:
                document.insert_text(action.start, action.text)
            else:
                document.delete_text(action.start, action.end)
        _restore(cursors, transaction.after)
        return True


def _restore(cursors: Cursors, state: Sequence[tuple[Pos, Pos]]) -> None:
    """Put the carets back where a transaction recorded them."""
    if not state:
        return
    del cursors[:]
    for index, (start, end) in enumerate(state):
        one = Cursor(start, end)
        one.main = index == 0
        cursors.append(one)
    cursors._main = 0  # noqa: SLF001 -- Cursors is this module's own type
    cursors._current = len(cursors) - 1  # noqa: SLF001


# --------------------------------------------------------------------------
# Bracketeer
# --------------------------------------------------------------------------
class BracketPair(NamedTuple):
    """A matched pair, its nesting level, and whether it is real.

    ``visible`` is false for the pairs inferred from indentation in a language
    like Python, which have no characters to draw on but still answer "what
    block am I in".
    """

    open_char: str
    start: Pos
    close_char: str
    end: Pos
    level: int
    visible: bool

    def surrounds(self, pos: Pos) -> bool:
        """Whether *pos* is inside this pair."""
        return self.start < pos <= self.end


class Bracketeer(list):
    """Where the bracket pairs are, so they can be coloured and jumped between.

    Only characters the colouriser called punctuation are considered, which is
    what keeps a ``)`` inside a comment or a string from matching -- the
    reference's ``isBracketCandidate``, and the reason this overlay runs after
    the colouriser rather than beside it.
    """

    _OPENERS = "([{"
    _CLOSERS = ")]}"
    _MATCH = {")": "(", "]": "[", "}": "{"}

    def update(self, config: EditorConfig, document: Document) -> None:
        """Rebuild the pair list and re-colour the brackets by nesting level."""
        del self[:]
        if not config.show_matching_brackets:
            return
        candidates = {int(Token.PUNCTUATION), int(Token.BRACKET_LEVEL1),
                      int(Token.BRACKET_LEVEL2), int(Token.BRACKET_LEVEL3),
                      int(Token.BRACKET_ERROR)}
        stack: list[tuple[str, Pos]] = []
        for number, line in enumerate(document.lines):
            for index, char in enumerate(line.text):
                if index >= len(line.colours) or line.colours[index] not in candidates:
                    continue
                here = Pos(number, index)
                if char in self._OPENERS:
                    stack.append((char, here))
                elif char in self._CLOSERS:
                    if stack and stack[-1][0] == self._MATCH[char]:
                        open_char, open_pos = stack.pop()
                        level = len(stack)
                        self.append(
                            BracketPair(open_char, open_pos, char, here, level, True)
                        )
                        token = _level_token(level)
                        document.lines[open_pos.line].paint(
                            open_pos.index, open_pos.index + 1, token
                        )
                        line.paint(index, index + 1, token)
                    else:
                        line.paint(index, index + 1, Token.BRACKET_ERROR)
        for _char, pos in stack:
            document.lines[pos.line].paint(pos.index, pos.index + 1, Token.BRACKET_ERROR)
        self.sort(key=lambda pair: pair.start)

    def enclosing(self, pos: Pos) -> BracketPair | None:
        """The innermost pair around *pos*, or ``None``."""
        best: BracketPair | None = None
        for pair in self:
            if pair.surrounds(pos) and (best is None or pair.level >= best.level):
                best = pair
        return best

    def at(self, pos: Pos) -> BracketPair | None:
        """The pair whose opener or closer is exactly at *pos*."""
        for pair in self:
            if pos in (pair.start, pair.end):
                return pair
        return None


def _level_token(level: int) -> Token:
    """Which of the three bracket colours a nesting level uses."""
    return (Token.BRACKET_LEVEL1, Token.BRACKET_LEVEL2, Token.BRACKET_LEVEL3)[level % 3]


# --------------------------------------------------------------------------
# The control
# --------------------------------------------------------------------------
@dataclass
class EditorConfig:
    """The editor's options, straight from the reference's ``Config``."""

    tab_size: int = 4
    insert_spaces_on_tabs: bool = True
    line_spacing: float = 1.0
    read_only: bool = False
    carets_visible: bool = True
    auto_indent: bool = True
    show_spaces: bool = False
    show_tabs: bool = False
    show_line_numbers: bool = True
    show_matching_brackets: bool = True
    complete_paired_glyphs: bool = True
    overwrite: bool = False
    left_margin: int = 1
    text_margin: int = 2
    language: Language | None = None


#: The glyphs drawn for a space and a tab when whitespace is shown.
#:
#: The reference uses ``→`` for a tab, and that glyph is **not baked into the
#: chrome's atlas** -- so it draws perfectly through the Qt painter and as
#: nothing at all through the GPU one, which is precisely the asymmetry
#: ``test_chrome_atlas.py`` exists to catch. ``»`` is baked, is the mark Vim
#: uses for the same job, and is narrower.
_SPACE_MARK = "·"
_TAB_MARK = "»"


class TextEditor:
    """A colourising, multi-cursor text editor drawn with a :class:`Painter`.

    Follows the package contract: construct it, :meth:`draw` it into a box,
    hand it the presses that land in that box, and feed it keys.

    Parameters
    ----------
    text : str, optional
        Initial contents.
    language : Language, optional
        What to colourise as. ``None`` draws everything as plain text.
    read_only : bool, optional
        A read-only editor still selects, copies, searches and scrolls -- the
        reference made that choice deliberately and it is what makes this
        usable as a log or a shader viewer.

    Notes
    -----
    The layout assumes a **monospaced** font, as the reference does: column
    *n* is at ``n * text_width("W")``. The chrome's font is Menlo, so this
    holds; a proportional font would need a per-character measure and the cost
    would land on every frame.
    """

    def __init__(
        self,
        text: str = "",
        language: Language | None = None,
        read_only: bool = False,
    ) -> None:
        self.config = EditorConfig(language=language, read_only=read_only)
        self.palette: tuple[Colour, ...] = DARK_PALETTE
        self.document = Document(text)
        self.cursors = Cursors()
        self.transactions = Transactions()
        self.colorizer = Colorizer()
        self.bracketeer = Bracketeer()

        #: First document line drawn, and first column drawn.
        self.first_visible_line = 0
        self.first_visible_column = 0
        #: Filled in by :meth:`draw`; read by :meth:`press` and the scrollers.
        self.visible_lines = 1
        self.visible_columns = 1
        self._glyph_w = 8.0
        self._line_h = 14.0
        self._text_x = 0.0
        self._body_y = 0.0
        self._dragging = False
        #: The vertical scrollbar, drawn when the file is taller than the box.
        self.vbar = ScrollBar()
        self._bar_drag = False
        #: What :meth:`copy` last put somewhere, so a host without a system
        #: clipboard still round-trips a cut and paste.
        self.clipboard = ""
        self._find_text = ""
        self._find_case_sensitive = True
        self._find_whole_word = False
        self._changed = False

    # -- text ----------------------------------------------------------- #
    @property
    def text(self) -> str:
        """The whole document."""
        return self.document.get_text()

    @text.setter
    def text(self, value: str) -> None:
        self.set_text(value)

    def set_text(self, text: str) -> None:
        """Replace the document and reset every piece of state that hung off it.

        Undo history included -- undoing across a document load would restore
        half of one file into another.
        """
        self.document.set_text(text)
        self.cursors.clear_all()
        self.transactions.reset()
        self.first_visible_line = 0
        self.first_visible_column = 0
        self._changed = False

    @property
    def line_count(self) -> int:
        """Number of lines."""
        return len(self.document)

    @property
    def is_empty(self) -> bool:
        """Whether the document is one empty line."""
        return self.document.is_empty

    @property
    def modified(self) -> bool:
        """Whether anything has been edited since the last :meth:`set_text` (or :meth:`mark_saved`)."""
        return self._changed

    def mark_saved(self) -> None:
        """The buffer was written out: not modified until the next edit."""
        self._changed = False

    def set_language(self, language: Language | None) -> None:
        """Change the language; every line is re-colourised on the next draw."""
        self.config.language = language
        for line in self.document.lines:
            line.needs_colorizing = True
        self.document.updated = True

    @property
    def language_name(self) -> str:
        """The current language's name, or ``"None"``."""
        return self.config.language.name if self.config.language else "None"

    def selected_text(self) -> str:
        """Every caret's selection, joined by newlines."""
        parts = []
        for one in self.cursors.in_document_order():
            low, high = one.selection()
            if low != high:
                parts.append(self.document.get_section_text(low, high))
        return "\n".join(parts)

    # -- cursors -------------------------------------------------------- #
    def set_cursor(self, pos: Pos) -> None:
        """Put a single caret somewhere and scroll it into view."""
        self.cursors.set_cursor(self.document.normalize(pos))
        self._follow_main()

    def select_all(self) -> None:
        """Select the whole document with one caret."""
        self.cursors.set_cursor(self.document.top(), self.document.bottom())

    def select_line(self, line: int) -> None:
        """Select one whole line."""
        line = int(clamp(int(line), 0, len(self.document) - 1))
        self.cursors.set_cursor(Pos(line, 0), self.document.end_of_line(Pos(line, 0)))

    def select_region(self, start: Pos, end: Pos) -> None:
        """Select an arbitrary range."""
        self.cursors.set_cursor(self.document.normalize(start), self.document.normalize(end))

    def select_word_at(self, pos: Pos) -> None:
        """Select the word under a position."""
        pos = self.document.normalize(pos)
        self.cursors.set_cursor(
            self.document.find_word_start(pos), self.document.find_word_end(pos)
        )

    def add_next_occurrence(self) -> bool:
        """Add a caret on the next copy of the current selection.

        This is the multi-cursor gesture people actually use (ctrl+D), and it
        is why :class:`Cursors` distinguishes *current* from *main*: each press
        continues from the caret the previous press added, not from the first.

        Returns
        -------
        bool
            Whether another occurrence was found.
        """
        one = self.cursors.current
        low, high = one.selection()
        if low == high:
            self.select_word_at(low)
            return True
        needle = self.document.get_section_text(low, high)
        found = self.document.find_text(high, needle, True, False)
        if found is None or found[0] == low:
            return False
        self.cursors.add_cursor(*found)
        self._follow_main()
        return True

    def select_all_occurrences(self) -> int:
        """Put a caret on every copy of the current selection.

        Returns
        -------
        int
            How many carets there now are.
        """
        one = self.cursors.current
        low, high = one.selection()
        if low == high:
            self.select_word_at(low)
            one = self.cursors.current
            low, high = one.selection()
        needle = self.document.get_section_text(low, high)
        matches = self.document.find_all(needle, True, False)
        if not matches:
            return len(self.cursors)
        self.cursors.set_cursor(*matches[0])
        for start, end in matches[1:]:
            self.cursors.add_cursor(start, end)
        return len(self.cursors)

    def select_to_brackets(self, include_brackets: bool = True) -> bool:
        """Grow every caret to the bracket pair enclosing it."""
        grew = False
        for one in self.cursors:
            pair = self.bracketeer.enclosing(one.selection()[0])
            if pair is None:
                continue
            if include_brackets:
                one.start, one.end = pair.start, self.document.right(pair.end)
            else:
                one.start, one.end = self.document.right(pair.start), pair.end
            grew = True
        return grew

    # -- editing -------------------------------------------------------- #
    def _begin(self) -> Transaction:
        """Start a transaction, recording where the carets are."""
        transaction = Transaction()
        transaction.before = [(one.start, one.end) for one in self.cursors]
        return transaction

    def _commit(self, transaction: Transaction) -> None:
        """Finish a transaction and push it, if it did anything."""
        if not transaction:
            return
        transaction.after = [(one.start, one.end) for one in self.cursors]
        self.transactions.add(transaction)
        self._changed = True
        self._follow_main()

    def _delete_selection(self, transaction: Transaction, cursor: Cursor) -> Pos:
        """Delete one caret's selection; return where the caret lands."""
        low, high = cursor.selection()
        if low == high:
            return low
        text = self.document.get_section_text(low, high)
        self.document.delete_text(low, high)
        transaction.add_delete(low, high, text)
        cursor.update(low)
        return low

    def insert(self, text: str) -> None:
        """Type text at every caret.

        Carets are processed **last first**. An insert shifts every position
        after it, so editing forwards would leave the later carets pointing at
        stale offsets; editing backwards means each edit only touches text no
        remaining caret has yet used. That is the whole multi-cursor
        correctness argument, and it is cheaper than the reference's
        ``adjustForInsert`` bookkeeping.
        """
        if self.config.read_only or not text:
            return
        transaction = self._begin()
        for one in sorted(self.cursors, key=lambda c: c.selection()[0], reverse=True):
            start = self._delete_selection(transaction, one)
            if self.config.overwrite and "\n" not in text:
                line = self.document.lines[start.line]
                room = min(len(text), len(line.text) - start.index)
                if room > 0:
                    over = Pos(start.line, start.index + room)
                    transaction.add_delete(
                        start, over, self.document.get_section_text(start, over)
                    )
                    self.document.delete_text(start, over)
            end = self.document.insert_text(start, text)
            transaction.add_insert(start, end, text)
            one.update(end)
        self.cursors.merge_overlapping()
        self._commit(transaction)

    def newline(self) -> None:
        """Insert a line break at every caret, carrying the indent when asked."""
        if self.config.read_only:
            return
        transaction = self._begin()
        for one in sorted(self.cursors, key=lambda c: c.selection()[0], reverse=True):
            start = self._delete_selection(transaction, one)
            body = "\n"
            if self.config.auto_indent:
                current = self.document.lines[start.line].text
                indent = current[: len(current) - len(current.lstrip(" \t"))]
                body += indent[: start.index]
            end = self.document.insert_text(start, body)
            transaction.add_insert(start, end, body)
            one.update(end)
        self.cursors.merge_overlapping()
        self._commit(transaction)

    def backspace(self) -> None:
        """Delete backwards at every caret."""
        if self.config.read_only:
            return
        transaction = self._begin()
        for one in sorted(self.cursors, key=lambda c: c.selection()[0], reverse=True):
            if one.has_selection:
                self._delete_selection(transaction, one)
                continue
            here = one.end
            start = self.document.left(here)
            if start == here:
                continue
            text = self.document.get_section_text(start, here)
            self.document.delete_text(start, here)
            transaction.add_delete(start, here, text)
            one.update(start)
        self.cursors.merge_overlapping()
        self._commit(transaction)

    def delete(self) -> None:
        """Delete forwards at every caret."""
        if self.config.read_only:
            return
        transaction = self._begin()
        for one in sorted(self.cursors, key=lambda c: c.selection()[0], reverse=True):
            if one.has_selection:
                self._delete_selection(transaction, one)
                continue
            here = one.end
            end = self.document.right(here)
            if end == here:
                continue
            text = self.document.get_section_text(here, end)
            self.document.delete_text(here, end)
            transaction.add_delete(here, end, text)
            one.update(here)
        self.cursors.merge_overlapping()
        self._commit(transaction)

    def replace_section(self, start: Pos, end: Pos, text: str) -> None:
        """Replace a range, as one undoable step."""
        if self.config.read_only:
            return
        start, end = self.document.normalize(start), self.document.normalize(end)
        transaction = self._begin()
        if start < end:
            old = self.document.get_section_text(start, end)
            self.document.delete_text(start, end)
            transaction.add_delete(start, end, old)
        if text:
            after = self.document.insert_text(start, text)
            transaction.add_insert(start, after, text)
            self.cursors.set_cursor(after)
        else:
            self.cursors.set_cursor(start)
        self._commit(transaction)

    # -- clipboard ------------------------------------------------------ #
    def copy(self) -> str:
        """Copy every selection; returns what was copied."""
        self.clipboard = self.selected_text()
        return self.clipboard

    def cut(self) -> str:
        """Copy then delete."""
        text = self.copy()
        if not self.config.read_only:
            transaction = self._begin()
            for one in sorted(self.cursors, key=lambda c: c.selection()[0], reverse=True):
                self._delete_selection(transaction, one)
            self.cursors.merge_overlapping()
            self._commit(transaction)
        return text

    def paste(self, text: str | None = None) -> None:
        """Insert the clipboard (or *text*) at every caret."""
        self.insert(self.clipboard if text is None else text)

    def undo(self) -> bool:
        """Undo one transaction."""
        if self.config.read_only:
            return False
        done = self.transactions.undo(self.document, self.cursors)
        if done:
            self._changed = True
            self._follow_main()
        return done

    def redo(self) -> bool:
        """Redo one transaction."""
        if self.config.read_only:
            return False
        done = self.transactions.redo(self.document, self.cursors)
        if done:
            self._changed = True
            self._follow_main()
        return done

    # -- line operations ------------------------------------------------ #
    def _selected_lines(self) -> list[int]:
        """Every line any caret touches, ascending and without duplicates."""
        touched: set[int] = set()
        for one in self.cursors:
            low, high = one.selection()
            end = high.line if (high.index or high.line == low.line) else high.line - 1
            touched.update(range(low.line, max(end, low.line) + 1))
        return sorted(touched)

    def _rewrite_lines(self, rewrite: Callable[[str], str]) -> None:
        """Apply *rewrite* to every touched line, as one undoable step."""
        if self.config.read_only:
            return
        transaction = self._begin()
        for number in reversed(self._selected_lines()):
            old = self.document.lines[number].text
            new = rewrite(old)
            if new == old:
                continue
            start, end = Pos(number, 0), Pos(number, len(old))
            self.document.delete_text(start, end)
            transaction.add_delete(start, end, old)
            after = self.document.insert_text(start, new)
            transaction.add_insert(start, after, new)
        self._clamp_cursors()
        self._commit(transaction)

    def indent_lines(self) -> None:
        """Indent every touched line by one tab stop."""
        pad = " " * self.config.tab_size if self.config.insert_spaces_on_tabs else "\t"
        self._rewrite_lines(lambda text: pad + text if text else text)

    def deindent_lines(self) -> None:
        """Remove one tab stop of leading whitespace from every touched line."""

        def strip(text: str) -> str:
            if text.startswith("\t"):
                return text[1:]
            room = len(text) - len(text.lstrip(" "))
            return text[min(room, self.config.tab_size):]

        self._rewrite_lines(strip)

    def toggle_comments(self) -> None:
        """Comment the touched lines, or uncomment them if all are commented.

        "All", not "any": a mixed block comments *in*, which is the behaviour
        every editor with this key has, and the alternative silently deletes a
        real ``#`` from a line that only looked commented.
        """
        prefix = self.config.language.comment_prefix if self.config.language else ""
        if not prefix or self.config.read_only:
            return
        numbers = self._selected_lines()
        texts = [self.document.lines[one].text for one in numbers]
        commented = all(
            not text.strip() or text.lstrip().startswith(prefix) for text in texts
        )

        def toggle(text: str) -> str:
            if not text.strip():
                return text
            room = len(text) - len(text.lstrip())
            head, body = text[:room], text[room:]
            if commented:
                if body.startswith(prefix + " "):
                    return head + body[len(prefix) + 1:]
                return head + body[len(prefix):] if body.startswith(prefix) else text
            return head + prefix + " " + body

        self._rewrite_lines(toggle)

    def move_lines(self, down: bool) -> None:
        """Move the touched lines up or down one, carrying the carets."""
        if self.config.read_only:
            return
        numbers = self._selected_lines()
        if not numbers:
            return
        first, last = numbers[0], numbers[-1]
        if (down and last >= len(self.document) - 1) or (not down and first == 0):
            return
        step = 1 if down else -1
        whole = self.document.get_text()
        transaction = self._begin()
        block = self.document.lines[first:last + 1]
        other = self.document.lines[last + 1] if down else self.document.lines[first - 1]
        if down:
            self.document.lines[first:last + 2] = [other, *block]
        else:
            self.document.lines[first - 1:last + 1] = [*block, other]
        for one in self.document.lines:
            one.needs_colorizing = True
        self.document.updated = True
        start, end = Pos(0, 0), self.document.bottom()
        transaction.add_delete(Pos(0, 0), self._pos_after(whole), whole)
        transaction.add_insert(start, end, self.document.get_text())
        for one in self.cursors:
            one.start = Pos(one.start.line + step, one.start.index)
            one.end = Pos(one.end.line + step, one.end.index)
        self._clamp_cursors()
        self._commit(transaction)

    def _pos_after(self, text: str) -> Pos:
        """The position at the end of *text*, treated as a whole document."""
        parts = text.split("\n")
        return Pos(len(parts) - 1, len(parts[-1]))

    def selection_to_upper(self) -> None:
        """Upper-case every selection."""
        self._filter_selections(str.upper)

    def selection_to_lower(self) -> None:
        """Lower-case every selection."""
        self._filter_selections(str.lower)

    def _filter_selections(self, filter_: Callable[[str], str]) -> None:
        """Rewrite every selection through *filter_*, as one undoable step."""
        if self.config.read_only:
            return
        transaction = self._begin()
        for one in sorted(self.cursors, key=lambda c: c.selection()[0], reverse=True):
            low, high = one.selection()
            if low == high:
                continue
            old = self.document.get_section_text(low, high)
            new = filter_(old)
            if new == old:
                continue
            self.document.delete_text(low, high)
            transaction.add_delete(low, high, old)
            end = self.document.insert_text(low, new)
            transaction.add_insert(low, end, new)
            one.start, one.end = low, end
        self._commit(transaction)

    def strip_trailing_whitespace(self) -> None:
        """Remove trailing spaces and tabs from every line."""
        if self.config.read_only:
            return
        transaction = self._begin()
        for number, line in enumerate(self.document.lines):
            stripped = line.text.rstrip(" \t")
            if stripped == line.text:
                continue
            start, end = Pos(number, len(stripped)), Pos(number, len(line.text))
            transaction.add_delete(start, end, line.text[len(stripped):])
            self.document.delete_text(start, end)
        self._clamp_cursors()
        self._commit(transaction)

    def tabs_to_spaces(self) -> None:
        """Replace every tab with ``tab_size`` spaces."""
        self._rewrite_all(lambda text: text.replace("\t", " " * self.config.tab_size))

    def spaces_to_tabs(self) -> None:
        """Replace runs of ``tab_size`` leading spaces with tabs."""
        size = self.config.tab_size

        def convert(text: str) -> str:
            room = len(text) - len(text.lstrip(" "))
            return "\t" * (room // size) + " " * (room % size) + text[room:]

        self._rewrite_all(convert)

    def _rewrite_all(self, rewrite: Callable[[str], str]) -> None:
        """Apply *rewrite* to every line in the document."""
        if self.config.read_only:
            return
        old = self.document.get_text()
        new = "\n".join(rewrite(line.text) for line in self.document.lines)
        if new == old:
            return
        transaction = self._begin()
        transaction.add_delete(Pos(0, 0), self._pos_after(old), old)
        self.document.set_text(new)
        transaction.add_insert(Pos(0, 0), self._pos_after(new), new)
        self._clamp_cursors()
        self._commit(transaction)

    def _clamp_cursors(self) -> None:
        """Pull every caret back inside the document after a bulk rewrite."""
        for one in self.cursors:
            one.start = self.document.normalize(one.start)
            one.end = self.document.normalize(one.end)

    # -- find and replace ----------------------------------------------- #
    def set_find_text(
        self, text: str, case_sensitive: bool = True, whole_word: bool = False
    ) -> None:
        """Remember what to search for, so :meth:`find_next` needs no arguments."""
        self._find_text = str(text)
        self._find_case_sensitive = bool(case_sensitive)
        self._find_whole_word = bool(whole_word)

    def find_next(self) -> bool:
        """Select the next occurrence of the remembered text."""
        if not self._find_text:
            return False
        found = self.document.find_text(
            self.cursors.current.selection()[1],
            self._find_text,
            self._find_case_sensitive,
            self._find_whole_word,
        )
        if found is None:
            return False
        self.cursors.set_cursor(*found)
        self._follow_main()
        return True

    def find_all(self) -> int:
        """Put a caret on every occurrence of the remembered text."""
        matches = self.document.find_all(
            self._find_text, self._find_case_sensitive, self._find_whole_word
        )
        if not matches:
            return 0
        self.cursors.set_cursor(*matches[0])
        for start, end in matches[1:]:
            self.cursors.add_cursor(start, end)
        self._follow_main()
        return len(matches)

    def replace_current(self, text: str) -> bool:
        """Replace the current selection."""
        one = self.cursors.current
        low, high = one.selection()
        if low == high:
            return False
        self.replace_section(low, high, text)
        return True

    def replace_all(self, text: str) -> int:
        """Replace every occurrence of the remembered text.

        Returns
        -------
        int
            How many were replaced.
        """
        if self.config.read_only or not self._find_text:
            return 0
        matches = self.document.find_all(
            self._find_text, self._find_case_sensitive, self._find_whole_word
        )
        if not matches:
            return 0
        transaction = self._begin()
        for start, end in reversed(matches):
            old = self.document.get_section_text(start, end)
            self.document.delete_text(start, end)
            transaction.add_delete(start, end, old)
            if text:
                after = self.document.insert_text(start, text)
                transaction.add_insert(start, after, text)
        self._clamp_cursors()
        self._commit(transaction)
        return len(matches)

    # -- markers -------------------------------------------------------- #
    def add_marker(
        self,
        line: int,
        number_colour: Colour,
        text_colour: Colour,
        tooltip: str = "",
    ) -> None:
        """Flag a line -- an error, a breakpoint, a hit.

        Markers are attached to the *line object*, so an insert above them
        moves them with the line and a delete takes them with it. The reference
        warns that undo does not bring a deleted marker back; neither does this.
        """
        line = int(clamp(int(line), 0, len(self.document) - 1))
        self.document.lines[line].marker = (number_colour, text_colour, str(tooltip))

    def clear_markers(self) -> None:
        """Remove every marker."""
        for line in self.document.lines:
            line.marker = None

    # -- movement ------------------------------------------------------- #
    def move_left(self, select: bool = False, word: bool = False) -> None:
        """Move every caret left."""
        self._move(lambda pos: self.document.left(pos, word), select)

    def move_right(self, select: bool = False, word: bool = False) -> None:
        """Move every caret right."""
        self._move(lambda pos: self.document.right(pos, word), select)

    def move_up(self, select: bool = False, lines: int = 1) -> None:
        """Move every caret up, keeping its preferred column."""
        self._move_vertically(-int(lines), select)

    def move_down(self, select: bool = False, lines: int = 1) -> None:
        """Move every caret down, keeping its preferred column."""
        self._move_vertically(int(lines), select)

    def move_home(self, select: bool = False, document: bool = False) -> None:
        """Move to the start of the line -- or of the document."""
        if document:
            self._move(lambda _pos: self.document.top(), select)
        else:
            self._move(self._smart_home, select)

    def move_end(self, select: bool = False, document: bool = False) -> None:
        """Move to the end of the line -- or of the document."""
        if document:
            self._move(lambda _pos: self.document.bottom(), select)
        else:
            self._move(self.document.end_of_line, select)

    def _smart_home(self, pos: Pos) -> Pos:
        """Home goes to the first non-blank character, then to column zero.

        Not the reference's behaviour -- it goes straight to column zero -- and
        a deliberate improvement: in indented code column zero is almost never
        where the line begins, and the second press still reaches it.
        """
        text = self.document.lines[pos.line].text
        first = len(text) - len(text.lstrip())
        return Pos(pos.line, 0 if pos.index == first else first)

    def _move(self, step: Callable[[Pos], Pos], select: bool) -> None:
        """Apply *step* to every caret's head."""
        for one in self.cursors:
            if one.has_selection and not select:
                low, high = one.selection()
                one.update(low if step(low) <= low else high)
            else:
                one.update(step(one.end), select)
            one.preferred_column = one.end.index
        self.cursors.merge_overlapping()
        self._follow_main()

    def _move_vertically(self, lines: int, select: bool) -> None:
        """Move every caret *lines* rows, restoring the preferred column."""
        for one in self.cursors:
            wanted = max(one.preferred_column, one.end.index)
            line = int(clamp(one.end.line + lines, 0, len(self.document) - 1))
            index = min(wanted, len(self.document.lines[line].text))
            one.update(Pos(line, index), select)
            one.preferred_column = wanted
        self.cursors.merge_overlapping()
        self._follow_main()

    # -- scrolling ------------------------------------------------------ #
    def scroll(self, lines: int) -> int:
        """Scroll vertically by *lines*; returns the new first visible line."""
        highest = max(len(self.document) - 1, 0)
        self.first_visible_line = int(clamp(self.first_visible_line + int(lines), 0, highest))
        return self.first_visible_line

    def scroll_columns(self, columns: int) -> int:
        """Scroll horizontally; returns the new first visible column."""
        self.first_visible_column = max(0, self.first_visible_column + int(columns))
        return self.first_visible_column

    def scroll_to_line(self, line: int, align: str = "middle") -> None:
        """Put *line* at the top, middle or bottom of the view."""
        line = int(clamp(int(line), 0, len(self.document) - 1))
        if align == "top":
            self.first_visible_line = line
        elif align == "bottom":
            self.first_visible_line = max(0, line - self.visible_lines + 1)
        else:
            self.first_visible_line = max(0, line - self.visible_lines // 2)

    def _follow_main(self) -> None:
        """Scroll so the main caret is on screen, vertically and horizontally."""
        pos = self.cursors.main.end
        if pos.line < self.first_visible_line:
            self.first_visible_line = pos.line
        elif pos.line >= self.first_visible_line + self.visible_lines:
            self.first_visible_line = pos.line - self.visible_lines + 1
        column = self._column_of(pos)
        if column < self.first_visible_column:
            self.first_visible_column = column
        elif column >= self.first_visible_column + self.visible_columns:
            self.first_visible_column = column - self.visible_columns + 1

    def _column_of(self, pos: Pos) -> int:
        """The screen column of a position, with tabs expanded."""
        text = self.document.lines[pos.line].text[: pos.index]
        column = 0
        for char in text:
            if char == "\t":
                column += self.config.tab_size - (column % self.config.tab_size)
            else:
                column += 1
        return column

    def _index_at_column(self, line: int, column: int) -> int:
        """Inverse of :meth:`_column_of`: which character a screen column is in."""
        text = self.document.lines[line].text
        at = 0
        for index, char in enumerate(text):
            width = (
                self.config.tab_size - (at % self.config.tab_size) if char == "\t" else 1
            )
            if at + width > column:
                return index
            at += width
        return len(text)

    # -- keys ----------------------------------------------------------- #
    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Handle one key press.

        Parameters
        ----------
        key : int
            One of :mod:`cmtk.keys`' ``KEY_*`` constants, or ``0`` for a
            key that only carries text.
        text : str, optional
            What the key typed, if anything.
        modifiers : int, optional
            A mask of :mod:`cmtk.events`' ``*_MODIFIER`` values.

        Returns
        -------
        bool
            Whether the editor consumed it. Everything is consumed while the
            editor has the caret, for the reason :class:`.text_field.TextField`
            gives: a key that falls through to a viewport shortcut while
            someone is typing is worse than one that does nothing.
        """
        from ..events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER
        from ..keys import (
            KEY_BACKSPACE,
            KEY_DELETE,
            KEY_DOWN,
            KEY_END,
            KEY_ENTER,
            KEY_ESCAPE,
            KEY_HOME,
            KEY_LEFT,
            KEY_PAGE_DOWN,
            KEY_PAGE_UP,
            KEY_RETURN,
            KEY_RIGHT,
            KEY_TAB,
            KEY_UP,
        )

        shift = bool(modifiers & SHIFT_MODIFIER)
        # Command on a Mac, Control elsewhere -- either is accepted, as the
        # command line accepts either, because the same intent arrives spelled
        # two ways depending on the host.
        command = bool(modifiers & (CONTROL_MODIFIER | META_MODIFIER))
        alt = bool(modifiers & ALT_MODIFIER)
        word = alt or (command and not _is_mac_style(modifiers))

        if command and text:
            letter = text.lower()
            if letter == "a":
                self.select_all()
                return True
            if letter == "c":
                self.copy()
                return True
            if letter == "x":
                self.cut()
                return True
            if letter == "v":
                self.paste()
                return True
            if letter == "z":
                self.redo() if shift else self.undo()
                return True
            if letter == "y":
                self.redo()
                return True
            if letter == "d":
                self.add_next_occurrence()
                return True
            if letter == "l":
                self.select_line(self.cursors.main.end.line)
                return True
            if letter == "/":
                self.toggle_comments()
                return True

        if key in (KEY_RETURN, KEY_ENTER):
            self.newline()
            return True
        if key == KEY_BACKSPACE:
            self.backspace()
            return True
        if key == KEY_DELETE:
            self.delete()
            return True
        if key == KEY_TAB:
            if self.cursors.any_has_selection or shift:
                self.deindent_lines() if shift else self.indent_lines()
            else:
                self.insert(
                    " " * self.config.tab_size
                    if self.config.insert_spaces_on_tabs
                    else "\t"
                )
            return True
        if key == KEY_LEFT:
            self.move_left(shift, word)
            return True
        if key == KEY_RIGHT:
            self.move_right(shift, word)
            return True
        if key == KEY_UP:
            self.move_lines(down=False) if alt else self.move_up(shift)
            return True
        if key == KEY_DOWN:
            self.move_lines(down=True) if alt else self.move_down(shift)
            return True
        if key == KEY_PAGE_UP:
            self.move_up(shift, max(self.visible_lines - 1, 1))
            return True
        if key == KEY_PAGE_DOWN:
            self.move_down(shift, max(self.visible_lines - 1, 1))
            return True
        if key == KEY_HOME:
            self.move_home(shift, command)
            return True
        if key == KEY_END:
            self.move_end(shift, command)
            return True
        if key == KEY_ESCAPE:
            self.cursors.clear_additional()
            return True

        typed = "".join(ch for ch in str(text) if ch >= " " and ch != "\x7f")
        if typed and not command:
            self._type(typed)
        return True

    def _type(self, typed: str) -> None:
        """Insert typed text, completing brackets and quotes when configured."""
        if (
            self.config.complete_paired_glyphs
            and len(typed) == 1
            and typed in "([{\"'"
            and not self.cursors.any_has_selection
        ):
            closer = {"(": ")", "[": "]", "{": "}"}.get(typed, typed)
            self.insert(typed + closer)
            self.move_left()
            return
        self.insert(typed)

    # -- mouse ---------------------------------------------------------- #
    def position_at(self, px: float, py: float) -> Pos:
        """Which document position a point on screen is over."""
        row = int((py - self._body_y) // max(self._line_h, 1e-6))
        line = int(clamp(self.first_visible_line + row, 0, len(self.document) - 1))
        column = self.first_visible_column + int(
            max(0.0, px - self._text_x) / max(self._glyph_w, 1e-6) + 0.5
        )
        return Pos(line, self._index_at_column(line, max(column, 0)))

    def press(
        self,
        px: float,
        py: float,
        x: float,
        y: float,
        w: float,
        h: float,
        modifiers: int = 0,
        clicks: int = 1,
    ) -> Pos | None:
        """Handle a press. Returns where the caret went, or ``None`` if outside.

        Parameters
        ----------
        px, py : float
            The pointer.
        x, y, w, h : float
            The box the editor was drawn in.
        modifiers : int, optional
            Shift extends the selection; alt (or command) adds a caret.
        clicks : int, optional
            2 selects a word, 3 selects a line -- taken as an argument because
            the chrome has no clock to derive it from, which is the rule this
            package's docstring states.
        """
        from ..events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER

        if not hit(px, py, x, y, w, h):
            return None
        if self.vbar.press(px, py):
            self.first_visible_line = self.vbar.top
            self._bar_drag = True
            return self.cursors.current.end
        where = self.position_at(px, py)
        if clicks >= 3:
            self.select_line(where.line)
        elif clicks == 2:
            self.select_word_at(where)
        elif modifiers & SHIFT_MODIFIER:
            self.cursors.current.update(where, keep_selection=True)
        elif modifiers & (ALT_MODIFIER | CONTROL_MODIFIER | META_MODIFIER):
            self.cursors.add_cursor(where)
        else:
            self.cursors.set_cursor(where)
        self._dragging = True
        return where

    def drag(self, px: float, py: float, x: float, y: float, w: float, h: float) -> Pos | None:
        """Extend the selection while the button is down.

        Dragging past the top or bottom edge scrolls, because a selection that
        stops at the edge of the box cannot reach the rest of the file.
        """
        if getattr(self, "_bar_drag", False):
            self.vbar.drag_to(py)
            self.first_visible_line = self.vbar.top
            return self.cursors.current.end
        if not self._dragging:
            return None
        if py < self._body_y:
            self.scroll(-1)
        elif py > self._body_y + self.visible_lines * self._line_h:
            self.scroll(1)
        where = self.position_at(px, py)
        self.cursors.current.update(where, keep_selection=True)
        return where

    def release(self) -> None:
        """Stop dragging (the selection, or the scrollbar's thumb)."""
        self._dragging = False
        self._bar_drag = False
        self.vbar.held = False

    # -- drawing -------------------------------------------------------- #
    def draw(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Paint the gutter, the text, the selections and the carets.

        Parameters
        ----------
        p : Painter
            The surface.
        x, y, w, h : float
            The box to draw in.
        """
        self.colorizer.update(self.config, self.document)
        if self.document.updated:
            self.bracketeer.update(self.config, self.document)
            self.document.updated = False

        self._line_h = max(p.line_height() * self.config.line_spacing, 1.0)
        self._glyph_w = max(p.text_width("W"), 1.0)
        self._body_y = y
        digits = len(str(max(len(self.document), 1)))
        gutter = (
            (digits + self.config.left_margin + self.config.text_margin) * self._glyph_w
            if self.config.show_line_numbers
            else self.config.text_margin * self._glyph_w
        )
        self._text_x = x + gutter
        self.visible_lines = max(int(h / self._line_h), 1)
        # A scrollbar down the right when the file is taller than the box --
        # a text editor with no bar shows a file with no bottom.
        bar_w = self.vbar.width if len(self.document) > self.visible_lines else 0.0
        self.visible_columns = max(int((w - gutter - bar_w) / self._glyph_w), 1)
        self.first_visible_line = int(
            clamp(self.first_visible_line, 0, max(len(self.document) - 1, 0))
        )
        self.vbar.top = self.first_visible_line
        self.vbar.clamp(len(self.document), self.visible_lines)

        p.fill_rect(x, y, w, h, FRAME_BG)
        p.push_clip(x, y, w, h)

        caret_lines = {one.end.line for one in self.cursors}
        active = self.bracketeer.at(self.cursors.main.end) or self.bracketeer.enclosing(
            self.cursors.main.end
        )

        for row in range(self.visible_lines):
            number = self.first_visible_line + row
            if number >= len(self.document):
                break
            line = self.document.lines[number]
            row_y = y + row * self._line_h

            if number in caret_lines:
                p.fill_rect(x, row_y, w, self._line_h, (255, 255, 255, 12))
            self._draw_selections(p, number, row_y, w, x)
            if self.config.show_line_numbers:
                self._draw_line_number(p, line, number, x, row_y, gutter)
            self._draw_line(p, line, number, row_y, w, x, gutter, active)

        self._draw_carets(p, x, y, w, h)
        if bar_w:
            self.vbar.draw(p, x + w - bar_w, y, h)
        p.pop_clip()
        p.stroke_rect(x, y, w, h, BORDER)

    def _draw_line_number(
        self, p: Painter, line: Line, number: int, x: float, row_y: float, gutter: float
    ) -> None:
        """Draw one right-aligned line number, in the marker's colour if any."""
        current = any(one.end.line == number for one in self.cursors)
        colour: Colour = (224, 224, 240) if current else (128, 128, 144)
        if line.marker is not None:
            colour = line.marker[0]
        p.text(
            x,
            row_y,
            gutter - self.config.text_margin * self._glyph_w,
            self._line_h,
            ALIGN_RIGHT | ALIGN_VCENTER,
            str(number + 1),
            colour,
        )

    def _draw_selections(
        self, p: Painter, number: int, row_y: float, w: float, x: float
    ) -> None:
        """Fill the selected span of one row, for every caret that covers it."""
        for one in self.cursors:
            low, high = one.selection()
            if low == high or not (low.line <= number <= high.line):
                continue
            start = self._column_of(low) if number == low.line else 0
            if number == high.line:
                end = self._column_of(high)
            else:
                end = self._column_of(self.document.end_of_line(Pos(number, 0))) + 1
            left = self._text_x + (start - self.first_visible_column) * self._glyph_w
            width = max((end - start) * self._glyph_w, self._glyph_w * 0.3)
            left = max(left, self._text_x)
            if left < x + w:
                p.fill_rect(left, row_y, min(width, x + w - left), self._line_h,
                            (32, 96, 160, 160))

    def _draw_line(
        self,
        p: Painter,
        line: Line,
        number: int,
        row_y: float,
        w: float,
        x: float,
        gutter: float,
        active: BracketPair | None,
    ) -> None:
        """Draw one row's characters, one painter call per run.

        A run is a stretch of equal colour **and** equal whitespace-ness. Two
        reasons it is not just equal colour. A tab is a *width*, not a glyph,
        so it has to be measured to its stop whether or not it is being shown
        -- and a run mixing a tab with letters would either draw the tab as a
        missing glyph or, routed wholesale to the whitespace path, drop the
        letters. And a document with **no language** has one colour for the
        whole line, so a space in it is only distinguishable by being a space:
        keying the whitespace marks off the colouriser's token instead is why
        "show spaces" silently did nothing until a language was chosen.

        A call per *character* would be one quad batch per glyph and is what
        makes a naive port of an immediate-mode editor slow; a call per run is
        typically a handful per line.
        """
        text = line.text
        if not text:
            return
        marker_colour = line.marker[1] if line.marker is not None else None
        column = 0
        index = 0
        while index < len(text):
            token = line.colours[index] if index < len(line.colours) else 0
            blank = text[index] in " \t"
            run = index
            while (
                run < len(text)
                and (line.colours[run] if run < len(line.colours) else 0) == token
                and (text[run] in " \t") == blank
            ):
                run += 1
            piece = text[index:run]
            if blank:
                column = self._draw_whitespace(p, piece, column, row_y, x, w)
            else:
                colour = marker_colour or self.palette[min(token, len(self.palette) - 1)]
                left = self._text_x + (column - self.first_visible_column) * self._glyph_w
                if left + len(piece) * self._glyph_w > x + gutter and left < x + w:
                    p.text(
                        max(left, x + gutter),
                        row_y,
                        x + w - max(left, x + gutter),
                        self._line_h,
                        ALIGN_LEFT | ALIGN_VCENTER,
                        piece if left >= x + gutter else piece[
                            int((x + gutter - left) / self._glyph_w):
                        ],
                        colour,
                    )
                column += len(piece)
            index = run

        if active is not None and self.config.show_matching_brackets:
            for pos in (active.start, active.end):
                if pos.line != number:
                    continue
                left = (
                    self._text_x
                    + (self._column_of(pos) - self.first_visible_column) * self._glyph_w
                )
                if left >= x + gutter:
                    p.stroke_rect(left, row_y, self._glyph_w, self._line_h, (140, 140, 140))

    def _draw_whitespace(
        self, p: Painter, piece: str, column: int, row_y: float, x: float, w: float
    ) -> int:
        """Draw a run of spaces and tabs; returns the column after it."""
        for char in piece:
            width = (
                self.config.tab_size - (column % self.config.tab_size)
                if char == "\t"
                else 1
            )
            show = (self.config.show_tabs if char == "\t" else self.config.show_spaces)
            if show:
                left = self._text_x + (column - self.first_visible_column) * self._glyph_w
                if self._text_x <= left < x + w:
                    p.text(
                        left,
                        row_y,
                        width * self._glyph_w,
                        self._line_h,
                        ALIGN_LEFT | ALIGN_VCENTER,
                        _TAB_MARK if char == "\t" else _SPACE_MARK,
                        self.palette[int(Token.WHITESPACE)],
                    )
            column += width
        return column

    def _draw_carets(self, p: Painter, x: float, y: float, w: float, h: float) -> None:
        """Draw every caret that is on screen."""
        if not self.config.carets_visible:
            return
        for one in self.cursors:
            pos = one.end
            row = pos.line - self.first_visible_line
            if not 0 <= row < self.visible_lines:
                continue
            left = (
                self._text_x
                + (self._column_of(pos) - self.first_visible_column) * self._glyph_w
            )
            if not self._text_x - self._glyph_w <= left <= x + w:
                continue
            p.fill_rect(
                left,
                y + row * self._line_h + self._line_h * 0.1,
                max(1.0, self._glyph_w * 0.12),
                self._line_h * 0.8,
                TEXT if one.main else (200, 200, 210),
            )


def _is_mac_style(modifiers: int) -> bool:
    """Whether the modifier mask carries Command rather than Control.

    On a Mac, Command is the shortcut modifier and **Option** is the
    word-movement one; elsewhere Control is both. Reading the mask is how the
    editor tells which convention it is being driven under, instead of asking
    the platform -- which would be wrong in the browser build, where the host
    is the one that knows.
    """
    from ..events import META_MODIFIER

    return bool(modifiers & META_MODIFIER)
